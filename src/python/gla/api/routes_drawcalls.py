"""Draw call list and detail endpoints."""
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["drawcalls"])


def _shader_param_to_dict(param) -> Dict[str, Any]:
    return {
        "name": param.name,
        "type": param.type,
        "value": param.value,
    }


def _texture_binding_to_dict(tex) -> Dict[str, Any]:
    return {
        "unit": tex.unit,
        "texture_id": tex.texture_id,
        "target": tex.target,
        "width": tex.width,
        "height": tex.height,
        "internal_format": tex.internal_format,
    }


def _pipeline_state_to_dict(ps) -> Dict[str, Any]:
    return {
        "blend_enabled": ps.blend_enabled,
        "depth_test_enabled": ps.depth_test_enabled,
        "depth_write_enabled": ps.depth_write_enabled,
        "stencil_test_enabled": ps.stencil_test_enabled,
        "cull_face_enabled": ps.cull_face_enabled,
        "cull_face_mode": ps.cull_face_mode,
        "blend_src_rgb": ps.blend_src_rgb,
        "blend_dst_rgb": ps.blend_dst_rgb,
        "depth_func": ps.depth_func,
    }


def _drawcall_summary(dc) -> Dict[str, Any]:
    """Minimal summary suitable for a list item."""
    return {
        "id": dc.id,
        "draw_call_index": dc.draw_call_index,
        "primitive_type": dc.primitive_type,
        "vertex_count": dc.vertex_count,
        "instance_count": dc.instance_count,
        "program_id": dc.program_id,
    }


def _drawcall_detail(dc) -> Dict[str, Any]:
    """Full detail for a single draw call."""
    result = _drawcall_summary(dc)
    result.update(
        {
            "index_count": dc.index_count,
            "base_vertex": dc.base_vertex,
            "pipeline_state": _pipeline_state_to_dict(dc.pipeline_state),
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
    drawcalls = qe.get_drawcalls(frame_id, limit=limit, offset=offset)
    if drawcalls is None:
        raise HTTPException(status_code=404, detail=f"Frame {frame_id} not found")
    total = qe.get_drawcall_count(frame_id)
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
    dc = qe.get_drawcall(frame_id, dc_id)
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
    dc = qe.get_drawcall(frame_id, dc_id)
    if dc is None:
        raise HTTPException(
            status_code=404, detail=f"Draw call {dc_id} in frame {frame_id} not found"
        )
    shader = qe.get_shader(frame_id, dc_id)
    params = shader.parameters if shader is not None else []
    return {
        "frame_id": frame_id,
        "dc_id": dc_id,
        "program_id": dc.program_id,
        "vertex_shader_source": shader.vertex_source if shader is not None else None,
        "fragment_shader_source": shader.fragment_source if shader is not None else None,
        "parameters": [_shader_param_to_dict(p) for p in params],
    }


@router.get("/frames/{frame_id}/drawcalls/{dc_id}/textures")
def get_drawcall_textures(
    frame_id: int, dc_id: int, request: Request
) -> Dict[str, Any]:
    """Return bound texture units for a draw call."""
    qe = request.app.state.query_engine
    dc = qe.get_drawcall(frame_id, dc_id)
    if dc is None:
        raise HTTPException(
            status_code=404, detail=f"Draw call {dc_id} in frame {frame_id} not found"
        )
    textures = qe.get_textures(frame_id, dc_id)
    return {
        "frame_id": frame_id,
        "dc_id": dc_id,
        "textures": [_texture_binding_to_dict(t) for t in (textures or [])],
    }


@router.get("/frames/{frame_id}/drawcalls/{dc_id}/vertices")
def get_drawcall_vertices(
    frame_id: int, dc_id: int, request: Request
) -> Dict[str, Any]:
    """Return vertex buffer info and attribute layout for a draw call."""
    qe = request.app.state.query_engine
    dc = qe.get_drawcall(frame_id, dc_id)
    if dc is None:
        raise HTTPException(
            status_code=404, detail=f"Draw call {dc_id} in frame {frame_id} not found"
        )
    vertices = qe.get_vertices(frame_id, dc_id)
    return {
        "frame_id": frame_id,
        "dc_id": dc_id,
        "vertex_count": dc.vertex_count,
        "index_count": dc.index_count,
        "primitive_type": dc.primitive_type,
        "attributes": vertices.attributes if vertices is not None else [],
        "vao_id": vertices.vao_id if vertices is not None else None,
    }
