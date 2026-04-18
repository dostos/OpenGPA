# R5_BUG_IN_RENDERING_GLB_MODELS: 16-bit index buffer overflow on large mesh

## Bug

A 3D model with more than 65,535 vertices is drawn through an engine that
hard-codes `GL_UNSIGNED_SHORT` (16-bit) index buffers. Any logical index
`i >= 65536` is silently truncated to `i & 0xFFFF` when written into the
`GLushort` array, so triangles/points that should reference the upper portion
of the vertex buffer instead dereference low-index vertices. The rendered
geometry is scrambled; entire regions of the model are missing or collapsed
back onto unrelated vertex data.

## Expected Correct Output

A 400×300 frame on a black background with two horizontal point strips:
- A green strip across the full width at y ≈ -0.5 (bottom).
- A red strip across the full width at y ≈ +0.5 (top).

## Actual Broken Output

Only the green bottom strip is visible. The top red strip is missing — its
65,536…69,999 indices all wrap to values 0…4463, which address the already-
rendered green vertices at y = -0.5. The top half of the frame contains zero
non-black fragments and zero red pixels anywhere in the image.

## Ground Truth Diagnosis

The upstream Mapbox GL JS maintainer pinpoints the limit in a reply to the
report:

> Mapbox GL only supports models that can fit in a 16 bit index buffer. Your
> model has 88948 vertices and doesn't fit.
>
> I'd suggest simplifying it a little bit to get under those limits. It
> should work then.

A 16-bit index buffer can address at most 65,536 distinct vertices (indices
0…65535). The user's `Marina_c.glb` has 88,948 vertices, so any index
referring to vertex 65,536 or above cannot be represented. The engine
neither splits the mesh across multiple draws nor promotes the index buffer
to `GL_UNSIGNED_INT`, so indices are truncated and the geometry corrupts.
Other viewers (Blender, gltf.report) render the same asset correctly
because they use 32-bit indices or chunked draws.

## Difficulty Rating

2/5

The visual symptom is striking but the root cause is specific and discoverable
once an agent inspects the draw call's index type and count. The diagnosis
requires noticing that `count` exceeds the representable range of the index
`type` — a small arithmetic fact that is easy to miss from source code alone
because the truncation happens during the typed-array store, not at draw time.

## Adversarial Principles

- **Silent numeric truncation**: writing a value > 65535 into a `GLushort`
  (or JS `Uint16Array`) is not a GL error and not a runtime error; the high
  bits are just dropped.
- **Self-consistent, partially-correct frame**: the bottom half of the mesh
  looks right, which suggests "the renderer mostly works", misleading an
  agent into hunting for shader / material bugs instead of index-width bugs.
- **Cross-tool divergence**: the same asset renders correctly in Blender and
  gltf.report, so the user reasonably suspects the renderer, not the asset —
  but the asset is in fact *incompatible* with this renderer's choice of
  index width.

## How OpenGPA Helps

`list_draw_calls()` and `get_draw_call(0)` expose the triple
`(mode=GL_POINTS, count=70000, type=GL_UNSIGNED_SHORT)`. The mismatch between
`count=70000` and the 65,536-value capacity of `GL_UNSIGNED_SHORT` is
immediately visible as a numeric fact in the captured draw arguments.
Inspecting the element buffer contents additionally shows that indices at
positions 65536+ wrap to small values, directly confirming the truncation.

## Source

- **URL**: https://github.com/mapbox/mapbox-gl-js/issues/13555
- **Type**: issue
- **Date**: 2024-11-22
- **Commit SHA**: (n/a)
- **Attribution**: Reported by @woyehenni; diagnosis in comment from Mapbox maintainer

## Tier

core

## API

opengl

## Framework

none

## Bug Signature

```yaml
type: color_histogram_in_region
spec:
  region: {x: 0, y: 0, w: 400, h: 150}
  expected_dominant_color: [255, 0, 0]
  expected_min_fraction: 0.02
  tolerance: 32
```

## Predicted OpenGPA Helpfulness

- **Verdict**: yes
- **Reasoning**: The diagnostic fact — that the draw call uses a 16-bit
  index type to address a 70,000-vertex buffer — is a direct property of
  the captured `glDrawElements` arguments. An agent reading raw source code
  sees only high-level mesh APIs and won't notice the index-width ceiling,
  but OpenGPA surfaces `type=GL_UNSIGNED_SHORT` and `count=70000` in the same
  record, where the contradiction is obvious.

## Observed OpenGPA Helpfulness
- **Verdict**: ambiguous
- **Evidence**: validation skipped (--no-validate)
