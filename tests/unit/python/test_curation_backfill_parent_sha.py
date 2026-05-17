"""Tests for the fix_parent_sha backfill tool.

Older mined scenarios committed before the curation pipeline fetched
the merge-commit's parent need their scenario.md fix blocks patched
in-place so the upstream snapshot points at the buggy state, not the
post-fix state.
"""
from __future__ import annotations

import subprocess
from unittest.mock import patch

from bhdr.eval.curation.backfill_parent_sha import (
    backfill_one,
    _patch_yaml_body,
    _extract_field,
)


_SCENARIO_MD = """## User Report

Some bug report.

## Fix

```yaml
fix_pr_url: https://github.com/godotengine/godot/pull/109971
fix_sha: ec62f12862c4cfc76526eaf99afa0a24249f8288
bug_class: framework-internal
files:
  - servers/rendering/foo.cpp
```
"""


def _gh_api_response(parents: list[str]) -> str:
    import json
    return json.dumps({
        "sha": "ec62f12862",
        "parents": [{"sha": p} for p in parents],
    })


def test_backfill_inserts_after_fix_sha(tmp_path):
    md = tmp_path / "scenario.md"
    md.write_text(_SCENARIO_MD)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_gh_api_response(["70f07467be0000000000000000000000000000aa",
                                     "f61ee7bdf60000000000000000000000000000bb"]),
            stderr="",
        )
        result = backfill_one(md)

    assert result.status == "patched"
    assert result.detail == "70f07467be0000000000000000000000000000aa"
    text = md.read_text()
    # Inserted in the right spot — between fix_sha and bug_class
    assert (
        "fix_sha: ec62f12862c4cfc76526eaf99afa0a24249f8288\n"
        "fix_parent_sha: 70f07467be0000000000000000000000000000aa\n"
        "bug_class: framework-internal"
    ) in text


def test_backfill_skips_if_already_present(tmp_path):
    md = tmp_path / "scenario.md"
    md.write_text(_SCENARIO_MD.replace(
        "fix_sha: ec62f128",
        "fix_sha: ec62f128\nfix_parent_sha: deadbeefcafe",
    ))
    with patch("subprocess.run") as mock_run:
        result = backfill_one(md)
    assert result.status == "skipped"
    mock_run.assert_not_called()


def test_backfill_skips_when_no_fix_block(tmp_path):
    md = tmp_path / "scenario.md"
    md.write_text("## User Report\n\nNo fix block here.\n")
    result = backfill_one(md)
    assert result.status == "no_fix_block"


def test_backfill_dry_run_does_not_write(tmp_path):
    md = tmp_path / "scenario.md"
    original = _SCENARIO_MD
    md.write_text(original)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_gh_api_response(["aabbccddeeff"]),
            stderr="",
        )
        result = backfill_one(md, dry_run=True)
    assert result.status == "patched"
    assert md.read_text() == original


def test_backfill_handles_lookup_failure(tmp_path):
    md = tmp_path / "scenario.md"
    md.write_text(_SCENARIO_MD)
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=128, cmd=[], output="", stderr="HTTP 404"
        )
        result = backfill_one(md)
    assert result.status == "lookup_failed"
    # File untouched
    assert md.read_text() == _SCENARIO_MD


def test_backfill_handles_empty_parents(tmp_path):
    md = tmp_path / "scenario.md"
    md.write_text(_SCENARIO_MD)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=_gh_api_response([]),  # initial commit with no parents
            stderr="",
        )
        result = backfill_one(md)
    assert result.status == "lookup_failed"


def test_patch_yaml_body_inserts_in_correct_position():
    yaml_body = (
        "fix_pr_url: https://example.com/pull/1\n"
        "fix_sha: abcdef\n"
        "bug_class: framework-internal\n"
        "files:\n"
        "  - foo.c"
    )
    out = _patch_yaml_body(yaml_body, "deadbeef")
    expected = (
        "fix_pr_url: https://example.com/pull/1\n"
        "fix_sha: abcdef\n"
        "fix_parent_sha: deadbeef\n"
        "bug_class: framework-internal\n"
        "files:\n"
        "  - foo.c"
    )
    assert out == expected


def test_extract_field_handles_url_with_colons():
    yaml_body = (
        "fix_pr_url: https://github.com/o/r/pull/1\n"
        "fix_sha: abc\n"
    )
    assert _extract_field(yaml_body, "fix_pr_url") == "https://github.com/o/r/pull/1"
    assert _extract_field(yaml_body, "fix_sha") == "abc"
    assert _extract_field(yaml_body, "missing") is None
