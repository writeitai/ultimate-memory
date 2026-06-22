# TY2 — Mention-level vs Entity-level typing: reconciliation + disagreement-as-ER-signal

**Question.** A mention is typed *in context*; the canonical entity needs *one* type. (1) How
are per-mention type votes reconciled into the entity type? (2) When mentions of the same
resolved entity disagree on type, is that genuine ambiguity/metonymy, or a SIGNAL that
resolution wrongly merged two referents (Washington-person vs Washington-place)? (3) How
should type-disagreement feed back into the ER cascade (D17/D21) and the blast-radius/review
machinery (D24)?

Scope: typing is the unspecified gap; identity is fully specified (D17). D18 domain/range
enforcement *requires* a known entity type, so reconciliation cannot be deferred.

---

## 1. Key findings

1. **No surveyed system treats type-disagreement as an ER signal — and that is the gap UGM
   should fill.** Every system reconciles types *assuming the merge was correct*: Graphiti
   promotes generic→specific monotonically and silently swallows specific-vs-specific
   conflicts (`dedup_helpers.py:175-188`); LightRAG takes a majority vote
   (`operate.py:1671-1674`); Cognee does first-writer-wins per canonical key with no
   arbitration; GraphRAG instead bakes type *into the identity key* (`groupby(["title","type"])`,
   `extract_graph.py:104-115`) so a type conflict *forks* the entity. None of them ever asks
   "does this disagreement mean the merge was wrong?" The disagreement is discarded as noise
   the moment a reconciliation rule fires.

2. **Type is a soft discriminator at resolution time, but only Graphiti actually uses it.**
   Graphiti's dedup LLM prompt feeds `entity_types` to the model and its few-shot examples
   *teach the model to use type difference to refuse a merge*: "NYC" → New York City
   (Location) not New York Knicks (Organization); "Java" the programming language is `-1`
   (no match) against "Java" the island (Location) — same name, different type, **distinct
   real-world things** (`dedupe_nodes.py:101-105, 166-170`). This is the production embodiment
   of the coref literature's "soft type consistency check" between candidate mentions
   ([Khosla & Rose 2020, *Using Type Information to Improve Entity Coreference Resolution*](https://arxiv.org/abs/2010.05738))
   — soft feature, never a hard block, so strong other evidence can override it.

3. **The Washington/Java case is a real, named failure mode in the coref/cross-doc
   literature, and type is the standard cue against it — but it is bound up with metonymy,
   which is the genuine-ambiguity case that must NOT trigger an un-merge.** "The US president"
   (Person) and "the White House" (Place/Org) are *metonymous* — legitimately co-referring
   facets of one entity — and coref systems need special handling to avoid both wrongly merging
   them and wrongly treating them as an error
   ([Cattan et al., cross-doc coref codebook](https://arxiv.org/pdf/2310.12064);
   [Jurafsky & Martin SLP3 ch.26](https://web.stanford.edu/~jurafsky/slp3/26.pdf)).
   So type-disagreement is genuinely **ambiguous between (a) metonymy/role-shift and (b) a bad
   merge** — UGM cannot auto-resolve it one way; it must route the *hard* cases to adjudication.

4. **A subtle reconciliation bug to avoid: LightRAG dedups the type list before the vote**
   (`list(dict.fromkeys(entity_types))`, `operate.py:1666`) then runs
   `max(set(...), key=...count)` — after dedup every type appears once, so the "majority vote"
   collapses to *first-seen-wins* whenever all types are distinct. A real vote must count over
   the **multiset** of mention types, not the deduped set. This matters directly for UGM's
   reconciliation rule (§4).

---

## 2. Evidence & detail with citations

All repo paths under `/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/`.

### 2a. How each system reconciles per-mention types → entity type

| System | Reconciliation rule | Disagreement handling | Cite |
|---|---|---|---|
| **Graphiti** | Monotonic **generic→specific promotion** on merge: if canonical is bare `Entity` and the new duplicate has a specific label, upgrade. | If canonical *already* has a specific label, **return it unchanged** — the incoming specific label is silently dropped. No conflict raised. | `dedup_helpers.py:170-188` (`_promote_resolved_node`); same-msg collapse keeps the more-specific node `node_operations.py:336-384` |
| **LightRAG** | **Majority vote** over mention types, `"UNKNOWN"` fallback. | Majority wins; minority discarded; **no signal**. (Bug: types deduped first → degrades to first-seen-wins, `operate.py:1666`.) | `operate.py:1671-1674` |
| **Cognee** | **First-writer-wins** per canonical (name-derived) key. | Two type strings that normalize differently → **two separate `EntityType` nodes / two `is_a` edges**; nothing arbitrates. | `expand_with_nodes_and_edges.py:113-120, 172-179` |
| **GraphRAG** | **Type is part of identity** — `groupby(["title","type"])`. | Type conflict **forks the entity** into two; no reconciliation at all. | `extract_graph.py:104-115` |
| **GLiNER** | N/A (mention-level only; per-span `score`, no merge). | Downstream's job. | `gliner/model.py:2279-2285` |

**Verified mechanics of Graphiti's silent-swallow** (the load-bearing detail): `if
resolved_specific_labels: return resolved_node` (`dedup_helpers.py:175-176`) — once the
canonical carries any non-`Entity` label, a *contradicting* specific label on the new mention
is never even compared. So Graphiti's promotion is **monotonic generic→specific but blind to
specific↔specific conflict**. That conflict is exactly the Washington/Java signal, and Graphiti
throws it away post-merge.

### 2b. Where type DOES act as an anti-merge signal (resolution time, not post-merge)

Graphiti's dedup *prompt* is the only place any system uses type to prevent a wrong merge, and
it is a **soft** cue inside an LLM judgment, not a hard rule:

- `dedupe_nodes.py:101` / `:166`: candidate set includes `New York City` (Location) and `New
  York Knicks` (Organization); the gold output picks the Location for "NYC" — type
  disambiguates which same-string candidate to bind.
- `dedupe_nodes.py:105` / `:170`: "Java" (programming language) vs existing "Java"
  (Location) → `duplicate_candidate_id = -1` — **type difference drives a non-merge** ("same
  name but distinct real-world things").
- System instruction: "NEVER mark entities as duplicates if … they have similar names …
  but refer to separate instances or concepts" (`dedupe_nodes.py` nodes prompt).

This matches the literature exactly:
- [Khosla & Rose 2020 (arXiv 2010.05738)](https://arxiv.org/abs/2010.05738): type used as a
  **soft type consistency check between coreference candidate mentions** — "modest gains",
  soft feature not hard constraint, so it can be overridden.
- [Cattan et al. cross-doc coref codebook (arXiv 2310.12064)](https://arxiv.org/pdf/2310.12064)
  and [SLP3 ch.26](https://web.stanford.edu/~jurafsky/slp3/26.pdf): conflated entities (mentions
  from different real entities in one cluster) are a named entity-level error class; **metonymy**
  ("the White House" ⇄ the administration) is the case where type-shift is *legitimate* and must
  not be coded as an error.

**Inference (clearly flagged):** the literature consensus — soft, never hard — is the right
stance for UGM. A hard "types must match to merge" rule would wrongly block metonymy
(Person/Organization facets, "Amazon" company/place/river when genuinely one referent) and
the very generic→specific upgrades Graphiti relies on. So type-disagreement should *raise a
review/escalation*, not *auto-reject a merge*.

### 2c. Why "disagreement = bad merge" is a usable but not sufficient signal

The same-string + different-type pattern (Washington person/place, Java language/island,
Apple company/fruit) is the textbook over-merge. But type-disagreement has **three distinct
causes** the system must separate:

1. **Bad merge / conflated entities** (over-merge) — Washington-the-person ∪
   Washington-the-place. *Action: this is the ER-signal; route to un-merge review.*
2. **Metonymy / role-shift** (genuine, one referent) — "the White House said" (Org/Place
   facet of an administration), a company referred to by its HQ city. *Action: keep merged;
   record both type facets; pick a canonical type by priority.*
3. **Mention-level typing error** (the typer was wrong on one mention) — GLiNER/LLM mis-typed
   a low-confidence span. *Action: down-weight the low-confidence vote; no ER action.*

No surveyed system distinguishes these. The discriminators that separate them are available
in UGM and cheap: **per-mention type confidence** (GLiNER `score`, `model.py:2279-2285`),
**vote distribution** (a 50/50 split is over-merge-shaped; a 90/10 split is a typing-error
or metonymy-shaped), and **type-pair compatibility** (Person/Place are incompatible →
over-merge; Person/Organization are a known metonymy pair → keep).

---

## 3. Confidence & gaps

**HIGH confidence:**
- Reconciliation rules of all five repos, verified at `file:line` (Graphiti promotion +
  silent-swallow, LightRAG vote + its dedup bug, Cognee first-writer, GraphRAG fork).
- Graphiti uses type as a *soft resolution-time discriminator* via its dedup few-shot
  (Washington/Java pattern in-prompt) — read directly from `dedupe_nodes.py`.
- The coref literature frames type as a soft consistency check and names metonymy as the
  legitimate-disagreement case.

**MEDIUM confidence:**
- That a vote-distribution / type-incompatibility heuristic cleanly separates over-merge from
  metonymy. The mechanism is sound and matches the literature, but **no surveyed system
  implements type-disagreement-as-ER-signal**, so there is no production precedent to copy —
  this is a UGM original (low risk, but must be golden-set-validated, D22).
- The Khosla & Rose "modest gains" magnitude (PDF was unreadable binary; relying on the
  abstract via the arXiv landing page, not the results tables).

**GAPS / could not verify:**
- No benchmark number for "what fraction of same-name type-disagreements are over-merges vs
  metonymy" exists in any source I found — **do not invent one**; this is a golden-set spike.
- Whether metonymy pairs (Person↔Organization, Organization↔Place) can be enumerated tightly
  enough to be a reliable allow-list vs. needing the LLM tier — unverified, needs corpus data.

---

## 4. Recommendation for ugm

Tie-in: D15 (type is registry content, an attribute), D17 (block-loose/decide-tight cascade,
type is *not* on the identity key), D18 (domain/range needs one known type), D21
(reversibility/un-merge records), D22 (golden set), D24 (blast-radius review).

### R1 — Keep type OFF the identity key; reconcile it as an entity-level attribute (confirms D17)
Adopt LightRAG's posture (type is reconciled, not part of identity), **reject GraphRAG's
`groupby(["title","type"])`** which forks on disagreement and contradicts D17/D21. The
mention's type is stored on the `mentions`/`resolution_decisions` row; the entity's `type`
column (registries_design §2) is a *derived reconciliation* over the mentions of that entity,
recomputable on rebuild.

### R2 — Reconciliation rule: confidence-weighted vote with a specificity tiebreak, fallback `Concept`
Per resolved entity, compute the canonical type as:
1. **Confidence-weighted vote** over the multiset of mention types (count *every* mention,
   weighted by typer confidence — GLiNER `score` / LLM logit). **Do not dedup the type list
   first** — that is LightRAG's bug (`operate.py:1666`); count the multiset.
2. **Specificity tiebreak via the registry parent chain (D15/D18):** between two tied types
   on the same `parent_type` path, prefer the more specific (child) — this is Graphiti's
   generic→specific promotion (`dedup_helpers.py:184-188`) generalized to the UGM type tree
   (`ResearchPaper ⊂ Document`). Never let a bare-parent vote outweigh a confident child.
3. **Fallback = `Concept`** (the D18 core parent / catch-all) when no mention is typed above
   threshold, so D18 domain/range always has a defined type to gate on (GLiNER drops
   sub-threshold spans, so this bucket must be explicit).
This is a total function mention-votes → one entity type, recomputed every projection rebuild
(D7), so retyping is retroactively clean.

### R3 — The disagreement-as-ER-signal mechanism (the original contribution)
After R2, examine the **vote distribution** and **type-pair compatibility**, not just the
winner. Define a `type_conflict_score` on the entity from:
- **Cross-branch incompatibility:** the two top types are on *different* core-parent branches
  (Person vs Place — incompatible; Person vs Organization — flagged metonymy-allowed; child
  vs its own ancestor — compatible, just specificity). Maintain a small registry
  `type_metonymy_pairs` allow-list (seed: Person↔Organization, Organization↔Place,
  Person↔Document for pen-names) so known metonymy is *not* scored as conflict.
- **Vote balance:** an even split (each branch backed by multiple *high-confidence* mentions)
  is over-merge-shaped; a lopsided split (one high-confidence majority + a single low-confidence
  outlier) is a typing-error and is absorbed by R2's weighting, not escalated.

Then route on `type_conflict_score`:
- **Incompatible cross-branch + balanced high-confidence split → ER over-merge candidate.**
  Do NOT auto-un-merge (over-merge is silent and catastrophic, but so is a wrong un-merge of a
  metonym). Instead **emit a candidate un-merge into the D24 review queue**, ranked by
  `expected_impact = blast_radius × (1 − confidence)` (D24) — type-conflict is a new, cheap
  contributor to that score. The pre-merge membership snapshot in `merge_events`
  (registries_design §6, D21) already lets the reviewer split the cluster back along the two
  type-coherent sub-clusters; the type votes *suggest the split boundary* (mentions typed
  Person vs mentions typed Place become the two proposed survivors).
- **Metonymy-allowed pair → keep merged**, store both type facets on the entity (a
  `type_facets[]` column; canonical `type` still chosen by R2 priority), and record it so it
  is not re-flagged each rebuild.
- **Low-confidence outlier only → no ER action**, absorbed by R2.

### R4 — Feed it back into the cascade as a *soft pre-merge* check too (D17)
Mirror Graphiti's dedup prompt: at **T5 LLM adjudication**, pass the candidate types into the
prompt as a **soft discriminator** (the NYC/Knicks, Java/island pattern,
`dedupe_nodes.py:101-105`) so cross-branch-incompatible candidates are *less* likely to merge
in the first place — caught at decide-tight time, before they ever need un-merging. Keep it
**soft, never a hard block** (literature consensus; preserves metonymy and generic→specific).
This makes type a two-sided lever: a soft *anti-merge* cue going in (T5), and a *bad-merge
detector* coming out (R3) for whatever slipped through.

### R5 — Golden-set obligation (D22)
The over-merge-vs-metonymy split rate is unmeasured anywhere — add a golden-set slice of
**same-name, type-disagreeing entity pairs** (Washington person/place, Java language/island,
Apple company/fruit as hard positives-for-split; White House/administration,
company-by-HQ-city as hard negatives-i.e.-keep-merged). Tune the `type_conflict_score`
threshold and the `type_metonymy_pairs` allow-list against it, per-type, versioned by
`resolver_version` — exactly the D17/D22 discipline already mandated for identity thresholds.
Wire `type_conflict_score` into the §10 health metrics (a rising rate = an emerging over-merge
or a missing metonymy pair).

**One-line rule:** reconcile by confidence-weighted multiset vote with a specificity tiebreak
and `Concept` fallback (R2); treat a *balanced, high-confidence, cross-branch-incompatible*
type split as an over-merge candidate routed to the D24 review queue (never an auto-un-merge),
with known metonymy pairs allow-listed so legitimate facet-shift stays merged (R3).
