"""Tests for extended ScenarioMetadata fields (real-world curation pipeline)."""
from gla.eval.scenario import ScenarioMetadata


def test_scenario_metadata_has_new_fields():
    s = ScenarioMetadata(
        id="r1_test",
        title="Test",
        bug_description="bug",
        expected_output="e",
        actual_output="a",
        ground_truth_diagnosis="gt",
        ground_truth_fix="fix",
        difficulty=3,
        adversarial_principles=[],
        gla_advantage="",
        source_path="/tmp/x.c",
        binary_name="r1_test",
        # New fields — all optional
        source_url="https://github.com/x/y/issues/1",
        source_type="issue",
        source_date="2024-03-17",
        source_commit_sha=None,
        source_attribution="Reported by @u",
        tier="core",
        api="opengl",
        framework="none",
        bug_signature={"type": "color_histogram_in_region",
                       "spec": {"region": [0, 0, 1, 1],
                                "dominant_color": [1, 0, 0, 1],
                                "tolerance": 0.1}},
        predicted_helps="yes",
        predicted_helps_reasoning="GPU state exposes the uniform",
        observed_helps=None,
        observed_helps_evidence=None,
        failure_mode=None,
        failure_mode_details=None,
    )
    assert s.source_url == "https://github.com/x/y/issues/1"
    assert s.tier == "core"
    assert s.bug_signature["type"] == "color_histogram_in_region"
    assert s.observed_helps is None
