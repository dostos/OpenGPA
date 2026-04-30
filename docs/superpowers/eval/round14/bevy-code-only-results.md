# R14 Bevy code-only baseline — 2026-04-30

## Setup

9 R14 Bevy scenarios mined under the "no framework-internal vocabulary in
the user report" rule. Each scenario was given to a fresh Claude Code
Explore subagent with read+grep access to the upstream Bevy snapshot at
`fix_parent_sha`. Same harness as the R13 baseline (`bevy-code-only-results.md`),
just stricter source filtering.

## Aggregate result

| Round | Solved | Partial | Miss | Mean score |
|---|---|---|---|---|
| R13 (vocab-leaky reports) | 5/5 | 0 | 0 | **1.00** |
| R14 (visual-symptom-only) | 3/9 | 0 | 6 | **0.33** |

R14's drop from 100% → 33% confirms the hypothesis: filtering out
framework vocabulary in the user report removes the grep shortcut and
forces the agent to reason from symptoms alone — which it gets wrong
two-thirds of the time.

## Per-scenario

| # | Scenario | Score | Agent picked | Real fix |
|---|---|---|---|---|
| 1 | child_text_invisible | 0.0 | render/mod.rs | update.rs |
| 2 | invisible_after_material_swap | 0.0 | material.rs | render/mesh.rs |
| 3 | mesh_flicker_mut_borrow | 0.0 | assets.rs, components.rs | bevy_mesh/lib.rs |
| 4 | meshes_disappear_camera_motion | 0.0 | gpu_preprocessing.rs | render_phase/mod.rs |
| 5 | sprite_mesh_one_frame_late | **1.0** | sprite_mesh/mod.rs | (same) |
| 6 | subtree_invisible_after_reparent | **1.0** | propagate.rs | (same) |
| 7 | text_vanishes_during_drag | 0.0 | bevy_sprite/text2d.rs | bevy_text/font.rs |
| 8 | text_wrap_flicker_resize | 0.0 | bevy_text/text2d.rs | bevy_ui/widget/text.rs |
| 9 | tilemap_edge_bleed | **1.0** | tilemap_chunk_material.wgsl | (same) |

## Why 3 still solved

- **#5 sprite_mesh_one_frame_late**: a "right image disappears on first
  frame" report; the only `sprite_mesh/mod.rs` file in the tree is
  small, and the user describing "right image" combined with grep for
  the example name made the location trivial.
- **#6 subtree_invisible_after_reparent**: the user explicitly named
  `detach_children` / `insert_children` (ECS API surface). That counts
  as user-side vocabulary — borderline keep — and grep-trivial.
- **#9 tilemap_edge_bleed**: the title contains "tilemap edges", which
  is a user-facing word but maps 1:1 onto the only WGSL file with
  `tilemap` in its name.

## Why the other 6 failed

In every miss case the agent picked a *plausible adjacent file*:

- For #1, the user said "text disappears when toggling menus" — the
  agent found a glyph-range bug in `render/mod.rs` (rendering side).
  The actual bug is in `update.rs` (UI traversal). Both deal with text;
  the runtime data would tell you which.
- For #2, "cubes invisible when material is swapped" — agent landed on
  `material.rs` (visibility check). The real fix is in `render/mesh.rs`
  (mesh extraction). Both touch materials; only frame-state reveals
  which entity-set is missing.
- For #3, "mesh flickers when getting a mutable borrow" — agent
  blamed `Assets::get_mut`. Real fix is in the mesh-marking system.
  Both are correct *symptoms*; the dispatcher state would
  disambiguate.
- For #4, "meshes appear and disappear with camera motion" — both
  files (gpu_preprocessing, render_phase) implement related batch
  logic. Agent's reasoning was coherent but pointed one layer too low.
- For #7 and #8, Bevy has *three* parallel text subsystems
  (`bevy_text`, `bevy_sprite::text2d`, `bevy_ui::widget::text`). The
  user can't tell which they're using; the agent guesses wrong.
  Frame-state would show which subsystem produced the buggy frame.

These are exactly the cases where OpenGPA's runtime capture should
help — the **structural** answer is correct, only the **specific
location** is wrong, and a recorded draw call list would point at
the right entity → right system → right file.

## Reproducibility

- Prompts: `/tmp/r14_p{1..9}.txt`
- Answers: `/tmp/r14_a{1..9}.json`
- Scoring: `/tmp/score_r14_eval.py`
- Snapshots: `/data3/opengpa-snapshots/github_com__bevyengine__bevy__*`

## Next step

For each of the 6 failing scenarios, build the corresponding Bevy
example at the parent SHA, run it under the OpenGPA Vulkan layer, and
re-run the agent in `with_gla` mode. Goal: lift the 33% baseline to
60+%. That would be the first quantified evidence of OpenGPA's marginal
value.
