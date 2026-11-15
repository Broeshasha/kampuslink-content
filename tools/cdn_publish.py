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

The script ASKS for what it needs once: public values go to tools/cdn_local.json (not in git), keys go to the
Windows Credential Manager when "pip install keyring" was done (else typed hidden each run). --forget-keys deletes them. Environment variables with these names still win:
  KAMPUS_SUPABASE_URL, KAMPUS_SERVICE_KEY                       (always: reads the export)
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET  (only with --upload)
Needs backend file 54 (cdn_module_export, cdn_set_path).
"""
import argparse, datetime, hashlib, hmac, json, os, secrets, sys, time, urllib.error, urllib.parse, urllib.request

PUBLIC_BASE = "https://files.kampus-link.com/"
UA = {"User-Agent": "KampusLink-publisher/1.0"}   # Cloudflare answers 403 to the default Python-urllib agent
CACHE = "public, max-age=31536000, immutable"


def canon(obj):
    """Stable bytes for hashing (same object = same file)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------- Supabase (service role)
def rpc(name, args):
    url = os.environ.get("KAMPUS_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("KAMPUS_SERVICE_KEY", "").strip()
    if not url or not key:
        raise SystemExit("Set KAMPUS_SUPABASE_URL and KAMPUS_SERVICE_KEY in this PowerShell session first.")
    headers = {"apikey": key, "Content-Type": "application/json", **UA}
    if not key.startswith("sb_"):          # legacy JWT keys also go in Authorization; new sb_ keys only in apikey
        headers["Authorization"] = f"Bearer {key}"
    body = json.dumps(args).encode()
    for attempt in range(4):
        req = urllib.request.Request(f"{url}/rest/v1/rpc/{name}", data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")[:300]
            if "PGRST303" in text and attempt < 3:      # clock gap between Supabase servers: wait and retry
                print(f"  {name}: Supabase clock gap (PGRST303), retry in 10 s...")
                time.sleep(10)
                continue
            kind = "sb_secret" if key.startswith("sb_secret_") else ("sb_publishable (WRONG key)" if key.startswith("sb_publishable_")
                    else ("legacy JWT" if key.startswith("eyJ") else "unknown format"))
            raise SystemExit(f"{name} failed: HTTP {e.code} {text}\n  key type sent: {kind}, length {len(key)}")


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
    req = urllib.request.Request(PUBLIC_BASE + key, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise SystemExit(f"Reading {PUBLIC_BASE}{key} gave HTTP {e.code}. Check in Cloudflare: the bucket's Custom Domain is "
                         f"files.kampus-link.com, and Security -> Bots / WAF do not block it. Nothing was published.")


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


LOCAL_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cdn_local.json")  # NOT secrets, not in git
PUBLIC_NAMES = {"KAMPUS_SUPABASE_URL": "Supabase project URL (https://....supabase.co)",
                "R2_ACCOUNT_ID": "Cloudflare account ID", "R2_BUCKET": "R2 bucket name"}
SECRET_NAMES = {"KAMPUS_SERVICE_KEY": "Supabase SECRET key", "R2_ACCESS_KEY_ID": "R2 Access Key ID",
                "R2_SECRET_ACCESS_KEY": "R2 Secret Access Key"}


KEYRING_SERVICE = "kampuslink-cdn-publish"


def _keyring():
    try:
        import keyring
        return keyring
    except ImportError:
        return None


def forget_keys():
    kr = _keyring()
    if not kr:
        print("keyring not installed: nothing saved.")
        return
    for n in SECRET_NAMES:
        try:
            kr.delete_password(KEYRING_SERVICE, n)
        except Exception:
            pass
    print("Saved keys deleted from Windows Credential Manager.")


def ask_missing(upload):
    """Public values: tools/cdn_local.json. Secrets: Windows Credential Manager (encrypted for this Windows user)
    when the 'keyring' package is installed, otherwise typed hidden at every run. Never in a file, never in git."""
    import getpass
    try:
        with open(LOCAL_CFG, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        saved = {}
    need_public = ["KAMPUS_SUPABASE_URL"] + (["R2_ACCOUNT_ID", "R2_BUCKET"] if upload else [])
    need_secret = ["KAMPUS_SERVICE_KEY"] + (["R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"] if upload else [])
    changed = False
    for n in need_public:
        if not os.environ.get(n):
            v = saved.get(n) or input(PUBLIC_NAMES[n] + ": ").strip()
            if n not in saved:
                saved[n] = v
                changed = True
            os.environ[n] = v
    kr = _keyring()
    for n in need_secret:
        if os.environ.get(n):
            continue
        v = kr.get_password(KEYRING_SERVICE, n) if kr else None
        if not v:
            v = getpass.getpass(SECRET_NAMES[n] + " (hidden): ").strip()
            if kr and v:
                kr.set_password(KEYRING_SERVICE, n, v)
                print(f"  saved in Windows Credential Manager ({SECRET_NAMES[n]})")
        os.environ[n] = v
    if changed:
        with open(LOCAL_CFG, "w", encoding="utf-8") as f:
            json.dump(saved, f, indent=1)
        print(f"(remembered the public values in {LOCAL_CFG}; delete the file to change them)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--module-id", default="", help="one id or a comma list")
    ap.add_argument("--out", default="_cdn_out")
    ap.add_argument("--upload", action="store_true", help="ONLY when the senior engineer says go")
    ap.add_argument("--forget-keys", action="store_true", help="delete the saved keys and stop")
    args = ap.parse_args()
    if args.forget_keys:
        forget_keys()
        return
    if not args.module_id.strip():
        raise SystemExit("--module-id is required (e.g. --module-id 1005)")
    ask_missing(args.upload)
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
