export const meta = {
  name: 'entity-typing-research',
  description: 'Research the entity-typing gap (how a mention/entity gets its type) for the ugm registry: repo evidence + web, verify, synthesize the best course of action',
  phases: [
    { title: 'RepoTyping', detail: 'how cloned systems assign entity types' },
    { title: 'Research', detail: 'answer TY1-TY5 from repo findings + web' },
    { title: 'Verify', detail: 'fact-check + completeness critique' },
    { title: 'Synthesize', detail: 'recommended typing architecture + design close' },
  ],
}

const BASE = '/Users/jpuc/code/moje/ultimate_memory/ugm'
const CTX = `${BASE}/_additional_context`
const OUT = `${BASE}/plan/analysis/entity_typing_research`
const WEB = `First load web tools: ToolSearch query "select:WebSearch,WebFetch" then use them.`
const DESIGN = `Design context: ${BASE}/plan/designs/registries_design.md, ${BASE}/decisions.md (D2,D4,D5,D15,D16,D17 resolution cascade,D18 8-type core+domain/range,D21 clustering/reversibility,D22 golden set), ${BASE}/plan/analysis/concepts.md.`
const GAP = `THE GAP: identity resolution (mention -> entity_id) is fully specified (D17); entity TYPING (assigning Person/Organization/Concept/... to a mention/entity) is NOT specified anywhere, yet predicate domain/range enforcement (D18) depends on types being known.`

// ---------- Phase 1: repo typing mechanisms ----------
const GROUPS = [
  { slug: 'graphiti_cognee', note: 'graphiti: entity_types system, graphiti_core/prompts/extract_nodes.py, utils/ontology_utils/entity_types_utils.py, nodes.py — how a type is attached to a node, default/fallback type, type-on-merge. cognee: how extracted entities match ontology classes (the ~0.8 fuzzy cutoff), unmatched handling, default typing.' },
  { slug: 'lightrag_graphrag_gliner', note: 'lightrag + graphrag: the entity_types list / DEFAULT_ENTITY_TYPES passed to the extraction prompt, how unknown/extra types are handled, the gleaning loop. GLiNER + GLiREL (zero-shot typed NER/RE): how the label set is supplied, model size/speed, suitability as a cheap typing tier. mem0: does it type entities at all?' },
]
const repoResults = await parallel(GROUPS.map(g => () =>
  agent(
`You are a code archaeologist. Read the actual source under ${CTX}/ for this group and report ONLY what is real (cite file:line). Subject: HOW does each system assign a TYPE to an entity (Person/Org/Concept/...)?

Group: ${g.note}

For each system report: (a) where/when the type is assigned (extraction prompt? post-hoc classifier? ontology match?); (b) the type inventory (fixed list? open/zero-shot? default fallback?); (c) what happens to entities that fit no type; (d) mention-level vs entity-level typing and any type-reconciliation-on-merge; (e) any confidence/validation on the type; (f) "steal vs avoid" for ugm.

${DESIGN} ${GAP}

Write findings to ${OUT}/repo_findings/${g.slug}.md (Write tool). Return: file path + 4 bullets.`,
    { label: `repo:${g.slug}`, phase: 'RepoTyping' }
  )
)).then(rs => rs.filter(Boolean))
log(`RepoTyping done: ${repoResults.length}/${GROUPS.length}`)

// ---------- Phase 2: research questions ----------
const QS = [
  { id: 'TY1', slug: 'when_where', q: `WHEN/WHERE should typing happen in the ugm pipeline? Options: (a) at extraction time — the E2/E3 LLM proposes a type as it extracts the mention (type as an enum field in the structured-output schema); (b) during entity resolution; (c) a dedicated typing stage. Consider: typing needs CONTEXT (the sentence), which extraction already has; domain/range validation needs types BEFORE it can run. Give the recommended pipeline position with rationale, and how the type menu (8 core + per-deployment extension/pack subtypes) is supplied to the extractor. Tie to D17/D18 and the per-document chain (D12).` },
  { id: 'TY2', slug: 'mention_vs_entity', q: `MENTION-level vs ENTITY-level typing. A mention is typed in context; the canonical entity needs ONE type. How are per-mention type votes reconciled into the entity type (majority? authority-wins? most-specific?)? Crucially: when mentions of the same resolved entity DISAGREE on type, is that (a) genuine ambiguity/metonymy, or (b) a SIGNAL that resolution wrongly merged two different referents (Washington-the-person vs Washington-the-place)? How should type-disagreement feed back into the ER cascade (D17/D21) and the blast-radius/review machinery (D24)? Recommend the reconciliation rule + the disagreement-as-ER-signal mechanism.` },
  { id: 'TY3', slug: 'typing_cascade', q: `Should there be a TYPING CASCADE analogous to the resolution cascade (D17), cheap-first? Candidate rungs: external-authority type (DOI->Document, ORCID->Person, GLEIF LEI->Organization, Wikidata P31/instance-of — free and near-certain, ties to D20); deterministic gazetteer/suffix signals (Inc./Ltd.->Org); a small zero-shot typed-NER model (GLiNER-style); the extraction LLM; human review for high blast-radius. Where does each earn its place, what confidence, and how does it ESCALATE? How does this interact with the resolution cascade (T0 already hits the same authorities)? Recommend the cascade or argue against one.` },
  { id: 'TY4', slug: 'retyping_versioning_order', q: `Is type FIXED or RE-ADJUDICABLE? The design says "retyping is retroactively clean in P2 after rebuild (D7)", so retyping must exist. (1) Specify the mechanism: is type a versioned, append-only decision like resolution_decisions (a type_decisions ledger with superseded_by)? (2) The CIRCULAR DEPENDENCY: domain/range validates relations but needs entity types; types come from the same extraction that yields relations. What is the correct ORDER OF OPERATIONS (type subject + object first, THEN validate the relation's domain/range) so it isn't circular? (3) When an entity is RETYPED, what happens to relations previously validated/rejected under the old type — re-validate? how, given rebuild-first (D7)? Recommend the data model + order + retyping ripple.` },
  { id: 'TY5', slug: 'ambiguity_subtype_dumping', q: `The HARD CASES. (1) POLYSEMY/METONYMY: "Washington"/"Apple"/"transformer"; "the White House said" (Organization, not Place). How does context-dependent typing handle these, and what's the fallback when genuinely ambiguous? (2) SUBTYPE granularity: does the extractor pick the leaf subtype (ResearchPaper) or the core (Document), and who refines core->subtype? Coarse-to-fine recommendation. (3) The Concept DUMPING-GROUND risk (Concept is our broadest, fuzziest type and the hardest ER case): evidence this happens in real systems, and mitigations (an explicit other/Thing floor? monitoring Concept growth? refusing to type rather than dumping?). Recommend handling for each.` },
]
const qResults = await parallel(QS.map(Q => () =>
  agent(
`Rigorous research analyst. Answer with EVIDENCE (cite sources/URLs + repo file:line); distinguish verified fact from inference; flag what you couldn't verify; do NOT invent benchmark numbers. ${WEB}

Read: ${OUT}/repo_findings/*.md (short), ${DESIGN}, ${GAP}, and the cloned repos under ${CTX}/ (graphiti, cognee, lightrag, graphrag, GLiNER, GLiREL) as needed.

QUESTION ${Q.id}: ${Q.q}

Markdown: (1) Key findings; (2) Evidence & detail with citations; (3) Confidence & gaps; (4) Recommendation for ugm (concrete, tied to D15/D17/D18/D21/D22).
Write to ${OUT}/questions/${Q.id}_${Q.slug}.md (Write tool). Return: file path + 4 highlights + confidence (high/medium/low).`,
    { label: `${Q.id}:${Q.slug}`, phase: 'Research' }
  )
)).then(rs => rs.filter(Boolean))
log(`Research done: ${qResults.length}/${QS.length}`)

// ---------- Phase 3: verify ----------
const VERS = [
  { slug: 'facts', q: `Fact-check load-bearing claims across ${OUT}/questions/*.md and ${OUT}/repo_findings/*.md: do graphiti/cognee/lightrag/graphrag/GLiNER actually type entities the way the analyses claim (re-check source under ${CTX}/)? Any benchmark/F1/coverage numbers traceable? External-authority typing claims (Wikidata P31, ORCID->Person, LEI->Org) correct? Output: claim | where | verdict (confirmed/unverified/likely-wrong) | note.` },
  { slug: 'completeness', q: `Completeness & coherence critic over ${OUT}/questions/*.md. What's MISSING (a typing sub-problem unaddressed)? Where do the answers CONTRADICT each other (esp. TY1 pipeline position vs TY3 cascade vs TY4 order-of-operations — do they compose into ONE coherent design)? What's OVERCLAIMED? Pressure-test: does the recommended approach actually resolve the circular dependency; does it handle the deferred-extraction case (value gate); does type-disagreement-as-ER-signal create loops. Output: gaps[], contradictions[], overclaims[], top-5-for-synthesis.` },
]
const vResults = await parallel(VERS.map(V => () =>
  agent(
`Adversarial fact-checker; default skeptical, confirm only with a traceable source. ${WEB}
Task: ${V.q}
Read from ${OUT}/questions/, ${OUT}/repo_findings/, repos under ${CTX}/. Write to ${OUT}/verify/${V.slug}.md (Write tool). Return: file path + 5 key verdicts.`,
    { label: `verify:${V.slug}`, phase: 'Verify' }
  )
)).then(rs => rs.filter(Boolean))
log(`Verify done: ${vResults.length}/${VERS.length}`)

// ---------- Phase 4: synthesize ----------
await agent(
`You are the lead architect. Synthesize the entity-typing research into the BEST COURSE OF ACTION for ugm, ready to drop into the registry design.

Read EVERYTHING: ${OUT}/repo_findings/*.md, ${OUT}/questions/*.md, ${OUT}/verify/*.md (downweight anything flagged unverified), ${OUT}/external_agents/*.md (independent Codex architecture stream + Antigravity landscape stream — reconcile with the Claude takes; if a file is 0 bytes note it failed and proceed), and design docs ${BASE}/plan/designs/registries_design.md + ${BASE}/decisions.md (D15-D24).

Write ${OUT}/SYNTHESIS.md with:
1. "Recommended architecture (TL;DR)" — ~8 bullets: where typing happens, the cascade (if any), mention->entity reconciliation, retyping/versioning, ambiguity & Concept handling, order-of-operations resolving the circular dependency.
2. "The five questions answered" (TY1-TY5): settled answer + confidence + key evidence; note where Codex/Antigravity/Claude agreed or diverged.
3. "Design close" — concrete, ready to apply: (a) the new section to add to registries_design.md (entity typing), (b) the data-model additions (tables/columns), (c) a proposed DECISION text (number it Dxx-typing as a placeholder; note D-numbering continues after the O5 PR's D17-D24), (d) how it amends D17/D18/D21.
4. "Open risks & what to spike."
Be decisive and concrete. Return an 8-bullet TL;DR.`,
  { label: 'synthesize', phase: 'Synthesize' }
)

return { repos: repoResults.length, questions: qResults.length, verifiers: vResults.length, synthesis: 'SYNTHESIS.md' }
