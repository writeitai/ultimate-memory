# Non-Relational Claim Conflicts

## Executive conclusion

The gap is real. D41 makes non-relational claims time-filterable as evidence, but it does not give
them a fact identity. Without a fact identity, the system cannot attach a `contradiction_group`, close
a validity window, or record an adjudicated current value. That is intentional in D2/D3, but it leaves
one unsafe retrieval behavior: an agent can ask for a single-entity or literal-valued fact and receive
one source assertion without being shown that other sources assert incompatible content for the same
entity, attribute, and period.

The right base design is **not** a second adjudicated fact layer. The right base design is a
lightweight, governed **non-relational conflict index over claim-derived attribute assertions**:

- extract immutable attribute assertions from claims that yield no relation;
- key them by canonical entity, governed attribute/measure, qualifiers, and the relevant
  source-asserted world-time semantics;
- detect incompatible value groups inside that block;
- store only conflict annotations and membership, never a winner, never `valid_until`, never
  `invalidated_at`, never `superseded_by`;
- make claim retrieval hydrate conflict siblings by default for attribute-style questions;
- trigger K-plane refresh so K3 can narrate the conflict or, when the deployment needs a belief, record
  a cited K3 belief with supporting and contradicting evidence.

This is option **B** below, with one important addition: detection requires a governed
attribute/measure vocabulary analogous to the predicate registry. Raw natural language plus embeddings
is not enough to decide that "FY2023 revenue", "sales", "ARR", "net revenue", and "founded" are the
same or different attributes at 10^7-10^8 claim scale. Entity resolution is also mandatory. The
blocking key cannot exist without a canonical subject entity and canonical attribute.

The named upgrade, admitted only when a deployment has measured demand for structured current values
for non-relational facts, is **Proposition Facts**: a full fact-identity layer for attributes and
quantities, with evidence, contradiction groups, adjudications, and bi-temporal validity mirroring
relations. That upgrade is coherent, but it is a large new system. It should not be smuggled in through
claim metadata or query recipes.

## What the problem is and is not

D2 deliberately says many claims produce no relation. Examples:

- single-entity attribute facts: "Acme was founded in 1998";
- literal or quantity facts: "Acme's FY2023 revenue was $5M";
- facts whose useful structure is n-ary: "Acme sold 40,000 units in Germany in Q4 through reseller X";
- claims where forcing a Date, dollar amount, or quantity into an entity node would violate D18 and
  contaminate the graph.

D41 solves one part of this: the source-asserted world-time interval is now structured on the claim.
For "FY2023 revenue was $5M", the measurement period can be filtered by `claim_valid_from/until` with
`claim_valid_kind = measurement_period`. That makes the claim retrievable as evidence for FY2023.

It does not solve fact identity. Two claims can now be time-aligned evidence, but the system still
does not know whether they assert the same non-relational fact unless it extracts and normalizes the
attribute and value. A Lance search over claim text may retrieve both sides, but it does not guarantee
that both sides are attached, grouped, or marked as incompatible.

The missing object is therefore not "claim validity". It is a **conflict-bearing identity for the same
attribute assertion block**, short of a full belief fact.

## Detection

### Detection requires a governed attribute/measure vocabulary

The system cannot reliably detect non-relational conflicts from raw claim text alone. The question
"are these the same attribute?" is itself an ontology question:

- `revenue` vs `net revenue` vs `sales` may or may not be the same measure;
- `founded` vs `incorporated` vs `launched` are different attributes in many corpora;
- `headcount` vs `employees` can be synonyms in one deployment and distinct in another;
- `FY2023 revenue` depends on fiscal-calendar interpretation, currency, and sometimes accounting
  basis.

So detection needs an **attribute registry**:

```
attributes
  attribute_id
  parent_attribute_id
  domain_entity_types
  value_kind              -- date | quantity | money | enum | string | boolean
  value_dimension         -- money, count, percent, date, duration, etc.
  aliases/synonyms
  examples
  conflict_rule
  compatible_refinement_rule
  qualifier_schema
  status/tier             -- core | extension | other | deprecated
  scope_id nullable
```

This is not a second predicate registry for graph edges. It is a registry for attributes and
measures that remain claim-level evidence unless promoted to a heavier fact layer. It should follow
D5's governance shape: constrained extraction, `other:<freetext>` escape, periodic review and
promotion, and no silent accretion of free-text keys.

The attribute registry can be smaller and more deployment-specific than the predicate registry.
Universal candidates might include `founded_date`, `fiscal_revenue`, `headcount`, `price`,
`launch_date`, and `status`, but the exact seed is less important than the rule: extraction must not
invent ungoverned labels that become blocking keys.

### Detection also requires entity resolution

The subject side of the key must be a canonical `entity_id`, not a surface string. Otherwise "Acme
Inc.", "ACME", and "Acme Corporation" form separate blocks and conflicts disappear. The existing
entity registry is the right authority. Non-relational conflict detection should inherit D17's
T0-T4 resolution decisions and rerun affected blocks after entity merges or un-merges.

### Extract an immutable claim-attribute assertion sidecar

The system should not overload the `claims` table with many attribute-specific columns. A claim can
contain several non-relational assertions after decomposition, and some assertions need qualifiers.
Instead, E2/E3 normalization should emit a sidecar row for each structured non-relational assertion:

```
claim_attribute_assertions
  assertion_id
  deployment_id
  claim_id
  subject_entity_id
  attribute_id
  attribute_tier           -- core | extension | other
  claim_valid_from
  claim_valid_until
  claim_valid_precision
  claim_valid_kind
  qualifiers_json          -- e.g. accounting_basis, geography, product line, fiscal_calendar_id
  qualifiers_hash
  value_kind
  normalized_value_json    -- typed normalized value, not prose
  value_text               -- source-facing rendered value for audit
  value_unit
  value_currency
  value_precision          -- exact | rounded | approximate | range | unknown
  value_range_low/high     -- when applicable, normalized for comparison
  extractor_or_normalizer_version
  ingested_at
```

This row is still evidence, not belief:

- identity is `assertion_id` or `claim_id`, not "the current value of Acme revenue";
- it is append-only;
- it has no `status`, no `invalidated_at`, no `valid_until` that the system closes, no
  `superseded_by`;
- it carries copied D41 source-asserted time only so blocking and query filters do not reparse text.

The distinction matters. This sidecar is a detection index over claims. It is not a new authority.

### Blocking key

The block key is not one key for every attribute. It depends on the time semantics of the assertion.

For measurement-period attributes, such as revenue:

```
(deployment_id,
 subject_entity_id,
 attribute_id,
 claim_valid_kind = measurement_period,
 normalized_measurement_period,
 qualifiers_hash)
```

Example: both "Acme FY2023 revenue was $5M" and "Acme reported FY2023 revenue of $7M" block together
if they resolve to Acme, `fiscal_revenue`, FY2023, and compatible qualifiers.

For event-time attributes, such as founding date:

```
(deployment_id,
 subject_entity_id,
 attribute_id,
 qualifiers_hash)
```

The date is the value, not the grouping period. "Founded in 1998" and "founded in 1999" must block
together even though their `claim_valid_*` intervals do not overlap. If the block included the date,
the conflict would be missed.

For proposition-validity or effective-period attributes, such as "status = active during 2024":

```
(deployment_id,
 subject_entity_id,
 attribute_id,
 claim_valid_kind = proposition_validity|effective_period,
 overlapping_validity_window_bucket,
 qualifiers_hash)
```

Here the value is a state, and the source-asserted interval is the period over which the state is
claimed to hold. Conflicts are value incompatibilities over overlapping windows.

Qualifiers are part of identity. "Global revenue" and "US revenue" are not a conflict. "Revenue under
IFRS" and "revenue under GAAP" may not be a conflict. The attribute registry must define which
qualifiers are identity-bearing for each attribute.

### Conflict tests

Detection should be aggregate-first, not pairwise-first. Inside a block:

1. normalize values to typed ranges or enum classes;
2. group compatible values into value clusters;
3. mark a conflict only if two or more value clusters are mutually incompatible under the
   attribute's conflict rule;
4. retain low-confidence or ambiguous cases as review candidates, not hard conflicts.

Concrete rules:

- **Date refinement:** `1998` and `1998-04-12` are compatible if the precise date lies inside the
  year and the coarse source did not assert exclusivity. `1998` and `1999` are incompatible for a
  single event-time attribute like `founded_date`.
- **Quantity rounding:** `$5M` and `$5.02M` may be compatible if `$5M` is rounded to one significant
  digit or the source says "about". `$5M` and `$7M` are incompatible unless qualifiers differ.
- **Restated quantity:** `$5M` in a 2024 report and `$5.2M` in a 2025 amended report for the same
  FY2023 period are incompatible values, with an additional `restatement_candidate` annotation if the
  source or text indicates correction.
- **Different attributes:** `founded_date = 1998` and `incorporated_date = 1999` are not a conflict.
  If the extractor cannot distinguish the attribute, the right outcome is an attribute-mapping review
  item, not an invented contradiction.
- **Different scopes:** `Acme revenue = $5M` and `Acme product-line revenue = $7M` are not a conflict
  if the qualifier schema captures product line. If the qualifier is missing in one claim, the result
  is a possible conflict, not a confirmed one.

### When detection runs

Detection should run in three places:

1. **At extraction/normalization time** for the new assertion's block. This catches conflicts while
   the evidence is fresh and creates a K refresh trigger. The lookup is bounded by
   `(entity_id, attribute_id, period/qualifier block)`, not by corpus size.
2. **Periodic and event-driven backfills** after entity merges, attribute promotions, fiscal-calendar
   fixes, unit-normalization changes, or normalizer-version changes. These operations can move claims
   between blocks, so conflict membership must be recomputed.
3. **Query-time hydration**, but only as a presentation safeguard. Query-time should attach known
   conflict siblings and value groups; it should not be the primary detector because raw query-time
   detection cannot scan 10^8 claims or call an LLM on the hot path.

This matches the existing system philosophy: cheap-first write-side detection and no LLM calls in
core retrieval.

## Tracking option space

### Option A: store nothing, surface only at query/K time

This keeps the current D41 non-goal exactly as written. Claim rows remain immutable evidence, and
`claims_as_of` can retrieve assertions over a time interval.

Scores:

| Criterion | Score | Reason |
|---|---:|---|
| D2/D3 compatibility | 10 | No new fact layer, no claim supersession. |
| D6 validity discipline | 10 | No new validity state. |
| D41 evidence semantics | 10 | Claims remain pure evidence. |
| Scale | 6 | Storage is cheap, but reliable conflict grouping shifts to expensive query-time work. |
| Surface contradictions | 3 | Retrieval may return both sides, but it does not guarantee grouping or warning. |
| Agent safety | 3 | An agent can read one claim as truth unless every consumer implements its own caution. |
| Restatement handling | 2 | Later corrected values are just more claims; no structured restatement signal. |

This option is too weak. It satisfies the letter of "claims are evidence" but not the operational
requirement that contradictions are surfaced. "The other side was searchable somewhere" is not enough.

### Option B: lightweight conflict annotations over claim attribute assertions

This option stores structured attribute assertion sidecars plus conflict sets:

```
nonrel_conflict_sets
  conflict_set_id
  deployment_id
  subject_entity_id
  attribute_id
  conflict_key_json
  conflict_kind          -- value_conflict | date_conflict | restatement_candidate | ambiguous
  confidence
  detector_version
  created_at
  updated_at

nonrel_conflict_members
  conflict_set_id
  assertion_id
  claim_id
  value_cluster_id
  role                  -- side | compatible_refinement | restatement_of | ambiguous_member
```

The set has no verdict. It says "these claim-derived assertions occupy the same fact slot and contain
incompatible or potentially incompatible content." It does not say which content is true.

Scores:

| Criterion | Score | Reason |
|---|---:|---|
| D2/D3 compatibility | 8 | Adds structure around non-relational claims, but not a belief fact or supersession target. |
| D6 validity discipline | 9 | No current-belief validity; conflict state is an annotation, not a validity home. |
| D41 evidence semantics | 9 | Uses `claim_valid_*` as evidence and blocking input only. |
| Scale | 8 | Bounded block lookups; storage proportional to structured attribute assertions, not pairwise comparisons. |
| Surface contradictions | 9 | Retrieval can attach all sides by stable conflict-set membership. |
| Agent safety | 9 | API can mark evidence as conflicting and force consumers to see sibling claims. |
| Restatement handling | 6 | Can flag restatement candidates, but cannot provide E-plane supersession semantics. |

This is the recommended base design. It closes the retrieval safety gap without turning every literal
fact into a new adjudicated object.

### Option C: full proposition/attribute-fact layer

This creates canonical non-relational facts, for example:

```
attribute_facts
  fact_id
  subject_entity_id
  attribute_id
  qualifiers
  value
  valid_from/valid_until
  ingested_at/invalidated_at
  evidence_count
  contradiction_group

attribute_fact_evidence
attribute_fact_adjudications
```

This mirrors relations for literal and n-ary facts. It gives a real identity to "Acme FY2023 revenue"
and can close or supersede old values when a restatement arrives.

Scores:

| Criterion | Score | Reason |
|---|---:|---|
| D2/D3 compatibility | 4 | It preserves claim immutability but creates a second verdict layer beside relations. |
| D6 validity discipline | 5 | Can be made single-home per attribute fact, but validity now has two homes by fact class: relations and attribute facts. |
| D41 evidence semantics | 7 | Claims remain evidence, but D41 becomes input to a new adjudicator. |
| Scale | 4 | Requires attribute ontology, qualifiers, value normalization, adjudication, evidence joins, and review at relation-like scale. |
| Surface contradictions | 10 | Strongest option for presentation and audit. |
| Agent safety | 10 | Can answer current-value questions explicitly. |
| Restatement handling | 10 | Gives temporal restatement a real supersession mechanism. |

This is coherent but expensive. It is the right named upgrade when a deployment needs structured
current values for literal facts as a product capability. It is not the right answer to the narrower
requirement "do not let agents miss contradictions in non-relational evidence."

The danger is not only table count. The danger is semantic gravity: once `attribute_facts` exist,
users will ask them to do everything relations do. That means `contradiction_group`, bi-temporal
validity, review, confidence, deletion cascade, K refresh triggers, golden-set evaluation, and
rebuild behavior. Pretending this can be a small table is how D3's "absurd task" returns under a new
name.

### Option D: promote on demand to a relation

Some non-relational content should become relational when the ontology naturally supports it. If the
domain has real entities for "FY2023 annual report", "Acme founding event", "Series A round", or
"Product Atlas launch", then relations can connect Acme to those entities and inherit E3 machinery.
The D5 `other:` funnel is the correct governance path for new predicates.

Scores:

| Criterion | Score | Reason |
|---|---:|---|
| D2/D3 compatibility | 7 | Good when the promoted object is a real entity; bad when literals are forced into entities. |
| D6 validity discipline | 9 | Uses existing relation validity. |
| D41 evidence semantics | 8 | Claims remain evidence for promoted relations. |
| Scale | 7 | Works for selected high-value domains; does not cover the general case. |
| Surface contradictions | 5 | Only after promotion; misses conflicts in unpromoted attributes. |
| Agent safety | 5 | Better for modeled domains, unchanged elsewhere. |
| Restatement handling | 6 | Works if the restatement can be represented as a relation event; awkward for scalar values. |

This is not a general solution. Promoting "Acme FY2023 revenue was $5M" by creating `$5M` as an entity
or making time a Date node violates the spirit of D18. Promotion is appropriate when the object is
already a domain entity, not as a workaround for quantities.

## Recommendation

Adopt option B as the base design:

**Add a governed claim-attribute assertion index and non-relational conflict sets. Keep them
evidence-grain, append-only at the assertion level, and non-adjudicating at the conflict-set level.**

The recommendation has four binding rules.

1. **Detection is structured.** A non-relational conflict cannot be declared unless the subject entity,
   attribute, relevant qualifiers, value kind, and time semantics have been normalized.
2. **The conflict set is not a fact.** It exists to surface incompatible evidence. It has no current
   value, no validity window, and no supersession.
3. **Claims are never updated.** A later restatement creates a new claim and a new attribute assertion.
   The old assertion remains part of the evidence record.
4. **Current belief belongs in E3 relations where the fact is relational, or in K3 where the belief is
   compiled narrative.** If a deployment needs structured current values for non-relational facts, it
   must adopt the named Proposition Facts upgrade rather than laundering belief semantics into claims.

This is decisive because it separates two needs that are easy to conflate:

- "Do not hide conflicts" needs a conflict index.
- "Tell me the current true scalar value" needs a belief/adjudication layer.

The first is required by the existing contradiction-surfacing requirement. The second is a larger
product capability.

## Concrete mechanics

### Attribute assertion extraction

During E2/E3 normalization, every claim that does not yield a relation should still be tested for
structured non-relational assertions. The extractor is constrained by the attribute registry and can
emit `other:<freetext>` only when no active attribute fits.

Examples:

```
"Acme's FY2023 revenue was $5M."
  subject_entity_id = Acme
  attribute_id = fiscal_revenue
  claim_valid_kind = measurement_period
  claim_valid_from/until = FY2023 normalized interval
  qualifiers = {basis: unknown, geography: global, fiscal_calendar: Acme or unknown}
  value_kind = money
  normalized_value = {amount: 5000000, currency: USD}
  value_precision = rounded_or_unknown

"Acme was founded in 1998."
  subject_entity_id = Acme
  attribute_id = founded_date
  claim_valid_kind = event_time
  value_kind = date
  normalized_value = {from: 1998-01-01, until: 1998-12-31, precision: year}

"Acme was founded on 1998-04-12."
  same block as above
  normalized_value = {from: 1998-04-12, until: 1998-04-12, precision: day}
```

A claim that yields both relations and attributes can emit both. For example, "Alice joined Acme as
VP in March 2024 with a $200k salary" may produce a `works_for` relation and a salary attribute
assertion. This does not violate D2; D2 already allows one claim to yield several downstream facts or
none.

### Conflict set creation

For each new attribute assertion:

1. compute the block key according to the attribute's time semantics;
2. retrieve existing assertions in the same block;
3. normalize values into comparable ranges or classes;
4. apply the attribute's compatibility and conflict rules;
5. if incompatible value clusters exist, upsert a conflict set and membership rows;
6. enqueue K refresh and, if blast radius/confidence lands in the review band, enqueue D24 review.

High-volume blocks must be handled by aggregation. The detector should not compare every revenue
claim to every other revenue claim. It should group by normalized value cluster and source/time
metadata, then compare clusters.

### Conflict kinds

Use at least these conflict kinds:

- `value_conflict`: same entity, same attribute, same measurement/effective block, incompatible
  values.
- `event_time_conflict`: same entity and event-time attribute, incompatible asserted event dates.
- `temporal_overlap_conflict`: same state attribute, overlapping source-asserted validity windows,
  incompatible values.
- `restatement_candidate`: same block and incompatible value, with text/source cues that the later
  assertion corrects or restates the earlier one.
- `attribute_mapping_ambiguous`: candidate conflict depends on whether two labels are the same
  attribute; route to registry review instead of presenting as confirmed contradiction.
- `qualifier_ambiguous`: candidate conflict may disappear if missing qualifiers differ; present as
  possible conflict.

The detector should distinguish "confirmed conflict" from "possible conflict". Over-warning is better
than hiding contradictions, but marking every coarse/fine refinement as conflict will make agents and
humans ignore the signal.

### D24 review interaction

Non-relational conflict sets should use the review queue, but the review action must be carefully
scoped.

Review can decide:

- this is a real conflict;
- this is compatible refinement;
- this is not the same attribute;
- qualifiers differ;
- this is a restatement candidate;
- this should trigger attribute-registry promotion or alias mapping.

Review should not silently write "the true value is X" into the E-plane conflict set. If a human
decision is intended to become a current belief, it should update a K3 belief artifact, or, for a
deployment that has adopted Proposition Facts, write an adjudication there. Otherwise D6's "one home"
discipline is weakened by turning a review queue into an unacknowledged fact store.

### Temporal restatement semantics

Temporal restatement is the sharpest case:

```
2024 report: Acme FY2023 revenue was $5M.
2025 amended report: Acme FY2023 revenue was $5.2M.
```

In the recommended base design, this gets **conflict and restatement annotation**, not E-plane
supersession:

- both claims remain immutable;
- both attribute assertions remain immutable;
- the block has two incompatible value clusters;
- the later assertion can be marked `restatement_candidate` if source/text cues support it;
- retrieval presents the later correction and earlier value together;
- K3 may compile the belief: "Acme's FY2023 revenue is treated as $5.2M based on the 2025 amended
  report; the 2024 report said $5M."

There is no relation window to close because there is no relation. That is not a bug in the
recommended base design. It is the honest boundary between surfacing evidence conflict and adjudicating
current scalar facts.

If the system must answer a structured API question like "what is Acme's current adjudicated FY2023
revenue value?", the base design should return:

```
no_adjudicated_nonrelational_fact
conflicting_evidence_available = true
conflict_set_id = ...
value_groups = [$5M, $5.2M]
```

It should not synthesize `$5.2M` as an E-plane verdict just because it is newer.

## Query-system reaction

### Claim queries remain evidence-grain

`claims_as_of(t)` should continue to mean "what did sources assert held over T?" It must not become
"what was true at T?"

With the conflict index, `claims_as_of` composes as:

1. retrieve claims whose `claim_valid_*` overlaps T, plus lexical/semantic filters;
2. hydrate their `claim_attribute_assertions`;
3. for each attribute assertion, attach any `nonrel_conflict_set`;
4. include sibling claims from the same conflict set even if they are not top-k semantic hits;
5. group presentation by value cluster with source, asserted_at, world-time, precision, and weight.

The important step is number 4. If an agent asks "Acme FY2023 revenue", retrieval should not return
only the semantically closest claim. It should return the conflict cluster:

```
Entity: Acme
Attribute: fiscal_revenue
Period: FY2023
Evidence grain: claims, not current belief
Conflict: yes

Value group A: $5M
  claims: c123, c456
  sources: 2024 annual report, analyst note
  asserted_at: 2024...
  precision: rounded/unknown

Value group B: $5.2M
  claims: c789
  source: 2025 amended annual report
  asserted_at: 2025...
  annotation: restatement_candidate
```

### API fields agents need

Every claim-attribute evidence result should expose:

- `result_grain = claim_evidence`;
- `current_belief = false`;
- `subject_entity_id`;
- `attribute_id`;
- `attribute_label`;
- `claim_valid_from/until/precision/kind`;
- `normalized_value` and `value_text`;
- `value_precision`;
- `qualifiers`;
- `source_doc_id`, `claim_id`, `source_span`, `asserted_at`, `ingested_at`;
- `source_weight` or authority signal if available, clearly labeled as a ranking signal, not truth;
- `conflict_state = none | possible | confirmed`;
- `conflict_set_id`;
- `value_cluster_id`;
- `conflict_siblings_count`;
- `requires_belief_route = true` when a current-truth answer was requested.

For API calls that ask current-truth questions, the router should enforce:

- relational current belief routes to relations;
- K3 belief routes to K3 artifacts with evidence links;
- non-relational evidence without Proposition Facts returns no adjudicated fact and surfaces the
  conflict set.

This is the agent-safety rule from requirements_v3 applied to the new gap. The API must make the
danger machine-readable, not merely documented in prose.

### Ranking and presentation

Ranking can use recency, source authority, and evidence count, but presentation must not let those
signals look like adjudication. The UI/API can say:

- "newer source";
- "source marked authoritative";
- "more supporting claims";
- "amended report";

It must not say:

- "winner";
- "superseded";
- "current value";
- "true as of";

unless the answer comes from relations, K3 belief, or the Proposition Facts upgrade.

## K-plane interaction

The K plane is the right home for narrative handling of important non-relational conflicts. The E
plane should detect and surface; K should synthesize.

K3 already has the right shape: every belief links supporting and contradicting evidence. A
non-relational conflict set should trigger K refresh for affected entities/scopes. K3 can then write:

> Acme's FY2023 revenue is reported inconsistently. The 2024 annual report says $5M. A 2025 amended
> report says $5.2M and appears to restate the earlier figure. Treat $5.2M as the working value when a
> single value is required, but retain the $5M source as contradictory evidence.

That is a compiled belief artifact, not a claim update and not a relation window. It is allowed to be
narrative, qualified, and source-sensitive in a way the E-plane schema should not be.

K3 may choose a working value using recency, source authority, direct restatement language, or human
review. The rule is that it must cite both supporting and contradicting evidence. The system should
not bury that choice inside retrieval ranking.

## What to reject

Reject pure query-time detection. It is attractive because it adds no schema, but it fails at the
point of use. The query path has no cheap way to know that the missing sibling claim is the important
one, and D9 bars LLM calls on the core search path.

Reject ungoverned attribute keys. A free-text `attribute = "revenue"` field without registry
governance will fragment exactly like free-text predicates. It will create a false sense of safety
while missing `sales`, `net revenue`, and deployment-specific measures.

Reject Date nodes, Money nodes, and quantity entities as a generic fix. That erodes D18 and pollutes
P2 with pseudo-entities whose only purpose is to make literal facts look relational. Some domain
events should become entities; scalar values should not.

Reject claim-level supersession. Marking the 2024 `$5M` claim as superseded by the 2025 `$5.2M` claim
reintroduces D3's absurd task. It is still true that the 2024 source asserted `$5M`; the evidence
record must not be rewritten into a belief record.

Reject a hidden winner in conflict sets. A field like `preferred_assertion_id` inside the
non-relational conflict table would become an ungoverned current-belief authority. If the system picks
a winner, that decision belongs in K3 or in the explicit Proposition Facts upgrade.

## Named upgrade: Proposition Facts

The named upgrade is **Proposition Facts**: a relation-like E-plane layer for non-relational facts.
It is admitted when measured demand shows that K narrative plus conflict surfacing is insufficient,
for example:

- agents frequently need structured scalar current values through API calls;
- high-value domains have many restatements or corrections;
- human reviewers are repeatedly adjudicating the same attribute conflicts;
- K3 beliefs are being used as a de facto structured fact store.

Proposition Facts would include:

- canonical fact identity: `(subject_entity_id, attribute_id, qualifiers, period semantics)`;
- typed current/adjudicated value;
- evidence join to claims or claim-attribute assertions;
- contradiction groups;
- adjudication log;
- bi-temporal validity for the proposition fact;
- deletion and rebuild semantics;
- review queue integration;
- search labels and embeddings if needed.

This is a full sibling to relations, not a patch to claims. If adopted, the design should state that
validity has one home per fact class: relation validity for entity-entity facts, proposition-fact
validity for governed attribute facts, and claim-validity only as immutable source evidence. That is a
real amendment to D6/D3 wording and should be treated as such.

## Overall consequences

The minimal intervention is not free. It adds a new ontology surface, new normalization work, new
evaluation needs, and another class of review items. The attribute registry will have the same failure
modes as predicates: fragmentation if too loose, missed coverage if too strict, and painful splits if
prematurely broad labels become popular. The system should expect a promotion funnel, golden-set
measurement for common attributes, and backfills after registry changes.

The scale cost is manageable if the design stays block-based. At 10^7-10^8 claims, a sidecar table is
acceptable only if hot operations are keyed by `(entity_id, attribute_id, period/qualifiers)` and
conflict detection compares value clusters, not every pair of claims. High-cardinality attributes and
ambiguous qualifiers need caps and review routing.

The bigger risk is semantic drift. Once the system stores normalized attribute assertions, people will
want to ask them truth questions. The API must resist that. The conflict index is evidence
infrastructure. It is not the current value of anything.

This does pull the system slightly toward a second fact layer because it introduces canonical
attribute names and fact-like blocks. That is unavoidable if contradictions must be surfaced
reliably. The line that prevents erosion of D2 is: **no evidence collapse into a verdict, no
adjudicated value, no supersession, no graph projection as facts**. The moment the system needs those,
it should cross the line explicitly into Proposition Facts.

The K plane alone is not enough as the base answer. K is the right place to narrate conflicts and hold
qualified beliefs, but K cannot be the only detector. K refresh needs a trigger, and raw retrieval
needs machine-readable warnings before a K artifact exists. E-plane conflict detection supplies that
trigger and warning without making E-plane scalar beliefs.

The recommended intervention therefore honors all load-bearing decisions:

- D2 remains intact because claims and relations are still distinct, and many claims still produce no
  relation.
- D3 remains intact because claims are not superseded and no non-relational relation window is closed.
- D6 remains intact because no new current-belief validity home is added.
- D41 remains intact because `claim_valid_*` remains immutable source evidence and is used only for
  filtering/blocking.
- D5's governance lesson is extended to attributes, where the same fragmentation risk exists.
- D24 becomes useful beyond entity clusters by reviewing high-impact conflict groups.
- "Contradictions are surfaced, never silently resolved" becomes true for non-relational evidence,
  not just relations.

The decisive answer is: **build the conflict index, not the verdict layer; make query surfaces attach
all sides; let K3 write cited beliefs; reserve Proposition Facts for deployments that truly need
structured adjudicated scalar facts.**
