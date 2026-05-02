import pytest
from pathlib import Path
from gpa.eval.curation.draft import compute_scenario_dir


def test_compute_scenario_dir_new_layout(tmp_path):
    out = compute_scenario_dir(
        eval_root=tmp_path / "tests" / "eval",
        category="native-engine",
        framework="godot",
        slug="godot_86493_world_environment_glow",
    )
    assert out == tmp_path / "tests" / "eval" / "native-engine" / "godot" / "godot_86493_world_environment_glow"


def test_compute_scenario_dir_synthetic_routes_through_topic(tmp_path):
    out = compute_scenario_dir(
        eval_root=tmp_path / "tests" / "eval",
        category="synthetic",
        framework="synthetic",
        slug="e34_state_leak_new_thing",
    )
    assert "synthetic" in str(out)
    assert "state-leak" in str(out) or "misc" in str(out)
    assert out.name == "e34_state_leak_new_thing"
