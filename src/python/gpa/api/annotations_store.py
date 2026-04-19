"""Per-frame free-form annotations store (minimal Tier-3 precursor).

A thread-safe LRU dictionary keyed by frame_id that holds arbitrary JSON
payloads posted by framework plugins during capture. There is no schema —
callers store whatever they want, and queriers read it back as-is.

This is intentionally tiny: the full Tier-3 framework integration plan
(`docs/superpowers/plans/2026-04-18-framework-integration.md`) adds a
structured scene-graph with correlation to GL draw calls. This store is the
precursor so plugins have somewhere to write while that larger design is
in flight.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Dict


class AnnotationsStore:
    """Thread-safe LRU-capped dict-per-frame store.

    Args:
        capacity: Maximum number of distinct frame_ids to retain. On
            overflow the least-recently-touched entry is evicted.
    """

    def __init__(self, capacity: int = 120) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._data: "OrderedDict[int, Dict[str, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    def put(self, frame_id: int, data: Dict[str, Any]) -> None:
        """Store (or overwrite) the annotation payload for *frame_id*."""
        with self._lock:
            if frame_id in self._data:
                # Overwrite + mark most-recently-used.
                self._data.move_to_end(frame_id)
                self._data[frame_id] = data
                return
            self._data[frame_id] = data
            if len(self._data) > self._capacity:
                # popitem(last=False) = evict oldest (FIFO/LRU head)
                self._data.popitem(last=False)

    def get(self, frame_id: int) -> Dict[str, Any]:
        """Return the payload for *frame_id*, or ``{}`` if none was stored."""
        with self._lock:
            value = self._data.get(frame_id)
            if value is None:
                return {}
            # Mark as recently used on read so hot frames survive eviction.
            self._data.move_to_end(frame_id)
            # Return a shallow copy so callers can't mutate the stored dict.
            return dict(value)

    def __len__(self) -> int:  # pragma: no cover - trivial
        with self._lock:
            return len(self._data)

    def __contains__(self, frame_id: int) -> bool:
        with self._lock:
            return frame_id in self._data
