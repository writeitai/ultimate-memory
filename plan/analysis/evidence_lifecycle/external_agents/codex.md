# Evidence lifecycle under re-extraction and source versioning - Codex analysis

This analysis covers two coupled design gaps in `ugm`:

- **Problem A: re-extraction evidence inflation.** A prompt/model/extractor version bump
  reprocesses the same document and creates new `claim_id` values for the same source
  sentences. Because `relation_evidence` and `observation_evidence` are currently keyed by
  `(fact_id, claim_id)`, every extractor generation can add another supporting evidence row
  to the same relation or observation.
- **Problem B: watched-source document versioning.** A connector such as Google Drive may see
  the same logical document every hour. When the source is edited, the bytes change and the
  `content_hash` changes. The current schema has no explicit lineage that says "these content
  hashes are versions of the same external document."

The two problems have the same structural root: the design currently treats an extraction row
(`claim_id`) or a byte snapshot (`content_hash`) as if it were the unit of independent
testimony. It is not. A confidence signal should count independent current testimony from
sources, not extractor artifacts and not every version of a living source.

## 1. Problem anatomy

### Terms

A **claim** is an immutable natural-language assertion extracted from source text. It records
what a source appeared to assert and how the extractor grounded that assertion. Claims are
never superseded; this is D2/D3.

A **relation** is an entity-to-entity believed fact, such as `(Alice, works_for, Acme)`. A
**observation** is a believed value or statement about one entity, such as "Acme's headcount
is 600." Relations and observations are the rows whose validity windows can be capped,
invalidated, or marked as contradictory.

An **evidence row** currently links a claim to a relation or observation. It says that this
claim supports or contradicts that believed fact.

An **evidence basis** is the missing concept I recommend adding. It is the stable unit of
source testimony that a claim represents: "this logical source, in this current source
version, contains this source-local assertion." Multiple claim rows from different extractor
generations can point at the same evidence basis. Multiple versions of a watched document can
also carry the same evidence basis without creating new independent support.

### What `evidence_count` should mean

`evidence_count` should mean:

> the number of distinct, currently active evidence bases supporting this relation or
> observation.

That is deliberately not "number of claims," "number of extraction runs," "number of source
versions," or "number of times the sentence appears in an hourly poll." It is a current
testimony count. A static uploaded PDF contributes one current testimony basis until the
document is deleted or forgotten. A watched Google Doc contributes one current testimony
basis for a fact while the latest source version still asserts that fact. If the Google Doc is
edited hourly but keeps asserting the same fact, the count stays one.

The same rule applies to `contradict_count`: it counts distinct current contradictory
evidence bases, not contradictory claim rows.

This is still only a salience and corroboration signal. It does not prove truth. A future
"independent external evidence" score can refine it further by discounting same-origin,
system-generated, syndicated, or mirror sources, but the first necessary correction is to stop
counting extractor/version duplicates.

### Signals affected by the gap

The gap affects more than `relations.evidence_count`.

- **`relations.evidence_count` / `observations.evidence_count`:** inflate on extractor
  version bumps and on source version churn.
- **`relations.contradict_count` / `observations.contradict_count`:** suffer the same defect
  for contradictory evidence.
- **`confidence`:** any aggregate confidence that uses evidence count inherits the inflation.
- **K3 gating:** D47 says K3 selects settled evidence using `evidence_count >= N` and no live
  contradiction group. Inflated counts promote facts into the belief tier for the wrong
  reason.
- **Retrieval reranking:** D9-style reranking by evidence count over-ranks facts repeatedly
  extracted from one source.
- **Adjudication priority:** anything that chooses which facts need review or which
  contradictions matter based on support volume sees false salience.
- **P1 claim search:** re-extraction creates multiple near-identical claim vectors, so claim
  search returns extraction generations instead of diverse testimony.
- **K staleness and citations:** if K candidate sets and citations key off claim IDs, an
  extractor bump can make pages stale even when the evidence basis did not change.
- **P2 graph edge properties:** graph edges carry `evidence_count`; inflated counts leak into
  graph traversal and graph-assisted reranking.
- **D42 origin math:** system-generated re-ingestion and extractor replays corrupt the same
  signal in different ways. Origin and evidence-basis identity must meet before K3 confidence
  math is trustworthy.
- **Deletion and source edits:** deleting a source, hard-forgetting a version, and a watched
  source no longer asserting a sentence are different events. The current row model cannot
  express those differences cleanly.

## 2. Candidate designs for Problem A

### A1. Count only claims from the current extractor version

Rule: a claim contributes to `evidence_count` only if its `extractor_version` equals the
document's current extractor version.

Benefits:

- Minimal schema change.
- Keeps old claims immutable and audit-visible.
- Prevents old extractor generations from continuing to count after a full re-extraction.

Costs:

- It only solves extractor-version inflation, not document version churn.
- It assumes each document has one "current extractor version." That is awkward once E0/E1
  workers are independently versioned and chunks can be reused.
- It does not prevent duplicates within the same extractor generation.
- It does not solve P1 claim search pollution unless P1 also filters by current version.
- It makes a prompt/model rerun look like a replacement of testimony, even when the source
  basis is unchanged and only the extraction wording improved.

This is a useful emergency patch, but it is not the right conceptual model.

### A2. Count distinct documents per fact

Rule: `evidence_count` is `COUNT(DISTINCT doc_id)` per relation or observation and stance.
Evidence rows stay claim-grained for provenance, but counts collapse to one vote per document.

Benefits:

- Simple to explain.
- Stops extractor reruns from increasing the count if all claim generations share the same
  document ID.
- Also collapses repeated same-fact sentences inside one document.

Costs:

- It fails when `doc_id` means content snapshot rather than logical source lineage.
- It cannot handle watched-source versions unless document identity is fixed first.
- It loses useful provenance distinctions for one logical source that contains separate
  independently authored sections, appendices, or attached documents.
- It does not give K or P1 a stable key for "same assertion, better extraction."

This is close to the right direction but too coarse by itself.

### A3. Canonicalize claims by text and source span

Rule: compute a deterministic claim fingerprint from source span, normalized claim text, and
document content. Re-extraction reuses the existing claim row or links to it instead of
creating a new counting unit.

Benefits:

- Directly attacks duplicate claims and P1 pollution.
- Keeps `relation_evidence` close to today's claim-centered shape.
- Can be highly effective for exact reruns.

Costs:

- Claim text is an extractor output. Better prompts may rewrite the same source assertion in
  a better standalone form, changing the fingerprint even though the source basis is the same.
- Source spans move when conversion, OCR, or chunking changes.
- It does not model watched-source currentness. An unchanged sentence in a new source version
  is not a new independent source, but it is a new occurrence in the living source's history.
- Reusing claim rows across versions muddies `asserted_at` unless occurrences are modeled
  separately.

This is useful as one input to reconciliation, but not a sufficient identity model.

### A4. Add stable evidence bases and count those

Rule: create an `evidence_basis_id` for the stable source-local assertion that claim rows
represent. `relation_evidence` and `observation_evidence` key on `(fact_id,
evidence_basis_id)`, while a child table records all claim rows that represented that basis.

Benefits:

- Solves extractor reruns and source-version churn with the same mechanism.
- Preserves claim immutability: no claim is edited or superseded.
- Preserves replay discipline: extractor and adjudicator outputs remain append-only and
  version-stamped.
- Gives P1 and K a stable current-testimony key.
- Supports historical/audit retrieval because old claims and old occurrences remain
  queryable.

Costs:

- Adds a new reconciliation responsibility: the system must decide when two claims represent
  the same source-local assertion.
- Requires schema changes to evidence joins, claim indexing, K citations, and document
  versioning.
- Exact identity is easy; semantic equivalence under changed extraction wording needs a
  conservative reconciler and evaluation.

This is my recommended design.

## 3. Candidate designs for Problem B

### B1. Keep one document row per content hash, no lineage

Rule: every new `content_hash` is a new document. The current `UNIQUE(deployment_id,
content_hash)` remains the only identity.

Benefits:

- Minimal change.
- Matches immutable raw storage.
- Simple idempotency for exact re-ingest.

Costs:

- A watched Google Doc edited hourly becomes many unrelated documents.
- Evidence counts inflate unless separately collapsed by source.
- Retrieval cannot distinguish current source testimony from historical snapshots.
- P3 paths cannot stay stable across edits except by heuristic title matching.
- Deletion semantics are confused: deleting one version, deleting the living source, and
  deleting bytes for hard forget are different operations.

This design is not adequate for watched sources.

### B2. Keep one mutable row per source and overwrite latest content

Rule: the document row is the living source. On edit, update content hash, URIs, and derived
state in place.

Benefits:

- Natural "current document" lookup.
- Stable path and stable source identity.
- Easy to avoid current-count inflation.

Costs:

- Breaks the immutable snapshot discipline of D7/D37.
- Destroys historical retrieval unless old versions are stored elsewhere.
- Makes replay and audits fragile because a claim's source version can disappear under the
  same row.
- Makes hard forget and normal delete harder to reason about because old byte-bearing
  artifacts are not first-class rows.

This design violates too much of the existing architecture.

### B3. Add document lineage plus immutable version rows

Rule: a **document lineage** represents the logical source across time, keyed by connector
identity when available. A **document version** represents one immutable content snapshot
within that lineage, keyed by `content_hash` and connector revision metadata.

Benefits:

- Preserves immutable storage and replay.
- Gives watched sources stable identity.
- Makes current-vs-historical retrieval explicit.
- Gives P3 stable paths by lineage while allowing version-specific raw/artifact addresses.
- Gives evidence counting the right source identity: a living source contributes at most one
  current basis to a fact.

Costs:

- Requires schema surgery: `documents` must either become `document_versions` or gain a
  `doc_version_id`.
- Existing claim/chunk FKs need to point to the immutable version, while lineages are used for
  currentness and P3 stability.
- Requires workers to handle lineage current-pointer transitions.

This is also my recommended design.

### B4. Event-source all source changes

Rule: store connector events and reconstruct document state from event logs and content
objects.

Benefits:

- Excellent audit history.
- Captures renames, moves, ACL changes, revision metadata, and deletions precisely.
- Could support connector-specific replay.

Costs:

- Too much machinery for the core problem.
- Does not remove the need for immutable version rows; it only explains how they were
  observed.
- Connector event fidelity varies. Some systems provide revisions, some provide only polling
  snapshots.

Connector event logs are useful as an optional audit source, but they should not be the
primary document identity model.

## 4. Recommended design

### 4.1 Identity model

Use three identities, each with a different job.

1. **Content object:** immutable bytes, keyed by `content_hash`. This is the idempotency and
   blob reuse key.
2. **Document lineage:** the logical source over time, keyed by connector-native identity
   when present. For Google Drive this is the file ID plus deployment/connector account, not
   the title or path.
3. **Document version:** one observed immutable snapshot of a lineage, pointing at one
   content object.

For static uploads with no connector-native identity, the upload creates a lineage with one
current version. That version behaves as current until the lineage is deleted or forgotten.
For watched sources, the lineage's `current_version_id` moves as the connector observes new
versions.

Schema sketch:

```sql
CREATE TABLE content_objects (
  deployment_id   uuid NOT NULL,
  content_hash    text NOT NULL,
  byte_size       bigint,
  mime            text NOT NULL,
  raw_uri         text NOT NULL,
  first_seen_at   timestamptz NOT NULL DEFAULT now(),
  ref_count       bigint NOT NULL DEFAULT 0,
  PRIMARY KEY (deployment_id, content_hash)
);

CREATE TABLE document_lineages (
  doc_id          uuid PRIMARY KEY,  -- stable logical document identity
  deployment_id   uuid NOT NULL REFERENCES deployments,
  origin          document_origin NOT NULL, -- D42
  source_kind     text NOT NULL, -- google_drive, upload, email, github, ...
  source_ref      text,          -- connector-native stable ID; NULL only for source kinds without one
  source_uri      text,
  title           text,
  current_version_id uuid,
  first_seen_at   timestamptz NOT NULL DEFAULT now(),
  last_observed_at timestamptz,
  deleted_at      timestamptz,
  UNIQUE (deployment_id, source_kind, source_ref)
);

CREATE TABLE document_versions (
  doc_version_id  uuid PRIMARY KEY,
  deployment_id   uuid NOT NULL REFERENCES deployments,
  doc_id          uuid NOT NULL REFERENCES document_lineages(doc_id),
  content_hash    text NOT NULL,
  source_version_ref text,       -- connector revision/etag/generation if available
  predecessor_version_id uuid,
  observed_at     timestamptz NOT NULL DEFAULT now(),
  source_modified_at timestamptz,
  published_at    timestamptz,
  is_current      boolean NOT NULL DEFAULT false,
  markdown_uri    text,
  pageindex_uri   text,
  conversion_uri  text,
  meta_uri        text,
  converter_name  text,
  converter_version text,
  structurer_name text,
  structurer_version text,
  pageindex_hash  text,
  placement_version text,
  section_index_version text,
  crossref_version text,
  status          document_status NOT NULL DEFAULT 'ingesting',
  deleted_at      timestamptz,
  UNIQUE (deployment_id, doc_id, content_hash),
  UNIQUE (deployment_id, doc_id, source_version_ref),
  FOREIGN KEY (deployment_id, content_hash)
    REFERENCES content_objects(deployment_id, content_hash)
);
```

The current `documents` table is doing both lineage and version work. The clean target is to
split it. If the name `documents` is retained for compatibility, it should mean
`document_versions`; the stable source identity must still be a separate lineage row.

GCS paths should use the stable lineage plus the content hash:

```text
gs://...-raw/<doc_id>/<content_hash>/original.<ext>
gs://...-artifacts/<doc_id>/<content_hash>/document.md
```

This matches the existing path shape and makes the implication real: many content hashes can
belong under one `doc_id`.

Chunks, sections, claims, and extraction decisions should point to `doc_version_id` because
they derive from one immutable content snapshot. They may denormalize `doc_id` for routing and
counting.

### 4.2 Evidence basis model

Add a stable evidence-basis layer between claims and fact evidence joins.

Schema sketch:

```sql
CREATE TABLE evidence_bases (
  evidence_basis_id uuid PRIMARY KEY,
  deployment_id     uuid NOT NULL REFERENCES deployments,
  doc_id            uuid NOT NULL REFERENCES document_lineages(doc_id),
  origin            document_origin NOT NULL,
  source_authority_key text, -- optional future D42/D51 independence grouping
  basis_key         text NOT NULL,
  assertion_fingerprint text NOT NULL,
  source_span_fingerprint text NOT NULL,
  first_doc_version_id uuid NOT NULL,
  current_doc_version_id uuid,
  current_from     timestamptz,
  current_until    timestamptz,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (deployment_id, doc_id, basis_key)
);

CREATE TABLE evidence_basis_occurrences (
  occurrence_id     uuid PRIMARY KEY,
  deployment_id     uuid NOT NULL REFERENCES deployments,
  evidence_basis_id uuid NOT NULL REFERENCES evidence_bases(evidence_basis_id),
  doc_version_id    uuid NOT NULL REFERENCES document_versions(doc_version_id),
  chunk_id          uuid,
  section_id        uuid,
  char_start        integer,
  char_end          integer,
  source_span_hash  text NOT NULL,
  asserted_at       timestamptz, -- assertion event for this source version
  observed_at       timestamptz NOT NULL,
  UNIQUE (deployment_id, evidence_basis_id, doc_version_id, chunk_id, char_start, char_end)
);
```

`basis_key` is deterministic when possible and conservative when not. It should combine:

- the document lineage (`doc_id`),
- a source-local anchor such as a converted block ID, section path, occurrence ordinal, and
  normalized source-span hash,
- an atomic assertion fingerprint derived from the decontextualized claim text and D41
  asserted-validity fields.

The key should not be only `claim_text`, because improved extraction wording should not create
new independent testimony. It should not be only offsets, because conversion and chunking
versions can move offsets. Exact matches should be automatic. Near matches should go through a
small conservative reconciler whose failure mode is duplicate evidence bases, not accidental
merging.

Claims then gain an `evidence_basis_id`:

```sql
ALTER TABLE claims ADD COLUMN evidence_basis_id uuid; -- logical FK
ALTER TABLE claims ADD COLUMN doc_version_id uuid;    -- immutable source snapshot
ALTER TABLE claims ADD COLUMN extraction_input_hash text;
```

`claims.asserted_at` can remain as the assertion event for the claim row's source version.
For reused unchanged content across later source versions, the per-version assertion event
lives on `evidence_basis_occurrences.asserted_at`. A `claims_as_of(t)` recipe should use the
occurrence table when the question is about what the living source asserted at a particular
source version time.

### 4.3 Evidence joins and counting rule

Change relation and observation evidence to key on `evidence_basis_id` for counting, while
keeping claim rows as provenance.

```sql
CREATE TABLE relation_evidence (
  deployment_id     uuid NOT NULL,
  relation_id       uuid NOT NULL,
  evidence_basis_id uuid NOT NULL,
  stance            evidence_stance NOT NULL,
  representative_claim_id uuid,
  normalizer_version text NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (relation_id, evidence_basis_id)
) PARTITION BY HASH (relation_id);

CREATE TABLE relation_evidence_claims (
  relation_id       uuid NOT NULL,
  evidence_basis_id uuid NOT NULL,
  claim_id          uuid NOT NULL,
  created_at        timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (relation_id, evidence_basis_id, claim_id)
);
```

Mirror the same shape for `observation_evidence`.

Then define the cached counts as:

```sql
-- supports
COUNT(DISTINCT re.evidence_basis_id)
WHERE re.stance = 'supports'
  AND eb.current_until IS NULL
  AND dl.deleted_at IS NULL
  AND dv.deleted_at IS NULL

-- contradicts
COUNT(DISTINCT re.evidence_basis_id)
WHERE re.stance = 'contradicts'
  AND eb.current_until IS NULL
  AND dl.deleted_at IS NULL
  AND dv.deleted_at IS NULL
```

If retaining exact historical counts is useful, add separate caches:

- `current_evidence_count` (the headline count; can keep the existing column name
  `evidence_count`),
- `historical_evidence_count` (all non-forgotten evidence bases ever linked),
- `raw_claim_count` (audit/debug only),
- `external_evidence_count` (future D42 refinement: current bases with external origin and
  independent-source grouping).

The current design's `evidence_count` column should become the current-basis count. K3 and
reranking should use that number, not raw claim rows.

### 4.4 Re-extraction reconciliation flow

When an extractor version changes for an existing document version:

1. Build the normal E2 context bundle and compute `extraction_input_hash`.
2. For each accepted claim, compute a candidate `basis_key`.
3. If the same source-local assertion already has an evidence basis, insert a new immutable
   claim row pointing to that basis. Do not create a new counting unit.
4. If the claim is genuinely new, create a new evidence basis and an occurrence for the
   document version.
5. Normalize the claim to relations and/or observations.
6. Upsert evidence by `(relation_id, evidence_basis_id)` or `(observation_id,
   evidence_basis_id)`. Insert the claim row into the provenance child table.
7. Choose a representative claim for P1 and hydration. Prefer the newest successful extractor
   version unless the claim is flagged or fails audit.
8. Recompute counts from current evidence bases. A pure extractor rerun of the same source
   assertion changes no count.
9. Emit a K `evidence_changed` event only if the basis set, stance, representative text used
   for retrieval, relation/observation mapping, validity fingerprint, or contradiction state
   changed. A new claim ID alone is not a K trigger.

This preserves D33: the extractor's decisions are still append-only and version-stamped. It
also preserves D3: old claims remain true records of what the source extraction asserted. They
just are not independent evidence bases.

### 4.5 Watched-source version flow

For an hourly connector:

1. Poll connector metadata. If the connector revision/etag/modified timestamp is unchanged,
   do nothing.
2. If metadata changed, fetch/export bytes and compute `content_hash`.
3. If `(deployment_id, content_hash)` already exists in `content_objects`, reuse raw and
   artifact references where the processing versions match. Create a new `document_versions`
   row for the lineage if this source revision has not been recorded.
4. If the bytes are new, store the content object and run E0 conversion/structure for this
   version.
5. Chunk by content-addressed units. Each chunk gets a `chunk_content_hash` and an
   `extraction_input_hash` covering the target text plus the context that can affect E2:
   header metadata, published/source-modified date, section path and summary, neighbor chunk
   hashes, context prefix, entity hints, and extractor version.
6. Reuse unchanged chunks and unchanged extraction inputs. Do not call the extractor for a
   chunk whose `extraction_input_hash` already has accepted claims and decisions.
7. For changed extraction inputs, run E2 normally and reconcile evidence bases.
8. Compare the previous current version's evidence bases with the new version's evidence
   bases:
   - basis still present: update `current_doc_version_id`, add an occurrence, keep count
     unchanged;
   - basis newly present: create/link it, increment affected current counts;
   - basis absent from the new current version: set `current_until` to the new version's
     `observed_at`, decrement affected current counts.
9. Move the lineage `current_version_id` to the new version in the same transaction that
   closes/opens evidence-basis currentness.
10. Emit K events for added, removed-current, or state-changed evidence bases. The payload
    should carry evidence basis IDs and affected relation/observation IDs, not only claim IDs.

### 4.6 Changed, unchanged, and removed content semantics

**Unchanged content inside a new document version** is not new independent evidence. It is the
same living source continuing to carry the same assertion. It may add a new occurrence with a
new `asserted_at`/`observed_at`, but `evidence_count` stays unchanged.

**Changed content that asserts a new fact** creates a new current evidence basis and can add a
new relation/observation or new evidence on an existing one.

**Changed content that asserts a contradictory fact** creates a new contradictory or
superseding basis and goes through the existing relation/observation adjudication cascade.
That is real testimony, not a version artifact.

**Removed content** closes the evidence basis's currentness for that lineage. Absence is not a
retraction. It should not by itself create a contradictory claim, cap a relation's valid-time,
or invalidate a relation as "wrong." It should reduce current support and trigger K because a
page's ground may have moved.

A source can retract only by asserting a retraction or correction. That retraction is a new
claim and should be normalized/adjudicated like any other claim.

### 4.7 Snapshot vs living source retrieval

Retrieval should expose the identity regime explicitly:

- **Current testimony (default for watched lineages):** use only evidence bases whose lineage
  current version still contains the assertion.
- **Snapshot testimony:** use the evidence bases present in a specific `doc_version_id`.
- **Historical testimony as of time T:** for each lineage, use the version current at T and
  evidence bases present in that version.
- **All archival testimony:** include every non-forgotten occurrence, useful for audit and
  source history, not for current belief confidence.

Static uploads are simple: their only version is current until deletion. A watched document
is a living source: its current version is the default; older versions require an explicit
historical query.

Current-belief recipes over relations and observations should continue to hydrate from live
Postgres, but they also need to expose evidence currency. A live relation with zero current
support is not the same as an invalidated relation; it is a historical or unsupported-current
belief. It should not pass K3 gating.

### 4.8 P1 claim search

P1 should not index every claim generation into the default claim-search channel. It should
have two modes:

- **Default claim search:** one representative claim per current evidence basis, filtered to
  current testimony unless the recipe asks otherwise.
- **Audit claim search:** all claim rows, including old extractor generations and historical
  source versions.

The representative can change when a better extractor version produces a clearer grounded
claim. Changing the representative may trigger re-embedding and maybe K if cited prose depends
on the claim text, but it does not change `evidence_count`.

### 4.9 K-plane interactions

K inputs and citations should use stable evidence identifiers.

Changes:

- Add `evidence_basis_id` as a legal target in `knowledge_artifact_evidence`, or make
  claim-target citations normalize to an evidence basis internally.
- Compute compiled-page `inputs_hash` from relation/observation IDs plus evidence-basis
  currentness and validity fingerprints, not from raw claim IDs.
- Treat these as evidence changes:
  - evidence basis became current for a fact,
  - evidence basis stopped being current,
  - stance changed,
  - relation/observation validity or contradiction fingerprint changed,
  - representative claim text changed enough to affect what a page cited.
- Do not treat "new claim row for same evidence basis" as an evidence change by itself.

This keeps K debounced and evidence-gated without making every extractor upgrade a
repo-wide stale storm.

### 4.10 P3 path stability

P3 should use lineage identity for stable browse paths. A generated stub at a stable path
points to the current document version:

```yaml
doc_id: <lineage id>
doc_version_id: <current version id>
content_hash: <current content hash>
artifact_uri: gs://...-artifacts/<doc_id>/<content_hash>/document.md
source_ref: google-drive:<file id>
observed_at: ...
```

Historical versions can be exposed under a generated `_versions/` subtree or through the API.
The default path should not churn every time a watched source edits its bytes.

### 4.11 Deletion and forget

Versioned documents need three deletion operations.

1. **Delete one version:** remove that immutable version from current/historical retrieval,
   purge bytes if no other row references the same content object, and remove or tombstone
   occurrences tied only to that version. If it was not current, current counts usually do not
   change.
2. **Delete a lineage:** close all current evidence bases for that source, tombstone the
   lineage, and remove it from P3. This is the watched-source equivalent of removing the
   document.
3. **Hard forget:** purge source bytes and derived text for all selected versions/lineages,
   delete or scrub claims and occurrences, recompute counts, and trigger K redaction exactly
   as the current deletion design requires.

Hard forget removes evidence. Source-version removal merely makes testimony no longer
current unless the old version is also purged.

## 5. Efficiency path for hourly watched corpora

The system cannot generally avoid all conversion for changed bytes, because it must know what
changed and conversion is the operation that maps bytes to text, blocks, offsets, and media.
But it can avoid paying full conversion plus full extraction for every hourly edit.

Efficiency should work at these levels:

1. **Connector metadata no-op:** unchanged revision/etag means no byte fetch.
2. **Content-object reuse:** if bytes hash to an existing `content_hash`, create a version row
   and reuse all content artifacts.
3. **Conversion artifact reuse:** if the same content object was already converted with the
   same converter version, reuse `document.md`, `conversion.json`, media, and costs.
4. **Chunk content-addressing:** after conversion, compute stable chunk/block hashes. Reuse
   chunk embeddings and chunk metadata for unchanged chunks.
5. **Extraction input-addressing:** E2 idempotency should key on `extraction_input_hash +
   extractor_version`, not just document-level `content_hash + extractor_version`. The input
   hash includes target chunk text plus all context that could change the claim.
6. **Evidence-basis reconciliation:** unchanged source-local assertions map to existing
   evidence bases, so E3 does not create new countable support.
7. **K delta routing:** emit changes only for currentness/state deltas, not for every version
   row or cloned claim.

This means an hourly edit to a 100-page Google Doc that changes one paragraph pays for:

- one fetch/export,
- conversion sufficient to produce the new Markdown/offset map,
- chunk hashing and diffing,
- extraction for the changed chunk and any chunks whose context bundle changed,
- evidence reconciliation for changed bases,
- K routing for affected facts only.

It does not pay to re-extract unchanged chunks or recompile every page touched by historical
claim IDs.

## 6. Coupling and genuine semantic differences

### One mechanism solves the shared part

Both problems are cases where the evidence basis of a document changed:

- In re-extraction, the source basis did not change, but the extractor produced a new claim
  representation.
- In source versioning, the living source's current basis set may have stayed the same,
  changed, gained assertions, or lost assertions.

The shared mechanism is the evidence-basis lifecycle:

- claims are immutable representations of a basis,
- occurrences record where and when a basis appeared in source versions,
- evidence joins count bases,
- currentness says whether a living source's latest version still carries the basis.

### Where the semantics differ

The difference is epistemic.

**Same-content re-transcription** is not new testimony. It is a new extraction artifact. The
only things that should change are extraction audit state, representative claim text,
embedding quality, and possibly fact mapping if the old extractor missed or mis-normalized
something.

**New source testimony** can be real evidence. If a watched source adds a sentence, removes a
sentence, or changes a value, the current testimony basis of that source changed. That should
affect current counts, K staleness, and retrieval freshness. But even here, the source lineage
still contributes at most one current support unit per fact. An hourly edited document does
not become 24 independent witnesses per day.

## 7. Interactions with existing decisions

### What stays intact

- **D2 claims/relations split:** preserved. Claims remain natural-language evidence records;
  relations/observations remain believed facts.
- **D3 claim immutability and relation-level supersession:** preserved. Evidence-basis
  currentness is not claim supersession and not relation validity.
- **D7 rebuild/replay discipline:** preserved. Evidence-basis reconciliation and K routing
  are durable state, not hidden session behavior.
- **D12 idempotency:** refined from document-level content hash to the correct target level:
  content objects for bytes, document versions for snapshots, extraction inputs for chunks,
  and evidence bases for testimony.
- **D25 no value gate:** preserved. This design does not skip extraction for low-value
  content; it reuses unchanged content-addressed work.
- **D33 extraction decision ledger:** preserved. New claim rows and decision rows remain
  append-only and version-stamped.
- **D37 E0 storage split:** preserved. Bodies stay in GCS; Postgres stores identity,
  currentness, hashes, URIs, and compact metadata.
- **D41 claim asserted validity:** preserved, with one refinement: version-specific assertion
  events for reused evidence bases live on occurrences.
- **D42 document origin:** becomes more useful. Origin should be copied from lineage to
  evidence basis so current counts can later be split into external/system-generated and
  independent/non-independent counts.
- **D43 observations:** mirror the same evidence-basis and counting changes as relations.
- **D45-D51 K/retrieval:** strengthened. K staleness and retrieval freshness become keyed to
  stable evidence bases and currentness fingerprints.

### What is refined

- The `documents` table should no longer be the sole identity for both source lineage and
  immutable content version.
- `UNIQUE(deployment_id, content_hash)` should move to a `content_objects` table. Document
  versions reference content objects; multiple lineages may point at the same content object
  without reprocessing bytes.
- `relation_evidence` and `observation_evidence` should enforce evidence-once on
  `(fact_id, evidence_basis_id)`, not `(fact_id, claim_id)`.
- K citations should be able to target evidence bases, or claim citations should normalize to
  evidence bases for staleness and count purposes.
- The deletion rule "zero evidence retires a relation" needs a distinction between "no
  retained evidence exists" and "no current living-source evidence exists." Hard deletion or
  forget can retire unsupported facts. A watched source merely removing a sentence should
  close current testimony, not assert falsity.

### What would break if left unchanged

- K3 thresholds become meaningless after extractor upgrades.
- P1 claim search becomes dominated by duplicate extraction generations.
- Watched documents become evidence multipliers.
- P3 paths either churn with content hashes or hide the fact that multiple versions exist.
- Historical retrieval cannot answer which version of a living source asserted a claim.
- Deletion and absence semantics collapse into one operation.

## 8. Failure modes of this recommendation

1. **False merge of evidence bases.** If the reconciler merges two distinct assertions into
   one basis, evidence is undercounted and provenance is confusing. The mitigation is a
   conservative merge policy: exact keys merge automatically; semantic merges require high
   confidence and leave an audit row; uncertain cases create duplicate bases.

2. **False split of evidence bases.** If the reconciler fails to match the same assertion
   across extractor versions or document versions, counts can still inflate. The mitigation is
   metrics: duplicate-basis rate on a golden set, especially under extractor version bumps and
   conversion/chunker changes.

3. **Basis keys are too span-sensitive.** OCR or converter changes can move offsets and break
   matching. The key must include text hashes and logical block identity, not only character
   offsets.

4. **Basis keys are too text-sensitive.** Better decontextualization can change claim text.
   The assertion fingerprint should include source span and structured normalized fields, not
   only the final claim sentence.

5. **Currentness bugs are high impact.** Moving a lineage current pointer and closing/adding
   evidence bases must be transactional. Partial updates would make retrieval and K disagree.

6. **Occurrence volume may grow quickly.** An hourly watched document with unchanged content
   can create many occurrences if every poll is recorded as a version. The connector should
   create a new version only when connector revision or bytes change, not every poll.

7. **K citation migration is disruptive.** Existing K citation schema targets claims,
   relations, or documents. Adding evidence bases is a real schema/API change. Without it, K
   can still normalize claim citations internally, but the model is less clear.

8. **"Current support" may be mistaken for truth.** A relation with low or zero current
   support might still be historically true. Retrieval envelopes must label the testimony
   regime instead of silently dropping history.

9. **Source lineage identity can be wrong.** Connector-native IDs are strong for Google Drive
   but weaker for copied files, exports, email attachments, or scraped URLs. The design needs
   source-kind-specific identity rules and tests.

10. **Independent evidence remains unsolved.** Counting current source lineages is better than
   counting claims, but it still does not prove independent corroboration. Syndicated copies,
   system-originated echoes, and mirrored files need the later D42 independence math.

## 9. Open questions and spikes

1. **Evidence-basis key quality.** Build a golden set with extractor version bumps,
   converter/chunker changes, repeated same-sentence assertions, and edited watched docs.
   Measure false merge and false split rates.

2. **Chunk-level reuse hit rate.** On a real Google Drive corpus, measure how often hourly
   edits change only a small fraction of extraction inputs.

3. **Conversion cost floor.** For each connector/source type, measure how much work is
   unavoidable before chunk hashes can be compared. Google Docs exports, PDFs, and office
   files may have very different floors.

4. **Occurrence retention policy.** Decide whether every content-changing version is retained
   forever, compacted, or governed by source-specific retention. Hard forget must still erase
   selected source-bearing text.

5. **P1 indexing policy.** Validate that representative-only default claim search improves
   diversity without hiding useful alternate phrasings. Audit search can remain exhaustive.

6. **K citation target migration.** Decide whether `knowledge_artifact_evidence` gets an
   `evidence_basis_id` column or whether claim citations remain externally visible while
   staleness normalizes them internally.

7. **Zero-current-support retrieval policy.** Decide how default current-belief recipes treat
   relations/observations that are still valid-time live but have no current evidence bases.
   My recommendation is: not K3-eligible, shown only with an explicit unsupported/historical
   freshness marker unless a snapshot/historical recipe asks for it.

8. **Origin and independence.** Define the first consumer of D42: `external_evidence_count`
   or `independent_external_evidence_count`. The evidence-basis table is the right place to
   carry the origin and future source-authority grouping.

9. **Deletion semantics tests.** Test version delete, lineage delete, normal delete, and hard
   forget against relations, observations, P1, P2, P3, and K citations.

10. **Connector identity rules.** For each watched source type, specify the stable
    `source_ref`, revision marker, rename/move semantics, copy/fork semantics, and deletion
    detection.

## Bottom line

The system needs a stable testimony identity between immutable claims and relation/observation
evidence. `evidence_count` should count current evidence bases, not claim rows. Document
sources need lineages and immutable versions so current testimony can be distinguished from
historical snapshots.

This one mechanism solves both inflation classes without weakening claim immutability or
replay-from-storage. Re-extraction creates new immutable claim rows on the same basis. Source
versioning creates, carries forward, or closes evidence bases as the living source changes.
Only the latter is a real change in current testimony.
