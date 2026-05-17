# WebGL Shim

WebGL capture shim for Beholder. Monkey-patches `WebGLRenderingContext` and `WebGL2RenderingContext` methods inside the browser, then relays captured data to the core engine via a Node.js bridge.

## Subdirectories
- `extension/` — Chrome extension that injects the monkey-patch into page contexts
- `bridge/` — Node.js process that relays WebSocket messages from the extension to the engine's Unix socket

## See Also
- `src/core/README.md` — engine that receives relayed captures
- `src/shims/gl/README.md` — native GL counterpart
