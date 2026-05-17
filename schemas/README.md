# Schemas

FlatBuffers schemas for IPC between Beholder's shims and the core engine.

## Key Files
- `frame_capture.fbs` — defines `FrameCapture` (top-level capture payload), `DrawCallCapture` (per-draw metadata), `Handshake` (shim registration), and `ControlCommand` (engine directives)

## Usage
Run `flatc --cpp frame_capture.fbs` to regenerate the C++ headers used in `src/core/ipc/` and the shim clients. Generated headers are not checked in.

## See Also
- `src/shims/gl/README.md` — producer of `FrameCapture` messages
- `src/core/README.md` — consumer of these messages
