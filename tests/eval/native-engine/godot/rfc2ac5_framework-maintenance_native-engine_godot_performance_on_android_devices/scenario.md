## User Report

### Tested versions

- Reproducible in: 4.4.dev4, 4.4.stable, 4.4.1.stable, and later **4.5 snapshots**.
- Not reproducible in: **4.4.dev3**, and earlier 4.4 snapshots.

### System information

Android 14 Samsung One UI 5.1 - Vulkan (Mobile) - Mali-G52 MC2

### Issue description

Until version *4.4dev3*, Godot on Android had good performance. A simple 3D example ran at 60fps, but starting with version *4.4dev4*, the same project dropped to an average of 45fps.

Here's a comparison:

| v4.4 dev3 | v4.4 dev4 | v4.5 beta4 |
| --- | --- | --- |
| ![Image](https://github.com/user-attachments/assets/e430d0ae-eecc-4471-bb4e-d73f7c8ad1e0) | ![Image](https://github.com/user-attachments/assets/b9aeed38-d094-40f4-9fe0-b2ae8f649954) | ![Image](https://github.com/user-attachments/assets/b7b66d6f-1f86-4a9c-b027-34e6ebcd2689) |

> Note¹: I hadn't noticed before because I don't really always use Android.
> Note²: 4.4.dev4 changelog: https://godotengine.github.io/godot-interactive-changelog/#4.4-dev4

build templates used:

* https://github.com/godotengine/godot-builds/releases/download/4.4-dev3/Godot_v4.4-dev3_export_templates.tpz
* https://github.com/godotengine/godot-builds/releases/download/4.4-dev4/Godot_v4.4-dev4_export_templates.tpz
* https://github.com/godotengine/godot-builds/releases/download/4.5-beta4/Godot_v4.5-beta4_export_templates.tpz

### Steps to reproduce

* Test any 3D project on Godot 4.4dev3 or lower.
* Then test on any higher version, including 4.5.beta4.

### Minimal reproduction project (MRP)

[MRP.zip](https://github.com/user-attachments/files/21561479/MRP.zip)

Contents:

```none
MRP.zip
├───.godot/
│   ├───.gdignore
│   └───export_credentials.cfg
├───debug.keystore
├───export_presets.cfg
├───icon.svg
├───icon.svg.import
├───level.tscn
├───project.godot
└───release.keystore
```

## Actual

Until version *4.4dev3*, Godot on Android had good performance. A simple 3D example ran at 60fps, but starting with version *4.4dev4*, the same project dropped to an average of 45fps.

Here's a comparison:

| v4.4 dev3 | v4.4 dev4 | v4.5 beta4 |
| --- | --- | --- |
| ![Image](https://github.com/user-attachments/assets/e430d0ae-eecc-4471-bb4e-d73f7c8ad1e0) | ![Image](https://github.com/user-attachments/assets/b9aeed38-d094-40f4-9fe0-b2ae8f649954) | ![Image](https://github.com/user-attachments/assets/b7b66d6f-1f86-4a9c-b027-34e6ebcd2689) |

> Note¹: I hadn't noticed before because I don't really always use Android.
> Note²: 4.4.dev4 changelog: https://godotengine.github.io/godot-interactive-changelog/#4.4-dev4

build templates used:

* https://github.com/godotengine/godot-builds/releases/download/4.4-dev3/Godot_v4.4-dev3_export_templates.tpz
* https://github.com/godotengine/godot-builds/releases/download/4.4-dev4/Godot_v4.4-dev4_export_templates.tpz
* https://github.com/godotengine/godot-builds/releases/download/4.5-beta4/Godot_v4.5-beta4_export_templates.tpz

## Ground Truth

See fix at https://github.com/godotengine/godot/pull/93933.

## Fix

```yaml
fix_pr_url: https://github.com/godotengine/godot/pull/93933
fix_sha: 8455b3343e723dbcaf4365e311371a80c448f121
bug_class: user-config
files:
  - doc/classes/ProjectSettings.xml
  - editor/editor_settings.cpp
  - main/main.cpp
  - platform/android/java/app/AndroidManifest.xml
  - platform/android/java/app/config.gradle
  - platform/android/java/editor/build.gradle
  - platform/android/java/editor/src/main/java/org/godotengine/editor/GodotEditor.kt
  - platform/android/java/editor/src/main/java/org/godotengine/editor/GodotGame.kt
  - platform/android/java/lib/src/org/godotengine/godot/Godot.kt
  - platform/android/java/lib/src/org/godotengine/godot/GodotFragment.java
  - platform/android/java/lib/src/org/godotengine/godot/GodotIO.java
  - platform/android/java/lib/src/org/godotengine/godot/GodotLib.java
  - platform/android/java/lib/src/org/godotengine/godot/gl/GLSurfaceView.java
  - platform/android/java/lib/src/org/godotengine/godot/input/GodotGestureHandler.kt
  - platform/android/java/lib/src/org/godotengine/godot/input/GodotInputHandler.java
  - platform/android/java/lib/src/org/godotengine/godot/input/GodotTextInputWrapper.java
  - platform/android/java/lib/src/org/godotengine/godot/utils/BenchmarkUtils.kt
  - platform/android/java_godot_lib_jni.cpp
  - platform/android/java_godot_lib_jni.h
```
