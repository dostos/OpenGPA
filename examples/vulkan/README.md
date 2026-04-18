# Vulkan Example

Minimal Vulkan test application for OpenGPA. Used to validate that `VK_LAYER_GLA_capture` intercepts correctly and that frame data reaches the core engine without loss.

## Usage
```sh
VK_INSTANCE_LAYERS=VK_LAYER_GLA_capture ./vk_triangle
```

## What It Tests
- Layer discovery and loading via the Vulkan loader
- Dispatch table chaining through the layer
- Frame capture triggered at `vkQueuePresentKHR`
- Engine receipt and storage of the captured frame

## See Also
- `src/shims/vk/README.md` — layer implementation being exercised
