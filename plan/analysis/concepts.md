# Concepts: Claims, Relations, Evidence, and the Two Clocks

A pedagogical companion to `../../requirements_v2.md` and `../designs/p2_graph_design.md`. Explains the core
data model with a running example.

**One-line mental model:** claims are the courtroom transcript (immutable testimony — who said
what, when); relations are the verdict (the current adjudicated facts, revisable); evidence is
the link between testimony and verdict; the graph is the published, navigable index of the
verdicts.

## 0. The terminology ladder (read this first)

The system's words stack bottom-to-top. Each row is a different *kind* of thing, in a
different place, with different rules:

| Term | What it is | Where it lives | Can it change? |
|---|---|---|---|
| **claim** | what one source *said* — the permanent record of an assertion | Postgres (E2) | never (immutable) |
| **relation** | a fact linking **two entities** — `(Alice, works_for, Acme)` | Postgres (E3) | validity windows close on supersession |
| **observation** | a fact stating a **value about one entity** — "Acme headcount 600" (D43) | Postgres (E3) | same bi-temporal rules; never enters the graph |
| **fact** | the umbrella word for *relation or observation* — "what the system currently holds true" | — | — |
| **core principle** | a chosen personal or organizational stance: authored K2 content, cited and watched but never machine-promoted or rewritten (D73) | the K git repo | only its accountable author changes it; evidence changes raise review flags |

Two distinctions that ride on the ladder:

- **The grains** (retrieval vocabulary, D49): every answer is labeled **`fact`** (relations/
  observations — what the system currently holds true, validity-filtered), **`evidence`**
  (claims — what sources asserted, possibly stale or contradictory), or **`compiled`** (K
  pages — pre-paid synthesis with a freshness stamp). A claim must never be mistaken for a
  current fact — that is the split this whole model exists to enforce. *(Naming note: the
  fact grain was called the "belief grain" in early drafts of D48–D51; renamed July 2026
  because "belief" ambiguously mixed current facts with normative stances. D73 places the
  latter in authored K2 pages.)*
- **Testimony currency** (D54): a claim is *current testimony* while it belongs to its
  document's current version and extraction generation; superseded generations and
  removed-content claims stop counting toward facts and drop out of default search, while
  remaining permanent history. Currency is bookkeeping about *our transcription*, never a
  judgment about truth — claims stay immutable in every sense.

So a sentence like "the roster says Bob is CFO" travels: **claim** ("this file said it") →
**relation** (`Bob works_for Acme`, the current fact the system holds) → possibly synthesized
in a compiled K1/K2 page. A personal principle may cite that history as context, but is never
inferred from it.

## Running example

Three documents enter the system:

- **Doc A** (press release, March 2024): *"Acme today announced that Alice Novak joins as VP of
  Engineering."*
- **Doc B** (interview, June 2025): *"Alice, who leads engineering at Acme, said the team
  doubled."*
- **Doc C** (news, January 2026): *"Alice Novak left Acme to found Beacon Labs."*

## 1. Claims: what a source *said*

Claim extraction (Claimify) turns each document into atomic, verifiable natural-language
statements:

```
c1 (from A): "Alice Novak joined Acme as VP of Engineering in March 2024."
c2 (from B): "Alice Novak leads engineering at Acme."         (as of June 2025)
c3 (from C): "Alice Novak left Acme in January 2026."
c4 (from C): "Alice Novak founded Beacon Labs."
```

The defining property of a claim: **its identity is the assertion-by-a-source.** c1 and c2 say
almost the same thing about the world, but they are *different claims* — different documents,
different dates, different wording. That's a feature, not redundancy: claims are the evidence
record. They stay in natural language because the world doesn't fit into triplets — c1 carries
a role *and* a date *and* an event ("joined"), and forcing it into one (s, p, o) would destroy
information. A claim can also be an opinion or a prediction, which should never become a graph
"fact" at all.

Claims are **append-only**. Nothing ever rewrites c1. It's true forever that *Doc A asserted
this in March 2024* — even after Alice leaves.

## 2. Relations: what the system *believes*

A separate normalization step looks at each claim, sees which canonical entities it mentions,
and asks: *which binary facts does this assert, in our controlled predicate vocabulary?*

```
c1 → (alice, works_at, acme)  +  (alice, has_role, vp_engineering@acme)
c2 → (alice, works_at, acme)          ← the SAME fact again
c3 → terminates (alice, works_at, acme)
c4 → (alice, founded, beacon_labs)
```

The defining property of a relation: **its identity is the fact itself**, independent of who
said it. `(alice, works_at, acme)` exists *once* in the relations table, no matter how many
documents assert it.

Claims-to-relations is many-to-many:

- c1 produced **two** relations (one claim, several facts)
- c2 produced **zero new** relations — the fact already existed
- some claims produce **no relation**: opinions are dropped at Selection; n-ary facts decompose;
  and single-entity **attribute statements** like "Acme was founded in 1998" / "Acme's headcount is
  600" now become **observations** — a separate, untyped, entity-anchored non-graph layer with the same
  bi-temporal validity and supersession (D43, `../designs/observations_design.md`). Either way the
  claim stays fully retrievable in E2 via Lance/FTS.

## 3. Evidence: the join between the two

When c2 arrives and normalizes to `(alice, works_at, acme)`, which already exists with a
compatible validity window, nothing new is created — the system records:

```
relation_evidence:
  (r1, c1, supports)
  (r1, c2, supports)
```

This is where corpus redundancy goes to die. At a million documents, popular facts get asserted
hundreds of times. Without the relation layer, that's hundreds of near-duplicate graph edges
needing fuzzy dedup. With it, it's **one edge with evidence_count = 247** — and that count is
itself useful: a fact independently asserted by 247 sources is more trustworthy than one
asserted once. Confidence becomes an aggregate over evidence rather than a guess at extraction
time. It is a ranking and adjudication signal, not an automatic promotion mechanism for
normative principles (D73).

## 4. Supersession at the relation level

c3 arrives: *"Alice left Acme in January 2026."*

What does this statement actually invalidate? **Not c1.** c1 remains perfectly true — Doc A
really did assert, in March 2024, that Alice joined. No document is wrong; nothing about the
*evidence record* changed. What changed is the **fact**: the relation `(alice, works_at, acme)`
stopped holding in January 2026.

So supersession updates the relation:

```
r1 = (alice, works_at, acme)
     valid_from  = 2024-03-01
     valid_until = 2026-01-15      ← closed by adjudication, evidence: c3
```

If supersession operated on claims instead, the system would face an absurd task: find *every
individual sentence in every document* that ever implied Alice works at Acme, and mark each one
superseded — hundreds of records, inevitably missing some, leaving "zombie" assertions that
retrieval still surfaces as current. Operating on the relation, it's **one update to one row**,
and every evidence claim automatically inherits the correct interpretation: "these sources
asserted something that *was* true until 2026-01-15."

Contradiction works the same way: if Doc D says Alice works at Acme *and* Doc C says she left,
and the system can't adjudicate (murky dates), both relations stay live with a shared
`contradiction_group`, and retrieval shows both sides instead of silently picking one.

## 5. Two clocks (bi-temporality)

Each layer carries bi-temporal fields, but they answer **different questions**:

| | Claim's clocks | Relation's clocks |
|---|---|---|
| **Question** | When was this *asserted*, when did *we ingest it*, and what world-time interval did the source say it held over? | When was this fact *true in the world*, and when did *we believe it*? |
| **Who sets it** | The source (assertion date + the asserted-validity interval, D41) and the pipeline (ingestion) | Adjudication over all evidence |
| **Ever changes?** | Never — claims (incl. their asserted interval) are immutable | Yes — windows get closed by supersession |

**Claims carry a third, immutable axis (D41): the validity interval the source *asserted*** —
"Alice joined Acme *in March 2024*" freezes an asserted `valid_from` of 2024-03 onto the claim. This
is *testimony about temporal extent*, not the system's belief: many sources may assert many different
(even contradictory) windows and all stand forever — that is what makes it evidence, not a second
authority. Its payoff is the facts that never become relations: "Acme's revenue was \$5M in FY2023"
yields no relation (revenue is a quantity, not an entity object — §2), so before D41 its world-time
lived only inside the claim text; now it carries `claim_valid_from`/`until` and is queryable by time
*as evidence*. The **adjudicated, revisable** window (the relation's `valid_from`/`valid_until`) is
computed *over* these asserted intervals and remains the single home of current belief. *(Updated by
**D43**: such non-relational facts now also become **observations** — entity-anchored, bi-temporal —
so two conflicting FY2023 revenue figures don't merely "both stand as raw evidence" but become two
two observations (same property + same period, matched semantically) linked by a shared
`contradiction_group`, surfaced as a structured conflict and still never silently resolved. See
`../designs/observations_design.md`.)*

Timeline of the example, system's perspective:

```
world time:      2024-03 ────────────────────── 2026-01
                 Alice works at Acme            Alice leaves

system time:     2024-04        2025-07         2026-02
                 ingest A       ingest B        ingest C
                 r1 created     evidence += c2  r1.valid_until = 2026-01-15
```

The two axes answer two genuinely different time-travel questions:

- *"Did Alice work at Acme in December 2025?"* → world time: yes
  (`valid_from <= t < valid_until`).
- *"What did the system believe on 2026-02-01, before we ingested Doc C?"* → system time: it
  believed she still worked there (`ingested_at <= t < invalidated_at`) — indispensable for
  debugging ("why did the agent say X last month?") and audit.

A single timestamp can't distinguish "the fact changed" from "we found out." Bi-temporality
keeps both.

## 6. Blocking: why supersession detection is a relations-shaped query

"Blocking" is a classic entity-resolution term: instead of comparing a new item against
*everything* (O(N) — fatal at millions of claims), you compare it only within a small *block*
of plausible candidates.

When c3 arrives, the question is: "does any existing fact conflict with this?" The candidate
set isn't "all 50M claims that are vaguely similar in embedding space" — vector similarity
surfaces tons of compatible-but-related statements (false positives an LLM then has to wade
through). The candidate set is precisely: **relations where `subject = alice` and
`predicate = works_at`**. Usually 1–5 rows. Then and only then are cheap similarity checks
spent — and (if still ambiguous) an LLM call — on the tiny remainder.

The block key is `(entity_id, predicate)` — but raw claims don't *have* a predicate; they're
free text. Blocking is only possible once normalization has produced the (s, p, o) form. So
the relations table isn't just nicer modeling — it is **the index that makes supersession
detection affordable at scale**. And it's small (distinct facts, not assertions), making the
scan even cheaper.

## 7. The Graphiti analogy

Graphiti (Zep's engine) has the same three-level shape under different names:

| Graphiti | Ours |
|---|---|
| **Episode** — a raw ingested message/document, kept forever | **Claim** (plus the E0 doc) — what was said, immutable |
| **Edge with a fact label** — a normalized fact between entity nodes, carrying `valid_at`/`invalid_at` | **Relation** → projected as graph edge |
| **Edge's episode list** — every episode that mentioned this fact | **relation_evidence** — every claim supporting/contradicting the fact |

When Graphiti ingests a new episode contradicting an existing edge, it doesn't touch old
episodes — it sets the *edge's* `invalid_at` and keeps the episode list as history. Exactly our
supersession-at-relation-level.

The one place we deliberately diverge: Graphiti runs this adjudication *inside the graph store
at write time*. We run it in Postgres at the E2/relation level, and the graph just mirrors the
result — because our graph is a disposable, rebuildable projection, and validity must have
exactly one home (see `../designs/p2_graph_design.md` §1).
