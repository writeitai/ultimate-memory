# Open Questions

Questions that requirements_v2.md deliberately leaves open. Answers will shape the design doc.

## Scale & cost
1. **What's the realistic document mix and arrival rate?** "Millions of documents" as a one-time
   backfill vs. thousands/day steady state leads to very different worker sizing and rate limits.
2. **Is there a monthly LLM/embedding budget ceiling?** The supersession cascade and novelty-gate
   thresholds should be tuned against a number, not a vibe.

## Models
3. **Which embedding model (and dimension)?** This is the hardest thing to change later
   (re-embedding everything). Candidates: OpenAI text-embedding-3-large, Voyage, Gemini
   embeddings, or a contextual model (voyage-context) which would replace the prefix approach.
4. **Which LLMs per stage?** Cheap model for context prefixes + claim extraction, small model for
   supersession judgment, frontier model for the ambiguous residue — concrete picks needed.
5. **PageIndex: hosted API or self-hosted?** Affects cost, privacy, and the rebuild story.

## Semantics
6. **Single user or multi-tenant?** Even "just me but multiple agents" affects ID scoping,
   retrieval filters, and the K2 directory layout.
7. **What seeds the P2 ontology?** Which entity types and relations matter on day one
   (people, papers, organizations, concepts, projects…)?
8. **K3 beliefs: qualitative or quantitative?** Plain markdown statements with claim links, or a
   numeric stance score with update rules? (v2 defaults to qualitative + links.)
9. **How fresh must K1/K2 be?** The debounce window (minutes? hours? daily?) is a core design
   parameter for the aggregate-layer triggers.
10. **Hard-delete requirements?** Does GDPR-style "forget this source completely" need to be
    supported, or is soft invalidation always sufficient? (Affects the append-only guarantee.)

## Operations
11. **API auth?** Who calls the retrieval API — only your own agents on trusted infra, or does it
    need keys/OAuth from day one?
12. **Postgres HA appetite?** Single Hetzner box + PITR backups, or a replica? How much downtime
    is acceptable for the spine?
13. **Observability stack?** Tracing/metrics for the pipelines (e.g. OpenTelemetry + Grafana,
    or GCP-native) — worth deciding before the first worker is written.
