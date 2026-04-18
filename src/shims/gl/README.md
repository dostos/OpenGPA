# OpenGL Shim

OpenGL LD_PRELOAD shim for OpenGPA. Intercepts GL calls via `dlsym`, maintains a shadow copy of GPU state, and captures completed frames into a shared memory ring buffer.

## Key Files
- `gl_shim.c` — entry point, `dlopen`/`dlsym` interception setup
- `gl_wrappers.c` — per-function interceptors for tracked GL calls
- `shadow_state.c` — in-process mirror of bound textures, VAOs, programs, uniforms
- `frame_capture.c` — serializes frame data at `eglSwapBuffers`/`glXSwapBuffers`
- `ipc_client.c` — connects to the core engine over a Unix socket

## See Also
- `schemas/frame_capture.fbs` — FlatBuffers schema for the capture payload
- `src/core/README.md` — engine that receives these captures
