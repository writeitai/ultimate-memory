# SYNTHESIS — Entity Registry / Ontology / Extraction Subsystem

Lead-architect synthesis of the registry research effort (R1–R10, repo_findings, verify/*,
external_agents/*) against the current design (`entity_registry.md`, `decisions.md` D1–D16,
`objections.md` O2–O6). Decisive where the evidence allows; flags what is still a spike.

**Provenance note (load-bearing).** The four `external_agents/` outputs (Codex R2/R6, Antigravity
R5/R8) are **0 bytes** — the independent cross-checks *never produced output* (only `.err` stubs:
"Reading additional input from stdin..."). R2/R5/R6/R8 say "a second independent take covers this";
that take does not exist. Per `verify/completeness.md` G1, the four most load-bearing questions
(ER cascade, ontology core, extraction, clustering) are therefore **single-source**. What *did*
provide independent scrutiny is the five `verify/` fact-check docs, which re-opened cloned source at
file:line and re-fetched primary papers — every repo-threshold and benchmark number came back
**confirmed** (`verify/numbers.md`, `verify/coref_clustering.md`, `verify/ontology_extraction.md`),
with two cosmetic slips (CORE-KG 28.32 vs 28.25; R6 mis-attributes the constrained-decoding result to
"Tam et al." — it is Geng et al. arXiv 2501.10868). So: the *facts* are well-verified; the *missing*
independent reasoning on R2/R5/R6/R8 is the real gap, and confidence on those four is downgraded one
notch accordingly.

---

## 1. Executive summary — the best path forward (≈10 bullets)

1. **Confirm the architecture; it survived scrutiny.** The transcript/verdict model (mentions →
   resolution_decisions → entities, append-only, merge=redirect, un-merge via `merge_events`
   snapshot), Postgres-single-authority (D6), rebuild-first projections (D7), and the cheap-first
   tiered cascade (D4) are all independently corroborated — by Senzing's incremental/explainable/
   reversible principles (R8), the nDR incremental method (R8/PMC7250616), Wikidata's QID-redirect
   governance (R4), and the universal *absence* of un-merge in every OSS tool (verify confirms zero
   un-merge in Splink/dedupe/Zingg-OSS/Graphiti/coref). Build it as designed.

2. **Coref: MAKE-OPTIONAL, do it inside the E2 call by default, but flip it ON for Czech/Slavic from
   day one.** The industry has dropped dedicated coref (6/6 systems use in-prompt); the only KG
   ablation (CORE-KG, −28% duplication) used an LLM coref *stage*, not a dedicated model, so it
   argues "have coref," not "buy a coref engine." But R1 (default OFF, in-call) and R3 (Czech needs a
   CorPipe-class multilingual model) collide for a Czech-first product. Resolution: **per-language
   default** — English default OFF (in-extraction), Czech/Slavic default ON (multilingual CorefUD
   model). Treat all coref output as candidate mention-links, never committed identity.

3. **Replace the folklore thresholds (JW≥0.92, cosine≥0.88) with per-type, golden-set-tuned bands.**
   JW 0.92 is real (Splink's top name level) but is a Bayes-factor *evidence level*, not a standalone
   accept bar; cosine 0.88 is a guess in a wide empirical band (0.6–0.95). The benchmark spread
   (Magellan 98.4 on clean bibliographic vs 43.6 on textual) proves no global constant works. Ship
   **no numeric threshold without a per-type precision/recall curve** measured on the golden set,
   using Wilson CIs near p≈1.

4. **Adopt the unified Tier 0–5 cascade with loose blocking and tight decisions.** Tier 0 external
   authority → 1 exact (on lemma) → 2 fuzzy blocking (`pg_trgm`, recall-first, low floor) → 3
   phonetic (Daitch-Mokotoff, **not** Soundex) → 4 embedding (Lance, residue only) → 5 LLM
   adjudication on the ambiguous middle band → human review for high blast-radius. LLM cost scales
   with ambiguity, not volume. Publish ONE canonical tier table to kill the R2/R3/R9 numbering drift.

5. **Seed core = 8 schema.org-anchored types + 14 predicates with domain/range.** The familiar-naming
   claim is true in spirit (LLMs interpret labels by pretrained semantics; meaningful≫arbitrary) but
   not in the narrow "schema.org beats other good names" letter — claim only "familiar,
   schema.org-aligned names + registry-rendered descriptions/examples." Enforce domain/range exactly
   as Graphiti's `edge_type_map` (the only structural ontology gate any production system ships); drop
   OWL reasoners. Spot-check the schema.org property mappings before freezing.

6. **Tier-0 authorities at launch: Wikidata (self-hosted reconciler) + OpenAlex + DOI/ORCID/LEI
   deterministic validators.** Never OpenCorporates (viral share-alike / paid) or ISBN-as-authority;
   GitHub/Google-Books only per-scope. Tier 0 is an **accelerator, never a gate**: on miss, mint a
   local ID and fall through (most real-world entities are long-tail misses). Store external IDs as
   aliases, never as the canonical `entity_id`. Self-host snapshots — do not put the write path on
   public rate-limited endpoints (OpenAlex moved to key+credit; Crossref cut limits 2025-12-01).

7. **Clustering: two-stage, never bare transitive closure.** Connected-components only to *gather*
   candidate blobs (with a black-hole guard: raise threshold + repartition when a component exceeds
   size T, à la dedupe `max_components`), then HAC-with-distance-cut *inside* each blob (dedupe's
   `linkage(centroid)`+`fcluster(distance)`) so A≈B, B≈C does not force A=C. Incremental maintenance =
   nDR at n=1 (re-cluster only the 1-hop neighbourhood), which removes insert-order dependence. Never
   Louvain/Leiden for ER (keep it in the D11 community pass). CLIP is unsuitable as primary (assumes
   duplicate-free sources, which conversations violate).

8. **Eval loop ships in v1 (closes O6, half of it).** Build a small **real, human-verified golden
   EVAL set** (~200 labeled pairs/type, ~100 hard positives incl. synthetic father/son/inflection +
   ~100 hard negatives; grow to ~400/type for auto-merge-critical types), per-tier precision/recall
   with Wilson CIs, plus a canary regression harness re-run per `resolver_version`. Keep the **eval
   set strictly separate from any active-learning training set** (AL-biased samples are invalid for
   measurement). Defer learned matchers and the AL training loop past v1.

9. **Scale is comfortable; engineer the indexes, not the row counts.** Only `mentions`/
   `resolution_decisions`/`relation_evidence` are ~10^8 rows and they are never fuzzy-scanned (queried
   by id/doc_id). Blocking runs over `entities`/`aliases` (≤10^7) and `relations` (5–15M). Put fuzzy
   (`pg_trgm` GIN) + phonetic (`daitch_mokotoff` GIN) on the small alias table; keep the hot tables
   btree-only to cap write-amplification; RANGE-partition the 10^8 tables by ingest month;
   embedding/HNSW stays in Lance (D8), never pgvector-in-OLTP (80–120 GB).

10. **Review tooling: BUILD a thin CLI cluster-review queue over Postgres; adopt nothing as system of
    record.** No OSS tool does cluster-queue + append-only reversible verdicts + merge provenance +
    blast-radius gating. Review **clusters, not pairs** (pairwise is quadratic), route only the
    blast-radius-weighted middle band to humans, borrow Splink's waterfall as the evidence panel and
    Zingg's 3-way verdict ergonomics, and append every verdict to `resolution_decisions`/`merge_events`
    (the part nobody else does). **Prototype-first risks: the value/salience gate (O3) and the
    un-merge → bi-temporal-supersession ripple — neither is researched yet.**

---

## 2. Per-question conclusions (R1–R10)

Confidence reflects the verify/* fact-checks AND the missing external cross-check (R2/R5/R6/R8 capped
at **medium-high** since their "second take" produced 0 bytes).

### R1 — Coreference necessity → **MAKE-OPTIONAL (default OFF English, in-extraction). Confidence: high.**
- **Settled answer:** No dedicated coref by default; let the E2 extraction LLM resolve pronouns
  in-call (6/6 surveyed systems do this). Keep a dedicated engine as a registry-configurable,
  per-language pre-pass, default OFF, treating its output as candidate mention-links only.
- **Key evidence (all verified):** 6/6 repos prompt-only; CRAC 2025 dedicated coref still beats LLM
  coref by ~13 CoNLL F1; CORE-KG −28% duplication from removing a coref *stage* (but the stage was an
  LLM, so it validates "have coref," not "buy a model"); fastcoref English-only; CorPipe multilingual
  SOTA is CC BY-NC-SA (non-commercial blocker).
- **Agreement/divergence:** No external agent. `verify/coref_clustering.md` confirms every R1 numeric/
  code claim (two cosmetic slips). **Internal divergence with R3 (see C1) and R6 (C2) is the real
  issue**, resolved in §3/§4 below.

### R2 — ER cascade numbers → **Folklore thresholds rejected; per-type learned bands. Confidence: medium-high** (single-source; numbers verified).
- **Settled answer:** Block loose / decide tight / LLM last. JW≥0.92 and cosine≥0.88 are placeholders
  to be replaced by golden-set-measured per-type bands. Use Fellegi-Sunter Bayes-factor composition
  for the relation/evidence side, not single-field cuts.
- **Key evidence (verified exact):** Splink `[0.92,0.88,0.7]` are per-field Bayes levels not accept
  bars; Magellan 98.4 (clean) vs 43.6 (textual) → no global threshold; GPT-4 zero-shot ≥ fine-tuned
  PLM on textual data + better unseen-entity generalization (PLM transfer cliff −22..61% F1); blocking
  imposes a hard recall ceiling (Abt-Buy 0.94 @ 5,380 vs 0.82 @ 1,076 pairs).
- **Divergence:** Codex R2 = 0 bytes. mem0's 0.95 is a retrieve/update gate, **not** an ER auto-merge
  precedent (verify/completeness C3 / numbers #4) — do not cite it as one.

### R3 — Multilingual / inflected → **New work package WP-ML; lemmatize-before-match. Confidence: high on components, low end-to-end.**
- **Settled answer:** Add a language-aware normalization stage: detect language → lemmatize names to
  nominative (UDPipe2/MorphoDiTa for cs) → store lemma as a first-class alias → Tier 2 fuzzy via
  `unaccent`+`pg_trgm`, Tier 3 phonetic via Daitch-Mokotoff (Postgres-native, UTF-8-safe). Czech coref
  = multilingual CorefUD model, not English OntoNotes. Transliteration is conditional (only if the
  corpus is genuinely multi-script).
- **Key evidence:** Czech declines names across 7 cases (≈7 surface forms/name) — a direct attack on
  D4's `(entity_id, predicate)` blocking; Soundex is English-biased, BMPM/D-M are the multilingual-
  correct methods and `fuzzystrmatch.daitch_mokotoff()` is native PG; NameTag3 86.39 F1, CorPipe
  Czech 80.7/77.1 (verify: ÚFAL-sourced, not re-fetched, low risk).
- **Divergence:** No external agent. **Collides with R1's default-OFF coref (C1).** Resolution: Czech
  defaults coref ON.

### R4 — External authorities (tier 0) → **Wikidata + OpenAlex + DOI/ORCID/LEI; tier 0 never gates. Confidence: medium-high.**
- **Settled answer:** Launch core = Wikidata (self-hosted reconciler, the only standardized multi-type
  one), OpenAlex (scholarly + crosswalk hub), and DOI/ORCID/LEI as deterministic ID validators.
  Never OpenCorporates (viral share-alike + paid) or ISBN-as-authority. GitHub/Books per-scope. On
  miss: mint local ID, fall through, store external IDs as aliases.
- **Key evidence (verify/external_facts confirms all):** Wikidata 122M items CC0 + W3C reconciliation
  API; OpenAlex 271M works CC0 but now key+credit ($1/day) — self-host snapshots; Crossref cut limits
  2025-12-01; GLEIF 2.93M LEIs CC0; OpenCorporates £2,250+/yr, 200 calls/day.
- **Divergence:** No external agent. Sourcing-hygiene caveats only (GitHub "12,500" not on cited page;
  OpenCorporates free-tier terms under-sourced) — none load-bearing.

### R5 — Ontology core → **8 types + 14 predicates, schema.org-anchored, domain/range not OWL. Confidence: medium-high** (single-source; repo claims verified).
- **Settled answer:** D15 is the right cut. Borrow schema.org top types (familiar = pretrained-
  semantics lever), enforce predicate domain/range exactly as Graphiti's `edge_type_map`, drop
  reasoners/cardinality/property-chains (recovered cheaper by rebuild-projection / bi-temporal windows
  / the registry).
- **Key evidence (verify/ontology_extraction confirms):** Graphiti `edge_type_map[(src,tgt)]→[rel]`
  is the ONLY structural ontology gate any production system ships; Cognee loads OWL but enforces NO
  domain/range (zero grep hits), only 0.8 canonicalization that never rejects; YAGO 4.5 precedent
  (schema.org upper, top-down); ICL semantic-anchoring (override rate exactly 0). Steal Graphiti's
  type-promotion-on-merge.
- **Divergence:** Antigravity R5 = 0 bytes. R5 *correctly self-hedges* the schema.org-specific claim
  (refuses to assert a measured delta) — no overclaim.

### R6 — Constrained extraction → **Provider JSON-schema + forgiving parser; dynamic predicate subset; E2/E3 split; one glean pass. Confidence: medium-high** (single-source; one citation error).
- **Settled answer:** E2 = Claimify 4-stage decontextualized NL claims; E3 = closed-IE minimal typed
  triples into the governed schema. Use provider JSON-schema structured output + defensive code
  validation (NOT a hand-written grammar, NOT free-form). Render only the domain/range-admissible
  predicate **subset** per extraction (schema size degrades precision past ~hundreds). One gleaning
  pass or none (D2 evidence aggregation recovers cross-doc misses). GLiNER/GLiREL = optional Phase-2
  pre-filter, not the extractor.
- **Key evidence (verify confirms):** 5/5 repos use typed JSON/Pydantic + forgiving parse, none ship
  grammars; closed-IE limits fabrication; dynamic top-N selection is the proven mitigation;
  constrained decoding *helps* when the schema reasons-first (Geng et al. 2501.10868, GSM8K
  80.1→83.8). **Citation fix:** R6 wrongly attributes this to "Tam et al." (the opposite-conclusion
  paper) — correct to Geng et al.
- **Divergence:** Codex R6 = 0 bytes.

### R7 — Golden set / active learning → **Ship a small real eval set + Wilson-CI metrics in v1; defer AL training. Confidence: high.**
- **Settled answer:** Two distinct assets — a GOLDEN EVAL set (unbiased, measures P/R, tunes
  thresholds) and a TRAINING set (only if a learned matcher is added; AL-sampled, biased, never used
  to measure). v1 ships the eval set + per-tier metrics + canary harness; learned matcher deferred.
- **Key evidence (verified):** binomial CI sizing (~100 @ ±0.10, ~384 @ ±0.05, Wilson near p≈1); AL
  cuts *training* labeling ~3–4× (EHR study, ~2,500–3,100 pairs); OpenSanctions used human labels with
  LLMs benchmarked *against* them (GPT-4o 98.95 F1) — pure-LLM labels are circular for self-measurement;
  GeCo/FEBRL synthetic data for recall stress-tests/canaries only.
- **Divergence:** No external agent. **Internal circularity (C5):** R7's concrete plan (cascade-
  generated, LLM-proposed candidates) is exactly the biased sampling it warns against — must resolve
  (see §4 #7). Also: R7 silently narrowed O6 to ER-only; retrieval eval (recall@k per recipe) is
  dropped (G7) and must be re-added.

### R8 — Incremental clustering + reversibility → **CC-to-gather + HAC-cut; nDR n=1; reversibility in Postgres only. Confidence: medium-high** (single-source; code verified, FAMER magnitude soft).
- **Settled answer:** Never bare transitive closure. Two-stage (CC blob + black-hole guard → HAC
  distance-cut). Incremental = max-both assignment + nDR n=1 (bounded blast radius, order-independent).
  Reversibility state lives ONLY in Postgres (`resolution_decisions` + `merge_events` pre-merge
  snapshot + `merged_into` redirect); D7 makes graph re-pointing on merge/un-merge a free no-op.
  Generic-identifier guard (Senzing): down-weight + re-evaluate when an alias suddenly links many.
- **Key evidence (verify confirms code verbatim):** dedupe HAC `linkage(centroid)`+`fcluster(distance)`
  + `max_components=30000` guard; zero un-merge in any OSS repo; nDR n=1 "same quality as batch"
  (PMC7250616); black-hole entity (Kardeş). FAMER/CLIP magnitude is abstract-sourced (medium) and
  CLIP's duplicate-free-source assumption is violated by ugm → HAC primary.
- **Divergence:** Antigravity R8 = 0 bytes. **Un-merge → relation/validity re-adjudication ripple (G6)
  is unowned** — a real gap.

### R9 — Scale & schema → **Registry is small where it matters; never fuzzy-scan 100M rows. Confidence: medium-high (architecture); medium (absolute numbers, modeled).**
- **Settled answer:** RANGE-partition the three 10^8 append-only tables by ingest month; do NOT
  partition `entities`/`aliases` (blocking targets); btree-only on hot tables, GIN trgm + GIN D-M on
  the small alias table; supersession + tiers 0–3 in Postgres, embedding tier 4 in Lance; keep HNSW
  out of OLTP.
- **Key evidence (verify confirms):** pgvector HNSW 10M×1536 ≈ 80–120 GB; COPY ~100k rows/s
  (backfill 10^8 ≈ 17 min); write-amp 2.5–3.8× scales with index count; `daitch_mokotoff` GIN-indexable
  + UTF-8-safe.
- **Divergence:** No external agent. **All row counts are modeled, not measured (O-2)** and contingent
  on O3's outcome (G9) — load-test before hardening.

### R10 — Review tooling → **BUILD thin CLI cluster-queue over Postgres; adopt nothing as store. Confidence: high.**
- **Settled answer:** No OSS tool provides cluster-queue + append-only reversible verdicts + provenance
  + blast-radius gating. Build it; borrow Splink waterfall (evidence panel), OpenRefine cluster-card-
  with-exclude (interaction), Zingg 3-way verdict (ergonomics). Review clusters not pairs; route only
  blast-radius × uncertainty middle band; every verdict appends to `resolution_decisions`/`merge_events`.
- **Key evidence (verified):** Splink dashboards are read-only (no write-back); OpenRefine merges
  spreadsheet cells not persistent IDs; Argilla is annotation-record-centric (you keep all the
  load-bearing write-back/reversibility logic); pairwise review is quadratic, cluster review is O(1)/
  cluster; r-HUMO/SystemER back blast-radius-weighted routing.
- **Divergence:** No external agent. Minor: `cluster_studio` no-write-back is doc-inferred not JS-read.

---

## 3. Implications for our design (D1–D16, O2–O6)

### CONFIRMED (build as designed — research strengthened these)
- **D4 (cheap-first cascade):** validated by benchmark numbers (cheap tier handles clean majority, LLM
  earns its keep only on textual/ambiguous residue) and by Graphiti's independently-derived identical
  shape (R2). Refinement, not change: insert an explicit loose-blocking tier with a measured recall
  target; make the cheap tier *escalate* near-misses, never auto-reject (textual recall is mediocre).
- **D5 / D15 (governed predicates + domain/range, not OWL):** the single OWL feature any production
  system enforces is predicate domain/range (Graphiti `edge_type_map`); the dropped OWL machinery is
  loaded-but-unused (Cognee) or absent. D15 keeps exactly the validated subset (R5, R6, verify).
- **D6 / D7 (Postgres authority, rebuild-first):** R8/R9 confirm — clustering + reversibility are
  Postgres operations; graph merge/un-merge/retype re-pointing is a free no-op on rebuild; HNSW must
  stay out of OLTP. No OSS tool offers reversibility, so building it in Postgres is correct, not
  over-engineering (verify).
- **D2 / D3 (claims≠relations; relation-level supersession):** R6 confirms the decontextualization-vs-
  minimality tension that *requires* the E2/E3 split; D2 evidence aggregation is what lowers the value
  of deep gleaning. Senzing/Wikidata/nDR confirm the verdict/redirect/reversibility epistemology.
- **D8 (vectors in Lance):** R9 confirms — pgvector at registry scale is the wrong tool; the tier-4
  embedding belongs in the existing Lance estate.
- **D11 (Louvain external, not in ER):** R8 confirms — Louvain/Leiden is community detection, never
  entity resolution; keeping it out of the ER path is correct.
- **D16 (one graph, scope views):** R4 reinforces (per-scope authority connectors are opt-in footprints,
  not new stores); nothing contradicts it.
- **O5 (ER/predicate-governance as a first-class subsystem):** wholly vindicated — this is exactly the
  body of work R1–R10 fills out. Promote to its own design doc with metrics from day one.
- **O6 (eval loop):** confirmed necessary; R7 makes it concrete and shippable in v1.

### CHANGE / ADD (research moves the design)
- **D4 thresholds → must be per-type, golden-set-tuned, three-band.** The doc's `JW≥0.92 / cosine≥0.88`
  placeholders are downgraded to "initial guesses to overwrite." No threshold ships without a per-type
  P/R curve (R2, R7). *This refines D4 and feeds O5/O6.*
- **D4 tier set → insert Tier 0 external authority + a language-aware normalization stage (WP-ML)
  before Tier 1.** Lemmatize-to-nominative + `unaccent` + Daitch-Mokotoff (not Soundex). This is NEW
  relative to the one-line §8.5 placeholder and is required for Czech to not silently split entities
  (R3, R4). *Additive to D4; does not disturb D6/D7/D15/D16.*
- **D4 "coref before extraction" wording → clarify the topology.** D4's text reads as a discrete prior
  stage (R6's reading); R1's cost argument assumes coref *inside* the E2 call. **Decide: coref is a
  logical guarantee satisfied inside E2 by default (English), as a discrete pre-pass when a language/
  scope flag turns it on (Czech/Slavic).** Update D4's wording to say so. (Resolves C2.)
- **D15 wording → soften the schema.org claim** to "familiar, schema.org-aligned names + registry-
  rendered descriptions/examples," and add a concrete seed (8 types / 14 predicates / domain-range
  table) with the note that schema.org mappings need a spot-check (R5).
- **O6 scope → re-add the retrieval-eval half.** R7 narrowed O6 to ER. Recall@k per search recipe (D9),
  rerank-weight tuning, and contradiction-detection precision must be back in the eval plan (G7).

### NEW (not in current decisions/objections)
- **WP-ML — multilingual/inflected work package** (R3): language detection → name lemmatization → alias
  normalization → D-M phonetic + trgm fuzzy tiers → language-aware coref. Czech-first.
- **Golden-set discipline as a hard gate** (R7): two separate assets (eval vs training), Wilson CIs,
  blocking-stratified positive over-sampling, canary regression per `resolver_version`.
- **Tier-0 connector operations** (R4): self-host Wikidata reconciler + OpenAlex/GLEIF snapshots; never
  put the write path on public rate-limited endpoints; external IDs are aliases, never canonical IDs.
- **Black-hole guard + nDR incremental procedure** (R8): mechanized giant-cluster partitioning and
  bounded 1-hop re-clustering on the write path.
- **CLI cluster-review queue with blast-radius × uncertainty routing** (R10).

### CONTRADICTIONS WITH CURRENT DECISIONS — call-outs
- **None fatal.** The only direct decision-level tension is **D4's "coreference resolution runs before
  claim extraction"** vs R1's "coref rides inside the E2 call." This is a wording/topology ambiguity,
  not a wrong decision — resolved by the per-language topology above. Flag it explicitly in D4 so it
  stops generating the R1↔R6 confusion.
- **O2 / O3 / O4 are essentially un-researched by R1–R10** and must not be treated as resolved:
  - **O3 (value/salience gate)** — the stated #1 objection — is absent. It changes R9 row counts, R7
    golden-set composition, R6 `other:` rates, and R1/R8 load. **Mark every downstream quantity
    "assumes full extraction" until O3 is decided.** (G2/G9.)
  - **O2 (collapse K1–K3)** is orthogonal to the registry and untouched here — leave open.
  - **O4 (semantic regenerability / manifests)** untouched — leave open.

---

## 4. Proposed decisions/changes (ready to become D17+ / design-doc edits)

1. **D17 — Canonical resolution tier table (0–5), block-loose/decide-tight.** Publish one authoritative
   definition, ending R2/R3/R9 numbering drift:
   `T0 external-authority match → T1 exact (on normalized lemma) → T2 fuzzy blocking (pg_trgm GIN,
   recall-first low floor, candidate-gen NOT a decision) → T3 phonetic (Daitch-Mokotoff GIN) → T4
   embedding similarity (Lance, residue only) → T5 LLM adjudication (small→frontier) on the ambiguous
   middle band → human review for high blast-radius.` Each tier's accept/reject bands are per-type,
   versioned config stamped with `resolver_version`. *(R2 §4.1, R9 §4.)*

2. **D18 — Ontology seed core.** 8 types (`Person, Organization, Place, Document⊂CreativeWork, Event,
   Concept, Project, Product`) + 14 predicates with `subject_type`/`object_type` columns
   (`works_for, member_of, affiliated_with, located_in, part_of, authored, created, about, knows_about,
   knows, participated_in, works_on, founded, related_to`). `related_to` is the predicate-side core
   parent for extend-never-fork. Time is bi-temporal edge metadata, not a predicate/Date node. Enforce
   domain/range as Graphiti `edge_type_map`; spot-check schema.org mappings before freezing. *(R5 §4.)*

3. **D19 — Coref topology + per-language default.** Coref is a guarantee that no claim leaves E2 with a
   dangling pronoun. **English default: satisfied inside the E2 call (no separate stage).** **Czech/
   Slavic default: ON, dedicated multilingual CorefUD (CorPipe-class) pre-pass.** Engine choice is a
   registry row per language/scope; output is candidate mention-links only, never committed identity;
   pin `resolver_version`. Resolves C1+C2. *(R1 §4, R3 §4 step 7.)*

4. **WP-ML — Multilingual/inflected normalization (new work package).** Intake: language-detect per
   mention → lemmatize names to nominative (UDPipe2/MorphoDiTa for cs; Stanza/spaCy tail) → store lemma
   as first-class alias (`provenance=lemmatizer`) → T1 exact runs on the lemma → T2 `unaccent`+`pg_trgm`
   → T3 `fuzzystrmatch.daitch_mokotoff` (optional app-layer BMPM behind a flag if D-M recall is short)
   → transliteration only if corpus is confirmed multi-script. Acceptance test: measured reduction in
   missed-supersession rate on inflected-name pairs vs the surface-form baseline. *(R3 §4.)*

5. **D20 — Tier-0 authority set + fall-through rule.** Launch: Wikidata (self-hosted reconciler) +
   OpenAlex (snapshot+API) + DOI/ORCID/LEI deterministic validators. Never OpenCorporates, never
   ISBN-as-authority. GitHub/Google-Books per-scope opt-in. **Tier 0 never gates:** on miss, mint a
   local `entity_id` (`method=tier0_miss`) and fall through. External IDs are stored as aliases with
   provenance, never as canonical IDs. Self-host all snapshots; budget for OpenAlex key/credit. *(R4 §4.)*

6. **D21 — Clustering algorithm + incremental procedure + reversibility records.** Decision clustering =
   CC-to-gather (with black-hole guard: raise threshold + repartition above size T) → HAC distance-cut
   inside each blob (never bare transitive closure; never Louvain for ER). Write-path incremental =
   max-both assignment + nDR n=1 (n=2 only when a hub is touched). Reversibility state in Postgres only:
   `resolution_decisions` (append-only, superseded_by), `merge_events` (append-only, pre-merge
   membership snapshot), `merged_into` redirect chain, optional negative/exclusion edges. Generic-
   identifier guard down-weights + re-evaluates over-shared aliases. P2 rebuild re-points edges for
   free. *(R8 §4.)*

7. **D22 — Golden-set + eval plan (v1).** Ship a real, human-verified golden EVAL set (~200 labeled
   pairs/type; ~100 hard positives incl. synthetic father/son/inflection/married-name + ~100 hard
   negatives; grow to ~400/type for auto-merge-critical types), with blocking-stratified positive
   over-sampling and **Wilson** CIs. **Break the circularity (C5):** the cascade/LLM may *propose*
   candidate pairs, but the labels used for measurement must be **human-adjudicated**, and the eval set
   is held **separate from any AL training set**. Canary regression harness re-run per `resolver_version`.
   Defer learned matchers + AL loop past v1. **Re-add the retrieval-eval half of O6** (recall@k per
   recipe, rerank-weight tuning, contradiction precision). *(R7 §4, G7.)*

8. **D23 — Registry scale/schema.** RANGE-partition `mentions`/`resolution_decisions`/`relation_evidence`
   by ingest month (`pg_partman`); btree-only on those hot tables; do NOT partition `entities`/`aliases`;
   GIN `gin_trgm_ops` + GIN `daitch_mokotoff(name)` on `aliases.normalized_name`; btree composite
   `(subject_entity_id, predicate)` (+object) on `relations`; embedding tier in Lance only. Load-test a
   representative corpus slice before locking partition/index choices. *(R9 §4.)*

9. **D24 — Review tooling.** BUILD a thin CLI cluster-review queue over Postgres (web/Argilla deferred
   until middle-band volume justifies it). Review clusters not pairs; route `expected_impact =
   blast_radius × (1−confidence)` middle band to humans; high-degree hub merges never auto-accept;
   render Splink-style waterfall evidence + Zingg 3-way verdict + OpenRefine cluster-card-exclude; every
   action appends a reversible, provenance-stamped, redirect-preserving record. *(R10 §4.)*

10. **Edit — D15 wording + D4 wording.** Soften D15's schema.org claim to "familiar/schema.org-aligned
    names + registry-rendered descriptions/examples; no measured schema.org-vs-synonym delta is
    claimed." Clarify D4's coref wording per D19. Fix the R6 citation (Geng et al. 2501.10868, not Tam
    et al.) wherever it propagates into design docs. *(R5, R6, verify.)*

11. **Edit — extraction design (E2→E3).** E2 = Claimify 4-stage decontextualized NL claims; E3 =
    closed-IE minimal typed triples via provider JSON-schema structured output + defensive code
    validation (no grammars, no free-form); render only the domain/range-admissible predicate **subset**
    per call; one glean pass or none; add an `evidence_quote`/`reasoning` field before the triple
    (reason-first improves constrained-decoding quality); log (don't silently drop) schema-violating
    triples — a dropped triple may be a missed supersession. *(R6 §4.)*

---

## 5. Open risks & what to prototype first

**Spike before committing (highest leverage first):**

1. **The value/salience gate (O3) — research + spike NOW.** It is the stated #1 objection, entirely
   absent from R1–R10, and it silently invalidates R9's row counts, R7's golden-set composition, R6's
   `other:` rate, and R1/R8's load. Prototype a cheap per-document/section salience gate (full /
   deferred / chunks-only) and measure the filter rate on a representative corpus slice. Until then,
   stamp every downstream quantity "assumes full extraction." *(G2/G9.)*

2. **Un-merge → bi-temporal supersession ripple — design spike.** R8 makes cluster membership
   reversible but nobody verified that relation validity windows closed *under the merged identity* are
   correctly re-adjudicated on un-merge. This is exactly where "silent supersession failure" (the
   existential risk, `entity_registry.md` §1) lives. Spike: take a merged pair with a closed validity
   window, un-merge, confirm the re-resolution-campaign + rebuild recomputes supersession cleanly. *(G6.)*

3. **Coref/chunk-size interaction — measure.** R6 wants ~600-token chunks for extraction recall; R1
   relies on the E2 LLM doing long-range in-context coref — small chunks break exactly that, and
   Ref-Long says long-context referencing is already weak. Run the missing ablation on the golden set:
   in-extraction coref @ small-chunk vs +dedicated pre-pass, per language, measuring downstream entity
   duplication. *(G8.)*

4. **Golden-set sampling without circularity — prototype the labeling loop.** Build the LLM-propose /
   human-verify loop (CHI'24 pattern), confirm the human-verified eval set is unbiased enough to
   generalize, and validate the denominator trap is handled (recall needs ~370 true-positive pairs;
   over-sample positives via blocking then re-weight). *(C5, O-7.)*

5. **WP-ML proper-noun lemmatization accuracy — measure.** Surname lemmatization (out-of-dictionary,
   adjectival paradigms) is the unverified hard case; UDPipe-with-disambiguation on Czech surnames must
   be measured before WP-ML is trusted, plus D-M precision/recall on declined names. *(R3 §3.)*

6. **Scale load-test before hardening partition/index choices.** R9 is all-modeled; get real
   mentions-per-doc, GIN index GB, and streaming throughput on a corpus slice — these are the only knobs
   that depend on measured values, and they are contingent on O3. *(R9 §4 #5, O-2.)*

7. **Re-run (or formally drop) the external cross-checks.** R2/R5/R6/R8 advertise independent Codex/
   Antigravity takes that produced 0 bytes. Either re-run them or carry these four at one-notch-lower
   confidence in the design doc. Do not let `registries_design.md` inherit a verification that never
   happened. *(G1.)*

**Also open, lower urgency:** relation/claim dedup mechanics (D2 side under-researched — G4); the
`other:`→core predicate promotion workflow and the cost of splitting a heavily-used predicate (G5);
cross-document definite-NP/pronoun grounding that intra-doc coref can't see (G3); scope-view definition
format in the registry (entity_registry §8.6 — covered by no question).

---

### Source map
R1–R10: `registry_research/questions/R*.md`. Fact-checks: `registry_research/verify/{numbers,
coref_clustering, ontology_extraction, external_facts, completeness}.md`. Repo archaeology (via R-docs):
`registry_research/repo_findings/{cognee,coref,graphiti,letta_hipporag,lightrag_graphrag,mem0,
splink_dedupe,zingg}.md`. External agents: `registry_research/external_agents/*` (all 0 bytes — failed).
Design: `plan/analysis/entity_registry.md`, `decisions.md` (D1–D16), `plan/analysis/objections.md`
(O1–O6).
