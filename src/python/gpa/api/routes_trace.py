"""Endpoints for ``gpa trace`` reflection-scanner sidecar (Phase 1).

The browser shim (``src/shims/webgl/extension/gpa-trace.js``) POSTs a
``sources`` payload per draw call containing a value-hash → path index.
Engine stores it; Phase 2 tooling (`gpa trace` CLI) will query it back.
"""
from fastapi import APIRouter, HTTPException, Request

from gpa.api.app import safe_json_response

router = APIRouter(tags=["trace"])

# 256 KB per drawcall payload cap — matches annotations. A full value
# index with depth-4 / 1000-object cap should be well under this.
MAX_SOURCES_BYTES = 256 * 1024


@router.post("/frames/{frame_id}/drawcalls/{dc_id}/sources")
async def post_sources(frame_id: int, dc_id: int, request: Request):
    """Store the reflection-scan sources for *(frame_id, dc_id)*."""
    raw = await request.body()
    if len(raw) > MAX_SOURCES_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Sources payload {len(raw)} bytes exceeds "
                f"{MAX_SOURCES_BYTES}-byte limit"
            ),
        )
    try:
        data = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=400,
            detail="Sources body must be a JSON object (dict)",
        )
    # The canonical wire shape is {"frame_id", "dc_id", "sources": {...}}.
    # Accept either that or a bare sources dict (keeps the shim simple).
    sources = data.get("sources") if "sources" in data else data
    if not isinstance(sources, dict):
        raise HTTPException(
            status_code=400,
            detail="'sources' field must be a JSON object",
        )

    store = request.app.state.trace_store
    store.put(frame_id, dc_id, sources)
    return safe_json_response({
        "ok": True,
        "frame_id": frame_id,
        "dc_id": dc_id,
        "byte_count": len(raw),
    })


@router.get("/frames/{frame_id}/drawcalls/{dc_id}/sources")
def get_sources(frame_id: int, dc_id: int, request: Request):
    """Return stored sources for *(frame_id, dc_id)*.

    404s when nothing was posted — distinguishes "nothing captured" from
    "empty scan" (which would be ``{"value_index": {}}``).
    """
    store = request.app.state.trace_store
    sources = store.get(frame_id, dc_id)
    if sources is None:
        raise HTTPException(
            status_code=404,
            detail=f"No sources stored for frame={frame_id} dc={dc_id}",
        )
    return safe_json_response(sources)
