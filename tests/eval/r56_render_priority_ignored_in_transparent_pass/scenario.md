# R56_RENDER_PRIORITY_IGNORED_IN_TRANSPARENT_PASS: render_priority ignored when material is transparent (Godot)

## Bug
A Godot user gives a `MeshInstance3D` a base material plus a
`next_pass` outline material with `render_priority = 1` and both
materials transparent (the standard outline / fresnel-rim pattern).
The user expects `render_priority` to make the outline draw last so it
appears on top. Godot's transparent pass sorts draws back→front by
camera distance and ignores `render_priority` for transparent /
no-depth materials, so the outline draws *first* and the base mesh's
alpha-blended fragment composites *over* the outline at the centre,
defeating the effect.

## Expected Correct Output
The user's intent ("outline pass last, on top") would produce a
yellow centre pixel where the outline material is composited last.
With straight-alpha blending against the cleared black background and
the outline pass second, the centre is approximately `(62, 51, 0,
185)` — red is the largest channel of R/G/B by a wide margin.

## Actual Broken Output
Godot's depth sort puts the outline first (its mesh is authored
slightly behind the base mesh) and the base mesh second. With
straight-alpha blending the final centre pixel is `(63, 69, 80, 185)`
— blue (80) is the largest of R/G/B and red (63) is *not* the
dominant channel. The outline colour is fully buried under the base
material.

## Ground Truth Diagnosis
The Godot reporter wrote:

> If you use the transparent flag or the no_depth flag in material the
> render priority seam to be ignored.

Godot's renderer keeps two draw lists: the opaque list (sorted by
`render_priority` then material) and the transparent list (sorted
back→front by camera distance, with `render_priority` honoured only as
a coarse bucket). When both passes of a `next_pass` chain are
transparent, the outline pass and the base pass land in the same
transparent bucket and the depth sort fully determines order. Because
authoring an outline as a slightly-larger / pushed-back silhouette is
the conventional pattern (so the outline doesn't z-clip the base), the
sort puts outline before base — exactly the opposite of what the user
asked for.

The recommended Godot-side fixes are: (1) use a `Compositor` /
`CompositorEffect` for the outline pass, (2) use `depth_draw_always` so
the depth sort places the pass in the opaque bucket, or (3) author the
outline pass on the *front* face with inverted normals.

## Difficulty Rating
3/5

## Adversarial Principles
- engine-sort-overrides-explicit-user-priority
- transparent-vs-opaque-bucket-trap
- effect-looks-correct-from-some-angles-not-others
- no-gl-error / no-warning surfaced

## How OpenGPA Helps
OpenGPA records the actual sequence of draw calls for the frame. An
agent asking "list draw calls for the current frame in order, with the
program / colour state of each" sees:

```
draw[0] = quad (yellow-ish, alpha 0.7) — the outline pass
draw[1] = quad (blue, alpha 0.7)       — the base pass
```

Cross-referenced with the user's stated `render_priority = 1` on the
outline material, the inverted order is the entire diagnosis: the
agent immediately concludes that the engine's transparent-pass depth
sort overrode the user's priority hint, and can recommend the standard
Godot workarounds (`depth_draw_always`, opaque pass, CompositorEffect)
without needing to inspect shader logic or per-pixel colours beyond the
single contradicting centre pixel.

## Source
- **URL**: https://github.com/godotengine/godot/issues/34177
- **Type**: issue
- **Date**: 2019-12-13
- **Commit SHA**: (n/a)
- **Attribution**: Reported on Godot 3.2 beta 3 (Linux); reduced to a two-pass blended-quad pattern at the GL layer for the eval

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
  expected: "red channel is the largest of R/G/B (yellow outline composited last)"
  actual: "blue channel is the largest of R/G/B and exceeds the red channel by ≥ 10 (depth-sort overrode render_priority — base material composited last)"
  rationale: "If render_priority were honoured, the yellow outline would composite last and dominate the centre pixel; depth-sort places base last and the centre is dominated by the dark-blue base material."
```

## Predicted OpenGPA Helpfulness
- **Verdict**: yes
- **Reasoning**: The defect is purely a draw-order observation. OpenGPA's per-frame draw-call list directly contradicts the user's mental model, and the contradicting pixel value at the centre confirms the diagnosis without needing further per-draw state introspection. The agent does not need to reason about Godot internals beyond "transparent-pass sorting overrides render_priority", a known Godot quirk that the GL trace makes obvious by showing the order on the wire.
