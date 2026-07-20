# Retrieval spike battery (WP-5.6)

**Question.** Close the six measurements left open by
`retrieval_design.md` §13 after the graph as-of and S58 spikes closed in
WP-4.1 and WP-5.5: filtered Lance search at retrieval scale, S49 hub paging,
RRF/rerank weights, envelope overhead, interactive hydration batching, and
S51 resolve-context ranking.

**Method.** `src/tests/spikes/test_retrieval_spikes.py` is the executable
battery. CI runs the same assertions with 20,000 Lance rows and 2,000 hub
edges as a capability canary; timings never gate CI. The recorded scale run
set `UGM_RETRIEVAL_SPIKE_LANCE_ROWS=10000000`,
`UGM_RETRIEVAL_SPIKE_HUB_EDGES=100000`, and five timing repeats. It ran on an
Apple-silicon laptop under macOS 26.5, Python 3.13.1, LanceDB 0.34.0,
LadybugDB 0.18.2, and PostgreSQL 16.14. The complete typed report was appended
as one `suite='retrieval'`, `component_version='retrieval-spikes-2026.07b'`
row in `eval_runs`; a report with a duplicate or missing spike is rejected.
The battery's 64 KiB page-envelope and 16 KiB inline-contradiction budgets are
conservative operational starting targets used to choose bounded defaults;
neither is a wire-protocol limit or an SLA.
With five samples, the battery's nearest-rank p95 is the maximum of five
warmed observations; these small-sample timings are context, not CI gates.

## Results and selected starting values

| Question | Scale-run observation | Selected value | Honest boundary |
|---|---|---|---|
| Lance scalar-prefiltered ANN | Five million claim rows and five million fact rows. Unindexed p95 was 272 ms / 337 ms; indexed p95 was 31 ms / 34 ms. Both channels returned ten correctly filtered rows and recovered the planted exact vector at distance zero. | Explicit post-bulk-load indexes: B-tree on deployment, bitmap on current/kind, IVF_FLAT at about 8,192 rows/partition (611 partitions/table here), `nprobes=20`. | This is the lower end of the designed 10^7–10^8 range. Independent synthetic 8-D vectors measure engine/filter shape, not embedding recall. |
| S49 hub pagination | At 100,000 edges, a 500-node envelope was 51,178 bytes and p95 was 310 ms; a 1,000-node envelope was 101,680 bytes. A complete 200-page walk returned all 100,000 unique neighbors once in 56.0 s. | 500 neighbors/page under the battery's 64 KiB operational target; snapshot-version + offset continuation; the 10,000-row count probe affects total metadata only. | The observed 310 ms is slightly above §10's 300 ms starting target and is machine-specific. Cursor completeness and the byte boundary, not timing, are the durable invariants; WP-7.3 owns load tuning. |
| RRF + rerank weights | A 64-point grid over five hand-labelled S46/S48 canaries, including one misleading graph signal, reached mean NDCG@4 = 1.0 at the defaults on a broad 49-setting plateau. | Retain the conventional RRF `k=60`, which the grid cannot distinguish from the other tested values; use the smallest tested nonzero pair, graph proximity `0.10` and evidence support `0.10`. | These planted canaries prevent simple regressions; they do not estimate corpus-wide relevance or empirically select `k=60`. |
| Envelope overhead | With deliberately long co-member labels, 3 / 10 / 25 / 50 inline members serialized to 2,135 / 4,531 / 9,691 / 18,257 bytes. p95 serialization stayed at or below 0.327 ms. | Keep 25 contradiction co-members inline under the 16 KiB operational target; the existing group id/count/continuation carries the rest. | This measures one worst-case-shaped contradiction envelope, not every envelope composition. |
| Cross-cloud hydration batching | At eight concurrent clients, local PostgreSQL p95 for the narrow indexed entity-id proxy at 1 / 8 / 32 / 64 / 128 / 256 ids was 16 / 17 / 34 / 23 / 23 / 86 ms. Adding an explicit, modeled 25 ms network round trip kept 256 ids at 111 ms, below retrieval §10's 300 ms starting budget. Every probed batch returned every requested id. | Chunk interactive confirmation reads at 256 ids while preserving candidate order and the honest drop count. | The proxy does not reproduce the production claim join or a full hydration envelope. PostgreSQL execution is measured; the 25 ms cross-cloud hop is modeled, and timings do not gate CI. WP-7.3 owns broader load tuning. |
| Resolve context | Four identical-name candidates had baseline top-1 accuracy 0.25. One current relation-adjacent focal entity raised it to 1.0, while every ambiguous candidate remained visible. | Rank by current relation-adjacency count; accept at most eight de-duplicated focal entity ids; no heavier ranker. | Four planted S51 cases use one focal entity each. Real-corpus lift and wider-context behavior remain D22 monitoring metrics. |

## Implementation findings

The battery caught one correctness bug rather than merely choosing numbers.
The graph query previously used the bounded 10,000-row count probe as the
paging boundary, so a 100,000-edge hub stopped producing continuations after
the cap. Paging now fetches one extra result to decide whether another page
exists; the bounded count remains honest, inexact metadata. A regression
canary lowers the probe cap to two and still walks the entire neighborhood.

Lance index construction is an explicit maintenance operation after bulk load,
not hidden inside every P1 upsert. Search uses scalar prefiltering before ANN
and probes 20 IVF partitions; the spike exercises those production parameters
directly rather than routing through the P1 wrapper. WP-7.1 owns wiring this
operation into backfill orchestration, and WP-7.2 validates the realized index
shape under load. Weighted reranking retains the raw and normalized RRF,
graph-proximity, and evidence-support contributions on every result. The
hydration confirmation hop chunks over-large candidate lists without changing
their order, and a surface regression crosses the configured batch boundary on
the real claim-confirmation path. Resolve context is a tie-break only: it counts
distinct focal entities, reports `context_hits`, and never removes a candidate
or silently chooses an identity.

## Reproduction

Capability-sized CI run:

```bash
UGM_DATABASE_URL=postgresql+psycopg://postgres:ugm@localhost:55433/ugm_check \
  uv run pytest -q -s src/tests/spikes/test_retrieval_spikes.py
```

Recorded scale run:

```bash
UGM_DATABASE_URL=postgresql+psycopg://postgres:ugm@localhost:55433/ugm_check \
UGM_RETRIEVAL_SPIKE_LANCE_ROWS=10000000 \
UGM_RETRIEVAL_SPIKE_HUB_EDGES=100000 \
UGM_RETRIEVAL_SPIKE_REPEATS=5 \
  uv run pytest -q -s src/tests/spikes/test_retrieval_spikes.py
```

The final scale run completed green in 421 seconds and wrote eval run
`eae2ddbb-1996-492f-a021-5c4da3d01511`. The committed report is a
machine-specific measurement, not an SLA; the executable invariants and the
versioned `eval_runs` payload are the durable result.
