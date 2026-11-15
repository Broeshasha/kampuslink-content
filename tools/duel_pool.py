"""
Duel question pool per chapter (DUELS_DESIGN.md 2c + 3), built at CDN publish time from the module export.
Standard library only. Used by cdn_publish.py; the duel room (Cloudflare Worker) reads these files.

One entry per usable question, language-independent (the phone shows the text from the lesson files it has):
  quiz question  {"id": "q:<question id>", "src": "quiz", "lesson_id", "question_id", "options": n, "correct": i, ...}
  set question   {"id": "s:<set id>:<slide id>", "src": "set", "set_id", "slide_id", "options": n, "correct": i, ...}
  card recall    {"id": "c:<card id>", "src": "card", "card_id", "option_cards": [4 card ids], "correct": i, ...}
Common keys: chapter_ref, kind (recall|concept|document|short_calc|boss), level (1 easy, 2 medium, 3 bac level),
timer (s), points, duel_ok, bac (real bac year or absent).
KNOWN LIMIT (DUELS_DESIGN 6): correct answers are public like the lesson files; duels give XP and fun, not prizes.
"""
import hashlib
import re

TIMERS = {"recall": 10, "concept": 15, "document": 25, "short_calc": 30, "boss": 60}
POINTS = {"recall": 100, "concept": 100, "document": 150, "short_calc": 150, "boss": 250}
MAX_PROMPT_CHARS = 320          # longer = "needs long reading" -> not in duels
MAX_FIGURE_CHARS = 60_000       # bigger figure = too big for a phone in a timed duel
_CALC = re.compile(r"\\\(|\\\[|\$|[0-9]")


def _texts(i18n, field):
    """{lang: text} of one field from an i18n map ({lang: {field: ...}})."""
    out = {}
    for lang, v in (i18n or {}).items():
        if isinstance(v, dict) and v.get(field) is not None:
            out[lang] = v[field]
    return out


def _plain(v):
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return " ".join(_plain(x) for x in v)
    if isinstance(v, dict):
        return " ".join(_plain(x) for x in v.values())
    return "" if v is None else str(v)


def _level(d):
    return d if d in (1, 2, 3) else 2


def _bac_year(src):
    if isinstance(src, dict) and (src.get("type") or src.get("kind")) == "bac":
        try:
            y = int(src.get("year"))
            return y if 1990 <= y <= 2100 else None
        except (TypeError, ValueError):
            return None
    return None


def _figure_chars(fig):
    return len(_plain(fig)) if fig else 0


def classify(prompt_text, options_text, difficulty, has_figure):
    """Kind from difficulty + figure + numbers/LaTeX (DUELS_DESIGN 3)."""
    calc = bool(_CALC.search(prompt_text)) or bool(_CALC.search(options_text))
    if has_figure:
        return "document"
    if calc:
        return "boss" if difficulty == 3 else "short_calc"
    return "concept"


def _entry(kind, level, **kw):
    e = {"kind": kind, "level": level, "timer": TIMERS[kind], "points": POINTS[kind]}
    e.update({k: v for k, v in kw.items() if v is not None})
    return e


def _first_lang_text(m):
    for lang in ("ar", "fr", "en"):
        if lang in m:
            return m[lang]
    return next(iter(m.values()), "")


def _stable(seed):
    return int(hashlib.sha256(seed.encode()).hexdigest()[:12], 16)


def card_recall(card, pool_cards):
    """4-option recall question from a card: right = its back, 3 wrong = backs of other cards of the same chapter
    and same card kind, with distinct texts of similar length in EVERY language. None when not possible."""
    backs = _texts(card.get("i18n"), "back")
    fronts = _texts(card.get("i18n"), "front")
    if not backs or not fronts:
        return None
    langs = sorted(backs)
    right = {l: _plain(backs[l]).strip() for l in langs}
    if any(not right[l] or len(right[l]) > 120 for l in langs):
        return None
    cands = []
    for other in pool_cards:
        if other["id"] == card["id"] or other.get("card_kind") != card.get("card_kind"):
            continue
        ob = _texts(other.get("i18n"), "back")
        if any(l not in ob for l in langs):
            continue
        txt = {l: _plain(ob[l]).strip() for l in langs}
        ok = True
        for l in langs:
            a, b = len(right[l]), len(txt[l])
            if not txt[l] or txt[l].lower() == right[l].lower() or not (0.5 <= b / max(a, 1) <= 2.0):
                ok = False
                break
        if ok:
            cands.append((abs(len(txt[langs[0]]) - len(right[langs[0]])), _stable(f"{card['id']}:{other['id']}"), other, txt))
    cands.sort(key=lambda c: (c[0], c[1]))
    chosen, seen = [], [right]
    for _, _, other, txt in cands:
        if any(txt[l].lower() == s[l].lower() for s in seen for l in langs):
            continue
        chosen.append(other["id"])
        seen.append(txt)
        if len(chosen) == 3:
            break
    if len(chosen) < 3:
        return None
    ids = [card["id"]] + chosen
    ids.sort(key=lambda i: _stable(f"order:{card['id']}:{i}"))
    return ids, ids.index(card["id"])


def build_pools(export):
    """{chapter_ref: [entries]} for one module export (cdn_module_export)."""
    pools = {}
    lesson_chapter = {}
    for les in export.get("lessons") or []:
        ch = ((les.get("unit") or {}).get("ref")) or f"lesson_{les['id']}"
        lesson_chapter[les["id"]] = ch
        pool = pools.setdefault(ch, [])
        for q in les.get("questions") or []:
            prompts = _texts(q.get("i18n"), "prompt")
            options = _texts(q.get("i18n"), "options")
            if not prompts or not options:
                continue
            n = len(_first_lang_text(options) or [])
            ci = q.get("correct_index")
            if n < 2 or not isinstance(ci, int) or not 0 <= ci < n:
                continue
            p = _plain(_first_lang_text(prompts))
            o = _plain(_first_lang_text(options))
            fig = q.get("figure") or q.get("option_figures")
            kind = classify(p, o, q.get("difficulty"), bool(fig))
            ok = len(p) <= MAX_PROMPT_CHARS and _figure_chars(fig) <= MAX_FIGURE_CHARS
            pool.append(_entry(kind, _level(q.get("difficulty")), id=f"q:{q['id']}", src="quiz", chapter_ref=ch,
                               lesson_id=les["id"], question_id=q["id"], options=n, correct=ci, duel_ok=ok,
                               bac=_bac_year(q.get("source"))))
        cards = [c for c in les.get("cards") or [] if c.get("i18n")]
        les["_cards"] = cards
    # recall questions: distractors from the whole chapter
    chapter_cards = {}
    for les in export.get("lessons") or []:
        chapter_cards.setdefault(lesson_chapter[les["id"]], []).extend(les.pop("_cards", []))
    for ch, cards in chapter_cards.items():
        for c in cards:
            r = card_recall(c, cards)
            if r is None:
                continue
            ids, ci = r
            pools[ch].append(_entry("recall", _level(c.get("difficulty")), id=f"c:{c['id']}", src="card", chapter_ref=ch,
                                    card_id=c["id"], option_cards=ids, correct=ci, duel_ok=True,
                                    bac=_bac_year(c.get("source"))))
    # carousel set questions
    for st in export.get("sets") or []:
        ch = lesson_chapter.get(st.get("lesson_id")) or (str(st.get("ref") or "").split("/")[0] or "sets")
        for sl in st.get("slides") or []:
            opts = sl.get("options")
            ci = sl.get("correct_index")
            if not isinstance(opts, list) or len(opts) < 2 or not isinstance(ci, int) or not 0 <= ci < len(opts):
                continue
            pr = sl.get("prompt")
            p = _plain(_first_lang_text(pr) if isinstance(pr, dict) and pr else pr)
            o = _plain([_first_lang_text(x) if isinstance(x, dict) and x else x for x in opts])
            if not p.strip():
                continue
            kind = classify(p, o, st.get("difficulty"), bool(sl.get("figure")))
            ok = len(p) <= MAX_PROMPT_CHARS and _figure_chars(sl.get("figure")) <= MAX_FIGURE_CHARS
            pools.setdefault(ch, []).append(_entry(kind, _level(st.get("difficulty")), id=f"s:{st['id']}:{sl.get('id')}",
                                                   src="set", chapter_ref=ch, set_id=st["id"], slide_id=sl.get("id"),
                                                   options=len(opts), correct=ci, duel_ok=ok,
                                                   bac=_bac_year(sl.get("source"))))
    return {ch: sorted(p, key=lambda e: e["id"]) for ch, p in pools.items() if p}


def summary(entries):
    out = {}
    for e in entries:
        if e["duel_ok"]:
            out[e["kind"]] = out.get(e["kind"], 0) + 1
    return out
