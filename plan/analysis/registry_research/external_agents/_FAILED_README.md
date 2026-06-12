# External-agent cross-checks: FAILED (registry round)

The four planned independent cross-checks (Codex R2/R6, Antigravity R5/R8) produced **0 bytes**.

**Cause:** `codex exec` / `agy` were launched as background jobs without redirecting stdin.
They printed `"Reading additional input from stdin..."` and blocked forever waiting for an
EOF that never arrives in a detached background context (~88 min, no output, then killed).

**Fix (applied to the O3 / value_gate_research round):** redirect stdin from /dev/null —
`codex exec --yolo --model gpt-5.5 "$(cat prompt)" < /dev/null > out.md`. Verified working.

**Impact:** R2/R5/R6/R8 in SYNTHESIS.md are therefore SINGLE-SOURCE (Claude only); confidence
on those four is carried one notch lower. Independent scrutiny still came from the five
`verify/*.md` fact-checkers, which re-opened cloned source at file:line and confirmed the
numbers. See SYNTHESIS.md "Provenance note" and verify/completeness.md G1.
