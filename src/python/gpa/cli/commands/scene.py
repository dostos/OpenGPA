"""``gpa scene`` — scene-graph inspection namespace.

Subverbs:
    gpa scene get     [--frame N]                           — full scene JSON
    gpa scene camera  [--frame N]                           — camera params
    gpa scene objects [--frame N] [--limit N] [--offset N]  — scene objects
    gpa scene find    [--frame N] --predicate STRING [--limit N]
    gpa scene explain [--frame N] --x N --y N               — pixel→draw→node

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
from urllib.parse import urlencode

from gpa.cli.frame_resolver import resolve_frame
from gpa.cli.rest_client import RestClient, RestError
from gpa.cli.session import Session


# --------------------------------------------------------------------------- #
# Subparser registration
# --------------------------------------------------------------------------- #


def add_subparser(subparsers) -> None:
    """Register ``scene`` (and its subverbs) on the parent CLI subparsers."""
    p = subparsers.add_parser(
        "scene",
        help="Scene-graph inspection (get, camera, objects, find, explain)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  gpa scene get                                   # full scene, latest frame\n"
            "  gpa scene camera --frame 5                      # camera for frame 5\n"
            "  gpa scene objects --limit 20 --offset 0         # first 20 objects\n"
            "  gpa scene find --predicate material:transparent  # predicate search\n"
            "  gpa scene explain --x 200 --y 150               # pixel→draw→node trace\n"
        ),
    )
    p.add_argument(
        "--session",
        dest="session",
        type=Path,
        default=None,
        help="Session directory (overrides $GPA_SESSION and the current-session link)",
    )

    sub = p.add_subparsers(dest="scene_cmd", required=True)

    # ---- get ----
    p_get = sub.add_parser("get", help="Full scene data from Tier 3 metadata (JSON)")
    p_get.add_argument("--frame", default=None,
                       help="Frame id (default: GPA_FRAME_ID env or latest)")

    # ---- camera ----
    p_camera = sub.add_parser("camera", help="Camera parameters (JSON)")
    p_camera.add_argument("--frame", default=None,
                          help="Frame id (default: GPA_FRAME_ID env or latest)")

    # ---- objects ----
    p_objects = sub.add_parser("objects", help="Scene objects list (JSON)")
    p_objects.add_argument("--frame", default=None,
                           help="Frame id (default: GPA_FRAME_ID env or latest)")
    p_objects.add_argument("--limit", type=int, default=None,
                           help="Maximum number of objects to return")
    p_objects.add_argument("--offset", type=int, default=None,
                           help="Offset into the objects list")

    # ---- find ----
    p_find = sub.add_parser("find", help="Predicate-driven scene-graph search (JSON)")
    p_find.add_argument("--frame", default=None,
                        help="Frame id (default: GPA_FRAME_ID env or latest)")
    p_find.add_argument("--predicate", required=True,
                        help="Comma-separated predicate(s) (e.g. material:transparent)")
    p_find.add_argument("--limit", type=int, default=10,
                        help="Maximum matches to return (default 10)")

    # ---- explain ----
    p_explain = sub.add_parser("explain", help="Pixel→draw→node trace (JSON)")
    p_explain.add_argument("--frame", default=None,
                           help="Frame id (default: GPA_FRAME_ID env or latest)")
    p_explain.add_argument("--x", type=int, required=True,
                           help="Pixel x coordinate")
    p_explain.add_argument("--y", type=int, required=True,
                           help="Pixel y coordinate")


# --------------------------------------------------------------------------- #
# Session / client helper
# --------------------------------------------------------------------------- #


_INJECTED_SENTINEL = object()


def _get_session_and_client(
    session_dir: Optional[Path],
    client: Optional[RestClient],
) -> tuple:
    """Resolve session and build client. Returns (session, client) or (None, None) on error.

    If a client is already injected (e.g., in tests), skip session discovery.
    """
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


def run_get(
    *,
    session_dir: Optional[Path] = None,
    client: Optional[RestClient] = None,
    print_stream=None,
    frame: Optional[str] = None,
) -> int:
    """Implement ``gpa scene get``."""
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
        data = client.get_json(f"/api/v1/frames/{fid}/scene")
    except RestError as exc:
        print(f"[gpa] {exc}", file=sys.stderr)
        return 1

    _print_json(data, print_stream)
    return 0


def run_camera(
    *,
    session_dir: Optional[Path] = None,
    client: Optional[RestClient] = None,
    print_stream=None,
    frame: Optional[str] = None,
) -> int:
    """Implement ``gpa scene camera``."""
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
        data = client.get_json(f"/api/v1/frames/{fid}/scene/camera")
    except RestError as exc:
        print(f"[gpa] {exc}", file=sys.stderr)
        return 1

    _print_json(data, print_stream)
    return 0


def run_objects(
    *,
    session_dir: Optional[Path] = None,
    client: Optional[RestClient] = None,
    print_stream=None,
    frame: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> int:
    """Implement ``gpa scene objects [--limit N] [--offset N]``."""
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

    params: dict = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset

    base_path = f"/api/v1/frames/{fid}/scene/objects"
    path = f"{base_path}?{urlencode(params)}" if params else base_path

    try:
        data = client.get_json(path)
    except RestError as exc:
        print(f"[gpa] {exc}", file=sys.stderr)
        return 1

    _print_json(data, print_stream)
    return 0


def run_find(
    *,
    session_dir: Optional[Path] = None,
    client: Optional[RestClient] = None,
    print_stream=None,
    frame: Optional[str] = None,
    predicate: str,
    limit: int = 10,
) -> int:
    """Implement ``gpa scene find --predicate STRING [--limit N]``."""
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

    qs = urlencode({"predicate": predicate, "limit": limit})
    path = f"/api/v1/frames/{fid}/scene/find?{qs}"

    try:
        data = client.get_json(path)
    except RestError as exc:
        print(f"[gpa] {exc}", file=sys.stderr)
        return 1

    _print_json(data, print_stream)
    return 0


def run_explain(
    *,
    session_dir: Optional[Path] = None,
    client: Optional[RestClient] = None,
    print_stream=None,
    frame: Optional[str] = None,
    x: int,
    y: int,
) -> int:
    """Implement ``gpa scene explain --x N --y N``."""
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
        data = client.get_json(f"/api/v1/frames/{fid}/explain-pixel?x={x}&y={y}")
    except RestError as exc:
        print(f"[gpa] {exc}", file=sys.stderr)
        return 1

    _print_json(data, print_stream)
    return 0


# --------------------------------------------------------------------------- #
# Top-level dispatcher (args-based)
# --------------------------------------------------------------------------- #


def run(args, *, client: Optional[RestClient] = None, print_stream=None) -> int:
    """Dispatch ``scene`` subverbs from parsed ``args``."""
    session_dir: Optional[Path] = getattr(args, "session", None)
    scene_cmd = getattr(args, "scene_cmd", None)

    common = dict(session_dir=session_dir, client=client, print_stream=print_stream)

    if scene_cmd == "get":
        return run_get(**common, frame=getattr(args, "frame", None))

    if scene_cmd == "camera":
        return run_camera(**common, frame=getattr(args, "frame", None))

    if scene_cmd == "objects":
        return run_objects(
            **common,
            frame=getattr(args, "frame", None),
            limit=getattr(args, "limit", None),
            offset=getattr(args, "offset", None),
        )

    if scene_cmd == "find":
        return run_find(
            **common,
            frame=getattr(args, "frame", None),
            predicate=args.predicate,
            limit=getattr(args, "limit", 10),
        )

    if scene_cmd == "explain":
        return run_explain(**common, frame=getattr(args, "frame", None),
                           x=args.x, y=args.y)

    # Should not be reached since argparse validates required=True.
    print(f"[gpa] unknown scene subcommand: {scene_cmd!r}", file=sys.stderr)
    return 1
