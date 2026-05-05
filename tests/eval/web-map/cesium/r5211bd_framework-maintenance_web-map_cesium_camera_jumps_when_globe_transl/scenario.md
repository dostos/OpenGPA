## User Report

### What happened?

I've encountered an issue with the camera jumping when globe translucency is enabled, starting from version 1.136
However, if we disable globe translucency, the camera movement works smoothly.
After investigating, I suspect that this issue might be related to recent changes in picking functionality.
The fix #12999 applied to https://github.com/CesiumGS/cesium/blob/ea5f4d9d2db6e9743ba8658852b4d63e41568685/packages/engine/Source/Scene/ScreenSpaceCameraController.js#L1145 `pickPosition` function (as issue affects not only zoom) helps mitigate the issue, but it also introduces a laggy camera movement due to throttled interactions, so I don't think it's a viable workaround.

### Reproduction steps

1. Open the [Sandcastle](https://sandcastle.cesium.com/#c=rVRbb9s2FP4rnF8qDQ4dJ02XOq7bxWmAAW0yLFn3ohdKOrYJ06RAUk7Uof+9hxfJshMULdon8dy/c/nEN5XSlvxOmCFzMLzekIVWG5INCi9lg4tMZrJQ0liy5fAAmrwhEh6iN/3kdUnrP1fSMi5BZ4Mh+T+ThFjQGjWTNuA+yNSV+U9pUUZFkg4z+SXtlTMFSMBqoSz14kVrXAqVO6PXUi/50CCbQgPIu4oVMGcb0Mzh0koIzAOS5QLmKHDDlbwCC4XFByZbMGFcGp+OWs2kETUmLBoHV9przPenqFbssrnixjJZwP40boDpa6bvCiYYDgXbf3l8TI+H7tV+zzvN2H/7LQsll9zWpUt7ND45oefnr16Nj7uuBbOt+eVrejI+PX/9R2dcAV+uLJpOdwGVMjw2FyHOmbb4YvLUr+AKljgqk3SVh12RYcyYxmxKABVqmbQ504PT+KhKEFgorL03vPd+4uUElTX4zheshN0MewbmpjvBWZ25a/AFIu61VMVa1datpVgnXcG069UqJXLm7rNURb0BaekS7HsB7nnZ/FXilUafbODCDjOzqhLNJZcll0uzqzBsM7uYhdIkCfUkXhbhctd7GlrnC7ILpitmbh/k31pVoG2TuKA0OhJyiADx3uYG9NYNrI/Ah1FT53jZPIekrkpmwQEi5AtOyg1qUctwyMGYxCrPHHOgQBm5FXA+szA/fkIE2LAX9L+pNznSfRfmDQFH6/MbNzfsJgkW8jbqJ+7c9/xi8x+ZXdFCsE0VQoaeKc47jQB+gI5UIgM/MVE7ivh0Fz+aYdElCDva9bp/tdgZYsS+2jK4hHbyHngm45+r8L8guhDNvUr8TkowlkvmtjXpOOoJoDTHa42WeCUVt8Vqsjcvq/5hJZLYJEenZ2l7BelgOJga2wiYOdU7Hv7utRYJpSMLmwq5DWaU18UaLC2McUinozZkWvIt4eWbZ/7mBDdkDFoWtRB3/DNkg9l0hP57YUIxR57bLWjBGueyGs8+BCWldDpC8WlUR0qPemrd8c1C61Obq7KJghN193ZSObvv7ZTEu56O0LDvtpNQ5rKq8XfRVOA6XUGxztUjtoi7Y0c58r9Vh3/WE16g66ifv18OBf0NuNd4QiRvSBmP6JdC3b/Pn0DpKfFd0Poa0uLEiS2x/L5twyWakNpPDOwRDeOnBmOh8iHjQ0u/+63jaiThkHjpX8/CCXnhIb7Yjx59Y8AWHi2OzeB5o3R2MOd+pe8cLj67+8V3POyWAV8B)
2. Attempt to move the camera by zooming in/out (this should be the simplest option)
3. Observe that the camera jumps unexpectedly
4. Re-run the Sandcastle demo, disable globe translucency and try moving the camera again
5. Notice that the camera now works as expected and moves smoothly

### Sandcastle example

https://sandcastle.cesium.com/#c=rVRbb9s2FP4rnF8qDQ4dJ02XOq7bxWmAAW0yLFn3ohdKOrYJ06RAUk7Uof+9hxfJshMULdon8dy/c/nEN5XSlvxOmCFzMLzekIVWG5INCi9lg4tMZrJQ0liy5fAAmrwhEh6iN/3kdUnrP1fSMi5BZ4Mh+T+ThFjQGjWTNuA+yNSV+U9pUUZFkg4z+SXtlTMFSMBqoSz14kVrXAqVO6PXUi/50CCbQgPIu4oVMGcb0Mzh0koIzAOS5QLmKHDDlbwCC4XFByZbMGFcGp+OWs2kETUmLBoHV9przPenqFbssrnixjJZwP40boDpa6bvCiYYDgXbf3l8TI+H7tV+zzvN2H/7LQsll9zWpUt7ND45oefnr16Nj7uuBbOt+eVrejI+PX/9R2dcAV+uLJpOdwGVMjw2FyHOmbb4YvLUr+AKljgqk3SVh12RYcyYxmxKABVqmbQ504PT+KhKEFgorL03vPd+4uUElTX4zheshN0MewbmpjvBWZ25a/AFIu61VMVa1datpVgnXcG069UqJXLm7rNURb0BaekS7HsB7nnZ/FXilUafbODCDjOzqhLNJZcll0uzqzBsM7uYhdIkCfUkXhbhctd7GlrnC7ILpitmbh/k31pVoG2TuKA0OhJyiADx3uYG9NYNrI/Ah1FT53jZPIekrkpmwQEi5AtOyg1qUctwyMGYxCrPHHOgQBm5FXA+szA/fkIE2LAX9L+pNznSfRfmDQFH6/MbNzfsJgkW8jbqJ+7c9/xi8x+ZXdFCsE0VQoaeKc47jQB+gI5UIgM/MVE7ivh0Fz+aYdElCDva9bp/tdgZYsS+2jK4hHbyHngm45+r8L8guhDNvUr8TkowlkvmtjXpOOoJoDTHa42WeCUVt8Vqsjcvq/5hJZLYJEenZ2l7BelgOJga2wiYOdU7Hv7utRYJpSMLmwq5DWaU18UaLC2McUinozZkWvIt4eWbZ/7mBDdkDFoWtRB3/DNkg9l0hP57YUIxR57bLWjBGueyGs8+BCWldDpC8WlUR0qPemrd8c1C61Obq7KJghN193ZSObvv7ZTEu56O0LDvtpNQ5rKq8XfRVOA6XUGxztUjtoi7Y0c58r9Vh3/WE16g66ifv18OBf0NuNd4QiRvSBmP6JdC3b/Pn0DpKfFd0Poa0uLEiS2x/L5twyWakNpPDOwRDeOnBmOh8iHjQ0u/+63jaiThkHjpX8/CCXnhIb7Yjx59Y8AWHi2OzeB5o3R2MOd+pe8cLj67+8V3POyWAV8B

### Environment

Browser: Chrome
CesiumJS Version: 1.136
Operating System: WIndows 11

## Actual

?

I've encountered an issue with the camera jumping when globe translucency is enabled, starting from version 1.136
However, if we disable globe translucency, the camera movement works smoothly.
After investigating, I suspect that this issue might be related to recent changes in picking functionality.
The fix #12999 applied to https://github.com/CesiumGS/cesium/blob/ea5f4d9d2db6e9743ba8658852b4d63e41568685/packages/engine/Source/Scene/ScreenSpaceCameraController.js#L1145 `pickPosition` function (as issue affects not only zoom) helps mitigate the issue, but it also introduces a laggy camera movement due to throttled interactions, so I don't think it's a viable workaround.

## Ground Truth

See fix at https://github.com/CesiumGS/cesium/pull/12983.

## Fix

```yaml
fix_pr_url: https://github.com/CesiumGS/cesium/pull/12983
fix_sha: 644c18332b0a6991868176f358c84d7d7724b292
fix_parent_sha: a6e02269689225d85fa0a6edefcbdafcf9cd40a9
bug_class: consumer-misuse
files:
  - packages/engine/Source/Renderer/Buffer.js
  - packages/engine/Source/Renderer/BufferUsage.js
  - packages/engine/Source/Renderer/Context.js
  - packages/engine/Source/Renderer/Sync.js
  - packages/engine/Source/Scene/PickFramebuffer.js
  - packages/engine/Source/Scene/Picking.js
  - packages/engine/Source/Scene/Scene.js
  - packages/engine/Specs/Renderer/BufferSpec.js
  - packages/engine/Specs/Renderer/ContextSpec.js
  - packages/engine/Specs/Renderer/SyncSpec.js
  - packages/engine/Specs/Scene/PickingSpec.js
  - packages/engine/Specs/Scene/SceneSpec.js
```
