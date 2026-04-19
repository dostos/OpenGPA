"""Per-frame free-form annotations endpoints (minimal Tier-3 precursor).

Framework plugins (mapbox, three.js, etc.) can POST arbitrary JSON to
``/api/v1/frames/{frame_id}/annotations`` during capture, and an agent can
GET it back. There is no schema validation and no correlation to GL state
— it's a dumb dict-per-frame KV store. The full Tier-3 plan adds scene
graph + correlation on top later.
"""
from fastapi import APIRouter, HTTPException, Request

from gpa.api.app import safe_json_response

router = APIRouter(tags=["annotations"])

# 256 KB payload cap. Annotations are meant to be a sidecar blob, not a
# full scene dump — if a plugin needs more, it should stream via another
# channel or split across frames.
MAX_ANNOTATION_BYTES = 256 * 1024


@router.post("/frames/{frame_id}/annotations")
async def post_annotations(frame_id: int, request: Request):
    """Store (or overwrite) the annotation payload for *frame_id*."""
    raw = await request.body()
    if len(raw) > MAX_ANNOTATION_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Annotation payload {len(raw)} bytes exceeds "
                f"{MAX_ANNOTATION_BYTES}-byte limit"
            ),
        )
    try:
        data = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")
    if not isinstance(data, dict):
        raise HTTPException(
            status_code=400,
            detail="Annotation body must be a JSON object (dict)",
        )

    store = request.app.state.annotations
    store.put(frame_id, data)
    return safe_json_response({
        "ok": True,
        "frame_id": frame_id,
        "byte_count": len(raw),
    })


@router.get("/frames/{frame_id}/annotations")
def get_annotations(frame_id: int, request: Request):
    """Return the stored annotation dict for *frame_id*, or ``{}``.

    Never 404s — absence is indistinguishable from "plugin posted an empty
    dict", which is fine for a free-form sidecar.
    """
    store = request.app.state.annotations
    return safe_json_response(store.get(frame_id))
