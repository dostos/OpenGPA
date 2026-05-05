## User Report

### Tested versions

v4.2.1.stable.official [b09f793f5]
I lack a reliable reproduction case to test other versions currently.

### System information

Windows 10, v4.2.1, Vulkan, ForwardPlus, RTX3090 (31.0.15.3734)

### Issue description

While the video shows a more complicated scene, I encountered this bug sporadically all throughout my project.
I have not yet found a way to reproduce it. Some days the bug did not occur at all.
I observed it together with issue #74790 so it might be related or not.

- Vulkan, Forward Plus, TAA and FXAA enabled.
- I used a World environment with Volumetric fog turned on and density at 1.0
- Then I placed several overlapping FogVolumes with negative density, here -1.5, to "cut out" parts of the global fog
- At this point the issue #74790 started appearing as well as rarely the black artifacts described here
- The black artifacts can seemingly not be recovered from and will cover the viewport eventually

https://github.com/godotengine/godot/assets/22944373/2c8b5a4b-dd99-4a23-a08a-7aae6bbcfdaa

My guess is that it is a NaN being propagated by the temporal reprojection.

I will keep this post updated with any new findings and hopefully a reproduction case to do regression testing.

### Steps to reproduce

Moving trough the fog eventually causes the issue.
I have not yet found any way to reliably reproduce this.
It happens very randomly. Sometimes not at all for a whole evening.

### Minimal reproduction project (MRP)

As I said, I don't know how to reliably reproduce it, but here is a setup like mine.
[FogVolumeBug.zip](https://github.com/godotengine/godot/files/13925356/FogVolumeBug.zip)

Closes #118198 (https://github.com/godotengine/godot/pull/118198)

## Actual

While the video shows a more complicated scene, I encountered this bug sporadically all throughout my project.
I have not yet found a way to reproduce it. Some days the bug did not occur at all.
I observed it together with issue #74790 so it might be related or not.

- Vulkan, Forward Plus, TAA and FXAA enabled.
- I used a World environment with Volumetric fog turned on and density at 1.0
- Then I placed several overlapping FogVolumes with negative density, here -1.5, to "cut out" parts of the global fog
- At this point the issue #74790 started appearing as well as rarely the black artifacts described here
- The black artifacts can seemingly not be recovered from and will cover the viewport eventually

https://github.com/godotengine/godot/assets/22944373/2c8b5a4b-dd99-4a23-a08a-7aae6bbcfdaa

My guess is that it is a NaN being propagated by the temporal reprojection.

I will keep this post updated with any new findings and hopefully a reproduction case to do regression testing.

## Ground Truth

See fix at https://github.com/godotengine/godot/pull/118198.

## Fix

```yaml
fix_pr_url: https://github.com/godotengine/godot/pull/118198
fix_sha: 179899680b588fcd64c7a8c5dce14ef663c6ff42
fix_parent_sha: 0b41f26b9b8b3bebce5417c3809d12c78502f05d
bug_class: consumer-misuse
files:
  - servers/rendering/renderer_rd/shaders/environment/volumetric_fog_process.glsl
```
