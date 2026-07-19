# Reuse hit-rate spike (WP-3.4, lifecycle §6 spike 1)

**Question.** "The reuse hit-rate on real edit patterns is spike 1" — does the D56
machinery (block-hash chunk identity, `extraction_input_hash` matching,
anchor-stabilized packing) actually deliver cost ∝ the edit, and what anchor
parameters make it true?

**Method.** Executable: `src/tests/workers/test_reuse_lifecycle.py` runs the real
chain (convert → structure → chunk → embed → extract, real Postgres, instrumented
fake model provider) over a watched lineage: a 24-paragraph document, then a
version 2 that rewrites exactly one paragraph. Every model call is counted.

## Findings

1. **Without effective anchors, one edit re-flows every later chunk.** Greedy
   budget packing means a paragraph whose token count changed shifts every
   subsequent chunk boundary: at this corpus scale the production anchor defaults
   (modulus 24, min gap 200 tokens) yielded ~0 effective anchors, and the
   one-paragraph edit re-hashed 7 of 12 chunks — extraction re-ran on 8. This is
   the exact failure amendment A2 exists to prevent; the parameters, not the
   mechanism, were wrong for the scale.

2. **Anchor spacing of ≈1–2 chunk budgets contains the re-flow.** A parameter
   sweep at this scale (≈9-token paragraphs, 25-token budget):

   | modulus | min gap (tokens) | chunks | re-hashed after 1-paragraph edit |
   |---|---|---|---|
   | 24 | 200 (defaults) | 12 | **7** |
   | 6 | 20 | 13 | 5 |
   | 3 | 10 | 13 | 3 |
   | **4** | **15** | 14 | **1** |

   The working ratio: mean anchor spacing ≈ 1.5 chunk budgets, min gap ≈ 0.6
   budgets. The production defaults (modulus 24, gap 200 against a 400-token
   budget) sit near the same ratio for production-sized blocks (~50–150 tokens);
   what this spike establishes is the *ratio to keep* when tuning, and that the
   defaults must be re-measured against a real corpus's block-size distribution
   (D22 — numbers are starting points).

3. **With containment, the measured economy** (14-chunk document, 1 paragraph
   edited):

   | metric | version 2 cost |
   |---|---|
   | chunks re-extracted (Selection calls) | **3** of 14 — the changed chunk + its two neighbors (their bundles changed → their `extraction_input_hash` changed; correct by construction) |
   | context-prefix generations | **1** (only the changed chunk; neighbors keep their own stored prefixes — same content hash) |
   | embedding calls | **1** (same: unchanged chunks copy their prior vector) |
   | **reuse hit rate** | **0.79** (11/14 chunks fully reused) |

4. **Re-attachment is exact.** Every reused chunk's `chunk_claims` occurrence
   links point at the *same immutable claim rows* as version 1 (verified id-set
   equality), and carried-forward prefixes are byte-identical (A3: LLM output is
   never regenerated for unchanged regions). Delta-only downstream holds by
   construction: E3 reads claims by origin chunk, and reused chunks have no
   origin claims in the new version — only occurrence links.

## Threshold adjustments

- No production constant changes in this WP: the defaults stay
  `modulus 24 / gap 200 / budget 400` pending measurement against a real corpus
  (the spike's scale is deliberately miniature). The binding takeaway is the
  ratio (anchor spacing ≈ 1–2 budgets) and the failure mode to watch (hit rate
  collapsing to ~0 when anchors are sparser than a few budgets).
- The neighbor re-extraction cost (2 extra chunks per edit) is the designed
  price of bundle-aware keys; no attempt to shrink it — a chunk whose context
  changed genuinely needs re-reading.
