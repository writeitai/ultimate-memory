export const meta = {
  name: 'registry-research',
  description: 'Research the entity-registry/ontology/extraction questions (R1-R10) by reading cloned repos + web, verify adversarially, synthesize implications for the ugm design',
  phases: [
    { title: 'RepoExtract', detail: 'read each cloned repo for ER/coref/extraction/ontology/temporal/merge mechanisms' },
    { title: 'Research', detail: 'answer R1-R10 from repo findings + web' },
    { title: 'Verify', detail: 'adversarially check numbers, external-system facts, and overclaims' },
    { title: 'Synthesize', detail: 'per-question conclusions + design implications + recommended path' },
  ],
}

const BASE = '/Users/jpuc/code/moje/ultimate_memory/ugm'
const CTX = `${BASE}/_additional_context`
const OUT = `${BASE}/plan/analysis/registry_research`
const WEB = `First load web tools: call ToolSearch with query "select:WebSearch,WebFetch" then use WebSearch/WebFetch freely.`
const DESIGN = `Our design docs (read for context): ${BASE}/plan/analysis/entity_registry.md, ${BASE}/decisions.md (D1-D16), ${BASE}/plan/analysis/concepts.md, ${BASE}/plan/analysis/objections.md.`

// ---------- Phase 1: repo extraction ----------
const REPOS = [
  { slug: 'graphiti', dirs: ['graphiti'], note: 'getzep/graphiti — THE most relevant. Read graphiti_core/: prompts/ (extract_nodes, extract_edges, dedupe_nodes, dedupe_edges, models.py), utils/maintenance/dedup_helpers.py, utils/ontology_utils/, nodes.py, edges.py. Temporal bi-temporal edges, node/edge dedup, entity/edge type system.' },
  { slug: 'cognee', dirs: ['cognee'], note: 'topoteretes/cognee — ontology matching/validation, entity description consolidation, temporal_awareness. Read examples/guides/ontology_quickstart.py, examples/demos/custom_graph_model_entity_schema_definition.py, cognee/tasks/, cognee/modules ontology code.' },
  { slug: 'mem0', dirs: ['mem0'], note: 'mem0ai/mem0 — ADD/UPDATE/DELETE/NOOP memory controller. Read mem0/utils/entity_extraction.py, mem0/configs/prompts.py, graph memory modules.' },
  { slug: 'letta_hipporag', dirs: ['letta', 'hipporag'], note: 'letta (MemGPT, OS-style tiered memory, self-editing tools) and hipporag (OSU-NLP-Group/HippoRAG — neurobiologically inspired, personalized PageRank over a KG, synonymy edges). Focus on memory lifecycle, entity/synonymy handling, retrieval.' },
  { slug: 'lightrag_graphrag', dirs: ['lightrag', 'graphrag'], note: 'HKUDS/LightRAG and microsoft/graphrag — entity+relationship extraction prompts, gleaning loop, dedup/merge of entities across chunks, community detection. Read their extraction prompts and entity-merge logic.' },
  { slug: 'splink_dedupe', dirs: ['splink', 'dedupe'], note: 'splink (Fellegi-Sunter probabilistic record linkage; blocking rules; m/u probabilities; clustering via connected components; thresholds) and dedupe (active-learning labeling, training, clustering, thresholds). The classical ER tradition — extract concrete algorithms and parameters.' },
  { slug: 'zingg', dirs: ['zingg'], note: 'zinggAI/zingg — ER at scale (Spark). Blocking, similarity, active-learning labeling, connected-components clustering, the review/labeling UX. Extract the scale architecture and human-in-the-loop review approach.' },
  { slug: 'coref', dirs: ['maverick-coref', 'fastcoref'], note: 'SapienzaNLP/maverick-coref and shon-otmazgin/fastcoref — modern coreference resolution. Extract: model architecture, accuracy (CoNLL-2012 F1), speed/cost per document, API usage, and whether it is mention-cluster or pronoun-only.' },
]

const repoResults = await parallel(REPOS.map(r => () =>
  agent(
`You are a code archaeologist. Read the actual source of the cloned repo(s) [${r.dirs.join(', ')}] under ${CTX}/ and extract what is REAL (cite file paths, quote code/prompts, give concrete numbers/thresholds). Do not speculate; if something isn't in the code, say "not found".

Repo focus: ${r.note}

${DESIGN}

Extract, with file references, whatever of these apply to this repo:
- Entity resolution / dedup mechanism: how it decides same-vs-different. Deterministic vs LLM. Exact thresholds/parameters in code.
- Coreference handling (if any).
- Extraction: how claims/entities/relations are prompted & constrained (free-form vs JSON-schema/function-calling vs grammar). Single vs multi-pass gleaning. Quote the schema/prompt shape.
- Ontology / type system: how types & predicates are defined, validated, enforced (domain/range?).
- Temporal / bi-temporal model: validity windows, supersession/invalidation.
- Clustering / merge / un-merge: algorithm, transitive-closure handling, reversibility.
- Concrete numbers: thresholds, model choices, accuracy/benchmark figures present in repo.
- "Steal vs avoid": techniques worth adopting for ugm, and pitfalls to avoid.

Write your findings as markdown to ${OUT}/repo_findings/${r.slug}.md (use the Write tool). Then return ONLY: the file path + 4 bullet highlights.`,
    { label: `repo:${r.slug}`, phase: 'RepoExtract' }
  )
)).then(rs => rs.filter(Boolean))

log(`RepoExtract done: ${repoResults.length}/${REPOS.length} repos`)

// ---------- Phase 2: research questions ----------
const QUESTIONS = [
  { id: 'R1', slug: 'coref_necessity', web: true, q: `Is a SEPARATE coreference-resolution step still warranted in 2026, or do long-context LLM extractors resolve pronouns/anaphora implicitly? Compare: dedicated coref (Maverick, fastcoref — see repo_findings/coref.md) vs letting the extraction LLM see the whole document. Evidence for claim quality with/without dedicated coref. Cost per document of each. Multilingual coref availability. Do graphiti/cognee/mem0 run a coref step (check repo_findings)? RECOMMEND: keep, drop, or make-optional the coref stage in our E2 pipeline, with reasoning.` },
  { id: 'R2', slug: 'er_cascade_numbers', web: true, q: `What do tiered-cascade ER systems ACTUALLY achieve, with real numbers? Our assumed thresholds (Jaro-Winkler >=0.92, cosine >=0.88) are folklore. Read repo_findings for graphiti/splink/dedupe/zingg/cognee/mem0. Find published precision/recall on standard ER benchmarks (Magellan/DeepMatcher, Abt-Buy, DBLP-ACM/Scholar, WDC) for classical Fellegi-Sunter vs embedding vs LLM matchers, and recall lost to blocking. Are our thresholds defensible? How should thresholds be set (per-type, learned)? RECOMMEND the tier ordering + where the LLM call belongs + how to set thresholds. NOTE: a Codex agent is independently analysing this; be rigorous so we can cross-check.` },
  { id: 'R3', slug: 'multilingual_inflected', web: true, q: `Multilingual & inflected-language entity resolution, with SPECIAL attention to Czech (the corpus may contain Czech). Inflected names: "Jiří Puc" -> "Jiřího Puce"/"Jiřímu Pucovi" (declension). English-biased phonetics (Soundex) fail. Research: lemmatization-before-matching, Beider-Morse phonetic matching, multilingual/transliteration name-matching, multilingual NER & coref quality for Czech and other Slavic/non-English languages. RECOMMEND a concrete approach for multilingual aliases & matching in our registry. Flag this clearly as a possible new work package.` },
  { id: 'R4', slug: 'external_authorities', web: true, q: `External authority files as ER "tier 0". For each of: OpenAlex, Crossref/DOI, ORCID, Wikidata (QIDs + reconciliation API), GLEIF LEI, OpenCorporates, ISBN, GitHub — describe: what entity types it authoritatively IDs, API access/rate limits/licensing/cost, real coverage of long-tail (non-famous) entities, and reconciliation-API quality. Which are worth integrating at launch for a general research/knowledge memory vs never. RECOMMEND a concrete tier-0 connector set + fallback when no authority matches.` },
  { id: 'R5', slug: 'ontology_core_validation', web: true, q: `(A second, independent take — an Antigravity agent also covers this.) Validate or refute "LLMs extract better into familiar/standard vocabularies (schema.org) than bespoke type names" with real evidence. Survey minimal core ontologies to borrow (schema.org, Wikidata top classes, FOAF, Dublin Core, CIDOC-CRM, DBpedia). Check how cognee & graphiti represent/enforce ontologies in code (repo_findings). Assess our "extend-never-fork + parent-anchor + domain/range, not OWL" decision (D15): sound? what's lost vs OWL and does it matter for extraction/blocking/retrieval? RECOMMEND a concrete seed core (8 types, ~12-15 predicates with domain/range mapped to standards).` },
  { id: 'R6', slug: 'constrained_extraction', web: true, q: `(A second, independent take — a Codex agent also covers this.) Best techniques for high-precision, scalable claim/relation extraction into a GOVERNED schema. From repo_findings (graphiti/cognee/mem0/lightrag/graphrag): free-form vs typed function-calling/JSON-schema vs grammar-constrained decoding; single vs multi-pass gleaning. Literature on closed-IE vs OpenIE precision/recall; cost of our closed-with-other-escape hybrid. Constrained decoding (Outlines/grammars, GLiNER, tool-calling) — which materially help. How to render a growing predicate set into prompts (static vs dynamically selected). Decontextualization-vs-minimality. RECOMMEND the E2->E3 extraction design + what to measure.` },
  { id: 'R7', slug: 'golden_set_active_learning', web: true, q: `Cheapest path to a labeled ER evaluation/training set + active learning. From repo_findings (dedupe's active learning, splink, zingg labeling). Research: LLM-generated candidate pairs + human verification, active-learning sampling (uncertainty/query-by-committee), how big a golden set per entity type before threshold tuning is statistically meaningful, semi-synthetic data. Tie to objection O6 (no eval loop). RECOMMEND a concrete bootstrapping plan: how to build the golden set, its size, how it feeds threshold tuning and regression testing, and whether quality metrics ship with v1.` },
  { id: 'R8', slug: 'incremental_clustering', web: true, q: `(A second, independent take — an Antigravity agent also covers this.) Correct production approach to INCREMENTAL entity clustering with reversible merges. From repo_findings (splink/dedupe/zingg clustering). Dangers of transitive closure; correlation clustering vs connected-components-with-edge-cutting vs Louvain vs hierarchical. Incremental cluster maintenance (add a mention without full re-cluster); Senzing-style real-time principle-based resolution. Un-merge: what state to retain. Quality safeguards: blast-radius limits, cluster-size & singleton monitoring. How does GRAPH-REBUILT-FROM-POSTGRES-EVERY-CYCLE (D7) change the choice? RECOMMEND the clustering algo, incremental procedure, reversibility records, and safeguard metrics for a Postgres-backed store.` },
  { id: 'R9', slug: 'scale_math', web: true, q: `Scale & storage engineering for the mention/entity/resolution-decision/relation tables at 1M docs (=> ~10^7-10^8 mentions). Postgres partitioning strategy, index sizes & types (btree vs GIN vs trigram for fuzzy blocking, pgvector?), expected row counts per table, write throughput under streaming ingest, blocking-query cost. Compare doing fuzzy/phonetic blocking in Postgres (pg_trgm, fuzzystrmatch) vs in LanceDB. RECOMMEND concrete schema partitioning, indexes, and where blocking runs. Calculable — show the arithmetic.` },
  { id: 'R10', slug: 'review_tooling', web: true, q: `Human-in-the-loop review tooling for merge proposals & resolution QA. From repo_findings (zingg review UX, dedupe console, splink dashboards/charts). Research existing tools (Zingg, splink comparison dashboards, OpenRefine reconciliation, Prodigy, Argilla) vs building a minimal CLI/web queue. What review granularity (pair vs cluster) scales. RECOMMEND build-vs-adopt for our review queue, the minimal viable reviewer workflow, and how decisions feed back into the append-only resolution records.` },
]

const qResults = await parallel(QUESTIONS.map(Q => () =>
  agent(
`You are a rigorous research analyst. Answer this question exhaustively with EVIDENCE (cite sources/URLs and repo file paths; give numbers; distinguish verified fact from inference; explicitly flag anything uncertain or that you could not verify — do NOT invent system names or benchmark numbers).

${WEB}

Inputs you should read:
- Relevant files in ${OUT}/repo_findings/ (glob & read the ones related to this question — they are short).
- ${DESIGN}
- The cloned repos under ${CTX}/ directly if you need code detail.

QUESTION ${Q.id}: ${Q.q}

Structure your markdown: (1) "Key findings" bullets; (2) Evidence & detail with citations; (3) "Confidence & gaps" — what is well-supported vs speculative; (4) "Recommendation for ugm" — concrete, actionable, tied to our decisions D1-D16 where relevant.

Write to ${OUT}/questions/${Q.id}_${Q.slug}.md (Write tool). Return ONLY: file path + 4 bullet highlights + a confidence label (high/medium/low).`,
    { label: `${Q.id}:${Q.slug}`, phase: 'Research' }
  )
)).then(rs => rs.filter(Boolean))

log(`Research done: ${qResults.length}/${QUESTIONS.length} questions`)

// ---------- Phase 3: adversarial verification ----------
const VERIFIERS = [
  { slug: 'numbers', q: `Verify every NUMERIC claim across ${OUT}/questions/*.md: thresholds (Jaro-Winkler 0.92, cosine 0.88, etc.), benchmark precision/recall figures, accuracy/F1 numbers, cost figures, scale arithmetic (R9). For each: is it traceable to a real source (repo code, paper, vendor doc) or is it folklore/unverifiable? Re-check the repos and do web spot-checks. Output a table: claim | where stated | verdict (confirmed / unverified / likely-wrong) | note.` },
  { slug: 'external_facts', q: `Verify external-SYSTEM factual claims across ${OUT}/questions/*.md, especially R4 (OpenAlex/ORCID/Crossref/Wikidata/GLEIF/OpenCorporates API limits, licensing, coverage), R8 (Senzing behavior), Wikidata redirect/QID semantics. Flag any hallucinated capabilities, made-up system names, or wrong API/licensing facts. Web-verify the load-bearing claims. Output: claim | verdict | corrected fact + source.` },
  { slug: 'ontology_extraction', q: `Verify R5 + R6 claims against the ACTUAL repos under ${CTX}/ (graphiti, cognee, mem0, lightrag, graphrag) and reputable sources: does the code really do what the analyses say (extraction constraint method, ontology enforcement, gleaning)? Is the "schema.org familiarity improves extraction" claim actually evidenced or asserted? Output: claim | verdict | evidence/file-ref.` },
  { slug: 'coref_clustering', q: `Verify R1 (coref) + R8 (clustering) claims: coref accuracy/speed numbers against the maverick-coref/fastcoref repos and CoNLL-2012 literature; clustering algorithm claims against splink/dedupe/zingg source. Confirm transitive-closure/un-merge claims are real. Output: claim | verdict | evidence.` },
  { slug: 'completeness', q: `Completeness & coherence critic over ALL of ${OUT}/questions/*.md and ${OUT}/repo_findings/*.md. What is MISSING (a question under-answered, a repo technique not surfaced, a design risk unaddressed)? Where do the question docs CONTRADICT each other? What is OVERCLAIMED relative to evidence? Output: gaps[], contradictions[], overclaims[], and the top 5 things the synthesis must resolve.` },
]

const vResults = await parallel(VERIFIERS.map(V => () =>
  agent(
`You are an adversarial fact-checker. Default to skepticism; a claim is "confirmed" only with a traceable source (repo file:line, paper, or vendor doc). ${WEB}

Task: ${V.q}

Read what you need from ${OUT}/questions/, ${OUT}/repo_findings/, and the cloned repos under ${CTX}/. Write your verdict report to ${OUT}/verify/${V.slug}.md (Write tool). Return ONLY: file path + the 5 most important verdicts.`,
    { label: `verify:${V.slug}`, phase: 'Verify' }
  )
)).then(rs => rs.filter(Boolean))

log(`Verify done: ${vResults.length}/${VERIFIERS.length} verifiers`)

// ---------- Phase 4: synthesis ----------
const synth = await agent(
`You are the lead architect synthesizing a research effort into an actionable analysis for the ugm entity-registry/ontology/extraction subsystem.

Read EVERYTHING:
- ${OUT}/repo_findings/*.md  (what real systems do)
- ${OUT}/questions/*.md      (R1-R10 analyses)
- ${OUT}/verify/*.md         (fact-check verdicts — DOWNWEIGHT anything flagged unverified/likely-wrong)
- ${OUT}/external_agents/*.md (independent Codex & Antigravity analyses on R2,R5,R6,R8 — reconcile with the Claude analyses; where they disagree, reason it out)
- ${BASE}/plan/analysis/entity_registry.md, ${BASE}/decisions.md, ${BASE}/plan/analysis/objections.md (our current design)

Write ${OUT}/SYNTHESIS.md with:
1. "Executive summary" — the best path forward in ~10 bullets.
2. "Per-question conclusions" (R1-R10): for each, the settled answer, confidence, and the key evidence — noting where Codex/Antigravity and Claude agreed or diverged.
3. "Implications for our design" — concrete changes mapped to decisions D1-D16 and objections O2-O6: what is CONFIRMED, what should CHANGE, what is NEW. Call out anything that contradicts a current decision.
4. "Proposed decisions/changes" — a numbered list ready to become D17+ or design-doc edits (ontology seed core, tier cascade + thresholds, coref verdict, multilingual plan, tier-0 authorities, clustering+reversibility, golden-set/eval plan, scale/schema, review tooling).
5. "Open risks & what to prototype first" — what still needs a spike before committing.

Be decisive and concrete; prefer recommendations over surveys. Cite the source docs. Return ONLY a 10-bullet executive summary.`,
  { label: 'synthesize', phase: 'Synthesize' }
)

return { repos: repoResults.length, questions: qResults.length, verifiers: vResults.length, synthesis: 'SYNTHESIS.md' }
