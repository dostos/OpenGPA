from pathlib import Path

from bhdr.eval.dashboard._narrative import find_narrative, extract_headline


def test_find_narrative_by_round_id(tmp_path):
    (tmp_path / "2026-05-14-r18.md").write_text("# R18\n")
    (tmp_path / "2026-05-05-r17.md").write_text("# R17\n")
    (tmp_path / "README.md").write_text("not a round")
    assert find_narrative(tmp_path, "r18").name == "2026-05-14-r18.md"
    assert find_narrative(tmp_path, "r17").name == "2026-05-05-r17.md"
    assert find_narrative(tmp_path, "r99") is None


def test_find_narrative_handles_missing_dir(tmp_path):
    assert find_narrative(tmp_path / "nope", "r1") is None


def test_extract_headline_basic():
    md = (
        "# Round R18 (2026-05-14)\n\n"
        "Three audit-driven changes shipped: expected_failure scenario\n"
        "slot (P0), prompt-rendering consolidation (P1), and...\n\n"
        "## Ran\n"
    )
    assert "Three audit-driven changes" in extract_headline(md)


def test_extract_headline_skips_blockquote_and_lists():
    md = (
        "# Round R12c\n\n"
        "> Pre-amble blockquote.\n\n"
        "- list item one\n"
        "- list item two\n\n"
        "Actual headline paragraph here.\n"
    )
    assert extract_headline(md) == "Actual headline paragraph here."


def test_extract_headline_none_when_no_paragraph():
    md = "# Round R0\n\n## Ran\n\nbody\n"
    assert extract_headline(md) is None
