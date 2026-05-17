"""R19-P0: maintainer-prompt depth tiers by fix.files count.

R17→R18 traded +1 solved for 4× tokens because the blanket
"5-15 files / 13-file refactor" depth pitch over-steered single-file
scenarios. The depth section is now sized to the canonical fix's
actual file count via a new ``fix_files_count`` parameter on
:func:`bhdr.eval.prompts.render_prompt`.

Tiers:
  1-2 files → focused single/few-file ("pointed edit")
  3-9 files → moderate refactor (default)
  10+ files → deep cross-module refactor
  0 or None → moderate default (unknown scope)
"""
from __future__ import annotations

import pytest

from bhdr.eval.prompts import render_prompt, _build_depth_section


@pytest.mark.parametrize("n,expected_phrase", [
    (1, "pointed edit"),
    (2, "pointed edit"),
    (3, "render-pass helper"),
    (5, "render-pass helper"),
    (9, "render-pass helper"),
    (10, "10+"),
    (22, "10+"),
    (0, "render-pass helper"),     # unknown → moderate
    (None, "render-pass helper"),  # ditto
])
def test_depth_section_tiers(n, expected_phrase):
    """Smoke-test the boundaries between tiers using a phrase unique to
    each. Phrases are intentionally distinct so a future edit to the
    moderate copy doesn't silently match the single tier and pass the
    test for the wrong reason."""
    assert expected_phrase in _build_depth_section(n)


def test_depth_section_single_tier_advises_against_sprawl():
    """The 1-2 file tier needs to be opinionated against proposing
    many files; otherwise the LLM defaults to the deep-tier behaviour."""
    text = _build_depth_section(1)
    assert "dilute your score" in text.lower() or "1-2 files" in text.lower()


def test_depth_section_deep_tier_keeps_r18_framing():
    """The 10+ tier should preserve the original R18-era language so
    large refactor scenarios don't lose what was working."""
    text = _build_depth_section(13)
    assert "10+" in text
    assert "score you below threshold" in text or "single-file" in text.lower()


def test_render_prompt_accepts_fix_files_count_param():
    """The plumbing (``fix_files_count`` kwarg on render_prompt) is
    retained for any future smaller intervention, even though R19-P0
    reverted the template-side usage (maintainer_framing.md no longer
    contains a ``{depth_section}`` placeholder — see R19 round log).
    Pure-function _build_depth_section is still exercised by the
    parametrized tests above; this test just confirms the kwarg
    doesn't break rendering when passed.
    """
    p_small = render_prompt(
        "maintainer_framing",
        framework="godot",
        user_report="test bug",
        upstream_snapshot_repo="https://github.com/godotengine/godot",
        upstream_snapshot_sha="abc123",
        fix_files_count=1,
    )
    p_large = render_prompt(
        "maintainer_framing",
        framework="godot",
        user_report="test bug",
        upstream_snapshot_repo="https://github.com/godotengine/godot",
        upstream_snapshot_sha="abc123",
        fix_files_count=15,
    )
    # Both must render successfully — no exception, no placeholder leak.
    assert "{depth_section}" not in p_small
    assert "{depth_section}" not in p_large
    # Both should carry the R18 blanket framing ("13-file refactor PRs
    # are normal") since maintainer_framing.md was reverted.
    assert "13-file refactor" in p_small
    assert "13-file refactor" in p_large


def test_render_prompt_default_when_count_omitted():
    """When the caller doesn't pass ``fix_files_count`` the prompt
    still renders the R18 blanket framing — backward-compat."""
    p = render_prompt(
        "maintainer_framing",
        framework="three.js",
        user_report="x",
        upstream_snapshot_repo=None,
        upstream_snapshot_sha=None,
    )
    assert "13-file refactor" in p
    assert "{depth_section}" not in p
