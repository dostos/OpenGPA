"""Tests for gpa.eval.index_cli."""
import pytest
from pathlib import Path


def test_index_by_taxonomy_renders_counts(tmp_path):
    from gpa.eval.index_cli import build_taxonomy_table
    from gpa.eval.scenario_metadata import (
        Scenario, Source, Taxonomy, Backend, dump_scenario_yaml, iter_scenarios,
    )
    for cat, fw, slug in [
        ("native-engine", "godot", "x1"),
        ("native-engine", "godot", "x2"),
        ("web-3d", "three.js", "y1"),
    ]:
        d = tmp_path / cat / fw / slug
        d.mkdir(parents=True)
        (d / "scenario.md").write_text("x")
        s = Scenario(path=d, slug=slug, round="r1", mined_at="2026-01-01",
                     source=Source(type="synthetic"),
                     taxonomy=Taxonomy(category=cat, framework=fw, bug_class="synthetic"),
                     backend=Backend(), status="drafted")
        dump_scenario_yaml(s, d / "scenario.yaml")
    table = build_taxonomy_table(list(iter_scenarios(tmp_path)))
    assert "native-engine" in table
    assert "godot" in table
    assert "| native-engine | godot | 2 |" in table


def test_index_by_backend_renders_counts(tmp_path):
    from gpa.eval.index_cli import build_backend_table
    from gpa.eval.scenario_metadata import (
        Scenario, Source, Taxonomy, Backend, dump_scenario_yaml, iter_scenarios,
    )
    for api, st, slug in [
        ("opengl", "not-yet-reproduced", "a1"),
        ("opengl", "not-yet-reproduced", "a2"),
        ("vulkan", "reproduced", "b1"),
    ]:
        d = tmp_path / "synthetic" / "synthetic" / slug
        d.mkdir(parents=True)
        (d / "scenario.md").write_text("x")
        s = Scenario(path=d, slug=slug, round="r1", mined_at="2026-01-01",
                     source=Source(type="synthetic"),
                     taxonomy=Taxonomy(category="synthetic", framework="synthetic", bug_class="synthetic"),
                     backend=Backend(api=api, status=st), status="drafted")
        dump_scenario_yaml(s, d / "scenario.yaml")
    table = build_backend_table(list(iter_scenarios(tmp_path)))
    assert "opengl" in table
    assert "vulkan" in table
    assert "| opengl | not-yet-reproduced | 2 |" in table


def test_main_returns_zero(tmp_path):
    from gpa.eval.index_cli import main
    from gpa.eval.scenario_metadata import (
        Scenario, Source, Taxonomy, Backend, dump_scenario_yaml,
    )
    d = tmp_path / "synthetic" / "synthetic" / "z1"
    d.mkdir(parents=True)
    (d / "scenario.md").write_text("x")
    s = Scenario(path=d, slug="z1", round="r1", mined_at="2026-01-01",
                 source=Source(type="synthetic"),
                 taxonomy=Taxonomy(category="synthetic", framework="synthetic", bug_class="synthetic"),
                 backend=Backend(), status="drafted")
    dump_scenario_yaml(s, d / "scenario.yaml")
    assert main(["index", "--by", "taxonomy", "--root", str(tmp_path)]) == 0


def _make_scenario(tmp_path, cat, fw, slug, round_="r1"):
    """Helper to create a scenario.yaml at tmp_path/<cat>/<fw>/<slug>/."""
    from gpa.eval.scenario_metadata import (
        Scenario, Source, Taxonomy, Backend, dump_scenario_yaml,
    )
    d = tmp_path / cat / fw / slug
    d.mkdir(parents=True)
    (d / "scenario.md").write_text("x")
    s = Scenario(path=d, slug=slug, round=round_, mined_at="2026-01-01",
                 source=Source(type="synthetic"),
                 taxonomy=Taxonomy(category=cat, framework=fw, bug_class="synthetic"),
                 backend=Backend(), status="drafted")
    dump_scenario_yaml(s, d / "scenario.yaml")
    return s


def test_index_by_round_renders_counts(tmp_path):
    from gpa.eval.index_cli import build_round_table
    from gpa.eval.scenario_metadata import iter_scenarios
    _make_scenario(tmp_path, "native-engine", "godot", "g1", round_="r1")
    _make_scenario(tmp_path, "native-engine", "godot", "g2", round_="r96fdc7")
    _make_scenario(tmp_path, "web-3d", "synthetic", "w1", round_="r96fdc7")
    scenarios = list(iter_scenarios(tmp_path))
    table = build_round_table(scenarios)
    assert "| r1 | 1 |" in table
    assert "| r96fdc7 | 2 |" in table


def test_filter_narrows_scenarios(tmp_path):
    from gpa.eval.index_cli import build_taxonomy_table, apply_filter
    from gpa.eval.scenario_metadata import iter_scenarios
    _make_scenario(tmp_path, "native-engine", "godot", "g1")
    _make_scenario(tmp_path, "native-engine", "godot", "g2")
    _make_scenario(tmp_path, "web-3d", "threejs", "t1")
    scenarios = list(iter_scenarios(tmp_path))
    filtered = apply_filter(scenarios, "taxonomy.framework=godot")
    table = build_taxonomy_table(filtered)
    assert "| godot | 2 |" in table
    assert "threejs" not in table


def test_filter_unknown_field_raises(tmp_path):
    from gpa.eval.index_cli import apply_filter
    from gpa.eval.scenario_metadata import iter_scenarios
    _make_scenario(tmp_path, "native-engine", "godot", "g1")
    scenarios = list(iter_scenarios(tmp_path))
    with pytest.raises(ValueError, match="unknown filter field"):
        apply_filter(scenarios, "no.such.field=x")


def test_filter_two_clauses_anded(tmp_path):
    from gpa.eval.index_cli import apply_filter
    from gpa.eval.scenario_metadata import iter_scenarios, Backend, dump_scenario_yaml, Scenario, Source, Taxonomy
    # godot+vulkan, godot+opengl, threejs+vulkan
    for fw, api, slug in [("godot", "vulkan", "g_vk"), ("godot", "opengl", "g_gl"), ("threejs", "vulkan", "t_vk")]:
        d = tmp_path / "native-engine" / fw / slug
        d.mkdir(parents=True)
        (d / "scenario.md").write_text("x")
        s = Scenario(path=d, slug=slug, round="r1", mined_at="2026-01-01",
                     source=Source(type="synthetic"),
                     taxonomy=Taxonomy(category="native-engine", framework=fw, bug_class="synthetic"),
                     backend=Backend(api=api), status="drafted")
        dump_scenario_yaml(s, d / "scenario.yaml")
    scenarios = list(iter_scenarios(tmp_path))
    filtered = apply_filter(scenarios, "taxonomy.framework=godot,backend.api=vulkan")
    assert len(filtered) == 1
    assert filtered[0].slug == "g_vk"
