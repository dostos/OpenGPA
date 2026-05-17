"""R19-corpus: aggregate dataset stats for the dashboard."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from gpa.eval.dashboard._corpus import compute_corpus_stats


_BASE_MD = """\
## Bug Description

something

## Difficulty

3

## Fix

```yaml
fix_pr_url: https://github.com/owner/repo/pull/1
fix_sha: deadbeef00000000000000000000000000000000
fix_parent_sha: cafebabe00000000000000000000000000000000
bug_class: {bug_class}
files:
{files_yaml}
```
"""

_BASE_YAML = """\
schema_version: 1
slug: {slug}
round: test-round
mined_at: '2026-05-02T00:00:00+00:00'
source:
  type: {source_type}
  url: https://github.com/owner/repo
  repo: owner/repo
  issue_id: 1
taxonomy:
  category: {category}
  framework: {framework}
  bug_class: {yaml_bug_class}
backend:
  api: {api}
  status: {bstatus}
status: {status}
tags: []
notes: ''
"""


def _write_scenario(
    root: Path, *, slug: str, category: str = "web-map", framework: str = "cesium",
    api: str = "unknown", bstatus: str = "not-yet-reproduced",
    yaml_bug_class: str = "unknown", md_bug_class: str = "framework-internal",
    status: str = "verified", source_type: str = "github_issue",
    files: list | None = None, expected_failure: dict | None = None,
):
    d = root / category / framework / slug
    d.mkdir(parents=True)
    files_yaml = "  - " + "\n  - ".join(files or ["src/foo.cpp"])
    md = _BASE_MD.format(bug_class=md_bug_class, files_yaml=files_yaml)
    (d / "scenario.md").write_text(md)
    yaml_text = _BASE_YAML.format(
        slug=slug, source_type=source_type,
        category=category, framework=framework,
        yaml_bug_class=yaml_bug_class,
        api=api, bstatus=bstatus, status=status,
    )
    if expected_failure is not None:
        yaml_text += "expected_failure:\n  reason: '" + expected_failure["reason"] + "'\n"
    (d / "scenario.yaml").write_text(yaml_text)


def test_compute_corpus_stats_basic(tmp_path):
    root = tmp_path / "eval"
    _write_scenario(root, slug="s1")
    _write_scenario(root, slug="s2", category="native-engine", framework="godot")
    _write_scenario(root, slug="s3", category="native-engine", framework="godot",
                    status="quarantined")

    stats = compute_corpus_stats(root)

    assert stats["total"] == 3
    assert stats["by_status"] == {"verified": 2, "quarantined": 1}
    assert stats["by_category"] == {"native-engine": 2, "web-map": 1}
    assert stats["by_framework"] == {"godot": 2, "cesium": 1}


def test_compute_corpus_stats_counts_fix_metadata(tmp_path):
    root = tmp_path / "eval"
    _write_scenario(root, slug="s1", md_bug_class="framework-internal",
                    files=["a.cpp", "b.cpp", "c.cpp"])
    _write_scenario(root, slug="s2", md_bug_class="consumer-misuse",
                    files=["a.js"])
    _write_scenario(root, slug="s3", category="native-engine", framework="godot",
                    md_bug_class="framework-internal",
                    files=["a.cpp"] * 8)

    stats = compute_corpus_stats(root)
    assert stats["with_fix_metadata"] == 3
    assert stats["by_md_bug_class"] == {
        "framework-internal": 2, "consumer-misuse": 1,
    }
    # 3 files = "few", 1 file = "single", 8 files = "many"
    assert stats["fix_scope_distribution"] == {
        "few": 1, "many": 1, "single": 1,
    }


def test_compute_corpus_stats_counts_expected_failure(tmp_path):
    root = tmp_path / "eval"
    _write_scenario(root, slug="s1")
    _write_scenario(root, slug="s2",
                    expected_failure={"reason": "reasoning-shallow"})
    _write_scenario(root, slug="s3", category="native-engine", framework="godot",
                    expected_failure={"reason": "model-tier ceiling"})

    stats = compute_corpus_stats(root)
    assert stats["with_expected_failure"] == 2


def test_compute_corpus_stats_missing_root(tmp_path):
    stats = compute_corpus_stats(tmp_path / "nonexistent")
    assert stats == {"total": 0}


def test_compute_corpus_stats_counters_sorted_by_count_desc(tmp_path):
    root = tmp_path / "eval"
    # 3 web-map, 1 native-engine
    for i in range(3):
        _write_scenario(root, slug=f"web_{i}")
    _write_scenario(root, slug="native_1", category="native-engine", framework="godot")

    stats = compute_corpus_stats(root)
    # First key should be the largest bucket
    assert list(stats["by_category"].keys()) == ["web-map", "native-engine"]
