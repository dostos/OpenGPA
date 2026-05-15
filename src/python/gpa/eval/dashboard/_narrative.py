"""Round-log narrative discovery + headline extraction."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


def find_narrative(rounds_dir: Path, round_id: str) -> Optional[Path]:
    """Find ``<rounds_dir>/*-<round_id>.md`` (case-insensitive on id)."""
    if not rounds_dir.exists() or not rounds_dir.is_dir():
        return None
    rid = round_id.lower()
    for p in sorted(rounds_dir.glob("*.md")):
        # Match suffix `-<rid>` before .md, e.g. "2026-05-14-r18.md".
        stem = p.stem.lower()
        if stem.endswith(f"-{rid}"):
            return p
    return None


_H1_RE = re.compile(r"^#\s+Round\s+R\w+", re.IGNORECASE)
_HEADING_RE = re.compile(r"^#{1,6}\s+")
_LIST_RE = re.compile(r"^\s*[-*+]\s+")
_BLOCKQUOTE_RE = re.compile(r"^\s*>")


def extract_headline(markdown_text: str) -> Optional[str]:
    """Return the first prose paragraph under the ``# Round R##`` heading.

    Skips other headings, list items, blockquotes, and blank lines.
    Returns the trimmed single-line paragraph (newlines collapsed to
    spaces) or None if no such paragraph exists.
    """
    lines = markdown_text.splitlines()
    in_h1 = False
    para: list[str] = []
    for line in lines:
        if _H1_RE.match(line):
            in_h1 = True
            continue
        if not in_h1:
            continue
        stripped = line.strip()
        if not stripped:
            if para:
                break
            continue
        if _HEADING_RE.match(line):
            # Any sub-heading ends the search window regardless of para state.
            break
        if _LIST_RE.match(line) or _BLOCKQUOTE_RE.match(line):
            if para:
                break
            continue
        para.append(stripped)
    if not para:
        return None
    return " ".join(para)
