# Internal multi-agent analysis — fact-layer architecture & LadybugDB projection

Output of an internal 5-angle workflow (unified-facts / separate-tables / projection-first /
radical-rethink / invariant-scale-adversarial), each proposal adversarially critiqued, then
synthesized. Companions: `external_agents/codex.md`, `external_agents/agy.md` (independent external
analyses), `ladybug_projection_findings.md` (verified LadybugDB facts). Consolidated in
`SYNTHESIS.md`. This is *analysis* — it recommends a candidate **D43**, logs nothing binding.

## Recommendation: scoped-U (one unified `facts` verdict layer, gated by `supersedable`)

One unified `facts` verdict table over immutable claims, with a polymorphic object
(`object_kind ∈ {entity, literal}`), **one** bi-temporal apparatus, **one** supersession/contradiction
engine (the D4 cascade generalized from `relation_id` to `fact_id`), **one** evidence join, **one**
adjudication transcript. `relations` becomes the `object_kind='entity'` **view** — the only slice the
graph can physically project (a literal can never be a LadybugDB REL edge). This is candidate **D43**.

**The decisive refinement all four critiques converged on — the `supersedable` gate.** A naïve single
`facts` table with one value-keyed EXCLUDE silently collapses two cases requirements_v3/D42 keep apart:
- (a) the **affirmed must-have** — a single-valued, open-ended (`valid_from`-only) literal that genuinely
  **supersedes** when the value changes (a balance / headcount / run-rate); and
- (b) the **D42 both-stand residue** — two sources giving different figures for the **same closed
  period** ($5M vs $7M FY2023), which must **never** acquire a silent winner.

So the belief axis (a closable `valid_until`, a transaction-time `invalidated_at`, the literal
supersession EXCLUDE) fires for a literal fact **only when it is supersedable**, and "supersedable" is
derived from the attribute's **existing `claim_valid_kind`** (`effective_period` ⇒ supersedable state;
`measurement_period` ⇒ both-stand; `event_time` ⇒ the date is the value). The non-supersedable subset
keeps D42's no-belief-axis, now enforced by a **CHECK** (`supersedable OR (valid_until IS NULL AND
invalidated_at IS NULL)`) + the CI schema-test + the recipe linter — D42 is **subsumed, not deleted**.
A new `attribute_value_semantics` enum was **rejected** as a 1:1 relabel of `claim_valid_kind`.

## Why U over S over D42 (the engine, not the table count)

- **D42 status quo — insufficient by construction.** Its sole D6 safety pillar is the
  mechanically-enforced *no-belief-axis*. The affirmed requirement *is* a belief axis (a closable
  world-time window). You cannot add it to `claim_attribute_facts` without detonating the invariant
  that table exists to protect. So D42 can't host the must-have (it survives, repurposed, for the
  both-stand residue).
- **S (separate `proposition_facts`) — rejected (its own critique scored `d6_ok=false`).** Its
  disjointness guarantee fires *only* along the promotion edge, and the promotable subset is exactly
  the subset the must-have does **not** center on — the pure-literal series. The same real-world fact
  can live as a `proposition_fact` **and** (after a sibling promotion) as a `relation`, with no shared
  identity key → two live beliefs drift = the Mem0 desync class D6 forbids, re-imported inside Postgres.
  Plus two GiST EXCLUDEs / two contradiction protocols / two transcripts kept identical by a fragile
  schema-test — duplication the requirement never demanded.
- **U (one engine) — wins.** Same proven machinery delivers the must-have; validity in **one** home
  for both fact kinds (D6 *strengthened*); claims immutable (D3 intact); projects to the graph as a
  trivial filtered+cast COPY (literals never selected — D18's graph rule held structurally). The
  entity/literal distinction D2/D18 care about survives as a discriminator column + CHECK + a
  projection filter, not as a table boundary.

## Projection (Q2) — the graph is neutral; U projects cleanly

Per `ladybug_projection_findings`: every option projects the entity subset and drops literals, so the
graph does not decide U vs S. U projects strictly cleanly:
- **Entity-subset filter** (`WHERE object_kind='entity'` inside the read-only `SQL_QUERY`) — literals
  are never selected; D18's no-Date/Money-node graph rule is structural.
- **`timestamptz` cast** — the four bi-temporal columns cast `AT TIME ZONE 'UTC'` Postgres-side in the
  `SQL_QUERY`; **U adds zero new cast surface** (only the entity arm crosses; the literal arm stays in
  Postgres/Lance where `timestamptz` is native).
- **UUID→STRING** PK (`entity_id::text`); `fact_id::text` rides as an edge property.
- **ATTACH-direct** `COPY Entity/RELATES FROM SQL_QUERY('pg', …)` replaces the Parquet hop; keep a
  Parquet/Arrow `COPY TO` only for the D11 community pass (no Louvain in LadybugDB) **and as a verified
  fallback** until ATTACH bulk-COPY is load-tested at 10⁸ (the attach scanner is in the un-vendored
  extensions repo).
- **No runtime `status<>'merged'` join** — canonical-only is a pre-projection invariant (entity merges
  re-point on rebuild, D21/p2 §2); the COPY needs no entity-status filter (a grafted fix rejecting the
  unified proposal's runtime join).
- **As-of** via `PROJECT_GRAPH_CYPHER` over the cast columns (D10); the literal supersedable as-of is a
  Lance scalar window scan (native `timestamptz`).

## Q3 — is there a fundamentally better architecture? No (alternatives weighed and rejected)

- **Event-sourced (fold belief on read)** — rejected: the D4 cascade is partly-LLM/partly-human
  adjudication whose verdict must be durable + cheap to read at 10⁸; re-folding over a 5×10⁷ log
  re-introduces the corpus-scale aggregation D23/D25 forbid. Its correct residue ("log=claims, durable
  adjudicated belief=facts") **is U**.
- **Reify literal facts as graph nodes** — rejected: node-only vector/FTS + no native temporal
  semantics buy no graph-native time-travel; ~doubles the graph; 20–90 GB embeddings/snapshot kills
  rebuild-and-ship (D8); Date/Money-node disease D18 forbids.
- **Force promotion to synthetic measurement entities** — rejected: literal-in-entity-costume; graph
  explosion; turns "headcount over time" into a traversal instead of a Lance window scan.
- **Drop LadybugDB / Postgres-only graph (recursive CTE / Apache AGE)** — rejected: traversal latency +
  write/read resource contention; gives up the reason P2 exists (isolated, snapshot-served traversal).
- **Optional in-graph refinement (documented, gated on demand):** a supersedable literal *may* project
  its currently-believed scalar as a **node property** on the subject Entity (single-valued,
  node-indexable, full history staying Postgres+Lance) — kept as an option, not core.

## Residual risks (carried into SYNTHESIS)

1. **Supersedable-vs-both-stand classification is now verdict-critical** (was surfacing-quality):
   mis-marking a `measurement_period` attribute as `effective_period` lets the system *silently
   supersede* figures that must both-stand (the exact requirements_v3 violation). `claim_valid_kind`
   is governed (start strict; default to the conservative `measurement_period`), golden-gated on
   `eval_suite='contradiction'` — **the single biggest correctness risk; gate before the literal arm ships.**
2. **Fiscal-calendar / value-normalization is now on the verdict path** — a FY≠CY or $5M-vs-$5MM error
   now writes a *wrong believed window* (a false verdict returned as truth), worse than D42's wrong
   grouping. Fail-safe: normalize-or-refuse → ambiguous values go to `contradiction_group`/unbelieved,
   never a confident `valid_from`.
3. **Scale unproven** — extend the §17 conflict-row sizing spike to the unified-table population;
   verify the planner uses the partial `WHERE object_kind='entity'` indexes through the `relations`
   view; load-test ATTACH bulk-COPY at 10⁸ before deleting the Parquet build path.
4. **Cardinality** — legitimately multi-valued literals (several office locations) need a registry
   `cardinality ∈ {single, set}` flag: `single` ⇒ value excluded from the literal EXCLUDE (supersede);
   `set` ⇒ value included (coexist). Must ship with the literal arm, golden-tested.
5. **Decision-log blast radius is large** (D2/D3/D6/D7/D18/D41/D42 amended + D43). Each change is a
   *simplification* (one engine, fewer tables), but the verdict is **conditional on the affirmed
   must-have being firm** — if temporal supersession of non-relational facts were withdrawn, D42 status
   quo would again be the better answer.

## Appendix — the five angles and their adversarial verdicts

| Angle | Q1 pick | Critique verdict | The objection that shaped the synthesis |
|---|---|---|---|
| unified-facts | U | sound_with_fixes (d6✓, projects✓) | A single value-keyed EXCLUDE collapses supersedable vs both-stand → needs the `supersedable` gate. |
| separate-tables | S | sound_with_fixes (**d6✗**, projects✓) | Disjointness only holds on the promotion edge; the pure-literal series (the must-have's core) drifts → two belief homes. **Rejected.** |
| projection-first | U | sound_with_fixes (d6✓, projects✓) | Schema didn't structurally separate the two literal cases → same `supersedable` fix; confirmed ATTACH-direct + UTC cast. |
| radical-rethink | U | sound_with_fixes (d6✗→fixable, projects✓) | "The real axis is *believed-supersedable* vs *raw testimony*, not relational vs non-relational" — but must keep the no-belief-axis guard for the both-stand residue. |
| invariant/scale-adversarial | D42 | **over_built** (d6✓) | Argued least-change, but its own critique showed it *redefines* the must-have down to a recency hint (`current_belief=false`) → does not deliver it. **Rejected as terminal answer.** |

Net: 4/5 angles land on U; the dissent (least-change) provably fails to deliver the affirmed must-have.
The unanimous fix is the `supersedable` gate (reusing `claim_valid_kind`) so U subsumes D42 rather than
violating it.
