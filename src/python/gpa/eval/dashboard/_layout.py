"""Round directory layout: id parsing, rerun folding, result-file picking."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


# Match `r12c`, `r13`, ..., `r18` (lowercase r + digits + optional letter).
# Also matches `round4` / `round12b` legacy form by alternation. Anchored to
# a `-`/`_` delimiter (or string boundary) on both sides so we don't
# accidentally pick up `iteration5` as `r5` or `dryrun18` as `r18`.
_ROUND_ID_RE = re.compile(r"(?:^|[-_])(?:r|round)(\d+[a-z]?)(?=[-_]|$)")


def extract_round_id(dirname: str) -> Optional[str]:
    """Extract the round id from a /data3/gla-eval-results/<dirname> basename.

    Examples:
      "2026-05-14-r18" -> "r18"
      "2026-05-05-r17-resume" -> "r17" (resume/rerun fold into parent)
      "2026-05-05-iter-r12c-rerun" -> "r12c"
      "2026-05-04-round4-claude-cli" -> "r4"
      "malformed" -> None
    """
    m = _ROUND_ID_RE.search(dirname.lower())
    if not m:
        return None
    return "r" + m.group(1)


def fold_rerun_dirs(root: Path) -> dict[str, list[Path]]:
    """Group round directories under ``root`` by extracted round id.

    Resume/rerun directories collapse into their parent's group. Returns
    a dict keyed by round id; values are sorted Path lists (base dir
    first, resumes/reruns after — lexical order is sufficient given the
    naming convention). Returns empty dict when ``root`` doesn't exist.
    """
    if not root.exists() or not root.is_dir():
        return {}
    grouped: dict[str, list[Path]] = {}
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        rid = extract_round_id(d.name)
        if rid is None:
            continue
        grouped.setdefault(rid, []).append(d)
    return grouped


def pick_result_files(round_dir: Path) -> list[Path]:
    """Return the preferred result-JSON files inside ``round_dir``.

    Priority: per-mode merged > per-mode full > legacy ``results.json``.
    A round can have multiple files when both ``code_only`` and
    ``with_gla`` ran; both are returned. Merged variants supersede
    their non-merged counterpart for the same mode.
    """
    files = {p.name: p for p in round_dir.iterdir() if p.is_file()}
    picked: list[Path] = []
    for mode in ("code_only", "with_gla"):
        merged = files.get(f"{mode}_merged.json")
        full = files.get(f"{mode}.json")
        if merged is not None:
            picked.append(merged)
        elif full is not None:
            picked.append(full)
    if picked:
        return picked
    legacy = files.get("results.json")
    return [legacy] if legacy is not None else []


_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def extract_date(dirname: str) -> Optional[str]:
    """Extract the ISO date prefix from a round directory basename."""
    m = _DATE_RE.match(dirname)
    return m.group(1) if m else None
