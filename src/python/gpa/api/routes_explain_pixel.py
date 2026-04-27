"""``GET /api/v1/frames/{frame_id}/explain-pixel`` endpoint.

Productionises the pixel→draw_call→scene_node chain. Uses an approximate
bounding-box hit-test: each draw call is treated as covering its viewport
(or scissor) rectangle, and the topmost matching draw at (x,y) wins.
The response includes ``"resolved": "approximate"`` so callers know a
precise draw-call-ID framebuffer is the future upgrade path (spec OQ4a).

Read-only. Returns ``safe_json_response()``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Request

from gpa.api.app import resolve_frame_id, safe_json_response
from gpa.api.routes_explain_draw import _sanitize, _scene_node_path, _shape_uniforms

router = APIRouter(tags=["explain-pixel"])


def _draw_covers(dc, x: int, y: int) -> bool:
    """Return True iff the draw's viewport (clipped by scissor when on)
    contains the pixel (x,y).

    This is the cheapest possible hit-test that beats "no answer at all"
    while we wait for ID-buffer instrumentation. False positives are
    expected for overlapping geometry; the topmost-wins rule below
    keeps the answer well-defined.
    """
    ps = dc.pipeline_state or {}
    vp_x = int(ps.get("viewport_x", 0) or 0)
    vp_y = int(ps.get("viewport_y", 0) or 0)
    vp_w = int(ps.get("viewport_w", 0) or 0)
    vp_h = int(ps.get("viewport_h", 0) or 0)
    if vp_w <= 0 or vp_h <= 0:
        return False
    if not (vp_x <= x < vp_x + vp_w and vp_y <= y < vp_y + vp_h):
        return False
    if ps.get("scissor_enabled"):
        sx = int(ps.get("scissor_x", 0) or 0)
        sy = int(ps.get("scissor_y", 0) or 0)
        sw = int(ps.get("scissor_w", 0) or 0)
        sh = int(ps.get("scissor_h", 0) or 0)
        if sw <= 0 or sh <= 0:
            return False
        if not (sx <= x < sx + sw and sy <= y < sy + sh):
            return False
    return True


def _explain_pixel(
    provider, annotation: Dict[str, Any], frame_id: int, x: int, y: int
) -> Dict[str, Any]:
    overview = provider.get_frame_overview(frame_id)
    if overview is None:
        raise KeyError(f"frame {frame_id} not found")
    fb_w = int(getattr(overview, "fb_width", 0) or 0)
    fb_h = int(getattr(overview, "fb_height", 0) or 0)
    if fb_w > 0 and fb_h > 0:
        if not (0 <= x < fb_w and 0 <= y < fb_h):
            raise ValueError(
                f"pixel ({x},{y}) outside viewport ({fb_w}x{fb_h})"
            )

    pixel = provider.get_pixel(frame_id, x, y)
    pixel_view: Optional[Dict[str, Any]] = None
    if pixel is not None:
        pixel_view = {
            "r": pixel.r, "g": pixel.g, "b": pixel.b, "a": pixel.a,
            "depth": pixel.depth,
        }

    drawcalls = provider.list_draw_calls(frame_id, limit=1000, offset=0)
    # Topmost wins: highest draw_id whose bounds cover (x,y).
    chosen = None
    for dc in drawcalls:
        if _draw_covers(dc, x, y):
            if chosen is None or int(dc.id) > int(chosen.id):
                chosen = dc

    if chosen is None:
        return {
            "frame_id": frame_id,
            "pixel": [x, y],
            "pixel_value": pixel_view,
            "draw_call_id": None,
            "scene_node_path": None,
            "material_name": None,
            "shader_program_id": None,
            "inputs": {"uniforms": [], "textures": []},
            "relevant_state": {},
            "resolved": "miss",
        }

    scene_path = _scene_node_path(chosen)
    node = None
    if annotation and scene_path:
        # Reuse the harvest helper from scene-find for symmetry.
        from gpa.api.routes_scene_find import _harvest_scene
        for cand in _harvest_scene(annotation):
            if cand.get("path") == scene_path:
                node = cand
                break
    material_name = None
    if node and isinstance(node.get("material"), dict):
        material_name = (
            node["material"].get("name") or node["material"].get("type")
        )

    uniforms_block = _shape_uniforms(getattr(chosen, "params", []) or [], cap=3)
    textures_block: List[Dict[str, Any]] = []
    for t in (chosen.textures or [])[:3]:
        textures_block.append({
            "unit": t.get("slot"),
            "tex_id": t.get("texture_id"),
            "format": t.get("format"),
        })

    ps = chosen.pipeline_state or {}
    relevant_state = {
        "GL_DEPTH_TEST": int(bool(ps.get("depth_test_enabled"))),
        "GL_BLEND":      int(bool(ps.get("blend_enabled"))),
        "GL_CULL_FACE":  int(bool(ps.get("cull_enabled"))),
    }

    return {
        "frame_id": frame_id,
        "pixel": [x, y],
        "pixel_value": pixel_view,
        "draw_call_id": int(chosen.id),
        "scene_node_path": scene_path,
        "material_name": material_name,
        "shader_program_id": getattr(chosen, "shader_id", 0) or 0,
        "inputs": {
            "uniforms": uniforms_block.get("items", []),
            "textures": textures_block,
        },
        "relevant_state": relevant_state,
        "resolved": "approximate",
    }


@router.get("/frames/{frame_id}/explain-pixel")
def get_explain_pixel(
    frame_id: Union[int, str],
    request: Request,
    x: int = -1,
    y: int = -1,
):
    if x < 0 or y < 0:
        raise HTTPException(
            status_code=400,
            detail="explain-pixel requires non-negative x and y",
        )

    provider = request.app.state.provider
    annotations_store = request.app.state.annotations
    frame_id = resolve_frame_id(frame_id, provider)
    annotation = annotations_store.get(frame_id) if annotations_store else {}

    try:
        payload = _explain_pixel(provider, annotation, frame_id, x, y)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'"))
    return safe_json_response(_sanitize(payload))
