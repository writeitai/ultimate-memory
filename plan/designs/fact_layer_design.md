# The Fact Layer — One Verdict Layer for Entity *and* Literal Facts (Design)

How the system turns immutable claims into the **facts it currently believes** — for *both*
relationships between entities (*"Alice works at Acme"*) and values attached to one entity
(*"Acme's headcount is 600"*) — in **one** unified layer, with **one** bi-temporal supersession
engine. Binding design for decision **D43**. It replaces the separate `relations` table and the
surface-only `claim_attribute_facts` projection (D42) with a single `facts` table; it builds on D2
(claims vs. facts), D3 (supersession over verdicts, never claims), D4 (the cheap-first cascade), D6
(validity has one home), D8 (vectors in Lance), D18 (the graph holds only entities), D41 (claims carry
an immutable asserted-validity interval), and D42 (which it subsumes). Full research + the rejected
alternatives + the reviewer round: `plan/analysis/fact_layer_architecture_research/`.

> **Reading this cold (CLAUDE.md Rule 1).** You do not need prior context. §1 gives the mental model
> with a running example; §2 the one idea; §3 the gate that makes it correct; §4 the worked examples;
> §5–§9 the mechanism, schema, and graph projection. Three recurring terms, defined here: a **claim**
> is an atomic, immutable, natural-language assertion *as a source made it* (the evidence record — it
> is never edited or "superseded"); a **fact** is the system's *current, adjudicated belief* about one
> thing in the world (revisable: its validity window can close); **bi-temporal** means we track two
> clocks — when a fact was *true in the world* (`valid_from`/`valid_until`) and when *we believed it*
> (`ingested_at`/`invalidated_at`). The split is the courtroom analogy: claims are the testimony
> (immutable), facts are the verdict (revisable).

## 1. The mental model, with a running example

Three documents arrive:

- **Doc A** (Jan 2024 press release): *"Acme today announced Alice Novak joins as VP of Engineering."*
- **Doc B** (a 2024 filing): *"Acme's headcount was 500 at year-end 2023; revenue was \$5M for FY2023."*
- **Doc C** (a 2025 report): *"Acme now employs around 600 people."*

Extraction (E2) writes these as **claims** — immutable, with provenance and an asserted time window
(D41). Then a normalization step (E3) decides **what the system currently believes** and writes
**facts**. Crucially, two *different shapes* of fact come out of the same documents:

- **Entity facts** — both ends are entities: `(Alice) —works_for→ (Acme)`. These are graph edges.
- **Literal facts** — the object is a *value*, not an entity: `(Acme) —headcount→ 500`,
  `(Acme) —fiscal_revenue→ $5M`. A value like `500` or `$5M` is **not** an entity, and by D18 it must
  never become a graph node. These are *not* graph edges.

Before D43, the system had a verdict layer (the `relations` table, with bi-temporal windows and
supersession) **only for entity facts**. Literal facts had no verdict layer — D42 could only *surface*
them and their conflicts, never record a believed, time-traveled value. So *"what was Acme's headcount
as of mid-2024?"* had no structured answer. **D43 gives literal facts the same verdict machinery
entity facts already had**, in one table.

## 2. The one idea — `fact` is the verdict layer; `relation` is just its graph-projectable subset

The reframe at the heart of D43: **stop treating "relation" as the name of the verdict layer.** The
foundational object is a **`fact`**:

```
fact = (subject_entity, governed_relationship, object)        -- object is an ENTITY or a typed LITERAL
     + bi-temporal window (valid_from/valid_until, ingested_at/invalidated_at)
     + evidence (the claims that support/contradict it)
     + contradiction group (when two facts conflict and can't be adjudicated)
     + an append-only adjudication transcript (why the window closed, etc.)
```

A **relation** (*"Alice works at Acme"*) is simply a fact **whose object is an entity** — and that
subset is exactly what the graph (P2) can hold. So `relations` becomes a **read-only view** over
`facts WHERE object_kind='entity'`, and the graph projects that view. Literal facts live in the same
table, get the same windows and supersession, but never enter the graph.

**Why one table, not two** (the decisive reasoning, from the analysis):

- **One belief home (D6).** A balance and an employment are both *a subject + a governed relationship +
  an object that holds over a time window*. They differ only in whether the object is identity-bearing
  (an entity) or value-bearing (a literal) — which is a *graph-projection* concern, not a *truth*
  concern. Putting them in one table keeps validity in exactly one place. A **separate**
  `proposition_facts` table was rejected: it is a *second* belief authority that drifts against
  `relations` for the same real-world fact across the promotion seam (the documented Mem0 desync
  failure D6 exists to prevent), and it duplicates the entire window/evidence/contradiction apparatus.
- **One engine.** The supersession/contradiction cascade (D4) — block on `(subject, relationship)`,
  compare, close a window or flag a contradiction — is identical for both kinds once the object is
  reduced to a canonical identity. Value normalization (money/date/unit) is **pre-processing** *before*
  the engine, exactly as entity resolution is pre-processing before relation normalization; the engine
  itself sees one shape.
- **Claims stay immutable (D3).** The verdict revises; the testimony never does. "Make claims
  mutable / give a claim a system-set `valid_until`" was ruled out — it destroys the evidence record
  and faces the "absurd task" (a new value would have to close *every* prior claim). The fact row is
  the right unit of supersession: one window closes, N immutable evidence rows are untouched.

## 3. The gate that makes it correct — `supersedable`

Here is the subtlety that a naïve "just put literals in the facts table" gets wrong, and the reason
D43 is more than a table merge. **Not every literal fact may supersede.** Two literal cases look
similar but are semantically opposite:

- **A changing *state*** — *"Acme's headcount is 500"* (Jan), then *"…600"* (later). The later value
  **should close** the earlier (one headcount at a time). This is the affirmed must-have.
- **A *period figure* with conflicting sources** — Doc X: *"FY2023 revenue \$5M"*; Doc Y: *"FY2023
  revenue \$7M"*. Same period, different sources — this is a **disagreement**, and the system must
  **never silently pick a winner** (requirements_v3: "contradictions are surfaced, never silently
  resolved"). The two figures must **both stand**.

If a single supersession rule applied to all literals, it would *silently overwrite* the \$5M with the
\$7M — exactly the forbidden behavior. So D43 gates the belief axis with a flag, **`supersedable`**,
that is **mechanically derived** (a generated column — an application cannot set it wrong) from the
attribute's *time-semantics* (`claim_valid_kind`, already on the registry) and its cardinality:

| Attribute kind (`claim_valid_kind`) | Cardinality | `supersedable` | Behavior |
|---|---|---|---|
| `effective_period` (a state: balance, headcount, status, current title) | `single` | **true** | a later value **caps** the predecessor's window — supersession |
| `measurement_period` (a period figure: FY2023 revenue) | — | **false** | both-stand: same-period conflicts share a `contradiction_group`, surfaced, never resolved (the D42 behavior, preserved) |
| `effective_period` but genuinely multi-valued (e.g. several office locations at once) | `set` | **false** (coexist) | distinct values **coexist**; only exact duplicates are forbidden |
| entity object (any relation) | — | **true** | the normal relation supersession (D3/D4) |

`supersedable = (object_kind='entity') OR (valid_kind='effective_period' AND cardinality='single')` —
a **generated, stored** column, so the gate cannot be forged. Its *inputs* (`valid_kind`, `cardinality`)
are themselves **locked from the `governed_relationships` registry by a `BEFORE` trigger** on every
write, so neither the flag nor what feeds it can be set wrong by a writer — a fact's time-semantics come
from its *registered relationship*, not the caller. (The flag is also NULL-safe — a literal with a
missing `valid_kind` falls to the safe non-supersedable side rather than escaping the constraints.) For
non-supersedable literals the **no-belief-axis** (no `invalidated_at`, no system-set window close) is
preserved and *mechanically enforced* by `CHECK (supersedable OR invalidated_at IS NULL)`; the companion
"never re-cap an already-asserted period" half is enforced by the **same trigger** (it rejects any change
to `valid_from`/`valid_until` on a non-supersedable row) rather than left to linter discipline. This is
D42's guard, **relocated** into the unified table and made DB-enforced for the both-stand subset.

**Cardinality gates the entity side too.** Just as `cardinality` splits literals into supersede
(`single`) vs coexist (`set`), it splits entity relations into **functional** (`single`, e.g.
`has_ceo` — a new object supersedes the old: one CEO at a time) and **multi-valued** (`set`, e.g.
`member_of` — several objects coexist). Entities stay `supersedable` either way (an edge can always be
invalidated); cardinality instead selects which entity exclusion arm applies (§7). The permissive
default is `set` (most relations are multi-valued), so a *functional* predicate **opts in** to `single`;
a forgotten declaration conservatively coexists (the adjudicator still supersedes, exactly as before
D43) rather than over-rejecting legitimate concurrent relations. The mirror holds for literals: a
stateful attribute that forgets `single` falls back to both-stand, never a silent overwrite.

> **Why the gate reuses `claim_valid_kind` rather than a new enum:** the distinction the gate needs —
> "is this a *state that holds until changed* or a *figure about a fixed period*?" — is exactly what
> `claim_valid_kind` (`effective_period` / `measurement_period` / `event_time`) already encodes (D41).
> A new `attribute_value_semantics` enum would be a 1:1 relabel, so it was rejected.

## 4. The gate in action (two worked examples)

**Supersedable — headcount (a state).** `headcount` is declared `effective_period`, `single`.

| Step | What happens |
|---|---|
| Doc B → claim "headcount 500 as of 2023-12-31" | E3 blocks on `(Acme, headcount)`, finds none, inserts fact **F1**: value `500`, `valid_from=2023-12-31`, `valid_until=NULL` (open). |
| Doc C → claim "≈600" (asserted 2025) | E3 finds F1; the value changed; **caps F1** (`valid_until` = the new value's `valid_from`, ~2025) — F1 stays *true for its window* (`invalidated_at` stays NULL); inserts **F2**: value `600`, open. A `fact_adjudications` row records `outcome=supersede`. |
| Query *"headcount as of mid-2024?"* | `valid_from <= t < valid_until AND invalidated_at IS NULL` → **F1 = 500**. One indexed query, zero LLM. |

**Both-stand — FY2023 revenue (a period figure).** `fiscal_revenue` is `measurement_period` ⇒
`supersedable=false`. Doc X "\$5M" and Doc Y "\$7M" each become a literal fact with the *asserted
period* `valid_from=2023-01-01, valid_until=2024-01-01` (the `CHECK` allows this — it only bars
`invalidated_at`). They share a `contradiction_group`; **both stand**; the recipe linter bars a
single-value answer. Exactly D42's behavior — now as no-belief-axis rows of `facts`.

This is why the gate is load-bearing: the **same `facts` table** delivers true supersession for the
state *and* refuses to resolve the disagreement — because `supersedable` routes them to different
constraints.

## 5. Bi-temporal supersession by interval-capping (the two clocks)

A *state* supersession never deletes or rewrites anything. It **caps**: set the predecessor's
`valid_until` to the successor's `valid_from`. The predecessor remains a believed historical fact
(`invalidated_at` stays NULL — *we still believe it was 500 back then*). Only when we learn a fact was
**wrong** (not merely *ended*) do we set `invalidated_at` (transaction-time) — that is the second
clock. So:

- *"What was the headcount in mid-2024?"* → **valid-time**: `valid_from <= t < valid_until`.
- *"What did we believe the headcount was, as of last March?"* → **transaction-time**:
  `ingested_at <= t < COALESCE(invalidated_at, ∞)`.

Both questions stay answerable for entity and literal facts alike. (A **restatement** — a later source
correcting a *closed* period, "\$5M"→"\$5.2M" for FY2023 — is *not* supersession; it is a same-period
disagreement tagged `restatement`, surfaced with an `asserted_at` ordering hint, both values kept.
D41's split of `asserted_at` from the world-time window is what lets us tell restatement from a state
change.)

## 6. The governed relationship vocabulary

Predicates (for entity facts) and attributes (for literal facts) merge into **one
`governed_relationships` registry**, discriminated by `range_kind ∈ {entity, literal}`:

- **entity-range** rows are predicates (`works_for`, `member_of`, …) and keep their **domain/range
  signatures** (the D18 `edge_type_map` — `works_for: Person → Organization`).
- **literal-range** rows are attributes (`headcount`, `fiscal_revenue`, `founded_date`, …) and carry a
  typed **`value_domain`** (`money | date | quantity | count | ratio | string_enum | boolean`) that
  drives deterministic value normalization (so `$5M` and `5,000,000 USD` are one value), the
  identity-bearing **qualifiers** (IFRS vs GAAP, global vs US — different qualifiers are a *different
  slot*, not a conflict), the **`default_valid_kind`** (the gate input), and the **`cardinality`**
  (`single`/`set`).

Both ranges use the same D5 governance: constrained extraction, an `other:<freetext>` escape, a
periodic promotion job, and a `usage_count`. `predicates` and `attributes` survive as **compatibility
views** during migration. The extraction LLM emits a *registered* relationship key (never free text),
so blocking never silently fragments (the D5 lesson).

## 7. Schema (essentials; full DDL in `postgres_schema_design.md` §9)

- **`facts`** — the verdict table. Polymorphic object (`object_kind` + `object_entity_id` **XOR**
  `object_value`/`object_value_identity`, enforced by one *exclusive-arc* CHECK); the bi-temporal
  window; `evidence_count`; `contradiction_group`; a generated `status`; the generated `supersedable`
  (NULL-safe); `valid_kind`/`cardinality` denormalized and **trigger-locked from the registry**;
  `fact_label` + a Lance embedding ref (D8, now for literals too); the cascade-blocking indexes. **Four**
  partial GiST **exclusion constraints**, split by `cardinality`, enforce "at most one believed fact per
  slot over overlapping world-time": the **entity-functional arm** (`single`; object *excluded* from the
  key → a new object supersedes), the **entity-set arm** (`set`; object *included* → distinct objects
  coexist), the **literal single-valued supersedable arm** (value *excluded* → a new value supersedes),
  and the **literal-set arm** (`effective_period`+`set`; value *included* → concurrent values coexist).
  A `measurement_period`/`event_time` literal is deliberately in *no* range-overlap arm — range overlap
  is the wrong operator for a period figure (FY2023 vs Q1-2023 overlap but differ) — so different values
  for the same period both-stand; an **always-on exact-duplicate `UNIQUE`** (applying even after rows are
  grouped) is their dup-guard and the floor for every kind. Intervals are strictly positive so an
  instantaneous fact cannot slip past as an empty range. A `BEFORE` trigger (`trg_facts_lock_gate`) locks
  the gate inputs, freezes the identity columns post-insert, and bars re-capping a non-supersedable
  window; a sibling guard freezes a relationship's gate fields once facts reference it (semantics changes
  are rebuild migrations, not in-place edits).
- **`fact_evidence`** — the many-to-many join to claims (`HASH(fact_id)`, evidence-once); this is where
  corpus redundancy collapses (200 documents asserting one fact = one fact + 200 evidence rows +
  `evidence_count`, D2). `relation_evidence`/`attribute_evidence` merge into it.
- **`fact_adjudications`** — the append-only "why" transcript (window closed, contradiction flagged,
  merge proposed), generalizing `relation_adjudications` to `fact_id`.
- **`governed_relationships`** — §6.
- **`relations` view** — `SELECT … FROM facts WHERE object_kind='entity'`, preserving every existing
  reader (graph build, blocking, recipes). Hard read-only (`INSTEAD OF` trigger + `REVOKE`), as are the
  `predicates`/`attributes` compatibility views — every write goes to the one base table.

## 8. The graph projection (P2 / LadybugDB) — and why the structure now projects *cleanly*

This is the part that looked hard and turns out to be easy. Verified LadybugDB facts (see
`plan/analysis/fact_layer_architecture_research/ladybug_projection_findings.md`; design:
`p2_graph_design.md`):

- **A LadybugDB relationship requires node endpoints** (`FROM NodeTable TO NodeTable`) — a literal can
  *never* be an edge. So the graph receives **only** `facts WHERE object_kind='entity'`. That is the
  structural guarantee for D18: literal facts are simply *not selected* into the projection.
- **`ATTACH 'postgres' … COPY Relates FROM SQL_QUERY('pg', …)`** bulk-loads the graph **directly from
  Postgres, with no Parquet hop**. The projection is a read-only `SQL_QUERY` that does three things in
  one place: filters `object_kind='entity'`, casts `entity_id::text` (UUID is not a node-PK type), and
  casts the four bi-temporal columns `AT TIME ZONE 'UTC'` (LadybugDB's attach does **not** support
  `timestamptz` — this cast is mandatory and is generated from the registry, never hand-maintained).
  Literal facts never cross this boundary, so they stay in Postgres + Lance where `timestamptz` is
  native. A Parquet/Arrow export is retained for the D11 community-detection pass and as a fallback.
- **As-of traversal** uses `PROJECT_GRAPH_CYPHER` rel-predicates over the (now UTC-`timestamp`)
  columns (D10); the `$as_of` parameter is supplied UTC-naïve to match.
- Entity merges re-point pre-projection on rebuild (D7/D21), so the projection needs **no** runtime
  merged-entity filter.

So D43 makes the projection a single filtered + cast `COPY` — *simpler* than before, and it directly
answers the worry that the typed-graph model would make projection hard: the Postgres view absorbs the
type-mismatch and the entity filter, and the LadybugDB side is trivial.

## 9. Promotion, K-plane, and search

- **Promotion (literal → entity).** When a literal value later resolves to a real entity (a string
  *"Acme Corp"* that becomes a canonical org; a *"a former Google exec"* CEO that resolves to a
  person), the fact is promoted via the D5 `other:` funnel to an entity fact in the **same table** — a
  single-table, audited hand-off (freeze the literal fact's window, point to the entity fact), with no
  cross-table dual-write. A pure scalar (a balance) never promotes; it lives as a supersedable literal
  fact forever, which is now fine because it *has* a believed value.
- **K-plane.** K3 still narrates with citations ("headcount reported 500 (2023 filing) then ≈600 (2025
  report)") and links supporting/contradicting evidence; it is the *consumer*, never the structured
  verdict home. A new/changed `contradiction_group` triggers a K refresh (D12).
- **Search (P1 / Lance, D8).** Every fact's `fact_label` is embedded in Lance keyed by `fact_id`, now
  including literal facts (a believed value series is searchable). Graph-workflow fact search filters
  `object_kind='entity'`. No vectors enter the graph (D8 unchanged).

## 10. Consequences, residuals, and what must be measured

**Invariants:** D2 (claims vs facts) preserved with "relations" reframed as the entity view; D3
generalized to fact-level supersession, claims still immutable; D6 *strengthened* (one belief home);
D18 held on the graph, amended to permit literals as Postgres *objects*; D8/D41 amended in reasoning.

**Residual risks — gate these before any implementation ships:**
1. **Supersedable-vs-both-stand classification is verdict-critical** (no longer just surfacing
   quality). Mis-marking a `measurement_period` attribute as `effective_period` would let the system
   **silently supersede** figures that must both-stand — the exact requirements_v3 violation.
   `claim_valid_kind` is governed (**start strict; default to `measurement_period`**), golden-gated on
   `eval_suite='contradiction'`, and an `effective_period`/supersedable declaration is reviewed like a
   predicate promotion. **The single biggest correctness risk.**
2. **Value normalization is now on the verdict path.** A fiscal-calendar (FY≠CY) or unit
   (`$5M` vs `$5MM`) error now writes a *wrong believed window* (a false verdict the API returns as
   truth) — strictly worse than D42's wrong *grouping*. Fail-safe: **normalize-or-refuse** —
   non-normalizable/precision-ambiguous values go to `contradiction_group`/unbelieved, never to a
   confident `valid_from`.
3. **Scale (10⁸).** The supersedable-literal subset on the literal EXCLUDE is bounded by ambiguity
   (D4 blocking), much smaller than all literals (the both-stand bulk stays off it). Still: load-test
   the unified-table conflict-row sizing and the supersession write path; verify the planner uses the
   partial `WHERE object_kind='entity'` indexes through the `relations` view; load-test ATTACH
   bulk-COPY throughput at 10⁸ before deleting the Parquet build path (the attach scanner is in the
   un-vendored extensions repo — treat throughput as unverified). See `postgres_schema_design.md` §17.
4. **Cardinality** must ship with the literal arm (without it, a multi-valued `effective_period`
   attribute wrongly supersedes coexisting values), golden-tested.
5. **Decision-log blast radius** is large (D2/D3/D4/D5/D6/D7/D8/D18/D41/D42 amended). Each change is a
   *simplification*, but the whole verdict is **conditional on the affirmed must-have being firm** — if
   temporal supersession of non-relational facts were withdrawn, D42 status quo would again be the
   better answer.

## 11. Decisions & spikes

**Decision:** **D43** (this layer), superseding/repurposing **D42**. Foundations: D2, D3, D4, D5, D6,
D7, D8, D18, D41. **Spikes (measure before locking — numbers are starting points):** (1) the
supersedable-vs-both-stand classification golden gate; (2) value-normalization incl. fiscal-calendar
correctness on the *verdict* path; (3) unified-table conflict-row sizing + supersession write-path +
ATTACH bulk-COPY load tests at 10⁸; (4) cardinality (`single`/`set`) golden coverage.

## References

Research: `plan/analysis/fact_layer_architecture_research/` (`SYNTHESIS.md`, `external_agents/codex.md`,
`external_agents/agy.md`, `internal_analysis.md`, `ladybug_projection_findings.md`). Decisions:
`decisions.md` (D43 + D2, D3, D4, D5, D6, D7, D8, D18, D41, D42). Schema: `postgres_schema_design.md`
(§9 `facts`/`governed_relationships`/`fact_evidence`/`fact_adjudications`, §17 spikes). Adjacent designs:
`p2_graph_design.md` (the ATTACH-direct projection), `e2_e3_claims_relations_design.md` (E3 writes
facts), `registries_design.md` (`governed_relationships`), `nonrelational_facts_design.md` (D42,
subsumed). Explainer: `concepts.md`. Requirement: `requirements_v3.md`. LadybugDB: `ladybug_capabilities.md`.
