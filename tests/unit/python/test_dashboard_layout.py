import pytest

from gpa.eval.dashboard._layout import extract_round_id


@pytest.mark.parametrize("dirname,expected", [
    ("2026-05-14-r18", "r18"),
    ("2026-05-05-r17", "r17"),
    ("2026-05-05-r17-resume", "r17"),
    ("2026-05-05-r16-rerun", "r16"),
    ("2026-05-05-iter-r12c-rerun", "r12c"),
    ("2026-05-05-iter-r12d-json", "r12d"),
    ("2026-05-05-r13-scope-hint", "r13"),
    ("2026-05-04-round4-claude-cli", "r4"),
    ("2026-05-04-round12b-smoke", "r12b"),
    ("2026-05-04-round12b-with-gla", "r12b"),
    ("malformed", None),
])
def test_extract_round_id(dirname, expected):
    assert extract_round_id(dirname) == expected


from gpa.eval.dashboard._layout import fold_rerun_dirs


def test_fold_rerun_dirs_groups_by_round_id(tmp_path):
    base = tmp_path / "data3"
    base.mkdir()
    for name in ("2026-05-05-r17", "2026-05-05-r17-resume",
                 "2026-05-14-r18", "malformed"):
        (base / name).mkdir()
    folded = fold_rerun_dirs(base)
    assert sorted(folded.keys()) == ["r17", "r18"]
    # r17 group has both dirs, sorted lexicographically (base < resume)
    assert [p.name for p in folded["r17"]] == [
        "2026-05-05-r17", "2026-05-05-r17-resume",
    ]
    assert [p.name for p in folded["r18"]] == ["2026-05-14-r18"]
    # malformed dropped silently — no Exception


def test_fold_rerun_dirs_missing_root_returns_empty(tmp_path):
    assert fold_rerun_dirs(tmp_path / "nope") == {}


from gpa.eval.dashboard._layout import pick_result_files


def test_pick_prefers_merged_over_full(tmp_path):
    (tmp_path / "code_only.json").write_text("[]")
    (tmp_path / "code_only_merged.json").write_text("[]")
    picked = pick_result_files(tmp_path)
    assert [p.name for p in picked] == ["code_only_merged.json"]


def test_pick_returns_both_modes(tmp_path):
    (tmp_path / "code_only.json").write_text("[]")
    (tmp_path / "with_gla.json").write_text("[]")
    picked = pick_result_files(tmp_path)
    assert sorted(p.name for p in picked) == ["code_only.json", "with_gla.json"]


def test_pick_legacy_results_json(tmp_path):
    (tmp_path / "results.json").write_text("[]")
    picked = pick_result_files(tmp_path)
    assert [p.name for p in picked] == ["results.json"]


def test_pick_empty_when_no_match(tmp_path):
    (tmp_path / "garbage.txt").write_text("")
    assert pick_result_files(tmp_path) == []


from gpa.eval.dashboard._layout import extract_date


@pytest.mark.parametrize("dirname,expected", [
    ("2026-05-14-r18", "2026-05-14"),
    ("2026-05-05-r17-resume", "2026-05-05"),
    ("malformed", None),
])
def test_extract_date(dirname, expected):
    assert extract_date(dirname) == expected
