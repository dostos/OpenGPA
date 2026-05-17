"""R18-P0: ``expected_failure`` scenario-yaml block.

When a scenario is a known stable failure for non-product reasons
(mining picked wrong PR, reasoning-shallow at this model tier), the
``scenario.yaml`` can carry an ``expected_failure:`` block. The
loader exposes it on ``ScenarioMetadata.expected_failure``, and the
report generator breaks those scenarios out from the regression-only
solved-rate row so round-over-round comparisons stay legible.
"""
from __future__ import annotations

from pathlib import Path

from bhdr.eval.metrics import EvalResult, ReportGenerator
from bhdr.eval.scenario import ScenarioLoader


_BASE_MD = """\
## Bug Description

Some rendering bug.

## Difficulty

3

## Fix

```yaml
fix_pr_url: https://github.com/godotengine/godot/pull/109971
fix_sha: ec62f12862c4cfc76526eaf99afa0a24249f8288
fix_parent_sha: deadbeef00deadbeef00deadbeef00deadbeef0000
bug_class: framework-internal
files:
  - servers/rendering/foo.cpp
```
"""

_YAML_WITHOUT_EF = """\
schema_version: 1
slug: {slug}
source:
  type: github_issue
  url: https://github.com/godotengine/godot/issues/86098
  repo: godotengine/godot
  issue_id: 86098
taxonomy:
  category: native-engine
  framework: godot
  bug_class: unknown
"""

_YAML_WITH_EF = _YAML_WITHOUT_EF + """\
expected_failure:
  reason: reasoning-shallow at opus-4-7 tier
  first_observed_round: r13
"""


def _make_scenario(tmp_path: Path, *, slug: str, yaml_text: str) -> None:
    d = tmp_path / "tests-eval" / "native-engine" / "godot" / slug
    d.mkdir(parents=True)
    (d / "scenario.md").write_text(_BASE_MD)
    (d / "scenario.yaml").write_text(yaml_text)


def test_loader_exposes_expected_failure_when_present(tmp_path):
    _make_scenario(
        tmp_path, slug="rfc2ac5_stable", yaml_text=_YAML_WITH_EF.format(slug="rfc2ac5_stable"),
    )
    loader = ScenarioLoader(str(tmp_path / "tests-eval"))
    s = loader.load("rfc2ac5_stable")
    assert s.expected_failure is not None
    assert s.expected_failure["reason"] == "reasoning-shallow at opus-4-7 tier"
    assert s.expected_failure["first_observed_round"] == "r13"


def test_loader_returns_none_when_block_absent(tmp_path):
    _make_scenario(
        tmp_path, slug="rfc2ac5_no_ef",
        yaml_text=_YAML_WITHOUT_EF.format(slug="rfc2ac5_no_ef"),
    )
    loader = ScenarioLoader(str(tmp_path / "tests-eval"))
    s = loader.load("rfc2ac5_no_ef")
    assert s.expected_failure is None


def test_loader_returns_none_for_empty_block(tmp_path):
    """A bare ``expected_failure:`` with no reason is treated as absent.

    Reason is the only mandatory field; without it the block has no
    semantic content and downstream code shouldn't have to special-case
    a no-reason marker.
    """
    yaml_text = _YAML_WITHOUT_EF.format(slug="rfc2ac5_empty_ef") + "expected_failure:\n  first_observed_round: r13\n"
    _make_scenario(tmp_path, slug="rfc2ac5_empty_ef", yaml_text=yaml_text)
    loader = ScenarioLoader(str(tmp_path / "tests-eval"))
    s = loader.load("rfc2ac5_empty_ef")
    assert s.expected_failure is None


def _mk_result(sid: str, *, solved: bool, mode: str = "code_only") -> EvalResult:
    return EvalResult(
        scenario_id=sid,
        mode=mode,
        diagnosis_text="x",
        input_tokens=100,
        output_tokens=100,
        total_tokens=200,
        tool_calls=1,
        num_turns=1,
        time_seconds=1.0,
        model="test",
        timestamp="2026-05-14T00:00:00Z",
        verdict={"solved": solved, "scorer": "file_level", "confidence": "high"},
    )


def test_report_splits_solved_rate_when_stable_failures_given():
    results = [
        _mk_result("scen_a", solved=True),
        _mk_result("scen_b", solved=True),
        _mk_result("scen_stable", solved=False),
    ]
    gen = ReportGenerator()
    summary = gen.generate_summary(results, stable_failure_ids={"scen_stable"})
    overall = summary["overall"]["code_only"]
    # Total: 2 of 3 solved
    assert overall["solved_rate"] == 2 / 3
    # Regression-only: 2 of 2 solved (stable excluded)
    assert overall["solved_rate_regression_only"] == 1.0
    assert overall["regression_count"] == 2
    assert summary["stable_failure_ids"] == ["scen_stable"]


def test_report_regression_row_equals_total_when_no_stable_ids():
    results = [
        _mk_result("scen_a", solved=True),
        _mk_result("scen_b", solved=False),
    ]
    gen = ReportGenerator()
    summary = gen.generate_summary(results)
    overall = summary["overall"]["code_only"]
    assert overall["solved_rate"] == 0.5
    # Default: no scenarios excluded, regression-only matches total
    assert overall["solved_rate_regression_only"] == 0.5
    assert overall["regression_count"] == 2
    assert summary["stable_failure_ids"] == []


def test_report_stable_ids_filtered_to_observed_scenarios():
    """Passing a stable ID that isn't in the result set shouldn't break."""
    results = [_mk_result("scen_a", solved=True)]
    gen = ReportGenerator()
    summary = gen.generate_summary(
        results, stable_failure_ids={"scen_a", "missing_id"},
    )
    # Only scen_a is observed; missing_id stays out of the summary
    assert summary["stable_failure_ids"] == ["scen_a"]
    overall = summary["overall"]["code_only"]
    # With scen_a marked stable, regression cohort is empty → None
    assert overall["solved_rate_regression_only"] is None
    assert overall["regression_count"] == 0


def test_report_markdown_lists_stable_failures():
    results = [
        _mk_result("scen_a", solved=True),
        _mk_result("scen_stable", solved=False),
    ]
    gen = ReportGenerator()
    md = gen.generate_markdown(results, stable_failure_ids={"scen_stable"})
    assert "Stable failures excluded" in md
    assert "scen_stable" in md
    assert "Solved (regression-only)" in md
