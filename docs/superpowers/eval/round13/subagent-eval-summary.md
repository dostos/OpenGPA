# Round 13 — subagent-driven eval (single tier, code-only)

*Run: 2026-04-29. Model: Opus 4.7 (1M context) — Claude Code session, no API key path.*

## Setup

Single-tier eval on the 4 direct-rule-match R13 scenarios: r1, r3, r6,
r13. Each scenario was dispatched as an independent
`general-purpose` subagent with:

- Just the user-report section of the scenario (Ground Truth / Fix /
  Bug Signature redacted).
- `gh` CLI for reading the upstream three.js repo at the relevant ref.
- A 20-tool-call budget cap.
- A required two-line output: `DIAGNOSIS:` + `FILE:`.

r9 was excluded — its `expected_files: []` (legacy, no fix PR) makes
it unscoreable under the file-match metric.

## What this measures

- **Code-navigation skill** of Opus 4.7 working from vague user
  reports — no captured frame, no GPA tools.
- **Scenario quality**: whether the redacted user report contains
  enough signal for a competent agent to find the offending file(s).

## What this does NOT measure

- **GPA value-add.** Maintainer-framing scenarios have no captured
  frame; with-gpa mode is not meaningful unless the buggy three.js
  example runs under the OpenGPA shim. Phase-2 plan addresses this.
- **Tier comparison.** Single-tier (Opus 4.7); no haiku / sonnet
  data points.
- **The Cat-2 cost regression** (+$0.39/pair) that originally
  motivated the cleanup — needs the full multi-tier matrix.

## Results

| Scenario | Expected files | Agent's answer | Match | Tool calls | Tokens |
|---|---|---|---|---|---|
| r13 autoClear PassNode | `src/nodes/display/PassNode.js` | `src/nodes/display/PassNode.js` | ✅ exact | 13 | ~32k |
| r3 Line2 logDepth | `src/materials/nodes/NodeMaterial.js`, `Line2NodeMaterial.js` | `NodeMaterial.js`, `Line2NodeMaterial.js` | ✅ both | 8 | ~25k |
| r1 logDepthBuffer transparency | `logdepthbuf_fragment.glsl.js`, `logdepthbuf_pars_fragment.glsl.js` | `logdepthbuf_pars_fragment.glsl.js`, `logdepthbuf_pars_vertex.glsl.js` | ⚠️ 1/2 | 23 | ~34k |
| r6 setScissor PassNode | `src/nodes/display/PassNode.js` | `src/nodes/display/PassNode.js` | ✅ exact | 9 | ~24k |

**Aggregate:**
- **3 of 4 scenarios** got every expected file exactly right.
- **1 of 4** (r1) was partial — agent identified the correct ShaderChunk
  family (`logdepthbuf`) and got one of two expected files exactly,
  but substituted `_pars_vertex` for `_fragment`. The diagnosis pointed
  at vFragDepth precision (a plausible adjacent root cause); the
  upstream fix actually edited both `_fragment.glsl.js` and
  `_pars_fragment.glsl.js`.
- Mean: **13 tool calls, ~29k tokens per scenario**.
- Total: **53 tool calls, ~115k tokens** for the round.

## Per-scenario notes

### r13 — WebGPURenderer autoClear=false (✅)

The pilot. User report was the original GH issue body — vague, blames
"objects or caches not properly culled." Agent navigated:
`gh search code "autoClear" --repo mrdoob/three.js` →
`PostProcessing.js` → `PassNode.js`. 13 calls. Identified that
`PassNode.updateBefore()` calls `renderer.render()` without forcing a
clear on the internal render target.

### r3 — Line2NodeMaterial + logDepth (✅ both)

Most efficient run (8 calls). User report mentions "Line2 occluded
by helmet at certain angles with logarithmicDepthBuffer." Agent
correctly identified that `Line2NodeMaterial` doesn't override
`setupDepth`, so `NodeMaterial.setupDepth` derives log-depth from
`positionView.z` while Line2 outputs custom clip-space — mismatch.

### r1 — logarithmicDepthBuffer + transparency (⚠️ 1/2)

Hardest scenario; 23 calls (highest budget consumption). The user
report names a hardware-specific symptom (Intel UHD only). Agent
hypothesized vFragDepth precision and pointed at the parameter file
+ the wrong sibling. Real fix touched the par-fragment AND the main
fragment chunk. Partial credit: right module family, wrong second
file.

### r6 — setScissor + PostProcessing (✅)

User-report explicitly mentions the user's `setScissor` /
`setViewport` setup. Agent immediately suspected
`PostProcessing` / `PassNode`, confirmed by reading `PassNode.js`
and seeing zero scissor/viewport handling in `updateBefore`. 9 calls.

## Takeaways

1. **Scenarios are well-formed.** Vague user reports are sufficient
   for a competent agent to find the offending file(s) in 3/4 cases —
   the eval set has the right shape for measuring code navigation.
2. **r1 is the hardest** (and the one that most needs GPA help, if
   we had captured frames). Cross-reference: it's also the only
   scenario where the agent *guessed wrong* about a sibling file —
   suggesting the search was navigating by symbol-name rather than
   diff-correctness.
3. **53 calls / 115k tokens / 4 scenarios** is the cost shape for
   single-tier code-only eval. Multi-tier on the same scenario set
   would be roughly 3× this (haiku ≈ 0.5×, sonnet ≈ 1×, opus ≈ 1.5×
   on cost-per-token-but-fewer-tokens basis).
4. **GPA tool value-add not yet measured** for the maintainer-framing
   eval shape — that requires either (a) capturing frames for these
   bugs, or (b) testing on GL-shaped scenarios from earlier rounds.

## Next steps (open)

- Run the same 4 scenarios with the **buildable GL eval scenarios
  from earlier rounds** (e.g. R10's transmission feedback loop with
  its captured frame) to get with_gpa evidence the cleanups didn't
  break the Tier-1 win.
- Mine more for the remaining check-config rules (color-space,
  tone-mapping, premultiplied-alpha, mipmap-NPOT) — only depth-write
  and autoClear/viewport got direct hits this round.
- When an API key is available, run the multi-tier matrix (haiku +
  sonnet + opus) to revisit the +$0.39/pair Cat-2 regression
  with the cleaned-up toolkit.
