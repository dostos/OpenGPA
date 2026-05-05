## User Report

### Tested versions

v4.4.1.stable.official [49a5bc7b6]

### System information

Godot v4.4.1.stable - Android - Single-window, 1 monitor - Vulkan (Mobile) - integrated Adreno (TM) 610 -  (8 threads)

### Issue description

A Shodow or something like this apear on m
mobile Renderer

Here is a screenshot:
![Image](https://github.com/user-attachments/assets/1fee3751-38d2-4204-af5c-be63aaa3ed98)

If you look closely you can see a difference between top of the screen and bottom of the screen.

The shodow is mostly visable on dark texture/color

### Steps to reproduce

- open Android Editor
- add mesh and apply dark texture

### Minimal reproduction project (MRP)

[test-895_2025-08-12_19-03-40.zip](https://github.com/user-attachments/files/21736416/test-895_2025-08-12_19-03-40.zip)

## Actual

A Shodow or something like this apear on m
mobile Renderer

Here is a screenshot:
![Image](https://github.com/user-attachments/assets/1fee3751-38d2-4204-af5c-be63aaa3ed98)

If you look closely you can see a difference between top of the screen and bottom of the screen.

The shodow is mostly visable on dark texture/color

## Ground Truth

See fix at https://github.com/godotengine/godot/pull/109084.

## Fix

```yaml
fix_pr_url: https://github.com/godotengine/godot/pull/109084
fix_sha: 91a179847437c3bc58501aa337ce3bbe94b6df6b
fix_parent_sha: aa88eb2a759c2f67228cf22d0b0f8fdf336fa1fb
bug_class: consumer-misuse
files:
  - doc/classes/ProjectSettings.xml
  - doc/classes/RenderingServer.xml
  - doc/classes/Viewport.xml
  - drivers/gles3/rasterizer_scene_gles3.cpp
  - drivers/gles3/rasterizer_scene_gles3.h
  - editor/editor_node.cpp
  - scene/main/scene_tree.cpp
  - servers/rendering/dummy/rasterizer_scene_dummy.h
  - servers/rendering/renderer_rd/forward_mobile/render_forward_mobile.cpp
  - servers/rendering/renderer_rd/forward_mobile/scene_shader_forward_mobile.h
  - servers/rendering/renderer_rd/renderer_scene_render_rd.cpp
  - servers/rendering/renderer_rd/renderer_scene_render_rd.h
  - servers/rendering/renderer_rd/shaders/forward_mobile/scene_forward_mobile.glsl
  - servers/rendering/renderer_rd/shaders/forward_mobile/scene_forward_mobile_inc.glsl
  - servers/rendering/renderer_scene_cull.h
  - servers/rendering/renderer_scene_render.h
  - servers/rendering/rendering_method.h
  - servers/rendering/rendering_server.cpp
  - servers/rendering/rendering_server.h
  - servers/rendering/rendering_server_default.h
```
