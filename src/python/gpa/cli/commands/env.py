"""``gpa env`` — print the env exports for the active session."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from gpa.cli.session import Session


def run(session_dir: Optional[Path] = None, *, print_stream=None) -> int:
    if print_stream is None:
        print_stream = sys.stdout
    sess = Session.discover(explicit=session_dir)
    if sess is None:
        print("[gpa] no active session found", file=sys.stderr)
        return 2
    print_stream.write(sess.env_exports())
    print_stream.flush()
    return 0
