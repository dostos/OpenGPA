"""``gpa passes`` — render pass inspection namespace.

Subverbs:
    gpa passes list [--frame N]      list render passes for a frame
    gpa passes get NAME [--frame N]  get a single render pass by name

All output is compact JSON (pass-through of the API response).

Exit codes:
    0  success
    1  REST / transport error
    2  no active session found
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from gpa.cli.frame_resolver import resolve_frame
from gpa.cli.rest_client import RestClient, RestError
from gpa.cli.session import Session


# --------------------------------------------------------------------------- #
# Subparser registration
# --------------------------------------------------------------------------- #


def add_subparser(subparsers) -> None:
    """Register ``passes`` (and its subverbs) on the parent CLI subparsers."""
    p = subparsers.add_parser(
        "passes",
        help="Render pass inspection (list, get)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  gpa passes list                   # all passes for current frame\n"
            "  gpa passes list --frame 7         # specific frame\n"
            "  gpa passes get shadows            # single pass by name\n"
            "  gpa passes get shadows --frame 7  # specific frame\n"
        ),
    )
    p.add_argument(
        "--session",
        dest="session",
        type=Path,
        default=None,
        help="Session directory (overrides $GPA_SESSION and the current-session link)",
    )

    sub = p.add_subparsers(dest="passes_cmd", required=True)

    # ---- list ----
    p_list = sub.add_parser("list", help="List render passes for a frame (JSON)")
    p_list.add_argument("--frame", default=None,
                        help="Frame id (default: GPA_FRAME_ID env or latest)")

    # ---- get ----
    p_get = sub.add_parser("get", help="Get a single render pass by name (JSON)")
    p_get.add_argument("name", help="Render pass name")
    p_get.add_argument("--frame", default=None,
                       help="Frame id (default: GPA_FRAME_ID env or latest)")


# --------------------------------------------------------------------------- #
# Session / client helper
# --------------------------------------------------------------------------- #


_INJECTED_SENTINEL = object()


def _get_session_and_client(
    session_dir: Optional[Path],
    client: Optional[RestClient],
) -> tuple:
    """Resolve session and build client. Returns (session, client) or (None, None) on error."""
    if client is not None:
        return _INJECTED_SENTINEL, client
    sess = Session.discover(explicit=session_dir)
    if sess is None:
        return None, None
    try:
        client = RestClient.from_session(sess)
    except Exception as exc:  # noqa: BLE001
        print(f"[gpa] failed to connect to engine: {exc}", file=sys.stderr)
        return sess, None
    return sess, client


# --------------------------------------------------------------------------- #
# Output helper
# --------------------------------------------------------------------------- #


def _print_json(data, print_stream) -> None:
    """Dump data as compact JSON to print_stream."""
    print_stream.write(json.dumps(data) + "\n")
    print_stream.flush()


# --------------------------------------------------------------------------- #
# Subverb implementations (kwargs-only, injectable client)
# --------------------------------------------------------------------------- #


def run_list(
    *,
    session_dir: Optional[Path] = None,
    client: Optional[RestClient] = None,
    print_stream=None,
    frame: Optional[str] = None,
) -> int:
    """Implement ``gpa passes list [--frame N]``."""
    if print_stream is None:
        print_stream = sys.stdout

    sess, client = _get_session_and_client(session_dir, client)
    if sess is None:
        print("[gpa] no active session found", file=sys.stderr)
        return 2
    if client is None:
        return 1

    try:
        fid = resolve_frame(client=client, explicit=frame)
    except Exception as exc:  # noqa: BLE001
        print(f"[gpa] could not resolve frame: {exc}", file=sys.stderr)
        return 1

    try:
        data = client.get_json(f"/api/v1/frames/{fid}/passes")
    except RestError as exc:
        print(f"[gpa] {exc}", file=sys.stderr)
        return 1

    _print_json(data, print_stream)
    return 0


def run_get(
    *,
    session_dir: Optional[Path] = None,
    client: Optional[RestClient] = None,
    print_stream=None,
    frame: Optional[str] = None,
    name: str,
) -> int:
    """Implement ``gpa passes get NAME [--frame N]``."""
    if print_stream is None:
        print_stream = sys.stdout

    sess, client = _get_session_and_client(session_dir, client)
    if sess is None:
        print("[gpa] no active session found", file=sys.stderr)
        return 2
    if client is None:
        return 1

    try:
        fid = resolve_frame(client=client, explicit=frame)
    except Exception as exc:  # noqa: BLE001
        print(f"[gpa] could not resolve frame: {exc}", file=sys.stderr)
        return 1

    try:
        data = client.get_json(f"/api/v1/frames/{fid}/passes/{name}")
    except RestError as exc:
        print(f"[gpa] {exc}", file=sys.stderr)
        return 1

    _print_json(data, print_stream)
    return 0


# --------------------------------------------------------------------------- #
# Top-level dispatcher (args-based)
# --------------------------------------------------------------------------- #


def run(args, *, client: Optional[RestClient] = None, print_stream=None) -> int:
    """Dispatch ``passes`` subverbs from parsed ``args``."""
    session_dir: Optional[Path] = getattr(args, "session", None)
    passes_cmd = getattr(args, "passes_cmd", None)

    common = dict(session_dir=session_dir, client=client, print_stream=print_stream)

    if passes_cmd == "list":
        return run_list(**common, frame=getattr(args, "frame", None))

    if passes_cmd == "get":
        return run_get(**common, frame=getattr(args, "frame", None), name=args.name)

    # Should not be reached since argparse validates required=True.
    print(f"[gpa] unknown passes subcommand: {passes_cmd!r}", file=sys.stderr)
    return 1
