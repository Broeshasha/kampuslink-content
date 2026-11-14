# KAMPUSLINK CARDS STANDARD v2  (2026-11-04) - replaces section 5 of KAMPUSLINK_CONTENT_STANDARD.md

The old cards were correct but boring: dictionary cards ("Definition of X?" -> a sentence to memorise).
A KampusLink card must give a small WIN: the student thinks 3-5 seconds, flips, and feels "yes!" or "ahh, that's why".
Useful (it is what the EMD asks and where students lose points) AND satisfying (curiosity, quick success, a click in the head).

## 1. The 10 rules
1. FRONT = A REAL QUESTION answerable in 3-5 seconds in the head. Never "Definition of ...?", never "What is ...?" alone.
   Ideal front <= 110 characters (hard limit 160).
2. BACK, FIRST LINE = THE ANSWER, alone and short (max ~8 words or one formula/number). Then a line break.
3. BACK, THEN ONE "WHY" SENTENCE that makes it click (the reason, the trick, the image). Ideal back <= 220 characters (hard limit 400).
   Optional last line: the lycee Arabic term as a bridge in the French version, or an "EMD trap" note.
4. ONE IDEA PER CARD. No lists, no "give the 4 ...". Split.
5. NUMBERS ARE EASY FOR MENTAL MATH. The card trains the idea, not the calculator.
6. USE THE TRAPS. Every chapter has the mistakes students really make (SOURCES_DIGEST.md, EMD corrections). Turn them into cards.
   Getting a trap right is the most satisfying feeling on a card.
7. EASY -> HARDER inside each episode. The FIRST card of every episode is a sure win (confidence).
8. ANSWERABLE FROM THE LESSON. Every card uses only what the lesson (source_block) teaches. Never beyond the syllabus.
9. TONE: friendly, short, soft humour on at most 1 card in 5 (a wink, never childish), never scary. Max one emoji per card, optional.
10. PLAIN TEXT + LaTeX \( \) only. No markdown (** # -), the app shows text as is. Line breaks with \n are fine.

## 2. Card types (field "kind") and the mix per chapter
| kind      | front looks like                                               | share   |
|-----------|----------------------------------------------------------------|---------|
| calc      | a 5-second mini calculation                                    | ~25%    |
| trap      | "Vrai ou piege : ... ?" a tempting wrong idea                   | ~20%    |
| why       | "Pourquoi ... ?" / "Et si ... ?"                                | ~20%    |
| which     | "Lequel ... ? A ou B ?" / "Quelle methode quand ... ?"          | ~15%    |
| picture   | a simple SVG (graph, diagram) + a question about it             | ~10-15% |
| definition| ONLY if unavoidable, asked from a situation, never word-for-word | <= 10% |
Allowed kind values: calc | trap | why | which | picture | definition | formula | when.
(Text-heavy modules like Metiers or Ethique: replace calc by "situation" cards: "Un ingenieur doit ... : que fait-il ?", kind which/why.)

## 3. Examples
BAD  front "Definition du nombre de masse A"  back "Le nombre de masse A est le nombre total de nucleons..."
GOOD front "Carbone 14 : A = 14, Z = 6. Combien de neutrons ?"
     back  "8\nN = A - Z : A compte tout le noyau, Z seulement les protons."
GOOD front "\(\lim_{x\to+\infty} \frac{3x+1}{x-2}\) = ?"
     back  "3\nA l'infini seuls les termes dominants comptent : \(\frac{3x}{x} = 3\)."
GOOD front "Vrai ou piege : si \(f(x) \to 0\), alors \(\frac{1}{f(x)} \to +\infty\)."
     back  "Piege !\nTout depend du signe : \(\frac{1}{x} \to -\infty\) quand \(x \to 0^-\)."
GOOD front "Une suite croissante et majoree : elle converge ou pas ?"
     back  "Elle converge\nElle monte mais a un plafond : elle finit forcement par s'approcher d'une limite."

## 4. Volume
6-8 cards per episode, ~30-40 per chapter. Every card must earn its place: if a weak student would not nod or smile, rewrite or drop it.

## 5. Languages
French first and best. Arabic: natural formal MSA with module_terms.json. English: simple. Same meaning in the 3 languages
(not word-for-word). Decimals: point in en, comma in fr/ar. SVG: no Arabic words inside, labels short.

## 6. Self-check before zipping (run it as code + read it)
- every front <= 160, every back <= 400 characters in each language; first back line <= 60 characters
- kind mix close to the table; first card of each episode is easy
- every number/result verified by code; every card's source_block exists in the chapter
- read 10 random cards aloud as a weak student: understandable in 5 s? satisfying? If not, fix.