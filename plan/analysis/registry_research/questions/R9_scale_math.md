# R9 — Scale & Storage Engineering for the Registry Tables at 1M Docs

**Question.** At 1M docs (→ ~10^7–10^8 mentions), what is the Postgres partitioning strategy,
index sizes/types (btree vs GIN vs trigram for fuzzy blocking, pgvector?), expected row counts
per table, write throughput under streaming ingest, and blocking-query cost? Compare doing
fuzzy/phonetic blocking in Postgres (`pg_trgm`, `fuzzystrmatch`) vs in LanceDB. Recommend
concrete schema partitioning, indexes, and where blocking runs. Show the arithmetic.

This answers the implicit scale question behind D4 (entity-keyed blocking), D6 (Postgres single
authority), D8 (vectors live in Lance not the graph), and the registry schema in
`entity_registry.md` §4. It complements R3 (which fixed *which* phonetic/fuzzy method —
Daitch-Mokotoff + `pg_trgm` + lemmatization) by answering *how it scales and where it runs*.

---

## 1. Key findings

- **The registry tables are not actually big by Postgres standards — the mention table is the
  only ~10^8-row object, and everything that blocking runs against is two-to-three orders of
  magnitude smaller.** Mentions are ~10^7–10^8 rows; **entities ~10^6–10^7**; **relations
  ~5–15M distinct facts** (D2 collapses corpus redundancy — `evidence_count` not parallel
  edges); **resolution_decisions ~ one-per-mention live + superseded history**; **aliases a few
  per entity (~10^6–10^7)**. Supersession blocking (D4) runs over the *relations* table keyed
  `(entity_id, predicate)` — a few-million-row btree lookup returning 1–5 rows
  (`concepts.md` §6), which is trivially cheap. **ER blocking** (resolving a new mention to an
  entity) runs over the *entities/aliases* tables (~10^6–10^7), not over the 10^8 mention table.
  This is the single most important sizing fact: **we never fuzzy-scan 100M rows.** (Inference
  from our data model; verified against the row-count logic in D2/`concepts.md`.)

- **`pg_trgm` GIN is the right fuzzy-blocking index and it is cheap at our candidate-table
  sizes; `daitch_mokotoff()` phonetic blocking is also a native Postgres GIN index. Both run
  in-database (D6), no new infrastructure.** A GIN trigram index turns fuzzy `%`/`ILIKE`/
  similarity probes into Bitmap Index Scans — one cited benchmark shows **8s → 103ms (~98.7%
  faster)** vs. seqscan ([whitestork](https://whitestork.me/blog/20/Fast-Search-with-PostgreSQL:-GIN-Index)).
  Postgres ships `daitch_mokotoff()` returning an array of phonetic codes, explicitly designed
  to be GIN-indexed: `CREATE INDEX ix ON s USING gin (daitch_mokotoff(nm))`
  ([PG fuzzystrmatch docs](https://www.postgresql.org/docs/current/fuzzystrmatch.html)) — and it
  is multibyte/UTF-8 safe and far better than Soundex for non-English (Czech) names, which R3
  requires. **Both fuzzy and phonetic blocking belong in Postgres.** (Verified.)

- **pgvector for ER blocking is the wrong tool at this scale — vectors belong in LanceDB (D8),
  and embedding similarity is tier 4, not the blocker.** An HNSW index over 10M × 1536-dim
  vectors is **80–120 GB and needs the working set in RAM** (raw column ~60 GB at ~6 KB/row);
  if it spills past `maintenance_work_mem` the build is **10–50× slower**
  ([Neon](https://neon.com/blog/pgvector-30x-faster-index-build-for-your-vector-embeddings),
  [pgvector#700](https://github.com/pgvector/pgvector/issues/700)). Putting that in the
  authoritative Postgres instance would bloat it and contend with OLTP ingest. LanceDB already
  exists for E1/E2/E3 vectors (D8), does disk-based IVF-PQ to ~200M vectors/index and 1B+ on S3
  ([AWS](https://aws.amazon.com/blogs/architecture/a-scalable-elastic-database-and-search-solution-for-1b-vectors-built-on-lancedb-and-amazon-s3/)),
  and now has native BM25 FTS. **Verdict: Postgres does exact+fuzzy+phonetic blocking (tiers
  0–3); Lance does the embedding-similarity tier (tier 4) when fuzzy/phonetic don't resolve —
  the same division of labor D8 already drew for relations.** (Verified components; the
  tier-to-store mapping is our inference.)

- **Streaming-ingest write throughput is comfortable, and the bottleneck is GIN/HNSW write
  amplification, not row volume.** Plain partitioned btree COPY sustains ~100k rows/s; index
  write-amplification is ~2.5–3.8× and **scales with index count** (~0.3–0.5× per index,
  GIN/HNSW worst — "a single row can cause 10s–100s of [GIN] index entries")
  ([Tiger Data](https://www.tigerdata.com/blog/write-amplification-in-postgres-the-3-4x-tax-on-every-insert),
  [pganalyze](https://pganalyze.com/blog/gin-index)). **Mitigation that fits our architecture:
  keep `mentions` lean (few/no fuzzy indexes — it's the transcript, you query it by id/doc_id),
  and put the GIN trigram/phonetic indexes on the small `entities`/`aliases` tables where
  amplification is paid over millions, not 100M, rows.** GIN `fastupdate` (pending-list)
  absorbs ingest bursts; batch the resolution write path. (Verified mechanisms.)

---

## 2. Evidence & detail (with the arithmetic)

### 2.1 Row-count model per table (the load-bearing arithmetic)

Assume 1M docs. Mid-range literature figures and our data model (D2):

| Table | Per-doc | Total rows | Driving assumption |
|---|---|---:|---|
| `mentions` (E: transcript) | ~10–100 | **10^7–10^8** | every entity surface form in every claim; immutable, append-only (`entity_registry.md` §4) |
| `resolution_decisions` (append-only verdict) | ≥ #mentions | **10^7–10^8 live + superseded history** | one *live* row per mention; re-resolution campaigns add superseded rows (`entity_registry.md` §4, D12 versioning) |
| `entities` (registry) | — | **10^6–10^7** | distinct real-world things; IDs never reused (`entity_registry.md` §4) |
| `aliases` | few per entity | **10^6–10^7** | nicknames, inflected forms (R3), transliterations |
| `relations` (E3, distinct facts) | — | **5–15M** | corpus redundancy collapsed by D2; same range D8 sizes ("5–15M fact embeddings") |
| `relation_evidence` (join) | ~ #claims | **10^7–10^8** | one row per (relation, claim, stance); the redundancy lands here, not in edges (`concepts.md` §3) |
| `merge_events` (append-only) | rare | **10^5–10^6** | only on merges; carries pre-merge snapshot for un-merge (`entity_registry.md` §4) |

**The critical consequence:** the two tables blocking actually scans are **`relations` (5–15M)**
for supersession (D4) and **`entities`+`aliases` (≤ 2×10^7)** for ER. The 10^8-row `mentions` /
`resolution_decisions` / `relation_evidence` tables are *written* heavily but **never fuzzy-
scanned** — they're read by primary key, `doc_id`, `mention_id`, or `relation_id`. So the
"100M-row fuzzy matching" fear never materializes; that's the whole point of the
transcript/verdict split (`entity_registry.md` §4) and of relations-as-blocking-index
(`concepts.md` §6).

### 2.2 Supersession blocking cost (D4) — arithmetic

D4 blocks on `(entity_id, predicate)` over `relations`. A composite btree on
`(subject_entity_id, predicate)` over 15M rows is ~3 levels deep; an equality probe returns the
candidate facts for one (entity, predicate) pair — **"Usually 1–5 rows"** (`concepts.md` §6).
Cost ≈ one index lookup (sub-millisecond) + reading ≤ a handful of heap tuples. No fuzzy/vector
work at all in the common case; tiers 1→5 escalate only on that 1–5-row remainder (D4). This is
why D4's claim "write-side LLM cost scales with ambiguity, not volume" holds: the *candidate
generation* is an O(log N) btree probe, not an O(N) scan.

### 2.3 ER blocking cost — where fuzzy/phonetic actually runs

Resolving a *new mention* to an entity (tiers 0–4, `entity_registry.md` §4) is the operation
that needs fuzzy/phonetic. Candidate set = entities/aliases whose name is plausibly the same:

- **Tier 1 exact:** btree on `normalized_name` (after R3 lemmatization to nominative + `unaccent`).
  O(log N) over ≤10^7. Sub-ms.
- **Tier 2 fuzzy:** `pg_trgm` GIN on `aliases.normalized_name`. `WHERE name % $1` (similarity) or
  `name ILIKE` → Bitmap Index Scan; cited speedup **8s→103ms vs seqscan**
  ([whitestork](https://whitestork.me/blog/20/Fast-Search-with-PostgreSQL:-GIN-Index)). Returns
  tens of candidates, not millions, because the trigram set of a name is sparse. GIN beats GiST
  to *search* but is slower to *build/update* and "better suited for static data"
  ([PG pg_trgm docs](https://www.postgresql.org/docs/current/pgtrgm.html)) — the alias table is
  near-static relative to mentions, so GIN is correct.
- **Tier 3 phonetic:** GIN on `daitch_mokotoff(name)`; probe `daitch_mokotoff($1) && dm_codes`
  (array overlap). Native, UTF-8-safe, Czech-capable (R3). Index pattern is the documented one
  ([PG fuzzystrmatch docs](https://www.postgresql.org/docs/current/fuzzystrmatch.html)).
- **Tier 4 embedding:** only the residue that tiers 1–3 leave ambiguous goes to **Lance**
  vector similarity over entity-profile embeddings — see §2.5.

Because the candidate **table** here is entities/aliases (≤2×10^7) not mentions (10^8), even GIN
fuzzy scans are over the small side.

### 2.4 Index sizing & types — concrete

| Index | Table | Type | Notes / cost |
|---|---|---|---|
| PK `mention_id` | mentions | btree | unavoidable; cheap |
| `doc_id`, `claim_id` | mentions | btree | retrieval-by-document; keep mentions *otherwise un-indexed* to cap write-amp |
| `(subject_entity_id, predicate)` | relations | btree composite | the D4 blocking key; 15M rows, sub-ms probe |
| `(object_entity_id, predicate)` | relations | btree composite | reverse traversal/blocking |
| `normalized_name` | entities/aliases | btree | tier-1 exact |
| `gin_trgm_ops(normalized_name)` | aliases | **GIN trigram** | tier-2 fuzzy; typically *larger than a btree* on the same column (one GIN entry per trigram); amortized over ≤10^7 rows, acceptable |
| `daitch_mokotoff(name)` | aliases | **GIN (functional, array)** | tier-3 phonetic |
| `relation_id` PK | relations / relation_evidence FK | btree | join key to Lance & evidence |

GIN size caveat (qualitative, verified): GIN indexes are larger and costlier to update than
btree because **"a single row can cause 10s or worst case 100s of index entries"**
([pganalyze](https://pganalyze.com/blog/gin-index)); default `gin_pending_list_limit` is 4 MB and
`fastupdate` defers index merges. **No public benchmark gives an exact GIN-trigram size multiple
for our column distribution — flagged as a gap (§3).** The mitigation is structural: put GIN only
on the small alias table.

**pgvector is deliberately absent from this table.** Sizing why: HNSW over 10M×1536-dim ≈
**80–120 GB**; raw vector column ≈ **60 GB** (~6 KB/row); build needs the set in RAM or runs
**10–50× slower** ([Neon](https://neon.com/blog/pgvector-30x-faster-index-build-for-your-vector-embeddings),
benchmark instance was **64 vCPU / 512 GB RAM** for the 10M/1536 case). That belongs in Lance
(D8), not in the authoritative OLTP Postgres.

### 2.5 Postgres `pg_trgm`/`fuzzystrmatch` vs LanceDB for blocking — the comparison

| Dimension | Postgres (`pg_trgm` + `fuzzystrmatch`) | LanceDB |
|---|---|---|
| What it's good at | **character/phonetic** similarity (typos, inflection, Czech phonetics) | **semantic** similarity (synonyms, paraphrase, cross-form profiles) |
| Tier mapping | tiers 1–3 (exact/fuzzy/phonetic) | tier 4 (embedding) |
| Index | btree + GIN trigram + GIN Daitch-Mokotoff, all native | IVF-PQ / HNSW, native; scales to ~200M/index, 1B+ on S3 ([AWS](https://aws.amazon.com/blogs/architecture/a-scalable-elastic-database-and-search-solution-for-1b-vectors-built-on-lancedb-and-amazon-s3/)) |
| Authority (D6) | **same store as the registry** — no cross-store consistency problem; resolution writes are local transactions | derived/rebuildable projection; must be kept in sync |
| FTS | PG FTS (tsvector) available; weaker ranking | native BM25 (post-Tantivy), 3–8× faster claims ([LanceDB FTS](https://docs.lancedb.com/search/full-text-search)) |
| Cost of a fuzzy probe | Bitmap Index Scan, sub-100ms at our table size | ANN query, ms-scale, but adds a network/store hop |
| Determinism / auditability | fully deterministic, replayable (matches Splink "explainable" lesson, `splink_dedupe.md`) | ANN recall is approximate; fine for *candidate generation*, not for the final verdict |

**Conclusion:** they are **complementary, not competing.** Postgres owns character/phonetic
blocking *because the registry lives there* (D6) and those methods are deterministic and exactly
indexable; Lance owns the semantic tier *because the vectors already live there* (D8) and Postgres
should not host an 80–120 GB HNSW index next to OLTP ingest. This mirrors the relation-search
division D8/D9 already settled: **Lance generates semantic candidates, the authoritative store
adjudicates.**

### 2.6 Write throughput under streaming ingest — arithmetic

- Baseline partitioned COPY: **~100k rows/s** sustained
  ([Tiger Data](https://www.tigerdata.com/learn/testing-postgres-ingest-insert-vs-batch-insert-vs-copy)).
  At 10^8 mentions, a *full* backfill is ~10^8 / 10^5 ≈ **1000 s ≈ 17 min of raw COPY** before
  index maintenance — i.e. the table volume itself is a non-event.
- Write amplification: **~2.5–3.8×**, dominated by index count (~0.3–0.5× per index), GIN/HNSW
  worst ([Tiger Data write-amp](https://www.tigerdata.com/blog/write-amplification-in-postgres-the-3-4x-tax-on-every-insert)).
  So the engineering lever is **number and type of indexes on the hot (10^8-row) tables**, not
  the row count. Keeping `mentions`/`resolution_decisions`/`relation_evidence` on btree-only
  (id/fk indexes) and reserving GIN for the ≤10^7 alias table caps the tax.
- Streaming (not backfill) ingest is per-document (D12: E0→E1→E2 chain via Cloud Tasks),
  so writes arrive as small idempotent batches — well within 100k rows/s headroom. GIN
  `fastupdate` pending-list absorbs bursts; schedule `gin_clean_pending_list()`/autovacuum off
  the ingest peak ([pganalyze](https://pganalyze.com/blog/gin-index)).

### 2.7 Partitioning strategy — concrete & sized

Postgres ≥12 handles **thousands of partitions** efficiently (pre-12 advice was ≤100); keep it
"reasonable" and verify partition pruning with `EXPLAIN ANALYZE`
([PG partitioning docs](https://www.postgresql.org/docs/current/ddl-partitioning.html),
[Elephas](https://elephas.io/is-there-a-limit-on-number-of-partitions-handled-by-postgres/)).

- **`mentions`, `resolution_decisions`, `relation_evidence` (the 10^8 tables): RANGE partition
  by ingest time** (monthly, via `pg_partman`). Rationale: append-only, time-correlated writes →
  inserts hit one hot partition (locality, cheaper index maintenance), old partitions go
  cold/detachable, and most queries (by `doc_id`/`mention_id`) don't need cross-partition fan-out.
  Monthly over a multi-year horizon = tens of partitions, far under the limit.
- **`entities`, `aliases`: do NOT partition** (or HASH-partition only if/when >10^7 and a
  measured planner problem). They're the *blocking target* — fuzzy/phonetic probes must hit every
  candidate regardless of partition, so partitioning here only adds fan-out. ≤10^7 rows is small;
  leave it single-table with the GIN indexes.
- **`relations`: optionally HASH-partition by `subject_entity_id`** *only if* 15M rows + the D4
  blocking probe ever measurably degrades — pruning works because the blocking key leads with
  `subject_entity_id`. Default: don't partition; 15M btree is fine.

---

## 3. Confidence & gaps

**Well-supported (verified, cited):**
- `pg_trgm` GIN speedup magnitude, GIN's "10s–100s entries per row" write cost, `fastupdate`/
  pending-list mechanics (PG docs, pganalyze, whitestork).
- `daitch_mokotoff()` exists in `fuzzystrmatch`, is GIN-indexable, multibyte-safe (PG docs) —
  consistent with R3.
- pgvector HNSW sizing (80–120 GB / 10M×1536; 60 GB raw; 10–50× slowdown if RAM-starved) and the
  64 vCPU/512 GB benchmark instance (Neon, pgvector issue #700).
- COPY ~100k rows/s baseline; write amplification 2.5–3.8× scaling with index count (Tiger Data).
- Postgres ≥12 handles thousands of partitions; pre-12 ≤100 (PG docs, Elephas).
- LanceDB scale (~200M/index, 1B+ on S3) and native BM25 FTS (AWS, LanceDB docs).
- Splink throughput (7M records in ~2 min on DuckDB; 1M/min on a laptop) — confirms classical
  ER backfill is cheap, supporting the "Splink for re-resolution campaigns" use
  (`splink_dedupe.md`, `entity_registry.md` §2). (Robin Linacre / Splink docs.)

**Speculative / inferred (flagged):**
- **All per-table row counts are modeled, not measured** — they depend on mentions-per-doc
  (assumed 10–100) and entities-per-doc, which are corpus-specific. The *ranges* are defensible
  from the data model (D2 collapses relations to 5–15M; D8 independently sizes the same range),
  but exact totals need the golden set / a real corpus (O6).
- **No public benchmark gives the exact GIN-trigram or GIN-Daitch-Mokotoff index *size multiple*
  for a name column at 10^7 rows** — I assert "larger than btree, acceptable on the small table"
  qualitatively; the precise GB figure must be measured. (Gap.)
- The **tier→store mapping** (tiers 1–3 in PG, tier 4 in Lance) is *our* synthesis from D6/D8/D9,
  not a benchmarked recommendation from any source.
- **No end-to-end benchmark of this specific schema under streaming ingest exists** — throughput
  is composed from component numbers (COPY rate × amplification × index count), not measured as a
  whole. (Gap — needs a load test before committing partition/index choices.)

Confidence overall: **medium-high** on the qualitative architecture and the "we never fuzzy-scan
100M rows" conclusion; **medium** on the absolute numbers (modeled, corpus-dependent).

---

## 4. Recommendation for ugm

Concrete, tied to decisions:

1. **Schema partitioning.** RANGE-partition the three 10^8-row append-only tables
   (`mentions`, `resolution_decisions`, `relation_evidence`) by ingest month via `pg_partman`
   (D12's per-doc append model makes time the natural axis). **Do not partition `entities`/
   `aliases`** — they are blocking *targets*; partitioning only adds fan-out. Leave `relations`
   (15M) unpartitioned; HASH-partition by `subject_entity_id` only if D4's probe ever measurably
   degrades (pruning works because the key leads with `subject_entity_id`).

2. **Indexes — minimize on the hot tables, concentrate on the small ones (caps write-amp, D6).**
   - `mentions`/`resolution_decisions`/`relation_evidence`: **btree only** (PK + `doc_id`/`claim_id`/
     `relation_id` FKs). No GIN, no vectors here.
   - `relations`: btree composite `(subject_entity_id, predicate)` (+ object variant) — the D4
     blocking key (`concepts.md` §6).
   - `entities`/`aliases`: btree `normalized_name` (tier 1) **+ GIN `gin_trgm_ops` (tier 2 fuzzy)
     + GIN `daitch_mokotoff(name)` (tier 3 phonetic)**. Store the R3 nominative-lemma +
     `unaccent`ed form as `normalized_name` so all three tiers key off the canonical surface form.

3. **Where blocking runs — split by similarity *kind*, honoring D6 and D8.**
   - **Supersession blocking (D4): Postgres**, btree `(entity_id, predicate)` over `relations`.
     Returns 1–5 rows; escalate tiers only on that remainder.
   - **ER tiers 0–3 (exact/fuzzy/phonetic): Postgres**, in the registry store — deterministic,
     replayable, no cross-store hop, indexes above. This is the natural home given D6 (single
     authority) and R3 (Daitch-Mokotoff + `pg_trgm` are native).
   - **ER tier 4 (embedding similarity): LanceDB**, over entity-profile embeddings — *only* on the
     residue tiers 1–3 leave ambiguous. Reuses the existing Lance estate (D8); **keep the 80–120 GB
     HNSW out of authoritative Postgres.** Lance generates semantic candidates; Postgres records
     the verdict (resolution_decisions) — exactly the candidate-vs-adjudication split of D8/D9.

4. **Ingest discipline.** Stream per-document (D12) in small idempotent batches; rely on GIN
   `fastupdate` to absorb bursts and schedule pending-list cleanup/vacuum off-peak. Use **COPY-
   based bulk load for re-resolution campaigns and backfills** (≈17 min raw for 10^8 rows before
   indexing); run classical batch ER (Splink/dedupe, `splink_dedupe.md`) for those campaigns —
   verified at 7M records / ~2 min — never as the online mechanism.

5. **Measure before hardening (O6 dependency).** The row-count model and GIN size are *modeled*.
   Before locking partition/index choices, run a load test on a representative corpus slice to
   get real mentions-per-doc, GIN index GB, and end-to-end streaming throughput. The architecture
   above is robust to the numbers; the exact partition granularity and whether `relations` needs
   HASH partitioning are the only knobs that depend on measured values.

---

## Sources

[PG pg_trgm docs](https://www.postgresql.org/docs/current/pgtrgm.html) ·
[PG fuzzystrmatch / daitch_mokotoff docs](https://www.postgresql.org/docs/current/fuzzystrmatch.html) ·
[PG table partitioning docs](https://www.postgresql.org/docs/current/ddl-partitioning.html) ·
[pganalyze: GIN indexes good & bad](https://pganalyze.com/blog/gin-index) ·
[whitestork: GIN index speedup](https://whitestork.me/blog/20/Fast-Search-with-PostgreSQL:-GIN-Index) ·
[Neon: pgvector 30× faster index build](https://neon.com/blog/pgvector-30x-faster-index-build-for-your-vector-embeddings) ·
[pgvector issue #700: HNSW QPS degradation past memory](https://github.com/pgvector/pgvector/issues/700) ·
[Tiger Data: Postgres ingest INSERT vs COPY](https://www.tigerdata.com/learn/testing-postgres-ingest-insert-vs-batch-insert-vs-copy) ·
[Tiger Data: write amplification 3–4× tax](https://www.tigerdata.com/blog/write-amplification-in-postgres-the-3-4x-tax-on-every-insert) ·
[Elephas: partition count limits](https://elephas.io/is-there-a-limit-on-number-of-partitions-handled-by-postgres/) ·
[AWS: 1B+ vectors on LanceDB + S3](https://aws.amazon.com/blogs/architecture/a-scalable-elastic-database-and-search-solution-for-1b-vectors-built-on-lancedb-and-amazon-s3/) ·
[LanceDB FTS docs](https://docs.lancedb.com/search/full-text-search) ·
[Robin Linacre: dedup 7M records in 2 min with Splink](https://www.robinlinacre.com/fast_deduplication/)
