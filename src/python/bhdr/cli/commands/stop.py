"""``gpa stop`` — terminate the engine and clean up session state."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from bhdr.cli.session import Session


def run(session_dir: Optional[Path] = None) -> int:
    sess = Session.discover(explicit=session_dir)
    if sess is None:
        print("[gpa] no active session to stop", file=sys.stderr)
        return 2
    sess.terminate_engine()
    sess.cleanup()
    return 0
