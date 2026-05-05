# Forensic: godot_4_2_world_environment — persistent unsolved

Unsolved across R12c / R12d / R13 in both modes. Worth a deeper look
because it's the canonical "agent diagnoses something plausible but
wrong" failure pattern.

## The bug

User report: with Godot 4.2 Mobile renderer + HDR 2D enabled +
`Environment.background_mode = BG_CANVAS` + Glow enabled, *every*
canvas pixel glows — even white sprites that should be below the
glow threshold.

## The actual fix (PR #109971)

13 files, scope: `servers/rendering/renderer_rd/`. Summary:

- New `force_hdr` member on `RenderSceneBuffersRD`, set true when
  `render_target_is_using_hdr(render_target)`.
- New `get_base_data_format()` method returning a **half-float**
  format when `force_hdr` is true (was UNORM unconditionally).
- New `get_luminance_multiplier()` method returning the right
  multiplier based on whether the buffer is HDR.
- Callers in `render_forward_*.cpp` / `renderer_scene_render_rd.cpp`
  switched from `base_data_format` (the old field) to
  `get_base_data_format()` (the new HDR-aware accessor).

In one sentence: **the 3D buffer was UNORM 8-bit when HDR 2D was on;
the fix makes it half-float so canvas pixels survive without
clipping**.

## What the agent diagnosed

(Verbatim from `/data3/gla-eval-results/2026-05-05-iter-r12c-rerun/with_gla.json`):

> CopyEffects::copy_to_drawlist skips the / luminance_multiplier
> (=2.0) division (it only fires inside the if (p_linear) branch,
> which is false when the destination is already HDR), so canvas
> pixels are stored at 1× while the 3D pipeline interprets the
> framebuffer with a 2× multiplier — doubling every 2D pixel before
> the glow glow_hdr_threshold test.

The agent identified `copy_to_drawlist` and the multiplier mismatch.
That code path does exist and the multiplier story is mechanically
sound — but it's a *consequence* of the bug, not the cause. The
fix doesn't touch `copy_effects.cpp`. It changes how the buffer
itself is created.

## Why the agent goes wrong

The agent's mental model: "Symptom = glow on everything → grep for
`glow` and `luminance` → find code that processes glow → look for
where the multiplier could be misapplied."

This finds the post-process glow path (`copy_to_fb.glsl`,
`copy_effects.cpp`) which *uses* `luminance_multiplier`, and the
agent constructs a plausible failure path through that code. But
the actual fix isn't there.

The right mental model would be: "Symptom only happens when HDR 2D
is enabled → grep for `hdr` and `HDR2D` → find code that activates
on HDR 2D → look at what *that* code does differently." This leads
to `render_target_is_using_hdr` and `get_base_data_format` —
exactly where the fix lives.

## Proposed next-iteration intervention

A general meta-hypothesis prompt addition: "**When the bug report
identifies a specific feature toggle, the fix is usually in code
that activates when that toggle is on — not in code adjacent to
the visible symptom.** Search for the toggle's enabling path before
searching for code near the symptom."

This generalizes beyond godot_4_2 — it applies to any "this
behavior is wrong when feature X is enabled" report. R12 cohort
candidates that fit this pattern:

- godot_4_2_world_environment: "when HDR 2D enabled" → look at
  HDR-2D-enabling code, not glow code
- godot_volumetric_fog_sporradically: "when XR enabled" → look at
  XR path
- maplibre 3d_terrain_with_partially_tran: "when terrain
  translucency enabled" → look at translucency path

Untested. Worth adding as a P1 candidate for R14 if other items
prove insufficient.

## What R13's scope hint did and didn't do

R13's scope hint correctly told the agent "13 files under
`servers/rendering/renderer_rd/`" — narrowing the search area. But
within that scope, the agent still picked the wrong file. The hint
calibrates *area* but not *causal direction*. The meta-hypothesis
above complements the scope hint by calibrating the *which-causal-
chain* axis.

## Status

- R12c, R12d, R13: unsolved both modes
- R14: still expected to fail without the meta-hypothesis prompt
  intervention. Track as a stable test case for the proposed
  prompt change in R15.
