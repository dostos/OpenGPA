"""``GET /api/v1/frames/{frame_id}/draws/{draw_id}/explain`` endpoint.

Single-call explanation for one draw call: scene-node path (from
``debug_groups``), program/material name (best-effort from annotations),
non-default uniforms (capped), textures sampled, and the three most
relevant pipeline-state values.

Read-only. Idempotent. Returns ``safe_json_response()`` per CLAUDE.md.
"""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException, Request

from gpa.api.app import resolve_frame_id, safe_json_response

router = APIRouter(tags=["explain-draw"])


def _sanitize(obj):
    """Recursively replace NaN/Inf floats with JSON-safe strings.

    Mirrors ``routes_drawcalls._sanitize_json_floats`` but kept inline to
    avoid the cross-module import surface.
    """
    if isinstance(obj, float):
        if math.isnan(obj):
            return "NaN"
        if math.isinf(obj):
            return "Infinity" if obj > 0 else "-Infinity"
        return obj
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_sanitize(v) for v in obj)
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    return obj


# Maximum uniforms returned per draw before summarising the rest with `…`.
DEFAULT_UNIFORM_CAP = 8


def _flatten_components(value: Any) -> List[Any]:
    if isinstance(value, (list, tuple)):
        out: List[Any] = []
        for v in value:
            if isinstance(v, (list, tuple)):
                out.extend(_flatten_components(v))
            else:
                out.append(v)
        return out
    return [value]


def _is_finite(value: Any) -> bool:
    """Return True if a decoded uniform value has no NaN/Inf components."""
    for comp in _flatten_components(value):
        if isinstance(comp, float):
            if math.isnan(comp) or math.isinf(comp):
                return False
    return True


def _looks_like_default(p: Dict[str, Any]) -> bool:
    """Heuristic: treat all-zero scalar/vector uniforms as 'probably default'.

    Programs initialise uniforms to zero; identifying obvious-defaults
    lets ``explain-draw`` highlight non-zero (interesting) uniforms first
    while still surfacing zero values when nothing else is set.
    """
    val = p.get("value")
    if val is None:
        return False
    components = _flatten_components(val)
    if not components:
        return False
    return all(
        (isinstance(c, (int, float)) and c == 0) for c in components
    )


def _scene_node_path(dc) -> Optional[str]:
    """Join debug_groups with '/' for human-readable display.

    Returns None when no groups are present (no plugin / no markers).
    """
    groups = list(getattr(dc, "debug_groups", []) or [])
    if not groups:
        return None
    return "/".join(groups)


def _shape_uniforms(
    params: List[Dict[str, Any]], cap: int = DEFAULT_UNIFORM_CAP
) -> Dict[str, Any]:
    """Pick the most useful subset of decoded uniforms for ``explain-draw``.

    Strategy: prefer non-default (non-zero) uniforms first, then defaults.
    Cap at ``cap`` entries. Always set ``truncated`` so callers know there
    were more.
    """
    decoded: List[Dict[str, Any]] = []
    for p in params or []:
        if "value" not in p:
            continue
        decoded.append({
            "name": p.get("name"),
            "value": p["value"],
        })
    interesting = [u for u in decoded if not _looks_like_default(u)]
    leftover = [u for u in decoded if _looks_like_default(u)]
    ordered = interesting + leftover
    truncated = len(ordered) > cap
    shown = ordered[:cap]
    return {
        "items": shown,
        "truncated": truncated,
        "total": len(decoded),
    }


def _shape_textures(dc) -> List[Dict[str, Any]]:
    """Compact texture-binding view: unit, id, format, dims, w/h only."""
    out: List[Dict[str, Any]] = []
    for t in (dc.textures or []):
        out.append({
            "unit": t.get("slot"),
            "tex_id": t.get("texture_id"),
            "format": t.get("format"),
            "width": t.get("width"),
            "height": t.get("height"),
        })
    return out


def _relevant_state(dc) -> Dict[str, Any]:
    """Pick the three pipeline-state values that explain visual outcomes.

    Default trio: GL_DEPTH_TEST, GL_BLEND, GL_CULL_FACE. These are the
    flags whose flips most commonly cause "missing/extra/wrong" pixel
    bugs. The full pipeline_state dict is always available via
    ``/drawcalls/{id}`` for the rare edge case.
    """
    ps = dc.pipeline_state or {}
    return {
        "GL_DEPTH_TEST": int(bool(ps.get("depth_test_enabled"))),
        "GL_BLEND":      int(bool(ps.get("blend_enabled"))),
        "GL_CULL_FACE":  int(bool(ps.get("cull_enabled"))),
    }


def _annotation_node_for_path(annotation: Dict[str, Any], scene_path: Optional[str]):
    """Find the scene-graph node whose ``path`` equals ``scene_path``.

    Walks each plugin's submission. Returns the matching node dict, or
    None if no annotation contains a path-matching node.
    """
    if not annotation or not scene_path:
        return None
    for value in (annotation.values() if isinstance(annotation, dict) else []):
        if not isinstance(value, dict):
            continue
        scene = value.get("scene")
        if not isinstance(scene, list):
            continue
        for node in scene:
            if isinstance(node, dict) and node.get("path") == scene_path:
                return node
    # Top-level form: caller may have POSTed the scene directly.
    if isinstance(annotation.get("scene"), list):
        for node in annotation["scene"]:
            if isinstance(node, dict) and node.get("path") == scene_path:
                return node
    return None


def build_explanation(
    provider, annotation: Dict[str, Any], frame_id: int, draw_id: int
) -> Optional[Dict[str, Any]]:
    """Assemble the explain-draw payload, or None when ``draw_id`` is missing."""
    dc = provider.get_draw_call(frame_id, draw_id)
    if dc is None:
        return None
    scene_path = _scene_node_path(dc)
    node = _annotation_node_for_path(annotation, scene_path)
    material_name = None
    node_uuid = None
    node_type = None
    if node is not None:
        node_uuid = node.get("uuid") or node.get("name")
        node_type = node.get("type")
        material = node.get("material")
        if isinstance(material, dict):
            material_name = material.get("name") or material.get("type")

    return {
        "frame_id": frame_id,
        "draw_call_id": draw_id,
        "scene_node_path": scene_path,
        "scene_node_uuid": node_uuid,
        "scene_node_type": node_type,
        "shader_program_id": getattr(dc, "shader_id", 0) or 0,
        "material_name": material_name,
        "uniforms_set": _shape_uniforms(getattr(dc, "params", []) or []),
        "textures_sampled": _shape_textures(dc),
        "relevant_state": _relevant_state(dc),
        "debug_groups": list(getattr(dc, "debug_groups", []) or []),
    }


@router.get("/frames/{frame_id}/draws/{draw_id}/explain")
def get_draw_explain(
    frame_id: Union[int, str],
    draw_id: int,
    request: Request,
):
    provider = request.app.state.provider
    annotations_store = request.app.state.annotations
    frame_id = resolve_frame_id(frame_id, provider)
    annotation = annotations_store.get(frame_id) if annotations_store else {}
    payload = build_explanation(provider, annotation, frame_id, draw_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Draw call {draw_id} not in frame {frame_id}",
        )
    return safe_json_response(_sanitize(payload))


# ---------------------------------------------------------------------------
# diff-draws
# ---------------------------------------------------------------------------


_VALID_SCOPES = ("state", "uniforms", "textures", "all")
_DIFF_LINE_CAP = 60


def _state_changes(a, b) -> List[Dict[str, Any]]:
    """Compute the small set of pipeline-state deltas worth showing."""
    out: List[Dict[str, Any]] = []
    psa = a.pipeline_state or {}
    psb = b.pipeline_state or {}
    for key, label in (
        ("blend_enabled",   "GL_BLEND"),
        ("depth_test_enabled", "GL_DEPTH_TEST"),
        ("depth_write_enabled", "GL_DEPTH_MASK"),
        ("depth_func",      "GL_DEPTH_FUNC"),
        ("cull_enabled",    "GL_CULL_FACE"),
        ("cull_mode",       "GL_CULL_MODE"),
        ("blend_src",       "GL_BLEND_SRC"),
        ("blend_dst",       "GL_BLEND_DST"),
        ("scissor_enabled", "GL_SCISSOR_TEST"),
        ("front_face",      "GL_FRONT_FACE"),
    ):
        va = psa.get(key)
        vb = psb.get(key)
        if va != vb:
            out.append({"key": label, "a": va, "b": vb})
    # Viewport / scissor packed: report as tuples for readability.
    vpa = (psa.get("viewport_x"), psa.get("viewport_y"),
           psa.get("viewport_w"), psa.get("viewport_h"))
    vpb = (psb.get("viewport_x"), psb.get("viewport_y"),
           psb.get("viewport_w"), psb.get("viewport_h"))
    if vpa != vpb:
        out.append({"key": "viewport", "a": list(vpa), "b": list(vpb)})
    sca = (psa.get("scissor_x"), psa.get("scissor_y"),
           psa.get("scissor_w"), psa.get("scissor_h"))
    scb = (psb.get("scissor_x"), psb.get("scissor_y"),
           psb.get("scissor_w"), psb.get("scissor_h"))
    if sca != scb:
        out.append({"key": "scissor", "a": list(sca), "b": list(scb)})
    if a.shader_id != b.shader_id:
        out.append({"key": "shader_program", "a": a.shader_id, "b": b.shader_id})
    return out


def _uniform_changes(a, b) -> List[Dict[str, Any]]:
    """Return only changed (or added/removed) decoded uniforms.

    Both draws' params are matched on ``name``. Bytes-only entries are
    ignored (no decoded value to compare).
    """
    def index(params):
        out: Dict[str, Any] = {}
        for p in params or []:
            name = p.get("name")
            if name is None:
                continue
            if "value" not in p:
                continue
            out[name] = p["value"]
        return out

    ia = index(a.params)
    ib = index(b.params)
    out: List[Dict[str, Any]] = []
    keys = set(ia) | set(ib)
    for k in sorted(keys):
        va = ia.get(k)
        vb = ib.get(k)
        if va != vb:
            out.append({"key": f"uniform:{k}", "a": va, "b": vb})
    return out


def _texture_changes(a, b) -> List[Dict[str, Any]]:
    """Return texture-binding deltas keyed by sampler unit."""
    def index(textures):
        out: Dict[int, Dict[str, Any]] = {}
        for t in textures or []:
            slot = t.get("slot")
            if slot is None:
                continue
            out[int(slot)] = {
                "tex_id": t.get("texture_id"),
                "format": t.get("format"),
            }
        return out

    ia = index(a.textures)
    ib = index(b.textures)
    out: List[Dict[str, Any]] = []
    units = set(ia) | set(ib)
    for unit in sorted(units):
        va = ia.get(unit)
        vb = ib.get(unit)
        if va != vb:
            out.append({"key": f"texture:unit{unit}", "a": va, "b": vb})
    return out


def build_diff(
    provider,
    annotation: Dict[str, Any],
    frame_id: int,
    a_id: int,
    b_id: int,
    scope: str,
) -> Dict[str, Any]:
    """Assemble the diff-draws payload.

    Raises ``KeyError`` (string) when either draw is missing in the frame.
    """
    if scope not in _VALID_SCOPES:
        raise ValueError(f"unknown scope {scope!r}")
    a = provider.get_draw_call(frame_id, a_id)
    if a is None:
        raise KeyError(f"draw {a_id} not in frame {frame_id}")
    b = provider.get_draw_call(frame_id, b_id)
    if b is None:
        raise KeyError(f"draw {b_id} not in frame {frame_id}")

    changes: List[Dict[str, Any]] = []
    if scope in ("state", "all"):
        changes.extend(_state_changes(a, b))
    if scope in ("uniforms", "all"):
        changes.extend(_uniform_changes(a, b))
    if scope in ("textures", "all"):
        changes.extend(_texture_changes(a, b))

    truncated = False
    if len(changes) > _DIFF_LINE_CAP:
        changes = changes[:_DIFF_LINE_CAP]
        truncated = True

    a_path = _scene_node_path(a)
    b_path = _scene_node_path(b)
    return {
        "frame_id": frame_id,
        "a": a_id,
        "b": b_id,
        "scope": scope,
        "a_node": a_path,
        "b_node": b_path,
        "changes": changes,
        "truncated": truncated,
    }


@router.get("/frames/{frame_id}/draws/diff")
def get_draw_diff(
    frame_id: Union[int, str],
    request: Request,
    a: Optional[int] = None,
    b: Optional[int] = None,
    scope: str = "state",
):
    if a is None or b is None:
        raise HTTPException(
            status_code=400,
            detail="diff requires query params 'a' and 'b'",
        )
    if scope not in _VALID_SCOPES:
        raise HTTPException(
            status_code=400,
            detail=f"unknown scope {scope!r}; must be one of {list(_VALID_SCOPES)}",
        )

    provider = request.app.state.provider
    annotations_store = request.app.state.annotations
    frame_id = resolve_frame_id(frame_id, provider)
    annotation = annotations_store.get(frame_id) if annotations_store else {}

    try:
        payload = build_diff(provider, annotation, frame_id, a, b, scope)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'"))
    return safe_json_response(_sanitize(payload))
