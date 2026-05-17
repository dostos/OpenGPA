"""``gpa explain-draw <draw_id>`` — single-call explanation for one draw call.

Calls ``GET /api/v1/frames/{id}/draws/{draw_id}/explain`` and renders a
focused summary. Replaces the dump-grep-grep pattern with one ~30-line
answer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from bhdr.cli.rest_client import RestClient, RestError
from bhdr.cli.session import Session


def add_subparser(subparsers) -> None:
    epilog = (
        "Examples:\n"
        "  gpa explain-draw 47                                     # 1) simplest\n"
        "  gpa explain-draw 47 --frame 7                           # 2) specific frame\n"
        "  gpa explain-draw 47 --json                              # 3) JSON\n"
        "  gpa explain-draw 47 --field uniforms                    # 4) filter\n"
        "  gpa scene-find material:transparent --json \\\n"
        "    | jq -r '.matches[].draw_call_ids[]' \\\n"
        "    | xargs -I% gpa explain-draw %                        # 5) pipeline\n"
    )
    p = subparsers.add_parser(
        "explain-draw",
        help="Explain a single draw call: scene node + uniforms + textures + state",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog,
    )
    p.add_argument("draw_id", type=int, help="Numeric draw call id")
    p.add_argument(
        "--session", dest="session", type=Path, default=None,
        help="Session directory (overrides $GPA_SESSION and the link)",
    )
    p.add_argument(
        "--frame", dest="frame", default=None,
        help="Frame id (default: latest). Use '-' to read from stdin.",
    )
    p.add_argument(
        "--field", dest="field", default="all",
        help=(
            "CSV of fields to show: name, uniforms, textures, state. "
            "Default 'all'."
        ),
    )
    p.add_argument(
        "--json", dest="json_output", action="store_true",
        help="Emit machine-readable JSON instead of plain text",
    )
    p.add_argument(
        "--full", dest="full", action="store_true",
        help="Include full uniform list (defeats narrow-query design — opt-in)",
    )


_VALID_FIELDS = {"all", "name", "uniforms", "textures", "state"}


def _format_human(payload: Dict[str, Any], fields: List[str], full: bool) -> str:
    lines: List[str] = []
    fid = payload.get("frame_id")
    did = payload.get("draw_call_id")
    lines.append(f"draw {did}  frame {fid}")
    show_all = "all" in fields
    if show_all or "name" in fields:
        node = payload.get("scene_node_path") or "(no debug-group context)"
        uuid = payload.get("scene_node_uuid")
        ntype = payload.get("scene_node_type")
        suffix = []
        if ntype:
            suffix.append(ntype)
        if uuid:
            suffix.append(f"uuid={uuid}")
        suffix_str = f"  ({', '.join(suffix)})" if suffix else ""
        lines.append(f"node      {node}{suffix_str}")
        prog = payload.get("shader_program_id")
        material = payload.get("material_name") or "(no material annotation)"
        lines.append(f"shader    program {prog}")
        lines.append(f"material  {material}")
    if show_all or "uniforms" in fields:
        u = payload.get("uniforms_set") or {}
        items = u.get("items") or []
        if not items:
            lines.append("uniforms  (none decoded)")
        else:
            limit = None if full else len(items)
            shown = items if limit is None else items[:limit]
            joined = "  ".join(_fmt_uniform(it) for it in shown)
            lines.append(f"uniforms  {joined}")
            if u.get("truncated") and not full:
                lines.append("          … (more uniforms; pass --full)")
    if show_all or "textures" in fields:
        textures = payload.get("textures_sampled") or []
        if not textures:
            lines.append("textures  (none bound)")
        else:
            for t in textures:
                lines.append(
                    f"textures  unit{t.get('unit')} tex{t.get('tex_id')} "
                    f"{t.get('format')} {t.get('width')}x{t.get('height')}"
                )
    if show_all or "state" in fields:
        st = payload.get("relevant_state") or {}
        if st:
            kvs = "  ".join(f"{k}={v}" for k, v in sorted(st.items()))
            lines.append(f"state     {kvs}")
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


def _resolve_frames(raw_flag: Optional[str], stdin_stream) -> List[Optional[int]]:
    """Mirror ``check_config._resolve_frames`` semantics."""
    if raw_flag == "-":
        ids: List[int] = []
        for line in stdin_stream:
            line = line.strip()
            if not line:
                continue
            try:
                ids.append(int(line))
            except ValueError:
                continue
        return list(ids) if ids else [None]
    if raw_flag is not None:
        try:
            return [int(raw_flag)]
        except ValueError:
            return [None]
    return [None]


def run(
    *,
    draw_id: int,
    session_dir: Optional[Path] = None,
    frame: Optional[str] = None,
    field: str = "all",
    json_output: bool = False,
    full: bool = False,
    client: Optional[RestClient] = None,
    print_stream=None,
    stdin_stream=None,
) -> int:
    if print_stream is None:
        print_stream = sys.stdout
    if stdin_stream is None:
        stdin_stream = sys.stdin

    raw_fields = [f.strip() for f in (field or "all").split(",") if f.strip()]
    for f in raw_fields:
        if f not in _VALID_FIELDS:
            print(
                f"Error: unknown field {f!r}. Allowed: "
                + ", ".join(sorted(_VALID_FIELDS))
                + "\n  gpa explain-draw 47 --field uniforms",
                file=sys.stderr,
            )
            return 2

    if frame is not None and frame != "-":
        try:
            int(frame)
        except ValueError:
            print(
                f"Error: --frame must be an integer or '-', got {frame!r}.\n"
                "  gpa explain-draw 47 --frame 7",
                file=sys.stderr,
            )
            return 2

    frames = _resolve_frames(frame, stdin_stream)

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

    overall = 0
    aggregated: List[Dict[str, Any]] = []
    for fid in frames:
        path = (
            f"/api/v1/frames/latest/draws/{draw_id}/explain"
            if fid is None else
            f"/api/v1/frames/{int(fid)}/draws/{draw_id}/explain"
        )
        try:
            payload = client.get_json(path)
        except RestError as exc:
            if exc.status == 404:
                print(
                    f"[gpa] draw {draw_id} not found in frame "
                    f"{'latest' if fid is None else fid}. "
                    "Try `gpa report` to list draws.",
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
            aggregated.append(payload)
        else:
            print_stream.write(_format_human(payload, raw_fields, full))

    if json_output:
        if len(aggregated) == 1:
            print_stream.write(json.dumps(aggregated[0], indent=2, sort_keys=True) + "\n")
        else:
            print_stream.write(
                json.dumps({"frames": aggregated}, indent=2, sort_keys=True) + "\n"
            )
    print_stream.flush()
    return overall
