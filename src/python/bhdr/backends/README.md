# Capture Backends

Capture backend abstraction layer for OpenGPA. Defines the `FrameProvider` ABC and ships two concrete implementations so the rest of the stack is decoupled from the capture source.

## Key Files
- `base.py` — `FrameProvider` ABC (interface all backends must implement)
- `native.py` — `NativeBackend`: wraps the C++ engine via `_gpa_native` bindings
- `renderdoc.py` — `RenderDocBackend`: reads `.rdc` capture files offline

## See Also
- `src/bindings/README.md` — pybind11 module used by `NativeBackend`
- `src/python/bhdr/api/README.md` — API layer that instantiates backends
