"""Draw call list and detail endpoints."""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["drawcalls"])


def _shader_param_to_dict(param) -> Dict[str, Any]:
    return {
        "name": param.name,
        "type": param.type,
        "data": param.data,
    }


def _texture_binding_to_dict(tex) -> Dict[str, Any]:
    return {
        "slot": tex.slot,
        "texture_id": tex.texture_id,
        "width": tex.width,
        "height": tex.height,
        "format": tex.format,
    }


def _pipeline_state_to_dict(ps) -> Dict[str, Any]:
    viewport = ps.viewport
    scissor = ps.scissor
    return {
        "viewport_x": viewport[0],
        "viewport_y": viewport[1],
        "viewport_w": viewport[2],
        "viewport_h": viewport[3],
        "scissor_enabled": ps.scissor_enabled,
        "scissor_x": scissor[0],
        "scissor_y": scissor[1],
        "scissor_w": scissor[2],
        "scissor_h": scissor[3],
        "blend_enabled": ps.blend_enabled,
        "blend_src": ps.blend_src,
        "blend_dst": ps.blend_dst,
        "depth_test_enabled": ps.depth_test,
        "depth_write_enabled": ps.depth_write,
        "depth_func": ps.depth_func,
        "cull_enabled": ps.cull_enabled,
        "cull_mode": ps.cull_mode,
        "front_face": ps.front_face,
    }


def _drawcall_summary(dc) -> Dict[str, Any]:
    """Minimal summary suitable for a list item."""
    return {
        "id": dc.id,
        "primitive_type": dc.primitive_type,
        "vertex_count": dc.vertex_count,
        "instance_count": dc.instance_count,
        "shader_id": dc.shader_id,
    }


def _drawcall_detail(dc) -> Dict[str, Any]:
    """Full detail for a single draw call."""
    result = _drawcall_summary(dc)
    result.update(
        {
            "index_count": dc.index_count,
            "pipeline_state": _pipeline_state_to_dict(dc.pipeline),
        }
    )
    return result


@router.get("/frames/{frame_id}/drawcalls")
def list_drawcalls(
    frame_id: int,
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """Return a paginated list of draw calls for a frame."""
    qe = request.app.state.query_engine
    # Verify frame exists by checking its overview first
    overview = qe.frame_overview(frame_id)
    if overview is None:
        raise HTTPException(status_code=404, detail=f"Frame {frame_id} not found")
    drawcalls = qe.list_draw_calls(frame_id, limit, offset)
    total = overview.draw_call_count
    return {
        "frame_id": frame_id,
        "offset": offset,
        "limit": limit,
        "total": total,
        "items": [_drawcall_summary(dc) for dc in drawcalls],
    }


@router.get("/frames/{frame_id}/drawcalls/{dc_id}")
def get_drawcall(frame_id: int, dc_id: int, request: Request) -> Dict[str, Any]:
    """Return full details for a single draw call."""
    qe = request.app.state.query_engine
    dc = qe.get_draw_call(frame_id, dc_id)
    if dc is None:
        raise HTTPException(
            status_code=404, detail=f"Draw call {dc_id} in frame {frame_id} not found"
        )
    return _drawcall_detail(dc)


@router.get("/frames/{frame_id}/drawcalls/{dc_id}/shader")
def get_drawcall_shader(
    frame_id: int, dc_id: int, request: Request
) -> Dict[str, Any]:
    """Return shader program info and uniform parameters for a draw call."""
    qe = request.app.state.query_engine
    dc = qe.get_draw_call(frame_id, dc_id)
    if dc is None:
        raise HTTPException(
            status_code=404, detail=f"Draw call {dc_id} in frame {frame_id} not found"
        )
    params = dc.params or []
    return {
        "frame_id": frame_id,
        "dc_id": dc_id,
        "shader_id": dc.shader_id,
        "parameters": [_shader_param_to_dict(p) for p in params],
    }


@router.get("/frames/{frame_id}/drawcalls/{dc_id}/textures")
def get_drawcall_textures(
    frame_id: int, dc_id: int, request: Request
) -> Dict[str, Any]:
    """Return bound texture units for a draw call."""
    qe = request.app.state.query_engine
    dc = qe.get_draw_call(frame_id, dc_id)
    if dc is None:
        raise HTTPException(
            status_code=404, detail=f"Draw call {dc_id} in frame {frame_id} not found"
        )
    textures = dc.textures or []
    return {
        "frame_id": frame_id,
        "dc_id": dc_id,
        "textures": [_texture_binding_to_dict(t) for t in textures],
    }


@router.get("/frames/{frame_id}/drawcalls/{dc_id}/vertices")
def get_drawcall_vertices(
    frame_id: int, dc_id: int, request: Request
) -> Dict[str, Any]:
    """Return vertex buffer info and attribute layout for a draw call."""
    qe = request.app.state.query_engine
    dc = qe.get_draw_call(frame_id, dc_id)
    if dc is None:
        raise HTTPException(
            status_code=404, detail=f"Draw call {dc_id} in frame {frame_id} not found"
        )
    return {
        "frame_id": frame_id,
        "dc_id": dc_id,
        "vertex_count": dc.vertex_count,
        "index_count": dc.index_count,
        "primitive_type": dc.primitive_type,
    }
