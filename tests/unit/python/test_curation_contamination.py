"""Unit tests for the validator's contamination checker.

A contaminated scenario leaks its diagnosis to the eval agent — either via
hint comments in source files, via runtime-output strings that announce
the bug, or via a scenario.md `## User Report` section that states the
root cause instead of describing symptoms.
"""
import re
from pathlib import Path

import pytest

from bhdr.eval.curation.validate import check_contamination


GOOD_MAIN_C = """\
// SOURCE: https://github.com/example/repo/issues/1
#include <GL/gl.h>

int main(void) {
    glClearColor(1.0f, 0.0f, 0.0f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    return 0;
}
"""

GOOD_SCENARIO_MD = """\
# E1: Example

## User Report
Two quads render on screen — the left one should be red, the right one blue.
Both come out red instead. No console errors. Textures were uploaded and
both IDs are valid (queried as RGBA8 512x512).

## Expected Correct Output
Left quad red, right quad blue.

## Actual Broken Output
Both quads are red.

## Ground Truth
The second `glBindTexture(GL_TEXTURE_2D, tex_blue)` call is omitted before
drawing the right quad, so the right draw inherits the red texture from
the previous draw.

## Fix
```yaml
fix_pr_url: https://github.com/example/repo/pull/2
fix_sha: deadbeef12345
fix_parent_sha: cafebabe6789
bug_class: framework-internal
files:
  - src/renderer/draw.c
change_summary: Re-bind the correct texture before the second draw.
```

## Difficulty Rating
2/5

## Adversarial Principles
- state-leak-from-previous-draw

## How Beholder Helps
`inspect_drawcall(aspect=textures)` reveals the identical texture_id bound
for both draws.

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


def _write_scenario(tmp_path: Path, main_c: str, scenario_md: str) -> Path:
    d = tmp_path / "e1_example"
    d.mkdir()
    (d / "main.c").write_text(main_c)
    (d / "scenario.md").write_text(scenario_md)
    return d


def test_clean_scenario_passes(tmp_path):
    d = _write_scenario(tmp_path, GOOD_MAIN_C, GOOD_SCENARIO_MD)
    assert check_contamination(d) is None


def test_bug_comment_in_source_rejected(tmp_path):
    dirty = GOOD_MAIN_C.replace(
        "glClearColor(1.0f, 0.0f, 0.0f, 1.0f);",
        "// BUG: should be blue, not red\n    glClearColor(1.0f, 0.0f, 0.0f, 1.0f);",
    )
    d = _write_scenario(tmp_path, dirty, GOOD_SCENARIO_MD)
    reason = check_contamination(d)
    assert reason is not None
    assert "BUG" in reason


def test_intentionally_omitted_comment_rejected(tmp_path):
    dirty = GOOD_MAIN_C.replace(
        "int main(void) {",
        "int main(void) {\n    // intentionally omitted: glEnable(GL_DEPTH_TEST);",
    )
    d = _write_scenario(tmp_path, dirty, GOOD_SCENARIO_MD)
    assert "intentionally" in (check_contamination(d) or "")


def test_arrow_missing_comment_rejected(tmp_path):
    dirty = GOOD_MAIN_C.replace(
        "glClear(GL_COLOR_BUFFER_BIT);",
        "glClear(GL_COLOR_BUFFER_BIT);  // <-- MISSING depth clear here",
    )
    d = _write_scenario(tmp_path, dirty, GOOD_SCENARIO_MD)
    assert "MISSING" in (check_contamination(d) or "")


def test_runtime_verdict_printf_rejected(tmp_path):
    dirty = GOOD_MAIN_C.replace(
        "return 0;",
        'printf("verdict: %s\\n", ok ? "clean" : "bug reproduced");\n    return 0;',
    )
    d = _write_scenario(tmp_path, dirty, GOOD_SCENARIO_MD)
    reason = check_contamination(d)
    assert reason is not None
    assert "runtime-output leak" in reason or "verdict" in reason


def test_shader_file_hint_rejected(tmp_path):
    d = _write_scenario(tmp_path, GOOD_MAIN_C, GOOD_SCENARIO_MD)
    (d / "frag.glsl").write_text(
        "#version 330\n"
        "// BUG: alpha is hardcoded to 1.0 — should be the sample alpha\n"
        "void main() { gl_FragColor = vec4(1,0,0,1); }\n"
    )
    assert "BUG" in (check_contamination(d) or "")


def test_missing_user_report_section_rejected(tmp_path):
    no_user_report = GOOD_SCENARIO_MD.replace("## User Report\n", "## Bug\n")
    d = _write_scenario(tmp_path, GOOD_MAIN_C, no_user_report)
    assert "User Report" in (check_contamination(d) or "")


def test_missing_ground_truth_section_rejected(tmp_path):
    no_gt = GOOD_SCENARIO_MD.replace(
        "## Ground Truth\n", "## Ground Truth Diagnosis\n"
    )
    d = _write_scenario(tmp_path, GOOD_MAIN_C, no_gt)
    assert "Ground Truth" in (check_contamination(d) or "")


def test_user_report_may_carry_reporter_hypothesis(tmp_path):
    """Real GitHub issue reporters often guess the cause in their own words.
    That is NOT contamination — the agent sees what a real debugger would.
    """
    reporter_guess = GOOD_SCENARIO_MD.replace(
        "Both come out red instead.",
        "Both come out red instead. I think the bug is a missing bind, "
        "but not sure.",
    )
    d = _write_scenario(tmp_path, GOOD_MAIN_C, reporter_guess)
    assert check_contamination(d) is None


def test_neutral_what_comments_are_allowed(tmp_path):
    ok = GOOD_MAIN_C.replace(
        "glClear(GL_COLOR_BUFFER_BIT);",
        "// upload vertex data for the quad\n    glClear(GL_COLOR_BUFFER_BIT);",
    )
    d = _write_scenario(tmp_path, ok, GOOD_SCENARIO_MD)
    assert check_contamination(d) is None


# --- `## Fix` section validation (maintainer-framing spec, Phase 1) ------


def test_validator_rejects_missing_fix_section(tmp_path):
    """A new draft without a `## Fix` heading is rejected."""
    no_fix = re.sub(
        r"\n## Fix\n```yaml\n.*?\n```\n", "\n", GOOD_SCENARIO_MD, flags=re.DOTALL
    )
    # Sanity: our regex actually removed the section.
    assert "## Fix" not in no_fix
    d = _write_scenario(tmp_path, GOOD_MAIN_C, no_fix)
    reason = check_contamination(d)
    assert reason is not None
    assert "missing_fix_section" in reason


def test_validator_rejects_fix_without_files(tmp_path):
    """`## Fix` with an empty files list and non-legacy bug_class is rejected."""
    empty_files = GOOD_SCENARIO_MD.replace(
        "files:\n  - src/renderer/draw.c",
        "files: []",
    )
    d = _write_scenario(tmp_path, GOOD_MAIN_C, empty_files)
    reason = check_contamination(d)
    assert reason is not None
    assert "fix_section_files_empty" in reason


def test_validator_accepts_legacy_bug_class(tmp_path):
    """`bug_class: legacy` with `files: []` is the retrofit escape hatch."""
    legacy = GOOD_SCENARIO_MD.replace(
        "bug_class: framework-internal\nfiles:\n  - src/renderer/draw.c",
        "bug_class: legacy\nfiles: []",
    )
    d = _write_scenario(tmp_path, GOOD_MAIN_C, legacy)
    assert check_contamination(d) is None


def test_validator_accepts_framework_internal_with_files(tmp_path):
    """The default `GOOD_SCENARIO_MD` (framework-internal + 1 file) passes."""
    d = _write_scenario(tmp_path, GOOD_MAIN_C, GOOD_SCENARIO_MD)
    assert check_contamination(d) is None


def test_validator_rejects_fix_section_without_yaml_block(tmp_path):
    """A `## Fix` heading with only prose and no yaml fence is rejected."""
    prose_only = re.sub(
        r"## Fix\n```yaml\n.*?\n```\n",
        "## Fix\nJust some prose without any yaml block whatsoever.\n",
        GOOD_SCENARIO_MD,
        flags=re.DOTALL,
    )
    d = _write_scenario(tmp_path, GOOD_MAIN_C, prose_only)
    reason = check_contamination(d)
    assert reason is not None
    assert "missing_yaml_block" in reason


def test_validator_rejects_invalid_bug_class(tmp_path):
    """A bug_class that isn't in the controlled vocabulary is rejected."""
    invalid = GOOD_SCENARIO_MD.replace(
        "bug_class: framework-internal", "bug_class: totally-made-up"
    )
    d = _write_scenario(tmp_path, GOOD_MAIN_C, invalid)
    reason = check_contamination(d)
    assert reason is not None
    assert "invalid_bug_class" in reason


def test_validator_rejects_fix_missing_pr_url(tmp_path):
    """A fix block that omits fix_pr_url is rejected."""
    no_url = re.sub(
        r"fix_pr_url: [^\n]+\n", "", GOOD_SCENARIO_MD
    )
    assert "fix_pr_url" not in no_url
    d = _write_scenario(tmp_path, GOOD_MAIN_C, no_url)
    reason = check_contamination(d)
    assert reason is not None
    assert "missing_fix_pr_url" in reason


def test_validator_rejects_fix_missing_bug_class(tmp_path):
    """A fix block that omits bug_class is rejected."""
    no_class = re.sub(
        r"bug_class: [^\n]+\n", "", GOOD_SCENARIO_MD
    )
    assert "bug_class" not in no_class
    d = _write_scenario(tmp_path, GOOD_MAIN_C, no_class)
    reason = check_contamination(d)
    assert reason is not None
    assert "missing_bug_class" in reason


