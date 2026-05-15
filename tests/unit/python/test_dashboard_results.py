# tests/unit/python/test_dashboard_results.py
import json
from pathlib import Path

import pytest

from gpa.eval.dashboard._results import (
    load_and_merge_results, load_or_seed_tier_meta, derive_scenario_type,
    enrich_results,
)
from gpa.eval.metrics import EvalResult


def _make_result_dict(sid="scen_a", mode="code_only", solved=True, **kw):
    return {
        "scenario_id": sid, "mode": mode,
        "diagnosis_text": "x", "input_tokens": 100, "output_tokens": 200,
        "total_tokens": 300, "tool_calls": 1, "num_turns": 1,
        "time_seconds": 1.0, "model": "unknown",
        "timestamp": "2026-05-14T00:00:00Z",
        "verdict": {"solved": solved, "scorer": "file_level", "confidence": "high"},
        **kw,
    }


def test_merge_overlays_by_scenario_and_mode(tmp_path):
    base = tmp_path / "code_only.json"
    base.write_text(json.dumps([
        _make_result_dict("scen_a", solved=False),
        _make_result_dict("scen_b", solved=True),
    ]))
    resume = tmp_path / "code_only_merged.json"
    resume.write_text(json.dumps([
        _make_result_dict("scen_a", solved=True),  # overrides
        _make_result_dict("scen_c", solved=True),
    ]))
    merged = load_and_merge_results([base, resume])
    # By (scenario_id, mode), latest write wins
    by_sid = {r.scenario_id: r for r in merged}
    assert by_sid["scen_a"].verdict["solved"] is True  # from resume
    assert by_sid["scen_b"].verdict["solved"] is True  # only in base
    assert by_sid["scen_c"].verdict["solved"] is True  # only in resume
    assert len(merged) == 3


def test_merge_drops_pre_verdict_rows(tmp_path):
    legacy = tmp_path / "results.json"
    legacy.write_text(json.dumps([
        # Pre-R12c shape: correct_diagnosis instead of verdict.
        # EvalResult.from_dict tolerates this; we drop verdict-less rows.
        {**_make_result_dict("scen_a"), "verdict": None},
        _make_result_dict("scen_b", solved=False),
    ]))
    merged = load_and_merge_results([legacy])
    # scen_a dropped (no verdict), scen_b kept
    assert [r.scenario_id for r in merged] == ["scen_b"]


def test_merge_empty_paths_returns_empty():
    assert load_and_merge_results([]) == []


def test_load_or_seed_tier_meta_reads_existing(tmp_path):
    (tmp_path / "meta.json").write_text(json.dumps({
        "tier": "sonnet", "model": "claude-sonnet-4-6",
    }))
    tier, model = load_or_seed_tier_meta(tmp_path)
    assert tier == "sonnet"
    assert model == "claude-sonnet-4-6"


def test_load_or_seed_tier_meta_seeds_opus_when_absent(tmp_path):
    tier, model = load_or_seed_tier_meta(tmp_path)
    assert tier == "opus"
    assert "opus" in model
    # And the file is now seeded on disk
    written = json.loads((tmp_path / "meta.json").read_text())
    assert written == {"tier": "opus", "model": "claude-opus-4-7[1m]"}


def test_load_or_seed_tier_meta_handles_malformed(tmp_path):
    (tmp_path / "meta.json").write_text("not json")
    tier, model = load_or_seed_tier_meta(tmp_path)
    # Malformed → treat as missing; re-seed opus
    assert tier == "opus"


def test_derive_scenario_type_from_eval_path():
    sd = "/home/x/gh/gla/tests/eval/web-map/cesium/r5211bd_camera_jumps"
    assert derive_scenario_type(sd) == "web-map/cesium"


def test_derive_scenario_type_godot():
    sd = "/x/tests/eval/native-engine/godot/rfc2ac5_glow"
    assert derive_scenario_type(sd) == "native-engine/godot"


def test_derive_scenario_type_no_eval_in_path():
    assert derive_scenario_type("/x/random/path/slug") == "unknown"


def test_derive_scenario_type_empty():
    assert derive_scenario_type(None) == "unknown"
    assert derive_scenario_type("") == "unknown"


class _FakeScenario:
    def __init__(self, scenario_dir, expected_failure=None):
        self.scenario_dir = scenario_dir
        self.expected_failure = expected_failure


class _FakeLoader:
    def __init__(self, scenarios):
        self._by_id = {sid: scen for sid, scen in scenarios.items()}

    def load(self, sid):
        return self._by_id[sid]


def test_enrich_results_attaches_type_and_expected_failure():
    rows = [
        EvalResult.from_dict(_make_result_dict("scen_a")),
        EvalResult.from_dict(_make_result_dict("scen_b")),
    ]
    loader = _FakeLoader({
        "scen_a": _FakeScenario("/x/tests/eval/web-map/cesium/scen_a"),
        "scen_b": _FakeScenario(
            "/x/tests/eval/native-engine/godot/scen_b",
            expected_failure={"reason": "model-tier ceiling"},
        ),
    })
    enriched = list(enrich_results(rows, tier="opus", scenario_loader=loader))
    assert enriched[0]["scenario_id"] == "scen_a"
    assert enriched[0]["scenario_type"] == "web-map/cesium"
    assert enriched[0]["tier"] == "opus"
    assert enriched[0]["expected_failure"] is None
    assert enriched[1]["scenario_type"] == "native-engine/godot"
    assert enriched[1]["expected_failure"] == {"reason": "model-tier ceiling"}


def test_enrich_results_handles_loader_failure_gracefully():
    rows = [EvalResult.from_dict(_make_result_dict("missing_scenario"))]

    class _FailingLoader:
        def load(self, sid):
            raise FileNotFoundError(sid)

    enriched = list(enrich_results(rows, tier="opus", scenario_loader=_FailingLoader()))
    # Loader failure → scenario_type "unknown", expected_failure None,
    # row still kept (it has eval data even without metadata)
    assert enriched[0]["scenario_type"] == "unknown"
    assert enriched[0]["expected_failure"] is None
