# R1_PIXIJS_ALPHAMASK_STALE_MAPCOORD: Pooled mask texture reused without refreshing UV-transform uniform

## Bug
Two consecutive `AlphaMask` filter applies share the same pooled
framebuffer texture object. Between the two applies, the pool returns the
texture, the second mask repopulates it with a different sub-region
(70x110 instead of 100x80), and the filter is invoked again. The shader's
`mapCoord` uniform — which encodes how the live sub-region maps into the
128x128 pooled source — is supposed to be refreshed each invoke, but the
texture-matrix setter early-returns whenever the underlying texture
*handle* matches its previous value. So draw call 2 inherits draw call 1's
`mapCoord` and samples the new mask data through the wrong UV transform.

## Expected Correct Output
- Left half: 130x130 green square, masked to a 100x80 axis-aligned region.
- Right half: 130x130 blue square, masked to a 70x110 axis-aligned region.

## Actual Broken Output
- Left half is correct.
- Right half's blue square is masked using mask A's `(100/128, 80/128)` UV
  transform applied to mask B's underlying 70x110 contents, so the visible
  blue region is squeezed horizontally and clipped vertically — roughly a
  ~50x110 strip rather than the intended 70x110 rectangle. (The reporter
  observed exactly this in the linked StackBlitz repro.)

## Ground Truth Diagnosis
The reporter's flow analysis traces the bug to `MaskFilter._textureMatrix`
short-circuiting on identical texture references inside `MaskFilter.apply()`:

> `this._textureMatrix.texture = this.sprite.texture` → same object reference
> → setter's `if (this.texture === value) return` fires → `update()` is
> skipped — `mapCoord` is still `{a: 108/128, d: 94/128}` from Mask A. But
> it should be `{a: 76/128, d: 79/128}` for Mask B. The shader samples at
> wrong UV coordinates → mask appears distorted.

The pooled-texture aliasing is intrinsic to PixiJS's `TexturePool` design:
both masks request a 128x128 source, so the pool hands back the same
`filterTexture_1` with `frame.width/height` rewritten and `updateUvs()`
called on the texture itself — but the *filter's* derived `_textureMatrix`
uniform is never re-derived because the equality guard fires first. The
reporter confirms a workaround: forcing `this._textureMatrix.update()` at
the top of `MaskFilter.apply()` restores correct UVs (their
`patchMaskFilterApply()` shim in the linked repro).

## Difficulty Rating
4/5

## Adversarial Principles
- pooled-resource identity collision (same handle, different intent)
- uniform staleness across superficially-independent draws
- equality-guard short-circuit hides a required side effect (`update()`)
- bug is invisible without comparing per-draw uniform values
- visual symptom is "wrong size" — easily mistaken for a bounds/layout bug

## How OpenGPA Helps
A single per-draw uniform inventory ("for each draw call, give me every
sampler binding and the value of every active uniform that references the
bound mask texture") shows draw call 1 and draw call 2 with identical
`uMapCoord = (0.781, 0.625)` despite the texture's *contents* having
changed between them. Comparing the texture's white-region extent on the
GPU against the `uMapCoord` value at the consuming draw immediately
flags the inconsistency — no framework knowledge required.

## Source
- **URL**: https://github.com/pixijs/pixijs/issues/11995
- **Type**: issue
- **Date**: 2026-04-18
- **Commit SHA**: (n/a)
- **Attribution**: Reported on the PixiJS issue tracker; the flow
  breakdown in the issue body (annotated by the reporter as
  AI-assisted) traces the regression to the
  `MaskFilter._textureMatrix.texture` setter's early-return.

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
  rule: "uMapCoord at draw call 1 must not equal uMapCoord at draw call 2 when the bound mask texture's live sub-region has changed between the draws"
  draw_call_indices: [0, 1]
  offending_uniform: uMapCoord
  shared_texture_uniform: uMask
  observed_state:
    draw_0: { uMapCoord: [0.78125, 0.625] }   # 100/128, 80/128 — correct for mask A
    draw_1: { uMapCoord: [0.78125, 0.625] }   # stale; should be 70/128, 110/128
  expected_state:
    draw_1: { uMapCoord: [0.546875, 0.859375] }
```

## Predicted OpenGPA Helpfulness
- **Verdict**: yes
- **Reasoning**: The bug surfaces as a per-draw uniform value that is
  silently wrong relative to the bound texture's intended use. OpenGPA's
  Tier-1 raw uniform capture exposes the discrepancy directly: two draw
  calls sharing one texture object but expecting different UV transforms
  is a one-query diagnostic. No heuristic or framework hook is needed —
  the agent just compares `uMapCoord` between the two draws and notices
  it didn't change despite the mask sub-region having changed.

## Observed OpenGPA Helpfulness
- **Verdict**: ambiguous
- **Evidence**: validation skipped (--no-validate)
