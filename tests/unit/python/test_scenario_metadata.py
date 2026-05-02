from pathlib import Path
import pytest
from gpa.eval.scenario_metadata import Scenario, Source, Taxonomy, Backend


def test_scenario_dataclass_minimum():
    s = Scenario(
        path=Path("/tmp/x"),
        slug="godot_86493_world_environment_glow",
        round="r96fdc7",
        mined_at="2026-04-21",
        source=Source(type="github_issue", url="https://github.com/godotengine/godot/issues/86493",
                      repo="godotengine/godot", issue_id=86493),
        taxonomy=Taxonomy(category="native-engine", framework="godot",
                          bug_class="framework-internal"),
        backend=Backend(api="vulkan", status="not-yet-reproduced"),
        status="drafted",
        tags=[],
        notes="",
    )
    assert s.slug == "godot_86493_world_environment_glow"
