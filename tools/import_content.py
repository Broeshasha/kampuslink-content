#!/usr/bin/env python3
"""
KampusLink content importer  v3   (Python 3.9+; optional "keyring" to remember the key)

v3 (15 Nov 2026, BAC-UPLOAD): --langs (e.g. ar,en for the bac: no French needed anywhere), --source-lang,
"source" / "based_on" kept on cards, questions, practice and set questions (needs backend file 57),
EVERYTHING is checked before the first write, bac modules (3001-3099) never published without --launch,
settings asked like cdn_publish.py (URL remembered, key in Windows Credential Manager).

Reads a module folder made by the content builder and loads it into Supabase:
  chapter_NN/source.json  -> learn_lessons (episodes) + learn_lesson_i18n (student blocks, SVG inlined)
                             + module_glossary
  chapter_NN/extras.json  -> learn_cards / learn_card_i18n / learn_questions / learn_question_i18n
  chapter_NN/sets.json    -> learn_card_sets                      (--sets, backend file 11)
  --full (backend file 15): figure / option_figures on cards and questions,
  chapter_NN/practice.json -> learn_practice,  exams/exams.json (kl-exams-1.0) -> learn_exam_papers
NOT uploaded: module_terms.json (builder-only).

Safe to run again: lessons are matched by (module_id, position), cards/questions by (lesson, order).
Lessons are created as DRAFT; add --publish to show them to students (bac modules: --publish --launch).

  Dry run (no key, no network, writes nothing):
      python tools\\import_content.py --module-dir mining\\L2\\S3\\843_probabilites_statistiques --module-id 843 --dry-run
  Real run (key only in this PowerShell session):
      $env:KAMPUS_SUPABASE_URL = "https://xxxx.supabase.co"
      $env:KAMPUS_SERVICE_KEY  = "<paste, never save in a file>"
      python tools\\import_content.py --module-dir ... --module-id 843 --chapters 1 --publish
"""
import argparse, copy, json, os, re, sys, urllib.request, urllib.error, urllib.parse

LANGS = ("en", "fr", "ar")          # set from --langs in main()
PRIMARY = "fr"                      # language used for counts, word counts and logs: fr when present, else the first
ML_CODES = {"en", "fr", "ar"}
BAC_IDS = range(3001, 3100)
INTERNAL = {"type_prepared_for", "source_refs", "origin", "rights_status", "source_quality_issues",
            "source_fidelity", "uncertainty_note", "source_notes", "source_pages"}
MIN_BLOCKS, MAX_BLOCKS = 8, 40
warnings, errors = [], []
OPTS = {"full": False}


def warn(m): warnings.append(m)
def err(m): errors.append(m)


def load_json(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{path}: file has a BOM (must be UTF-8 without BOM)")
    return json.loads(raw.decode("utf-8"))


# ---------------------------------------------------------------- localisation
def is_ml(d):
    return (isinstance(d, dict) and 2 <= len(d) <= 3 and set(d) <= ML_CODES
            and all(isinstance(v, (str, list)) for v in d.values()))


def localize(o, lang, where=""):
    """{en,fr,ar} objects -> the string/list of one language; internal fields removed."""
    if is_ml(o):
        if lang not in o:
            warn(f"{where}: missing '{lang}' in multilingual object")
            return o.get(PRIMARY) or o.get("fr") or next(iter(o.values()))
        return o[lang]
    if isinstance(o, dict):
        return {k: localize(v, lang, where) for k, v in o.items() if k not in INTERNAL}
    if isinstance(o, list):
        return [localize(v, lang, where) for v in o]
    return o


def inline_svgs(o, chapter_dir, stats):
    """asset {type:'svg', file:'svg/x.svg'} -> asset {type:'svg', svg:'<svg..>'}"""
    if isinstance(o, dict):
        a = o.get("asset")
        if isinstance(a, dict) and a.get("type") == "svg" and a.get("file"):
            p = os.path.join(chapter_dir, *a["file"].split("/"))
            if not os.path.isfile(p):
                err(f"SVG file missing: {a['file']} ({chapter_dir})")
            else:
                svg = open(p, "r", encoding="utf-8").read()
                if "viewBox" not in svg: err(f"SVG without viewBox: {a['file']}")
                if re.search(r"<script|<style|foreignObject|href\s*=\s*[\"']https?:", svg):
                    err(f"SVG with forbidden content: {a['file']}")
                if len(svg.encode()) > 60_000: warn(f"SVG over 60 KB: {a['file']}")
                a = {k: v for k, v in a.items() if k != "file"}
                a["svg"] = svg
                o["asset"] = a
                stats["svg"] += 1
        for v in o.values():
            inline_svgs(v, chapter_dir, stats)
    elif isinstance(o, list):
        for v in o:
            inline_svgs(v, chapter_dir, stats)


def text_of(block, lang):
    """rough plain text of a block for summaries / word counts"""
    out = []
    def walk(x):
        if isinstance(x, str): out.append(x)
        elif isinstance(x, dict):
            for k, v in x.items():
                if k in ("content", "text", "items", "label", "caption"): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(localize(block, lang))
    return " ".join(out)


# ---------------------------------------------------------------- episodes
def build_units(sections):
    units, cur = [], None
    for sec in sections:
        if sec.get("level", 9) == 0:
            continue                      # chapter title: becomes the unit title, not a block
        has_blocks = cur is not None and any(s.get("blocks") for s in cur)
        if cur is None or (sec.get("level", 9) in (1, 2) and has_blocks):
            cur = []
            units.append(cur)
        cur.append(sec)
    return units


def nblocks(unit): return sum(len(s.get("blocks") or []) for s in unit)


def merge_units(units):
    if not units: return []
    out = [units[0]]
    for u in units[1:]:
        acc = out[-1]
        if nblocks(acc) < MIN_BLOCKS or (nblocks(u) < MIN_BLOCKS and nblocks(acc) + nblocks(u) <= MAX_BLOCKS):
            out[-1] = acc + u
        else:
            out.append(u)
    if len(out) > 1 and nblocks(out[-1]) < MIN_BLOCKS and nblocks(out[-2]) + nblocks(out[-1]) <= MAX_BLOCKS:
        out[-2] = out[-2] + out[-1]
        out.pop()
    return out


def unit_title(unit):
    titles = []
    for s in unit:
        if s.get("level") in (1, 2) and s.get("title"):
            titles.append(s["title"])
    if not titles: titles = [unit[0]["title"]]
    # keep it short: the deepest of the first two
    return titles[0] if len(titles) == 1 else titles[1] if titles[0] != titles[1] and len(titles) > 1 and unit[0].get("level") == 1 else titles[0]


def student_blocks(unit, lang, chapter_dir, stats):
    blocks = []
    for s in unit:
        if s.get("title") and s.get("level", 9) >= 1:
            num = s.get("number")
            blocks.append({"id": "h_" + s["id"], "type": "heading", "level": s["level"],
                           "content": localize(s["title"], lang, s["id"]),
                           **({"number": num} if num else {})})
        for b in s.get("blocks") or []:
            blocks.append(localize(b, lang, b.get("id", "?")))
    inline_svgs(blocks, chapter_dir, stats)
    return blocks


# ---------------------------------------------------------------- extras
def find_lists(o, key, acc):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key and isinstance(v, list): acc.extend(v)
            else: find_lists(v, key, acc)
    elif isinstance(o, list):
        for v in o: find_lists(v, key, acc)
    return acc


def strip_internal(o):
    if isinstance(o, dict): return {k: strip_internal(v) for k, v in o.items() if k not in INTERNAL}
    if isinstance(o, list): return [strip_internal(v) for v in o]
    return o


def inlined(o, cdir, stats):
    """deep copy without internal fields, SVG files inlined (asset.file -> asset.svg)"""
    if o is None: return None
    o = strip_internal(json.loads(json.dumps(o)))
    holder = {"x": o}
    inline_svgs(holder, cdir, stats)
    return holder["x"]


def item_figures(it, cdir, stats):
    fig = it.get("figure")
    if fig is not None and "asset" not in fig: fig = {"asset": fig}
    return inlined(fig, cdir, stats), inlined(it.get("option_figures"), cdir, stats)


# ---------------------------------------------------------------- REST
class Rest:
    def __init__(self, url, key):
        self.base = url.rstrip("/") + "/rest/v1/"
        self.h = {"apikey": key, "Content-Type": "application/json"}
        if not key.startswith("sb_"):
            self.h["Authorization"] = "Bearer " + key   # legacy JWT keys only; new sb_secret keys go in apikey only

    def call(self, method, table, body=None, params=None, prefer=None):
        u = self.base + table + ("?" + urllib.parse.urlencode(params, safe=",.()*") if params else "")
        h = dict(self.h)
        if prefer: h["Prefer"] = prefer
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        req = urllib.request.Request(u, data=data, headers=h, method=method)
        import time
        for attempt in range(8):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    txt = r.read().decode("utf-8")
                    return json.loads(txt) if txt else None
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 7:
                    print(f"  server busy (HTTP {e.code}), retry {attempt + 1}/7 ..."); time.sleep(5 * (attempt + 1)); continue
                raise SystemExit(f"\nSTOP: {method} {table} -> HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:600]}")
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
                if attempt < 7:
                    print(f"  network hiccup ({e}), retry {attempt + 1}/7 ..."); time.sleep(5 * (attempt + 1)); continue
                raise SystemExit(f"\nSTOP: network failed 8 times ({e}). Check the internet and run again (safe to repeat).")


def upsert(rest, table, rows, conflict):
    if rows:
        rest.call("POST", table, rows, {"on_conflict": conflict}, "resolution=merge-duplicates,return=minimal")


# ---------------------------------------------------------------- chapter
def process_chapter(cdir, module_id, rest, args, chap_no):
    name = os.path.basename(cdir)
    src = load_json(os.path.join(cdir, "source.json"))
    ch = src["chapter"]
    sections = ch["sections"]
    stats = {"svg": 0}
    units = merge_units(build_units(sections))
    plan = []
    block_to_ep = {}
    for i, u in enumerate(units, 1):
        for s in u:
            for b in s.get("blocks") or []:
                block_to_ep[b["id"]] = i
        plan.append({"idx": i, "unit": u, "title": unit_title(u)})

    ids = [b["id"] for s in sections for b in (s.get("blocks") or [])]
    if len(ids) != len(set(ids)): err(f"{name}: duplicate block ids")

    # extras
    cards, questions = [], []
    ep = os.path.join(cdir, "extras.json")
    if os.path.isfile(ep):
        ex = load_json(ep)
        find_lists(ex, "cards", cards)
        find_lists(ex, "questions", questions)
    per_ep = {p["idx"]: {"cards": [], "questions": []} for p in plan}
    orphans = 0
    for kind, items in (("cards", cards), ("questions", questions)):
        for it in items:
            e = block_to_ep.get(it.get("source_block"))
            if e is None:
                orphans += 1
                e = 1
            per_ep[e][kind].append(it)
    if orphans: warn(f"{name}: {orphans} cards/questions have no known source_block (put in episode 1)")
    if OPTS["full"]:
        fst = {"svg": 0}
        for it in cards + questions:
            f, of = item_figures(it, cdir, fst)
            if of is not None and len(of) != len(((it.get("options") or {}).get(PRIMARY)) or []):
                err(f"{name}: question {it.get('id')} option_figures count differs from options")
        print(f"  figures on cards/questions: {fst['svg']} SVG")

    print(f"\n=== {name}: {len(sections)} sections, {len(ids)} blocks -> {len(plan)} episodes; "
          f"{len(cards)} cards, {len(questions)} questions; source keys: {sorted(ch.keys())}")
    result = []
    for p in plan:
        i = p["idx"]
        blocks = {l: student_blocks(p["unit"], l, cdir, stats if l == LANGS[0] else {"svg": 0}) for l in LANGS}
        words = len(" ".join(text_of(b, PRIMARY) for s in p["unit"] for b in (s.get("blocks") or [])).split())
        mins = max(1, round(words / 180))
        first_text = next((text_of(b, PRIMARY) for s in p["unit"] for b in (s.get("blocks") or [])
                           if b.get("type") in ("paragraph", "definition")), "")
        kb = {l: round(len(json.dumps(blocks[l], ensure_ascii=False).encode()) / 1024) for l in LANGS}
        print(f"  ep{i}: {nblocks(p['unit']):>3} blocks, ~{mins} min, "
              f"{len(per_ep[i]['cards'])} cards, {len(per_ep[i]['questions'])} questions, KB {kb}  | "
              f"{localize(p['title'], PRIMARY)}")
        result.append((p, blocks, mins, per_ep[i]))
    print(f"  SVG inlined: {stats['svg']}")

    glossary = [g for g in (ch.get("glossary") or [])]
    if args.dry_run:
        return result, glossary

    # --------------------------- write
    position_base = chap_no * 100
    touched = []
    for p, blocks, mins, extras in result:
        pos = position_base + p["idx"]
        ex = rest.call("GET", "learn_lessons", params={"module_id": f"eq.{module_id}", "position": f"eq.{pos}", "select": "id"})
        fields = {"module_id": module_id, "position": pos, "source_lang": OPTS["source_lang"], "generated_by": "kampus-content-ai",
                  "needs_review": False, "review_reason": None, "rights_status": "own_work",
                  "chapter_ref": name, "unit_number": chap_no, "unit_title": ch.get("title") or {},
                  "estimated_minutes": mins}
        if ex:
            lid = ex[0]["id"]
            rest.call("PATCH", "learn_lessons", fields, {"id": f"eq.{lid}"}, "return=minimal")
        else:
            fields["status"] = "draft"
            lid = rest.call("POST", "learn_lessons", fields, prefer="return=representation")[0]["id"]
        touched.append(lid)
        rows = []
        for l in LANGS:
            summ = re.sub(r"\s+", " ", next((text_of(b, l) for s in p["unit"] for b in (s.get("blocks") or [])
                                              if b.get("type") in ("paragraph", "definition")), ""))[:280]
            rows.append({"lesson_id": lid, "lang": l, "title": localize(p["title"], l), "summary": summ,
                         "body_md": "", "key_terms": [], "blocks": blocks[l]})
        upsert(rest, "learn_lesson_i18n", rows, "lesson_id,lang")
        write_cards(rest, lid, extras["cards"], name, cdir)
        write_questions(rest, lid, extras["questions"], name, cdir)
        print(f"  written ep{p['idx']} -> lesson {lid}")
    return touched, glossary


def tag(chap, c):
    k = c.get("concept")
    return None if not k else (k if ":" in k else f"{chap}:{k}")


def diff(c):
    d = c.get("difficulty")
    return d if d in (1, 2, 3) else None


def bac_refs(it):
    """Real bac item -> "source"; reworded drill -> "based_on" (never shown as bac). null when absent."""
    return {"source": strip_internal(it.get("source")) if isinstance(it.get("source"), dict) else None,
            "based_on": strip_internal(it.get("based_on")) if isinstance(it.get("based_on"), dict) else None}


def write_cards(rest, lid, cards, chap="", cdir=""):
    old = rest.call("GET", "learn_cards", params={"lesson_id": f"eq.{lid}", "order": "position", "select": "id,position"}) or []
    i18n = []
    for i, c in enumerate(cards):
        body = {"lesson_id": lid, "position": i, "concept": tag(chap, c), "difficulty": diff(c), "card_kind": c.get("kind"),
                **bac_refs(c)}
        if OPTS["full"]: body["figure"] = item_figures(c, cdir, {"svg": 0})[0]
        if i < len(old):
            cid = old[i]["id"]
            rest.call("PATCH", "learn_cards", body, {"id": f"eq.{cid}"}, "return=minimal")
        else: cid = rest.call("POST", "learn_cards", body, prefer="return=representation")[0]["id"]
        for l in LANGS:
            i18n.append({"card_id": cid, "lang": l, "front": localize(c["front"], l), "back": localize(c["back"], l)})
    for o in old[len(cards):]:
        rest.call("DELETE", "learn_cards", params={"id": f"eq.{o['id']}"}, prefer="return=minimal")
    upsert(rest, "learn_card_i18n", i18n, "card_id,lang")


def write_questions(rest, lid, qs, chap="", cdir=""):
    old = rest.call("GET", "learn_questions", params={"lesson_id": f"eq.{lid}", "order": "position", "select": "id,position"}) or []
    i18n = []
    for i, q in enumerate(qs):
        kind = q.get("kind", "mcq")
        body = {"lesson_id": lid, "kind": kind, "correct_index": q["correct_index"], "position": i,
                "concept": tag(chap, q), "difficulty": diff(q), **bac_refs(q)}
        if OPTS["full"]:
            body["figure"], body["option_figures"] = item_figures(q, cdir, {"svg": 0})
        if i < len(old):
            qid = old[i]["id"]
            rest.call("PATCH", "learn_questions", body, {"id": f"eq.{qid}"}, "return=minimal")
        else:
            qid = rest.call("POST", "learn_questions", body, prefer="return=representation")[0]["id"]
        for l in LANGS:
            i18n.append({"question_id": qid, "lang": l, "prompt": localize(q["prompt"], l),
                         "options": localize(q["options"], l), "explanation": localize(q["explanation"], l)})
    for o in old[len(qs):]:
        rest.call("DELETE", "learn_questions", params={"id": f"eq.{o['id']}"}, prefer="return=minimal")
    upsert(rest, "learn_question_i18n", i18n, "question_id,lang")



# ---------------------------------------------------------------- carousel sets (needs backend file 11)
def convert_slide(sl, cdir, stats):
    """builder slide -> app slide: {id, role, title?, content?, highlights?, prompt?, options?[{..}], correct_index?, explanation?, figure?}"""
    out = {k: v for k, v in sl.items() if k not in INTERNAL and k not in ("question", "figure")}
    q = sl.get("question")
    if q:
        out["prompt"] = q.get("prompt")
        o = q.get("options") or {}
        n = len(o.get(PRIMARY, []))
        out["options"] = [{l: o[l][i] for l in LANGS if l in o} for i in range(n)]
        out["correct_index"] = q.get("correct_index")
        out["explanation"] = q.get("explanation")
        for k, v in bac_refs(q).items():
            if v is not None: out[k] = v
    fig = sl.get("figure")
    if fig:
        fig = json.loads(json.dumps(fig))
        holder = {"asset": fig.get("asset")} if "asset" in fig else {"asset": fig}
        inline_svgs(holder, cdir, stats)
        out["figure"] = fig
    return out


def process_sets(cdir, module_id, rest, args, chap_no):
    sp = os.path.join(cdir, "sets.json")
    if not os.path.isfile(sp): return 0
    data = load_json(sp)
    sets = find_lists(data, "sets", []) or (data if isinstance(data, list) else [])
    name = os.path.basename(cdir)
    stats = {"svg": 0}
    n = 0
    for i, st in enumerate(sets, 1):
        slides = [convert_slide(sl, cdir, stats) for sl in st.get("slides", [])]
        if not 3 <= len(slides) <= 8: warn(f"{name}: set {st.get('id')} has {len(slides)} slides (expected 3-8)")
        row = {"module_id": module_id, "ref": f"{name}/{st.get('id', i)}", "position": chap_no * 100 + i,
               "kind": st.get("kind", "mystery"), "concept": st.get("concept"), "difficulty": st.get("difficulty"),
               "title": st.get("title") or {}, "slides": slides,
               "status": "published" if args.publish else "draft", "rights_status": "own_work"}
        n += 1
        if not args.dry_run:
            upsert(rest, "learn_card_sets", [row], "module_id,ref")
    print(f"  {name}: {n} carousel sets ({stats['svg']} SVG inlined)" + ("" if args.dry_run else " written"))
    return n


# ---------------------------------------------------------------- practice + exams (needs backend file 15, flag --full)
def now_iso():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def archive_missing(rest, table, module_id, keep_refs, extra_filter=None):
    params = {"module_id": f"eq.{module_id}", "status": "neq.archived", "select": "id,ref"}
    if extra_filter: params.update(extra_filter)
    for o in rest.call("GET", table, params=params) or []:
        if o["ref"] not in keep_refs:
            rest.call("PATCH", table, {"status": "archived"}, {"id": f"eq.{o['id']}"}, "return=minimal")
            print(f"  archived old {table} row {o['ref']}")


def process_practice(cdir, module_id, rest, args, chap_no):
    pp = os.path.join(cdir, "practice.json")
    if not os.path.isfile(pp): return 0
    data = load_json(pp)
    probs = find_lists(data, "problems", []) or find_lists(data, "practice", []) or (data if isinstance(data, list) else [])
    name = os.path.basename(cdir)
    stats = {"svg": 0}
    rows, seen = [], set()
    for i, p in enumerate(probs, 1):
        pid = str(p.get("id") or i)
        if pid in seen: err(f"{name}: practice id {pid} repeated")
        seen.add(pid)
        parts = p.get("parts") or []
        if not parts: err(f"{name}: practice {pid} has no parts")
        for pt in parts:
            if not pt.get("solution_steps") or not pt.get("final_answer"):
                err(f"{name}: practice {pid} part {pt.get('id')} needs solution_steps and final_answer")
        for f in ("title", "statement"):
            if not is_ml(p.get(f) or {}): warn(f"{name}: practice {pid} {f} is not a language object")
        fig = p.get("figure")
        if fig is not None and "asset" not in fig: fig = {"asset": fig}
        rows.append({"module_id": module_id, "chapter_ref": name, "unit_number": chap_no, "ref": f"{name}/{pid}",
                     "position": chap_no * 100 + i, "difficulty": diff(p),
                     "concepts": [tag(name, {"concept": c}) for c in (p.get("concepts") or []) if c],
                     "title": strip_internal(p.get("title") or {}), "statement": strip_internal(p.get("statement") or {}),
                     "figure": inlined(fig, cdir, stats), "table_data": inlined(p.get("table"), cdir, stats),
                     "parts": inlined(parts, cdir, stats), **bac_refs(p),
                     "status": "published" if args.publish else "draft", "rights_status": "own_work", "updated_at": now_iso()})
    print(f"  {name}: {len(rows)} practice problems ({stats['svg']} SVG inlined)" + ("" if args.dry_run else " written"))
    if not args.dry_run and not errors:
        upsert(rest, "learn_practice", rows, "module_id,ref")
        archive_missing(rest, "learn_practice", module_id, {r["ref"] for r in rows}, {"chapter_ref": f"eq.{name}"})
    return len(rows)


def close(a, b): return abs(float(a or 0) - float(b or 0)) < 0.011


ALIASES = {
    "exercises": ("exercises", "sections", "exercices", "problems", "parts_list"),
    "parts": ("parts", "questions", "items", "subquestions", "sub_questions"),
    "points": ("points", "marks", "score", "bareme", "max_points"),
    "statement": ("statement", "intro", "context", "stem", "text", "enonce"),
    "prompt": ("prompt", "question", "statement", "text", "enonce"),
    "solution_steps": ("solution_steps", "steps", "solution", "worked_solution", "correction"),
    "final_answer": ("final_answer", "answer", "final", "result"),
    "marking": ("marking", "marking_scheme", "rubric", "bareme_detail", "grading"),
    "duration_min": ("duration_min", "duration", "duration_minutes", "time_min"),
    "total_points": ("total_points", "total", "points", "max_points"),
}


def pick(d, key, default=None):
    for k in ALIASES[key]:
        if k in d and d[k] not in (None, "", []):
            return d[k]
    return default


def zip_ml(v):
    """{en:[a,b],fr:[a,b],ar:[a,b]} -> [{en:a,fr:a,ar:a},{...}]"""
    if is_ml(v) and all(isinstance(x, list) for x in v.values()):
        n = max(len(x) for x in v.values())
        return [{l: v[l][i] for l in v if i < len(v[l])} for i in range(n)]
    return v


def pts_in(text):
    m = re.match(r"\s*\(?\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:pt|pts|point|points|p\b)", text or "", re.I)
    return float(m.group(1).replace(",", ".")) if m else None


def norm_marking(mk):
    out = []
    for m in (zip_ml(mk) or []):
        if isinstance(m, str):
            out.append({"points": pts_in(m), "criterion": {"en": m, "fr": m, "ar": m}})
        elif is_ml(m):
            out.append({"points": pts_in(m.get("fr") or m.get("en")), "criterion": m})
        elif isinstance(m, dict):
            out.append(dict(m, points=pick(m, "points")))
    return out


def normalize_paper(pa):
    """accepts papers > exercises > parts AND papers > sections > questions (older kl-exams-1.0 builders)"""
    out = dict(pa)
    out["total_points"] = pick(pa, "total_points", 20)
    out["duration_min"] = pick(pa, "duration_min", 120)
    exs = []
    for j, ex in enumerate(pick(pa, "exercises", []) or [], 1):
        e = dict(ex)
        e["id"] = str(ex.get("id") or f"ex{j}")
        parts = []
        for k, pt in enumerate(pick(ex, "parts", []) or [], 1):
            q = dict(pt)
            q["id"] = str(pt.get("id") or chr(96 + k))
            q["points"] = pick(pt, "points", 0)
            for f in ("prompt", "solution_steps", "final_answer", "marking"):
                v = pick(pt, f)
                if v is not None: q[f] = v
            q["solution_steps"] = zip_ml(q.get("solution_steps") or [])
            if isinstance(q["solution_steps"], dict): q["solution_steps"] = [q["solution_steps"]]
            if "hints" in q: q["hints"] = zip_ml(q["hints"])
            q["marking"] = norm_marking(q.get("marking"))
            parts.append(q)
        e["parts"] = parts
        st = pick(ex, "statement")
        if st is not None: e["statement"] = st
        pts = pick(ex, "points")
        e["points"] = pts if pts not in (None, 0) else sum(float(q["points"] or 0) for q in parts)
        exs.append(e)
    out["exercises"] = exs
    return out


def show_shape(o, depth=0, name="paper"):
    if depth > 4: return
    if isinstance(o, dict):
        print("    " + "  " * depth + f"{name}: keys {sorted(o.keys())}")
        for k, v in o.items():
            if isinstance(v, list) and v and isinstance(v[0], dict): show_shape(v[0], depth + 1, k + "[0]")
            elif isinstance(v, dict) and not is_ml(v): show_shape(v, depth + 1, k)


def process_exams(mdir, module_id, rest, args):
    edir = os.path.join(mdir, "exams")
    ep = os.path.join(edir, "exams.json")
    if not os.path.isfile(ep): return 0
    data = load_json(ep)
    if isinstance(data, dict) and data.get("schema") not in (None, "kl-exams-1.0"):
        warn(f"exams.json schema is {data.get('schema')} (expected kl-exams-1.0)")
    papers = find_lists(data, "papers", []) or (data if isinstance(data, list) else [])
    stats = {"svg": 0}
    rows, seen = [], set()
    print(f"\n=== exams: {len(papers)} papers")
    for i, raw in enumerate(papers, 1):
        pa = normalize_paper(raw)
        ref = str(pa.get("id") or f"mock_{i:02d}")
        if not pa["exercises"]:
            print(f"  {ref}: NO exercises found. Structure of this paper:"); show_shape(raw)
        if ref in seen: err(f"exams: paper id {ref} repeated")
        seen.add(ref)
        tot = pa.get("total_points", 20)
        exs = pa.get("exercises") or []
        s_ex, ex_ids = 0.0, set()
        for ex in exs:
            if ex.get("id") in ex_ids: err(f"exams {ref}: exercise id {ex.get('id')} repeated")
            ex_ids.add(ex.get("id"))
            s_parts, part_ids = 0.0, set()
            for pt in ex.get("parts") or []:
                if pt.get("id") in part_ids: err(f"exams {ref}/{ex.get('id')}: part id {pt.get('id')} repeated")
                part_ids.add(pt.get("id"))
                s_parts += float(pt.get("points") or 0)
                if not pt.get("final_answer"): err(f"exams {ref}/{ex.get('id')}/{pt.get('id')}: no final_answer")
                mk = pt.get("marking") or []
                if mk and all(isinstance(m, dict) and m.get("points") is not None for m in mk) and not close(sum(float(m["points"]) for m in mk), pt.get("points")):
                    warn(f"exams {ref}/{ex.get('id')}/{pt.get('id')}: marking points do not add up to {pt.get('points')}")
            if not close(s_parts, ex.get("points")):
                err(f"exams {ref}/{ex.get('id')}: parts add up to {s_parts:g}, exercise says {ex.get('points')}")
            s_ex += float(ex.get("points") or 0)
        if not close(s_ex, tot): err(f"exams {ref}: exercises add up to {s_ex:g}, total_points is {tot}")
        print(f"  {ref}: {len(exs)} exercises, {s_ex:g}/{tot} points, {pa.get('duration_min', 120)} min")
        rows.append({"module_id": module_id, "ref": ref, "position": i, "schema": "kl-exams-1.0",
                     "duration_min": pa.get("duration_min", 120), "total_points": tot,
                     "title": strip_internal(pa.get("title") or {}), "instructions": strip_internal(pa.get("instructions") or {}),
                     "exercises": inlined(exs, edir, stats),
                     "status": "published" if args.publish else "draft", "rights_status": "own_work", "updated_at": now_iso()})
    print(f"  exams SVG inlined: {stats['svg']}" + ("" if args.dry_run else ""))
    if not args.dry_run and not errors:
        upsert(rest, "learn_exam_papers", rows, "module_id,ref")
        archive_missing(rest, "learn_exam_papers", module_id, {r["ref"] for r in rows})
        print(f"  {len(rows)} papers written")
    return len(rows)


def validate_extras(items, kind, name):
    for it in items:
        if kind == "questions":
            opts = it.get("options") or {}
            lens = {l: len(opts.get(l, [])) for l in LANGS}
            if len(set(lens.values())) != 1: err(f"{name}: question {it.get('id')} option counts differ {lens}")
            elif lens[PRIMARY] < 2: err(f"{name}: question {it.get('id')} has fewer than 2 options")
            elif not (0 <= it.get("correct_index", -1) < lens[PRIMARY]): err(f"{name}: question {it.get('id')} bad correct_index")
            if not it.get("explanation"): err(f"{name}: question {it.get('id')} has no explanation")
        else:
            for f in ("front", "back"):
                missing = set(LANGS) - set(it.get(f) or {}) if isinstance(it.get(f), dict) else set(LANGS)
                if not is_ml(it.get(f) or {}) or missing: err(f"{name}: card {it.get('id')} {f} misses {sorted(missing)}")


def glossary_key(term):
    for l in ("fr", "en", "ar"):
        v = (term or {}).get(l)
        if v and str(v).strip(): return l, str(v).strip().lower()
    return None, None


def main():
    global LANGS, PRIMARY
    ap = argparse.ArgumentParser()
    ap.add_argument("--module-dir", required=True)
    ap.add_argument("--module-id", type=int, required=True)
    ap.add_argument("--chapters", default="", help="e.g. 1 or 1,2,3 (default: all)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--langs", default="en,fr,ar", help="content languages, e.g. ar,en for the bac")
    ap.add_argument("--source-lang", default="", help="default: fr when in --langs, else the first of --langs")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--launch", action="store_true", help="needed with --publish for bac modules (3001-3099)")
    ap.add_argument("--sets", action="store_true", help="also upload sets.json (backend file 11 must be applied)")
    ap.add_argument("--full", action="store_true", help="figures on cards/questions + practice.json + exams.json (backend file 15)")
    args = ap.parse_args()
    LANGS = tuple(x.strip() for x in args.langs.split(",") if x.strip())
    if not LANGS or not set(LANGS) <= ML_CODES: raise SystemExit("--langs: use en, fr, ar (e.g. ar,en)")
    PRIMARY = "fr" if "fr" in LANGS else LANGS[0]
    OPTS["full"] = args.full
    OPTS["source_lang"] = args.source_lang or PRIMARY
    if OPTS["source_lang"] not in LANGS: raise SystemExit("--source-lang must be one of --langs")
    if args.publish and args.module_id in BAC_IDS and not args.launch:
        raise SystemExit("Bac module: drafts only until the launch. (--publish --launch only on launch day.)")
    print(f"Languages {LANGS}, source_lang {OPTS['source_lang']}, " + ("PUBLISH" if args.publish else "drafts"))

    # 1) CHECK EVERYTHING FIRST (no network, nothing written)
    check = copy.copy(args)
    check.dry_run = True
    run(check, None)
    if errors:
        print("\nERRORS (nothing was written):")
        for e in errors[:60]: print("  -", e)
        raise SystemExit("CHECK FAILED: fix the errors above. Nothing was written.")
    if args.dry_run:
        if warnings:
            print(f"\nWARNINGS ({len(warnings)}):")
            for w in warnings[:40]: print("  -", w)
        print("\nDRY RUN: nothing was written.")
        return
    warnings.clear()

    # 2) WRITE
    try:
        from cdn_publish import ask_missing          # same settings + saved key as the CDN publisher
        ask_missing(False)
    except ImportError:
        pass
    url, key = os.environ.get("KAMPUS_SUPABASE_URL"), os.environ.get("KAMPUS_SERVICE_KEY")
    if not url or not key: raise SystemExit("Set KAMPUS_SUPABASE_URL and KAMPUS_SERVICE_KEY first.")
    rest = Rest(url, key)
    m = rest.call("GET", "study_modules", params={"id": f"eq.{args.module_id}", "select": "id,name"})
    if not m: raise SystemExit(f"Module {args.module_id} not found.")
    print("Module:", m[0]["name"])
    try:
        rest.call("GET", "learn_questions", params={"select": "source,based_on", "limit": "1"})
    except SystemExit:
        raise SystemExit("Backend file 57 (source/based_on columns) is not applied yet. Run 57_BAC_SOURCE.sql first.")
    run(args, rest)


def run(args, rest):
    mdir = args.module_dir
    chdirs = sorted(d for d in os.listdir(mdir) if re.fullmatch(r"chapter_\d+", d) and os.path.isdir(os.path.join(mdir, d)))
    if args.chapters:
        want = {int(x) for x in args.chapters.split(",")}
        chdirs = [d for d in chdirs if int(d.split("_")[1]) in want]
    if not chdirs: raise SystemExit("No chapter folders found.")

    all_lessons, all_gloss = [], []
    for d in chdirs:
        cdir = os.path.join(mdir, d)
        n = int(d.split("_")[1])
        ep = os.path.join(cdir, "extras.json")
        if args.dry_run and os.path.isfile(ep):
            ex = load_json(ep)
            validate_extras(find_lists(ex, "cards", []), "cards", d)
            validate_extras(find_lists(ex, "questions", []), "questions", d)
        res, gl = process_chapter(cdir, args.module_id, rest, args, n)
        all_gloss.extend(gl)
        if not args.dry_run: all_lessons.extend(res)
        if args.sets:
            process_sets(cdir, args.module_id, rest, args, n)
        if args.full:
            process_practice(cdir, args.module_id, rest, args, n)

    if args.full and not args.chapters:
        process_exams(mdir, args.module_id, rest, args)
    if args.dry_run:
        return
    if errors:
        print("\nERRORS:")
        for e in errors[:60]: print("  -", e)
        raise SystemExit("Stopped. Rows written so far stay as drafts; fix and run again (safe to repeat).")
    # glossary (key: French term when present, else English, else Arabic)
    gl_rows = {}
    for g in all_gloss:
        lang, k = glossary_key(g.get("term"))
        if k: gl_rows[(lang, k)] = {"module_id": args.module_id, "fr": g["term"].get("fr"), "ar": g["term"].get("ar"),
                                    "en": g["term"].get("en"), "definition": g.get("definition")}
    print(f"\nGlossary terms: {len(gl_rows)}")
    old = rest.call("GET", "module_glossary", params={"module_id": f"eq.{args.module_id}", "select": "id,fr,en,ar"}) or []
    by_key = {}
    for o in old:
        lang, k = glossary_key(o)
        if k: by_key[(lang, k)] = o["id"]
    for k, row in gl_rows.items():
        if k in by_key: rest.call("PATCH", "module_glossary", row, {"id": f"eq.{by_key[k]}"}, "return=minimal")
        else: rest.call("POST", "module_glossary", row, prefer="return=minimal")
    if args.publish:
        for lid in all_lessons:
            rest.call("PATCH", "learn_lessons", {"status": "published"}, {"id": f"eq.{lid}"}, "return=minimal")
        print(f"Published {len(all_lessons)} lessons.")
    else:
        print("Lessons are DRAFTS (students do not see them).")
    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings[:40]: print("  -", w)
    print("\nDONE.")


if __name__ == "__main__":
    main()
