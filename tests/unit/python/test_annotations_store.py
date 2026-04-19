"""Unit tests for AnnotationsStore (thread-safe LRU dict-per-frame store)."""
import threading

import pytest

from gpa.api.annotations_store import AnnotationsStore


def test_put_and_get_roundtrip():
    store = AnnotationsStore()
    store.put(1, {"zoom": 4.5, "tile": "a/b/c"})
    assert store.get(1) == {"zoom": 4.5, "tile": "a/b/c"}


def test_get_missing_returns_empty_dict():
    store = AnnotationsStore()
    assert store.get(999) == {}


def test_get_returns_copy_not_reference():
    store = AnnotationsStore()
    store.put(1, {"k": "v"})
    out = store.get(1)
    out["mutated"] = True
    # Original store entry must be unchanged.
    assert store.get(1) == {"k": "v"}


def test_overwrite_same_frame():
    store = AnnotationsStore()
    store.put(1, {"a": 1})
    store.put(1, {"b": 2})
    assert store.get(1) == {"b": 2}
    assert len(store) == 1


def test_lru_eviction_at_capacity():
    store = AnnotationsStore(capacity=3)
    store.put(1, {"id": 1})
    store.put(2, {"id": 2})
    store.put(3, {"id": 3})
    assert len(store) == 3
    # Adding a 4th evicts frame 1 (oldest).
    store.put(4, {"id": 4})
    assert len(store) == 3
    assert 1 not in store
    assert store.get(1) == {}
    assert store.get(2) == {"id": 2}
    assert store.get(3) == {"id": 3}
    assert store.get(4) == {"id": 4}


def test_overwrite_does_not_evict():
    store = AnnotationsStore(capacity=2)
    store.put(1, {"a": 1})
    store.put(2, {"a": 2})
    # Overwriting an existing key must not evict anything.
    store.put(1, {"a": "new"})
    assert len(store) == 2
    assert store.get(1) == {"a": "new"}
    assert store.get(2) == {"a": 2}


def test_get_marks_recently_used():
    store = AnnotationsStore(capacity=3)
    store.put(1, {"id": 1})
    store.put(2, {"id": 2})
    store.put(3, {"id": 3})
    # Touch frame 1 so it's now MRU.
    store.get(1)
    # Inserting 4 should now evict frame 2 (the oldest untouched).
    store.put(4, {"id": 4})
    assert 2 not in store
    assert 1 in store
    assert 3 in store
    assert 4 in store


def test_invalid_capacity():
    with pytest.raises(ValueError):
        AnnotationsStore(capacity=0)
    with pytest.raises(ValueError):
        AnnotationsStore(capacity=-1)


def test_thread_safety_smoke():
    """Concurrent puts/gets must not raise or corrupt state."""
    store = AnnotationsStore(capacity=500)

    def worker(start: int) -> None:
        for i in range(start, start + 100):
            store.put(i, {"i": i})
            store.get(i)

    threads = [threading.Thread(target=worker, args=(n * 100,)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # All 500 items fit within capacity.
    assert len(store) == 500
