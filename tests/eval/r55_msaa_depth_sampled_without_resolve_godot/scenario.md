# R55_MSAA_DEPTH_SAMPLED_WITHOUT_RESOLVE_GODOT: MSAA depth bound for sampling without a resolve blit (Godot Forward Mobile)

## Bug
A Godot user enables MSAA on the Forward Mobile renderer and writes a
`ShaderMaterial` that samples `DEPTH_TEXTURE` (`hint_depth_texture`) for
an outline / fog / SSAO effect. The Forward Mobile path renders to a
multisample depth attachment and then binds the *non-MSAA* depth texture
for sampling without a blit-resolve in between. The non-MSAA texture
still holds its initial cleared depth (1.0), so the user's depth-driven
shader sees `DEPTH_TEXTURE == 1.0` everywhere and produces no visible
effect.

## Expected Correct Output
The post-process pass writes magenta wherever the scene's depth is
closer than the far plane (`d < 0.99`), so the centre of the scene
triangle (depth ≈ 0.25) shows magenta on the default framebuffer. The
sampled centre pixel is `(255, 0, 255, 255)`.

## Actual Broken Output
The depth comparison sees `d == 1.0` at every texel because the
non-MSAA depth texture was never written. The post-process branch
produces black, including at the triangle's centre. The sampled centre
pixel is `(0, 0, 0, 255)`.

## Ground Truth Diagnosis
Per the upstream report,

> On Forward Mobile having a Shader Material which samples the Depth
> Texture and having MSAA X2, X4, X8 enabled, causes the Depth Textures
> sampled data to be corrupted. Most likely its missing an MSAA Resolve
> before being bound.

In GL terms the Forward Mobile pipeline does:

1. Render scene to an FBO with multisample color and multisample depth
   renderbuffers (`glRenderbufferStorageMultisample` ×2).
2. `glBlitFramebuffer(... GL_COLOR_BUFFER_BIT ...)` to a non-MSAA
   resolve FBO — depth is *not* in the bitmask.
3. Bind the non-MSAA depth texture to a `sampler2D` and draw a
   full-screen post-process quad.

Step 2 leaves the non-MSAA depth texture at its `glClearDepth(1.0)`
state. Step 3 reads back 1.0 across the whole screen, so any consumer
shader that gates on `DEPTH_TEXTURE < 1.0` (outline, fog, edge,
contact-shadow, depth-fade) renders nothing. The fix on the engine
side is to add `GL_DEPTH_BUFFER_BIT` to the resolve blit (or to use
`glFramebufferTexture2DMultisample` and a sampler2DMS in the shader).

## Difficulty Rating
4/5

## Adversarial Principles
- missing-resolve-step-between-msaa-and-sample
- bound-resource-was-never-written-this-frame
- effect-is-completely-absent-not-glitchy (hard to localise)
- only-triggers-with-msaa-enabled (works on the dev machine without it)

## How OpenGPA Helps
OpenGPA tracks per-frame `glClear` calls (recent commit:
`feat: intercept glClear — track per-frame clear calls`) and FBO
attachments. Querying "what was the last write to `resolve_depth` this
frame" returns only the `glClearDepth` call from the resolve FBO setup;
no draw nor blit wrote depth into that texture. The single follow-on
fact — `resolve_depth` is then bound to a `sampler2D` in the post-
process draw — points the agent at the missing depth-resolve blit
without needing to inspect shader semantics.

## Source
- **URL**: https://github.com/godotengine/godot/issues/80991
- **Type**: issue
- **Date**: 2023-08-23
- **Commit SHA**: (n/a)
- **Attribution**: Reported by upstream Godot user against Forward Mobile + MSAA in Godot 4.1.1; resolved by PR #108636. Reduced to GL renderbuffer + blit primitives for the eval

## Tier
core

## API
opengl

## Framework
none

## Bug Signature
```yaml
type: framebuffer_dominant_color
spec:
  region: center_pixel
  expected_dominant_rgb: [255, 0, 255]
  actual_dominant_rgb: [0, 0, 0]
  tolerance: "red & blue channels both > 128 ⇒ correct; all channels < 32 ⇒ depth-resolve bug"
```

## Predicted OpenGPA Helpfulness
- **Verdict**: yes
- **Reasoning**: The defect reduces to "a texture is sampled in draw N but no draw or blit wrote it this frame other than its initial clear". OpenGPA's clear / FBO-attachment trace surfaces exactly that fact; combined with the read of `resolve_depth` in the post-process draw it uniquely identifies the missing depth blit. No shader-level inference is required.
