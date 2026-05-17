"""``gpa scene-explain --pixel X,Y`` — pixel-to-scene-node traversal.

Productionises the pixel→draw_call→scene_node chain. Hit-test is by
viewport bounding box (approximate); the JSON output reports
``"resolved":"approximate"`` so callers know the mode.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bhdr.cli.rest_client import RestClient, RestError
from bhdr.cli.session import Session


def add_subparser(subparsers) -> None:
    epilog = (
        "Examples:\n"
        "  gpa scene-explain --pixel 200,150                 # 1) simplest\n"
        "  gpa scene-explain --pixel 200,150 --json          # 2) JSON\n"
        "  gpa scene-explain --pixel 200,150 --frame 7       # 3) specific frame\n"
        "  printf '200,150\\n401,98\\n' \\\n"
        "    | xargs -I% gpa scene-explain --pixel %         # 4) batch via xargs\n"
        "  gpa scene-explain --pixel 0,0 --frame latest      # 5) corner pixel\n"
    )
    p = subparsers.add_parser(
        "scene-explain",
        help="Pixel → draw_call → scene_node traversal (one tool call)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )
    p.add_argument(
        "--pixel", dest="pixel", required=True,
        help="X,Y coordinates in viewport space (comma-separated)",
    )
    p.add_argument(
        "--session", dest="session", type=Path, default=None,
        help="Session directory (overrides $BHDR_SESSION and the link)",
    )
    p.add_argument(
        "--frame", dest="frame", default=None,
        help="Frame id (default: latest).",
    )
    p.add_argument(
        "--json", dest="json_output", action="store_true",
        help="Emit machine-readable JSON instead of plain text",
    )


def _parse_pixel(arg: str) -> Optional[Tuple[int, int]]:
    if "," not in arg:
        return None
    pieces = arg.split(",", 1)
    try:
        return int(pieces[0].strip()), int(pieces[1].strip())
    except ValueError:
        return None


def _format_human(payload: Dict[str, Any]) -> str:
    lines: List[str] = []
    fid = payload.get("frame_id")
    px = payload.get("pixel") or [0, 0]
    lines.append(f"scene-explain frame {fid}  pixel ({px[0]},{px[1]})")
    pv = payload.get("pixel_value")
    if pv is not None:
        lines.append(
            f"  rgba=({pv.get('r')},{pv.get('g')},{pv.get('b')},{pv.get('a')})"
            f"  depth={pv.get('depth')}"
        )
    did = payload.get("draw_call_id")
    if did is None:
        lines.append("  draw      (no draw covers this pixel)")
        lines.append(f"  resolved  {payload.get('resolved')}")
        return "\n".join(lines) + "\n"
    lines.append(f"  draw      {did}  ({payload.get('resolved')})")
    node = payload.get("scene_node_path") or "(no scene-node link)"
    lines.append(f"  node      {node}")
    if payload.get("material_name"):
        lines.append(f"  material  {payload['material_name']}")
    prog = payload.get("shader_program_id")
    if prog:
        lines.append(f"  shader    program {prog}")
    inputs = payload.get("inputs") or {}
    uniforms = inputs.get("uniforms") or []
    if uniforms:
        joined = "  ".join(_fmt_uniform(u) for u in uniforms)
        lines.append(f"  uniforms  {joined}")
    textures = inputs.get("textures") or []
    if textures:
        for t in textures:
            lines.append(
                f"  textures  unit{t.get('unit')} tex{t.get('tex_id')} "
                f"{t.get('format')}"
            )
    state = payload.get("relevant_state") or {}
    if state:
        kvs = "  ".join(f"{k}={v}" for k, v in sorted(state.items()))
        lines.append(f"  state     {kvs}")
    return "\n".join(lines) + "\n"


def _fmt_uniform(item: Dict[str, Any]) -> str:
    name = item.get("name") or "?"
    val = item.get("value")
    if isinstance(val, (list, tuple)):
        if len(val) > 4:
            head = ",".join(_fmt_num(v) for v in val[:3])
            return f"{name}=[{head},…]"
        return f"{name}=[{','.join(_fmt_num(v) for v in val)}]"
    return f"{name}={_fmt_num(val)}"


def _fmt_num(v) -> str:
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def run(
    *,
    pixel: str,
    session_dir: Optional[Path] = None,
    frame: Optional[str] = None,
    json_output: bool = False,
    client: Optional[RestClient] = None,
    print_stream=None,
) -> int:
    if print_stream is None:
        print_stream = sys.stdout

    coords = _parse_pixel(pixel or "")
    if coords is None:
        print(
            f"Error: --pixel expects X,Y, got {pixel!r}.\n"
            "  gpa scene-explain --pixel 200,150",
            file=sys.stderr,
        )
        return 2
    x, y = coords
    if x < 0 or y < 0:
        print(
            f"Error: pixel coordinates must be non-negative, got ({x},{y}).\n"
            "  gpa scene-explain --pixel 200,150",
            file=sys.stderr,
        )
        return 2

    if frame is not None:
        try:
            int(frame)
        except ValueError:
            print(
                f"Error: --frame must be an integer, got {frame!r}.\n"
                "  gpa scene-explain --pixel 200,150 --frame 7",
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
    path = f"/api/v1/frames/{fid_part}/explain-pixel?x={x}&y={y}"
    try:
        payload = client.get_json(path)
    except RestError as exc:
        if exc.status == 400:
            print(
                f"[gpa] {exc}\n"
                "  Example: gpa scene-explain --pixel 200,150",
                file=sys.stderr,
            )
            return 3
        if exc.status == 404:
            print(f"[gpa] {exc}", file=sys.stderr)
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
    if payload.get("draw_call_id") is None:
        return 1
    return 0
