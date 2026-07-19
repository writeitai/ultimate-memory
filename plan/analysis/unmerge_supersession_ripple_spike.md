# Un-merge ↔ supersession ripple spike (WP-2.7, registries §11 spike 3)

**Question.** "Confirm relation validity windows closed under a merged identity are
correctly re-adjudicated on un-merge — this is where silent supersession failure
lives." What actually happens when a supersession was decided while two entities
were (wrongly) one, and the merge is later reversed?

**Method.** Executable: the full scenario runs against the real machinery in
`src/tests/spine/test_unmerge_ripple.py` — merge, supersede across the merged
identity, un-merge, inspect every row.

## Findings

1. **Without identity-set blocking, the ripple cannot even form — but for the wrong
   reason.** Relations keep their original endpoint ids across a merge (a merge is a
   redirect, never a rewrite — D21), and supersession blocking was endpoint-exact. So
   an absorbed entity's employment spell was *invisible* to the survivor's
   supersession: no cross-identity closure ever happened, hence nothing to
   re-adjudicate on un-merge — and, worse, a genuine job change reported against the
   survivor could not close the absorbed endpoint's spell while the two were believed
   to be one person. That is an under-supersession hole, the mirror image of the
   silent failure the spike worried about.

2. **Fix applied: identity-set blocking.** The supersession block now spans every
   endpoint that redirects to the subject's survivor root (a recursive walk in
   `_BLOCK_CANDIDATES`). While merged, the identity's history is one person's
   history: "Robert moved to NewCo" correctly closes the spell recorded under the
   absorbed "R. Klein" endpoint. Locked by test.

3. **The ripple is real after the fix, and it is flagged — never silently resolved
   in either direction.** On un-merge, every live `supersede` adjudication whose two
   sides sit on the split pair (closed endpoint on one side, superseding endpoint on
   the other) is flagged into the review queue (`split_cluster`, reason
   `unmerge_supersession_ripple`, both relation ids and the un-merge event attached,
   `expected_impact` above the routine band). The closed window is **not**
   automatically reopened: the closure *may still be right* (the two people might
   genuinely have had those spells) and a mechanical reopen would be the same silent
   overwrite in reverse. A reviewer (or the future reviewer agent) decides; the
   `restore_support`-style verdict machinery from WP-2.6 is the template for the
   split-verdict tooling when it lands.

4. **Same-identity closures do not ripple.** An un-merge of an unrelated pair flags
   nothing — no queue noise. Locked by test.

## Threshold adjustments

- Ripple review items carry `expected_impact = 1.0` (blast 2 × (1 − 0.5)) — above
  routine `support_withdrawn` items (0.5), below hub merges: they surface promptly
  without outranking catastrophic-merge review. A starting point.
- No change to the supersede margin: the coordinate failure the spike names (silent
  wrong closure) is addressed structurally (flag-on-split), not by tightening the
  margin — a tighter margin would trade it for under-supersession within genuinely
  single identities.

## Stance-holder resolution note (D59, the second half of WP-2.7)

The stance path (attributed claim → observation anchored on the holder) was
end-to-end proven in WP-1.4/2.5; the WP-2.7 check adds the guard test that the
stance's *content* never becomes a fact: "the team considers Atlas a success"
anchors an observation on the team entity only — no relation or observation about
Atlas is derived. Holder resolution rides the ordinary cascade (T0–T4), so its
quality is measured by the resolution suite's per-type P/R rather than a separate
stance eval; a stance-specific golden stratum is worth adding when WP-0.6's
labeling tooling exists (recorded as a follow-up, not built speculatively).
