# R6_TRANSPARENT_OBJECTS_IN_THREE_JS: Back transparent object vanishes when drawn after a closer one

## Bug
Two overlapping transparent quads are rendered with `glDepthMask(GL_TRUE)` and `GL_BLEND` enabled. The closer (outer) quad is drawn first; it writes depth values at z=0.2. The farther (inner) quad is drawn second at z=0.8, fails the depth test on every fragment, and contributes nothing to the framebuffer — even though its draw call is issued and blending is active.

## Expected Correct Output
A green outer quad with a teal/blue-tinted center where the inner blue quad blends through the green at 50% opacity. Both transparent objects visible.

## Actual Broken Output
Only the green outer quad is visible over the dark gray clear color. The inner blue quad is entirely absent from the framebuffer; no hint of blue appears anywhere.

## Ground Truth Diagnosis
The accepted Stack Overflow answer explains the mechanism directly:

> The `WebGLRenderer` in three.js sorts objects based upon their distance from the camera, and renders transparent objects in order from farthest to closest. ... So for two transparent objects to render correctly, the object that is in back ... must be rendered first. Otherwise, it will not be rendered at all, due to the depth buffer.

When transparent objects write depth and are drawn front-to-back, the first draw writes near depth values; subsequent farther transparent draws fail `GL_LESS` and emit zero fragments. The answer's three suggested fixes — `material.depthWrite = false`, `renderOrder`, and `sortObjects = false` — all address the same underlying foot-gun: **`GL_BLEND` enabled together with `GL_DEPTH_WRITEMASK = GL_TRUE`**. In the original Three.js report, the two spheres share a center, making the sort key ambiguous; whichever order the sort picks, the back sphere is culled by the front sphere's depth writes.

## Difficulty Rating
3/5

## Adversarial Principles
- transparent_depth_write_trap
- order_dependent_blending
- ambiguous_sort_at_equal_depth

## How OpenGPA Helps
`get_draw_call` exposes per-draw state: both draws have `GL_BLEND = enabled` AND `GL_DEPTH_WRITEMASK = GL_TRUE`, the canonical suspicious combo for transparency bugs. A pixel probe in the expected-overlap region via `get_pixel` returns pure green with no blue component, confirming the back object's fragments never reached the framebuffer.

## Source
- **URL**: https://stackoverflow.com/questions/15994944/transparent-objects-in-three-js
- **Type**: stackoverflow
- **Date**: 2013-04-12
- **Commit SHA**: (n/a)
- **Attribution**: Accepted answer by WestLangley (Three.js contributor)

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
  condition: blend_enabled_with_depth_write
  required_state:
    GL_BLEND: true
    GL_DEPTH_WRITEMASK: true
    GL_DEPTH_TEST: true
  applies_to: any_draw_call
  rationale: >
    Transparent objects (GL_BLEND enabled) that also write to the depth buffer
    are order-dependent: a closer transparent fragment occludes every farther
    transparent fragment regardless of alpha. Correct usage disables depth
    writes for transparent draws or sorts back-to-front strictly.
```

## Predicted OpenGPA Helpfulness
- **Verdict**: yes
- **Reasoning**: The bug is fully diagnosable from per-draw GL state without needing to interpret the rendered image. `get_draw_call` reveals the blend-plus-depth-write combo on both transparent draws, which is the textbook transparency bug signature. A follow-up `get_pixel` in the overlap region confirms the back object contributed zero fragments, closing the loop.

## Observed OpenGPA Helpfulness
- **Verdict**: ambiguous
- **Evidence**: validation skipped (--no-validate)
