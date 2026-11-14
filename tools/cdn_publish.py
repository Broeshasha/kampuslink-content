#!/usr/bin/env python3
"""
KampusLink CDN publisher (CDN-1, FIX_PLAN 3.1)  -  Python 3.9+, standard library only.

Turns one published module into static files for Cloudflare R2 (files.kampus-link.com):
  v1/m/<module>/<version>-<token>/manifest.json   one per published version, never changes
  v1/b/<sha256>.json                              one lesson / extras / practice chapter / exam
Files are named by their content hash: an unchanged lesson keeps its file across versions.

DEFAULT = DRY RUN: files are written to a local folder only (nothing uploaded, database untouched).
  python tools/cdn_publish.py --module-id 3004
  python tools/cdn_publish.py --module-id 3001,3002,3003,3004 --out _cdn_out
--upload (ONLY when the senior engineer says go): upload to R2, read every file back from
files.kampus-link.com and check its hash, THEN cdn_set_path (the publish switch). Any failure =
the switch is not set and phones keep using Supabase.

Environment (type in PowerShell with Read-Host, never save in a file):
  KAMPUS_SUPABASE_URL, KAMPUS_SERVICE_KEY                       (always: reads the export)
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET  (only with --upload)
Needs backend file 54 (cdn_module_export, cdn_set_path).
"""
import argparse, datetime, hashlib, hmac, json, os, secrets, sys, time, urllib.error, urllib.parse, urllib.request

PUBLIC_BASE = "https://files.kampus-link.com/"
CACHE = "public, max-age=31536000, immutable"


def canon(obj):
    """Stable bytes for hashing (same object = same file)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------- Supabase (service role)
def rpc(name, args):
    url = os.environ.get("KAMPUS_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("KAMPUS_SERVICE_KEY", "")
    if not url or not key:
        raise SystemExit("Set KAMPUS_SUPABASE_URL and KAMPUS_SERVICE_KEY in this PowerShell session first.")
    req = urllib.request.Request(f"{url}/rest/v1/rpc/{name}", data=json.dumps(args).encode(), method="POST",
                                 headers={"apikey": key, "Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{name} failed: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}")


# ---------------------------------------------------------------- R2 (S3 API, AWS SigV4)
def _hm(k, m):
    return hmac.new(k, m.encode("utf-8"), hashlib.sha256).digest()


def sigv4_headers(method, host, path, body, access_key, secret_key, region="auto", service="s3",
                  extra=None, now=None):
    """Signed headers for one S3 request (path must already be URL-encoded)."""
    now = now or datetime.datetime.utcnow()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body).hexdigest()
    headers = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    for k, v in (extra or {}).items():
        headers[k.lower()] = v
    names = sorted(headers)
    canonical = "\n".join([method, path, "", "".join(f"{n}:{headers[n].strip()}\n" for n in names),
                           ";".join(names), payload_hash])
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    k = _hm(_hm(_hm(_hm(("AWS4" + secret_key).encode(), day), region), service), "aws4_request")
    sig = hmac.new(k, to_sign.encode(), hashlib.sha256).hexdigest()
    headers["authorization"] = (f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
                                f"SignedHeaders={';'.join(names)}, Signature={sig}")
    return headers


class R2:
    def __init__(self):
        need = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"]
        miss = [n for n in need if not os.environ.get(n)]
        if miss:
            raise SystemExit("For --upload set first: " + ", ".join(miss))
        self.host = f"{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
        self.bucket = os.environ["R2_BUCKET"]
        self.ak, self.sk = os.environ["R2_ACCESS_KEY_ID"], os.environ["R2_SECRET_ACCESS_KEY"]

    def put(self, key, body):
        path = "/" + urllib.parse.quote(f"{self.bucket}/{key}")
        h = sigv4_headers("PUT", self.host, path, body, self.ak, self.sk,
                          extra={"content-type": "application/json; charset=utf-8", "cache-control": CACHE})
        req = urllib.request.Request(f"https://{self.host}{path}", data=body, method="PUT", headers=h)
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    if r.status in (200, 201):
                        return
            except urllib.error.HTTPError as e:
                if e.code < 500 or attempt == 3:
                    raise SystemExit(f"R2 upload {key} failed: HTTP {e.code} {e.read().decode('utf-8','replace')[:200]}")
            except urllib.error.URLError:
                if attempt == 3:
                    raise
            time.sleep(2 * (attempt + 1))


def public_get(key):
    try:
        with urllib.request.urlopen(PUBLIC_BASE + key, timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


# ---------------------------------------------------------------- build
def build(export):
    """(files {key: bytes}, manifest dict) for one module export."""
    files = {}

    def add(obj):
        b = canon(obj)
        h = sha(b)
        key = f"v1/b/{h}.json"
        files[key] = b
        return {"path": key, "sha256": h, "bytes": len(b)}

    lessons = []
    for les in export["lessons"]:
        ref = add(les)
        i18n = les.get("i18n") or {}
        lessons.append({
            "id": les["id"], "position": les.get("position"), "unit": les.get("unit"),
            "estimated_minutes": les.get("estimated_minutes"),
            "titles": {lang: (v or {}).get("title") for lang, v in i18n.items()},
            "langs": sorted(i18n.keys()),
            "cards": len(les.get("cards") or []), "questions": len(les.get("questions") or []),
            "rev": ref["sha256"], **ref})
    extras = add({"glossary": export["glossary"], "sets": export["sets"]})
    practice = [{"chapter_ref": p["chapter_ref"], "unit_number": p["unit_number"], "count": len(p["items"]),
                 "rev": None, **add(p["items"])} for p in export["practice"]]
    for p in practice:
        p["rev"] = p["sha256"]
    exams = []
    for x in export["exams"]:
        ref = add(x)
        exams.append({"id": x["id"], "ref": x.get("ref"), "position": x.get("position"),
                      "duration_min": x.get("duration_min"), "total_points": x.get("total_points"),
                      "title": x.get("title"), "exercises": len(x.get("exercises") or []),
                      "rev": ref["sha256"], **ref})
    manifest = {
        "schema": 1, "module": export["module"], "module_id": export["module_id"], "version": export["version"],
        "generated_at": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "lessons": lessons, "extras": {"rev": extras["sha256"], **extras},
        "practice": practice, "exams": exams,
        "files": len(files), "bytes": sum(len(b) for b in files.values()),
    }
    return files, manifest


def write_local(out, files, manifest_key, manifest_bytes):
    for key, b in list(files.items()) + [(manifest_key, manifest_bytes)]:
        p = os.path.join(out, *key.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--module-id", required=True, help="one id or a comma list")
    ap.add_argument("--out", default="_cdn_out")
    ap.add_argument("--upload", action="store_true", help="ONLY when the senior engineer says go")
    args = ap.parse_args()
    ids = [int(x) for x in args.module_id.split(",") if x.strip()]
    r2 = R2() if args.upload else None
    for mid in ids:
        export = rpc("cdn_module_export", {"p_module": mid})
        if not export:
            raise SystemExit(f"module {mid}: not found")
        if not export["lessons"]:
            print(f"module {mid}: no published lessons - skipped")
            continue
        files, manifest = build(export)
        token = secrets.token_hex(8)
        mkey = f"v1/m/{mid}/{export['version']}-{token}/manifest.json"
        mbytes = canon(manifest)
        print(f"\n=== module {mid} v{export['version']}: {len(manifest['lessons'])} lessons, "
              f"{len(manifest['practice'])} practice chapters, {len(manifest['exams'])} exams, "
              f"{manifest['files']} files, {round(manifest['bytes'] / 1024)} KB")
        write_local(args.out, files, mkey, mbytes)
        print(f"  written to {os.path.join(args.out, 'v1')}  (manifest {mkey})")
        if not r2:
            print("  DRY RUN: nothing uploaded, database untouched.")
            continue
        sent = skipped = 0
        for key, b in files.items():
            if public_get(key) == b:          # same hash = same file already there
                skipped += 1
                continue
            r2.put(key, b)
            sent += 1
        r2.put(mkey, mbytes)
        for key, b in list(files.items()) + [(mkey, mbytes)]:   # read back through the public domain
            got = public_get(key)
            if got is None or sha(got) != sha(b):
                raise SystemExit(f"  VERIFY FAILED for {key}: NOT published (phones keep using Supabase).")
        res = rpc("cdn_set_path", {"p_module": mid, "p_version": export["version"], "p_path": mkey})
        print(f"  uploaded {sent}, already there {skipped}; verified; PUBLISHED -> {res}")


if __name__ == "__main__":
    main()
