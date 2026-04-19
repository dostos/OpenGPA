"""``gpa`` CLI entry point.

Usage:
    gpa start [--session DIR] [--daemon/--no-daemon] [--port PORT]
    gpa stop  [--session DIR]
    gpa env   [--session DIR]
    gpa run   [--session DIR] [--timeout SEC] [--port PORT] -- <cmd> [args...]

Exit codes:
    0 success
    1 runtime / engine failure
    2 no session found (stop/env)
    127 target command not found (run)
    other: propagated from the target's own exit code (run)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from gpa.cli import __version__
from gpa.cli.commands import env as env_cmd
from gpa.cli.commands import run as run_cmd
from gpa.cli.commands import start as start_cmd
from gpa.cli.commands import stop as stop_cmd


def _add_session_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--session",
        dest="session",
        type=Path,
        default=None,
        help="Session directory (overrides $GPA_SESSION and the current-session link)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gpa",
        description="OpenGPA — live graphics debugger CLI (Phase 1a).",
    )
    parser.add_argument("--version", action="version", version=f"gpa {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="Start a persistent engine session")
    _add_session_arg(p_start)
    p_start.add_argument("--port", type=int, default=18080, help="REST API port")
    p_start.add_argument(
        "--daemon",
        dest="daemon",
        action="store_true",
        default=True,
        help="Detach engine so it outlives this process (default)",
    )
    p_start.add_argument(
        "--no-daemon",
        dest="daemon",
        action="store_false",
        help="Keep engine in the current process group",
    )

    p_stop = sub.add_parser("stop", help="Terminate the active session")
    _add_session_arg(p_stop)

    p_env = sub.add_parser("env", help="Print env exports for the active session")
    _add_session_arg(p_env)

    p_run = sub.add_parser(
        "run",
        help="Launch a target under an embedded engine + shim",
    )
    _add_session_arg(p_run)
    p_run.add_argument("--port", type=int, default=18080, help="REST API port")
    p_run.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="SIGTERM the target after N seconds (SIGKILL +3s)",
    )
    p_run.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Target command and arguments",
    )

    return parser


def _extract_command(argv: List[str]) -> List[str]:
    """argparse leaves a leading ``--`` in REMAINDER; strip it."""
    if argv and argv[0] == "--":
        return argv[1:]
    return argv


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "start":
        return start_cmd.run(
            session_dir=args.session,
            daemon=args.daemon,
            port=args.port,
        )
    if args.cmd == "stop":
        return stop_cmd.run(session_dir=args.session)
    if args.cmd == "env":
        return env_cmd.run(session_dir=args.session)
    if args.cmd == "run":
        cmd = _extract_command(list(args.command or []))
        if not cmd:
            parser.error("run: missing target command (use `--` then the command)")
        return run_cmd.run(
            cmd,
            session_dir=args.session,
            timeout=args.timeout,
            port=args.port,
        )

    parser.error(f"unknown command: {args.cmd}")  # pragma: no cover
    return 1


if __name__ == "__main__":
    sys.exit(main())
