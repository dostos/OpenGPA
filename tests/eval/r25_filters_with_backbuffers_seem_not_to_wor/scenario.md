# R6_FILTERS_WITH_BACKBUFFERS_SEEM_NOT_TO_WOR: PixiJS filter backbuffer bound to wrong texture unit when only glProgram is supplied

## Bug
A PixiJS filter declared with `blendRequired: true` but only a `glProgram` (no `gpuProgram`) samples `uBackTexture` and gets the front-sprite texture back instead of the backbuffer. The filter's fragment shader sees `uBackTexture` point at texture unit 0 (where `uTexture` is bound) while `FilterSystem` has placed the actual backbuffer texture at texture unit 3. The unit-3 texture is never read.

## Expected Correct Output
A fragment shader that outputs `texture(uBackTexture, vUV)` should show whatever is behind the sprite — in this minimal reproducer, a solid blue frame (the back texture bound at unit 3).

## Actual Broken Output
A solid red frame — the front texture that is bound at unit 0 and is what `uTexture` points at. The shader nominally reads `uBackTexture`, but because its sampler uniform has been set to `0`, it samples from unit 0 and returns the front-sprite color.

## Ground Truth Diagnosis
The root cause is a bind-point collision between PixiJS's `FilterSystem` and its `Shader` constructor's fallback path for GL-only filters.

The issue reporter traced it (comment 3):

> FilterSystem (line 517) always places the backbuffer texture at group 0, binding 3. Without gpuProgram: Shader constructor has no binding metadata, so assigns ALL resources to group 99 with sequential bindings. Result: uBackTexture ends up at group 99, binding 0 but FilterSystem puts the texture at group 0, binding 3 — mismatch causes wrong texture to be sampled.

and quoted the relevant block in `Shader.ts`:

> if (!groups[99]) { groups[99] = new BindGroup(); ... } nameHash[i] = { group: 99, binding: bindTick, name: i };

The workaround the reporter discovered — supplying a dummy `gpuProgram` whose WGSL declares `@group(0) @binding(3) var uBackTexture` — works because it populates `nameHash` before the group-99 fallback runs, so the `if (nameHash[i]) continue;` line skips the incorrect re-binding. The followup comment ("Have a fix for this locally now ... I'll raise a PR soon") confirms this is a real bug and not a misunderstanding.

In GL terms: `glUniform1i(loc_uBackTexture, ...)` is called with the stale binding index `0` instead of `3`. The texture at unit 3 is bound but unsampled; unit 0 (the front texture) is sampled by both `uTexture` and `uBackTexture`.

## Difficulty Rating
3/5

## Adversarial Principles
- Sampler uniform points to wrong texture unit
- Non-sequential texture unit assignments (unit 3 used, units 1-2 unused)
- Silent failure (no GL error, rendering "succeeds")
- The wrong texture is a valid, complete texture — just the wrong one

## How OpenGPA Helps
A per-draw-call uniform dump shows `uBackTexture = 0` even though unit 0 already belongs to `uTexture`. Cross-referencing the texture-unit binding table with sampler uniforms immediately reveals the collision: unit 3 has a texture bound but no sampler uniform points at it, while unit 0 is referenced by two samplers.

## Source
- **URL**: https://github.com/pixijs/pixijs/issues/11745
- **Type**: issue
- **Date**: 2026-04-18
- **Commit SHA**: (n/a)
- **Attribution**: Reported and diagnosed by the issue author on pixijs/pixijs#11745

## Tier
core

## API
opengl

## Framework
none

## Bug Signature
```yaml
type: unexpected_state_in_draw
spec:
  draw_call_index: 0
  state_kind: sampler_uniform
  uniform_name: uBackTexture
  expected_texture_unit: 3
  actual_texture_unit: 0
  collision_with: uTexture
```

## Predicted OpenGPA Helpfulness
- **Verdict**: yes
- **Reasoning**: The bug's signature — a sampler uniform holding an index that collides with another sampler while a texture at a different unit goes unused — is exactly the kind of cross-state inconsistency that a frame debugger surfaces trivially but is nearly invisible from JS-land source reading. Without OpenGPA, the reporter had to read PixiJS's binding fallback code end-to-end; with OpenGPA, one draw-call dump shows two sampler uniforms both equal to 0 plus a stranded texture at unit 3.

## Observed OpenGPA Helpfulness
- **Verdict**: ambiguous
- **Evidence**: validation skipped (--no-validate)
