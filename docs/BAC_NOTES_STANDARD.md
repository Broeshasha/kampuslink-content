# KAMPUSLINK BAC NOTES STANDARD v1  (2026-11-11)  -  3AS, Arabic content

Goal: notes that feel like the best revision notes in the country - airy, clear, deep - and that are FULL of real bac
questions with answers in the official grading style. Students must feel: "this app knows exactly what the bac asks".
Style references we studied: great A-level revision notes (syllabus box first, short bullets, bold key terms, labelled
diagrams next to the text, "Exam tip" boxes, real past questions with marks and mark-scheme answers, comparison tables,
practice at the end). We copy the METHOD, never anyone's text or diagrams.

## 1. Language rules (non-negotiable)
- Student content is in ARABIC (formal fusha, Algerian school register), exactly the terms of the official Algerian
  sources: ONEFD 3AS course, official programme (التدرجات السنوية), official bac papers and official corrections.
- Every subject term comes from GLOSSARY.json (built from the official sources, each term with its source).
  A term not in the glossary is not allowed until it is added WITH a source. No Middle-Eastern/other-country variants.
- OFFICIAL DEFINITION blocks: the short definitions students must write in the bac are copied word for word from the
  official source (ONEFD / textbook / official correction) and labelled "تعريف رسمي". Our own simple explanation follows
  in our own words.
- Bac answers use the wording of the official correction (الإجابة النموذجية) because graders reward that wording.
- English ("en") = a faithful translation of every text, used by the founder to check meaning (he does not read Arabic).
- Optional "fr" ONLY in the glossary (term bridge for university). Lessons, cards, questions: "ar" + "en".
- Digits and notation exactly as in Algerian bac papers (check the papers). Units SI.

## 2. Chapter anatomy (same order every chapter)
1. ما يطلبه البكالوريا  (What the bac asks): the official skills of this chapter + how often it appeared in the bac
   2008-2026 (from BAC_INDEX) + the typical question types. Short.
2. خريطة الفصل (chapter map): 1.1, 1.2, 1.3 ...
3. Each section, always in this order:
   a. تعريف رسمي (official definition, exact)        b. simple explanation (daily-life example / analogy, short)
   c. labelled diagram (SVG, Arabic labels allowed in SVG text only if short; RTL checked)
   d. step by step, ONE STEP PER ITEM (processes, mechanisms, reasoning)
   e. ⚠️ نصيحة البكالوريا (bac tip): where students lose points, from the official corrections and BAC_INDEX
   f. 📜 3-4 REAL BAC QUESTIONS on this section, from DIFFERENT YEARS (not one!), each with its source line
      "بكالوريا 2019 - علوم تجريبية - الموضوع الأول - التمرين 2 - السؤال 3 - (2 ن)" and
   g. ✅ the answer in OFFICIAL GRADING STYLE: what earns each point (as the official correction), accepted alternatives,
      and one line "why" for understanding. If the official correction is missing, write our solution and label it
      "حل مقترح من KampusLink" (never call it official).
4. 📊 comparison tables for confusing pairs.
5. 📝 one-screen summary (ملخص).
6. 🏋️ practice: more real bac questions + NEW "bac style" exercises (label: ✍️ على نمط البكالوريا), full solutions.

## 3. Spacing and look
Max 2-3 lines per block. One idea per block. Bullets < 15 words. Bold only key terms. A diagram every 3-6 blocks.
No walls of text. Each episode 8-40 blocks (importer rule).

## 4. Real bac material everywhere
- Every item taken from a real bac (question, card, quiz, practice) carries a "source" object:
  {"type":"bac","year":2019,"session":"june|special","stream":"SE","subject_no":1,"exercise":2,"question":"3","points":2}
- Real bac text is reproduced EXACTLY (same wording, same numbers). Never alter a real bac question and still call it bac.
- Our own items carry {"type":"kampuslink_bac_style"} and are NEVER presented as real bac.
- Documents (graphs/tables/figures) of real bac questions: redraw cleanly as SVG with the same data, note "مأخوذ من".
- Target per chapter: at least 25 real bac items spread across sections + practice, from as many different years as exist.

## 5. Cards and quizzes
CARDS_STANDARD_V2 applies (question front answerable in 3-5 s, answer first line, one "why"). For the bac add:
- "bac" cards: one sub-question of a real bac exercise -> short answer (with source).
- trap cards from the official corrections (typical grading losses).
- quizzes: wrong options = real student mistakes (from corrections/bac tips). 
Every number/fact checked against the official sources; every fact must match ONEFD/programme exactly; every number recomputed by code (physics, maths).

## 6. Self-check before every zip
- every term in GLOSSARY.json; every official definition matches its source text
- 3-4 real bac questions per section with complete source lines; sources exist in BAC_INDEX
- answers follow the official correction; no unofficial text labelled official
- en translation present for every ar text; importer dry run with --langs ar,en passes
- read 10 random blocks aloud as a weak student: clear in 10 seconds? If not, fix.
