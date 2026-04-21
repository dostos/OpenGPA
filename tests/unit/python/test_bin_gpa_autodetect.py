"""Tests for the `bin/gpa` wrapper's Python + extension autodetection.

Exercises the diagnostic mode (GPA_DIAG=1) which prints the resolved
GPA_PYTHON + PYTHONPATH and exits 0 — this lets us assert wiring without
actually booting the CLI.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
BIN_GPA = REPO_ROOT / "bin" / "gpa"
BINDINGS_DIR = REPO_ROOT / "bazel-bin" / "src" / "bindings"


def _run_diag(extra_env: dict | None = None) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["GPA_DIAG"] = "1"
    # Scrub any pre-existing GPA_PYTHON unless the test injects one.
    env.pop("GPA_PYTHON", None)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run(
        [str(BIN_GPA), "--help"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_bin_gpa_exists_and_executable():
    assert BIN_GPA.exists(), f"{BIN_GPA} missing"
    assert os.access(BIN_GPA, os.X_OK), f"{BIN_GPA} not executable"


def test_diag_exits_zero():
    code, out, _err = _run_diag()
    assert code == 0, out


def test_diag_reports_pythonpath_contains_src_python():
    code, out, _err = _run_diag()
    assert code == 0
    assert f"PYTHONPATH=" in out
    # src/python is always present (regardless of whether bazel artifacts exist).
    assert str(REPO_ROOT / "src" / "python") in out


def test_diag_prepends_bindings_dir_when_present():
    """If bazel has built _gpa_core.so, the bindings dir must appear
    before src/python on PYTHONPATH so `import _gpa_core` resolves."""
    so = BINDINGS_DIR / "_gpa_core.so"
    if not so.exists():
        # Can't verify prepend without the artifact; at least the binding
        # warning should be visible on stderr.
        code, _out, err = _run_diag()
        assert code == 0
        assert "_gpa_core.so not found" in err
        return
    code, out, _err = _run_diag()
    assert code == 0
    path_line = next(
        (ln for ln in out.splitlines() if ln.startswith("PYTHONPATH=")),
        None,
    )
    assert path_line is not None, out
    value = path_line.split("=", 1)[1]
    entries = value.split(":")
    assert str(BINDINGS_DIR) in entries
    assert str(REPO_ROOT / "src" / "python") in entries
    # Bindings dir must come before src/python.
    assert entries.index(str(BINDINGS_DIR)) < entries.index(
        str(REPO_ROOT / "src" / "python")
    )


def test_diag_detects_bazel_python_3_11_when_available():
    """If a bazel-built python 3.11 is available in ~/.cache/bazel, we
    should pick it up automatically (no GPA_PYTHON set)."""
    code, out, _err = _run_diag()
    assert code == 0
    py_line = next(
        (ln for ln in out.splitlines() if ln.startswith("GPA_PYTHON=")),
        None,
    )
    assert py_line is not None, out
    py = py_line.split("=", 1)[1]
    # Either the bazel 3.11 was found, or we fell back to `python3`.
    if "rules_python" in py and "python_3_11" in py:
        assert os.access(py, os.X_OK), f"detected py not executable: {py}"
    else:
        # Fallback path is acceptable only when the bazel cache is absent.
        assert py == "python3"


def test_diag_honors_explicit_gpa_python_override():
    code, out, _err = _run_diag(extra_env={"GPA_PYTHON": "/opt/custom/python"})
    assert code == 0
    assert "GPA_PYTHON=/opt/custom/python" in out
