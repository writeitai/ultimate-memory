# R3 — Multilingual & Inflected-Language Entity Resolution (Czech focus)

**Question.** Inflected names (`Jiří Puc` → `Jiřího Puce` / `Jiřímu Pucovi`) break naive matching;
English-biased phonetics (Soundex) fail; we need lemmatization-before-matching, Beider-Morse
phonetics, transliteration name-matching, and an honest read on multilingual NER + coref quality
for Czech/Slavic. Recommend a concrete approach for multilingual aliases & matching in the ugm
registry. **Flagged here as a candidate new work package (WP-ML).**

This answers open question §8.5 ("Multilingual aliases and transliteration handling") in
`entity_registry.md` and touches §8.7 (coref engine) and §8.2 (tier thresholds).

---

## 1. Key findings

- **Inflection is a first-class blocker for the registry, not a nice-to-have.** Czech is a
  fusional Slavic language with **7 cases** applied to *people's names themselves* (`Jiří` →
  gen. `Jiřího`, dat. `Jiřímu`, surname `Puc` → `Puce`/`Pucovi`). The same person's name has
  ~7+ distinct surface forms before nicknames/diacritics even enter. This directly attacks D4's
  blocking key `(entity_id, predicate)`: a surface-form-keyed exact/fuzzy tier will *silently
  split* `Jiřího Puce` from `Jiří Puc` → missed supersession (the exact failure mode
  `entity_registry.md` §1 calls existential). **Verified** (Czech declension has 7 cases;
  Wikipedia/Slavic cataloging manual). The fix is well-established: **lemmatize/normalize to
  nominative (citation) form before matching**, which library cataloging already does manually.
- **Soundex is the wrong phonetic tier for this corpus; Beider-Morse (BMPM) and
  Daitch-Mokotoff (D-M) Soundex are the right ones — and Postgres ships D-M natively.** BMPM
  explicitly supports **Czech** (one of 16 languages), keys on language-specific phonetics not
  English spelling, and produces far fewer false hits than Soundex/Metaphone. Crucially,
  **PostgreSQL's `fuzzystrmatch` extension implements `daitch_mokotoff()`** (multi-code,
  UTF-8/multibyte-safe), and `unaccent` strips Czech diacritics, and `pg_trgm` gives indexed
  trigram similarity — so most of the multilingual matching machinery is available *in our
  single authority store* (D6, registry-lives-in-Postgres) with zero new infrastructure.
  **Verified** (PG docs; BMPM language list).
- **Multilingual NER and coreference for Czech are production-viable today, with concrete F1
  numbers — but English-only defaults (the OntoNotes coref model named in our `coref.md`
  finding) would underperform on Czech.** Czech NER: **NameTag 3 reaches 86.39 F1 fine-grained
  / 89.29 coarse on CNEC 2.0** (ÚFAL). Multilingual coref: **CorPipe (CRAC winner) scores
  80.7 CoNLL F1 on Czech-PDT, 77.1 on Czech-PCEDT** — strong, and notably the best LLM coref
  system trailed CorPipe by ~13 points (LLMs are *not* the answer for coref here). The
  registry's lemmatization need is met by the same ÚFAL stack (**MorphoDiTa / UDPipe 2** for
  Czech lemmatization; UDPipe/Stanza cover ~60–100 languages). **Verified** (NameTag 3 models
  page; CRAC 2024/2025 findings).
- **Recommendation (WP-ML): add a language-aware normalization stage to the registry intake and
  a multilingual phonetic tier — do NOT bolt language onto the LLM and hope.** Concrete: (1)
  detect language per mention; (2) **lemmatize names to nominative form** (UDPipe/MorphoDiTa for
  cs, spaCy/Stanza elsewhere) and store the lemma as a first-class **normalized alias** in the
  alias table (`entity_registry.md` §4); (3) make Tier 2 (fuzzy) `unaccent`+`pg_trgm` and Tier 3
  (phonetic) **Daitch-Mokotoff in Postgres**, not Soundex; (4) hold **transliteration** as a
  separate, lower-priority sub-problem (cross-script Latin↔Cyrillic) gated on whether the corpus
  is actually mixed-script. **Confidence: medium** — the components are individually verified and
  off-the-shelf, but no end-to-end Czech-registry benchmark exists; tier thresholds remain
  golden-set-dependent (O6, §8.2).

---

## 2. Evidence & detail

### 2.1 The inflection problem (verified)

Czech is "extremely inflective": nouns and adjectives **including people's and place names**
decline across **7 cases** — nominative, genitive, dative, accusative, vocative, locative,
instrumental ([Czech declension, Wikipedia](https://en.wikipedia.org/wiki/Czech_declension)).
Worked example for the prompt's name:

| Case | "Jiří Puc" form (illustrative) |
|---|---|
| Nominative (citation) | Jiří Puc |
| Genitive | Jiřího Puce |
| Dative | Jiřímu Pucovi |
| Accusative | Jiřího Puce |
| Vocative | Jiří Puci |
| Locative | (o) Jiřím Pucovi |
| Instrumental | (s) Jiřím Pucem |

So a single entity emits ~6–7 distinct token strings *for the name alone*, before diacritic
loss (`Jiri Puc`), nicknames (`Jirka`), or transliteration. Library/authority practice already
handles this manually: names appearing in genitive must be "converted to nominative form before
constructing an authorized access point" ([Slavic Cataloging Manual — Czech and Slovak Personal
Names](https://sites.google.com/site/seesscm/czech-and-slovak-personal-names);
[Czechia Personal Names, FamilySearch](https://www.familysearch.org/en/wiki/Czechia_Personal_Names)).
**This is the lemmatization-before-matching mandate, validated by domain practice.**

Why this is existential for ugm specifically (inference, grounded in our own docs): D4 blocks
supersession detection on `(entity_id, predicate)`; D2 dedupes relations on `(s,p,o)`. Both
presume the entity resolved correctly. An inflected surface form that fails to resolve = a split
entity = a silently-missed supersession and split evidence (`entity_registry.md` §1). The
over-merge asymmetry (§1) means we must *not* fix this by loosening thresholds globally (that
risks fusing distinct people); we must fix it by **normalizing the surface form to a canonical
lemma** so legitimate variants collapse without widening the fuzzy net.

### 2.2 Phonetics: why Soundex fails, what to use (verified)

- **Soundex / Metaphone are English-spelling-biased** and generate large numbers of false hits
  on non-English (esp. Slavic/Yiddish) names
  ([Daitch–Mokotoff Soundex, Wikipedia](https://en.wikipedia.org/wiki/Daitch%E2%80%93Mokotoff_Soundex);
  [Beider-Morse: an alternative to Soundex with fewer false hits](https://avotaynuonline.com/2008/07/beider-morse-phonetic-matching-an-alternative-to-soundex-with-fewer-false-hits-by-alexander-beider-and-stephen-p-morse/)).
- **Beider-Morse Phonetic Matching (BMPM)** keys on the *linguistic properties of multiple
  languages*, not just spelling, supports **16 languages including Czech, Polish, Russian
  (Latin + Cyrillic)**, and produces **fewer false hits than Soundex and Metaphone**
  ([stevemorse.org/phonetics/bmpm.htm](https://stevemorse.org/phonetics/bmpm.htm);
  [BMPM info](https://stevemorse.org/phoneticinfo.htm)). BMPM can guess or be told the source
  language, and emits multiple phonetic keys to cover ambiguity.
- **Daitch-Mokotoff (D-M) Soundex**: 6 meaningful letters (vs Soundex's 4), 10 codes (vs 7),
  emits **multiple codes** when a letter combo has multiple sounds — far better for Slavic names
  ([D-M Soundex, Wikipedia](https://en.wikipedia.org/wiki/Daitch%E2%80%93Mokotoff_Soundex)).
- **Decisive for ugm: PostgreSQL natively supports the right tools.** `fuzzystrmatch` provides
  **`daitch_mokotoff()`** and the docs explicitly note: "Use `daitch_mokotoff` or `levenshtein`
  with multibyte encodings such as UTF-8" — i.e. Czech-character-safe
  ([PG 17 fuzzystrmatch](https://www.postgresql.org/docs/17/fuzzystrmatch.html)). `unaccent`
  removes diacritics as a text-search dictionary
  ([PG unaccent](https://www.postgresql.org/docs/current/unaccent.html)); `pg_trgm` gives
  indexed (GiST/GIN) trigram `similarity()` and `%` operators for the fuzzy tier
  ([pg_trgm tutorial](https://dev.to/talemul/fuzzy-string-matching-in-postgresql-with-pgtrgm-trigram-search-tutorial-2hc6)).
  Net: Tiers 2 (fuzzy) and 3 (phonetic) of D4 can run **in the authority store itself**, no new
  service. BMPM (richer, language-aware, but not in `fuzzystrmatch`) would be an
  application-layer add (libraries exist: `abydos`, Apache Commons Codec, `BMDMSoundex`) if D-M
  proves insufficient.

### 2.3 Lemmatization / morphology tooling for Czech (verified)

- **MorphoDiTa** (ÚFAL, Charles University): morphological analysis + **lemmatization** +
  tagging + tokenization, SOTA for Czech, ~10–200K words/s
  ([MorphoDiTa, ÚFAL](https://ufal.mff.cuni.cz/morphodita)).
- **UDPipe 2** improves on MorphoDiTa: a newer contextual-embedding system reports **~35% error
  reduction in lemmatization vs UDPipe 2 and ~50% vs MorphoDiTa**, and UDPipe covers ~60+
  languages via Universal Dependencies
  ([Czech Text Processing with Contextual Embeddings, Straka et al.](https://link.springer.com/chapter/10.1007/978-3-030-27947-9_12);
  [ÚFAL morphosyntactic web service, arXiv 2406.12422](https://arxiv.org/html/2406.12422v2)).
- **Stanza** (Stanford) and **spaCy** offer multilingual lemmatizers for the non-Czech tail.

**Caveat for names specifically:** general lemmatizers are tuned on common nouns/verbs; **proper
noun (esp. surname) lemmatization is harder** — surnames may be out-of-dictionary and decline by
their own (sometimes adjectival) paradigm. UDPipe with full morphological disambiguation handles
names better than a bare dictionary lemmatizer, but this is the place where the WP must measure,
not assume (see gaps §3).

### 2.4 Multilingual NER quality for Czech/Slavic (verified numbers)

- **NameTag 3** (ÚFAL): on **CNEC 2.0**, **86.39 F1 fine-grained / 89.29 F1 coarse**; seq2seq
  head does nested NER (46 types, 4 containers) at SOTA
  ([NameTag 3 Models, ÚFAL](https://ufal.mff.cuni.cz/nametag/3/models);
  [NameTag 3 paper, arXiv 2506.05949](https://arxiv.org/pdf/2506.05949)).
- **Slavic cross-lingual NER baseline (XLM-RoBERTa-large)**: **92.22 micro-F1 in-domain / 85.03
  cross-domain** on the SlavNER corpus
  ([Cross-lingual NE Corpus for Slavic Languages, arXiv 2404.00482](https://arxiv.org/pdf/2404.00482)).
- **GLiNER-Multi** (compact zero-shot NER): on MultiCoNER (11 langs) surpasses ChatGPT in most
  languages and shows cross-lingual transfer; a 90M model rivals UniNER-13B (~55 F1) on hard
  zero-shot sets ([GLiNER, arXiv 2311.08526 / NAACL 2024](https://aclanthology.org/2024.naacl-long.300.pdf)).
  **Not found in-source: GLiNER's specific Czech F1** — state as unverified for Czech.

Takeaway: a Czech-specialized model (NameTag 3) beats a generic English NER on Czech; a
multilingual encoder (XLM-R / GLiNER-Multi) is a reasonable single-model fallback covering the
long tail. This intersects our `coref.md` repo-finding: **the OntoNotes-trained Maverick/F-COREF
models cited there are English-centric; for a Czech corpus they would underperform** — which is
why the coref engine choice (§8.7) must be made language-aware, not defaulted.

### 2.5 Multilingual coreference quality (verified, including LLM caveat)

- CorefUD / CRAC shared tasks are the benchmark; CorefUD 1.0 had **2 Czech datasets** (PDT,
  PCEDT); CRAC 2024 used CorefUD 1.2 (**21 datasets, 15 languages**, incl. Czech).
- **CorPipe** (ÚFAL, multi-year winner) — **Czech-PDT 80.7 CoNLL F1, Czech-PCEDT 77.1**; CRAC
  2025 CorPipeEnsemble ~75.84 avg (head-match, no singletons)
  ([Findings CRAC 2025, arXiv 2509.17796](https://arxiv.org/html/2509.17796v1);
  [CorPipe CRAC 2024, arXiv 2410.02756](https://arxiv.org/pdf/2410.02756)).
- **LLMs do NOT win coref here:** the best LLM coref system trailed the best supervised system
  by **~13 points**; "all LLMs could beat the non-LLM baseline" but none beat CorPipe
  ([Findings CRAC 2025](https://arxiv.org/html/2509.17796v1)). Relevant to ugm because our
  pipeline already wants coref *before* extraction (D4 consequence; `coref.md` §9) and avoids
  LLMs on the hot path (D9) — the evidence says a trained multilingual coref model (CorPipe-class
  / multilingual CorefUD-trained) is both better *and* cheaper than an LLM for Czech.

### 2.6 Transliteration / cross-script (verified, but scoped as secondary)

Transliteration matching matters when a corpus mixes scripts (Cyrillic ↔ Latin, CJK ↔ Latin) —
e.g. AML/KYC name screening against Latin sanctions lists
([Datactics: transliteration matching](https://www.datactics.com/blog/cto-vision/transliteration-matching/);
[Senzing v4 cross-script ER](https://senzing.com/senzing-ai-sdk-v4-release/)). Research shows
cross-language person-name linking across 20 non-English languages reaching **0.84–0.98
accuracy** ([Multilingual person name recognition and transliteration, arXiv cs/0609051](https://arxiv.org/pdf/cs/0609051)).
Best practice = **transliterate to a common script, then apply fuzzy + phonetic matching** on the
result. **For Czech specifically this is mostly moot** (Czech is Latin-script); diacritic folding
(`unaccent`) covers the common `Jiří`→`Jiri` case. Hold transliteration as a *conditional*
sub-task: only stand it up if the real corpus contains Cyrillic/CJK mentions of the same
entities. **Note:** multilingual embeddings (mE5-large-instruct > LaBSE on cross-lingual STS) can
serve as a *language-agnostic* candidate-generation tier (Tier 4 in D4), and morphological
complexity measurably degrades embedding alignment (analytic langs F1≈0.78 vs agglutinative 0.67)
([Multilingual E5, arXiv 2402.05672](https://arxiv.org/html/2402.05672v1)) — so embeddings help
but do not *replace* lemmatization for inflected forms.

---

## 3. Confidence & gaps

**Well-supported (verified from primary/official sources):**
- Czech has 7 cases and names decline; lemmatize-to-nominative is established authority practice. **High.**
- Soundex/Metaphone are English-biased; BMPM (Czech-supporting) and D-M Soundex are the
  multilingual-correct phonetic methods. **High.**
- PostgreSQL `fuzzystrmatch.daitch_mokotoff`, `unaccent`, `pg_trgm` exist and are UTF-8-safe —
  the matching tiers can live in our authority store (D6). **High.**
- Concrete Czech NER (NameTag 3: 86.39/89.29 F1) and coref (CorPipe: 80.7/77.1 Czech CoNLL F1)
  numbers; LLMs trail supervised coref by ~13 pts. **High** (each number cited to source).
- ÚFAL MorphoDiTa/UDPipe are the Czech lemmatization stack. **High.**

**Inference (reasoned from our docs, not externally measured):**
- That inflected surface forms will *split* entities under D4 blocking unless normalized — a
  direct logical consequence of `(entity_id, predicate)` blocking + surface-form matching, but
  **not empirically measured on our corpus**. **Medium.**
- That the English OntoNotes coref models in `coref.md` would underperform on Czech — strongly
  implied by the existence of dedicated Czech models and CorefUD, but **no head-to-head ran**. **Medium.**

**Gaps / could not verify (flag explicitly):**
- **No end-to-end Czech entity-registry benchmark exists** anywhere I found — every number above
  is component-level (lemmatizer accuracy, NER F1, coref F1), not "ER precision/recall on
  inflected Czech mentions." This must be measured against the ugm golden set (O6, §8.2). **Low
  confidence on end-to-end numbers — do not invent any.**
- **Proper-noun / surname lemmatization accuracy specifically** (vs general-word lemmatization)
  is not separately reported in sources I read; surnames are the hard, out-of-dictionary case.
  **Unverified — must measure.**
- **GLiNER Czech F1** and **BMPM Czech precision/recall on declined names** — not found in
  sources. **Unverified.**
- Whether our corpus is actually multi-script (needs transliteration) vs Czech-Latin-only
  (needs only diacritic folding) — **unknown; corpus-dependent.** Don't build transliteration
  until confirmed.

---

## 4. Recommendation for ugm — WP-ML (candidate new work package)

**Headline: this is a real, separable work package.** It is not covered by D1–D16 and is bigger
than the one-line §8.5 placeholder suggests. Recommend logging it explicitly. It is largely
*additive* to the existing tiered resolver (D4) — it inserts a normalization stage and swaps two
tier implementations — so it does **not** require revisiting the registry architecture (D6
single-authority, D7 rebuild-first, D15/D16 ontology all stand).

**Concrete design, mapped to the transcript/verdict model (`entity_registry.md` §4) and D4 tiers:**

1. **Language detection per mention (intake).** Cheap `fasttext`/`lingua` language ID on the
   mention's context window. Store `lang` on the `mention` row. Drives all downstream choices.
   *(New column; trivial.)*

2. **Name lemmatization → canonical alias (the core of WP-ML).** Run a language-appropriate
   morphological lemmatizer (**UDPipe 2 / MorphoDiTa for `cs`**; Stanza/spaCy for the tail) to
   convert each name mention to **nominative/citation form**. Insert the lemma as a first-class
   row in the **alias table** (`alias → entity, provenance, confidence`, §4) with
   `provenance='lemmatizer'`. This is the single highest-leverage change: it collapses
   `Jiřího Puce`/`Jiřímu Pucovi` → `Jiří Puc` *before* blocking, fixing the D4 split-entity
   risk **without** loosening fuzzy thresholds (preserving the over-merge discipline, §1).

3. **Tier 1 (exact) runs on the lemma**, not the raw surface form. Exact-match recall jumps for
   free once lemmas exist.

4. **Tier 2 (fuzzy) = `unaccent` + `pg_trgm` in Postgres.** Diacritic-folded trigram similarity
   handles `Jiri`↔`Jiří` and minor misspellings, indexed (GIN/GiST), in the authority store
   (D6). Term-frequency adjustment idea from Splink (`splink_dedupe.md` "steal" #2) still
   applies — a rare surname agreeing is stronger evidence.

5. **Tier 3 (phonetic) = Daitch-Mokotoff in Postgres (`fuzzystrmatch.daitch_mokotoff`), NOT
   Soundex.** This is the literal answer to "Soundex fails." Optionally add application-layer
   **BMPM** (Czech-aware, multi-key) if D-M's recall/precision on the golden set is insufficient;
   keep it behind a tier flag so it's measured before adopted.

6. **Tier 4 (embedding) = multilingual embeddings** (mE5-large-instruct class) as
   language-agnostic candidate generation — complements, never replaces, lemmatization (§2.6).
   This already aligns with D9's embedding channel and D8's Lance estate.

7. **Coref engine choice (§8.7) must be language-aware.** Do **not** default to the
   OntoNotes/English Maverick or F-COREF from `coref.md` for a Czech corpus. Use a
   **multilingual CorefUD-trained model (CorPipe-class)** for `cs`; the evidence (§2.5) says this
   beats an LLM by ~13 pts and is cheaper (consistent with D9's no-LLM-on-hot-path rule). If a
   single coref engine must serve all languages, choose the multilingual one over the English
   one. Pin the model in `resolver_version` provenance (§4) exactly as `coref.md` §9 warns.

8. **Transliteration = conditional, lower priority.** Only build a transliterate-then-match path
   (per §2.6) if the corpus is confirmed multi-script. For Czech-Latin-only, `unaccent` (step 4)
   suffices. Decide this from the actual corpus, not speculatively.

9. **Golden set must include inflected/Slavic hard cases (ties to O6, §8.2, §7.1).** The
   labeled mention-pair set must contain: same-entity-different-case pairs (`Jiří Puc` /
   `Jiřího Puce` = MATCH), diacritic variants (MATCH), and **hard negatives** (same-surname
   father/son; two different `Novák`s = NO-MATCH). Tier thresholds (incl. D-M code overlap,
   trigram cutoff) are tuned against *this* set per language — never a global constant
   (`splink_dedupe.md` "avoid" #4).

**What does NOT change:** registry as single authority (D6), append-only mentions + re-decidable
resolution (§4), merge-as-redirect + un-merge (§4), rebuild-first projections (D7),
universal-core ontology (D15), one-graph (D16). WP-ML slots *inside* the existing tier cascade —
it's a normalization stage + two tier swaps + a language-aware coref choice, all of which the
re-resolution-campaign mechanism (§4) lets us roll out retroactively against existing mentions
once the lemmatizer is in place.

**Suggested WP-ML acceptance test:** measured ER precision/recall on a Czech golden set, with the
specific target of **>0 missed-supersession rate reduction** on inflected-name pairs vs the
surface-form baseline — i.e. prove the split-entity risk (§3 inference) is real and that
lemmatization closes it.

---

## Sources

- [Czech declension — Wikipedia](https://en.wikipedia.org/wiki/Czech_declension) ·
  [Surname inflection — Wikipedia](https://en.wikipedia.org/wiki/Surname_inflection) ·
  [Slavic Cataloging Manual: Czech/Slovak Personal Names](https://sites.google.com/site/seesscm/czech-and-slovak-personal-names) ·
  [Czechia Personal Names — FamilySearch](https://www.familysearch.org/en/wiki/Czechia_Personal_Names)
- [Beider-Morse Phonetic Matching](https://stevemorse.org/phonetics/bmpm.htm) ·
  [BMPM info / language list](https://stevemorse.org/phoneticinfo.htm) ·
  [BMPM: fewer false hits than Soundex (Beider & Morse)](https://avotaynuonline.com/2008/07/beider-morse-phonetic-matching-an-alternative-to-soundex-with-fewer-false-hits-by-alexander-beider-and-stephen-p-morse/) ·
  [Daitch–Mokotoff Soundex — Wikipedia](https://en.wikipedia.org/wiki/Daitch%E2%80%93Mokotoff_Soundex)
- [PostgreSQL fuzzystrmatch (daitch_mokotoff, levenshtein, UTF-8)](https://www.postgresql.org/docs/17/fuzzystrmatch.html) ·
  [PostgreSQL unaccent](https://www.postgresql.org/docs/current/unaccent.html) ·
  [pg_trgm trigram tutorial](https://dev.to/talemul/fuzzy-string-matching-in-postgresql-with-pgtrgm-trigram-search-tutorial-2hc6)
- [MorphoDiTa — ÚFAL](https://ufal.mff.cuni.cz/morphodita) ·
  [Czech Text Processing with Contextual Embeddings (UDPipe 2, Straka et al.)](https://link.springer.com/chapter/10.1007/978-3-030-27947-9_12) ·
  [ÚFAL morphosyntactic web service (arXiv 2406.12422)](https://arxiv.org/html/2406.12422v2)
- [NameTag 3 Models — ÚFAL (CNEC 2.0: 86.39/89.29 F1)](https://ufal.mff.cuni.cz/nametag/3/models) ·
  [NameTag 3 paper (arXiv 2506.05949)](https://arxiv.org/pdf/2506.05949) ·
  [Cross-lingual NE Corpus for Slavic Languages (XLM-R: 92.22/85.03 F1) (arXiv 2404.00482)](https://arxiv.org/pdf/2404.00482) ·
  [GLiNER (arXiv 2311.08526 / NAACL 2024)](https://aclanthology.org/2024.naacl-long.300.pdf)
- [CRAC 2025 Findings: LLMs vs CorPipe, Czech 80.7/77.1 (arXiv 2509.17796)](https://arxiv.org/html/2509.17796v1) ·
  [CorPipe at CRAC 2024 (arXiv 2410.02756)](https://arxiv.org/pdf/2410.02756) ·
  [CorefUD / CRAC 2022 Findings (arXiv 2209.07841)](https://arxiv.org/pdf/2209.07841)
- [Multilingual person name recognition & transliteration (arXiv cs/0609051)](https://arxiv.org/pdf/cs/0609051) ·
  [Datactics: transliteration matching](https://www.datactics.com/blog/cto-vision/transliteration-matching/) ·
  [Senzing v4 cross-script ER](https://senzing.com/senzing-ai-sdk-v4-release/) ·
  [Multilingual E5 (arXiv 2402.05672)](https://arxiv.org/html/2402.05672v1)
