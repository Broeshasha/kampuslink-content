# KAMPUSLINK CONTENT STANDARD  (v1, 2026-10-30)

Every AI that writes KampusLink content follows this file. It wins over habits and over any module prompt on HOW to teach.
Module prompts only add the subject, the sources and the volumes. The JSON shapes are in docs/CONTENT_FORMAT.txt and in
reference/ (the importer reads exactly those shapes).

Goal: the clearest, most useful study material an Algerian student has ever had. A weak student can follow every line alone.
A strong student reaches a top exam mark. Everything is correct, checked by code.

------------------------------------------------------------------------------------------------------------------------
## 0. The 12 proven methods we build on (and what each one forces you to do)

| # | Method (evidence) | What you MUST do |
|---|---|---|
| 1 | Retrieval practice (testing effect: Roediger & Karpicke; Dunlosky et al. 2013 "high utility") | Every episode ends with questions. Cards ASK, they never just tell. |
| 2 | Spaced repetition (Ebbinghaus; distributed practice) | One idea per card, so the app can space it. No "list all 7 properties" cards. |
| 3 | Worked examples then fading (Sweller, cognitive load theory) | Ladder in every episode: fully solved -> half solved -> solve alone (section 3). |
| 4 | Interleaving (Kornell & Bjork; Rohrer) | Each chapter ends with a MIXED practice set where the student must choose the method. |
| 5 | Pretesting / prediction (generation effect) | Start each episode with a hook question; carousels make the student commit a guess before the reveal. |
| 6 | Dual coding (Paivio; Mayer multimedia principles) | A diagram in nearly every section, placed next to the text it explains, with "How to read this diagram". |
| 7 | Low cognitive load (Sweller; Mayer segmenting) | 3-8 minute episodes, one idea at a time, short paragraphs, nothing decorative. |
| 8 | Concept questions on misconceptions (Mazur, Peer Instruction, Harvard) | Wrong options are REAL student mistakes; the explanation says why the trap is tempting. |
| 9 | Elaboration and self-explanation | "Why" cards, "explain it like I'm 15" blocks, links to other chapters. |
| 10 | Concrete before abstract | Real situation first (daily life, the student's engineering field), then the rule. |
| 11 | Immediate explained feedback | Every answer explained; every practice step written out. |
| 12 | Mastery and calibration | Self-rating after practice (got it / partly / missed); a "weak spots" set before exams. |

------------------------------------------------------------------------------------------------------------------------
## 1. Anatomy of an EPISODE (one level-2 section = one lesson of 3-8 minutes, 8-40 blocks)

In this order:
1. **Hook** (note_kind "intuition"): a question or situation that makes the idea needed. 1-3 sentences.
   Good: "Your phone computes sin(0.3) in a microsecond. It does not know a sine table. How?"
   Bad: "In this chapter we will study Taylor expansions."
2. **Explain it like I'm 15** (paragraph): plain words, one analogy, no formula yet.
3. **Exact definition / rule** (definition or equation block): symbol by symbol, units, hypotheses highlighted
   ("ONLY IF the terms are positive"). Say what happens if a quantity doubles.
4. **Why it is true** (short): a picture, a numeric table, or a proof idea. Not a full proof unless the exam asks for it.
5. **The method** (bullet_list titled "Method"): numbered recipe the student can apply in an exam.
6. **Diagram + "How to read this diagram"** (wherever a picture helps).
7. **Common mistakes** (note_kind "mistake"): the 2-3 real errors, each with the correct version.
8. **Worked examples ladder** (level-3 section "Worked examples / Exercices résolus / تمارين محلولة", LAST part of the episode):
   at least 3 exercises, easy -> exam level, following section 3.
9. **Exam tip + Remember** (note_kind "exam_tip", "remember"): the 3 lines to keep.

The quiz questions and cards of the episode come from extras.json and are shown by the app after the lesson.

------------------------------------------------------------------------------------------------------------------------
## 2. Writing rules (every text)

- One idea per paragraph. Paragraphs under 600 characters (hard limit 900).
- Short sentences. Active voice. "We", "you". Warm, a little humour, never childish, never sarcastic.
- Never skip a step. Never write "obviously", "clearly", "it is easy to see". If it is obvious, it costs one line to show it.
- Recall prerequisites in one line when used ("Recall: \( (a+b)^2 = a^2 + 2ab + b^2 \).").
- Name things the way the student's exam names them (French course vocabulary).
- Numbers: realistic, and recomputed in code. Units always written and carried through.
- Highlights: only the 1-3 key terms/values of a block, exact substrings.

------------------------------------------------------------------------------------------------------------------------
## 3. WORKED SOLUTIONS - the most important rule of this standard

Students learn most from solutions they can follow line by line. A solution is a staircase: ONE STEP PER LINE, with space
between steps. Never a paragraph, never steps glued together with semicolons or commas.

### 3.1 The rules
1. **One action per step.** One step = one thing done (substitute, simplify, factor, apply a theorem, conclude).
2. **Each step is its own item**:
   - in lessons: each step is its own block (an "example" block or an "equation" block), or its own item in a bullet_list;
   - in practice.json and exams.json: each step is its own element of the `solution_steps` list.
   NEVER put two steps in one string. NEVER chain steps with ";" or with "then ... then ...".
3. **Every step has a reason.** Format: what we do, then why, in plain words.
   "Step 3 - We divide numerator and denominator by \(n^2\), because \(n^2\) is the biggest power: this makes the limit visible."
4. **Show the small algebra.** Write the intermediate line even when it seems trivial (expanding, common denominator, sign change).
5. **Start with the plan.** Before step 1: "What we recognise" and "Which tool we choose, and why".
6. **End with a sentence conclusion** that answers the question asked, with the unit
   ("Conclusion: the series converges and its sum is \(2\)." / "The force is \(F = 4{,}9\ \mathrm{N}\), directed upward.").
7. **Add a check line** when possible (units, order of magnitude, a special case, a quick numeric test).
8. **Add the trap line**: "Trap: many students forget ... here".

### 3.2 Bad vs good

BAD (one block, everything glued):
"On a \(u_n = \frac{n^2+1}{2n^2-3}\) ; on divise par \(n^2\) ; donc \(u_n \to \frac{1}{2}\) ; la suite converge."

GOOD (separate items, one step each, reason each time):
- Ce que l'on reconnaît : une fraction de deux polynômes en \(n\). Outil : diviser par la plus grande puissance de \(n\).
- Étape 1 - On écrit la suite : \(u_n = \dfrac{n^2+1}{2n^2-3}\).
- Étape 2 - On divise le numérateur et le dénominateur par \(n^2\), la plus grande puissance : \(u_n = \dfrac{1 + \frac{1}{n^2}}{2 - \frac{3}{n^2}}\).
- Étape 3 - Quand \(n \to +\infty\), \(\frac{1}{n^2} \to 0\) et \(\frac{3}{n^2} \to 0\).
- Étape 4 - Donc le numérateur tend vers \(1\) et le dénominateur vers \(2\).
- Conclusion : \(\lim u_n = \dfrac{1}{2}\), la suite converge vers \(\dfrac{1}{2}\).
- Vérification : pour \(n = 100\), \(u_n \approx 0{,}5001\). Cohérent.
- Piège : diviser seulement le numérateur par \(n^2\) (erreur fréquente).

### 3.3 The worked-examples ladder (fading)
In each episode's "Worked examples" part:
1. **Example A - fully solved** (all steps as above).
2. **Example B - half solved**: the plan and the first steps are given; the last 1-2 steps are asked as "Your turn: ..."
   with the answer right after under "Answer:" (separate block).
3. **Example C - exam level, fully solved**, the kind of exercise that appears in the EMD.
Practice problems (practice.json) then let the student solve ALONE with progressive hints.

------------------------------------------------------------------------------------------------------------------------
## 4. Diagrams

- Draw from code and from the real equation/data (never sketched by hand). Labelled. Readable at 360 px wide, dark and light.
- Right after each lesson figure: a block titled "How to read this diagram / Comment lire ce schéma / كيف تقرأ هذا الرسم"
  with 3-6 numbered points: (a) what axes, symbols, colours mean; (b) where to look first; (c) what it shows in one sentence;
  (d) the usual misreading; (e) which formula it matches.
- Colours: {{accent}} = the key idea or unknown, {{warn}} = the trap, {{ok}} = the correct result, {{c1}}..{{c6}} for series.
- Text inside the SVG: minimal, language-neutral (symbols, numbers, units). Never Arabic words inside an SVG.
- Use diagrams in cards and questions too (about a quarter of them): "Which arrow is the normal force?", "Which graph is ...?".

------------------------------------------------------------------------------------------------------------------------
## 5. Flashcards (based on the "20 rules of formulating knowledge", P. Wozniak)

1. **One fact per card** (minimum information principle).
2. **Ask a real question**, answer in a few words or one formula. Front <= 160 characters, back <= 400.
3. **No lists/enumerations** on one card. Split them.
4. **Kinds** (field "kind"): definition | why | when | trap | formula. Mix them; at least a third are "why" or "when".
5. **Both directions** when useful (term -> meaning AND meaning -> term, as two cards).
6. **Context cues**: start with the topic when ambiguous ("[Suites] ...").
7. **Pictures** on about a quarter of the cards.
8. **Trap cards**: front = a tempting wrong statement, back = why it is wrong and the right version.
9. Every card links to its lesson block (source_block) and has concept + difficulty.

Good: Front "Why does \(u_n \to 0\) NOT prove that \(\sum u_n\) converges?" Back "Counter-example: \(\sum \frac{1}{n}\) diverges although \(\frac{1}{n} \to 0\). The condition is necessary, not sufficient."
Bad: Front "Convergence of series" Back "(10 lines of theory)".

------------------------------------------------------------------------------------------------------------------------
## 6. Quiz questions

- **Mix per chapter**: 40% recall/understanding, 40% apply/compute, 20% analyse (choose the method, find the error, read a graph).
- **Concept questions** (Mazur): test the idea, not arithmetic speed. At least one per episode.
- **Distractors = real misconceptions** (list them in distractor_misconceptions, internal). Never silly options, never "all of the above".
- **Explanation** (required, 2-4 sentences): why the right answer is right AND why the most tempting wrong answer is wrong.
- 3-5 options (mcq) or 2 (true_false). Same order in the 3 languages. Correct answer position varied.
- **Target difficulty**: students should get 70-85% right on the first try. Use difficulty 1/2/3 honestly.
- Numeric drills may be GENERATED BY CODE from templates (different numbers, verified answers), to save effort and add volume.

------------------------------------------------------------------------------------------------------------------------
## 7. Carousels (sets.json)

Short stories that make an idea click, 3-8 slides, 1-3 sentences per slide.
- **mystery**: hook -> clues -> COMMIT (student locks a guess) -> reveal -> takeaway/quiz.
- **explainer**: a derivation or method frame by frame.
- **quiz_chain**: 3-5 linked questions that build one idea.
Never clickbait. Every carousel teaches something examinable.

------------------------------------------------------------------------------------------------------------------------
## 8. Practice problems and mock exams

- **Practice** (practice.json): NEW exam-style problems. Each part: 2-3 progressive hints (hint 1 = which idea, hint 2 = first step,
  hint 3 = almost the answer), then solution_steps following section 3 (ONE STEP PER LIST ITEM), then final_answer with unit.
- **End of chapter: one MIXED set** (interleaving): problems from all episodes, the student must choose the method.
- **Mock exams** (exams.json): same structure, length, barème and style as the real exams of the sources. Because exams are written by
  each university, VARY the styles across papers (calculation-heavy, conceptual, long problem, short questions). Marking lines with
  numeric points that add up. Solutions follow section 3.

------------------------------------------------------------------------------------------------------------------------
## 9. Languages

- Every student text in en, fr, ar. French = the exam language: write French first, carefully.
- Arabic: formal Modern Standard Arabic, university register, natural sentences (not word-for-word), consistent terms from
  module_terms.json, second pass on every string. Formulas, numbers, units = LTR islands.
- Module and speciality names stay in French in every language.

------------------------------------------------------------------------------------------------------------------------
## 10. Correctness (non-negotiable)

- Every number, limit, derivative, integral, unit, answer key and graph is computed/verified in code (sympy/numpy).
- Source errors are never silently copied: log them (source_quality_issues) and teach the correct version.
- Sources are reference only: rewrite everything, invent NEW exercises; never copy TD or exam statements.
- Run the importer dry run before every zip; it must end with "DRY RUN: nothing was written." and no ERRORS.

------------------------------------------------------------------------------------------------------------------------
## 11. Self-check before every zip (answer YES to all, write the result in report.txt)

1. Does every episode start with a hook and end with >= 3 worked examples (A full, B half, C exam level)?
2. Is EVERY solution written one step per item, each with its reason, with no steps glued by ";"?
3. Does every diagram have its "How to read this diagram" block?
4. Is every card one fact, a real question, with a short answer?
5. Do the wrong options of every question come from real mistakes, and does every explanation address the tempting wrong one?
6. Is there a mixed (interleaved) practice set at the end of the chapter?
7. Were all numbers and keys verified by code? Does the importer dry run pass?
8. Would a student who missed the lecture understand this alone? If not, add the missing step.
