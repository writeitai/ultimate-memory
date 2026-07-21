# Retrieval Stress Scenarios — the query battery (S1–S63)

The scenario set that drives `retrieval_design.md` (binding, D48–D51): concrete questions the system
must answer (or must *honestly refuse*), spanning every plane, both time axes, all four target
deployments (personal assistant, agency brain, data-migration project, law engine), and every
consumption pattern from point lookup to corpus orientation. Written per the review's F4
recommendation (`design_review_2026_07.md`): the retrieval design must be validated against
concrete consumer queries *before* it hardens, and any scenario that cannot be composed from
the designed primitives is a design finding.

**How to read a scenario.** Each has: the question (with deployment flavor), *what it
stresses*, and the *expected path* through the system (entry → expand → hydrate, per D9). The
battery deliberately includes questions the system must **refuse with a capability boundary**
(marked ⛔) — honest failure is part of the contract. Scenarios marked ⏳ depend on an open
decision, named inline.

**Second use.** Every scenario here is a seed for the retrieval half of the D22 eval
(recall@k per recipe, per scenario class). The battery is the golden-set skeleton.

Grain vocabulary (see `concepts.md`): **fact grain** = relations/observations with adjudicated
validity ("what the system currently holds true"); **evidence grain** = claims ("what sources
asserted", immutable, possibly stale/contradictory); the query surface must never let one
masquerade as the other (requirements §Retrieval, D41).

---

## A. Point lookups — fact grain, the baseline

- **S1** *(assistant)* "What is Bob's current employer?"
  Stresses: the trivial path stays trivial — zero LLM, no K, no claims.
  Path: entity-resolve "Bob" → relations `(bob, works_for, ?)` live filter → hydrate labels.
- **S2** *(agency)* "What is Acme's current headcount?"
  Stresses: observation lookup is *semantic* (no typed attribute key, D43).
  Path: entity block on Acme → semantic match "headcount" over observation statements → live window.
- **S3** "Who works at Acme right now?"
  Stresses: reverse lookup (object-side blocking index).
  Path: relations `(?, works_for, acme)` live → hydrate subjects.
- **S4** *(law)* "Is statute §12 currently in force?"
  Stresses: fact routing discipline — must answer from relations/observations, never from a
  claim's asserted validity (D41's bar).
  Path: entity-resolve §12 → its status observation / relation windows, live.

## B. Provenance and audit — hydrating down

- **S5** "Show me the sources saying Alice is VP of Engineering."
  Stresses: the full hydration chain, ID-addressed end to end.
  Path: relation → `relation_evidence` → claims (`source_span`, offsets) → documents → GCS artifact URIs.
- **S6** "What exactly did the 2024 10-K say about headcount?"
  Stresses: doc-scoped evidence-grain retrieval; verbatim spans.
  Path: claims filtered by `doc_id` + semantic/FTS "headcount" → `claim_text` + `source_span`.
- **S7** "Which documents evidence the Acme–Beacon partnership, and with what stance?"
  Stresses: stance exposure (supports vs contradicts) in the answer shape.
  Path: relation → evidence rows with `stance` → docs.
- **S8** "Why does the system believe Alice left Acme?"
  Stresses: transcripts as query surface — the audit path is a first-class query.
  Path: relation → `relation_adjudications` (which rung, why) → superseding evidence → sources.

## C. Temporal — both axes, and their composition

- **S9** "What was Acme's headcount in mid-2024?"
  Stresses: valid-time as-of on observations (the D43 worked example).
- **S10** "What did we believe about Alice's employer last March?"
  Stresses: transaction-time as-of (`ingested_at`/`invalidated_at`) — belief history.
- **S11** "What did sources assert held during 2023 about Atlas's markets?"
  Stresses: `claims_as_of` — evidence grain, D41; the answer must be *labeled* evidence and the
  recipe barred from posing as current fact.
- **S12** "How did Acme's headcount evolve 2022–2026?"
  Stresses: entity timeline — ordered capped windows; history as a first-class shape.
- **S13** "When did we *learn* the merger closed?"
  Stresses: exposure of transaction metadata (ingested_at of the decisive evidence).
- **S14** "What changed about the migration in the last two weeks?"
  Stresses: delta queries (new/capped/invalidated since T, scoped) — the change feed as a query.
- **S15** "Who worked at Acme **when the Beacon contract was signed**?"
  Stresses: **temporal composition** — the as-of instant is *derived from another fact* (the
  signing's event time), then applied to `works_for` windows. Two primitives composed, no
  special machinery.
- **S16** *(law)* "Was the §12 amendment in force when the ruling was issued?"
  Stresses: same composition pattern; comparing two validity windows.

## D. Multi-hop / graph

- **S17** "How are Alice and the Beacon project connected?"
  Path: entity-resolve both → SHORTEST path over live edges (P2 snapshot).
- **S18** "Everything within 2 hops of Acme, current."
  Stresses: hub neighborhoods — caps must be **explicit** (truncation marker + continuation),
  never silent (the no-silent-caps rule).
- **S19** *(migration)* "Which people worked on projects connected to the ESB migration?"
  Stresses: predicate-constrained multi-hop (`works_on` → `part_of`/`depends_on`).
- **S20** "Colleagues of Bob who know about vector databases."
  Stresses: graph join across predicates (`works_for` co-membership + `knows_about`).
- **S21** "Who was connected to Atlas, by any path, as of 2024-06?"
  Stresses: multi-hop as-of via inline path predicates (D44 — projected graphs don't `MATCH`);
  the known perf spike.
- **S22** "Which documents ultimately cite the original spec?"
  Stresses: document-graph traversal (`DOC_CROSSREF` transitive).

## E. Contradiction surfacing — the non-negotiable shape

- **S23** "What was Acme's FY2023 revenue?"
  Stresses: **both** figures return ($5M, $7M) with their shared `contradiction_group` and
  per-side evidence — the system never picks (requirements; D43 no-cap rule).
- **S24** "Where do our sources disagree about Acme?"
  Path: contradiction groups scoped to the entity, both relations and observations.
- **S25** "Do any beliefs about the migration rest on contradicted evidence?"
  Stresses: cross-plane integrity — K belief citations joined against contradict state.

## F. Aggregation and analytics

- **S26** *(migration)* "How many modules depend on legacy table T?"
  Path: scalar count on relations (`object=T, predicate=depends_on`).
- **S27** *(migration)* "List all decisions made in Q1 about the migration."
  Stresses: Work-pack query patterns — `Decision` entities, windows, scope filters.
- **S28** "The most-evidenced facts about Acme."
  Stresses: `evidence_count` as an exposed, sortable salience signal.
- **S29** ⛔ "All portfolio companies with revenue above $5M."
  **Capability boundary** (D43: no structured value column → no cross-entity numeric range
  scans). Contract: an explicit boundary error naming the limitation + the workaround
  (per-entity lookups; K fact sheets) — never a silent empty result.
- **S30** "Which entities gained the most new evidence this month?"
  Stresses: delta aggregation (ops/curiosity class).

## G. High-level orientation — the K plane as answer

- **S31** "Brief me on Acme before the call."
  Path: K entity page (compiled) + its freshness footer; fact-sheet-only fallback. Stresses:
  K-first routing and freshness honesty.
- **S32** "What do we know about the EU expansion — and what changed our mind?"
  Stresses: the product's headline promise. K topic/belief pages + superseded relations with
  their adjudication transcripts ("changed our mind" = invalidated/superseded belief-relevant
  facts, mechanically enumerable).
- **S33** *(migration)* "Summarize the open tensions in the migration scope."
  Path: contradiction groups + open authored-review flags + the K synthesis pages.
- **S34** *(migration)* "What is the current standing target architecture?"
  Stresses: compiled to-be pages **plus reader-facing flag state** — an agent must see "N
  unresolved evidence-change flags" before planning against the answer (k_layers spike 9).
- **S35** "Which K pages are stale right now, and why?"
  Stresses: the control plane itself is queryable (inputs-hash mismatches + deltas).

## H. Attributed content and stance

- **S36** "What did Alice say about the migration timeline, in order?"
  Path: attributed claims (speaker mention → Alice) ordered by `asserted_at`; evidence grain,
  labeled as such.
- **S37** "Who disagreed with the ESB decision?" *(unblocked by D59)*
  Stresses: stance observations — attributed stances normalize to observations anchored on
  their holders ("X opposes the ESB decision"), searchable and as-of-queryable like any fact.
  Path: resolve the decision/topic → semantic match over stance-observation statements →
  holders; stance changes are ordinary supersession ("who *still* opposed it in May?" =
  as-of).
- **S38** *(assistant)* "What did I promise Bob last month?"
  Stresses: D42 `origin` as a query filter (self-generated docs), attribution + time window.

## I. Absence and coverage

- **S39** "Do we know anything about Contoso?"
  Stresses: the negative-answer taxonomy — *unknown entity* must be distinguishable from
  *known entity, no facts*.
- **S40** *(migration)* "Which modules have no documented interfaces?"
  Stresses: absence via anti-join (typed entity enumeration minus predicate existence) —
  answerable *because* the ontology types the entities.
- **S41** "Is there evidence *against* belief B?"
  Path: belief page citations → contradicting-stance evidence rows.

## J. Freshness and reproducibility

- **S42** "How fresh is this answer?"
  Stresses: the freshness contract — every response stamped per source (PG live; P1 write
  lag; P2 snapshot timestamp; K `compiled_at` + stale/flag state). Mixed-freshness reasoning
  (`questions.md` #23) becomes data, not folklore.
- **S43** "Answer as of the audit date — using only what we knew then."
  Stresses: transaction-time caps applied coherently across *all* channels at once.

## K. Navigation — the filesystem and the map

- **S44** *(any, agentic)* Find the Acme material by `ls`/`grep` over the mounted corpus fs,
  drill from `_index.md` into artifacts.
  Stresses: P3 as a first-class query modality; path stability contract.
- **S45** "Which page should I read about X?"
  Stresses: reverse routing — `pages_about(entity | key)` answered from the **K rule-key
  index** (the routing infrastructure doubles as a discovery index); plus `llms.txt`
  orientation for browse-first agents.

## L. Hybrid cross-plane — the flagship compositions

- **S46** *(vague)* "Anything about pricing problems with European customers?"
  Path: parallel channels (semantic claims+relations+chunks, BM25, FTS) → RRF → graph-distance
  + evidence-count rerank → hydrate (the D9 flagship).
- **S47** "Everything Alice said about pricing, in order — plus what we currently believe."
  Stresses: both grains in one composed answer, **explicitly separated** (evidence timeline ↔
  fact snapshot) — the requirements' split made visible in a single response.
- **S48** *(assistant)* "Given this email thread, whom should I loop in?"
  Path: thread entities → neighborhood expansion → people ranking by
  relevance/evidence/recency. Agent composes; primitives suffice.

## M. Scale, multilingual, adversarial

- **S49** Hub entity ("me", the agency's own company): full neighborhood at 10⁴–10⁵ edges.
  Stresses: pagination, ranked truncation with explicit markers, never a timeout.
- **S50** *(Czech)* "Kde pracuje **Jiřího Puce**?" / "u Jiřího Puce" — the query carries an
  **inflected (genitive/accusative) form**, not the nominative.
  Stresses: query-time entity resolution reuses the T0–T2 deterministic tiers (canonical
  aliases + trigram + Daitch-Mokotoff) — no LLM on the hot path (D17, registries §5).
- **S51** "Where does John work?" — four Johns in the registry.
  Stresses: the ER-at-query contract — return ranked disambiguation candidates, never a silent
  guess; optionally narrowed by the caller's focal-entity context.
- **S52** Verbatim needle: an exact phrase over ~5×10⁷ claims.
  Stresses: the FTS/BM25 path at scale, no vector detour.
- **S53** Full export: "stream every live relation in the migration scope."
  Stresses: the batch/scan surface is distinct from the interactive path (compilers, K
  writers, and auditors are also retrieval consumers).

## N′. Harness consumption — filesystem-first (primary consumers: Claude Code / Codex / OpenCode)

- **S56** *(any, mounted)* A coding harness with the mounts available answers "brief me on
  Acme, then check the source figure" entirely on the filesystem: K page → P3 entity folder →
  E0 artifact `document.md` → **the referenced figure image**, read directly as media.
  Stresses: the Markdown-first-media-available contract — navigation points to Markdown, but
  source imagery is on the browse path (conversion is lossy exactly where sources are visual).
- **S57** *(any, unmounted)* The same task in an environment that cannot mount: every artifact
  of S56 is reachable via API/CLI (parity), including fetching the image bytes by artifact
  handle.
  Stresses: full mount/API parity; the precedence rule (prefer filesystem when mounted; API/CLI
  reserved for query-engine capabilities — semantic search, graph, as-of, hydration — which
  have no filesystem equivalent).
- **S58** *(cold agent)* A harness that has never seen this system is pointed at the memory
  and, from the shipped **consumption skill** alone (planes, grains, testimony currency,
  freshness, contradiction semantics, mount layout, precedence rules), correctly: orients via
  K, **routes is-it-true questions to the fact layer by default**, distinguishes fact from
  evidence in its answer, respects `support: withdrawn` markers, and does not misuse
  `claims_as_of` or superseded testimony as current truth.
  Stresses: the skill is a first-class deliverable — the system must be usable well with zero
  human explanation; this scenario is its acceptance test.
- **S59** *(any, multimodal)* "Review the recorded steering call and check what was actually
  agreed about the cutover date" — the agent finds the meeting via P3/K, reads the transcript
  from artifacts, then follows the **explicit raw pointer** to ingest the original MP3/video
  itself (the transcript is lossy; tone and the exact exchange matter). **Strengthened (D65):**
  the pointer is not to the whole file — the claim's **source locator** deep-links the exact
  interval (`original.mp3#t=873`, segment-or-word precision as the ASR delivered), so the
  agent lands at 14:33, not at the start of 90 minutes. And **parity is part of the pass
  bar**: a *mounted* agent seeks via the deep link; an *unmounted* agent gets the same ten
  seconds through the locator-aware serving operation (`hydrate depth=bytes` + time range) —
  it must never need to download 2 GB to check one exchange.
  Stresses: the raw mount (D51) — whole-file media originals reachable read-only, off the
  navigation path, audit-logged; storage-class routing keeps the read cheap; typed source
  locators + codec-aware segment serving (D65).

## N. Security and lifecycle

- **S54** ⛔ A generic search by an agent "without the people-profiles scope" leaking
  profile facts — **out of library scope by design** (retrieval_design §9): a deployment is
  **one trust domain**; every agent that reaches it is trusted with all of it. Content-level
  authorization would have to hold across every channel at once (Lance, graph, PG FTS, K, P3,
  raw — mounts cannot query-time-filter), which degenerates to a deployment inside a
  deployment; the deployment boundary *is* the isolation mechanism (registries §1). Data with
  a different trust boundary belongs in a **separate deployment**. Perimeter security (who
  reaches the API/mounts at all) is deployment infrastructure, not the library.
- **S55** ⏳ After a hard-forget of document D: no query — semantic, verbatim, graph, K, or
  browse — resurfaces its content; and *forgotten* is indistinguishable from *never existed*
  (deletion cascade §13; K git-history erasure). **This is the contract; D74 now designs the
  P1/P2/P3/K active-store purge and restore non-resurrection path.** Its CI gate activates when
  WP-7.5's executable canary is green, not merely because the design exists. Physical backup
  retention is operator/cloud policy under D60; the library makes restored serving state safe
  through portable-manifest replay regardless.

## O. Identity lifecycle — merges, un-merges, identity as-of

- **S60** "What do we know about **Acme Corp**?" — where `Acme Corp` was merged into `Acme`
  last month (a `merged_into` redirect, D21).
  Stresses: query-time resolution follows the survivor chain (the old name still resolves —
  aliases survive merges); the envelope discloses the redirect (resolved-as: Acme, via merge).
  Path: resolve → redirect chain → survivor's facts; `transcript(entity)` exposes the merge.
- **S61** "As we understood it **last March** (pre-merge): what did we believe about Acme
  Corp?" — `believed_at` predates the merge.
  Stresses: **identity-as-of is transcript-based, not automatic**: `resolve` always returns
  *current* identities; reconstructing a pre-merge identity boundary walks
  `resolution_decisions`/`merge_events` (the `transcript` primitive) and re-scopes the query
  to the pre-merge membership — a documented recipe (`identity_as_of`), not a default. An
  un-merge (D21 reversal) is the same machinery mirrored. The envelope must say which identity
  regime answered.

## P. Media discovery and grounding (D65)

- **S62** *(assistant, multimodal)* "Find the photo with the **small red connector**" — where
  the VLM's stored description of the right photo says "a workshop bench with a disassembled
  pump" and never mentions any connector. Text search over descriptions **must** fail here
  (the words don't exist), and that failure is the scenario's point: discovery must not be
  bounded by what the derivation happened to write down.
  Path: `search(channel=semantic, target=media_segments, query="small red connector")` —
  cross-modal embeddings match the *pixels*; the hit hydrates to description passage +
  thumbnail preview + the raw deep link, RRF-fusable with the text channels.
  Stresses: the `media_segments` P1 target; **access ≠ discovery** (an agent can open any file
  it found, never one it didn't retrieve); the typed `boundary` negative when the deployment
  has no media embedder configured — the missing channel is stated, never silently absent.
- **S63** *(any, multimodal)* "Where exactly does the **Q3 roadmap slide** appear in the
  recorded all-hands, and does the fact we extracted from it actually match what's on screen?"
  — the agent retrieves the fact, reads its provenance: `evidence_mode: model_observation
  (vlm_shot_notes)`, follows the **video-region locator** (`start_ms`/`end_ms` + keyframe +
  region) to the exact moment and frame, and verifies against the raw pixels.
  Stresses: image-region/video-region locators — version-pinned (the locator names the
  document *version* whose bytes it indexes, never the lineage), precision-honest; derivation
  disclosure in the envelope (the agent knows it is checking a model's observation, not
  rendered text); the two-hop grounding chain (claim → span → source map → raw region) that
  the modality-aware D32 audit walks.

---

## Coverage map — what the battery exercises

| Capability under test | Scenarios |
|---|---|
| fact-grain lookups + validity filters | S1–S4, S9–S10, S23 |
| evidence-grain + provenance chain | S5–S8, S11, S36, S47 |
| the two grains kept distinct | S4, S11, S47 (the pair-test: same topic, both grains) |
| temporal: valid-time / transaction-time / composition | S9–S16, S21, S43 |
| graph traversal + reranking | S17–S22, S46, S48 |
| contradiction surfacing | S23–S25, S33, S41 |
| aggregation + honest boundaries | S26–S30, S40 |
| K plane as answer + meta-queries | S31–S35, S45 |
| entity resolution at query time | S1, S50, S51, S60 |
| identity lifecycle (merge / un-merge / identity-as-of) | S60, S61 |
| media: raw access, locators, discovery, disclosure | S56, S59, S62, S63 |
| freshness / staleness exposure | S31, S34, S35, S42 |
| negative answers + capability errors | S29, S39, S55 |
| scale / batch / hubs | S18, S49, S52, S53 |
| trust boundary (documented) + deletion | S54 ⛔, S55 |

## Deliberate boundaries the design must state (not solve)

1. **No cross-entity numeric range scans** (S29) — the D43 price; explicit error + workaround.
2. **No prose generation on the query path** (D9) — answers are structured envelopes; the
   *agent* writes prose. "Summarize X" routes to the K plane (S31) or is the caller's job.
3. **Claims never answer "is it true now"** (S4/S11) — the recipe registry bars it (D41).
4. **Corpus-wide open-ended synthesis** ("what's interesting in the corpus?") is the K plane's
   compile-time job, not a query — the query surface serves what K precomputed (S31–S33).
5. ~~Attributed-stance dependency~~ **resolved (D59)** — attributed stances are kept and
   normalized to holder-anchored observations; S37 is a live scenario.
6. **Content-level authorization / per-user scoping** (S54) — a library non-goal: one trust
   domain per deployment; isolation = separate deployments; perimeter auth = deployment
   infrastructure (retrieval_design §9).

## Open items this battery exposes for the design

- The **response envelope** must carry: grain label, validity windows, freshness stamps,
  contradiction co-members, truncation markers, provenance handles (S23, S29, S42, S49).
- **Temporal composition** (S15/S16) requires as-of values derivable from prior results —
  a composition property of primitives, not a recipe.
- **`pages_about`** (S45) — the K rule-key index doubles as a reader-side discovery index.
- **Negative-answer taxonomy** (S39, S55): unknown / known-empty / boundary-refused /
  forgotten-as-never-existed. (No `denied` kind — content authz is out of library scope, S54.)
- **Batch surface** (S53) distinct from interactive; both zero-LLM.

## References

Decisions already fixing retrieval shape: D8 (relations vectors in Lance), D9 (channels + RRF
+ rerankers + recipes, zero LLM), D10/D44 (as-of mechanics), D41 (`claims_as_of`, the bar),
D43 (observation retrieval semantics + the numeric-scan boundary), D16 (scope views), D22
(retrieval eval). Requirements §Retrieval. The K reader surface: `k_layers_design.md` §5
(reader-facing flags, spike 9). This battery feeds `retrieval_design.md` (D48–D51) and the
D22 retrieval golden set.
