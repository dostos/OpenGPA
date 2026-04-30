# Round 14 — Godot mining summary

Mined 7 Godot rendering bugs whose **issue body** is visual-symptom-only.
All have a single fix PR (no multi-PR fixes) and a clean
`fix_parent_sha` to anchor an upstream snapshot.

## Scenarios

| # | Slug | Why opaque | parent sha12 |
|---|------|-----------|-----------------|
| 1 | r14_godot_dpi_alpha_borders | Reporter says "black border around my sprite at non-integer position"; fix is in the asset importer, not the renderer | `fe6f78a4c788` |
| 2 | r14_godot_blit_rect_resize | Reporter says "second `blit_rect` produces wrong result after a resize"; root cause is two no-op setters that never re-allocate the GPU texture | `d1f2007d4954` |
| 3 | r14_godot_ninepatch_misalign | Reporter says "panels with identical params show 1-pixel texture offset depending on screen position"; root cause is half-float UV varying quantization | `895630e853b7` |
| 4 | r14_godot_canvasgroup_tiny_black | Reporter says "CanvasGroup goes solid black under 41px"; root cause is texture-storage's defensive size guard refusing to allocate the back-buffer base mip | `c4a893e98893` |
| 5 | r14_godot_lcd_button_transparent | Reporter says "duplicate of button has fully transparent background"; root cause is a per-batch state-leak flag in canvas batching | `a3e84cc2af14` |
| 6 | r14_godot_sprite_bleed_top | Reporter says "1-pixel white line appears above moving sprite, only at top edge"; root cause is pixel-snap performed in the wrong coordinate space in the canvas vertex shader | `621cadcf651b` |
| 7 | r14_godot_axes_flicker_distant | Reporter says "negative half of 3D editor axes flickers when zoomed far out"; root cause is editor-plugin gizmo geometry whose endpoint occasionally lands behind the near plane under fp precision | `9d6bdbc56e0a` |

## Rejected for vocabulary leakage

- **117423** (low-res normal maps + reflection artifacts) — closed
  as not-a-bug after maintainer pointed user at roughness limiter setting.
- **115075** (sampler array missing texture) — title and body name
  "shader" and "sampler array".
- **117890** (color correction Mobile renderer) — title leaks "Mobile
  renderer".
- **115431** (CanvasItem texture rect performance regression) —
  performance bug, not a visual symptom.
- **115476** (Polygon2D performance) — performance bug.
- **117303** (SDFGI on stereoscopic / frustum cameras) — body
  explicitly names SDFGI as the broken subsystem.
- **86530** (clearcoat NaN) — body says "Clearcoat enabled" which
  is a material vocabulary that points at the shader.
- **115906** (SSR blurriness) — body explicitly names SSR.
- **116146** (reflection probe ambient) — body explicitly names
  "reflection probe" + "ambient light".
- **117770** (LightmapGI probe update speed) — title names
  "Compatibility renderer".
- **114995** (Sprite3D fixed_size) — body uses "Forward+, Mobile,
  Compatibility" naming all three renderer subsystems; also has 2
  fix PRs (multi-PR, skip per constraint).
- **116775** (Gridmap mesh-cast-shadows + lightmap baking) — no
  closed-by PR linkage, can't establish a fix commit.
- **117082** (DPITexture) — kept (this is the one above).

## Notes

- All 7 kept scenarios have `observed_helps: ambiguous` with the
  rationale "validation pending — code_only baseline not yet run."
- API is set to `vulkan` for the RD-renderer (Forward+/Mobile)
  scenarios, `opengl` for the Compatibility-renderer scenarios,
  and `unknown` for editor-only or asset-importer scenarios.
- Source files in the issue body include some Godot-specific
  type names (e.g. `Sprite2D`, `CanvasGroup`, `Button`,
  `StyleBoxTexture`) — those are user-facing node and resource
  names, not renderer-internal subsystem names, so they pass the
  filter. They name *what* the user is using, not *how* it's
  rendered.
