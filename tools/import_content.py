#!/usr/bin/env python3
"""
KampusLink content importer  v2   (Python 3.9+, standard library only)
LOCAL COPY of the project-knowledge file (used only for the dry run in checks.py).
"""
import argparse, json, os, re, sys, urllib.request, urllib.error, urllib.parse

LANGS = ("en", "fr", "ar")
import sys as _sys
if "--langs" in _sys.argv:
    LANGS = tuple(_sys.argv[_sys.argv.index("--langs") + 1].split(","))
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


def is_ml(d):
    return (isinstance(d, dict) and min(2, len(LANGS)) <= len(d) <= 3 and set(d) <= set(LANGS)
            and all(isinstance(v, (str, list)) for v in d.values()))


def localize(o, lang, where=""):
    if is_ml(o):
        if lang not in o:
            warn(f"{where}: missing '{lang}' in multilingual object")
            return o.get(LANGS[0]) or o.get("fr") or next(iter(o.values()))
        return o[lang]
    if isinstance(o, dict):
        return {k: localize(v, lang, where) for k, v in o.items() if k not in INTERNAL}
    if isinstance(o, list):
        return [localize(v, lang, where) for v in o]
    return o


def inline_svgs(o, chapter_dir, stats):
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


def build_units(sections):
    units, cur = [], None
    for sec in sections:
        if sec.get("level", 9) == 0:
            continue
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
    if o is None: return None
    o = strip_internal(json.loads(json.dumps(o)))
    holder = {"x": o}
    inline_svgs(holder, cdir, stats)
    return holder["x"]


def item_figures(it, cdir, stats):
    fig = it.get("figure")
    if fig is not None and "asset" not in fig: fig = {"asset": fig}
    return inlined(fig, cdir, stats), inlined(it.get("option_figures"), cdir, stats)


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
            if of is not None and len(of) != len(((it.get("options") or {}).get(LANGS[0])) or []):
                err(f"{name}: question {it.get('id')} option_figures count differs from options")
        print(f"  figures on cards/questions: {fst['svg']} SVG")

    print(f"\n=== {name}: {len(sections)} sections, {len(ids)} blocks -> {len(plan)} episodes; "
          f"{len(cards)} cards, {len(questions)} questions; source keys: {sorted(ch.keys())}")
    result = []
    for p in plan:
        i = p["idx"]
        blocks = {l: student_blocks(p["unit"], l, cdir, stats if l == LANGS[0] else {"svg": 0}) for l in LANGS}
        words = len(" ".join(text_of(b, LANGS[0] if "fr" not in LANGS else "fr") for s in p["unit"] for b in (s.get("blocks") or [])).split())
        mins = max(1, round(words / 180))
        kb = {l: round(len(json.dumps(blocks[l], ensure_ascii=False).encode()) / 1024) for l in LANGS}
        print(f"  ep{i}: {nblocks(p['unit']):>3} blocks, ~{mins} min, "
              f"{len(per_ep[i]['cards'])} cards, {len(per_ep[i]['questions'])} questions, KB {kb}  | "
              f"{localize(p['title'], 'fr')}")
        result.append((p, blocks, mins, per_ep[i]))
    print(f"  SVG inlined: {stats['svg']}")
    glossary = [g for g in (ch.get("glossary") or [])]
    return result, glossary


def convert_slide(sl, cdir, stats):
    out = {k: v for k, v in sl.items() if k not in INTERNAL and k not in ("question", "figure")}
    q = sl.get("question")
    if q:
        out["prompt"] = q.get("prompt")
        o = q.get("options") or {}
        n = len(o.get("fr") or o.get(LANGS[0]) or [])
        out["options"] = [{l: o[l][i] for l in LANGS if l in o} for i in range(n)]
        out["correct_index"] = q.get("correct_index")
        out["explanation"] = q.get("explanation")
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
        n += 1
    print(f"  {name}: {n} carousel sets ({stats['svg']} SVG inlined)")
    return n


def diff(c):
    d = c.get("difficulty")
    return d if d in (1, 2, 3) else None


def tag(chap, c):
    k = c.get("concept")
    return None if not k else (k if ":" in k else f"{chap}:{k}")


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
            if not is_ml(p.get(f) or {}): warn(f"{name}: practice {pid} {f} is not {{en,fr,ar}}")
        fig = p.get("figure")
        if fig is not None and "asset" not in fig: fig = {"asset": fig}
        rows.append({"ref": f"{name}/{pid}", "figure": inlined(fig, cdir, stats), "parts": inlined(parts, cdir, stats),
                     "concepts": [tag(name, {"concept": c}) for c in (p.get("concepts") or []) if c], "difficulty": diff(p)})
    print(f"  {name}: {len(rows)} practice problems ({stats['svg']} SVG inlined)")
    return len(rows)


def validate_extras(items, kind, name):
    for it in items:
        if kind == "questions":
            opts = it.get("options") or {}
            lens = {l: len(opts.get(l, [])) for l in LANGS}
            if len(set(lens.values())) != 1: err(f"{name}: question {it.get('id')} option counts differ {lens}")
            elif not (0 <= it.get("correct_index", -1) < lens[LANGS[0]]): err(f"{name}: question {it.get('id')} bad correct_index")
            if not it.get("explanation"): err(f"{name}: question {it.get('id')} has no explanation")
        else:
            for f in ("front", "back"):
                if not is_ml(it.get(f) or {}) or len(it[f]) != len(LANGS): err(f"{name}: card {it.get('id')} {f} not in {len(LANGS)} languages")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--module-dir", required=True)
    ap.add_argument("--module-id", type=int, required=True)
    ap.add_argument("--chapters", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--langs", default="en,fr,ar")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--sets", action="store_true")
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    OPTS["full"] = args.full
    if not args.dry_run: raise SystemExit("LOCAL COPY: dry run only.")
    mdir = args.module_dir
    chdirs = sorted(d for d in os.listdir(mdir) if re.fullmatch(r"chapter_\d+", d) and os.path.isdir(os.path.join(mdir, d)))
    if args.chapters:
        want = {int(x) for x in args.chapters.split(",")}
        chdirs = [d for d in chdirs if int(d.split("_")[1]) in want]
    if not chdirs: raise SystemExit("No chapter folders found.")
    all_gloss = []
    for d in chdirs:
        cdir = os.path.join(mdir, d)
        n = int(d.split("_")[1])
        res, gl = process_chapter(cdir, args.module_id, None, args, n)
        all_gloss.extend(gl)
        if args.sets: process_sets(cdir, args.module_id, None, args, n)
        if args.full: process_practice(cdir, args.module_id, None, args, n)
        ep = os.path.join(cdir, "extras.json")
        if os.path.isfile(ep):
            ex = load_json(ep)
            validate_extras(find_lists(ex, "cards", []), "cards", d)
            validate_extras(find_lists(ex, "questions", []), "questions", d)
    if errors:
        print("\nERRORS (nothing was published):")
        for e in errors[:60]: print("  -", e)
        raise SystemExit("DRY RUN FAILED: fix the errors above.")
    gl_rows = {}
    for g in all_gloss:
        fr = (g.get("term") or {}).get("fr")
        if fr: gl_rows[fr.strip().lower()] = 1
    print(f"\nGlossary terms: {len(gl_rows)}")
    if warnings:
        print(f"\nWARNINGS ({len(warnings)}):")
        for w in warnings[:40]: print("  -", w)
    print("\nDRY RUN: nothing was written.")


if __name__ == "__main__":
    main()
