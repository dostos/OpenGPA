# REST API

FastAPI application for Beholder. Exposes 22+ endpoints covering frames, draw calls, pixels, textures, and scene queries. All route handlers wrap responses in `safe_json_response()` to handle non-serializable GPU data types.

## Key Files
- `app.py` — application factory; mounts routers and configures middleware
- `routes_frames.py` — frame listing, metadata, and diff endpoints
- `routes_drawcalls.py` — per-draw-call query endpoints
- `routes_pixels.py` — pixel readback and overdraw endpoints
- `routes_scene.py` — scene-graph and bounding-box queries

## See Also
- `src/python/bhdr/mcp/README.md` — MCP server that proxies to this API
- `src/python/bhdr/backends/README.md` — backends that back these routes
