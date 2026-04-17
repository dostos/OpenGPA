# GLA WebGL Shim — M6

WebGL interception via a Chromium browser extension + a Node.js WebSocket bridge.

## Architecture

```
Browser (page context)
  interceptor.js  ← monkey-patches WebGLRenderingContext / WebGL2RenderingContext
       |
       | WebSocket  ws://127.0.0.1:18081
       v
  Node.js bridge  (bridge.js)
       |
       | Unix domain socket  /tmp/gla.sock
       v
  GLA engine
```

The content script (`content.js`) injects `interceptor.js` into the page context at
`document_start` so the patches are in place before any WebGL context is created.

## Loading the Extension in Chrome

1. Open `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked**
4. Select `src/shims/webgl/extension/`

The extension patches all WebGL contexts in every tab automatically.

## Starting the Bridge

```bash
cd src/shims/webgl/bridge
npm install
npm start
```

The bridge must be running before the GLA engine (or at least before the first
WebGL frame is rendered).

## Environment Variables

| Variable          | Default          | Description                              |
|-------------------|------------------|------------------------------------------|
| `GLA_SOCKET_PATH` | `/tmp/gla.sock`  | Unix socket path to the GLA engine       |
| `GLA_WS_PORT`     | `18081`          | WebSocket port the bridge listens on     |

## Known Limitations (v1)

- **No shared memory (SHM).** The bridge sends only frame metadata (frame ID +
  draw-call count) over the Unix socket. Full pixel data would require a native
  Node.js addon (`node-addon-api`) to call `shm_open`/`mmap`. Planned for a
  future milestone.
- **No `gl.readPixels` readback per frame.** Framebuffer readback is expensive;
  it will be triggered on demand by the engine, not automatically every frame.
- **Uniform tracking is a passthrough.** Uniform setter methods are patched but
  values are not stored in shadow state in v1.
- **Single shared state object.** All WebGL contexts in a page share the same
  `state` object. Multi-canvas pages may produce interleaved draw-call lists.
  Per-context state is a future improvement.
