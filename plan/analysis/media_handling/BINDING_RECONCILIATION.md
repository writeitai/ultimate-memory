# D65 Binding — Codex review reconciliation

Codex (gpt-5.6-sol, xhigh) adversarially reviewed the D65 binding package
(`external_agents/codex_binding_review.md`: 12 findings — 7 must-fix, 5 should-fix, verdict
"not yet implementation-ready"). Reconciliation (final say: internal): **all 12 findings
accepted** — every must-fix was a genuine translation defect from the SYNTHESIS into binding
text, not a re-litigation of settled choices. What changed, by finding:

| # | Finding (short) | Resolution |
|---|---|---|
| 1 | Representation generations promised but not modeled — a re-conversion would overwrite the coordinate system historical claims resolve against | **Bound the object**: `document_representations` (immutable; route + component graph + output hashes + artifact URIs), representation-addressed artifact paths (`…/<content_hash>/<representation_id>/…`), `document_versions.current_representation_id` swapped only on chain completion; `content_objects` "converted once" corrected to per-toolchain. Schema §6, e0 §2, media §1/§6 |
| 2 | Basis tuple not full (structurer missing) and conflating three identities | **Three identities bound apart**: source snapshot = `version_id`; representation = `representation_id`; extraction basis = `(representation_id, blockizer_version, structurer_version, extractor_version)`, persisted on occurrence records. Lifecycle §1/§3, D54/D65 notes |
| 3 | Locator union incomplete (no `source_range`, no `precision` on video_region, pinning/time-base/coordinate conventions undefined) | **One normative schema** in media §4 (five kinds incl. `source_range`; every variant carries `precision`; 1-based pages, normalized top-left rects, half-open ms intervals on the manifest-declared timeline; pin lives on the carrier record naming version + representation; locator lists per span). e1 §2 syncs and points at the normative home |
| 4 | Section-grain `evidence_mode` not deterministically derivable (one section mixes observation + interpretation) | **Mode-homogeneous labeled ranges** are a converter output-contract obligation (interpretations emitted separately from observations); claims crossing modes take the **most-mediated** mode. Media §2/§5; disclosure eval gains a mixed-content fixture condition |
| 5 | No schema home for disclosure/locators; envelope's singular `derivation` destroys claim-level association | **Occurrence-grain home bound**: `chunk_claims` gains `derivation_kind`/`evidence_mode`/`source_locators`; chunks/sections gain `representation_id`; envelope carries derivation + locators on **evidence-grain items only** (facts hydrate to per-claim records). Schema §7, retrieval §5 |
| 6 | P3 stub contract not updated; `#t=873` is not a filesystem operation; `hydrate` had no locator parameter | e0 §5 stub frontmatter gains `raw_uri` + duration + preview links; media §8 states fragment = display rendering, mounted consumers seek locally with the structured locator, unmounted via `hydrate depth=bytes` + locator (signature updated, retrieval §3) |
| 7 | Manifest weaker than adopted (no coverage/gaps/warnings/output hashes/execution context; acoustic events dropped) | Manifest bound as the route's **complete self-account** (component graph, D61 execution context, output hashes, coverage policy+result, gaps/warnings, selected tracks); **Acoustic events** bound as a capability-dependent route section. Media §2, e0 §3 |
| 8 | Single-table/single-model `media_segments` assumption; all-or-nothing boundary; eval under-tests | **Logical target over per-modality subindexes** (modality + embedding family/version/dimension per row; rank fusion only across families); capability advertised **per query→target modality pair**, typed `boundary` per missing pair. Media §7, retrieval §3, P1 eval |
| 9 | `e0_converter_router_versioned` contradicts D65; media checks encode the gaps above | Old check updated to the generalized contract + representation immutability; all five media checks updated to the resolved schemas (locators, representation object + swap, mode-homogeneity fixture, capability pairs) |
| 10 | Rule 2 violation: correlation handling deferred to "future confidence policy"; K3 admission spike dropped | **Policy bound now**: distinct-lineage counts are the only confidence input; derivation-family provenance is disclosure-only; correlation-aware adjustment is a documented alternative (not in the system). The K3 dial restored at this review point was later removed with the tier by D73. Media §5/§10 |
| 11 | D65 not self-contained (eighth P3 binding missing; representation object reduced to a tuple; D56 unannotated) | D65 now eight bindings (P3 stubs+previews added; representation object stated); D56 gains a refinement note (representation-aware reuse + occurrence provenance) |
| 12 | overall_design/schema still carry pre-D65 assumptions (artifacts "re-run by converter_version"; P1 target list; no D65 coverage row) | Store table corrected (replayed-not-regenerated; media segments), §4 pipeline names the media routes + representations; schema §16 gains the D65 row |

Nothing was rejected. One deliberate narrowing: finding 5's "dedicated claim-grounding/
evidence-occurrence table" option was resolved *onto the existing `chunk_claims` map* (it
already is the occurrence table; a second one would duplicate it), and finding 2's option to
fold blockizer/structurer into representation identity was resolved as **extraction-basis
coordinates** instead (they are deterministic derivations over the representation, not part
of the converter's reading).
