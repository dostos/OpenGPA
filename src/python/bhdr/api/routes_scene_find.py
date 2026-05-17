"""``GET /api/v1/frames/{frame_id}/scene/find`` endpoint.

Predicate-driven scene-graph search. Read-only. Returns nodes whose
annotation matches every supplied predicate (CSV-AND form), each
annotated with the draw-call IDs whose ``debug_groups`` resolve to the
node.

Predicates implemented:
  - ``material:transparent`` / ``material:opaque``
  - ``material-name:<substr>`` (case-insensitive substring match)
  - ``name-contains:<substr>`` (case-insensitive substring match)
  - ``type:<exact>`` (exact match on ``obj.type``)
  - ``uniform-has-nan`` (any decoded uniform on a linked draw has NaN/Inf)
  - ``texture:missing`` (node references a tex id absent from any draw)

The companion CLI lives in ``src/python/bhdr/cli/commands/scene_find.py``.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import APIRouter, HTTPException, Query, Request

from bhdr.api.app import resolve_frame_id, safe_json_response

router = APIRouter(tags=["scene-find"])


KNOWN_PREDICATES = (
    "material:transparent",
    "material:opaque",
    "material-name:<substr>",
    "name-contains:<substr>",
    "type:<exact>",
    "uniform-has-nan",
    "texture:missing",
)


# ---------------------------------------------------------------------------
# Predicate parser
# ---------------------------------------------------------------------------


class PredicateError(ValueError):
    """Raised when a predicate string is not recognised."""


def parse_predicates(raw: List[str]) -> List[Tuple[str, Optional[str]]]:
    """Flatten and parse a list of CSV-AND predicate strings.

    Returns ``[(name, arg_or_None), ...]``. ``name`` is the canonical key
    (``material:transparent``, ``material-name``, etc.) and ``arg`` is the
    parameter value when the predicate takes one (``material-name``,
    ``name-contains``, ``type``).
    """
    parsed: List[Tuple[str, Optional[str]]] = []
    for entry in raw or []:
        for piece in entry.split(","):
            piece = piece.strip()
            if not piece:
                continue
            if piece in ("material:transparent", "material:opaque",
                        "uniform-has-nan", "texture:missing"):
                parsed.append((piece, None))
                continue
            for prefix in ("material-name:", "name-contains:", "type:"):
                if piece.startswith(prefix):
                    parsed.append((prefix.rstrip(":"), piece[len(prefix):]))
                    break
            else:
                raise PredicateError(
                    f"unknown predicate {piece!r}. Known: "
                    + ", ".join(KNOWN_PREDICATES)
                )
    return parsed


# ---------------------------------------------------------------------------
# Scene-graph harvesting
# ---------------------------------------------------------------------------


def _harvest_scene(annotation: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the flat list of scene-graph nodes from an annotation payload.

    The plugin namespace convention is ``annotations[plugin_name].scene``
    but a top-level ``scene`` key is also accepted (for plugins that POST
    directly without namespacing). Multiple plugins' scenes are
    concatenated.
    """
    if not isinstance(annotation, dict):
        return []
    scenes: List[List[Dict[str, Any]]] = []
    for value in annotation.values():
        if isinstance(value, dict) and isinstance(value.get("scene"), list):
            scenes.append(value["scene"])
    if isinstance(annotation.get("scene"), list):
        scenes.append(annotation["scene"])
    out: List[Dict[str, Any]] = []
    for scene in scenes:
        for node in scene:
            if isinstance(node, dict):
                out.append(node)
    return out


def _node_path(node: Dict[str, Any]) -> str:
    return str(node.get("path") or node.get("name") or "")


def _build_path_to_drawcalls(drawcalls) -> Dict[str, List[int]]:
    """Map a debug-group join-path to the list of draw-call IDs under it.

    The mapping uses ``"/".join(debug_groups)`` as the key, which matches
    the human path written by ``serializeNode`` in the three.js plugin.
    Draw calls without any debug-group context are not indexed.
    """
    out: Dict[str, List[int]] = {}
    for dc in drawcalls or []:
        groups = list(getattr(dc, "debug_groups", []) or [])
        if not groups:
            continue
        path = "/".join(groups)
        out.setdefault(path, []).append(int(dc.id))
    return out


def _has_nan(params: List[Dict[str, Any]]) -> bool:
    for p in params or []:
        if "value" not in p:
            continue
        for comp in _flatten(p["value"]):
            if isinstance(comp, float) and (math.isnan(comp) or math.isinf(comp)):
                return True
    return False


def _flatten(value):
    if isinstance(value, (list, tuple)):
        out = []
        for v in value:
            out.extend(_flatten(v) if isinstance(v, (list, tuple)) else [v])
        return out
    return [value]


# ---------------------------------------------------------------------------
# Predicate evaluation
# ---------------------------------------------------------------------------


def _matches_predicate(
    node: Dict[str, Any],
    pred: Tuple[str, Optional[str]],
    *,
    drawcalls_for_node: List,
    all_texture_ids: set,
) -> bool:
    name, arg = pred

    if name == "material:transparent":
        m = node.get("material") or {}
        return bool(m.get("transparent"))
    if name == "material:opaque":
        m = node.get("material") or {}
        # "opaque" = explicitly transparent==false, or material present with
        # no transparent flag at all (three.js default).
        if not isinstance(m, dict):
            return False
        return not bool(m.get("transparent"))
    if name == "material-name":
        m = node.get("material") or {}
        if not isinstance(m, dict) or arg is None:
            return False
        mname = str(m.get("name") or m.get("type") or "")
        return arg.lower() in mname.lower()
    if name == "name-contains":
        if arg is None:
            return False
        candidate = str(node.get("name") or _node_path(node) or "")
        return arg.lower() in candidate.lower()
    if name == "type":
        if arg is None:
            return False
        return str(node.get("type") or "") == arg
    if name == "uniform-has-nan":
        for dc in drawcalls_for_node or []:
            if _has_nan(getattr(dc, "params", []) or []):
                return True
        return False
    if name == "texture:missing":
        m = node.get("material") or {}
        if not isinstance(m, dict):
            return False
        tex_id = m.get("map_texture_id")
        if tex_id is None:
            return False
        try:
            tex_id_int = int(tex_id)
        except (TypeError, ValueError):
            return False
        return tex_id_int not in all_texture_ids
    return False


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


def evaluate(
    provider,
    annotation: Dict[str, Any],
    frame_id: int,
    predicates: List[Tuple[str, Optional[str]]],
    limit: int,
) -> Dict[str, Any]:
    drawcalls = provider.list_draw_calls(frame_id, limit=1000, offset=0)
    path_to_dcs = _build_path_to_drawcalls(drawcalls)
    dc_by_id = {int(dc.id): dc for dc in drawcalls}
    all_tex_ids = {
        int(t["texture_id"])
        for dc in drawcalls
        for t in (dc.textures or [])
        if t.get("texture_id")
    }

    nodes = _harvest_scene(annotation)
    matches: List[Dict[str, Any]] = []
    truncated = False
    for node in nodes:
        path = _node_path(node)
        dc_ids = path_to_dcs.get(path, [])
        node_dcs = [dc_by_id[i] for i in dc_ids if i in dc_by_id]
        if all(
            _matches_predicate(
                node, p,
                drawcalls_for_node=node_dcs,
                all_texture_ids=all_tex_ids,
            )
            for p in predicates
        ):
            material = node.get("material")
            material_name = None
            if isinstance(material, dict):
                material_name = material.get("name") or material.get("type")
            matches.append({
                "path": path,
                "uuid": node.get("uuid"),
                "type": node.get("type"),
                "material_name": material_name,
                "draw_call_ids": dc_ids,
            })
            if len(matches) >= limit:
                truncated = True
                break

    return {
        "frame_id": frame_id,
        "predicate": ",".join(_pred_to_string(p) for p in predicates),
        "limit": limit,
        "match_count": len(matches),
        "matches": matches,
        "truncated": truncated,
        "annotation_present": bool(nodes),
    }


def _pred_to_string(pred: Tuple[str, Optional[str]]) -> str:
    name, arg = pred
    if arg is None:
        return name
    if name in ("material-name", "name-contains", "type"):
        return f"{name}:{arg}"
    return name


@router.get("/frames/{frame_id}/scene/find")
def get_scene_find(
    frame_id: Union[int, str],
    request: Request,
    predicate: List[str] = Query([]),
    limit: int = Query(10, ge=1, le=200),
):
    if not predicate:
        raise HTTPException(
            status_code=400,
            detail="scene/find requires at least one predicate=… query param",
        )

    try:
        parsed = parse_predicates(predicate)
    except PredicateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail="no predicates parsed from input",
        )

    provider = request.app.state.provider
    annotations_store = request.app.state.annotations
    frame_id = resolve_frame_id(frame_id, provider)
    annotation = annotations_store.get(frame_id) if annotations_store else {}
    payload = evaluate(provider, annotation, frame_id, parsed, limit)
    from bhdr.api.routes_explain_draw import _sanitize
    return safe_json_response(_sanitize(payload))


# ---------------------------------------------------------------------------
# Plugin fallback POST endpoint (manual link records).
# ---------------------------------------------------------------------------


@router.post("/frames/{frame_id}/links")
async def post_links(frame_id: Union[int, str], request: Request):
    """Accept manual link records for plugins that can't emit debug markers.

    Body forms accepted:
      - ``{"records": [{"drawcall_id":…, "scene_node_uuid":…, "scene_node_path":…, "framework":…}]}``
      - A bare list of records ``[{...}, {...}]``
      - A single record ``{...}`` (auto-wrapped into a 1-element list)

    Records are stored under ``annotations[frame_id]["links"]`` so
    ``scene-find`` and ``explain-draw`` can fall back to them when no
    debug-marker correlation is available.
    """
    provider = request.app.state.provider
    annotations_store = request.app.state.annotations
    frame_id = resolve_frame_id(frame_id, provider)

    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}")

    if isinstance(body, dict) and isinstance(body.get("records"), list):
        records = body["records"]
    elif isinstance(body, list):
        records = body
    elif isinstance(body, dict) and "drawcall_id" in body:
        records = [body]
    else:
        raise HTTPException(
            status_code=400,
            detail=(
                "links payload must be either "
                "{'records':[…]}, a JSON list, or a single record"
            ),
        )

    cleaned: List[Dict[str, Any]] = []
    for r in records:
        if not isinstance(r, dict):
            continue
        if "drawcall_id" not in r:
            continue
        cleaned.append({
            "drawcall_id": int(r.get("drawcall_id")),
            "scene_node_uuid": r.get("scene_node_uuid"),
            "scene_node_path": r.get("scene_node_path"),
            "framework": r.get("framework", "unknown"),
        })

    existing = annotations_store.get(frame_id) if annotations_store else {}
    if not isinstance(existing, dict):
        existing = {}
    existing["links"] = cleaned
    annotations_store.put(frame_id, existing)
    return safe_json_response({
        "ok": True,
        "frame_id": frame_id,
        "record_count": len(cleaned),
    })
