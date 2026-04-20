"""Unit tests for TraceStore (per-(frame, dc) reflection-scan sources)."""
import threading

import pytest

from gpa.api.trace_store import TraceStore


def _sources(path: str, vhash: str = "h1", value_type: str = "number"):
    return {
        "roots": ["THREE"],
        "mode": "gated",
        "value_index": {
            vhash: [{"path": path, "type": value_type, "confidence": "high"}],
        },
        "truncated": False,
        "scan_ms": 0.5,
    }


def test_put_and_get_roundtrip():
    store = TraceStore()
    src = _sources("map._transform._maxZoom")
    store.put(1, 3, src)
    assert store.get(1, 3) == src


def test_get_missing_frame_returns_none():
    store = TraceStore()
    assert store.get(999, 0) is None


def test_get_missing_dc_returns_none():
    store = TraceStore()
    store.put(1, 0, _sources("a"))
    assert store.get(1, 99) is None


def test_get_returns_copy_not_reference():
    store = TraceStore()
    store.put(1, 0, _sources("a"))
    out = store.get(1, 0)
    out["mutated"] = True
    assert "mutated" not in store.get(1, 0)


def test_overwrite_same_drawcall():
    store = TraceStore()
    store.put(1, 0, _sources("a", vhash="h1"))
    store.put(1, 0, _sources("b", vhash="h2"))
    got = store.get(1, 0)
    assert "h2" in got["value_index"]
    assert "h1" not in got["value_index"]


def test_multiple_dcs_per_frame():
    store = TraceStore()
    store.put(1, 0, _sources("a"))
    store.put(1, 1, _sources("b"))
    store.put(1, 2, _sources("c"))
    assert store.get(1, 0)["value_index"]["h1"][0]["path"] == "a"
    assert store.get(1, 1)["value_index"]["h1"][0]["path"] == "b"
    assert store.get(1, 2)["value_index"]["h1"][0]["path"] == "c"


def test_get_frame_lists_all_dcs_sorted():
    store = TraceStore()
    store.put(5, 2, _sources("c"))
    store.put(5, 0, _sources("a"))
    store.put(5, 1, _sources("b"))
    out = store.get_frame(5)
    assert [e["dc_id"] for e in out] == [0, 1, 2]
    assert out[0]["sources"]["value_index"]["h1"][0]["path"] == "a"


def test_get_frame_missing_returns_empty_list():
    store = TraceStore()
    assert store.get_frame(42) == []


def test_find_value_returns_matches_with_dc_id():
    store = TraceStore()
    # Same hash appears in dc 0 and dc 2 under different paths.
    store.put(1, 0, _sources("map._transform._maxZoom", vhash="zhash"))
    store.put(1, 1, _sources("other.value", vhash="otherhash"))
    store.put(1, 2, _sources("sourceCache.maxzoom", vhash="zhash"))
    hits = store.find_value(1, "zhash")
    assert len(hits) == 2
    got_paths = {(h["dc_id"], h["path"]) for h in hits}
    assert got_paths == {
        (0, "map._transform._maxZoom"),
        (2, "sourceCache.maxzoom"),
    }
    # Every hit must carry the enriched dc_id plus the original path metadata.
    for h in hits:
        assert h["type"] == "number"
        assert h["confidence"] == "high"


def test_find_value_unknown_hash():
    store = TraceStore()
    store.put(1, 0, _sources("a"))
    assert store.find_value(1, "nope") == []


def test_find_value_unknown_frame():
    store = TraceStore()
    assert store.find_value(999, "h1") == []


def test_find_value_tolerates_malformed_payload():
    store = TraceStore()
    # Missing value_index entirely.
    store.put(1, 0, {"roots": ["x"]})
    # Non-list hash value.
    store.put(1, 1, {"value_index": {"h1": "not-a-list"}})
    # Non-dict path entry.
    store.put(1, 2, {"value_index": {"h1": ["just-a-string"]}})
    assert store.find_value(1, "h1") == []


def test_lru_eviction_at_capacity():
    store = TraceStore(capacity=3)
    for fid in range(3):
        store.put(fid, 0, _sources(f"frame{fid}"))
    assert len(store) == 3
    # Adding frame 3 evicts frame 0.
    store.put(3, 0, _sources("frame3"))
    assert 0 not in store
    assert store.get(0, 0) is None
    assert store.get(3, 0) is not None


def test_lru_eviction_at_120_default():
    """Explicit check that default capacity is 120 and eviction kicks in."""
    store = TraceStore()  # default cap 120
    assert store.capacity == 120
    for fid in range(120):
        store.put(fid, 0, _sources(f"f{fid}"))
    assert len(store) == 120
    # 121st push evicts the oldest frame.
    store.put(120, 0, _sources("f120"))
    assert len(store) == 120
    assert 0 not in store
    assert 120 in store


def test_overwrite_does_not_evict():
    store = TraceStore(capacity=2)
    store.put(1, 0, _sources("a"))
    store.put(2, 0, _sources("b"))
    # Adding a new dc to an existing frame must NOT grow the frame count.
    store.put(1, 1, _sources("a2"))
    assert len(store) == 2
    assert store.get(1, 0) is not None
    assert store.get(1, 1) is not None


def test_get_marks_frame_recently_used():
    store = TraceStore(capacity=3)
    store.put(1, 0, _sources("a"))
    store.put(2, 0, _sources("b"))
    store.put(3, 0, _sources("c"))
    # Touch frame 1 → now MRU.
    store.get(1, 0)
    store.put(4, 0, _sources("d"))
    # Frame 2 should now be evicted (oldest untouched).
    assert 2 not in store
    assert 1 in store


def test_invalid_capacity():
    with pytest.raises(ValueError):
        TraceStore(capacity=0)
    with pytest.raises(ValueError):
        TraceStore(capacity=-5)


def test_thread_safety_smoke():
    store = TraceStore(capacity=500)

    def worker(start: int) -> None:
        for i in range(start, start + 100):
            store.put(i, 0, _sources(f"p{i}"))
            store.get(i, 0)

    threads = [threading.Thread(target=worker, args=(n * 100,)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(store) == 500
