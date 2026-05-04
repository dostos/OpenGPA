"""Rank `fix.files` by diff size + Jasmine Spec.js filter (P1-5).

R12 audit found two collateral problems with `expected_files`:

1. Jasmine `*Spec.js` test files survived the existing filter because
   it checks lowercased `.spec.` (with leading dot) while Cesium's
   convention is `Specs/Renderer/BufferSpec.js` — no leading dot, no
   lowercase `tests/` segment. These polluted ground truth and tanked
   file-level recall.
2. Godot fix-PRs touch header+impl pairs, shader-include sweeps, and
   refactor collateral. The bug-causing file is 1 of 13–22; an
   unranked filter weights all of them equally so the agent's correct
   single-file diagnosis scores 1/13 instead of 1/1 against a more
   focused ground-truth set.

Two changes land:

- `_filter_source_files` drops `Specs/` segments and `*Spec.js` /
  `*Spec.ts` basenames (case-insensitive).
- `_filter_and_rank_source_files(items, top_n=5)` ranks dict entries
  by `additions+deletions` desc and caps at `top_n` — unless the PR
  has ≤3 files, in which case all are kept.

`extract_draft` consumes `fix_pr["files_meta"]` when present (preferred
path), falling back to `fix_pr["files_changed"]` (string list, no
ranking) for backward compatibility with hand-built test fixtures.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# _filter_source_files: Jasmine Spec / Specs/ exclusions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "packages/engine/Specs/Renderer/BufferSpec.js",
        "packages/engine/Specs/Scene/PickingSpec.js",
        "packages/widgets/Specs/Foo.js",  # Specs segment alone
        "Specs/integration/Smoke.js",     # leading Specs segment
        "packages/engine/Specs/SpecRunner.js",
    ],
)
def test_jasmine_specs_dropped(path):
    from gpa.eval.curation.extract_draft import _filter_source_files
    assert _filter_source_files([path, "src/keep.js"]) == ["src/keep.js"]


@pytest.mark.parametrize(
    "path",
    [
        "packages/engine/Source/Renderer/BufferSpec.js",  # CamelCase basename
        "packages/engine/Source/Renderer/PickingSpec.ts",
    ],
)
def test_jasmine_basename_dropped_outside_specs_dir(path):
    """Even when the Jasmine spec lives outside a Specs/ directory, the
    `*Spec.js`/`*Spec.ts` basename pattern still drops it."""
    from gpa.eval.curation.extract_draft import _filter_source_files
    assert _filter_source_files([path, "src/keep.js"]) == ["src/keep.js"]


def test_filter_keeps_real_source_alongside_specs():
    """Mixed input — only the spec entries dropped."""
    from gpa.eval.curation.extract_draft import _filter_source_files
    files = [
        "packages/engine/Source/Scene/Picking.js",   # keep
        "packages/engine/Specs/Scene/PickingSpec.js",  # drop
        "packages/engine/Source/Renderer/Context.js",  # keep
        "packages/engine/Specs/Renderer/ContextSpec.js",  # drop
    ]
    out = _filter_source_files(files)
    assert out == [
        "packages/engine/Source/Scene/Picking.js",
        "packages/engine/Source/Renderer/Context.js",
    ]


def test_existing_test_filter_still_works():
    """Regression guard: the lowercase `*.test.*` / `_test.*` /
    `test_*` patterns the filter already supported must keep working."""
    from gpa.eval.curation.extract_draft import _filter_source_files
    out = _filter_source_files([
        "src/foo.ts",
        "src/foo.test.ts",
        "src/foo_test.go",
        "tests/integration/bar.py",
    ])
    assert out == ["src/foo.ts"]


# ---------------------------------------------------------------------------
# _filter_and_rank_source_files: rank + cap
# ---------------------------------------------------------------------------


def test_rank_by_diff_size_descending():
    from gpa.eval.curation.extract_draft import _filter_and_rank_source_files
    items = [
        {"filename": "src/small.ts",  "additions": 1,   "deletions": 0},
        {"filename": "src/big.ts",    "additions": 200, "deletions": 50},
        {"filename": "src/medium.ts", "additions": 30,  "deletions": 5},
    ]
    out = _filter_and_rank_source_files(items, top_n=5)
    assert out == ["src/big.ts", "src/medium.ts", "src/small.ts"]


def test_cap_at_top_n_when_many_files():
    from gpa.eval.curation.extract_draft import _filter_and_rank_source_files
    items = [
        {"filename": f"src/file{i:02d}.ts", "additions": 100 - i, "deletions": 0}
        for i in range(13)
    ]
    out = _filter_and_rank_source_files(items, top_n=5)
    assert out == [
        "src/file00.ts", "src/file01.ts", "src/file02.ts",
        "src/file03.ts", "src/file04.ts",
    ]


def test_keep_all_when_pr_has_three_or_fewer_files():
    """Small PRs are unlikely to contain refactor collateral — keep
    every entry rather than imposing the top-N cap."""
    from gpa.eval.curation.extract_draft import _filter_and_rank_source_files
    items = [
        {"filename": "src/a.ts", "additions": 5,  "deletions": 0},
        {"filename": "src/b.ts", "additions": 50, "deletions": 5},
        {"filename": "src/c.ts", "additions": 1,  "deletions": 0},
    ]
    out = _filter_and_rank_source_files(items, top_n=5)
    # Sorted but all 3 kept
    assert out == ["src/b.ts", "src/a.ts", "src/c.ts"]


def test_filter_drops_non_source_then_ranks():
    """Filter happens before ranking — Specs/ entries don't get top
    spots even if they have huge diffs."""
    from gpa.eval.curation.extract_draft import _filter_and_rank_source_files
    items = [
        {"filename": "Specs/Big.js",     "additions": 999, "deletions": 0},
        {"filename": "src/keep.ts",      "additions": 5,   "deletions": 1},
        {"filename": "tests/keep.ts",    "additions": 99,  "deletions": 0},
        {"filename": "src/another.ts",   "additions": 50,  "deletions": 5},
    ]
    out = _filter_and_rank_source_files(items, top_n=5)
    assert out == ["src/another.ts", "src/keep.ts"]


def test_zero_diff_files_kept_at_bottom():
    """Files with zero diff (e.g. binary changes that GitHub doesn't
    expose) must still be kept — they sort last but aren't dropped."""
    from gpa.eval.curation.extract_draft import _filter_and_rank_source_files
    items = [
        {"filename": "src/a.ts", "additions": 10, "deletions": 0},
        {"filename": "src/b.ts"},  # no additions/deletions key
    ]
    out = _filter_and_rank_source_files(items, top_n=5)
    assert "src/a.ts" in out
    assert "src/b.ts" in out
    assert out[0] == "src/a.ts"


def test_filter_and_rank_empty_input():
    from gpa.eval.curation.extract_draft import _filter_and_rank_source_files
    assert _filter_and_rank_source_files([], top_n=5) == []


# ---------------------------------------------------------------------------
# extract_draft consumption: files_meta wins when present
# ---------------------------------------------------------------------------


def _make_thread_dict():
    return {
        "url": "https://github.com/o/r/issues/1",
        "title": "T",
        "body": "## Expected\nworks\n## Actual\nbreaks",
        "comments": [],
    }


def test_extract_draft_prefers_files_meta(monkeypatch):
    from gpa.eval.curation.extract_draft import extract_draft
    fix_pr = {
        "url": "https://github.com/o/r/pull/2",
        "commit_sha": "abc1234",
        "files_meta": [
            {"filename": "src/big.ts",    "additions": 200, "deletions": 0},
            {"filename": "src/small.ts",  "additions": 5,   "deletions": 0},
            *[
                {"filename": f"src/extra{i:02d}.ts",
                 "additions": 200 - i, "deletions": 0}
                for i in range(10)
            ],
        ],
        # files_changed left for back-compat — extract_draft must ignore it
        # when files_meta is present.
        "files_changed": ["src/should_not_appear.ts"],
    }
    draft = extract_draft(
        thread=_make_thread_dict(), fix_pr=fix_pr,
        taxonomy_cell="framework-maintenance.web-3d.three.js",
    )
    assert "src/should_not_appear.ts" not in draft.expected_files
    assert "src/big.ts" in draft.expected_files
    assert len(draft.expected_files) == 5  # capped at top-5 (12 inputs)


def test_extract_draft_falls_back_to_files_changed():
    """Hand-built test fixtures + back-compat: when no files_meta is
    provided, extract_draft uses the legacy filename list path."""
    from gpa.eval.curation.extract_draft import extract_draft
    fix_pr = {
        "url": "https://github.com/o/r/pull/2",
        "commit_sha": "abc1234",
        "files_changed": ["src/foo.ts", "tests/bar.ts"],
    }
    draft = extract_draft(
        thread=_make_thread_dict(), fix_pr=fix_pr,
        taxonomy_cell="framework-maintenance.web-3d.three.js",
    )
    assert draft.expected_files == ["src/foo.ts"]
