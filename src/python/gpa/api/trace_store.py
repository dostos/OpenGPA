"""Per-(frame, drawcall) trace-source store for ``gpa trace`` (Phase 1).

Browser shims POST a ``sources`` payload — a map of value-hash →
[{path, type, confidence, ...}] — for each draw call where reflection
scanning ran. This store keeps the payloads in memory keyed first by
``frame_id`` (with LRU eviction) then by ``dc_id``.

The store is intentionally dumb: no schema enforcement, no hash
canonicalization. Callers (the JS scanner) are responsible for that.
Design mirrors :class:`gpa.api.annotations_store.AnnotationsStore`.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Dict, List, Optional


class TraceStore:
    """Thread-safe LRU-per-frame store of trace-source payloads.

    Structure::

        frame_id -> {dc_id: sources_dict, ...}

    where ``sources_dict`` is the payload supplied by the browser shim
    (expected to contain a ``value_index`` mapping but not enforced).
    """

    def __init__(self, capacity: int = 120) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._data: "OrderedDict[int, Dict[int, Dict[str, Any]]]" = OrderedDict()
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def put(self, frame_id: int, dc_id: int, sources: Dict[str, Any]) -> None:
        """Store (or overwrite) sources for *(frame_id, dc_id)*."""
        with self._lock:
            if frame_id in self._data:
                # Existing frame — update drawcall entry and mark MRU.
                self._data.move_to_end(frame_id)
                self._data[frame_id][dc_id] = sources
                return
            self._data[frame_id] = {dc_id: sources}
            if len(self._data) > self._capacity:
                self._data.popitem(last=False)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def get(self, frame_id: int, dc_id: int) -> Optional[Dict[str, Any]]:
        """Return stored sources for *(frame_id, dc_id)* or *None*."""
        with self._lock:
            frame = self._data.get(frame_id)
            if frame is None:
                return None
            self._data.move_to_end(frame_id)
            entry = frame.get(dc_id)
            if entry is None:
                return None
            # Return a shallow copy so mutation by callers is harmless.
            return dict(entry)

    def get_frame(self, frame_id: int) -> List[Dict[str, Any]]:
        """Return all stored sources for *frame_id* as a list.

        Each item is ``{"dc_id": int, "sources": dict}``. Empty list
        when the frame is unknown.
        """
        with self._lock:
            frame = self._data.get(frame_id)
            if frame is None:
                return []
            self._data.move_to_end(frame_id)
            return [
                {"dc_id": dc_id, "sources": dict(src)}
                for dc_id, src in sorted(frame.items())
            ]

    def find_value(self, frame_id: int, value_hash: str) -> List[Dict[str, Any]]:
        """Return every path across every drawcall in *frame_id* whose
        ``value_index`` contains *value_hash*.

        Each result item is the path entry (``{"path": ..., "type":
        ..., "confidence": ...}``) enriched with the owning ``dc_id``.
        """
        results: List[Dict[str, Any]] = []
        with self._lock:
            frame = self._data.get(frame_id)
            if frame is None:
                return results
            self._data.move_to_end(frame_id)
            for dc_id, src in frame.items():
                idx = src.get("value_index") if isinstance(src, dict) else None
                if not isinstance(idx, dict):
                    continue
                paths = idx.get(value_hash)
                if not isinstance(paths, list):
                    continue
                for p in paths:
                    if not isinstance(p, dict):
                        continue
                    enriched = dict(p)
                    enriched["dc_id"] = dc_id
                    results.append(enriched)
        return results

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    def __len__(self) -> int:  # pragma: no cover - trivial
        with self._lock:
            return len(self._data)

    def __contains__(self, frame_id: int) -> bool:
        with self._lock:
            return frame_id in self._data
