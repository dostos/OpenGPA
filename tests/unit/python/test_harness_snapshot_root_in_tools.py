"""When a scenario references an upstream snapshot, the harness should
expose the resolved snapshot root via tools["snapshot_root"] so the
cli_agent can pin GPA_UPSTREAM_ROOT for `gpa upstream` shell calls.

Lazy callable shape (matching tools["run_with_capture"]): returns Path
on success, None on fetch error."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bhdr.eval.harness import EvalHarness
from bhdr.eval.scenario import ScenarioMetadata


def _make_scenario(**overrides) -> ScenarioMetadata:
    base = dict(
        id="test_id",
        title="T",
        bug_description="b",
        expected_output="e",
        actual_output="a",
        ground_truth_diagnosis="gt",
        ground_truth_fix="fix",
        difficulty=3,
        adversarial_principles=[],
        gpa_advantage="",
        source_path="/tmp/x.c",
        binary_name="test_id",
    )
    base.update(overrides)
    return ScenarioMetadata(**base)


def _bare_harness() -> EvalHarness:
    h = EvalHarness.__new__(EvalHarness)
    h.results = []
    h._model = "test"
    h._snapshot_fetcher = MagicMock()
    h.runner = MagicMock()
    h.loader = MagicMock()
    h._scorer = MagicMock()
    return h


def test_snapshot_root_callable_returns_path_when_fetch_succeeds(tmp_path):
    h = _bare_harness()
    h._snapshot_fetcher.fetch.return_value = tmp_path / "fake_snap"
    scenario = _make_scenario(
        upstream_snapshot_repo="https://github.com/o/r",
        upstream_snapshot_sha="abc123",
    )
    tools = h._build_tools(scenario, mode="with_gla")
    assert "snapshot_root" in tools
    assert callable(tools["snapshot_root"])
    assert tools["snapshot_root"]() == tmp_path / "fake_snap"


def test_snapshot_root_callable_returns_none_on_fetch_error():
    h = _bare_harness()
    h._snapshot_fetcher.fetch.side_effect = RuntimeError("clone failed")
    scenario = _make_scenario(
        upstream_snapshot_repo="https://github.com/o/r",
        upstream_snapshot_sha="abc123",
    )
    tools = h._build_tools(scenario, mode="with_gla")
    assert tools["snapshot_root"]() is None


def test_snapshot_root_absent_when_no_snapshot_refs():
    h = _bare_harness()
    scenario = _make_scenario()  # no upstream_snapshot_repo / sha
    tools = h._build_tools(scenario, mode="with_gla")
    assert "snapshot_root" not in tools


def test_snapshot_root_present_in_code_only_too(tmp_path):
    """Snapshot tools (read/list/grep_upstream) are exposed for both modes
    so code_only can also navigate upstream — snapshot_root should be too."""
    h = _bare_harness()
    h._snapshot_fetcher.fetch.return_value = tmp_path / "snap"
    scenario = _make_scenario(
        upstream_snapshot_repo="https://github.com/o/r",
        upstream_snapshot_sha="abc123",
    )
    tools = h._build_tools(scenario, mode="code_only")
    assert tools["snapshot_root"]() == tmp_path / "snap"
