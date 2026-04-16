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
        "framebuffer_width": overview.framebuffer_width,
        "framebuffer_height": overview.framebuffer_height,
        "timestamp": overview.timestamp,
    }


@router.get("/frames/current/overview")
def get_current_frame_overview(request: Request) -> Dict[str, Any]:
    """Return an overview of the most recently captured frame."""
    qe = request.app.state.query_engine
    overview = qe.get_current_frame_overview()
    if overview is None:
        raise HTTPException(status_code=404, detail="No frame captured yet")
    return _overview_to_dict(overview)


@router.get("/frames/{frame_id}/overview")
def get_frame_overview(frame_id: int, request: Request) -> Dict[str, Any]:
    """Return an overview for the specified frame."""
    qe = request.app.state.query_engine
    overview = qe.get_frame_overview(frame_id)
    if overview is None:
        raise HTTPException(status_code=404, detail=f"Frame {frame_id} not found")
    return _overview_to_dict(overview)


@router.get("/frames/{frame_id}/framebuffer")
def get_framebuffer(frame_id: int, request: Request) -> Dict[str, Any]:
    """Return the colour buffer for a frame as base64-encoded raw RGBA bytes."""
    qe = request.app.state.query_engine
    result = qe.get_framebuffer(frame_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Frame {frame_id} not found")
    # result is expected to expose: width, height, rgba_bytes (bytes or bytearray)
    encoded = base64.b64encode(bytes(result.rgba_bytes)).decode("ascii")
    return {
        "frame_id": frame_id,
        "width": result.width,
        "height": result.height,
        "format": "RGBA8",
        "encoding": "base64",
        "image": encoded,
    }


@router.get("/frames/{frame_id}/framebuffer/depth")
def get_framebuffer_depth(frame_id: int, request: Request) -> Dict[str, Any]:
    """Return the depth buffer for a frame as base64-encoded raw float32 bytes."""
    qe = request.app.state.query_engine
    result = qe.get_framebuffer_depth(frame_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Frame {frame_id} not found")
    # result is expected to expose: width, height, depth_bytes (bytes or bytearray)
    encoded = base64.b64encode(bytes(result.depth_bytes)).decode("ascii")
    return {
        "frame_id": frame_id,
        "width": result.width,
        "height": result.height,
        "format": "DEPTH32F",
        "encoding": "base64",
        "image": encoded,
    }
