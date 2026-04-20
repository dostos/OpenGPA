"""Unit tests for the Phase-3 ranking layer.

Exercises :func:`gpa.api.trace_ranking.rank_candidates` independently
from the REST/CLI wiring.
"""
from __future__ import annotations

import pytest

from gpa.api.trace_ranking import (
    FRAMEWORK_HINT_PATTERNS,
    build_corpus_for_value,
    rank_candidates,
)
from gpa.api.trace_store import TraceStore


# ----------------------------------------------------------------------
# Basic ordering: tier → hops → path length
# ----------------------------------------------------------------------


def test_sorted_by_tier_then_hops():
    cands = [
        {"path": "a.b.c.d", "confidence": "high"},
        {"path": "a.b", "confidence": "low"},
        {"path": "a.b.c", "confidence": "high"},
    ]
    out = rank_candidates(cands)
    # both high candidates precede the low; among highs, a.b.c (2 hops)
    # beats a.b.c.d (3 hops).
    assert [c["path"] for c in out] == ["a.b.c", "a.b.c.d", "a.b"]


def test_stable_within_same_tier_and_hops_prefers_shorter():
    cands = [
        {"path": "aaaaaaaaaa.longer", "confidence": "high"},
        {"path": "a.x", "confidence": "high"},
    ]
    out = rank_candidates(cands)
    assert out[0]["path"] == "a.x"


def test_distance_hops_populated():
    cands = [{"path": "map._transform._maxZoom", "confidence": "high"}]
    out = rank_candidates(cands)
    assert out[0]["distance_hops"] == 2


def test_hop_count_handles_bracket_index():
    cands = [
        {"path": "scene.children[0].material.uniforms.uZoom.value",
         "confidence": "high"},
    ]
    out = rank_candidates(cands)
    # scene . children . [0] . material . uniforms . uZoom . value — 6 hops
    assert out[0]["distance_hops"] == 6


def test_invalid_confidence_coerced_to_high():
    cands = [{"path": "a.b", "confidence": "nonsense"}]
    out = rank_candidates(cands)
    assert out[0]["confidence"] == "high"


def test_empty_input_returns_empty():
    assert rank_candidates([]) == []


def test_malformed_entries_skipped():
    cands = [{"no_path": "x"}, "not-a-dict", {"path": "ok.x"}]
    out = rank_candidates(cands)  # type: ignore[arg-type]
    assert len(out) == 1
    assert out[0]["path"] == "ok.x"


# ----------------------------------------------------------------------
# Rarity penalty / boost
# ----------------------------------------------------------------------


def test_rarity_unique_value_upgrades_tier():
    cands = [{"path": "x.rare", "confidence": "low"}]
    # Unique — upgrades low→medium.
    out = rank_candidates(cands, corpus={"__count__": 1})
    assert out[0]["confidence"] == "medium"


def test_rarity_unique_value_medium_upgrades_to_high():
    cands = [{"path": "x.rare", "confidence": "medium"}]
    out = rank_candidates(cands, corpus={"__count__": 1})
    assert out[0]["confidence"] == "high"


def test_rarity_very_common_downgrades_tier():
    cands = [{"path": "x.common", "confidence": "high"}]
    out = rank_candidates(cands, corpus={"__count__": 20})
    assert out[0]["confidence"] == "medium"


def test_rarity_common_downgrades_medium_to_low():
    cands = [{"path": "x.common", "confidence": "medium"}]
    out = rank_candidates(cands, corpus={"__count__": 20})
    assert out[0]["confidence"] == "low"


def test_rarity_no_corpus_keeps_tier_untouched():
    cands = [{"path": "x.whatever", "confidence": "high"}]
    out = rank_candidates(cands)  # no corpus passed
    assert out[0]["confidence"] == "high"
    assert out[0]["raw_confidence"] == "high"


def test_rarity_middle_band_keeps_tier():
    cands = [{"path": "x.y", "confidence": "medium"}]
    out = rank_candidates(cands, corpus={"__count__": 3})
    assert out[0]["confidence"] == "medium"


def test_rarity_corpus_as_path_map_counts_keys():
    cands = [{"path": "x.y", "confidence": "medium"}]
    corpus = {"path1": 1, "path2": 1}
    out = rank_candidates(cands, corpus=corpus)
    assert out[0]["confidence"] == "medium"  # count is 2, mid band


# ----------------------------------------------------------------------
# Framework-specific hints
# ----------------------------------------------------------------------


def test_framework_hint_boosts_low_to_medium():
    cands = [{"path": "THREE.uniforms.uZoom.value", "confidence": "low"}]
    out = rank_candidates(cands)
    assert out[0]["confidence"] == "medium"


def test_framework_hint_boosts_medium_to_high():
    cands = [{"path": "map._transform._maxZoom", "confidence": "medium"}]
    out = rank_candidates(cands)
    assert out[0]["confidence"] == "high"


def test_framework_hint_preserves_high():
    cands = [{"path": "scene.foo", "confidence": "high"}]
    out = rank_candidates(cands)
    assert out[0]["confidence"] == "high"


def test_non_hint_path_gets_no_bump():
    cands = [{"path": "random._private.stash", "confidence": "low"}]
    out = rank_candidates(cands)
    assert out[0]["confidence"] == "low"


def test_framework_hint_list_is_nonempty_and_documented():
    """Sanity — if someone wipes the heuristic list, the test fails loudly."""
    assert len(FRAMEWORK_HINT_PATTERNS) >= 3


def test_raw_confidence_preserved():
    cands = [{"path": "map._transform.zoom", "confidence": "low"}]
    out = rank_candidates(cands, corpus={"__count__": 1})
    # Expect double promotion: rarity (low → medium) + hint (medium → high)
    assert out[0]["raw_confidence"] == "low"
    assert out[0]["confidence"] == "high"


# ----------------------------------------------------------------------
# Full-pipeline integration: mix all signals
# ----------------------------------------------------------------------


def test_unique_rare_framework_path_beats_common_deep_path():
    cands = [
        # Generic, deeply buried.
        {"path": "app._internal.cache.row[3].cell", "confidence": "high"},
        # Framework prefix, shallow, and unique.
        {"path": "map._transform._maxZoom", "confidence": "high"},
    ]
    out = rank_candidates(cands, corpus={"__count__": 1})
    # Unique + high + framework hint + shallow → first.
    assert out[0]["path"] == "map._transform._maxZoom"


# ----------------------------------------------------------------------
# build_corpus_for_value
# ----------------------------------------------------------------------


def _src(path: str, vhash: str = "h"):
    return {
        "roots": ["X"],
        "value_index": {vhash: [{"path": path, "type": "number"}]},
    }


def test_build_corpus_counts_distinct_paths():
    store = TraceStore()
    store.put(1, 0, _src("a.x"))
    store.put(2, 0, _src("b.y"))
    # Duplicate path under different frames — should count once.
    store.put(3, 0, _src("a.x"))
    corpus = build_corpus_for_value(store, "h", [1, 2, 3])
    assert corpus == {"__count__": 2}


def test_build_corpus_missing_hash_yields_zero():
    store = TraceStore()
    store.put(1, 0, _src("a.x"))
    corpus = build_corpus_for_value(store, "missing-hash", [1])
    assert corpus == {"__count__": 0}


def test_build_corpus_unknown_frame_ids_tolerated():
    store = TraceStore()
    corpus = build_corpus_for_value(store, "h", [999, 1000])
    assert corpus == {"__count__": 0}
