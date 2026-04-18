# R14_DEPTH_BUFFER_ISSUE_WHEN_USING_DEPTHOFFIE: CoC shader linearizes perspective depth as if it were orthographic

## Bug
Under a perspective projection, the DepthOfFieldEffect's circle-of-confusion (CoC) shader computed per-fragment focus by comparing the scene depth texture to a target depth derived from `worldFocusDistance`. When the `PERSPECTIVE_CAMERA` define was absent from `cocMaterial`, the shader treated the depth-buffer value as already linear in `[near, far]` and the target depth as `(focusDist - near) / (far - near)`. The depth buffer stores a nonlinear, perspective-encoded value, so the two sides of the CoC comparison use incompatible units. The equation accidentally holds only at the endpoints (near-plane depth = 0, far-plane depth = 1), which is why focus "works" when the target is at the clip planes but drifts toward the near plane for every distance in between.

## Expected Correct Output
A fullscreen red channel close to zero: a single plane at view-space z = −5.5, rendered under near=1/far=10 perspective, compared against a focus distance of 5.5, is exactly at the focus plane. CoC (= red channel) should be ~0 everywhere, so the center pixel reads `R ≈ 0`.

## Actual Broken Output
The center pixel reads `R ≈ 104` (out of 255), because the depth buffer stores ~0.909 for a perspective fragment at z=−5.5 while the shader's linear "focus depth" is 0.5. `|0.909 − 0.5| ≈ 0.409` is written into the red channel and the plane renders uniformly red instead of black. Reruns with `uFocusDist = 1.0` (near plane) or `uFocusDist = 10.0` (far plane) produce `R ≈ 0` as expected, demonstrating the nonlinearity: only the endpoints satisfy the shader's linear assumption.

## Ground Truth Diagnosis
Two independent comments on the thread identify the root cause. First, maintainer @vanruesc (comment 9) acknowledges that the CoC path assumes a linear mapping that only matches an orthographic camera:

> The unexpected behaviour that can be observed when the target is off-center has to do with perspective projection. The object would probably remain in focus at all times with an orthographic camera. The effect translates the world distance to a linear, orthographic depth value which basically counters the perspective projection.

Second, a user (comment 12) pinned the exact preprocessor flag governing the path:

> I had the same issue, with the focus working only with low and high value. In my case the defines "PERSPECTIVE_CAMERA" wasn't present in cocMaterial. By adding it like this: `depthOfFieldEffect.cocMaterial.defines.PERSPECTIVE_CAMERA = "1"` it solved my problem.

With the define set, the shader runs `perspectiveDepthToViewZ(depth, near, far)` before feeding the value into `viewZToOrthographicDepth`; without it, the nonlinear buffer value is used directly. The proper long-term fix — compute distance from fragment to camera, giving a spherical focus field — was tracked in issue #569 and landed in v6.38.0:

> distance-based CoC has made it into Version 6.38.0. Focus distance/range are now always in world units and target tracking should also work as expected now.

## Difficulty Rating
4/5

## Adversarial Principles
- unit-mismatch-across-pipeline-stages — depth buffer stores nonlinear perspective z; the shader consumes it as if it were linear
- endpoint-aliased-correctness — the bug is invisible at the near and far clip planes, where the linear and perspective encodings agree by construction
- preprocessor-define-gates-correctness — a missing `#define PERSPECTIVE_CAMERA` silently switches the shader into the wrong depth-linearization branch with no compilation failure

## How OpenGPA Helps
An agent looking at a washed-out / uniformly blurred CoC pass can ask OpenGPA for the active fragment shader source and the set of `#define`s applied to the post-process draw call, alongside the projection matrix of the scene draw that wrote the sampled depth texture. Seeing a perspective projection matrix in the producer draw plus a CoC shader whose depth-linearization branch lacks `PERSPECTIVE_CAMERA` — or reads the depth texel as if it were linear — is the diagnostic signature. Without this, the agent is left guessing whether the issue is logarithmic-depth, camera-settings timing, or world-vs-view coordinates (each of which came up on the thread before the root cause was identified).

## Source
- **URL**: https://github.com/pmndrs/postprocessing/issues/426
- **Type**: issue
- **Date**: 2022-11-16
- **Commit SHA**: (n/a)
- **Attribution**: Reported by @hybridherbst; root cause identified by @vanruesc and confirmed by a commenter who pinpointed the missing `PERSPECTIVE_CAMERA` define; distance-based fix shipped in postprocessing v6.38.0

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
  # Center pixel of the CoC output. The rendered plane is exactly at the
  # focus distance under perspective projection; with the perspective-aware
  # path, the red channel (CoC magnitude) should be ~0. With the bug, the
  # depth buffer's nonlinear value (~0.909) is compared against a naively
  # linearized focus depth (0.5), so the red channel is ~104/255.
  pixel: {x: 64, y: 64}
  expected_rgb: [0, 0, 0]
  tolerance: 16
  actual_when_buggy_rgb: [104, 0, 0]
  actual_tolerance: 16
```

## Predicted OpenGPA Helpfulness
- **Verdict**: yes
- **Reasoning**: The diagnosis requires correlating state across two draw calls (the scene geometry's projection matrix and the post-process CoC fragment shader's defines/source), which is exactly what OpenGPA's per-draw-call Tier 1 capture exposes as raw facts without heuristics. The thread itself shows the failure mode of screenshot-only debugging: reporters churned through camera-setting timing, logarithmic depth, world-vs-view coordinates, and `getWorldPosition` bugs before the depth-linearization branch was identified months later.

## Observed OpenGPA Helpfulness
- **Verdict**: ambiguous
- **Evidence**: validation skipped (--no-validate)
