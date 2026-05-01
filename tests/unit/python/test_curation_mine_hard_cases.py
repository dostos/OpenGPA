from gpa.eval.curation.discover import DiscoveryCandidate
from gpa.eval.curation.mine_hard_cases import score_candidate, select_stratified
from gpa.eval.curation.triage import IssueThread


def make_synthetic_candidate(*, body: str, url: str, has_fix_pr_linked: bool):
    """Build a synthetic DiscoveryCandidate with the body embedded in metadata.

    When ``has_fix_pr_linked=True``, append a closing-PR reference so the
    ``fix_pr_linked`` triage_required group matches.
    """
    if has_fix_pr_linked and "Closed by #" not in body and "pull/" not in body:
        body = f"{body}\n\nClosed by #2"
    cand = DiscoveryCandidate(
        url=url,
        source_type="issue",
        title="synthetic",
        labels=[],
        metadata={"body": body},
    )
    return cand


def test_score_stackoverflow_threejs_user_config():
    cand = DiscoveryCandidate(
        url="https://stackoverflow.com/questions/37647853/depthwrite",
        source_type="stackoverflow",
        title="Three.js transparent points depthWrite problem",
        labels=["three.js"],
    )
    thread = IssueThread(
        url=cand.url,
        title=cand.title,
        body="Transparent points overlap incorrectly and look solid.",
        comments=[
            "=== Accepted Answer (score: 61) ===\n"
            "Use depthWrite false for transparent points; depth and blending "
            "do not work together in this case."
        ],
    )

    rec = score_candidate(cand, thread)

    assert rec.category == "framework-app-dev"
    assert rec.subcategory == "web-3d"
    assert rec.framework == "three.js"
    assert rec.bug_class_guess == "user-config"
    assert rec.score >= 6
    assert "gpu:depth_blend_state" in rec.reason_codes
    assert "resolution:accepted_answer" in rec.reason_codes


def test_score_framework_repo_not_planned_can_be_app_dev():
    cand = DiscoveryCandidate(
        url="https://github.com/mrdoob/three.js/issues/31132",
        source_type="issue",
        title="WebGPURenderer images with metadata produce different result",
        labels=["Browser Issue"],
    )
    thread = IssueThread(
        url=cand.url,
        title=cand.title,
        body="WebGPU and WebGL render the same PNG texture with different colors.",
        comments=["The workaround is colorSpaceConversion none and premultiplyAlpha none."],
    )

    rec = score_candidate(cand, thread)

    assert rec.category == "framework-app-dev"
    assert rec.subcategory == "web-3d"
    assert rec.framework == "three.js"
    assert rec.score > 0
    assert "gpu:color_pipeline" in rec.reason_codes


def test_select_stratified_caps_per_taxonomy_cell():
    records = []
    for i in range(5):
        cand = DiscoveryCandidate(
            url=f"https://stackoverflow.com/questions/{i}/depthwrite",
            source_type="stackoverflow",
            title=f"Three.js transparent depthWrite {i}",
            labels=["three.js"],
        )
        records.append(score_candidate(cand, IssueThread(
            url=cand.url,
            title=cand.title,
            body="Transparent wrong output with depthWrite.",
            comments=["=== Accepted Answer (score: 2) ===\nset depthWrite false"],
        )))
    for i in range(3):
        cand = DiscoveryCandidate(
            url=f"https://stackoverflow.com/questions/9{i}/shadow",
            source_type="stackoverflow",
            title=f"React Three Fiber cropped shadow {i}",
            labels=["react-three-fiber"],
        )
        records.append(score_candidate(cand, IssueThread(
            url=cand.url,
            title=cand.title,
            body="Shadows are cropped in a rectangular region.",
            comments=["=== Accepted Answer (score: 2) ===\nset shadow-camera-left"],
        )))

    selected = select_stratified(records, top_k=4, min_score=1, per_cell_cap=2)

    assert len(selected) == 4
    counts = {}
    for rec in selected:
        counts[rec.taxonomy_cell] = counts.get(rec.taxonomy_cell, 0) + 1
    assert max(counts.values()) == 2
    assert all(rec.selected for rec in selected)


def test_classify_score_drops_when_triage_required_unmet():
    from gpa.eval.curation.mine_hard_cases import score_candidate, load_rules
    rules = load_rules()  # default rules file
    cand = make_synthetic_candidate(
        body="Cubes flicker on Vulkan. Repro: ...",
        url="https://github.com/x/y/issues/99",
        has_fix_pr_linked=False,
    )
    rec = score_candidate(cand, rules)
    assert rec.terminal_reason == "triage_rejected"
    assert "missing_fix_pr_linked" in rec.score_reasons


def test_classify_score_drops_feature_request_via_reject_rule():
    from gpa.eval.curation.mine_hard_cases import score_candidate, load_rules
    rules = load_rules()
    cand = make_synthetic_candidate(
        body=(
            "Feature request: please add a depth-of-field shader. "
            "Currently glitches when missing inputs."
        ),
        url="https://github.com/x/y/issues/100",
        has_fix_pr_linked=True,
    )
    rec = score_candidate(cand, rules)
    assert rec.terminal_reason == "triage_rejected"
    assert "feature_request" in rec.score_reasons
