# R14 Godot code-only baseline — 2026-04-30

## Setup

7 R14 Godot scenarios mined under the same "no framework-internal
vocabulary" rule used for R14 Bevy. Each scenario was given to a fresh
Claude Code Explore subagent with read+grep access to the upstream
Godot snapshot at `fix_parent_sha`. Same harness as the R14 Bevy run.

## Aggregate result

| Round | Solved | Mean score |
|---|---|---|
| R13 Bevy (vocab-leaky) | 5/5 | **1.00** |
| R14 Bevy (visual-only) | 3/9 | **0.33** |
| R14 Godot (this run) | 7/7 | **1.00** |

## Per-scenario

| # | Scenario | Score | Agent picked | Real fix |
|---|---|---|---|---|
| 1 | axes_flicker_distant | **1.0** | node_3d_editor_plugin.cpp | (same) |
| 2 | blit_rect_resize | **1.0** | drawable_texture_2d.cpp | (same) |
| 3 | canvasgroup_tiny_black | **1.0** | gles3/storage/texture_storage.cpp | (same) |
| 4 | dpi_alpha_borders | **1.0** | dpi_texture.cpp + resource_importer_svg.cpp | (same) |
| 5 | lcd_button_transparent | **1.0** | renderer_canvas_render_rd.cpp | (same) |
| 6 | ninepatch_misalign | 1.0 | renderer_rd/shaders/canvas.glsl | renderer_canvas_render_rd.cpp + shaders/canvas.glsl |
| 7 | sprite_bleed_top | **1.0** | renderer_rd/canvas.glsl + gles3/canvas.glsl | (same) |

#6 is a "partial" — agent found the shader file but missed the
batching code. Under the same intersection-based scoring used for
R13/R14 Bevy, it counts as a hit (1.0).

## Why the Godot baseline came in at 100%

The Godot miner did not scrub Godot class names from the user reports.
Each report mentions one or more user-facing scene-tree classes that
map 1:1 onto the subsystem file via grep:

| Scenario | Leaked class names | What grep finds |
|---|---|---|
| axes | "3D editor", "axis line" | `node_3d_editor_plugin.cpp` |
| blit | `set_width`, `set_height`, `blit_rect` | `drawable_texture_2d.cpp` |
| canvasgroup | `CanvasGroup`, `SubViewport` | backbuffer in `texture_storage.cpp` |
| dpi | `DPITexture` (literal class name) | `dpi_texture.cpp` |
| lcd | `Button`, `StyleBoxTexture`, "subpixel text antialiasing" | `renderer_canvas_render_rd.cpp` |
| ninepatch | `StyleBoxTexture`, `texture_margin`, `region_rect` | `canvas.glsl` ninepatch path |
| sprite | `Sprite2D`, `AnimatedSprite2D` | `canvas.glsl` |

Crucially, Godot is not Bevy: Bevy has *three* parallel text
subsystems (`bevy_text`, `bevy_sprite::text2d`, `bevy_ui::widget::text`)
where the user can't tell which they're using, so naming "text" in the
report still leaves three plausible files. Godot has exactly one
`Sprite2D` rendering path (RD or GLES3), one `CanvasGroup`
implementation, one `node_3d_editor_plugin.cpp`. Naming the class
in the report effectively names the file.

This is a Godot-specific structural property, not just a miner
hygiene problem. R14 Bevy got headroom from the symmetry of
Bevy's three text crates; Godot doesn't have that symmetry to
exploit.

## What this means for OpenGPA on Godot

Two paths forward:

1. **Mine harder Godot bugs.** Look for cross-file bugs — e.g. a
   batching bug whose visible symptom is in Sprite2D but whose fix
   is in batch state hand-off, plus a parallel bug in a different
   stylebox path. The user can describe "sprite shows wrong color
   when StyleBox above it changes" and grep on either class won't
   land on the actual offender.
2. **Switch the metric.** File-level identification is too easy
   for Godot regardless of report-vocabulary because Godot's
   layering is shallow. A *line-range* metric (within ±50 lines of
   the actual fix hunk) would be much harder, and OpenGPA's draw
   call list would help disambiguate which branch of a file is
   active.

For now: mark all 7 R14 Godot scenarios `observed_helps: no` for
the file-level metric, and document that future Godot mining must
use cross-subsystem bugs, not single-class regressions.

## Reproducibility

- Prompts: `/tmp/r14g_p{1..7}.txt`
- Answers: `/tmp/r14g_a{1..7}.json`
- Manifest: `/tmp/r14g_manifest.json`
- Scoring: `/tmp/score_r14g_eval.py`
- Snapshots: `/data3/opengpa-snapshots/github_com__godotengine__godot__*`

## Next step

Two parallel actions:

- **Easy headroom**: re-run R14 Bevy in `with_gla` mode on the 6
  failing scenarios — that's where the 33%→60+% lift would land.
  Bevy scenarios already produce visual symptoms that beat
  code_only; the runtime trace should disambiguate which of the
  three text/render subsystems fired.
- **Godot mining v2**: target cross-subsystem Godot bugs (batch
  state, render-pass ordering, shader-cache invalidation across
  pipeline rebuilds) where grepping a class name returns several
  plausible files, not one.
