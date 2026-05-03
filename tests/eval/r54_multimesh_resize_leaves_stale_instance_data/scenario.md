# R54_MULTIMESH_RESIZE_LEAVES_STALE_INSTANCE_DATA: MultiMesh instance-count change leaves stale GPU buffer regions (Godot)

## Bug
A Godot user grows a `MultiMesh` from N=4 back to N=8 and re-uploads
transforms for instances `[0..3]`, expecting Godot to clear or default-
init `[4..7]`. Godot keeps the same VBO and only writes the region the
caller touches; the remaining bytes still hold whatever transforms /
colors were last written for those slots. The reporter described this
as "strange data appears in the buffer", and instances 4..7 visually
appear at locations the user never set.

## Expected Correct Output
At least the four newly-uploaded green instances render in their new
green row at y≈128. The pixel sampled at (432, 80) — outside any
intentionally-drawn instance — must remain black. Instances 4..7 are
expected to be either cleared or rendered at the user's *new* intent
(off-screen / out of frame).

## Actual Broken Output
The four "stale" instances 4..7 are drawn at the GPU-resident positions
left from the previous N=8 frame: a cyan square renders at (432, 80)
even though no current MultiMesh instance was placed there. Sampling
that pixel yields `(0, 153, 153)` (`0.0, 0.6, 0.6` in linear, stored as
sRGB-clamped `0, 153, 153`) instead of the expected black.

## Ground Truth Diagnosis
The Godot reporter observed:

> When I change the instance count of MultiMesh, sometimes strange data
> will appear in the buffer.

The defect localises to the path that resizes (or re-uses) the per-
instance VBO across instance-count changes. In OpenGL terms, the
sequence is:

1. `glBufferData(VBO, 8 × stride, initial, GL_DYNAMIC_DRAW)` — upload
   eight initial instances.
2. The user lowers `instance_count` to 4 and re-raises it to 8.
3. `glBufferSubData(VBO, 0, 4 × stride, new_first_four)` — only the
   first four instances are rewritten.
4. `glDrawArraysInstanced(..., 8)` — the GPU reads instances 4..7 from
   the still-resident bytes from step 1.

GL gives this exactly-defined semantics (the bytes are whatever the
last write left there), so the bug is firmly in the engine /
application contract: the API user expects "set instance count" to
imply "instances beyond the count I personally re-set are reset", but
no such guarantee exists. The fix is either to `glBufferSubData` the
full count every frame, to `glClearBufferSubData` over the unused
range, or to orphan the VBO with `glBufferData(..., NULL, ...)` before
re-uploading.

## Difficulty Rating
4/5

## Adversarial Principles
- gpu-resident-stale-bytes-after-partial-update
- assumed-reset-semantics-not-actually-guaranteed
- only-some-instances-look-wrong (the "needle in a haystack" symptom)
- intermittent (only triggered by specific count-change sequences)

## How OpenGPA Helps
OpenGPA's per-draw snapshot exposes the raw per-instance attribute
buffer for the offending `glDrawArraysInstanced` call. An agent can
dump instances 0..7's `a_offset` and `a_color` and immediately spot
that 4..7 are at coordinates the application never wrote in the
current frame. Cross-referencing the most recent `glBufferSubData`
range (`[0, 4*stride)`) with the read range of the draw (`[0,
8*stride)`) shows the un-written tail — pointing directly at the
partial-update bug rather than at shader logic, viewport, or culling.

## Source
- **URL**: https://github.com/godotengine/godot/issues/75485
- **Type**: issue
- **Date**: 2023-03-29
- **Commit SHA**: (n/a)
- **Attribution**: Reported on Godot 4.1.dev (Windows / Vulkan); reduced to GL instance-buffer primitives for the eval

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
  region:
    x: 416
    y: 64
    width: 32
    height: 32
  expected_dominant_color: [0, 0, 0]
  min_fraction: 0.9
  rationale: "Region is outside any newly-uploaded instance; should be the cleared black background. If a cyan square appears (≈0,153,153), instances 4..7 read stale bytes from the prior upload."
```

## Predicted OpenGPA Helpfulness
- **Verdict**: yes
- **Reasoning**: The defect is fully expressible as a per-instance attribute trace for one draw call. OpenGPA's instance-attribute capture (already used for r19) directly exposes that the four trailing instances render at coordinates not reachable from the application's current transform set, and the buffer-update history shows only a 4-instance write was issued before the 8-instance draw. The agent reaches "stale instance buffer tail" without speculating about shader, depth, or culling.
