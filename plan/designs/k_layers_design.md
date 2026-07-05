# K Plane — Compiled and Authored Knowledge (Design)

How the system turns the evidence spine into the high-level, browsable knowledge layer agents
read *first* — per-purpose curated summaries, entity profiles, and authored documents — while
keeping every page mechanically traceable to the evidence it rests on. Binding design for
decisions **D45–D47** (which also accept objections **O2** and **O4**); builds on D1 (split
source of truth), D11 (communities), D12 (debounced aggregate triggers), D24 (blast-radius
review), D33 (decision ledgers for non-deterministic stages), D42 (document origin), D43
(observations). This one document covers the whole plane — the previously separate
`k3_beliefs_design.md` is folded in (one mechanism, D47). Schema:
`postgres_schema_design.md` §11. Numbers here are starting points to measure, not committed
constants (CLAUDE.md).

> **Reading this cold (CLAUDE.md Rule 1).** Plane E (evidence) stores what sources said as
> **claims** (immutable natural-language assertions), normalized into **relations**
> (entity→entity facts) and **observations** (single-entity value facts), all anchored on
> canonical **entities** with bi-temporal validity windows. Plane K (this doc) is the layer
> above: **markdown pages in a git repo**, written for reading — an agent looks here first and
> drills into evidence only when needed. Two words carry precise meanings throughout:
> **compiled** = a page written by an LLM *from* the evidence and regenerated when that
> evidence changes; **authored** = a page written by a human or agent as first-class content
> (a plan, a target design, a decision log) — never regenerated, but *alerted* when evidence
> it relied on changes. A page's **citations** are the recorded evidence IDs it rests on; a
> page's **routing rule** is the stored, mechanically-evaluable definition of what evidence
> belongs to it. Together they are the page's *manifest* — the thing that makes staleness,
> deletion, and audit computable instead of guessed.

## 1. The core idea: intelligence chooses; machinery routes

The design splits plane K's work along one line: **an LLM decides what pages exist and what
each page is *about*; SQL decides which pages a new piece of evidence affects.** This works
because of something plane E already guarantees — by the time evidence lands, it has been
through entity resolution, relation normalization, and community assignment (D11), so every
new claim/relation/observation arrives *pre-labeled* with the keys rules match on (canonical
entity IDs, governed predicates, community IDs, document metadata). The expensive semantic
understanding happened upstream, once; K routing reuses it for free.

The alternative — free agent sessions browsing the repo each cycle to *discover* what to
update — leaves the two load-bearing steps (routing new evidence to pages; deciding which
pages exist) as unrecorded, per-cycle LLM improvisation, and then needs merge-conflict retry
and hot-file serialization machinery to survive concurrent sessions. It also makes the
system's core promises undecidable: "is this page stale?", "which pages must recompile when
this document is deleted?", and "is this page's coverage complete?" have no computable answer
when the compile's read set was never recorded. D45 rejects that mechanism. (This is not a new
discipline — it is D33's discipline, already applied to every other non-deterministic stage:
extraction has its decision ledger, adjudication its transcript, resolution its append-only
decisions. Plane K was the last LLM stage whose decisions evaporated when the session ended.)

What is **not** deterministic — deliberately — is the content. Writers have full creative
latitude (and may be full agent sessions with retrieval tools, §7). Determinism lives only in
*triggering* (what is stale), *routing* (which page gets what evidence), and *bookkeeping*
(what fed what).

## 2. One mechanism, many scopes (D47 — accepts O2)

Plane K runs **one compilation mechanism**. The K1/K2/K3 names survive as *content tiers*, not
separate machinery:

| Tier | What it is under this design |
|---|---|
| **K1 — general knowledge** | the **default scope**: entity pages, topic (community) pages, source digests, the root index |
| **K2 — purpose scopes** | additional scopes (people profiles, business planning, as-is/to-be migration tracking, …) — each a git subtree + registry rows (`scopes`, `scope_interests`, D16), sharing the one entity space |
| **K3 — core beliefs** | a distinguished **belief tier** (§8): compiled pages under stricter rules — evidence-gated updates, mandatory supporting *and* contradicting citations |

A scope is: a subtree of the repo, its registry rows, its pages (compiled and authored), and
one **shared model page** (§7) that anchors its vocabulary. "Scopes multiply, truth doesn't"
(D16) holds: scopes own compiled markdown and authored documents, never facts.

## 3. Three roles and one ownership rule (D45)

| Role | What it is | What it owns | What it may never do |
|---|---|---|---|
| **Planner** (LLM) | maintains the *structure*: which pages exist, the tree, each page's routing rules | page existence, splits/merges/moves, rule changes — all as append-only `knowledge_plan_decisions` | write page content |
| **Writer** (LLM, per page — Codex/OpenCode) | compiles **one page per invocation** from its inputs (§6); may be agentic (§7) | the body of *compiled* pages | touch any other file; leave inputs uncited |
| **Driver** (deterministic worker) | computes staleness (SQL), schedules writers in dependency order, validates outputs, syncs Postgres, commits | the git *commit* — it is the repo's **only automated committer** | generate content; override curation |

**Authors** — humans or operating agents (in the named deployments, almost always agents) —
own the fourth surface: **authored pages and curation sidecars** (§4), committed through
normal git flow. The driver pulls before each cycle. Because the compile system's file set and
the authors' file set are disjoint by the ownership contract, merge conflicts between the
system and itself are structurally impossible, and conflicts among authors happen only in
their own files, under ordinary git rules. The prior design's in-session
conflict-retry and the hot-file rolling-window worker are **removed** (the root `index.md` is
simply the last target in the dependency order, compiled once per cycle — D12 refined).

## 4. Two page kinds and the ownership contract (D46)

Every K artifact is one of two kinds. Both carry citations; they differ in who writes the body
and what happens when cited evidence changes:

| | **Compiled page** | **Authored page** |
|---|---|---|
| body written by | its writer (LLM) | a human or an authoring agent |
| derived from evidence? | yes — regenerated from its rules' evidence | no — it *is* first-class content (a design, a decision, a target state) |
| when cited evidence changes | page goes **stale → recompiled** | page gets a **review flag** ("a decision here rests on changed evidence") — never auto-rewritten |
| human input via | the **curation sidecar** | direct editing (it's theirs) |
| examples | entity profile, topic summary, as-is system description, belief page | to-be architecture, mapping decisions, project plans, position papers |

**Curation sidecars.** Human judgment about a *compiled* page lives in a per-page, git-tracked
sidecar (`<page>.curation.md`): pins ("keep this framing"), exclusions ("never cite claim X"),
corrections ("this conclusion is disputed — present both sides"), free guidance. The sidecar
is a first-class compile input (it is hashed into `inputs_hash`, §5 — editing it triggers a
recompile), and the enforceable subset is enforced mechanically (excluded evidence IDs are
filtered from the writer's bundle and rejected from its citations).

**The quarantine rule.** Compiled bodies are machine-owned. If anyone — a human or an
out-of-band agent — edits one directly, the driver detects it (`content_hash` mismatch), does
**not** overwrite and does **not** silently absorb it: the diff is quarantined into a
*proposed sidecar entry* and the page is excluded from recompilation until the proposal is
accepted or rejected (or the page is adopted — see below). An author's work is never
destroyed; it is moved to where it survives regeneration.

**Authored pages still participate in the manifest system.** An authored page's frontmatter
declares its citations (`cites:` — the evidence IDs the author relied on) and optional
**watch rules** (`watch:` — routing rules whose consequence is a *flag*, not a recompile:
"tell me when anything new lands about module X"). The driver syncs frontmatter to Postgres.
This is what makes authored content safe at scale: decisions are automatically alerted when
the ground they stand on moves (§9).

### How a page gets its kind — and how it changes

The system never *classifies* a page's kind — kind is fixed by **which door the page entered
through**, and enforced by ownership:

- **Planner-created pages are compiled, always.** The planner creates a page *because* evidence
  needs a home (orphan facts, a splitting page, a new community) — so its content is by
  construction derivable from the spine, and it gets routing rules and a writer. The planner
  cannot create authored pages; there is nobody to write them.
- **Committed pages are authored, always.** An authored page comes into existence when a person
  (or an authoring agent) writes a file and commits it through normal git flow; on the next
  cycle's pull the driver finds a file that is not one of its own artifacts, registers it
  `authored`, and syncs its frontmatter.

The judgment that *does* exist belongs to the author choosing a door: **could every sentence on
this page cite evidence already in the spine?** If yes, don't write it — request it as a
compiled page and it stays current forever. If it contains **commitments the world has no
evidence for yet** — a target design, a decision, a stance, a plan — it cannot be compiled
(there is nothing to compile it *from*) and must be authored. Mixed needs resolve by
**composition, never hybrid pages**: human input into a compiled page goes through its sidecar;
an authored page wanting an evidence-derived section *links to* a compiled page rather than
inlining a copy that would rot.

Kind can change — always as a recorded plan decision (`convert_kind`), never silently:

- **Adoption (compiled → authored).** The natural path is the quarantine flow: an author edited
  a compiled body, and one triage outcome is "the author takes this page over" — flip to
  `authored`, stop recompiling, keep its routing rules as watch rules (staleness becomes review
  flags, §5).
- **Handover (authored → compiled).** The author judges the page fully evidence-backed: the
  planner attaches rules, a writer takes over, and the author's residual judgment moves into
  the sidecar. Because this discards an author's ownership of a body, it is the one plan
  action that **never auto-applies** regardless of blast radius — it stays `proposed` until
  the author (human or agent) confirms.

A complementary route exists for content, not just pages: finalized authored material can be
**ingested as a source** (D42 stamps it system-originated), so its statements enter plane E as
evidence — compiled pages then absorb it and the authored draft retires. §9 shows this
*promotion loop* end to end.

**Consequence for D1 (refined by D46).** The git repo remains plane K's source of truth, but
its *irreducible* core — what backups genuinely protect — narrows to **human-authored
content** (authored pages + sidecars). Compiled pages are *semantically regenerable*: re-running
a compile over the same recorded inputs yields a page that is not byte-identical (LLM
non-determinism) but says the same thing, traceable to the same evidence. That is exactly what
objection O4 asked for.

## 5. Routing rules, citations, and what "stale" means (D45)

### Routing rules — mechanical, chosen by the planner

A routing rule is a stored row (`knowledge_page_rules`): a **kind** plus parameters, where
each kind has one fixed, deterministic SQL evaluation over the spine. A page may hold several
rules (their union). The closed kind set:

| Kind | Parameters | Matches |
|---|---|---|
| `entity` | entity_id; optional predicate filter; which fact layers (relations / observations / claims-via-mentions) | everything about one entity |
| `entity_subtree` | root entity_id | the entity plus its `part_of` closure (e.g. a subsystem and its modules), then as `entity` per member |
| `predicate_beat` | predicate; optional subject/object | e.g. `works_for → acme`: who works at Acme |
| `community` | community_id (D11 writeback) | evidence on the community's member entities |
| `doc_set` | document metadata filter (source, mime, `origin` D42, time range) | evidence from a document family (e.g. board minutes) |
| `scope_interests` | scope_id | delegates to the registry's `scope_interests` rows (entity types, predicates, metadata, keywords) |
| `manual` | explicit entity/evidence ID list | the editorial escape hatch (§ below) |

**Why not description-based (semantic) rules.** A description rule ("this page covers Acme's
pricing strategy") needs an LLM or embedding comparison *per new evidence item, per page* —
a classification pass whose cost scales with volume × page count and whose answers are
non-reproducible. That is the pre-extraction value gate's mistake in new clothes (D25). The
division of labor instead: the planner (an LLM) *chooses* "there should be an Acme page keyed
on `entity: acme`"; SQL *evaluates* "these 12 new rows match `entity: acme`". Zero LLM calls
on the routing path — the same rule the query path already obeys (D9).

**Routing granularity vs. editorial granularity.** Mechanical keys route at the granularity
plane E produces: entity, predicate, community, document set. Finer subdivision ("Acme
pricing" vs "Acme hiring" as separate pages) is *editorial*, not routing: the rule delivers
everything-Acme to one page, whose writer organizes it into sections. The planner splits at
the routing level only where a mechanical key exists to split on (a predicate set, a doc-set,
a subtree member); where none exists, a split uses `manual` rules with explicit assignments
(typically adopted from the writer's own split suggestion). Intelligence decides the split;
the *record* of the split is mechanical.

**The inverted key index.** Every rule's match keys are materialized to `knowledge_rule_keys`
(`(key_kind, key_value) → rule`). Routing a batch of new evidence is then one indexed lookup —
the same block-first philosophy as supersession (D4): exact keys narrow, expensive work runs
only on the narrowed set. `entity_subtree` and `community` rules have *derived* membership, so
the driver re-materializes their keys when their inputs change (a `part_of` relation touching
the subtree; a community-detection writeback) — both are ordinary evidence events the driver
already sees.

**Orphan evidence — the planner's inbox.** Evidence matching *no* rule in a scope is counted
per entity ("Bob has 14 unhoused facts"). Aggregated orphans, page-size overflows, community
changes, writer suggestions, and reflection findings (§7) are the planner's triggers; its
outputs are append-only `knowledge_plan_decisions` (create/split/merge/move/retire/adjust-rule)
with a rationale. Low-blast-radius decisions auto-apply; restructures above a threshold queue
for review by an **accountable reviewer outside the proposing context** — a human or a
designated reviewer agent (§7) — the D24 pattern applied to structure.

### Citations — the binding output contract

Every compile ends with the writer returning, besides the markdown: its **citations** (the
evidence IDs the page rests on, with roles `supports | contradicts | cites`), a short
**page summary** (2–3 sentences, stored in Postgres — parents consume child summaries without
re-reading files), and optional **suggestions** (planner inputs, never direct action). The
driver validates citations (IDs must exist; excluded IDs must be absent), replaces the page's
`knowledge_artifact_evidence` rows, and records the compile in `knowledge_compilations`
(inputs hash, candidate/cited/uncited counts, versions, commit). Rule-matched evidence the
writer chose *not* to cite is thereby counted — the K-plane analogue of D33's Selection-drop
ledger ("why isn't fact X on this page?" has an answer).

### Staleness — mechanical, three causes

A page was compiled from a snapshot of its rules' answer. It is **stale** when that snapshot
no longer matches reality:

1. **New evidence matches a rule** but was never in the page's candidate set.
2. **Cited (or candidate) evidence changed state** — a relation's validity window was capped
   or invalidated, an observation superseded, a contradiction opened.
3. **Cited evidence was deleted** (source document removed — §10).

Formally, the driver computes per page an
`inputs_hash = hash(sorted candidate evidence IDs + each ID's validity fingerprint
+ curation sidecar hash + sorted child page-summary hashes + shared-model-page summary hash
+ writer prompt/model version + rule configuration)`, and the page is stale **iff** it differs
from the hash recorded at last compile. This is D12's idempotency discipline (content hash +
version) applied to K: re-running a cycle is a no-op; a prompt-version bump recompiles exactly
everything; "is anything stale?" is one deterministic computation. Stale ≠ wrong — it means
"compiled from inputs that are no longer current"; what the new text *says* is entirely the
writer's judgment. Stale also ≠ instant recompile: plane K stays debounced (D12) — stale pages
accumulate and compile on the window. For **authored** pages, causes 1–3 produce the review
flag instead (D46).

Every compiled page carries a machine-written provenance footer (compiled-at, evidence as-of,
citation count) — the per-page freshness metadata that mixed-freshness reasoning
(`questions.md` #23) needs.

### What compilation consumes — the adjudicated layers are the skeleton, claims are hydrated selectively

Compiling from raw claims would re-pay, at every compile, exactly the work E3 already did —
redundancy collapse (200 claims asserting one employment → one relation), validity adjudication,
contradiction grouping — and claims cannot answer "is this still true" (current belief is
relation/observation semantics; requirements bar claims from it). So a compiled page's primary
inputs are the **adjudicated layers**: **relations** — the distinct facts, whose windows give
current-vs-ended, whose `evidence_count` gives salience ordering, and whose
`contradiction_group` marks what to surface as tension — and **observations** — the value facts
and their capped history, which is precisely the timeline material ("headcount 500 → 600 over
2024"). Claims enter in exactly two roles:

1. **The residue** — kept claims that normalized into *neither* layer: attributed statements
   ("Alice said the migration would slip"), n-ary and qualified assertions. Without
   claims-via-mentions in the rule, a person page would silently miss half its value.
2. **Color for the leading facts** — the fact label says `works_for(alice, acme)`; its best
   evidence claim says *"hired as VP of Engineering to rebuild the platform team."* The writer
   hydrates a claim or two for the facts that lead the page.

This is also the hub-entity budget rule (§11, residual 3) made concrete: relations +
observations are **bounded** (distinct facts, not corpus-proportional) and always included in
full; claims are the unbounded layer and are **capped** — the residue plus top-K evidence per
leading fact, evidence-count-ranked, with the cut recorded in the compile transcript (no silent
caps).

### The two-band page — deterministic fact sheet + LLM prose

Part of an entity page needs no LLM at all: a table of current relations and an observation
timeline is a *deterministic render* — and asking a writer to re-type facts into prose is
exactly where hallucination risk lives and tokens burn. A compiled page therefore has **two
bands**:

```markdown
# Acme
_LLM band — the synthesis a machine can't do: what Acme is, what changed
lately, what is contested, what is load-bearing. Sections group and
narrativize (People; Financials — surfacing the FY2023 $5M-vs-$7M conflict
side by side; Trajectory — over the observation timeline), each statement
citing the facts it interprets._

---
## Fact sheet (generated)
| fact                                 | valid since | evidence |
| Alice Novak works for Acme (VP Eng)  | 2024-03     | 12 docs  |
| …                                    |             |          |
_deterministic driver render: current relations, observation history, open
contradiction groups — exact at compile time, zero LLM._
_compiled 2026-07-05 · evidence as of 2026-07-05T06:00Z_
```

- The **fact-sheet band** is rendered by the *driver* from the same candidate set the writer
  received: deterministic, always literally correct, zero hallucination surface, zero token
  cost.
- The **LLM band** is where the writer earns its place — salience, trends, tensions, narrative.
  Its citations shrink to what the prose actually *interprets*, which sharpens the faithfulness
  audit (§7).
- **Degradation mode:** the planner may designate a page **fact-sheet-only**
  (`kind='fact_sheet'`) — zero writer cost for low-importance entities, upgraded to full prose
  when evidence volume or demonstrated demand justifies it (an ordinary plan decision).

## 6. The compile cycle

Triggered by the D12 debounce window ("N changed evidence items or T minutes"). One cycle:

1. **Pull** the repo (pick up human commits: authored pages, sidecars). Sync authored
   frontmatter (`cites:`/`watch:`) to Postgres; quarantine any direct edits to compiled bodies.
2. **Route**: consume queued evidence events → `knowledge_rule_keys` lookups →
   re-materialize derived rule keys where needed → stale set (compiled) + review flags
   (authored) + orphan aggregates.
3. **Plan** (only when structural triggers fire): planner emits `knowledge_plan_decisions`;
   auto-apply the low-blast-radius band, queue the rest for review.
4. **Compile** stale pages in dependency order — the scope's shared model page first if stale,
   then children before parents (parents consume child summaries), the root index last, once.
   Writers run in parallel across disjoint pages (Cloud Run jobs, D12 retry/DLQ semantics); per
   page, the driver renders the deterministic fact-sheet band and the writer produces the LLM
   band (§5) — fact-sheet-only pages skip the writer entirely.
5. **Validate & commit**: citations resolve, exclusions honored, internal links resolve to
   existing artifacts; one commit for the cycle; two-phase against Postgres (record compilations
   `pending` → push → mark committed; reconcile HEAD on startup).

A failed writer job leaves its page at the previous version — stale but consistent, retried
next cycle, dead-lettered after the D12 retry budget. There is no partial-page state.

**Walkthrough.** A memo lands: *"Bob joined Acme as CFO; Alice departed."* Plane E (unchanged)
extracts claims, resolves Bob/Alice/Acme, inserts `(bob, works_for, acme)`, and supersession
caps `(alice, works_for, acme)`. Routing, all SQL: the new relation carries keys `bob` and
`acme` → the Acme page's `entity` rule matches (**stale, cause 1**); the capped Alice relation
is cited by both the Acme page and Alice's profile (**both stale, cause 2**); Bob matches no
rule → orphan count (enough Bob facts and the planner proposes a Bob page). Next window:
three writers recompile three pages from current evidence; the team page keyed
`works_for → acme` also caught cause 1; the topic index and root recompile last because child
summaries changed.

## 7. Quality at scale — coherence, completeness, and where the intelligence lives

Per-page compilation raises a fair objection: locally fine pages, globally incoherent scope
(inconsistent terminology, duplicated coverage, missed cross-cutting insight). Four mechanisms
answer it:

- **The shared model page.** Each scope maintains one page (compiled or authored) holding its
  conceptual model: vocabulary, the domain's shape, naming conventions (for a migration scope:
  the system landscape and glossary). It is a declared input of *every* writer in the scope
  (in `inputs_hash` — it compiles first, everyone consumes it). One vocabulary, one model,
  hundreds of pages. It should be small and stable: when it materially changes, dependent
  pages legitimately recompile — that is correct semantics, priced consciously.
- **Parents synthesize.** A parent page compiles after its children and sees their summaries —
  cross-child insight ("three modules all depend on the same legacy table") lives at the level
  that can see across, and can pull cross-child evidence directly.
- **Writers may be agents — the rule is a completeness floor, not a ceiling.** Nothing
  restricts a writer to its pre-hydrated bundle: for high-stakes scopes the writer is a full
  agent session (Codex/OpenCode) with retrieval tools over the memory. The rule guarantees the
  *floor* — every matching evidence item verifiably reached the compile (candidate set
  recorded, uncited items counted) — and citations record everything used, floor or beyond.
  The contract is only: one owner per page, recorded inputs.
- **The reflection pass.** A periodic LLM job reads across the compiled tree plus health
  metrics (orphan volume, staleness distribution, page sizes, uncited-candidate rates,
  navigation dead-ends) and proposes structural changes — repo-wide noticing, landing as
  recorded `knowledge_plan_decisions` instead of anonymous edits. It should run as a
  **different agent/model than the planner** — fresh eyes challenging the tree, not the
  proposer grading its own work.

**Review without a human in the loop.** The design's gates — the blast-radius review band,
`authored_review` flags, quarantine triage, handover confirmation — require an **accountable
decision point outside the automatic path**, not specifically a person. In agent-operated
deployments (the norm for the named targets), the review-band consumer is a designated
**reviewer agent**, authored pages are owned by the operating agents that wrote them, and the
user is *notified, never consulted*. This is safe to run because structure is revertible by
construction (append-only plan decisions + git history + snapshots), so a wrong verdict costs
a revert, not a loss. The residual risk — agents reviewing agents, the same family as D42's
self-confirmation concern — is accepted and priced: every decision carries its trigger and
rationale, every compile its inputs and citation deltas, so a human can always **audit after
the fact**. The human's realistic role in these deployments is auditor, not operator.

The **semantic linter** survives, demoted from load-bearing to quality assurance: it no longer
detects staleness (that is mechanical now); it checks prose — cross-page contradictions,
broken narrative, tone drift — and files findings as review items or recompile requests.

**Evaluation (O6, D22 pattern).** Plane K gets its own eval surface: *writer completeness*
(planted-fact canaries — a claim matching a page's rule must appear or be counted uncited),
*citation faithfulness* (sampled audit that the page's statements are supported by its
citations — the D32-layer-4 pattern applied to K), and *staleness latency* (evidence-change →
recompile lag against the configured cadence).

## 8. The belief tier (K3 under D47)

K3 is not separate machinery; it is the same mechanism under stricter configuration:

- **Rules select only settled evidence**: relations/observations with `evidence_count ≥ N`
  (placeholder to measure) and **no live `contradiction_group`** — the candidate filter D2
  anticipated ("a candidate filter for L5 core beliefs").
- **Updates are evidence-gated**: belief pages recompile only when their evidence set changes
  — never on a timer — which is what "updates only on evidence, resistant to drift"
  (requirements) means operationally.
- **Citations are mandatory in both roles**: every belief links its supporting *and*
  contradicting evidence (`knowledge_evidence_role`), so a belief is always one hydration away
  from its grounds.
- Human stance enters through the same two doors as everywhere else: sidecar curation on
  compiled belief pages, or authored position pages that cite evidence and carry watch rules.

Open, deliberately (tracked in `questions.md` #5): *whose* beliefs these are (the user's? the
system's epistemic state?) and whether a belief carries a numeric stance. The mechanism above
is agnostic to that answer; the answer will configure it, not replace it.

## 9. Worked example — a migration scope (as-is / to-be), and the promotion loop

The data-migration deployment (registries §1) tracks the **as-is** state of an enterprise
system landscape and designs the **to-be** state. One scope, two subtrees — and the split
between compiled and authored does **not** fall on the as-is/to-be line. The line is
*attested vs. being-created* (§4): future-state facts that sources attest are evidence like
any other; only content no source yet attests must be authored.

- The systems extension pack (registries §4) makes the landscape *entities*:
  `System`/`Module ⊂ Product`, `BusinessProcess ⊂ Concept`, predicates `uses`, `depends_on`,
  `part_of`. Workshop notes, emails, and specs from different people all resolve onto the same
  module entities — that is plane E doing its job.
- **`as-is/` is compiled.** The ordering-subsystem page holds an `entity_subtree` rule on the
  subsystem entity; module pages hold `entity` rules; the scope's shared model page holds the
  landscape overview and glossary. Every workshop note that mentions module X mechanically
  reaches module X's page (the completeness floor — for a migration, "no interface silently
  missed" *is* the quality bar), and every statement hydrates to claims to source documents
  (the audit bar).
- **`to-be/` is mostly compiled too.** The future state is *attested*: workshop minutes,
  decision registers, and ratified design documents assert it. "Orders flow through the new
  ESB from Q3" is a claim like any other, carried by the Work pack's `Decision` entities
  (registries §4 — a decision is a fact that holds until reversed) and future-dated validity
  windows (D41 intervals are just windows; nothing requires them to be past). A later workshop
  revising a decision is **ordinary supersession** — "what was the standing decision on X as
  of March?" is an as-of query — and the to-be pages recompile as decisions move. This is why
  the most-important-to-track content belongs on the compiled side: *tracking is what compiled
  pages do.* The authored-only alternative fails visibly: fifteen workshops in, an authored
  target-architecture doc drowns in review flags while someone manually merges every change.
- **Only the drafting front is authored.** The target design *being written* — commitments no
  source attests yet — is an authored page citing the as-is evidence it stands on, with watch
  rules on the entities it maps.
- **The promotion loop** closes the two: **draft** (authored) → **ratify** → **ingest the
  ratified document as a source** (D42 stamps it system-originated, so it never inflates
  external evidence counts) → its statements become claims / `Decision` entities / future-dated
  relations → the compiled `to-be/` pages **absorb it automatically** → the draft page is
  retired or handed over (`convert_kind`, §4). Authored is the *workbench*; compiled is the
  *record*.
- **The ground shifts**: a late workshop note yields the claim "module X *also* writes table
  B." Plane E records it; routing marks the module X as-is page and the affected compiled
  to-be pages stale (recompiled next window) — and any still-authored draft citing the old
  fact gets a **review flag** routed to its author (in these deployments, the operating
  agent): *a commitment on this page rests on evidence that changed.* Nothing is silently
  rewritten and nothing goes silently stale.
- **Structure without a human.** The scope's tree (an `as-is/` subtree mirroring the system
  landscape; a `to-be/` decision-log + target-architecture layout) is planner-maintained
  state, seeded and periodically challenged by the reflection/reviewer agent (§7) — recorded
  plan decisions end to end; the human appears only in the audit trail.

## 10. Deletion and hard-forget

The deletion cascade (requirements; E0 §2) reaches plane K mechanically through citations:

- **Delete a document** → its claims/relations/evidence go (E-plane cascade) → reverse lookup
  through `knowledge_artifact_evidence` → affected **compiled** pages recompile without the
  removed evidence; affected **authored** pages get review flags; pages whose rules now match
  nothing become planner retire proposals. No tombstone guesswork.
- **Hard forget (GDPR)** additionally requires erasing the *text* the evidence produced. New
  compiled bodies regenerate clean, but **git history retains prior page versions** — so the
  K repo's hard-forget mechanism is a history-erasure step (rewrite/squash of the affected
  paths' history, e.g. `git filter-repo`, plus the same treatment for the repo's backups),
  scoped by the citation index to exactly the pages that ever cited the forgotten source.
  Authored pages that cited it are flagged for the author to redact — the system must not
  rewrite an author's words, even to forget.

## 11. Consequences, residuals, and spikes

**What this buys** (mapped to standing requirements): "refreshed incrementally, never
globally" becomes exact (the stale set *is* the refresh set); K3's "every belief linked to
evidence" holds by construction; the deletion cascade reaches K mechanically; per-page
freshness metadata exists; the K half of the "serial git bottleneck" risk is removed
structurally (one committer, disjoint writes, DAG order).

**Residuals, honestly named:**
1. **Planner quality is the new load-bearing judgment.** A bad tree is a bad tree — but it is
   inspectable, append-only state (reviewable, revertible), not emergent session behavior.
   Blast-radius gating (D24 pattern) bounds the damage of any single decision.
2. **Rule-kind coverage.** The closed kind set must express how real scopes define their
   pages; `manual` is the escape hatch and new kinds are additive registry-style changes. If a
   scope's pages routinely need semantic membership, that is a signal to improve plane E's
   keys (an ontology extension), not to add description-matching to routing.
3. **Hub pages.** A mega-entity's candidate set (the user in an assistant deployment; the
   company in the agency) can exceed a writer's context: the rule needs ranking/budgeting
   (evidence-count-ordered top-N with an explicit "and N more" ledger) — the same hub problem
   observations handle, solved the same cheap-first way.
4. **Shared-model-page churn** recompiles its scope; keep it small, stable, and mostly
   authored.

**Spikes (measure before locking numbers):**
1. Rule-kind coverage on a real scope (drive the planner over an actual corpus slice; count
   `manual`-rule frequency — high frequency = missing kind or missing ontology key).
2. Planner blast-radius bands (auto-apply vs review thresholds; like D24's
   `expected_impact` middle band).
3. Writer completeness + citation faithfulness eval (canaries; sampled audits) — joins the
   E2/E3 harness (`questions.md` #14) as one eval surface.
4. Belief-tier thresholds (`evidence_count ≥ N`; contradiction handling policy).
5. Compile-cycle economics at scale (dirty-pages distribution per debounce window; hub-page
   budgets; shared-model-page recompile blast radius).
6. Git-history erasure mechanics for hard-forget (filter-repo on a living repo + backup
   rotation) — coordinates with the end-to-end forget item (`questions.md` #24).
7. **Future-state extraction** for migration-style scopes (§9): decision-language →
   `Decision` entities + future-dated D41 windows, and how planned flows normalize
   (future-dated `uses`/`depends_on` relations vs Decision-mediated) — measure on a corpus
   slice; gates how much of a `to-be/` subtree can be compiled.

## References

Decisions: **D45–D47** (this design), D1, D11, D12, D16, D24, D33, D42, D43 (`decisions.md`).
Objections resolved: O2, O4 (`plan/analysis/objections.md`). Review that motivated it:
`plan/analysis/design_review_2026_07.md` (F1). Schema: `postgres_schema_design.md` §11.
Adjacent designs: `overall_design.md` §5, `registries_design.md` (scopes, extension packs),
`e0_files_design.md` §2 (deletion), `p2_graph_design.md` §7 (community → refresh hints).
