# Vulkan Shim End-to-End Status — 2026-04-30

## Summary

The OpenGPA Vulkan capture layer (`VK_LAYER_BHDR_capture` /
`libVkLayer_bhdr_capture.so`) **builds clean** and **captures frames
end-to-end** against the engine. Verified with a minimal `xlib_surface`
present app on Mesa lvp (CPU swrast over Xvfb). 5 `vkQueuePresentKHR`
calls produced 5 captured frames in the engine, each with the correct
extent (320x240) and timestamp.

This means we can extend Round 13 mining to Vulkan-shape bugs from
Bevy / wgpu / Godot. See `tests/eval/r13_bevy_*` for the new scenarios
drafted in this round.

## Verification setup

- Build: `bazel build //src/shims/vk/...` — succeeds in 8.6s on a clean
  cache.
- Engine: own engine on port 18081 (`/tmp/bhdr_b.sock`, `/bhdr_b`) so the
  long-lived port-18080 engine wasn't disturbed.
- Test app: `/tmp/vk_present_test.c` (xlib_surface + minimal render pass
  via `vkCmdPipelineBarrier` to layout-transition the swapchain image
  to `PRESENT_SRC_KHR`, then `vkQueuePresentKHR`). 5 frames.
- Layer dir: `/tmp/bhdr_vk_layer/{libVkLayer_bhdr_capture.so,bhdr_layer.json}`
  with `VK_LAYER_PATH=/tmp/bhdr_vk_layer
  VK_INSTANCE_LAYERS=VK_LAYER_BHDR_capture`.
- Result: `curl localhost:18081/api/v1/frames` returned
  `{"frames":[1,2,3,4,5],"count":5}` after the test app exited.
- Per-frame overview reflects the swapchain extent correctly:
  `{"frame_id":1,"draw_call_count":0,"clear_count":0,
    "framebuffer_width":320,"framebuffer_height":240}`.

## Known issues (non-blocking)

1. **Stale broken symlink in the source tree**:
   `src/shims/vk/libVkLayer_gla_capture.so` is a symlink to a
   non-existent `bazel-bin/src/shims/vk/libVkLayer_gla_capture.so`. The
   actual artefact has the **gpa** spelling
   (`libVkLayer_bhdr_capture.so`). This is a pre-existing rename
   inconsistency; not blocking, but the broken symlink should be
   removed or repointed.

2. **`bhdr_layer.json` library_path**: the manifest in
   `src/shims/vk/bhdr_layer.json` references `./libVkLayer_bhdr_capture.so`
   (relative). When loading via `VK_LAYER_PATH` this works as long as
   the manifest sits next to the shared object. We sidestepped this in
   testing by writing a manifest with the absolute path.

3. **Soft warning during capture**: `[OpenGPA-VK] cannot resolve
   GetPhysicalDeviceMemoryProperties` is logged once per present.
   `vk_capture.c:370` falls back to `dlsym(RTLD_DEFAULT, ...)` which
   fails when running through the loader chain. This means CPU
   read-back of the swapchain image (for pixel queries) is not
   wired up yet — but `vkQueuePresentKHR`-triggered frame metadata
   (extent, format, draw-call count, clear count) is captured. Pixel
   readback is a follow-up; tracking under this same status doc.

4. **Draw-call count is 0 in the smoke test** because the smoke test
   only does a layout transition, not a real `vkCmdDraw`. The next step
   to harden the Vulkan path is to capture from a real Bevy scene
   (e.g. `cargo run --example 3d_shapes`) and confirm `vkCmdDraw* ` and
   `vkCmdBeginRenderPass` calls flow through to the engine — that's the
   work that the 5 new `r13_bevy_*` scenarios will exercise.

## Decision

Vulkan layer **works**. Proceeding to **Phase 2A (Bevy/wgpu mining)**.
5 candidates drafted, each with a closed issue + merged fix PR + parent
SHA pinned for reproducibility.

## Update 2026-04-30 — chromium captures via headless emulation

Implemented `VK_EXT_headless_surface` entirely inside the layer (no ICD
support required, NVIDIA 595's ICD doesn't expose it). Layer maintains a
small slot table of synthetic `VkSurfaceKHR` / `VkSwapchainKHR` handles
and allocates real `VkImage` + device-local memory under each emulated
swapchain. `vkAcquireNextImageKHR` rotates through the images;
`vkQueuePresentKHR` short-circuits all-headless presents (driver would
reject our synthetic handles).

Key correctness fix uncovered while testing real swapchains:
`disp->GetInstanceProcAddr(instance, "vkSomeExt")` from inside our own
intercept causes infinite recursion because the loader trampoline routes
extension-function lookups through every loaded layer (including us).
The fix is to resolve all instance-level extension functions ONCE at
`vkCreateInstance` time via `next_gipa` and store them on
`BhdrInstanceDispatch`. Same recursion was hiding the
`vkGetPhysicalDeviceMemoryProperties` "cannot resolve" warning in
`vk_capture.c`; that's now fixed via the same cached-pointer approach.

**Verified end-to-end with real chromium**:

```bash
BHDR_VULKAN_CAPTURE=1 \
VK_LAYER_PATH=/tmp/gpa-vk-layer \
chrome --headless=new --use-vulkan --use-angle=vulkan \
  --no-sandbox --disable-gpu-sandbox \
  --enable-features=Vulkan --enable-webgl --ignore-gpu-blocklist \
  --enable-unsafe-swiftshader file:///tmp/p2-index.html
```

`curl localhost:18085/api/v1/frames` returned 10 captured frames per
page-load with `framebuffer_width=500 framebuffer_height=300` (matches
the chromium `--window-size`).

**Pixel readback caveats**: chromium queues many in-flight submissions,
and the readback's transitive `WaitForFences` exceeds 1s before the
queue drains. The capture path falls back to "metadata-only" (extent,
format, draw count) on the timeout — frame boundaries flow through
cleanly but pixel content is unreliable for compositor-style apps. See
`fix(vk): make headless readback robust for chromium-vulkan` in the
git log.

This unblocks any agent eval scenario that spawns a Vulkan-backed
chromium GPU process (WebGL via ANGLE-Vulkan), which was previously
blocked by ANGLE's handle-scoped `dlsym()` of libGL bypassing
`LD_PRELOAD`. The Vulkan path takes a different layer-interposed
codepath that ANGLE cannot opt out of.

## Files touched / created in this round

- `docs/superpowers/eval/round13/vulkan-shim-status.md` (this file)
- `tests/eval/r13_bevy_depth_prepass_skipped_no_opaque/scenario.md`
- `tests/eval/r13_bevy_wireframe_depth_bias_line_topology/scenario.md`
- `tests/eval/r13_bevy_volumetric_fog_postprocess_ordering/scenario.md`
- `tests/eval/r13_bevy_no_cpu_culling_runtime_disappears/scenario.md`
- `tests/eval/r13_bevy_clustering_vertex_storage_webgpu/scenario.md`
