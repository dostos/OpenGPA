"""``gpa source read|grep`` — harness-local source access.

Operates inside ``$GPA_SOURCE_ROOT``. All paths are validated by
``gpa.cli.local_roots`` before any filesystem access.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable, TextIO

from gpa.cli.local_roots import (
    LocalRoot,
    LocalRootError,
    resolve_relative,
)


_DEFAULT_MAX_BYTES = 200_000
_DEFAULT_MAX_MATCHES = 50
_HARD_MAX_MATCHES = 500
_ENV_NAME = "GPA_SOURCE_ROOT"


def add_subparser(subparsers) -> None:
    p = subparsers.add_parser(
        "source",
        help="Harness-local source access (under $GPA_SOURCE_ROOT)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="source_cmd", required=True)

    p_read = sub.add_parser("read", help="Read a source file as JSON")
    p_read.add_argument("path", help="Path relative to $GPA_SOURCE_ROOT")
    p_read.add_argument(
        "--max-bytes", type=int, default=_DEFAULT_MAX_BYTES,
        help=f"Truncation cap (default {_DEFAULT_MAX_BYTES})",
    )

    p_grep = sub.add_parser("grep", help="Regex search across the source root")
    p_grep.add_argument("pattern", help="Python regex")
    p_grep.add_argument("--subdir", default="", help="Restrict to a subdir")
    p_grep.add_argument("--glob", default="", help="Filename glob, e.g. '*.c'")
    p_grep.add_argument(
        "--max-matches", type=int, default=_DEFAULT_MAX_MATCHES,
        help=f"Cap (default {_DEFAULT_MAX_MATCHES}, hard cap {_HARD_MAX_MATCHES})",
    )


def run_read(
    *, path: str, max_bytes: int,
    print_stream: TextIO = sys.stdout,
    err_stream: TextIO = sys.stderr,
) -> int:
    try:
        root = LocalRoot.from_env(_ENV_NAME)
        target = resolve_relative(root, path)
    except LocalRootError as e:
        print(str(e), file=err_stream)
        return 2
    if not target.is_file():
        print(f"not a file: {path}", file=err_stream)
        return 2
    raw = target.read_bytes()
    truncated = len(raw) > max_bytes
    payload = raw[:max_bytes]
    text = payload.decode("utf-8", errors="replace")
    obj = {
        "path": path,
        "bytes": len(raw),
        "truncated": truncated,
        "text": text,
    }
    print(json.dumps(obj, ensure_ascii=False), file=print_stream)
    return 0


def run_grep(
    *, pattern: str, subdir: str, glob: str, max_matches: int,
    print_stream: TextIO = sys.stdout,
    err_stream: TextIO = sys.stderr,
) -> int:
    try:
        root = LocalRoot.from_env(_ENV_NAME)
        base = resolve_relative(root, subdir) if subdir else root.path
    except LocalRootError as e:
        print(str(e), file=err_stream)
        return 2
    cap = min(max(1, max_matches), _HARD_MAX_MATCHES)
    try:
        regex = re.compile(pattern)
    except re.error as e:
        print(f"bad pattern: {e}", file=err_stream)
        return 2
    matches: list[dict] = []
    truncated = False
    iterator: Iterable[Path] = (
        base.rglob(glob) if glob else base.rglob("*")
    )
    for path in iterator:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                rel = path.relative_to(root.path).as_posix()
                matches.append(
                    {"path": rel, "line": lineno, "text": line[:500]}
                )
                if len(matches) >= cap:
                    truncated = True
                    break
        if truncated:
            break
    obj = {"matches": matches, "truncated": truncated}
    print(json.dumps(obj, ensure_ascii=False), file=print_stream)
    return 0


def run(args: argparse.Namespace) -> int:
    sub = args.source_cmd
    if sub == "read":
        return run_read(path=args.path, max_bytes=args.max_bytes)
    if sub == "grep":
        return run_grep(
            pattern=args.pattern, subdir=args.subdir, glob=args.glob,
            max_matches=args.max_matches,
        )
    raise AssertionError(sub)
