# Key findings

- The naive single-chunk baseline is structurally unable to produce standalone claims: the extractor accepts one chunk and sends only the chunk id, evidence id, and chunk text to the model. Orchestration maps the extraction call over chunks independently, including the concurrent path. There is no document title, section path, E1 prefix, or neighbor text. This is the known anti-pattern that ugm's E2 must avoid.
- The extract-everything baseline's prompt and validator create the wrong incentive. The prompt asks for claims supported by an "exact quote copied from this chunk", while the verbatim-substring grounding gate accepts only if the normalized verbatim evidence-quote field is contained in the normalized chunk text. A good decontextualized claim rewrites pronouns, acronyms, ellipses, and relative time, so this gate preserves contextual claims and drops better ones.
- Claimify's relevant abstraction is not "copy an evidence quote"; it is sentence-local extraction with explicit context. Claimify creates per-sentence context from configurable preceding sentences, following sentences, and optional metadata such as header hierarchy [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:112). Its Disambiguation stage detects referential and structural ambiguity [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:128), discards sentences when ambiguity cannot be resolved [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:136), and then Decomposition emits decontextualized factual claims [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:142).
- Discarding unresolvable ambiguity is a precision feature, not lost work. Claimify reports the largest `Cannot be disambiguated` rate as 5.4% across tested models, with GPT-4o at 3.2% [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:138), [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:148). The full system reached 99% entailment on 12,406 claims and 87.9% element-level coverage accuracy [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:193), [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:197).
- Minimality is the guardrail against "helpful" hallucination. Molecular Facts defines decontextuality as making a rewritten claim interpretable on its own while preserving its contextual truth conditions, and minimality as selecting the version supported by the largest evidence set [molecular_facts.txt](/tmp/ugm_claimify_sources/molecular_facts.txt:140), [molecular_facts.txt](/tmp/ugm_claimify_sources/molecular_facts.txt:135). The paper found true non-minimality in 1.7% to 9.6% of decontextualizations [molecular_facts.txt](/tmp/ugm_claimify_sources/molecular_facts.txt:397), [molecular_facts.txt](/tmp/ugm_claimify_sources/molecular_facts.txt:400).
- Grounding should be split into provenance and entailment. Store a verbatim source span and character offsets for audit, but validate `claim_text` by checking that the source context entails it. DnDScore explicitly identifies the verification ambiguity created by augmented claims and proposes verifying a specific subclaim with its decontextualized form as relevant context [dndscore.txt](/tmp/ugm_claimify_sources/dndscore.txt:123), [dndscore.txt](/tmp/ugm_claimify_sources/dndscore.txt:292).
- ugm already has the necessary input material. E0 creates PageIndex hierarchy and summaries; E1 creates semchunks with an LLM context prefix and PageIndex references [overall_design.md](/Users/jpuc/code/moje/ultimate_memory/ugm/plan/designs/overall_design.md:92), [overall_design.md](/Users/jpuc/code/moje/ultimate_memory/ugm/plan/designs/overall_design.md:94). By design, ugm's E1 chunk model already carries the chunk's section-parent reference, character offsets, and entity hints.
- The concrete replacement is: `claim_text` is standalone; `source_span_text` is verbatim; `source_char_start`/`source_char_end` point into the source document or chunk; `decontextualization_changes` records what was rewritten; `grounding_status` records deterministic span containment plus model entailment. This keeps D7 because every input, prompt/model version, span, and entailment decision is stored in Postgres; it keeps D12 because claim IDs remain deterministic over evidence/chunk/span/claim/prompt version and workers are idempotent.

# 1. Decontextualization

**Anti-pattern baseline defect.** The naive single-chunk baseline treats "grounded" as "quote copied from this chunk." Its system prompt instructs the model to trust the chunk boundary, not split or merge chunks, and return only claims directly supported by an exact quote from the chunk. The extracted-claim schema has only `claim_text`, `claim_kind`, the verbatim evidence-quote field, and `confidence`. Validation then checks quote containment and silently skips rejected claims. Because the extractor receives one chunk at a time, a chunk beginning "It launched last year" can only produce either a contextual claim with "It" and "last year" or an unsupported-looking rewrite. Both outcomes are bad for E2.

**Precise definition.** A decontextualized claim is a complete natural-language assertion that a verifier or retrieval system can interpret without the source chunk, while preserving the meaning the assertion had inside the source. Claimify's decomposition prompt defines this as self-contained and meaning-preserving relative to the question, context, and other propositions [structured_prompts.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_claimsmcp/structured_prompts.py:128). The claimeai reimplementation uses the same two-part definition for propositions: independently understandable and context-meaning preserving [prompts.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimeai/apps/agent/claim_extractor/prompts.py:121). For ugm, that means:

- Referential decontextualization: replace pronouns, noun phrases, partial names, and intra-list references when the context resolves them. Claimify names referential ambiguity and gives "They", "the policy", and "next year" as examples [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:130).
- Structural decontextualization: resolve grammar that supports multiple readings, including attribution boundaries between what a source says and what an author infers [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:132).
- Temporal decontextualization: resolve relative phrases such as "next year" and "last winter" only when the date anchor is present. Claimify treats temporal ambiguity as referential ambiguity in its prompt [prompts.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/src/prompts.py:56).
- Entity naming and acronym expansion: expand partial names and acronyms when the full form is provided in context, and leave them unchanged otherwise to avoid factual additions [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:146).

**Claimify stages.** Claimify runs Selection, Disambiguation, then Decomposition. Selection keeps only verifiable content or drops the sentence [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:124). Disambiguation asks whether ambiguity has a clear resolution using the question and context [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:128). The prompt's operational test is whether readers shown the same context would likely agree on the interpretation [prompts.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/src/prompts.py:96). If they would not, the sentence is marked `Cannot be decontextualized` and skipped [claimify.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/src/claimify.py:123), [claimify.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/src/claimify.py:453). Decomposition then splits the disambiguated sentence into standalone claims, preserving attribution such as "John highlights..." instead of turning it into a naked normative claim [prompts.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/src/prompts.py:119).

The prompt-level rules are explicit: "Do NOT use any external knowledge" [prompts.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/src/prompts.py:60), return `Cannot be decontextualized` when consensus would fail [prompts.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/src/prompts.py:71), and emit the "simplest possible discrete units" [prompts.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/src/prompts.py:103).

**Inference for ugm.** The single-call ugm extractor can collapse Claimify's three stages into one structured-output call only if it keeps the same decisions explicit in the schema: selected/dropped, disambiguation status, atomic claims, and discard reasons. Otherwise the model will hide ambiguity resolution inside unsupported rewrites, and downstream validation will not know whether a rewrite is a supported resolution or an invention.

# 2. Minimality trade-off

**Verified desiderata.** Molecular Facts makes the key correction: standalone is necessary but not sufficient. It defines decontextuality as a rewritten claim that has the same contextual truth conditions when interpreted alone [molecular_facts.txt](/tmp/ugm_claimify_sources/molecular_facts.txt:129), [molecular_facts.txt](/tmp/ugm_claimify_sources/molecular_facts.txt:140). It defines minimality by choosing the decontextualized statement with the largest supportable evidence set, because unnecessary descriptors shrink the set of documents that can support the claim [molecular_facts.txt](/tmp/ugm_claimify_sources/molecular_facts.txt:135). Its examples show the problem: "Ann Jansson" may need "Swedish footballer", but adding birthdate and club history is non-minimal because those extra facts also require verification [molecular_facts.txt](/tmp/ugm_claimify_sources/molecular_facts.txt:155), [molecular_facts.txt](/tmp/ugm_claimify_sources/molecular_facts.txt:175).

**Concrete numbers.** Molecular Facts found automatically flagged potential non-minimality in 8.49% of SAFE-decontextualized claims and 23.39% of simple decontextualized claims [molecular_facts.txt](/tmp/ugm_claimify_sources/molecular_facts.txt:359). After human review, 43.8% of SAFE's flagged subset and 72.5% of the simple baseline's flagged subset were truly non-minimal [molecular_facts.txt](/tmp/ugm_claimify_sources/molecular_facts.txt:368). In full-dataset terms, the authors state that decontextualization can create true non-minimal cases in 1.7% to 9.6% of decontextualizations [molecular_facts.txt](/tmp/ugm_claimify_sources/molecular_facts.txt:397), [molecular_facts.txt](/tmp/ugm_claimify_sources/molecular_facts.txt:400). On ambiguous biographies, all decontextualization methods beat atomic claims on accuracy: atomic 68.7%, SAFE 73.4%, Molecular 74.7%, Simple 76.2%; average lengths rose from 7.61 words to 9.86, 14.96, and 15.55 words respectively [molecular_facts.txt](/tmp/ugm_claimify_sources/molecular_facts.txt:405). The design implication is not "always add more"; it is "add the least context needed to make the claim uniquely interpretable."

**Instruction policy.** The extractor should say: add only information necessary to resolve a reference, time, acronym, ellipsis, section-scoped subject, or attribution boundary. Do not add background descriptors merely because they are true or helpful. If two descriptors both resolve the ambiguity, choose the one most directly stated in the local context and most likely to appear in ordinary evidence. If no local descriptor resolves it, discard the claim or leave the unresolved token only if the token is already a usable standalone name. This follows Molecular Facts' prompt instruction to minimally modify the claim and use contextual information for pronouns/incomplete names [decontext_prompt.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/molecular_facts/src/prompts/decontext_prompt.py:7), [decontext_prompt.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/molecular_facts/src/prompts/decontext_prompt.py:11).

**Inference for ugm.** Minimality matters more in ugm than in one-off fact checking because E2 claims become embeddings, E3 relations, supersession candidates, and K-layer source material. Over-contextualized claims reduce deduplication and relation merging: "Alice Smith, the former 2019 interim CFO of X, approved Y" will not cluster with "Alice Smith approved Y" even if the role is irrelevant. Under-contextualized claims create false merges and false contradictions. The right invariant is: every added token must be justifiable by one entry in `decontextualization_changes`.

# 3. Extractor context bundle

**Verified available context.** ugm's E-plane design already creates the ingredients. E0 stores original files, Markdown, PageIndex hierarchy, and node summaries [overall_design.md](/Users/jpuc/code/moje/ultimate_memory/ugm/plan/designs/overall_design.md:92). E1 creates semchunks, an LLM context prefix per chunk, embeddings, and references to document plus PageIndex node [overall_design.md](/Users/jpuc/code/moje/ultimate_memory/ugm/plan/designs/overall_design.md:94). E2 is explicitly Claimify plus coreference in the extraction call [overall_design.md](/Users/jpuc/code/moje/ultimate_memory/ugm/plan/designs/overall_design.md:101). D19 says no claim leaves E2 with a dangling pronoun and that this guarantee is satisfied inside the E2 extraction call [decisions.md](/Users/jpuc/code/moje/ultimate_memory/ugm/decisions.md:384).

**Minimal context bundle.** Feed one target chunk at a time, but not in isolation:

1. Stable document header: `document_id`, title, source URI, publication/creation date if known, and language. Title and dates are cheap and resolve "this report", "the company", and relative time anchors.
2. PageIndex path: section heading path plus PageIndex node summary. Claimify allows optional metadata such as header hierarchy [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:112); ugm PageIndex is exactly that metadata.
3. E1 context prefix for the target chunk. This is already generated for every chunk and prompt-cached by design [overall_design.md](/Users/jpuc/code/moje/ultimate_memory/ugm/plan/designs/overall_design.md:94). It is the highest-value compact summary because it was written to make the chunk understandable.
4. Neighbor text: previous and next chunk snippets, capped by tokens and marked read-only context. Claimify uses preceding/following sentence windows; the reference implementation uses five preceding sentences, five following for Selection, and zero following for Disambiguation/Decomposition [claimify.py](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/src/claimify.py:46). VeriScore uses a sliding window with 0-3 preceding sentences and 0-1 following sentence [veriscore.txt](/tmp/ugm_claimify_sources/veriscore.txt:160). Chunk neighbors are ugm's analogue.
5. Known entity hints: entity IDs and canonical names from the chunk's entity hints, if already available. By design, ugm's E1 chunk model carries entity hints. These are hints, not permission to add facts; the source text must still entail the claim.
6. Target chunk text with local line or character coordinate metadata. By design, ugm's E1 chunk model already has chunk-level character offsets, which makes offsets cheap if extraction returns spans relative to the chunk.

**Token discipline.** Use a shared per-document prefix for title, date, PageIndex path, and section summary; then vary only the target chunk and neighbor snippets. That aligns with the existing E1 "context prefix" and prompt-caching design [overall_design.md](/Users/jpuc/code/moje/ultimate_memory/ugm/plan/designs/overall_design.md:94). E1.5 still gates whether E2 runs at all: FULL runs immediately, DEFERRED runs only on triggers, CHUNKS-ONLY stores retrievable chunks without claims [e1_5_value_gate_design.md](/Users/jpuc/code/moje/ultimate_memory/ugm/plan/designs/e1_5_value_gate_design.md:69). This report's proposal is claim-level quality after E2 is invoked; it does not weaken the cheap-first gate.

**Inference for bundle sizing.** Start with: document prefix <= 400 tokens, section path/summary <= 250, E1 prefix <= 250, previous chunk tail <= 350, target chunk full text <= current chunk size, next chunk head <= 250, entity hints <= 150. For long chunks, the target text remains authoritative and neighbors shrink first. If the model cannot resolve a reference within that bundle, the correct answer is `discard_unresolved_context`, not a wider automatic fetch. Wider fetches should be a cheap-first escalation only for high-value chunks, because D4 and D25 require LLM cost to scale with ambiguity and value, not volume [decisions.md](/Users/jpuc/code/moje/ultimate_memory/ugm/decisions.md:66), [decisions.md](/Users/jpuc/code/moje/ultimate_memory/ugm/decisions.md:503).

# 4. Grounding without verbatim quotes

**Anti-pattern baseline problem.** The verbatim-substring grounding gate validates only the quote, not the claim. It rejects empty claim text and empty quote text, then checks normalized quote containment in normalized chunk text. It never asks whether `claim_text` follows from the chunk. Therefore a contextual claim like "It launched last year" can pass if the quote exists, while "Project Atlas launched in 2024" can fail unless the model also returns a verbatim quote separate from the rewritten claim.

**Option A: character span pointers.** Keep a verbatim `source_span_text` plus offsets into the target chunk or source document. This is necessary for auditability, provenance, UI highlighting, idempotent debugging, and D7 rebuilds. It is not sufficient for semantic grounding, because a source span can contain "it", "last year", or an elided table header. But it lets validators check a deterministic invariant: the source span bytes match the stored chunk/document text at offsets. This should replace fuzzy normalized substring matching. If offsets are unavailable in first implementation, compute the first exact occurrence of `source_span_text` in the target chunk and store offsets; reject if zero or multiple occurrences unless the model supplied disambiguating offsets.

**Option B: entailment/NLI verification.** Validate `claim_text` by asking whether the source context entails the standalone claim. Claimify evaluates entailment against the combined source sentence, context, and question, and reports Claimify and VeriScore at about 99% entailed claims [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:193), [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:197). VeriScore defines support as requiring all meaningful parts of the claim to be supported by evidence [veriscore.txt](/tmp/ugm_claimify_sources/veriscore.txt:143), [veriscore.txt](/tmp/ugm_claimify_sources/veriscore.txt:147). DnDScore shows why this matters: once a claim is augmented, verification must know which part is the original subclaim and which part is context [dndscore.txt](/tmp/ugm_claimify_sources/dndscore.txt:280), [dndscore.txt](/tmp/ugm_claimify_sources/dndscore.txt:292).

**Option C: store both.** This is the recommended contract. `source_span_text` is verbatim and local; `claim_text` is standalone and may be a rewrite. `source_span_text` answers "where did this come from?" `claim_text` answers "what assertion should retrieval, E3 relation extraction, supersession, and K-layer synthesis reason over?" `decontextualization_changes` explains every non-verbatim addition. This mirrors Claimify's bracketed clarifications: bracketed text flags information implied by context but not explicitly in the sentence [paper_text.md](/Users/jpuc/code/moje/ultimate_memory/ugm/_additional_context/claimify_deshwalmahesh/paper_text.md:144). ugm should not require brackets in final `claim_text`, because they pollute embeddings; instead store changes in a structured side field.

**Option D: self-check pass.** A self-check LLM can be useful as a cheap same-call field or as an escalation, but should not be the only validator. The extractor can output `support_rationale` and `confidence`, but acceptance should be: deterministic span check first, then an independent entailment decision for claims above risk/cost thresholds. For low-risk/high-volume mode, use a small NLI model or distilled verifier as the normal path and frontier LLM only for uncertain entailment. This matches D4's cheap-first cascade philosophy, where exact/fuzzy/small model stages handle clear cases before frontier LLM residue [decisions.md](/Users/jpuc/code/moje/ultimate_memory/ugm/decisions.md:68).

**Recommended grounding contract.** Accept an extracted claim only when all are true:

1. `claim_text` is non-empty, declarative, standalone, and contains no unresolved pronouns or relative temporal references unless the source itself has no resolvable anchor and the term is already a stable name.
2. `source_span_text` is non-empty and exactly equals the substring at `source_char_start:source_char_end` in the target chunk text, or in the source document text when document offsets are available.
3. The standalone `claim_text` is entailed by `source_span_text + minimal_context_bundle`, where context fields are title, date, section path/summary, E1 prefix, and neighbor snippets.
4. Every entity, date anchor, acronym expansion, and attribution added to `claim_text` appears in the minimal context bundle and is recorded in `decontextualization_changes`.
5. Claims with `disambiguation_status != resolved` are not inserted as active claims. Store a dropped-candidate audit row if useful, but do not write to the active claims.

# 5. Concrete proposal for ugm's E2 design

**Schema.** The extracted-claim schema should be a structured boundary model that separates assertion, provenance, and grounding:

```python
class DecontextualizationChange(BaseModel):
    kind: Literal[
        "pronoun_coref",
        "partial_name",
        "acronym_expansion",
        "relative_time",
        "section_subject",
        "ellipsis",
        "attribution",
    ]
    original_text: str
    replacement_text: str
    support_text: str

class ExtractedClaim(BaseModel):
    claim_text: str
    claim_kind: ClaimKind
    source_span_text: str
    source_char_start: int
    source_char_end: int
    disambiguation_status: Literal["resolved", "unambiguous", "discard_unresolved"]
    decontextualization_changes: list[DecontextualizationChange] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
```

For durable rows, add claim-level provenance fields either directly to the claim record or, preferably, to a `claim_support_spans` table keyed by `claim_id`. A claim record that only stores supporting chunk/evidence IDs cannot represent offsets, source span text, verifier version, or decontextualization changes. A support-span table is cleaner because future claims may have multiple source spans.

**Validation design.** The grounding validator should make the deterministic path explicit:

```python
def validate_claim_grounding(
    *,
    chunk: ChunkModel,
    claim_text: str,
    source_span_text: str,
    source_char_start: int,
    source_char_end: int,
    disambiguation_status: str,
    entailment: ClaimEntailmentDecision,
) -> ClaimValidationResult:
    if not claim_text.strip():
        return ClaimValidationResult(False, "claim_text_empty")
    if disambiguation_status == "discard_unresolved":
        return ClaimValidationResult(False, "unresolved_disambiguation")
    if source_char_start < 0 or source_char_end <= source_char_start:
        return ClaimValidationResult(False, "invalid_source_offsets")
    if chunk.text[source_char_start:source_char_end] != source_span_text:
        return ClaimValidationResult(False, "source_span_offset_mismatch")
    if entailment.label != "entailed":
        return ClaimValidationResult(False, f"claim_not_entailed:{entailment.label}")
    if chunk.scope_project is None:
        return ClaimValidationResult(False, "project_claim_requires_project_scope")
    return ClaimValidationResult(True)
```

`ClaimEntailmentDecision` should include `label: Literal["entailed", "not_entailed", "uncertain"]`, `confidence`, `verifier_model`, `verifier_prompt_version`, and `rationale`. For phase 1, the verifier can be an LLM structured-output call. Phase 2 can distill to a small verifier for cheap-first operation.

**Extractor prompt text.** Use one structured-output call per target chunk with shared document prefix and local context. The prompt below is implementation-ready and intentionally forbids external knowledge.

```text
System:
You extract atomic project-memory claims from a target chunk.
Each accepted claim must be standalone: a reader must understand it without the chunk, neighboring chunks, section path, title, or other claims.
Each accepted claim must also be grounded: the target chunk plus the supplied local context must entail the claim.

Resolve pronouns, partial names, acronyms, relative dates, section-scoped subjects, ellipses, and attribution only when the supplied context makes the resolution clear.
Use the minimum added context needed for the claim to stand alone.
Do not add background facts, world knowledge, or plausible details.
If readers shown the same context would not likely agree on the interpretation, discard that candidate.
Do not extract advice, opinions, generic interpretations, examples, or summaries unless the source states a specific verifiable fact about an entity, event, state, decision, obligation, or relationship.

For every claim, return:
- claim_text: standalone rewritten claim
- claim_kind
- source_span_text: exact text copied from the target chunk that supports the claim
- source_char_start and source_char_end: offsets into target_chunk_text for source_span_text
- disambiguation_status: resolved or unambiguous
- decontextualization_changes: one item for each rewrite; support_text must quote the local context that justifies the replacement
- confidence

Reject instead of guessing. Return no claim when support requires external knowledge or unresolved context.

User:
document:
  document_id: {document_id}
  title: {title}
  source_uri: {source_uri}
  document_date: {document_date_or_unknown}
  language: {language}

section:
  pageindex_path: {heading_path}
  pageindex_summary: {section_summary}

target_chunk:
  chunk_id: {chunk_id}
  evidence_id: {evidence_id}
  chunk_char_start_in_document: {chunk_char_start}
  e1_context_prefix: {context_prefix}
  known_entity_hints: {entity_names_and_ids}
  previous_chunk_tail: {prev_tail_or_empty}
  target_chunk_text:
{chunk_text}
  next_chunk_head: {next_head_or_empty}
```

**Cost, rebuildability, idempotency.** Store extraction input hashes, prompt version, model, response JSON, verifier model/version, source offsets, and final decision in Postgres. Plane E is the source of truth, and Postgres is already defined as the spine for chunk metadata, claims, evidence, validity, processing state, and costs [overall_design.md](/Users/jpuc/code/moje/ultimate_memory/ugm/plan/designs/overall_design.md:45). D7 requires rebuilds to come from Postgres-derived state, not re-running mutable model endpoints [decisions.md](/Users/jpuc/code/moje/ultimate_memory/ugm/decisions.md:118). D12 requires per-document Cloud Tasks workers to be idempotent by content hash plus processing version [decisions.md](/Users/jpuc/code/moje/ultimate_memory/ugm/decisions.md:216). Therefore claim IDs should include `evidence_id`, `chunk_id`, `source_char_start`, `source_char_end`, normalized `claim_text`, and `claim_extraction_prompt_version`. If the same task is retried, it writes the same rows or no-ops. If the prompt changes, it creates a new extraction version rather than mutating history.

# Concrete recommendation for ugm's E2 design

1. Use `source_span_text` plus offsets instead of a single verbatim evidence-quote field; keep source spans verbatim and claims rewritten. Claim-record support IDs remain useful but are not enough for grounding.
2. Have orchestration extract from a context bundle rather than a bare chunk, where the bundle contains target chunk, E1 prefix, title/date, PageIndex path/summary, previous/next snippets, and entity hints. The target chunk remains the only place offsets may point.
3. Use `validate_claim_grounding` instead of substring validation: deterministic offset match plus entailment label. A normalized substring check can remain only as a fallback for legacy rows, not as the canonical gate.
4. Add an entailment verifier after extraction. Start with LLM structured output; record prompt/model/version/rationale. Later distill to a small verifier and escalate uncertain cases.
5. Persist raw extraction responses and dropped unresolved candidates for audit, but insert only `resolved` or `unambiguous` entailed claims into active E2 claims.
6. Keep brackets out of final `claim_text`; store rewrites in `decontextualization_changes`. This preserves clean embeddings while retaining the Claimify-style audit trail for inferred context.
