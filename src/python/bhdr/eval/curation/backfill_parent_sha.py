"""Backfill ``fix_parent_sha`` into scenario.md fix blocks.

Older mined scenarios were committed before the curation pipeline
fetched the merge-commit's parent. Without ``fix_parent_sha`` the
upstream snapshot defaults to ``fix_sha`` — i.e. the *post-fix* state —
so agents investigate already-fixed code and the eval is meaningless.

Usage:
    python -m bhdr.eval.curation.backfill_parent_sha tests/eval [--dry-run]

Walks every ``scenario.md`` under the given root, parses the fix block,
and for any entry that has ``fix_pr_url`` + ``fix_sha`` but no
``fix_parent_sha``, calls ``gh api repos/<o>/<r>/commits/<fix_sha>`` and
inserts ``fix_parent_sha: <parents[0].sha>`` into the YAML block. Files
without a fix block are skipped.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_LOG = logging.getLogger(__name__)

_FIX_BLOCK_RE = re.compile(
    r"(```yaml\s*\n)"           # opening fence
    r"(.*?)"                    # YAML body (group 2)
    r"(\n```)",                 # closing fence
    re.DOTALL,
)
_REPO_RE = re.compile(r"github\.com/([^/]+)/([^/]+)/")


@dataclass
class BackfillResult:
    path: Path
    status: str           # "patched" | "skipped" | "no_fix_block" | "lookup_failed"
    detail: str = ""


def _extract_field(yaml_body: str, key: str) -> Optional[str]:
    m = re.search(rf"^{re.escape(key)}\s*:\s*(\S.*?)\s*$", yaml_body, re.MULTILINE)
    return m.group(1).strip() if m else None


def _resolve_parent_sha(fix_pr_url: str, fix_sha: str) -> Optional[str]:
    repo_m = _REPO_RE.search(fix_pr_url)
    if not repo_m:
        return None
    owner, repo = repo_m.group(1), repo_m.group(2)
    try:
        proc = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/commits/{fix_sha}"],
            capture_output=True, text=True, check=True, timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    try:
        commit = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    parents = commit.get("parents") or []
    return (parents[0].get("sha") or None) if parents else None


def _patch_yaml_body(yaml_body: str, parent_sha: str) -> str:
    """Insert ``fix_parent_sha: <sha>`` immediately after the ``fix_sha:`` line."""
    lines = yaml_body.split("\n")
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and re.match(r"\s*fix_sha\s*:", line):
            out.append(f"fix_parent_sha: {parent_sha}")
            inserted = True
    return "\n".join(out)


def backfill_one(path: Path, *, dry_run: bool = False) -> BackfillResult:
    text = path.read_text(encoding="utf-8")
    m = _FIX_BLOCK_RE.search(text)
    if not m:
        return BackfillResult(path, "no_fix_block")
    yaml_body = m.group(2)

    fix_pr_url = _extract_field(yaml_body, "fix_pr_url")
    fix_sha = _extract_field(yaml_body, "fix_sha")
    existing = _extract_field(yaml_body, "fix_parent_sha")

    if existing:
        return BackfillResult(path, "skipped", "already has fix_parent_sha")
    if not fix_pr_url or not fix_sha:
        return BackfillResult(path, "skipped", "fix block lacks fix_pr_url/fix_sha")

    parent_sha = _resolve_parent_sha(fix_pr_url, fix_sha)
    if not parent_sha:
        return BackfillResult(path, "lookup_failed", f"no parent for {fix_sha}")

    new_yaml = _patch_yaml_body(yaml_body, parent_sha)
    new_text = text[: m.start(2)] + new_yaml + text[m.end(2):]

    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return BackfillResult(path, "patched", parent_sha)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill fix_parent_sha into scenario.md fix blocks.",
    )
    parser.add_argument("root", type=Path,
                        help="Root directory to walk (typically tests/eval)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report changes without writing files")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    if not args.root.is_dir():
        print(f"ERROR: not a directory: {args.root}", file=sys.stderr)
        return 2

    counts = {"patched": 0, "skipped": 0, "no_fix_block": 0, "lookup_failed": 0}
    for md in sorted(args.root.rglob("scenario.md")):
        result = backfill_one(md, dry_run=args.dry_run)
        counts[result.status] += 1
        if result.status in ("patched", "lookup_failed"):
            print(f"{result.status:14s} {result.path}: {result.detail}")

    verb = "would patch" if args.dry_run else "patched"
    print(f"\n{verb}: {counts['patched']}")
    print(f"already had fix_parent_sha: {counts['skipped']}")
    print(f"no fix block: {counts['no_fix_block']}")
    print(f"lookup failed: {counts['lookup_failed']}")
    return 0 if counts["lookup_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
