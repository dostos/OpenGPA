"""Tests for parsing the `## Fix` section of scenario.md per the
maintainer-framing spec (docs/superpowers/specs/2026-04-21-maintainer-framing-design.md).

The `## Fix` section is Phase-1-forward: newly-drafted scenarios emit it,
but legacy scenarios on disk predate the spec and must still load with
`fix=None`.
"""
from __future__ import annotations

import logging
import textwrap
from pathlib import Path

import pytest

from gpa.eval.scenario import FixMetadata, ScenarioLoader


# ---------------------------------------------------------------------------
# Skeleton scenario.md that satisfies the rest of the loader.  Tests inject
# a `## Fix` section into it (or omit it, for legacy parity).
# ---------------------------------------------------------------------------

_BASE_MD_WITHOUT_FIX = """\
# R99_FIX_TEST: Fix section parser test scenario

## User Report
A user-filed bug description.

## Expected Correct Output
Correct frame.

## Actual Broken Output
Broken frame.

## Ground Truth
Root cause blockquote:

> "the upstream bug is ..." (quoted from upstream)

## Difficulty Rating
3/5

## Adversarial Principles
- some-principle

## How OpenGPA Helps
Tier 1 capture.

## Source
- **URL**: https://github.com/owner/repo/issues/1
- **Type**: issue
- **Date**: 2026-04-01
- **Commit SHA**: (n/a)
- **Attribution**: Reported by @user

## Tier
core

## API
opengl

## Framework
none

## Bug Signature
```yaml
type: framebuffer_dominant_color
spec:
  expected_rgba: [1.0, 0.0, 0.0, 1.0]
  tolerance: 0.1
```
"""


_GOOD_MAIN_C = """\
// SOURCE: https://github.com/owner/repo/issues/1
#include <GL/gl.h>
int main(void) { return 0; }
"""


def _write_scenario(
    tmp_path: Path, scenario_id: str, scenario_md: str, main_c: str = _GOOD_MAIN_C
) -> ScenarioLoader:
    """Materialize a scenario dir under tmp_path/scenario_id, return a loader
    rooted at tmp_path so `loader.load(scenario_id)` works.
    """
    d = tmp_path / scenario_id
    d.mkdir()
    (d / "main.c").write_text(main_c)
    (d / "scenario.md").write_text(scenario_md)
    return ScenarioLoader(eval_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# Parse tests
# ---------------------------------------------------------------------------


def test_parse_fix_section_all_fields(tmp_path):
    """Scenario with a complete `## Fix` YAML block populates FixMetadata."""
    fix_block = textwrap.dedent("""\
        ## Fix

        ```yaml
        fix_pr_url: https://github.com/mrdoob/three.js/pull/27456
        fix_sha: a1b2c3d4e5f6
        fix_parent_sha: 1234abcd5678
        bug_class: framework-internal
        files:
          - src/renderers/webgl/WebGLBackground.js
          - src/renderers/webgl/WebGLRenderer.js
        change_summary: >
          WebGLBackground.render() called before autoClear, causing sky to
          paint over user geometry.  Move background draw to after clear.
        diff_excerpt: |
          -  this.render(scene, camera);
          +  this.clear();
          +  this.render(scene, camera);
        ```
        """)
    md = _BASE_MD_WITHOUT_FIX + "\n" + fix_block
    loader = _write_scenario(tmp_path, "r99_fix_all", md)
    scenario = loader.load("r99_fix_all")

    assert scenario.fix is not None, "expected FixMetadata to be populated"
    assert isinstance(scenario.fix, FixMetadata)
    assert scenario.fix.fix_pr_url == "https://github.com/mrdoob/three.js/pull/27456"
    assert scenario.fix.fix_sha == "a1b2c3d4e5f6"
    assert scenario.fix.fix_parent_sha == "1234abcd5678"
    assert scenario.fix.bug_class == "framework-internal"
    assert scenario.fix.files == [
        "src/renderers/webgl/WebGLBackground.js",
        "src/renderers/webgl/WebGLRenderer.js",
    ]
    assert "WebGLBackground.render() called before autoClear" in scenario.fix.change_summary
    assert "Move background draw" in scenario.fix.change_summary
    assert scenario.fix.diff_excerpt is not None
    assert "this.clear()" in scenario.fix.diff_excerpt


def test_parse_fix_section_missing_yaml_block(tmp_path, caplog):
    """A `## Fix` heading with no fenced YAML block → fix=None + warning."""
    fix_block = "## Fix\n\nSome prose but no YAML block whatsoever.\n"
    md = _BASE_MD_WITHOUT_FIX + "\n" + fix_block
    loader = _write_scenario(tmp_path, "r99_fix_no_yaml", md)
    with caplog.at_level(logging.WARNING, logger="gpa.eval.scenario"):
        scenario = loader.load("r99_fix_no_yaml")
    assert scenario.fix is None
    assert any(
        "no parseable YAML block" in r.getMessage() or "no YAML block" in r.getMessage()
        for r in caplog.records
    )


def test_parse_fix_section_missing_required_field(tmp_path, caplog):
    """`## Fix` YAML without `files` → fix=None + warning."""
    fix_block = textwrap.dedent("""\
        ## Fix

        ```yaml
        fix_pr_url: https://github.com/x/y/pull/1
        bug_class: framework-internal
        change_summary: No files listed, which is a schema error for non-legacy.
        ```
        """)
    md = _BASE_MD_WITHOUT_FIX + "\n" + fix_block
    loader = _write_scenario(tmp_path, "r99_fix_no_files", md)
    with caplog.at_level(logging.WARNING, logger="gpa.eval.scenario"):
        scenario = loader.load("r99_fix_no_files")
    assert scenario.fix is None
    assert any("empty files list" in r.getMessage() for r in caplog.records)


def test_parse_fix_section_missing_fix_pr_url(tmp_path, caplog):
    """YAML without `fix_pr_url` is also invalid (required field)."""
    fix_block = textwrap.dedent("""\
        ## Fix

        ```yaml
        bug_class: framework-internal
        files:
          - src/a.js
        change_summary: Missing fix_pr_url.
        ```
        """)
    md = _BASE_MD_WITHOUT_FIX + "\n" + fix_block
    loader = _write_scenario(tmp_path, "r99_fix_no_url", md)
    with caplog.at_level(logging.WARNING, logger="gpa.eval.scenario"):
        scenario = loader.load("r99_fix_no_url")
    assert scenario.fix is None
    assert any("required field" in r.getMessage() for r in caplog.records)


def test_parse_legacy_scenario_without_fix(tmp_path, caplog):
    """No `## Fix` heading at all → fix=None, no warning emitted."""
    loader = _write_scenario(tmp_path, "r99_legacy", _BASE_MD_WITHOUT_FIX)
    with caplog.at_level(logging.WARNING, logger="gpa.eval.scenario"):
        scenario = loader.load("r99_legacy")
    assert scenario.fix is None
    # Critically: no warning, because there's no section at all.
    assert not any(
        "`## Fix`" in r.getMessage() for r in caplog.records
    ), "legacy scenarios must load silently"


def test_fix_section_with_multiple_files(tmp_path):
    """Multi-file YAML list is preserved in order."""
    fix_block = textwrap.dedent("""\
        ## Fix

        ```yaml
        fix_pr_url: https://github.com/x/y/pull/42
        fix_sha: deadbeef
        fix_parent_sha: cafebabe
        bug_class: framework-internal
        files:
          - a.js
          - b.js
          - c.js
        change_summary: Multi-file fix spanning three modules.
        ```
        """)
    md = _BASE_MD_WITHOUT_FIX + "\n" + fix_block
    loader = _write_scenario(tmp_path, "r99_fix_multi", md)
    scenario = loader.load("r99_fix_multi")
    assert scenario.fix is not None
    assert scenario.fix.files == ["a.js", "b.js", "c.js"]


def test_bug_class_legacy_allowed(tmp_path, caplog):
    """`bug_class: legacy` with `files: []` parses cleanly (escape hatch)."""
    fix_block = textwrap.dedent("""\
        ## Fix

        ```yaml
        fix_pr_url: https://github.com/x/y/issues/99
        bug_class: legacy
        files: []
        change_summary: Fix PR not resolvable — retrofit escape hatch.
        ```
        """)
    md = _BASE_MD_WITHOUT_FIX + "\n" + fix_block
    loader = _write_scenario(tmp_path, "r99_fix_legacy", md)
    with caplog.at_level(logging.WARNING, logger="gpa.eval.scenario"):
        scenario = loader.load("r99_fix_legacy")
    assert scenario.fix is not None
    assert scenario.fix.bug_class == "legacy"
    assert scenario.fix.files == []
    # No warnings for the legacy escape hatch.
    assert not any(
        "empty files list" in r.getMessage() for r in caplog.records
    ), "bug_class: legacy with empty files must not warn"


def test_bug_class_unknown_preserved_with_warning(tmp_path, caplog):
    """Unknown bug_class value → kept on object, warning emitted."""
    fix_block = textwrap.dedent("""\
        ## Fix

        ```yaml
        fix_pr_url: https://github.com/x/y/pull/1
        bug_class: some-new-category
        files:
          - a.js
        change_summary: Novel class we haven't catalogued yet.
        ```
        """)
    md = _BASE_MD_WITHOUT_FIX + "\n" + fix_block
    loader = _write_scenario(tmp_path, "r99_fix_unknown_class", md)
    with caplog.at_level(logging.WARNING, logger="gpa.eval.scenario"):
        scenario = loader.load("r99_fix_unknown_class")
    assert scenario.fix is not None
    assert scenario.fix.bug_class == "some-new-category"
    assert any(
        "unknown bug_class" in r.getMessage() for r in caplog.records
    )


def test_fix_section_malformed_yaml(tmp_path, caplog):
    """Broken YAML syntax → fix=None + warning, no exception."""
    fix_block = textwrap.dedent("""\
        ## Fix

        ```yaml
        fix_pr_url: [unclosed
          bug_class: {invalid
        ```
        """)
    md = _BASE_MD_WITHOUT_FIX + "\n" + fix_block
    loader = _write_scenario(tmp_path, "r99_fix_bad_yaml", md)
    with caplog.at_level(logging.WARNING, logger="gpa.eval.scenario"):
        scenario = loader.load("r99_fix_bad_yaml")
    assert scenario.fix is None
