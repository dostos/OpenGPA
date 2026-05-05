## User Report

### Tested versions

4.4.dev3, (Probably also 4.3)

### System information

Windows 10 High-End PC, tested on Android 14, Samsung Galaxy A35

### Issue description

With Mobile Renderer enabled, I created an empty scene without a sky or anything, and just put a MeshInstance with a Cube Mesh and a Standard Emissive Material. It renders with smooth 120 FPS on my Galaxy A35.

Then I enable Glow to actually see some glowing. It works on my PC, but on my phone:

1. The glow is not visible, as if it is turned off somehow.
2. FPS drops from 120 to 37...

Then I switched to Compatibility Renderer:
1. Glow is visible now
2. FPS is back to 120

If I do the same in Unreal Engine, no matter if I use GLES3 or Vulkan renderer there, it is always at 60 FPS and Glow is always working.

So there must be a huge performance issue with turning on Glow/Postprocessing with Mobile Renderer.

I read an official article that SSGI and other effects are not optimized in Godot yet and will improved with upcoming releases, so hopefully Glow will be part of that upcoming optimizations?

Anyway, thanks for your hard work on the engine, just wanted to report this and hope it gets fixed soon. (Still kinda hope there is just a setting I did wrong).

### Steps to reproduce

I attached MRP. Basically just make an emissive cube, run on low/mid-range android device with Mobile compared to Compatibility renderer.

### Minimal reproduction project (MRP)

[slowglowmrp.zip](https://github.com/user-attachments/files/17526220/slowglowmrp.zip)

Closes #110077 (https://github.com/godotengine/godot/pull/110077)

## Actual

With Mobile Renderer enabled, I created an empty scene without a sky or anything, and just put a MeshInstance with a Cube Mesh and a Standard Emissive Material. It renders with smooth 120 FPS on my Galaxy A35.

Then I enable Glow to actually see some glowing. It works on my PC, but on my phone:

1. The glow is not visible, as if it is turned off somehow.
2. FPS drops from 120 to 37...

Then I switched to Compatibility Renderer:
1. Glow is visible now
2. FPS is back to 120

If I do the same in Unreal Engine, no matter if I use GLES3 or Vulkan renderer there, it is always at 60 FPS and Glow is always working.

So there must be a huge performance issue with turning on Glow/Postprocessing with Mobile Renderer.

I read an official article that SSGI and other effects are not optimized in Godot yet and will improved with upcoming releases, so hopefully Glow will be part of that upcoming optimizations?

Anyway, thanks for your hard work on the engine, just wanted to report this and hope it gets fixed soon. (Still kinda hope there is just a setting I did wrong).

## Ground Truth

See fix at https://github.com/godotengine/godot/pull/110077.

## Fix

```yaml
fix_pr_url: https://github.com/godotengine/godot/pull/110077
fix_sha: 3c1e4792909fbaff63e2437f1c06029bd1aa507f
fix_parent_sha: c2c7bf6b01906677a681f6042a36cd3e835ecfb6
bug_class: consumer-misuse
files:
  - doc/classes/Environment.xml
  - drivers/gles3/effects/glow.h
  - drivers/gles3/rasterizer_scene_gles3.cpp
  - scene/resources/environment.cpp
  - scene/resources/environment.h
  - servers/rendering/renderer_rd/effects/copy_effects.cpp
  - servers/rendering/renderer_rd/effects/copy_effects.h
  - servers/rendering/renderer_rd/effects/smaa.cpp
  - servers/rendering/renderer_rd/effects/smaa.h
  - servers/rendering/renderer_rd/effects/tone_mapper.cpp
  - servers/rendering/renderer_rd/effects/tone_mapper.h
  - servers/rendering/renderer_rd/renderer_scene_render_rd.cpp
  - servers/rendering/renderer_rd/renderer_scene_render_rd.h
  - servers/rendering/renderer_rd/shaders/effects/blur_raster.glsl
  - servers/rendering/renderer_rd/shaders/effects/blur_raster_inc.glsl
  - servers/rendering/renderer_rd/shaders/effects/smaa_blending.glsl
  - servers/rendering/renderer_rd/shaders/effects/tonemap.glsl
  - servers/rendering/renderer_rd/shaders/effects/tonemap_mobile.glsl
  - servers/rendering/renderer_rd/storage_rd/render_scene_buffers_rd.cpp
  - servers/rendering/renderer_rd/storage_rd/render_scene_buffers_rd.h
  - servers/rendering/storage/environment_storage.cpp
  - servers/rendering/storage/environment_storage.h
```
