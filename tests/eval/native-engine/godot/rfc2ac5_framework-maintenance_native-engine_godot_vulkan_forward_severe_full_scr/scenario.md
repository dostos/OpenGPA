## User Report

### Tested versions

### Godot version
4.5.1.stable

### System information
Windows 11, Nvidia RTX 5060

### System information

Windows 11, Godot 4.5.1, Vulkan, Forward+

### Issue description

### Issue description
When using the Vulkan Forward+ renderer on a new Nvidia RTX 50-series GPU, severe unfiltered dithering/stippling artifacts cover the screen. It looks like a compute shader or denoiser fails to resolve the noise patterns.

This seems to be an architecture or driver-specific issue with the 50-series, as the exact same project renders perfectly clean on an older RTX 3060 Mobile GPU (see comparison screenshots attached).

**What I have already tested to isolate the issue:**
* I completely disabled SSAO, SSIL, SSR, and SDFGI in the WorldEnvironment and Project Settings -> The artifact remains.
* I tested changing Shadow Filters, Mesh LOD, and Material Distance Fades -> The artifact remains.
* I attempted to bypass the Vulkan driver by using the `--rendering-driver d3d12` launch argument. While this removes the dithering, D3D12 currently fails to compile distance-based shaders in my project (specifically Terrain3D clipmaps and Volumetric Fog), resulting in black rendering at a distance. Therefore, sticking to Vulkan is necessary.

<img width="2559" height="1439" alt="Image" src="https://github.com/user-attachments/assets/e45de573-41ca-4080-b377-cee25a960833" />
<img width="1919" height="1079" alt="Image" src="https://github.com/user-attachments/assets/721cf610-b4d0-4dfc-b01b-0f4f5c0e249d" />

### Steps to reproduce

### Steps to reproduce
1. Open a 3D scene using the Forward+ renderer.
2. Run the project on an Nvidia RTX 50-series GPU with the latest drivers.
3. Observe the heavy dithering/stippling overlay on geometry and shadows.

### Minimal reproduction project (MRP)

### Minimal reproduction project (MRP)
N/A (Hardware/Driver specific. The issue appears in regular 3D scenes on the mentioned GPU architecture).

## Ground Truth

See fix at https://github.com/godotengine/godot/pull/119038.

## Fix

```yaml
fix_pr_url: https://github.com/godotengine/godot/pull/119038
fix_sha: b81c232f043371f35407c69d26fa136daded385d
fix_parent_sha: c434c4528ad1aeaefbda80816b397bfb51f466cd
bug_class: consumer-misuse
files:
  - servers/rendering/renderer_rd/shaders/effects/cubemap_roughness_inc.glsl
```
