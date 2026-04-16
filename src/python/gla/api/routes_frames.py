"""Frame overview and framebuffer endpoints."""
import base64
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["frames"])


def _overview_to_dict(overview) -> Dict[str, Any]:
    """Convert a FrameOverview object (or mock) to a JSON-serialisable dict."""
    return {
        "frame_id": overview.frame_id,
        "draw_call_count": overview.draw_call_count,
        "framebuffer_width": overview.fb_width,
        "framebuffer_height": overview.fb_height,
        "timestamp": overview.timestamp,
    }


@router.get("/frames/current/overview")
def get_current_frame_overview(request: Request) -> Dict[str, Any]:
    """Return an overview of the most recently captured frame."""
    qe = request.app.state.query_engine
    overview = qe.latest_frame_overview()
    if overview is None:
        raise HTTPException(status_code=404, detail="No frame captured yet")
    return _overview_to_dict(overview)


@router.get("/frames/{frame_id}/overview")
def get_frame_overview(frame_id: int, request: Request) -> Dict[str, Any]:
    """Return an overview for the specified frame."""
    qe = request.app.state.query_engine
    overview = qe.frame_overview(frame_id)
    if overview is None:
        raise HTTPException(status_code=404, detail=f"Frame {frame_id} not found")
    return _overview_to_dict(overview)


@router.get("/frames/{frame_id}/framebuffer")
def get_framebuffer(frame_id: int, request: Request) -> Dict[str, Any]:
    """Return the colour buffer for a frame as base64-encoded raw RGBA bytes."""
    raise HTTPException(status_code=501, detail="Framebuffer readback not yet implemented")


@router.get("/frames/{frame_id}/framebuffer/depth")
def get_framebuffer_depth(frame_id: int, request: Request) -> Dict[str, Any]:
    """Return the depth buffer for a frame as base64-encoded raw float32 bytes."""
    raise HTTPException(status_code=501, detail="Framebuffer depth readback not yet implemented")
