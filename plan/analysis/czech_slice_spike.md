# Czech slice spike — inflected-language behavior of the ER cascade (WP-2.1)

**Question** (registries §5, phase-2 plan): does the T0–T4 cascade handle a Czech
name slice — diacritics, morphological inflection, feminine surname forms — or does
an inflected language need machinery beyond the stored canonical aliases + T1/T2
blocking the design bets on?

**Method.** Synthetic golden pairs (marked `is_synthetic`, `adjudicated_by =
'synthetic-starter'`) seeded through `eval/resolution.py` and judged by the cascade's
decision function (`CascadeResolver.judge_pair`) in `src/tests/spine/test_resolver.py`.
The T4 seat is a deterministic stand-in; what the spike measures is which *tier*
carries each case, not model quality.

**Findings** (locked as tests):

| Case | Example | Carried by | Note |
|---|---|---|---|
| diacritic loss | Pavel Kovář ↔ Pavel Kovar | **T0** | `normalized_lemma` accent-folds (NFKD strip), so the pair is lemma-equal — no fuzzy tier needed |
| phonetic spelling drift | Karel Dvořák ↔ Karel Dvorzak | **T1/T2 → T4** | trigram + Daitch-Mokotoff both surface the candidate; the decision correctly escalates (never auto-accepts) |
| feminine surname (-ová) | Jan Novák ↔ Jana Nováková | blocked → **T4 no-match** | trigram similarity is high enough to block, which is correct: these are *usually different people* and must reach adjudication, not be auto-merged on string similarity |
| case inflection | Petr Svoboda ↔ Petra Svobodu | blocked → **T4** | genitive/accusative inflections reach the candidate set via trigram; the LLM-emitted **nominative canonical form** at extraction (registries §5) makes this rare in practice — most mentions arrive already nominative |

**Conclusion.** The design's bet holds for the Czech slice: accent-folded lemmas
(T0), recall-first trigram + Daitch-Mokotoff blocking (T1/T2), and
escalate-never-auto-reject cover the morphology cases without a language-specific
tier. The load-bearing element is the **extraction-time nominative canonical form**
feeding T0 — its quality should be watched per deployment. Threshold values stay
starting points; the real-corpus P/R curves (grown golden set, WP-0.6 tooling)
decide per-type bands.

**Adjustments made:** none required beyond the seeded starting thresholds; the
feminine-surname case is kept in the golden set as a permanent hard-negative canary
so a future threshold change that auto-merges -ová pairs fails the resolution suite.
