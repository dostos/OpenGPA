## User Report

### Tested versions

Reproducible in 4.4.beta2, 4.4.beta3 & 4.3-Stable

### System information

Godot v4.4.beta2 - Linux Mint 22.1 (Xia) on X11 - X11 display driver, Multi-window, 2 monitors - OpenGL 3 (Compatibility) - NVIDIA GeForce RTX 4060 Ti (nvidia; 550.120) - AMD Ryzen 9 3900X 12-Core Processor (24 threads)

### Issue description

An image that is transparent, will break in the web on desktops if it is VRAM import if it is using transparent on Linux Desktop (Firefox & Chrome). Yet it works on Android mobile browser using Firefox, could this indicate that something is wrong with S3TC/BPTC but the same works in ETC2/ASTC? If the image that is having the problem is imported as Lossless or Lossy it works fine in the desktop browser.

Also I think it could be related to https://github.com/godotengine/godot/issues/58012. Though I could be wrong.

### Steps to reproduce

Run the included MRP in the web browser using 4.4.beta2 and notice the black images. After check the project and switch to the import tab and notice the way that the images were imported. All of the VRAM imported images are black in the web.

### Minimal reproduction project (MRP)

[VRAM_Broken_On_Web.zip](https://github.com/user-attachments/files/18708163/VRAM_Broken_On_Web.zip)

Closes #104590 (https://github.com/godotengine/godot/pull/104590)

## Actual

An image that is transparent, will break in the web on desktops if it is VRAM import if it is using transparent on Linux Desktop (Firefox & Chrome). Yet it works on Android mobile browser using Firefox, could this indicate that something is wrong with S3TC/BPTC but the same works in ETC2/ASTC? If the image that is having the problem is imported as Lossless or Lossy it works fine in the desktop browser.

Also I think it could be related to https://github.com/godotengine/godot/issues/58012. Though I could be wrong.

## Ground Truth

See fix at https://github.com/godotengine/godot/pull/104590.

## Fix

```yaml
fix_pr_url: https://github.com/godotengine/godot/pull/104590
fix_sha: e3063f5675f7952765b4aa7a9a0ec8c1a08cc184
bug_class: consumer-misuse
files:
  - core/io/image.cpp
  - core/io/image.h
  - core/io/resource_importer.cpp
  - core/io/resource_importer.h
```
