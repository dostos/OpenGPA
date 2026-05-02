## User Report

### Tested versions

4.2 Stable

### System information

WIndows 10 Godot Steam Version - Mobile Mode

### Issue description

In Godot 3x World Environment used to be simple on choosing what object should glow, you just had to add the World Environment change **Background** to **Canvas** , and **Enable Glow**.

But in Godot 4x The World Environment glow makes everything to glow even the things they aren't supposed to glow.

### **Example Imagen**
![image](https://github.com/godotengine/godot/assets/109998396/4fd4367a-0095-46e9-a657-b50d6603d2d5)

### Steps to reproduce

1. Go to **Project** -> **Project Settings**, Scroll into section of **Rendering** -> **Viewport** -> **Enable HDR 2D**
2. Add a **Node**
3. In the **Node**, add **two Sprite2d** node and set one to **RAW(1.5,1.5,1.5)**
4. Add a **WorldEnvironment+Environment**, set background to Canvas, enable Glow
5. Change **Glow Mode** to **Screen**
6. See both of them are glowing

### Minimal reproduction project (MRP)

[Godot Test FIles.zip](https://github.com/godotengine/godot/files/13654207/Godot.Test.FIles.zip)

Closes #109971 (https://github.com/godotengine/godot/pull/109971)

## Actual

In Godot 3x World Environment used to be simple on choosing what object should glow, you just had to add the World Environment change **Background** to **Canvas** , and **Enable Glow**.

But in Godot 4x The World Environment glow makes everything to glow even the things they aren't supposed to glow.

## Ground Truth

See fix at https://github.com/godotengine/godot/pull/109971.

## Fix

```yaml
fix_pr_url: https://github.com/godotengine/godot/pull/109971
fix_sha: ec62f12862c4cfc76526eaf99afa0a24249f8288
bug_class: user-config
files:
  - servers/rendering/renderer_rd/forward_clustered/render_forward_clustered.cpp
  - servers/rendering/renderer_rd/forward_mobile/render_forward_mobile.cpp
  - servers/rendering/renderer_rd/forward_mobile/render_forward_mobile.h
  - servers/rendering/renderer_rd/renderer_scene_render_rd.cpp
  - servers/rendering/renderer_rd/renderer_scene_render_rd.h
  - servers/rendering/renderer_rd/shaders/forward_clustered/scene_forward_clustered_inc.glsl
  - servers/rendering/renderer_rd/shaders/forward_mobile/scene_forward_mobile.glsl
  - servers/rendering/renderer_rd/shaders/forward_mobile/scene_forward_mobile_inc.glsl
  - servers/rendering/renderer_rd/shaders/scene_forward_lights_inc.glsl
  - servers/rendering/renderer_rd/storage_rd/light_storage.cpp
  - servers/rendering/renderer_rd/storage_rd/render_scene_buffers_rd.cpp
  - servers/rendering/renderer_rd/storage_rd/render_scene_buffers_rd.h
  - servers/rendering/renderer_rd/storage_rd/texture_storage.cpp
```
