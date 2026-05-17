"""``gpa run`` — spawn an embedded engine and exec a target under the shim."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from bhdr.cli.commands.start import _spawn_engine
from bhdr.cli.session import Session, wait_for_port


DEFAULT_SHIM_PATH = "bazel-bin/src/shims/gl/libbhdr_gl.so"


def _resolve_shim_path() -> str:
    return os.environ.get("BHDR_SHIM_PATH", DEFAULT_SHIM_PATH)


def _prepend_ld_preload(env: dict, shim: str) -> dict:
    existing = env.get("LD_PRELOAD", "")
    env["LD_PRELOAD"] = f"{shim}:{existing}" if existing else shim
    return env


def _count_frames(sess: Session) -> Optional[int]:
    """Best-effort count of captured frames for the end-of-run summary."""
    try:
        import urllib.request

        req = urllib.request.Request(
            f"http://127.0.0.1:{sess.read_port()}/api/v1/frames",
            headers={"Authorization": f"Bearer {sess.read_token()}"},
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            import json

            data = json.loads(resp.read())
        if isinstance(data, dict):
            if "frames" in data and isinstance(data["frames"], list):
                return len(data["frames"])
            if "count" in data:
                return int(data["count"])
        if isinstance(data, list):
            return len(data)
    except Exception:
        return None
    return None


def run(
    command: List[str],
    *,
    session_dir: Optional[Path] = None,
    timeout: Optional[float] = None,
    port: int = 18080,
) -> int:
    if not command:
        print("[gpa] run: missing target command", file=sys.stderr)
        return 1

    sess = Session.create(dir=session_dir, port=port)
    try:
        engine = _spawn_engine(sess, daemon=False)
    except Exception as exc:
        print(f"[gpa] failed to spawn engine: {exc}", file=sys.stderr)
        sess.cleanup()
        return 1

    if not wait_for_port("127.0.0.1", sess.read_port(), timeout=3.0):
        print(
            f"[gpa] engine did not become ready; see {sess.log_path}",
            file=sys.stderr,
        )
        sess.terminate_engine()
        sess.cleanup()
        return 1

    sess.mark_current()
    print(f"[gpa] session {sess.dir}", file=sys.stderr)

    shim = _resolve_shim_path()
    child_env = _prepend_ld_preload(sess.child_env(), shim)

    child_rc = 1
    try:
        child = subprocess.Popen(command, env=child_env)
        try:
            child_rc = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            child.terminate()
            try:
                child_rc = child.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                child.kill()
                child_rc = child.wait()
    except FileNotFoundError as exc:
        print(f"[gpa] {exc}", file=sys.stderr)
        child_rc = 127
    finally:
        frames = _count_frames(sess)
        sess.terminate_engine()
        try:
            engine.wait(timeout=1.0)
        except Exception:
            pass
        sess.cleanup()
        if frames is not None:
            print(f"[gpa] captured {frames} frames", file=sys.stderr)

    return child_rc
