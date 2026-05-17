# R14 Bevy mining — visual-symptom-only scenarios

Mining round to avoid the keyword-leak failure mode of R13 (where every
scenario named its subsystem and `code_only` solved 5/5 by grep). Each
scenario below is sourced from a closed Bevy issue whose **original**
body uses only end-user vocabulary (flicker, invisible, disappear,
bleeding, wrong color), with no maintainer-side terms (prepass,
pipeline, shader-stage, render-pass, etc.).

## Scenarios drafted (9)

| # | Scenario dir | Issue | Fix PR | Parent SHA12 | Why kept |
|---|---|---|---|---|---|
| 1 | `r14_bevy_mesh_flicker_mut_borrow` | bevy#19409 | bevy#21002 | `859d84910f74` | "Mesh flickers when getting a mutable borrow" — visual-only; bug is asset-event/change-tick ordering in `bevy_mesh/src/lib.rs`, no naming hints. |
| 2 | `r14_bevy_tilemap_edge_bleed` | bevy#22250 | bevy#22449 | `238e1ea665a1` | "Color bleeding along tile edges" — visual-only; fix is sub-pixel UV rounding in a WGSL fragment shader; user blames "graphics-API issue". |
| 3 | `r14_bevy_sprite_mesh_one_frame_late` | bevy#23590 | bevy#23591 | `20407a3767b7` | "Right-hand image flickers / disappears" — visual; system-ordering bug. (User did suggest a file in their body — trimmed in scenario for fairness.) |
| 4 | `r14_bevy_text_wrap_flicker_resize` | bevy#9874 | bevy#9923 | `96a7b4a777d7` | "Text flickers between one and two lines" — visual; bug is sub-pixel rounding feedback loop in UI layout. |
| 5 | `r14_bevy_meshes_disappear_camera_motion` | bevy#18550 | bevy#18761 | `dc7c8f228faa` | "Meshes appear and disappear with camera motion" — pure visual; bug is off-by-one in indirect-draw batching. |
| 6 | `r14_bevy_invisible_after_material_swap` | bevy#18608 | bevy#18631 | `95b9117eac34` | "Cubes invisible when material is swapped in a hook" — visual; bug is in mesh extract not in hooks. |
| 7 | `r14_bevy_child_text_invisible` | bevy#18616 | bevy#18664 | `9daf4e7c8b69` | "Text disappears when toggling between menus" — visual; bug is stale `Local` in UI traversal. |
| 8 | `r14_bevy_text_vanishes_during_drag` | bevy#23004 | bevy#23190 | `c89541a1af0a` | "Text vanishes while dragging window" — visual; bug is async font-instance lifecycle. |
| 9 | `r14_bevy_subtree_invisible_after_reparent` | bevy#23893 | bevy#24019 | `5754300ef001` | "Re-parented subtree becomes invisible" — visual; bug is generic propagation walker early-out, not in any UI file. |

All 9 are sourced from issues closed by a single linked PR (`closedByPullRequestsReferences[0]`) — multi-PR fixes were rejected.

## Rejected for vocabulary leakage

Issues whose original body explicitly named a subsystem in the user-side
description, making them grep-tractable:

- bevy#23143 "SMAA flickering" — leaks `SMAA`
- bevy#22963 "Flickering in `anti_aliasing` example with FXAA enabled" — leaks `FXAA`
- bevy#23472 "`scrolling_fog` example broken since `PostProcess` set split" — leaks `PostProcess`
- bevy#23061 "Motion blur broken on WebGL/WebGPU" — leaks subsystem
- bevy#19177 "Forward decals broken on Web (crashes WebGL2, requires `Msaa::Off`)" — leaks `MSAA`, `WebGL`, `WebGPU`
- bevy#16531 "Toggling sharpening on then off massively oversharpens" — leaks `sharpening`
- bevy#23769 "Pcss example is broken" — leaks `Pcss` (percentage-closer soft shadows)
- bevy#22882 "Atmosphere only renders a half sphere" — leaks `Atmosphere`
- bevy#21784 "Atmosphere with Gizmos is broken" — leaks `Atmosphere`, `Gizmos`
- bevy#18371 "SpotLight / PointLight artifacts in FogVolume" — body extensively names `VolumetricFog`, `FogVolume`, `VolumetricLight`
- bevy#5809 "Wrong background color with the same `ClearColor` on some machines" — body names `gamma`
- bevy#4356 "ClearColor and Sprite same value yields different color" — same gamma issue, leaks color-space hint
- bevy#16185 "Shadows in 3D scene are flickering" — leaks `shadow`
- bevy#22179 "Strange clipping in joints in gizmos example" — leaks `gizmos`
- bevy#5656 "Flickering with transparency and identical 'depth'" — leaks `depth`
- bevy#3307 "ClearPass leads to flickering" — leaks `ClearPass`
- bevy#5426 "Background changes color when all entities are despawned" — *no* maintainer fix PR linked (rejected on tractability rather than vocabulary)
- bevy#23473 "Adding NoCpuCulling to a mesh at runtime hides the mesh" — *no* fix PR linked yet
- bevy#22705 "Mesh spawned with `Disabled` remains invisible after enabling" — *no* fix PR linked
- bevy#21934 "Adding an Observer with Camera2d makes scene disappear" — *no* fix PR linked
- bevy#20652 "Mesh Material becomes invisible when mouse hovers if entity has observers" — *no* fix PR linked
- bevy#18904 "Meshes not rendering with default GpuPreprocessing on Intel iGPU" — body leaks `GpuPreprocessing`; fix is in `mesh_preprocess.wgsl`
- bevy#20334 "Window displays incorrect magenta color" — *no* fix PR linked
- bevy#21896 "Visual errors with meshes on bevy example" — *no* fix PR; user-side speculative
- bevy#18945 "PointLight shadows glitch out in 0.16" — leaks `PointLight`, `shadows`
- bevy#19000 "Corrupted rendering with Integrated Intel GPUs + Vulkan + Indirect" — leaks `Vulkan`, `Indirect`
- gfx-rs/wgpu#7922, #6786, #5491 etc. — body specifies backend or buffer-reuse causes (vocab leak)

Rough count: **20+ candidates rejected** for vocabulary leakage or
no-single-PR-fix; **9 kept**.

## What changed vs R13

R13 used issue *titles* containing the maintainer's diagnosis (e.g.
"depth prepass skipped" — a maintainer's wording, not the user's).
R14 starts from issue *bodies* and excludes any title that names a
subsystem. Several R14 issues that were closed via a single PR could
have been kept under R13's looser bar but were rejected here.

## Next step

Run the same `code_only` Explore subagent against these 9 scenarios
with the upstream snapshot at each `fix_parent_sha`, and compare
file-level hit rate to R13. R13 hit 5/5; if R14 hits noticeably less
(say ≤6/9), then runtime capture has measurable headroom on these
bugs and we can move to running them with `with_bhdr`.
