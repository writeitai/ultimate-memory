export const meta = {
  name: 'value-gate-research',
  description: 'Research objection O3 (value/salience gate + lazy/deferred extraction) for the ugm pipeline: repo evidence + web, verify, synthesize design implications',
  phases: [
    { title: 'RepoGate', detail: 'read cloned systems for any pre-extraction value/novelty/filter gate' },
    { title: 'Research', detail: 'answer V1-V6 from repo findings + web' },
    { title: 'Verify', detail: 'fact-check numbers/claims and critique completeness' },
    { title: 'Synthesize', detail: 'O3 verdict + design implications + recommended gate' },
  ],
}

const BASE = '/Users/jpuc/code/moje/ultimate_memory/ugm'
const CTX = `${BASE}/_additional_context`
const OUT = `${BASE}/plan/analysis/value_gate_research`
const REG = `${BASE}/plan/analysis/registry_research`
const WEB = `First load web tools: ToolSearch query "select:WebSearch,WebFetch" then use them.`
const DESIGN = `Design context: ${BASE}/plan/analysis/objections.md (O3), ${BASE}/plan/designs/overall_design.md (planes E/K/P, trigger model), ${BASE}/decisions.md (D1 source-of-truth, D4 cheap-first cascade, D7 rebuildable, D12 triggers), ${BASE}/plan/analysis/entity_registry.md.`

// ---------- Phase 1: repo gating evidence ----------
const REPOGROUPS = [
  { slug: 'mem0_cognee', note: 'mem0 (custom_instructions filtering; fact-extraction prompt that DROPS chit-chat; the ADD/UPDATE/DELETE/NOOP novelty controller in mem0/memory/main.py incl. the 0.95 gate; configs/prompts.py) and cognee (any salience/relevance filter before graph extraction; chunk selection).' },
  { slug: 'graphrag_lightrag_hipporag', note: 'graphrag (does it extract EVERYTHING? gleaning loop; any filtering of low-value text), lightrag (entity/relation extraction — any value/novelty filter; incremental insert dedup), hipporag (what gets into the KG; synonymy/filtering).' },
]
const repoResults = await parallel(REPOGROUPS.map(g => () =>
  agent(
`You are a code archaeologist. Read the actual source under ${CTX}/ for this group and report ONLY what is real (cite file:line). Question: does any of these systems GATE/FILTER what gets extracted before spending LLM cost — a value, salience, novelty, dedup, or relevance filter? Or do they extract everything?

Group: ${g.note}

Also note: where each system spends vs SAVES LLM cost; any near-duplicate/novelty check before extraction; any cost/quality numbers in the repo or its docs.

Reuse (don't redo) the prior repo reads in ${REG}/repo_findings/ if helpful. ${DESIGN}

Write findings to ${OUT}/repo_findings/${g.slug}.md (Write tool). Return: file path + 4 bullets on whether/how each system gates extraction.`,
    { label: `repo:${g.slug}`, phase: 'RepoGate' }
  )
)).then(rs => rs.filter(Boolean))
log(`RepoGate done: ${repoResults.length}/${REPOGROUPS.length}`)

// ---------- Phase 2: research questions V1-V6 ----------
const QS = [
  { id: 'V1', slug: 'junk_rate_evidence', q: `How much extracted content is actually LOW-VALUE at scale, and does junk measurably degrade quality? Verify (or debunk) the "~98% of unfiltered memory entries are junk" claim attributed to a Mem0 audit — find the ACTUAL source. Gather other evidence: KG/RAG quality degradation from noisy extraction, hallucination rates in LLM extraction, duplicate/boilerplate prevalence. Build a taxonomy of "junk" (boilerplate, navigation, references, near-duplicate, trivia, hallucinated, low-salience). CONCLUDE: is O3's premise (most content is low-value) empirically supported, and how strongly?` },
  { id: 'V2', slug: 'gating_signals_mechanisms', q: `(A Codex agent independently covers this — be rigorous.) Best CHEAP techniques to score document/section/chunk VALUE before expensive extraction. Signals: source type/trust, structural role (boilerplate/refs vs body), information/entity density, novelty-vs-known (embedding distance to existing claims; near-dup MinHash/SimHash), length/perplexity, query-demand. Mechanisms: heuristics vs small classifier vs small-LLM judge vs embedding-novelty threshold vs dedup pre-pass. The gate must cost MUCH less than the extraction it gates — give cost ratios. RECOMMEND a concrete signal set + mechanism + the 3 output tiers (full/deferred/chunks-only).` },
  { id: 'V3', slug: 'lazy_deferred_extraction', q: `(An Antigravity agent independently covers this.) Architecture for LAZY / DEFERRED / on-demand extraction. Patterns: eager vs lazy materialization, extract-on-first-retrieval + cache, priority work queues, backfill-on-demand, extract-on-scope-interest (a K2 scope declaring interest triggers extraction). Who does this (lazy GraphRAG, RAG-on-demand)? CONSISTENCY: does deferral break "rebuildable from Postgres" (D7) and the per-doc trigger chain (D12)? Is the defer DECISION itself versioned, replayable state? How to keep deferred work tracked/idempotent/not-lost. RECALL risk: deferred docs contribute nothing to global aggregation until pulled — acceptable? mitigations. RECOMMEND the lazy/deferred pattern, where deferred state lives, and the safeguards.` },
  { id: 'V4', slug: 'how_systems_gate', q: `Synthesize from the repo_findings (this dir + ${REG}/repo_findings/) HOW real systems gate/filter extraction, with cost/quality numbers where present: mem0's instruction-based + novelty filtering, cognee, graphrag (extract-all + gleaning), lightrag (incremental dedup), hipporag. What is the actual industry practice — gate or extract-all? Where do the ones that DON'T gate pay for it? RECOMMEND what to borrow.` },
  { id: 'V5', slug: 'recall_safeguards', q: `The rare-but-critical-fact problem: gating risks dropping a low-frequency but vital fact (the classic "user medical allergy" / one-off key decision). How to gate WITHOUT losing gems. Safeguards: DEFER-don't-DROP (L0 immutable so always re-extractable), retrieval-triggered backfill, salience override / pinning, never-drop rules by source/type, sampling audits of dropped content. Evidence on recall loss from aggressive filtering (TTL/LRU/salience eviction studies). RECOMMEND the safeguard set so the gate is reversible and low-regret.` },
  { id: 'V6', slug: 'pipeline_integration', q: `Integrate the gate into OUR pipeline. Where does it sit (E0->E1->E2 boundary; per-document vs per-section vs per-chunk)? The gate/defer DECISION as versioned, rebuildable state (D7): a gate verdict must be recomputable & stored, not a silent drop. Interaction with the per-doc trigger model (D12) and D4 cheap-first cascade. The COST MODEL: expected filter rate x per-stage savings; how it reshapes the R9 scale numbers (which assumed full extraction). Tiers: full / deferred / chunks-only — what each means concretely for E1/E2/E3 and retrieval. RECOMMEND the integration design + cost model + metrics, tied to D7/D12 and to ${REG}/SYNTHESIS.md (which flagged O3 as upstream of R7/R9).` },
]
const qResults = await parallel(QS.map(Q => () =>
  agent(
`Rigorous research analyst. Answer with EVIDENCE (cite sources/URLs + repo file:line); distinguish verified fact from inference; flag anything you could not verify — do NOT invent benchmark numbers or system behaviors. ${WEB}

Read: ${OUT}/repo_findings/*.md and ${REG}/repo_findings/*.md (short), ${DESIGN}, and the cloned repos under ${CTX}/ if needed.

QUESTION ${Q.id}: ${Q.q}

Markdown structure: (1) Key findings; (2) Evidence & detail with citations; (3) Confidence & gaps; (4) Recommendation for ugm (concrete, tied to D1/D4/D7/D12 and O3).
Write to ${OUT}/questions/${Q.id}_${Q.slug}.md (Write tool). Return: file path + 4 highlights + confidence (high/medium/low).`,
    { label: `${Q.id}:${Q.slug}`, phase: 'Research' }
  )
)).then(rs => rs.filter(Boolean))
log(`Research done: ${qResults.length}/${QS.length}`)

// ---------- Phase 3: verification ----------
const VERS = [
  { slug: 'facts', q: `Fact-check every load-bearing NUMBER and external claim across ${OUT}/questions/*.md: the "98% junk" Mem0 figure (does the cited source exist and say that?), any cost-ratio/filter-rate/recall-loss numbers, claims about what mem0/graphrag/lightrag/cognee do (re-check repos under ${CTX}/). Output a table: claim | where | verdict (confirmed/unverified/likely-wrong) | corrected source.` },
  { slug: 'completeness', q: `Completeness & coherence critic over ${OUT}/questions/*.md + repo_findings. What is MISSING (an O3 sub-question under-answered, a risk unaddressed)? Where do docs CONTRADICT each other? What is OVERCLAIMED vs evidence? Specifically pressure-test: (a) does the gate itself risk being a new expensive LLM stage; (b) the rebuildability/versioning of gate decisions; (c) the recall-loss safeguards actually sufficient. Output gaps[], contradictions[], overclaims[], top-5-for-synthesis.` },
]
const vResults = await parallel(VERS.map(V => () =>
  agent(
`Adversarial fact-checker; default skeptical, confirm only with a traceable source. ${WEB}
Task: ${V.q}
Read from ${OUT}/questions/, ${OUT}/repo_findings/, and repos under ${CTX}/. Write to ${OUT}/verify/${V.slug}.md (Write tool). Return: file path + 5 key verdicts.`,
    { label: `verify:${V.slug}`, phase: 'Verify' }
  )
)).then(rs => rs.filter(Boolean))
log(`Verify done: ${vResults.length}/${VERS.length}`)

// ---------- Phase 4: synthesis ----------
await agent(
`Lead architect. Synthesize the O3 research into an actionable verdict for the ugm value/salience gate.

Read EVERYTHING: ${OUT}/repo_findings/*.md, ${OUT}/questions/*.md, ${OUT}/verify/*.md (downweight anything flagged unverified), ${OUT}/external_agents/*.md (independent Codex V2 + Antigravity V3 — reconcile with the Claude takes; if 0 bytes, note they failed and proceed), and design docs ${BASE}/plan/analysis/objections.md, ${BASE}/decisions.md, ${REG}/SYNTHESIS.md (which marked O3 upstream of R7/R9).

Write ${OUT}/SYNTHESIS.md with:
1. "Executive summary" (~8 bullets): is O3's premise real, and the recommended gate design.
2. "Per-question conclusions" (V1-V6): settled answer + confidence + key evidence; note Codex/Antigravity vs Claude agreement.
3. "Recommended design": the gate's position (E-plane boundary), signals, mechanism, the 3 tiers (full/deferred/chunks-only), lazy/deferred architecture, where deferred & gate-decision state lives in Postgres (must be rebuildable per D7), recall safeguards (defer-don't-drop), and the cost model (filter-rate x savings; impact on R9 numbers).
4. "Implications for decisions/objections": resolve O3; what changes in D4/D7/D12; new decisions to propose (D-numbers continue after the registry's proposed D17-D24, so start at D25); whether R7/R9 numbers must be re-derived.
5. "Open risks & what to prototype first".
Be decisive and concrete. Return a 8-bullet executive summary.`,
  { label: 'synthesize', phase: 'Synthesize' }
)

return { repos: repoResults.length, questions: qResults.length, verifiers: vResults.length, synthesis: 'SYNTHESIS.md' }
