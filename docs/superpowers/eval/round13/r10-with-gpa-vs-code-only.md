# R10 — with_bhdr vs code_only (single tier, single scenario)

*Run: 2026-04-30. Model: Opus 4.7 (1M context) via Claude Code subagent dispatch.*

## Setup

Two parallel `general-purpose` subagents on
`r10_feedback_loop_error_with_transmission_an` (a buildable GL
scenario from earlier rounds — has a `.c` reproduction, captured
frame is available).

Both subagents got:
- The user-report section verbatim from `scenario.md` (with Ground
  Truth and downstream sections redacted).
- `gh` CLI for reading three.js source.
- A 20-tool-call budget cap.

The **with_bhdr** subagent additionally got:
- `curl` access (no auth) to a running OpenGPA engine at
  `localhost:18080` with the R10 scenario captured at `frame_id=1,
  draw_call_id=0`.
- Documentation of the relevant GPA REST endpoints
  (overview, drawcalls/0, drawcalls/0/feedback-loops,
  drawcalls/0/textures, draws/0/explain, check-config).

## What this measures

- **GPA tool value-add** on a known-positive case (state-collision
  scenario where GPA's narrow `feedback-loops` /
  `textures.collides_with_fbo_attachment` checks fire).
- **Apples-to-apples** at single tier: same model (Opus 4.7), same
  user report, same prompt structure, same time budget. Only the GPA
  toolset differs.

## What this does NOT measure

- Tier comparison (only Opus 4.7).
- Cat-2 framework-app-dev cost regression (R10 is graphics-lib-dev).
- Generalization — N=1 scenario.

## Results

| Metric | code_only | with_bhdr | Δ |
|---|---|---|---|
| **Diagnosis accuracy** | correct root cause (PR #32444, samples=0, MSAA-resolve indirection lost) | correct root cause (same reasoning + GL-level evidence anchor) | tie |
| **Files matched** | `WebGLRenderer.js` + `WebGLCapabilities.js` (2/4 expected) | `WebGLRenderer.js` + `WebGLCapabilities.js` (2/4 expected) | tie |
| **Tool calls** | 5 | 4 | **−20%** |
| **Total tokens** | 21,266 | 19,313 | **−10%** |
| **Wall time** | 37 s | 24 s | **−35%** |

Expected files: `WebGLRenderer.js`, `WebGLCapabilities.js`,
`WebGLRenderTarget.js`, `WebGLTextures.js`. Both agents got the two
that contain the regression line + capabilities exposure; both missed
the two adjacent files (the actual upstream fix touched all four).

## Tool-call breakdown

**code_only (5 calls):**
1. `gh pr view 32444 -R mrdoob/three.js --json files,title,body` → saw the diff summary
2. `gh api repos/mrdoob/three.js/pulls/32444/files` → identified the changed line
3. `gh api repos/mrdoob/three.js/contents/src/renderers/WebGLRenderer.js?ref=r182` → read the full file around the change
4. `gh search code "transmissionRenderTarget" --repo mrdoob/three.js --limit 5`
5. `gh api repos/mrdoob/three.js/contents/src/renderers/webgl/WebGLCapabilities.js?ref=r182`

**with_bhdr (4 calls):**
1. `curl /api/v1/frames/1/drawcalls/0/textures` → instant smoking gun: `collides_with_fbo_attachment: true` on `texture_id=1`
2. `gh pr view 32444 -R mrdoob/three.js --json files,title`
3. `gh api repos/mrdoob/three.js/pulls/32444/files`
4. `gh api repos/mrdoob/three.js/contents/src/renderers/webgl/WebGLCapabilities.js?ref=r182`

The with_bhdr agent skipped one source-navigation call because the
GPA narrow check confirmed the GL-level pattern up-front, letting it
go straight to the regression line in PR #32444 with stronger
confidence.

## Takeaways

1. **GPA tools provide a small but real efficiency gain** even on a
   scenario where the fix is hint-revealed (PR # in the user report).
   The narrow `textures.collides_with_fbo_attachment` check delivers
   a single-call smoking gun that anchors the agent's reasoning in
   GL-level evidence.
2. **Diagnosis quality is identical** under both modes when the fix
   is straightforward and the user report includes a regression
   marker (PR #). On harder scenarios without that hint, the gap may
   be larger.
3. **Wall-time delta (−35%)** is bigger than token delta because
   `curl` to a local engine is faster than `gh api` to GitHub. Real
   cost of the GPA capture pipeline isn't measured here (Xvfb +
   build + run = several minutes one-time; query is sub-second).
4. **Scope of the claim:** N=1, single tier (Opus 4.7), code-only
   baseline includes the PR-# hint. To generalize, run the same
   matrix across 5-10 scenarios at multiple tiers (haiku / sonnet /
   opus) — gated on API key.

## Comparison to R13 subagent eval (different scenario shape)

The R13 maintainer-framing scenarios (r1, r3, r6, r13) had no
captured frames, so the with_bhdr-vs-code_only comparison wasn't
runnable there. Their token costs (mean 29k / scenario) include
cross-repo navigation that R10's 19-21k doesn't, suggesting
maintainer-framing eval intrinsically costs ~50% more than
buildable-GL eval at single tier.

## Open follow-ups

- Run this same comparison on harder scenarios (no PR-# hint,
  multi-file fix) to see if the GPA gap widens.
- When the API key is available, run the multi-tier matrix (haiku /
  sonnet / opus × code_only / with_bhdr) on at least 5 R10-shape
  scenarios. **Estimated cost: ~$15** based on R10v2/R11 means.
- Capture frames for the R13 maintainer-framing scenarios (run the
  buggy three.js examples under the OpenGPA shim) to enable
  with_bhdr runs there too.
