# Vulkan Shim

Vulkan implicit layer (`VK_LAYER_GPA_capture`) for OpenGPA. Hooks into the Vulkan dispatch chain to intercept command buffer recording and queue submissions, capturing frame metadata without modifying the application.

## Key Files
- `gpa_layer.c` — layer entry points, `vkGetInstanceProcAddr` / `vkGetDeviceProcAddr` overrides
- `vk_dispatch.c` — dispatch table construction and chaining
- `vk_capture.c` — frame capture triggered at `vkQueuePresentKHR`
- `gpa_layer.json` — layer manifest consumed by the Vulkan loader

## See Also
- `src/core/README.md` — engine that receives capture data
- `examples/vulkan/README.md` — minimal test app for validating this layer
