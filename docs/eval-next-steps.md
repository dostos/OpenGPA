# OpenGPA Eval — Strategic Direction

This file captures cross-round strategic context. Per-round work-item
backlog lives in `docs/eval-rounds/<date>-<round>.md`. **Don't put
round-specific items here** — they belong in their round file.

## What we learned

Minimal single-file reproductions (200 lines) are too easy for any LLM
model tier. R1–R3: 100% accuracy in both modes across Haiku and Sonnet.
**Root cause**: the bug *is* the entire codebase. Nothing to search.

## What shows OpenGPA's value

OpenGPA's value appears when the agent must choose between:
- Reading 50,000 lines of framework source to trace state (slow)
- Querying 3 OpenGPA endpoints to see actual runtime state (fast)

Requires eval scenarios that include the **actual upstream codebase**,
not a minimal repro.

## The 5-stage flywheel

1. **Mine** — Curate real bugs with `fix_pr_url`/`fix_sha`/`fix_parent_sha`/`bug_class`/`files`
2. **Verify** — `python -m gpa.eval.curation.verify` (static + network + build); quarantine failures
3. **Capture** — Run native scenarios under the GL/Vulkan shim. Skip WebGL/JS — shim doesn't intercept browser GL.
4. **Evaluate** — `python -m gpa.eval.cli run` with `--judge` (default on). Compare accuracy × token cost.
5. **Improve** — Fix gaps; write `docs/eval-rounds/<round>.md` with Findings / Added / Removed / Numbers / Open backlog.

Full skill: `~/.claude/skills/eval-driven-improvement/SKILL.md`.

## Open strategic questions

These are NOT round-specific — they're persistent design questions.
Each round's "Findings" should reference whichever of these it
informs.

### Q1. WebGL coverage

OpenGPA ties code_only on web-map at 71% (R12c). The shim doesn't
intercept browser WebGL — the tier-mismatch warning prevents bad
with_gla token spend, but real *lift* on browser scenarios needs a
WebGL backend. Two paths:

1. **Gate at the harness** (shipped in `d7bd4bb`) — prevents
   regressions, warns the user. Done.
2. **Add a WebGL backend**: extend `src/shims/webgl/` to surface
   frame state via the FrameProvider ABC. Real engineering investment;
   only worth it once we have hard evidence that WebGL frame state
   would close real diagnoses.

### Q2. Mining quality bar

When the judge says `none` for both modes across multiple model tiers,
the scenario may be **unsolvable from the materials we provide** (the
relevant context isn't in the snapshot or user report). Need a
"scenario-level difficulty" gate — quarantine consistently-unsolvable
scenarios so they don't drag the cohort.

R12c surfaced two scenario-quality failures (`cesium_camera_jumps`,
`godot_performance_on_android`) where mining picked an incomplete fix.
Multi-PR detection is now in the round backlog (R12c P0).

### Q3. Cost of the judge

Sonnet judge runs at ~$0.005/scenario × N modes. At 100-scenario
cohorts × 2 modes × 3 model tiers = $3/round. Acceptable but worth a
daily-budget knob when we scale up.

### Q4. Token spend as a real-time confidence signal

R12c confirmed: solved scenarios use ~half the tokens of failed ones.
Failed agents grind — repeated greps, multi-file backtracking. We
could surface this signal *during* a run (tool-call budget +
checkpoint) instead of only post-hoc. Tracked as P2 in R12c backlog.

## Snapshot pipeline invariants (load-bearing)

If any of these break, eval signal is silently fake. Verifier and
unit tests cover all 5; documenting here so the constraints are
explicit:

| Invariant | Failure mode if violated |
|---|---|
| `fix_parent_sha` populated for every fix-anchored scenario | Snapshot serves the post-fix tree → agent investigates already-fixed code → false negatives across the board |
| `SnapshotFetcher.fetch()` holds a per-cache-key fcntl lock | Parallel modes race on the same cache dir; one rmtrees the other's in-flight clone; FileNotFoundError on cwd |
| `--unshallow` only when `.git/shallow` exists | git fatals on a complete repo when fallback 1 already pulled the full history |
| Verifier runs before every eval round | Hint-comment leaks bias the agent; stale SHAs fail mid-run; no source means no Bazel target |
| `runner._bazel_target_for(scenario)` derives the nested package | Old `//tests/eval:<slug>` targets don't exist after the taxonomy migration; live capture silently disabled |
| Judge fetches the actual fix-PR diff (depth ≥ 2 from fix_sha) | `git show <fix_sha>` against depth-1 reports the merge as additive-from-nothing; judge sees garbage |
