"""Debug group tree builder.

Reconstructs a hierarchical tree of debug groups from per-draw-call
``debug_groups`` lists (preferred) or legacy ``debug_group_path`` strings
(``"GBuffer/Player Mesh"``).

The list form preserves names that contain ``/`` literally (per spec OQ1
in ``2026-04-27-bidirectional-narrow-queries-design.md``); the string form
is retained as a back-compat fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class DebugGroupNode:
    name: str
    children: List['DebugGroupNode'] = field(default_factory=list)
    draw_call_ids: List[int] = field(default_factory=list)


def _draw_call_groups(dc) -> List[str]:
    """Return the list of debug-group names for one draw call.

    Prefers the ``debug_groups`` list field; falls back to splitting the
    legacy ``debug_group_path`` string on ``/``. Returns ``[]`` for draws
    with no group context.
    """
    if isinstance(dc, dict):
        groups = dc.get('debug_groups')
        if groups is None:
            path = dc.get('debug_group_path', '')
            return path.split('/') if path else []
        return list(groups) if groups else []
    groups = getattr(dc, 'debug_groups', None)
    if groups is None:
        path = getattr(dc, 'debug_group_path', '')
        return path.split('/') if path else []
    return list(groups) if groups else []


def build_debug_group_tree(draw_calls) -> DebugGroupNode:
    """Build a tree from draw calls with debug_groups lists (or paths).

    Each draw call has debug_groups like ``["GBuffer", "Player Mesh"]``.
    Returns root DebugGroupNode with hierarchy.

    draw_calls: list of objects/dicts exposing ``id`` and either
    ``debug_groups`` (preferred) or ``debug_group_path`` (legacy).
    """
    root = DebugGroupNode(name="Frame")
    for dc in draw_calls:
        # Support both objects and dicts
        dc_id = dc.id if hasattr(dc, 'id') else dc.get('id', 0)
        parts = _draw_call_groups(dc)

        if not parts:
            root.draw_call_ids.append(dc_id)
            continue

        node = root
        for part in parts:
            child = next((c for c in node.children if c.name == part), None)
            if not child:
                child = DebugGroupNode(name=part)
                node.children.append(child)
            node = child
        node.draw_call_ids.append(dc_id)
    return root
