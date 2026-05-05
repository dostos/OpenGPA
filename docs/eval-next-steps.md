# OpenGPA Eval — Next Steps

## What We Learned

Minimal single-file reproductions (200 lines) are too easy for any LLM model tier.
All 3 rounds: 100% accuracy for both code-only and with-OpenGPA across Haiku and Sonnet.

**Root cause**: The bug IS the entire codebase. There's nothing to search through.

## What Would Show OpenGPA's Value

OpenGPA's value appears when the agent must choose between:
- **Reading 50,000 lines** of framework source to trace state (expensive, slow)
- **Querying 3 OpenGPA endpoints** to see the actual runtime state (cheap, fast)

This requires eval scenarios that include the **actual upstream codebase**, not a minimal reproduction.

## The Plan: Real Codebase Eval

### Setup
1. Use `SnapshotFetcher` to clone upstream repos at the pre-fix commit SHA
2. Give the agent: upstream source (Three.js/Godot) + the bug report + the app code
3. The agent must find the root cause in the framework source

### Two Modes
- **Code-only**: Agent reads bug report + app code + framework source. Must grep/read through framework files to find the state management bug. Token-expensive.
- **With OpenGPA**: Agent reads bug report + app code + queries OpenGPA for runtime state. Can skip reading framework source entirely if the captured state reveals the issue.

### Metrics
- **Tokens consumed**: How much framework source did the agent read?
- **Files opened**: How many framework files did the agent explore?
- **Accuracy**: Did it find the correct root cause?
- **Time**: Wall clock to diagnosis

### Expected Results
- Code-only: reads 5-20 framework files (10,000-50,000 tokens) to trace the state
- With OpenGPA: reads 0-2 framework files (0-5,000 tokens) because the runtime state directly shows the problem

### Candidates (from SnapshotFetcher)

Scenarios that already have upstream snapshot references:
- Issues with `upstream_snapshot.repo` and `upstream_snapshot.sha` in their metadata
- The snapshot contains the actual buggy framework code at the pre-fix commit
- The `relevant_files` list tells which framework files contain the root cause

### Implementation
1. `SnapshotFetcher.fetch(repo, sha)` → clones to `/data3/snapshots/{repo}/{sha}/`
2. Eval agent gets the snapshot path as a "working directory" to explore
3. For code-only: agent can `Read` any file in the snapshot
4. For with-OpenGPA: agent can also query the REST API

### Priority Candidates (multi-file, state bugs)

| Issue | Framework | Root Cause Location | Files to Read |
|-------|-----------|--------------------|----|
| three.js #26762 (depthMask) | Three.js r157 | `src/renderers/webgl/WebGLState.js` | ~5 files |
| three.js #25618 (texture cache) | Three.js r155 | `src/renderers/webgl/WebGLTextures.js` | ~8 files |
| godot #76334 (blend equation) | Godot 4.1 | `drivers/gles3/rasterizer_scene_gles3.cpp` | ~10 files |
| three.js #32444 (transmission) | Three.js r182 | `src/renderers/webgl/WebGLRenderer.js` | ~6 files |

## Status

- [x] Minimal reproduction eval (rounds 1-3): 100% accuracy, too easy
- [x] Curation pipeline discovers real issues
- [x] SnapshotFetcher clones upstream repos
- [x] Scenarios have upstream_snapshot metadata
- [x] Eval harness passes snapshot path to agents (upstream tools wired)
- [x] Live capture unblocked: `runner.py` derives nested-taxonomy Bazel
      target paths so `run_with_capture` actually emits frames
- [x] `fix_parent_sha` populated end-to-end so the snapshot serves the
      buggy parent state, not the post-fix state
- [x] Scenario verifier (`gpa.eval.curation.verify`) with static /
      network / build tiers; failed scenarios moved to
      `tests/eval-quarantine/`
- [x] Re-run R12-style cohort with capture working + verified scenarios
      (R12c, 2026-05-05): 5/14 with_gla, 7/14 code_only — was 1/14 with
      stale snapshots. Real signal restored.
- [x] Measure token reduction from OpenGPA on the cleaned cohort:
      with_gla 147k vs code_only 163k total (≈10% reduction overall).
      Native godot tied 2/8; web-map widened gap (3/6 vs 5/6) because
      the GL shim doesn't intercept browser WebGL — see
      `docs/eval-results.md` "R12c Re-evaluation".

## Open question for next iteration

OpenGPA loses to code-only on JS/WebGL scenarios (2 maplibre bugs in
R12c). The shim only intercepts native GL/Vulkan, so browser-side
WebGL surfaces no useful frame state — yet the agent still pays the
prompt overhead enumerating empty overviews. Two paths forward:

1. **Gate at the harness**: detect WebGL-tier scenarios from
   `framework_kind` / source language and skip GPA tool injection
   entirely. Cheap, immediate.
2. **Add a WebGL backend**: extend `src/shims/webgl/` to surface
   frame state via the same FrameProvider ABC. Higher payoff but
   a real engineering investment.

Option 1 is the ratchet — pick it up before the next eval round.
