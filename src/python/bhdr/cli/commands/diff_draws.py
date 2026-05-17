"""``gpa diff-draws A B`` — return state/uniform/texture deltas between two draws.

Single tool call answer to "what's different between these two draw calls
inside one frame?". Replaces "dump A, dump B, eyeball-diff".
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from bhdr.cli.rest_client import RestClient, RestError
from bhdr.cli.session import Session


_VALID_SCOPES = ("state", "uniforms", "textures", "all")


def add_subparser(subparsers) -> None:
    epilog = (
        "Examples:\n"
        "  gpa diff-draws 4 5                              # 1) state delta (default)\n"
        "  gpa diff-draws 4 5 --scope uniforms             # 2) uniform delta\n"
        "  gpa diff-draws 4 5 --scope all --json           # 3) full JSON\n"
        "  gpa diff-draws 4 5 --frame 7                    # 4) specific frame\n"
        "  gpa scene-find uniform-has-nan --json \\\n"
        "    | jq -r '.matches[].draw_call_ids[]' \\\n"
        "    | xargs -I% gpa diff-draws 0 %                # 5) pipeline\n"
    )
    p = subparsers.add_parser(
        "diff-draws",
        help="Show state/uniform/texture delta between two draw calls",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )
    p.add_argument("a", type=int, help="First draw-call id")
    p.add_argument("b", type=int, help="Second draw-call id")
    p.add_argument(
        "--session", dest="session", type=Path, default=None,
        help="Session directory (overrides $BHDR_SESSION and the link)",
    )
    p.add_argument(
        "--frame", dest="frame", default=None,
        help="Frame id (default: latest).",
    )
    p.add_argument(
        "--scope", default="state",
        choices=_VALID_SCOPES,
        help="What to diff. Default: state.",
    )
    p.add_argument(
        "--json", dest="json_output", action="store_true",
        help="Emit machine-readable JSON instead of plain text",
    )


def _format_human(payload: Dict[str, Any]) -> str:
    lines: List[str] = []
    fid = payload.get("frame_id")
    a = payload.get("a")
    b = payload.get("b")
    a_node = payload.get("a_node") or "(no scene context)"
    b_node = payload.get("b_node") or "(no scene context)"
    scope = payload.get("scope")
    lines.append(
        f"diff-draws frame {fid}  A={a} ({a_node})  B={b} ({b_node})  "
        f"scope={scope}"
    )
    changes = payload.get("changes") or []
    if not changes:
        lines.append(f"(no differences at scope '{scope}')")
        return "\n".join(lines) + "\n"
    lines.append("changes A → B")
    for c in changes:
        key = c.get("key")
        va = c.get("a")
        vb = c.get("b")
        lines.append(f"  {key:<20s}  {va!r} → {vb!r}")
    if payload.get("truncated"):
        lines.append("  … (output truncated; pass --json for full list)")
    return "\n".join(lines) + "\n"


def run(
    *,
    a: int,
    b: int,
    session_dir: Optional[Path] = None,
    frame: Optional[str] = None,
    scope: str = "state",
    json_output: bool = False,
    client: Optional[RestClient] = None,
    print_stream=None,
) -> int:
    if print_stream is None:
        print_stream = sys.stdout

    if scope not in _VALID_SCOPES:
        print(
            f"Error: unknown scope {scope!r}. Allowed: {list(_VALID_SCOPES)}\n"
            "  gpa diff-draws 4 5 --scope state",
            file=sys.stderr,
        )
        return 2

    if frame is not None:
        try:
            int(frame)
        except ValueError:
            print(
                f"Error: --frame must be an integer, got {frame!r}.\n"
                "  gpa diff-draws 4 5 --frame 7",
                file=sys.stderr,
            )
            return 2

    sess = Session.discover(explicit=session_dir)
    if sess is None:
        print(
            "Error: no active GPA session. Run 'gpa start' first.",
            file=sys.stderr,
        )
        return 2

    if client is None:
        try:
            client = RestClient.from_session(sess)
        except Exception as exc:  # noqa: BLE001
            print(f"[gpa] failed to connect to engine: {exc}", file=sys.stderr)
            return 1

    fid_part = "latest" if frame is None else int(frame)
    path = f"/api/v1/frames/{fid_part}/draws/diff?a={int(a)}&b={int(b)}&scope={scope}"
    try:
        payload = client.get_json(path)
    except RestError as exc:
        if exc.status == 404:
            print(
                f"[gpa] one of draws {a},{b} not found in frame "
                f"{fid_part}.\n  Example: gpa diff-draws 4 5",
                file=sys.stderr,
            )
            return 1
        print(f"[gpa] {exc}", file=sys.stderr)
        return 1

    if not isinstance(payload, dict):
        print(f"[gpa] unexpected response shape: {type(payload).__name__}",
              file=sys.stderr)
        return 1

    if json_output:
        print_stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    else:
        print_stream.write(_format_human(payload))
    print_stream.flush()
    # Empty diff is exit 0 (it's a successful "no difference" answer);
    # the spec calls out exit 1 only for missing draws.
    return 0
