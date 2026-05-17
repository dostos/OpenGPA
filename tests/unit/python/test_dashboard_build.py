import json
from pathlib import Path

import pytest

from bhdr.eval.dashboard.build import build_index


def _write_result(path, scenario_id, mode, solved, **kw):
    rows = [{
        "scenario_id": scenario_id, "mode": mode,
        "diagnosis_text": "x", "input_tokens": 100, "output_tokens": 200,
        "total_tokens": 300, "tool_calls": 1, "num_turns": 1,
        "time_seconds": 1.0, "model": "unknown",
        "timestamp": "2026-05-14T00:00:00Z",
        "verdict": {"solved": solved, "scorer": "file_level", "confidence": "high"},
        **kw,
    }]
    path.write_text(json.dumps(rows))


class _StubLoader:
    """ScenarioLoader stub for tests — returns a fake scenario per id."""

    def load(self, sid):
        class _S:
            scenario_dir = f"/x/tests/eval/web-map/cesium/{sid}"
            expected_failure = None
        return _S()


def test_build_index_minimal_round(tmp_path):
    data3 = tmp_path / "data3"
    rounds = data3 / "2026-05-14-r18"
    rounds.mkdir(parents=True)
    _write_result(rounds / "code_only.json", "scen_a", "code_only", True)

    rounds_md = tmp_path / "rounds"
    rounds_md.mkdir()
    (rounds_md / "2026-05-14-r18.md").write_text(
        "# Round R18\n\nTest headline.\n"
    )

    out = tmp_path / "out.json"
    build_index(
        data3_root=data3,
        rounds_dir=rounds_md,
        output_path=out,
        scenario_loader=_StubLoader(),
    )
    payload = json.loads(out.read_text())
    assert payload["rounds"][0]["id"] == "r18"
    assert payload["rounds"][0]["headline"] == "Test headline."
    assert payload["rounds"][0]["results"][0]["scenario_id"] == "scen_a"
    assert payload["scenario_types"] == ["web-map/cesium"]
    assert "built_at" in payload


def test_build_index_folds_rerun(tmp_path):
    data3 = tmp_path / "data3"
    base = data3 / "2026-05-05-r17"
    resume = data3 / "2026-05-05-r17-resume"
    base.mkdir(parents=True)
    resume.mkdir(parents=True)
    _write_result(base / "code_only.json", "scen_a", "code_only", False)
    _write_result(resume / "code_only.json", "scen_a", "code_only", True)

    out = tmp_path / "out.json"
    build_index(
        data3_root=data3,
        rounds_dir=tmp_path,  # no narratives
        output_path=out,
        scenario_loader=_StubLoader(),
    )
    payload = json.loads(out.read_text())
    assert len(payload["rounds"]) == 1
    rnd = payload["rounds"][0]
    assert rnd["id"] == "r17"
    # The resume's solved=True overrode the base's solved=False
    assert rnd["results"][0]["solved"] is True


def test_build_index_skips_round_with_no_verdict_data(tmp_path):
    data3 = tmp_path / "data3"
    legacy = data3 / "2026-05-04-round4-claude-cli"
    legacy.mkdir(parents=True)
    # Pre-verdict legacy row
    (legacy / "results.json").write_text(json.dumps([{
        "scenario_id": "scen_a", "mode": "code_only",
        "diagnosis_text": "x", "input_tokens": 100, "output_tokens": 200,
        "total_tokens": 300, "tool_calls": 1, "num_turns": 1,
        "time_seconds": 1.0, "model": "unknown",
        "timestamp": "2026-05-14T00:00:00Z",
        "verdict": None,
    }]))

    out = tmp_path / "out.json"
    build_index(
        data3_root=data3,
        rounds_dir=tmp_path,
        output_path=out,
        scenario_loader=_StubLoader(),
    )
    payload = json.loads(out.read_text())
    assert payload["rounds"] == []


def test_build_index_missing_data3_raises(tmp_path):
    with pytest.raises(SystemExit):
        build_index(
            data3_root=tmp_path / "nope",
            rounds_dir=tmp_path,
            output_path=tmp_path / "out.json",
            scenario_loader=_StubLoader(),
        )
