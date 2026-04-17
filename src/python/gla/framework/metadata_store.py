"""In-memory store for per-frame framework metadata.

Framework plugins POST scene graph data for a given frame ID.  The store
keeps up to *capacity* entries and evicts the oldest when full.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from .types import (
    FrameMetadata,
    FrameworkMaterial,
    FrameworkObject,
    FrameworkRenderPass,
)


class MetadataStore:
    """Bounded LRU-style store mapping frame_id → FrameMetadata."""

    def __init__(self, capacity: int = 120) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._capacity = capacity
        # OrderedDict preserves insertion order for eviction
        self._data: OrderedDict[int, FrameMetadata] = OrderedDict()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def store(self, frame_id: int, data: dict) -> None:
        """Parse *data* into a FrameMetadata and store it under *frame_id*.

        If *frame_id* already exists it is replaced.  When the store exceeds
        *capacity* the oldest entry (by insertion order) is evicted first.
        """
        metadata = self._parse(data)

        # Replace existing entry (remove so re-insert lands at the end)
        if frame_id in self._data:
            del self._data[frame_id]
        elif len(self._data) >= self._capacity:
            # Evict oldest
            self._data.popitem(last=False)

        self._data[frame_id] = metadata

    def get(self, frame_id: int) -> Optional[FrameMetadata]:
        """Return the FrameMetadata for *frame_id*, or *None* if not present."""
        return self._data.get(frame_id)

    def has(self, frame_id: int) -> bool:
        """Return True if metadata exists for *frame_id*."""
        return frame_id in self._data

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse(data: dict) -> FrameMetadata:
        """Convert a raw JSON dict into a FrameMetadata, tolerating missing fields."""
        objects = [
            FrameworkObject(
                name=obj.get("name", ""),
                type=obj.get("type", ""),
                parent=obj.get("parent", ""),
                draw_call_ids=list(obj.get("draw_call_ids", [])),
                transform=dict(obj.get("transform", {})),
                visible=bool(obj.get("visible", True)),
                properties=dict(obj.get("properties", {})),
            )
            for obj in data.get("objects", [])
        ]

        materials = [
            FrameworkMaterial(
                name=mat.get("name", ""),
                shader=mat.get("shader", ""),
                used_by=list(mat.get("used_by", [])),
                properties=dict(mat.get("properties", {})),
                textures=dict(mat.get("textures", {})),
            )
            for mat in data.get("materials", [])
        ]

        render_passes = [
            FrameworkRenderPass(
                name=rp.get("name", ""),
                draw_call_range=list(rp.get("draw_call_range", [])),
                output=rp.get("output"),
                input=list(rp.get("input", [])),
            )
            for rp in data.get("render_passes", [])
        ]

        return FrameMetadata(
            framework=data.get("framework", ""),
            version=data.get("version", ""),
            objects=objects,
            materials=materials,
            render_passes=render_passes,
        )
