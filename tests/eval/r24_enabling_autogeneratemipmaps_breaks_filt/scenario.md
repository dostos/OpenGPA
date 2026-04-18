# R5_ENABLING_AUTOGENERATEMIPMAPS_BREAKS_FILT: Mipmap levels allocated but never populated cause filter sampling to read uninitialized data

## Bug
A render-target texture is allocated with multiple mipmap levels, but only level 0 is ever rendered into. A subsequent "filter" pass samples the texture at a LOD greater than 0 (either explicitly via `textureLod` or implicitly via derivatives / `LOD bias` / a smaller filter framebuffer). The GPU reads from uninitialized higher mip levels and produces corrupt output — typically black or driver-dependent garbage — instead of the scene content that was rendered into level 0.

## Expected Correct Output
The full-screen quad should show the scene rendered into level 0 (a UV-derived gradient). At the center of the window, the pixel should be a non-black color roughly `(128, 128, 51)` reflecting the fragment-shader output `vec4(uv, 0.2, 1)` at `uv=(0.5, 0.5)`.

## Actual Broken Output
The center pixel is black (or undefined / driver-dependent garbage), because the filter fragment shader sampled level 2 of the render-target texture, which was allocated but never written. The rendered scene content exists only on level 0 and is not visible in the composited frame.

## Ground Truth Diagnosis
The PixiJS `TexturePool` creates filter render targets with mipmap storage allocated whenever `TextureSource.defaultOptions.autoGenerateMipmaps = true` (needed so `PIXI.Text` can mipmap), but after rendering into the filter target it never calls `glGenerateMipmap`. Filter shaders that sample with a non-zero effective LOD then read uninitialized mip levels:

> Enabling mipmaps causes the `TexturePool` to create render textures with mipmap levels which are never populated with any real data. This causes filters that do scaled UV sampling to sample invalid or "corrupt" data.

The maintainer rejected the naive fix (disabling mipmaps globally in the pool, which regresses `Text` from issue #11304) and pointed at the actual design bug:

> The actual fix should add mipmap setting into the ids generated for the pool so that it wouldn't use textures with mipmaps for filters.

i.e. the pool cache key fails to distinguish mipmapped vs. non-mipmapped render targets, so a texture originally allocated with mipmap storage (for text) gets reused as a filter target and the filter shader ends up sampling uninitialized mip levels.

## Difficulty Rating
3/5

## Adversarial Principles
- silent_uninitialized_mip_levels
- lod_sampling_without_mipmap_generation
- cross_feature_state_pollution (text-mipmap setting leaks into filter pool via a cache key that ignores the mipmap flag)

## How OpenGPA Helps
OpenGPA's Tier-1 capture exposes per-texture metadata including the declared mip level range (`GL_TEXTURE_BASE_LEVEL`/`MAX_LEVEL`) and which levels actually received writes (via `glTexImage2D` with non-NULL data, FBO attachments, or `glGenerateMipmap`). A single `texture_mip_state` query on the filter render target immediately shows that levels 1..3 are allocated but unwritten while the sampler's min filter is `GL_LINEAR_MIPMAP_LINEAR`. That mismatch — declared vs. populated — is invisible to shader-level or code-level inspection alone.

## Source
- **URL**: https://github.com/pixijs/pixijs/issues/11717
- **Type**: issue
- **Date**: 2026-04-18
- **Commit SHA**: (n/a)
- **Attribution**: Reported via PixiJS issue #11717; maintainer diagnosis in comment 5 of the same thread.

## Tier
core

## API
opengl

## Framework
none

## Bug Signature
```yaml
type: unexpected_color
spec:
  region: center_pixel
  probe_xy: [256, 256]
  expected_rgb_min: [32, 32, 16]
  expected_rgb_max: [255, 255, 255]
  broken_rgb: [0, 0, 0]
  note: "Correct frame has level-0 gradient visible at center (roughly (128,128,51)). Broken frame samples uninitialized mip level 2 → typically all-zero black."
```

## Predicted OpenGPA Helpfulness
- **Verdict**: yes
- **Reasoning**: The bug is a state-vs-content mismatch on a specific texture: the sampler requests a mipmap level that was never written. A graphics debugger that records per-texture mip-level write history and sampler settings surfaces this directly, whereas static code inspection of either the filter shader or the pool allocation path in isolation does not reveal the problem — both are individually "correct," and the bug only exists in the interaction.

## Observed OpenGPA Helpfulness
- **Verdict**: ambiguous
- **Evidence**: validation skipped (--no-validate)
