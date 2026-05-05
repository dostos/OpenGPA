## User Report

### Tested versions

Godot v4.5.beta5 release

### System information

Godot v4.5.beta5 - Windows 11 (build 22631) - Multi-window, 1 monitor - Vulkan (Forward+) - Meta Quest 2 - dedicated NVIDIA GeForce RTX 4060 Laptop GPU (NVIDIA; 31.0.15.4660) - AMD Ryzen 7 8845H w/ Radeon 780M Graphics (16 threads) - 31.29 GiB memory

### Issue description

When using Godot XR, the **volumetric fog** seems to have a **wrong position** in the view of **XR camera**. Here are the screenshots from the MRP:\
The intended location of volumetric fog in godot editor:\
<img width="1094" height="617" alt="Image" src="https://github.com/user-attachments/assets/a080c6b4-d485-442b-9ec1-6289c5e885c1" />\
The actual running screenshots with different headset facing directions:\
<img width="2551" height="1346" alt="Image" src="https://github.com/user-attachments/assets/0b61b971-6faf-4872-9fa6-73a2037b3ce3" />
<img width="2557" height="1334" alt="Image" src="https://github.com/user-attachments/assets/c4c5bea6-26fe-4d97-80f6-b7f07185c939" />

---

In actual developing environments, this bug may cause the fog to be appeared in wrong position such as in the sky.\
The intended location of volumetric fog in godot editor (just above the sea and covers the rock stacks):\
<img width="888" height="547" alt="Image" src="https://github.com/user-attachments/assets/6775aefd-d3f6-404f-a687-af3edff0f41f" />\
The actual running screenshots with different headset facing directions, where the fog appears to be in the sky: \
<img width="902" height="780" alt="Image" src="https://github.com/user-attachments/assets/d0e0615e-383d-476f-b6bc-d031b526ac4b" />\
<img width="1176" height="1097" alt="Image" src="https://github.com/user-attachments/assets/9b212deb-7e24-481f-87bd-c5bb08a33532" />

### Steps to reproduce

1. Please create a project using Godot v4.5.beta5 and Vulkan (Forward+)
2. Import the "Godot XR Tools for Godot 4" plugin in AssetLib
3. Enable this plugin in Project Settings -> Plugins
4. Go to Project Settings -> General -> XR, and enable OpenXR and Shaders
5. Create a scene structure like this:\
<img width="381" height="216" alt="Image" src="https://github.com/user-attachments/assets/dbb3544d-0370-49e9-918f-cd911cc2a96c" /> \
6. Attach a script for the main node which contains these code:
  ```
  extends Node3D
  var xr_interface: XRInterface
  func _ready() -> void:
      xr_interface = XRServer.find_interface("OpenXR")
      if xr_interface and xr_interface.is_initialized():
          DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
          get_viewport().use_xr = true
  ```
7. Create a new Environment in the node WorldEnvironment, and enable the Volumetric Fog. Set the Density to 0.0 _(to disable the global fog)_, and set the Length to 1024 _(to make sure this area of fog can be seen in distance)_
8. Make sure the XR camea is outside of the volumetric fog, then run the game and you may find this issue.

### Minimal reproduction project (MRP)

[Issue Volumetric Fog.zip](https://github.com/user-attachments/files/21704323/Issue.Volumetric.Fog.zip)

Closes #115292 (https://github.com/godotengine/godot/pull/115292)

## Actual

When using Godot XR, the **volumetric fog** seems to have a **wrong position** in the view of **XR camera**. Here are the screenshots from the MRP:\
The intended location of volumetric fog in godot editor:\
<img width="1094" height="617" alt="Image" src="https://github.com/user-attachments/assets/a080c6b4-d485-442b-9ec1-6289c5e885c1" />\
The actual running screenshots with different headset facing directions:\
<img width="2551" height="1346" alt="Image" src="https://github.com/user-attachments/assets/0b61b971-6faf-4872-9fa6-73a2037b3ce3" />
<img width="2557" height="1334" alt="Image" src="https://github.com/user-attachments/assets/c4c5bea6-26fe-4d97-80f6-b7f07185c939" />

---

In actual developing environments, this bug may cause the fog to be appeared in wrong position such as in the sky.\
The intended location of volumetric fog in godot editor (just above the sea and covers the rock stacks):\
<img width="888" height="547" alt="Image" src="https://github.com/user-attachments/assets/6775aefd-d3f6-404f-a687-af3edff0f41f" />\
The actual running screenshots with different headset facing directions, where the fog appears to be in the sky: \
<img width="902" height="780" alt="Image" src="https://github.com/user-attachments/assets/d0e0615e-383d-476f-b6bc-d031b526ac4b" />\
<img width="1176" height="1097" alt="Image" src="https://github.com/user-attachments/assets/9b212deb-7e24-481f-87bd-c5bb08a33532" />

## Ground Truth

See fix at https://github.com/godotengine/godot/pull/115292.

## Fix

```yaml
fix_pr_url: https://github.com/godotengine/godot/pull/115292
fix_sha: b268b1013de7e7f17fed4186c0884bb00ad480d6
fix_parent_sha: 4738ce72e3af500ee3bd23506c04879f983ec98f
bug_class: consumer-misuse
files:
  - servers/rendering/renderer_rd/environment/sky.cpp
```
