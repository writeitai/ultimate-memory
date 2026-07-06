# E0 — Files / Document Layer + the Corpus Filesystem (P3)

How a raw input file becomes a **structured document** (E0), and how documents are organized into
a **mountable corpus filesystem** that agents browse (P3, a projection). Decisions **D36–D40**.
Companion working analysis: `_feature_planning/e0/` (Claude + Codex). Numbers/choices here are
starting points to measure, not committed constants (CLAUDE.md).

## 1. Where this sits

E0 is the **document layer** of plane E. Its product is a *structured document*: the original
bytes, a clean Markdown rendering, a section tree, and cross-references — everything E1 (chunking)
and E2 (claim extraction) need. E0 is not a single worker; it is a short chain of **idempotent
sub-workers**, because document ingestion is genuinely several distinct, separately-failing jobs:

```
ingest ──► convert ──► structure ──► crossref
(store raw  (raw → md,   (PageIndex     (citations /
 + hash)    OCR/logic)   tree + roles    document links)
                         + placement)
```

These are *sub-workers of E0*, not new top-level stages: **the E-numbers name product layers**
(files → chunks → claims → relations), and PageIndex structure is metadata *about the document*
(before chunking), so it belongs to E0. We deliberately do **not** renumber E1→E2→E3 to give
structuring its own number — that's churn across every doc for no architectural gain (D36). The
complexity is handled by *decomposition into sub-workers*, each separately idempotent (on
`content_hash + that sub-worker's version`, D12) and separately observable.

## 2. Storage layout — GCS holds bodies, Postgres holds the index

Two buckets per deployment (storage is per-deployment, like entity spaces, D16):

- **raw** — `gs://ugm-<dep>-raw/<doc_id>/<content_hash>/original.<ext>` — immutable source-of-truth
  bytes (D1). Strict per-deployment IAM. **Mounted read-only, but off the navigation path**
  (D51): P3 and the Markdown never *promote* raw — stubs and `document.md` frontmatter carry an
  explicit raw pointer, so reaching an original is always a deliberate act (following a link),
  never a browse default. The point is whole-file media: for a video, an MP3, a photo *input*,
  the original **is** the artifact a multimodal harness needs — conversion yields only a lossy
  transcript/description. Three guardrails replace the old never-mounted rule: (1) **storage
  class routes by mime** (per-deployment config, like the D38 converter router): media likely
  to be read by agents (video/audio/images) → standard/nearline; text/office originals kept
  only for audit and re-conversion → archive (this kills the grep-the-archive cost bug at the
  source); (2) **data-access audit logging on the bucket is mandatory** — the audit property
  of the old rule came from logging, not from unmountedness, and a gcsfuse read is a GCS read;
  (3) originals may carry what conversion strips (EXIF, tracked changes, embedded metadata) —
  acceptable because a deployment is **one trust domain** (D50): every agent that reaches the
  mount is trusted with the deployment's content; data with a different trust boundary belongs
  in a separate deployment, never behind an in-library filter.
- **artifacts** — `gs://ugm-<dep>-artifacts/<doc_id>/<content_hash>/` holding `document.md`,
  `pageindex.json`, `conversion.json` (blocks + offsets), `meta.json`, and **`media/`** — the
  document's *derived* media: figures extracted from documents, thumbnails, transcripts,
  referenced from `document.md` by relative links. Standard storage. This is the per-document
  material an agent *reads*; it is reachable from the corpus filesystem (§6). Media matters
  because conversion is lossy exactly where a source is visual: agents are pointed
  **Markdown-first**, but a multimodal harness must be able to open the referenced image
  directly from the browse path. **Whole-file media originals** (a video, an MP3, a photo
  input) are *not* duplicated into `media/` — they are served from the raw mount (above) via
  the explicit raw pointer; `media/` holds only what conversion *derived*.

(`content_hash` = sha256 of the raw bytes — the single canonical byte identity, used in both the
path and the `documents` row.)

Canonical objects are **ID-addressed** (`doc_id` + `content_hash`), never title-addressed — titles
change, collide, and contain hostile characters. Human-readable names live only in the corpus
filesystem projection (§6), which points back at these stable paths.

**The Postgres / GCS split (D37).** Postgres is the E-plane *ledger*; GCS is the *blob store*. The
rule is precise:

> **Postgres never stores document *body* text or Markdown bodies. It stores compact, query-critical
> metadata** — document identity, versions, processing state, artifact URIs, hashes, costs, and the
> *section index* (titles, paths, roles, spans, summaries). Bodies live in GCS.

This keeps Postgres lean (1M document bodies would bloat it for nothing) and puts the text where it
belongs — in the mountable artifact store. `documents`:

```
documents(
  doc_id, deployment, content_hash,                -- sha256(raw bytes) = idempotency key (D12)
  UNIQUE(deployment, content_hash),                -- per-deployment; never dedup across deployments
  title, source, mime, byte_size,
  raw_uri, markdown_uri, pageindex_uri,
  converter_name, converter_version,               -- conversion provenance
  structurer_name, structurer_version, structurer_model, structurer_prompt_version,
  pageindex_hash, placement_version, section_index_version,   -- structure provenance (LLM-derived)
  status, ingested_at, updated_at)
```

PageIndex, summaries, and placement are **LLM-derived, non-deterministic** E0 state, so every
producing step is **versioned** (`structurer_*`, `placement_version`) and its output persisted. Like
every non-deterministic stage (D7), structure is **replayed from stored state** on rebuild and only
re-run on a version change; downstream E1/E2/P3 invalidation keys include `structure`/`converter`
versions, so a converter or structurer bump reprocesses exactly the affected documents.

Re-ingesting an identical file is a `content_hash` no-op (this is the *only* surviving "dedup" — as
idempotency, never a value tier, per D25).

**Deletion / forget (cascade).** Removing a document hard-deletes its **raw + artifacts** objects in
GCS and its Postgres rows (`documents`, `document_sections`) and cascades downstream like any input
removal (chunks → claims → relations). **P3 cascades for free** — it's a projection, so the document
simply isn't materialized on the next rebuild; nothing to delete there. A tombstone signal also reaches the K layer (per the deletion-cascade requirement). This satisfies the
deletion/forget requirement end-to-end (incl. GDPR-style hard delete of the original bytes).

## 3. The conversion module (raw → Markdown) — D38

A **configurable, pluggable** converter — the boundary is library-shaped and reusable; its quality
gates everything downstream:

- **Interface:** `convert(bytes, mime, hints) -> { markdown, blocks[], media[] }`, where `blocks`
  carry **page + character offsets back to the source**, and `media` carries the extracted
  images (id, bytes, page/position, caption if any) that land in the artifact `media/` folder
  and are linked from the Markdown. Offsets are load-bearing: E2 grounding (D32) needs verbatim
  `source_span`s, and chunking + PageIndex need positions.
- **Router by input type** (per-deployment config): digital PDF → direct text extraction; scanned /
  complex PDF + images → **OCR** (e.g. Mistral OCR / docling / marker); office / html / email →
  **markitdown**; plain text → passthrough. (This generalizes the common practice of *Mistral OCR for
  PDFs, markitdown for the rest* into a routing table.)
- **Versioned** (`converter_version`): a converter or routing change re-converts the affected docs (a
  batch keyed by version), which rebuilds everything downstream — the D7 rebuildability discipline
  applied to the foundation.

Output Markdown → artifacts bucket; `blocks` → `conversion.json`; Postgres gets only the URIs +
`converter_version`.

## 4. PageIndex — per-document structure — D39

**What PageIndex is** (verified from the tool): a per-document hierarchical *table-of-contents tree*
(`node_id`, `title`, `summary`, nested `nodes`, page/char spans). It is marketed as a vectorless,
reasoning-based retrieval system; **for us it is structure, not a retrieval engine** — we keep the
chunk + embed + graph hybrid (D8/D9). We use its **tree + section roles + spans** to:

- give E1 **section-aware chunk boundaries** (never split mid-section; one chunk = one topic),
- give E2 the **section path/role signal** it consumes (D25/D31 — Selection drops
  references/boilerplate at proposition grain),
- carry **per-section summaries** (kept — see below), and
- carry a **placement hint** for the corpus filesystem (§6).

`role` is a small enum (extensible): `body, abstract, introduction, results, methods, discussion,
conclusion, references, appendix, table, figure_caption, nav, boilerplate, legal`. The structurer
assigns it; E2 uses it to drop low-value roles at proposition grain.

**Every document gets a section structure — unconditionally.** The *output contract* is that every
document has `document_sections` rows; whether the expensive PageIndex *tool* runs is an
implementation choice, not a contract gap. A short/simple document gets a **single synthetic root
section** (full-document span, `role=body`, a one-line summary, root path) — so E1/E2/P3 always have
a path/role to read.

**Where it lives — both, by role:**
- **`pageindex.json` sidecar** in the artifacts bucket — the reproducible, mountable artifact (the
  "JSON next to the Markdown"), and
- **Postgres `document_sections`** — the queryable index, because E1/E2 query path/role per chunk and
  must not re-parse JSON each time:
  ```
  document_sections(
    section_id, doc_id, parent_section_id, node_path,    -- e.g. '0.2.1'
    title, role, char_start, char_end, ordinal,
    summary, placement_path, structurer_version)
  ```

**Summaries: kept** (not dropped). They are per-*section* (cheap, not per-chunk), and they earn their
keep as **context, never as facts**: they feed E1 context prefixes, agent navigation, and
"why-was-this-selected" explainability. They are versioned with the structurer. Crucially, the
*global* high-level picture of the corpus is the **K plane's** job (compiled knowledge over
relations/evidence), **not** these per-document summaries — so the high-level picture never depends
on summary quality, but the summaries usefully enrich local navigation.

**Placement hint (the extension).** The PageIndex output is **extended** with a `placement` field: a
proposed path for the document (and optionally key sections) within a *hypothetical directory tree*
of the whole corpus — e.g. `"/finance/annual-reports/2023/"` or
`"/research/transformers/attention/"`. This is a **per-document hint**, produced where the document's
content and structure are freshly understood. It is *advisory*: the authoritative, coherent tree is
materialized later by the projection (§6), which can reconcile, rename, and reorganize across the
whole corpus as it grows (a single document cannot know the global tree).

## 5. Mounting — agents read the memory on their filesystem

A hard requirement: agentic workers get the memory **on their filesystem** and navigate it without
querying Postgres per step. `gcsfuse` mounts a GCS bucket as a filesystem on Cloud Run/GKE, so an
agent can `ls / cat / grep` the corpus. Three buckets are mounted **read-only** (writes always go
through the pipeline; Postgres stays the authority):

- the **corpus filesystem** bucket (§6) — the navigable hierarchy agents browse *first*,
- the **artifacts** bucket — the per-document material they *drill into* (linked from the tree), and
- the **raw** bucket — originals, **off the navigation path** (§2, D51): reached only by following
  an explicit raw pointer from a stub or `document.md` frontmatter (whole-file media ingestion,
  verification, re-OCR debugging, legal provenance); mandatory data-access audit logging; storage
  class routed by mime so browse-pattern reads never hit archive-class retrieval fees.

(The K repo is the fourth mounted surface of the system overall — a read-only checkout — but it is
plane K's concern, not E0's; see `retrieval_design.md` §7.)

**Mount mechanics (not a normal POSIX FS).** A `gcsfuse` mount is object storage behind a filesystem
facade — directories are inferred from object name prefixes, and symlinks/hard-links are not
first-class. So the corpus filesystem is built from **real generated files**, not links: every leaf
is a small generated Markdown **stub** with frontmatter (`doc_id`, `artifact_uri`, `content_hash`,
`section_path`) and a relative pointer to the artifact, so `cat` shows orientation and the agent
follows `artifact_uri` for the full body. Mount config: **read-only**, `--implicit-dirs` (so prefix
folders list correctly), with stat/list caching tuned for the rebuild cadence. (gcsfuse semantics:
https://cloud.google.com/storage/docs/cloud-storage-fuse/overview.)

## 6. The corpus filesystem — P3, a projection — D40

**We build a canonical corpus filesystem.** It is a real, materialized **GCS bucket laid out as a
directory tree** that organizes the whole corpus for agent navigation. It is a **P-plane projection**
(P3): **derived, holding no source-of-truth, no validity state**, and discardable/rebuildable. It is
"canonical" only in the sense of being *the published navigable view* — never an independent truth.

**Rebuild semantics — snapshot + pointer-swap, like P2 (D7).** P3 is a **full snapshot rebuild** by
default: the projection worker builds the whole tree into
`gs://ugm-<dep>-corpusfs/snapshots/<version>/`, validates it, then atomically swaps the `latest`
pointer; agent mounts read `latest`. Incremental tree maintenance is permitted only as an *internal
optimization* that produces the same validated snapshot — never as authority and never a separate
mutable state. This is the same rebuild-first discipline as P2.

**Rebuild inputs (Postgres-anchored).** The tree *structure* is built from **Postgres** (the
placement hints D39, plus entities/relations that define topic/entity folders) **+ the GCS
artifacts** (for the leaf stubs). It **cross-links to** K-plane pages by reference but does **not**
take K as a structural input — so P3 stays rebuildable from the E spine + artifacts, consistent with
P1/P2 (it does not depend on the non-reproducible K git repo for its shape).

```
gs://ugm-<dep>-corpusfs/snapshots/<version>/
  finance/annual-reports/2023/
    acme-10k-2023.md            # generated stub: frontmatter (doc_id, artifact_uri, content_hash)
    _index.md                   # generated: what's here, summaries, links down + across (+ to K)
    llms.txt                    # generated agent-navigation manifest
  research/transformers/attention/
    attention-is-all-you-need.md
    _index.md
  entities/organization/acme/
    _index.md                   # Acme: profile + the docs/sections evidencing facts about it
```

- Folders come from placement hints reconciled across the corpus (topics, sources, time) and from
  entity/relation structure (`entities/...`); leaves are **generated stub files** pointing at the
  per-document artifacts (the agent drills from the tree into the Markdown + per-doc structure).
- Each level carries a generated **`_index.md` / `llms.txt`** so an agent reads orientation before
  contents (the navigation-manifest pattern). Where an `_index.md` links to a **K page**, it
  carries that page's freshness state alongside the link (`compiled_at`, stale?, open review
  flags) — the **browse-path half of the D49 reader-facing flag surface** (the query engine's
  envelope is the other half, `retrieval_design.md` §5): an agent must be able to see "this
  page has unresolved evidence-change flags" *before* reading it, on either path.
- **Composition with K (cross-link, not dependency):** the K plane (compiled understanding) is the
  *summarized* layer; P3 is the *navigable index over sources*. `_index.md` files **link to** relevant
  K pages and vice versa (understanding ↔ evidence) — complementary mounts, not duplicates, and P3's
  *structure* does not depend on K.
- **Reorganizable for free:** because it's a rebuilt projection, the tree reorganizes as the corpus
  grows on the next rebuild — placement hints are inputs, never commitments.

**Why a projection, not E0 state:** the *organization of the corpus* is a function of the evolving
knowledge; freezing it as E0 state would lock an organization that should change as understanding
changes. Per-*document* structure (PageIndex) is intrinsic → E0; *cross-document* organization is
derived → P3.

## 7. End-to-end (one document)

1. Upload `acme-10k-2023.pdf` → **ingest**: raw bytes to the raw bucket, `content_hash`, a
   `documents` row.
2. **convert**: router picks OCR (scanned PDF) → `document.md` + `conversion.json` (offsets) to
   artifacts.
3. **structure**: PageIndex builds the tree (sections, roles, spans, summaries) + a `placement` hint
   `/finance/annual-reports/2023/`; `pageindex.json` to artifacts, `document_sections` rows to
   Postgres.
4. **crossref**: extract citations / document links.
5. → E1 chunks along sections → E2/E3 extract claims/relations.
6. On the next **P3 build**, the document appears at
   `/finance/annual-reports/2023/acme-10k-2023.md` in the mounted corpus filesystem, with a generated
   `_index.md`, cross-linked from `/entities/organization/acme/`.

## 8. Decisions & spikes

Decisions: **D36** (E0 = document layer of sub-workers, no renumber), **D37** (storage split +
Postgres-metadata rule + ID-addressed paths + read-only mount), **D38** (configurable conversion
module), **D39** (PageIndex structure: sidecar + PG index, structure-only, summaries kept, placement
hint), **D40** (P3 corpus-filesystem projection).

Open spikes (measure before committing):
1. **Conversion fidelity vs cost** — OCR is the expensive, quality-critical step; cheap-extract →
   OCR-on-failure fallback chain? Measure on real PDFs.
2. **When to run the PageIndex tool vs. a synthetic root.** Every doc gets a `document_sections`
   structure either way (§4); measure where running the full tool earns its cost vs. a synthetic
   root — an implementation-routing question, not a contract gap.
3. **Placement-hint quality** — how good is a per-document path guess, and how much does the P3 build
   reconcile/override? Measure tree coherence.
4. **P3 build cadence & scale** — rebuild-all vs incremental tree maintenance as the corpus grows;
   how the tree stays stable enough for agents to rely on paths.
5. **doc_id scheme** — hash (collision-safe, opaque canonical paths) + readable names in P3.
6. **Raw storage-class routing** (D51) — measure the read patterns per mime class on a real
   corpus slice; set the standard/nearline/archive routing table and verify the mounted-read
   cost envelope (no archive-class retrieval fees on agent browse patterns).
