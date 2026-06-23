# Fact-check: load-bearing numbers & external claims in claimify_research

**Scope.** Every load-bearing NUMBER and external claim across `questions/C1–C8` and
`repo_findings/*.md` was re-checked against the primary sources:
- Claimify paper markdown `_additional_context/claimify_deshwalmahesh/paper_text.md` (read in full at cited lines).
- PDFs in `_additional_context/claimify_papers/` — Molecular Facts (2406.20079), DnDScore (2412.13175) — extracted with `pdftotext -layout` and grepped at the cited tables.
- Cloned repos under `_additional_context/` (deshwalmahesh, claimsmcp, claimeai, veriscore, factscore, safe, molecular_facts) re-opened at file:line.
- The naive single-chunk baseline (the extract-everything anti-pattern E2 must avoid), described conceptually below.

**Verdict legend.** confirmed = matched source exactly (or within a trivial ±1-line citation drift).
unverified = could not confirm from available sources. likely-wrong = source contradicts the claim.

**Headline:** The research is unusually accurate. Every Claimify paper number, every Molecular
Facts / DnDScore number, every repo mechanic, and every baseline-extractor defect checked out. The only
issues are (i) a handful of ±1-line citation drifts (non-load-bearing), and (ii) one over-stated
framing about the verbatim-substring grounding gate that the corpus itself contradicts internally.

---

## A. Claimify paper — metrics & stage mechanics

| Claim | Where | Verdict | Corrected source / note |
|---|---|---|---|
| Entailment: Claimify 99.0, VeriScore 99.2, SAFE 96.6, DnD 89.1 | C1:49,213-216; C4:58; C6:123 | confirmed | Table 1, `paper_text.md:197-202` |
| Claimify vs VeriScore entailment tie p=0.145; other pairs p<0.001 | C1:218; paper §5.1 | confirmed | `paper_text.md:193` |
| Claims counts 12,406 / 7,420 / 22,786 / 27,717 | C1:213-216 | confirmed | Table 1, `paper_text.md:199-202` |
| Element coverage macro-F1 83.7 (Claimify), 62.5 (VeriScore), 56.2 (DnD), 57.3 (SAFE) | C1:52,232-235 | confirmed | Table 2, `paper_text.md:207-210` |
| Element accuracy 87.9; sentence accuracy 91.8 / macro-F1 91.2 | C1:52,232 | confirmed | Table 2, `paper_text.md:207`,226,234 |
| AFaCTA 81.6 acc / 78.7 F1; Factcheck-GPT 81.5 / 78.0 (sentence) | C1:236-237 | confirmed | Table 2, `paper_text.md:211-212` |
| Selection class recall_V 93.9 sent / 87.6 elem; precision_UV 65.6 elem | C4:77,125 | confirmed | Table 2, `paper_text.md:207` |
| Decontext desirable: Claimify 80.6 (G)/80.5 (B); VeriScore 78.3/79.3; DnD 78.4/78.6; SAFE 78.2/78.7 | C1:252-255 | confirmed | Table 3, `paper_text.md:270-273` |
| Result-1 (c=c_max): Claimify 16.3, VeriScore 13.2, DnD 12.9, SAFE 10.4 | C1:252-255 | confirmed | Table 3, `paper_text.md:270-273` |
| Bing desirable: Claimify beats all except VeriScore (p=0.159); Google all p<0.001 | C1:258 | confirmed | `paper_text.md:261` |
| Ablation: remove Selection → element-F1 83.7→54.4; detector-only→74.7; remove Disamb→75.9 | C1:267-268; C4:11 | confirmed | Table 4, `paper_text.md:277-284` |
| "Removing Selection caused the largest performance drop" | C4:11; C8:27,386 | confirmed | `paper_text.md:257` |
| Decontextualization unaffected by ablations (p>0.05) | C1:269 | confirmed | `paper_text.md:257` |
| Table 8 macro-avg: Entailment 97.2, Elem-F1 78.4, Decontext 80.8 — all best/tied | C1:262 | confirmed | Table 8, `paper_text.md:670-672` |
| ≥95% entailed across all models | C1:263,296 | confirmed | `paper_text.md:296` (mistral 95.4, deepseek 97.1, gpt-4o 99) |
| Cost/yield: Claimify 58.3% sentences yield, 3.31 claims/sent, 0.55% invalid; SAFE 98.7%, DnD 96.5%, VeriScore 40.4% | C1:57-58 | confirmed | Table 7, `paper_text.md:627-630` |
| "Cannot be disambiguated" ≤5.4%; Decomposition "no claims" 0.8% | C1:59-61; C3:296; C4:77 | confirmed | `paper_text.md:138,142` (per-model 5.4/3.2/2.4) |
| 73,229 de-duplicated claims | C1:204-205 | confirmed | `paper_text.md:181` (73,681 raw → 73,229 dedup) |
| BingCheck = 396 Copilot answers; 6,490 sentences annotated; 63% verifiable | C1:202; C3; paper §4 | confirmed | `paper_text.md:156,160,218` |
| 4 stages: Sentence-split & context → Selection → Disambiguation → Decomposition | C1:19; C3; C7 | confirmed | `paper_text.md:108-142` |
| Context windows: Selection 5 prec/5 foll; Disamb & Decomp 5 prec/0 foll | C1,C2,C3,C5,C8 (many) | confirmed | Appendix D, `paper_text.md:582-583` |
| max_retries=2; temp 0 (0.2 if completions>1); completions 3/3/1; min_successes 2/2/1 | C1:91-96 | confirmed | `paper_text.md:581-589` |
| Selection 3 outcomes (drop / rewrite-verifiable / unchanged); ignores ambiguity & relevance | C1,C3,C4 | confirmed | `paper_text.md:124`; prompt rules `:821-823` |
| Disambiguation: referential + structural; temporal is a sub-type of referential | C1:142-149; C2:102 | confirmed | `paper_text.md:130-132,898` |
| Discard rule = "group of readers reach consensus"; "Cannot be disambiguated" excluded from Decomp even if verifiable | C1:38-40,151-156; C3 | confirmed | `paper_text.md:134-136`; prompt `:97` |
| No external knowledge; no citations; partial-name only if in context | C1,C2,C4,C6 | confirmed | `paper_text.md:900-902,986` |
| Decomposition `[...]` bracket = "John [a celebrity] has called for peace [in the Middle East]" | C1:43-48,186; C3:147 | confirmed | `paper_text.md:144` |
| "[Boston] local council expects its law [banning plastic bags]" bracket example | C1:186 | confirmed | `paper_text.md:1042` |
| Retain-attribution / Statements-and-Actions Rule ("John highlights X" ≠ "X") | C1:179-181; C6:120 | confirmed | `paper_text.md:982,1082` |
| Entailment validated by LLM prompt (NLI abandoned); 20×4=80 claims, 5 conflicts | C1:209; C6:111-123,170 | confirmed | `paper_text.md:189-191` |
| NLI failure example "it"→Plankalkül (antecedent in preceding sentence) | C1:288; C2:204; C6:37 | confirmed | `paper_text.md:682` |
| Entailment judged over sentence+context+question; "if context entails C but S doesn't, conclude S entails C" | C6:122 | confirmed | `paper_text.md:1080` |
| Choi 2021 2-part decontext definition (quoted verbatim) | C2:24,90; C1:76 | confirmed | `paper_text.md:38` |
| Claim def from Ni et al. 2024 ("verifiable facts… objectively verified") | C1:69 | confirmed | `paper_text.md:30` |
| Atomicity deliberately rejected | C1:78-80 | confirmed | `paper_text.md:40` |
| 7 result types; desirable = 1,2,4,7 | C1:245; C8:431 | confirmed | `paper_text.md:88-94,102,275` |
| §2.3 "John Smith supports government regulations" only revealed after verification | C2:106-109 | confirmed | `paper_text.md:60-64` |
| Metadata (Markdown header hierarchy) defined but unused in experiments | C2:184; C5:118 | confirmed | `paper_text.md:112,120` |
| SAFE uses entire response as decontext context | C2:77,193; C5:168 | confirmed | `paper_text.md:605,609` |
| VeriScore context = 3 preceding + 1 following | repo_findings:256; C7 | confirmed | `paper_text.md:603` |
| List-item "- Investing in renewable energy" ambiguity = narrow-window limitation | C4:78; C1:321 | confirmed | `paper_text.md:306` |
| Temporal under-specification ("unemployment rate decreased in California") not flagged | C1:321; C2:102; C4:79 | confirmed | `paper_text.md:310` |
| Molecular Facts criticized for using parametric/world knowledge | C2:339; C7; C8:96 | confirmed | `paper_text.md:286` |
| Baselines = AFaCTA, Factcheck-GPT, VeriScore, DnD, SAFE | C1:203 | confirmed | `paper_text.md:164-173` |

## B. Molecular Facts PDF (arXiv 2406.20079)

| Claim | Where | Verdict | Corrected source / note |
|---|---|---|---|
| Over-contextualization flips SUPPORTED→NOT_SUPPORTED on 1.7%–9.6% of decontextualizations | C2:52,140 | confirmed | mol.txt:380-381,398-399 (§4.5) |
| Table 1: SAFE 3.94% auto / 8.49% potential; SIMPLE 13.42% auto / 23.39% potential | C2:53,138 | confirmed | mol.txt:358-361,380-387 |
| Table 2 human-confirmed non-minimal: SIMPLE 72.5%, SAFE 43.8% | C2:54,141 | confirmed | mol.txt:369-370,398-401 |
| Table 5 ambiguous-bios: SAFE 24/0/76; MOLECULAR 52/24/24 (minimal/non-min/ambiguous) | C2:54,144-145 | confirmed | mol.txt:429-430 |
| Table 3 accuracy: ATOMIC 68.7%, SIMPLE 76.2%, MOLECULAR 74.7% | C2:146 | confirmed | mol.txt:407-410 |
| Avg words MOLECULAR 14.96 vs SIMPLE 15.55 | C2:148 | confirmed | mol.txt:408-410 |
| Criterion 2 Minimality = argmax_{m} |E(m)| (maximize supporting-evidence breadth) | C2:48,126-128 | confirmed | mol.txt:135-140 |
| Criterion 1 Decontextuality / "Molecular Fact" two-criterion definition | C2:123-135 | confirmed | mol.txt:140+, §2.1 |
| Stage 1 sees claim alone + world knowledge; Stage 2 sees claim + full passage | repo_findings:340-353 | confirmed | molecular_prompt.py:10; pipeline_molecular_gpt4.py |
| "Utilize your world knowledge" (the faithfulness departure) | repo_findings:344,380; C2:341 | confirmed | molecular_prompt.py:10 (impls.md says :11 — off by 1) |

## C. DnDScore PDF (arXiv 2412.13175)

| Claim | Where | Verdict | Corrected source / note |
|---|---|---|---|
| Decontext changes FActScore judgment on 19.11% of subclaim pairs | C2:64,169 | confirmed | dnd.txt:401 |
| 16.25% flip false→true; 3.26% true→false | C2:64-66,169-170 | confirmed | dnd.txt:401-411 |
| 48.52% of false→true flips involve a pronoun replacement | C2:65,170 | confirmed | dnd.txt:403-404 |
| Choi's 4 edit types: name completion, pronoun/NP swap, discourse-marker removal, addition (bridging global scope) | C2:29,94-95 | confirmed | dnd.txt:169-171 |
| DnDScore verifies atomic subclaim using decontextualized form as context, vs source document | C6:44-48,133-138 | confirmed | dnd.txt:295-298 (§4.2) |
| Two naive orders both fail (decompose→decontext loses atomicity; decontext→decompose inflates) | C2:58,156-160 | confirmed | dnd.txt §intro/Fig1, :98-100 |
| Authors Wanner, Van Durme, Dredze 2024 | C6:44 | confirmed | dnd.txt:1 (JHU, 17 Dec 2024) |

## D. Cloned repos (re-opened at file:line)

| Claim | Where | Verdict | Corrected source / note |
|---|---|---|---|
| deshwalmahesh hyperparams: 5 / 5-sel-0-disamb-0-decomp; completions 3/3/1; min 2/2/1 | repo_findings:63-69; C1 | confirmed | claimify.py:46-57 |
| deshwalmahesh user template `Question:\nExcerpt:\nSentence:` | repo_findings:74-76 | confirmed | claimify.py:242-247 |
| deshwalmahesh Selection 5 "does NOT matter" / lack-of-info rules | C4:38-42 | confirmed | prompts.py:1-7 |
| deshwalmahesh consensus discard → "Cannot be decontextualized" | repo_findings:107; C2:114 | confirmed | prompts.py:97 (cited as :96 — off by 1) |
| deshwalmahesh "no external knowledge" rule | repo_findings:105 | confirmed | prompts.py:60 |
| **claimsmcp DEVIATION: f=5 for ALL stages** (paper sets f=0 for Disamb/Decomp) | repo_findings:135-143; C1:104 | confirmed | pipeline.py:377,445 (`p=5, f=5`) |
| claimsmcp single structured request per stage, no voting | repo_findings:156-158; C8:51 | confirmed | pipeline.py make_structured_request; no min_successes loop |
| claimsmcp Pydantic SelectionResponse (final_submission Literal; verifiable bool=True thinking aid) | C4:52; repo_findings:152-176 | confirmed | structured_models.py:19,56,85 |
| claimeai windows: sel 5/5, disamb 5/0, decomp 5/0 (paper-faithful) | repo_findings:187-190 | confirmed | config/nodes.py:30-42 |
| **claimeai bug: paragraph split on literal "\\n" (2-char), not real newline** | repo_findings:206-209; C7 | confirmed | sentence_splitter.py:61 |
| claimeai question-agnostic (drops "question" framing) | repo_findings:215-218; C2:253; C5:167 | confirmed | prompts.py:18 ("an excerpt from a text") |
| VeriScore window: context1=`[max(0,i-3):i]`, `<SOS>..<EOS>`, context2=`[i+1:i+2]`, +lead, +question(QA) | repo_findings:259-265 | confirmed | claim_extractor.py:56-68,121-125 |
| FActScore: "Please breakdown the following sentence into independent facts"; BM25 demos; one-sentence, no neighbors | repo_findings:287-294 | confirmed | atomic_facts.py:10,111,115 |
| SAFE revise feeds entire response as context | repo_findings:315-323 | confirmed | classify_relevance.py:252,280-281 (`response=response`) |
| Molecular = no selection; refines every input fact; world-knowledge homonym pass | repo_findings:344-354 | confirmed | molecular_prompt.py:10; pipeline_molecular_gpt4.py |
| Ambiguity-discard rule unique to Claimify across all surveyed systems | C2:115; C4:64-65; C7 | confirmed | repo_findings:381-383 + each repo re-read |

## E. Baseline-extractor diagnosis (the naive single-chunk anti-pattern)

This section diagnoses the *naive single-chunk baseline* — the extract-everything, FActScore-shaped
extractor that ugm's E2 design must avoid. It is a KNOWN ANTI-PATTERN, not a target. Each row below
states a behavior of that baseline conceptually, with the verdict on whether the research corpus
characterized it correctly.

| Claim | Where | Verdict | Corrected source / note |
|---|---|---|---|
| Single structured LLM call per chunk; system prompt = the quoted 5 lines | C1:275-278; C3:92-95; C5,C6,C8 | confirmed | baseline issues one structured extraction call per chunk; the 5-line system prompt is reproduced verbatim in the corpus |
| User msg = only chunk identifier + evidence identifier + chunk text (no neighbors/question/title) | C2:81; C3:96; C5:20 | confirmed | baseline user message carries only chunk id + evidence id + chunk text, with no neighbors, question, or section title |
| The extracted-claim schema = {claim_text, claim_kind, evidence_quote, confidence} | C3:99; C6:75 | confirmed | baseline extracted-claim record has exactly these four fields |
| Grounding gate: `_normalize(verbatim evidence-quote field) not in _normalize(chunk text)` → `evidence_quote_not_found_in_chunk` | C1:281; C2:42; C3:136; C6:71 | confirmed | the verbatim-substring grounding gate normalizes both sides and rejects with that reason code when the quote is not a substring of the chunk |
| `_normalize` = whitespace-collapse + casefold | C2:216; C6:72 | confirmed | normalization in the grounding gate is whitespace-collapse plus casefold |
| Rejected claims silently dropped (skip-and-continue on non-acceptance) | C3:43; C8:75 | confirmed | the per-chunk extraction orchestration drops any non-accepted claim with no record |
| Content-derived claim-id over (evidence_id, chunk_id, claim_text) = sha256 → same fact in 2 chunks = 2 ids | C3:69-76,203-208 | confirmed | the content-derived claim-id function hashes evidence id + chunk id + claim text, so the same fact appearing in two chunks yields two distinct ids |
| supporting_chunk_ids / supporting_evidence_ids always the single originating chunk | C3:71 | confirmed | the per-chunk extraction orchestration sets both supporting-id lists to the lone originating chunk |
| Chunk model already carries section-parent reference, character offsets, content hash, entity hints (window data exists, unused) | C1:341; C2:297; C3,C5,C8 | confirmed | ugm's E1 chunk model provides, BY DESIGN, the chunk's section-parent reference and character offsets, the chunk content hash, and entity hints — yet the naive baseline ignores all of this window data |
| The claim record has NO verbatim evidence-quote field / NO span offsets; quote is discarded after the grounding gate | C6:77-82 | confirmed | the persisted claim model omits the evidence-quote field and span offsets; the baseline throws the quote away once the grounding gate passes |
| Claim-kind labels incl. PREFERENCE / OBSERVATION / RELATIONSHIP (no verifiability filter) | C3:54,174; C4:31 | confirmed | the baseline's claim-kind labels include PREFERENCE / OBSERVATION / RELATIONSHIP with no verifiability filter |
| Contract test pins: verbatim quote accepted, non-substring rejected with that reason | C6:84-89 | confirmed | the baseline's grounding-gate contract test pins exactly this: a verbatim quote is accepted and a non-substring quote is rejected with the reason code |
| **Defect (a) no surrounding context / no coref input** (FActScore-shaped) | C3 defect a; C8 | confirmed | baseline assembles no neighbor context and provides no upstream context prefix |
| **Defect (b) verbatim-substring grounding gate hostile to decontextualization** | C3 defect b; C6; C7 | confirmed (with caveat) | real; but see note ★ below — only the verbatim evidence-quote field, not the claim text, is substring-gated |
| **Defect (c) "extract ALL atomic claims", no Selection** | C3 defect c; C4 | confirmed | the baseline system prompt instructs extracting every atomic claim, with no Selection stage |
| **Defect (d) no ambiguity discard path** | C3 defect d | confirmed | no abstain state in the baseline schema or flow |
| **Defect (e) chunk-keyed identity, no cross-chunk convergence** | C3 defect e | confirmed | the content-derived claim-id function and single-chunk supporting-id lists prevent any cross-chunk convergence |
| E1 "context prefix" is a surrounding-ugm-stage property, absent from the naive baseline's chunk text | C3:307-311 (flagged unverified) | confirmed | the naive baseline has no contextual-retrieval prefix; its chunk text is a bare semantic-chunk piece. E1.5 and E3 are the surrounding ugm stages that the baseline lacks entirely |

★ **Caveat on Defect (b) framing (likely-overstated, not wrong).** C3:42-44 and C6:24-28 imply the
substring gate forces the *claim_text* to stay contextual / non-standalone. The grounding gate actually
gates only the verbatim evidence-quote field, and the baseline's own contract test accepts a
decontextualized `claim_text="The target ERP is NetSuite."` because its separate `evidence_quote`
is a substring. So the schema already separates the two
fields and a decontextualized claim *can* pass — the real defect is that the **prompt** says
"supported by an exact quote copied from this chunk," nudging the model to keep the quote (and thus
the claim) close to surface form, plus the quote cannot point at a neighbor. C7:138-141 states this
correctly ("the schema already separates claim_text from evidence_quote… the bug is that the prompt
is silently nudging the model to rewrite the quote too"). Net: the defect is real and the fix
direction is right; the C3/C6 phrasing overstates the mechanism. Confidence the defect exists: HIGH.

---

## F. Citation-precision nits (non-load-bearing, all ±1 line)

- deshwalmahesh consensus rule cited as `prompts.py:96`; actually `:97` (repo_findings:107; C2:114).
- Molecular world-knowledge line cited as `molecular_prompt.py:11`; actually `:10` (repo_findings:380).
- The chunk model's character-offset/field block: the start-offset field sits one line earlier than cited (C5:100).
- Contract test ranges `:14-27` / `:30-45`; actual `:14-28` / `:31-45` (C6:84-89).
None change any conclusion.

## G. Could-not-verify / out-of-scope

- verifact PDF (2505.09701) is present but **not cited** in any question — no claims to check.
- Transfer of single-deployment benchmark numbers to ugm's corpora: correctly self-flagged as
  MEDIUM/assumption throughout (C2:238-245, C6:193-195) — not a factual error.
- Prompt-caching economics (C5 §2.5: read 0.1×, write 1.25×, break-even 2, Opus 4096-tok minimum):
  sourced to the `claude-api` skill doc, not re-verified here (out of the paper/repo/code scope).
- The naive baseline wraps an API timeout error into a dedicated extraction-timeout error. Tangential
  to the questions, but note it sits against the ugm design principle that the extraction pipeline
  should not introduce timeouts.
