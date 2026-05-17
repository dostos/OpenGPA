"""R19-P5: per-scenario filesystem sandbox.

The agent subprocess must not be able to read scenario.md (Ground
Truth), other scenarios' files, prior eval results, or the project's
CLAUDE.md. The sandbox is the structural defense — agents get a fresh
tmpdir tree containing only the source files they're meant to see.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from bhdr.eval.sandbox import (
    ScenarioSandbox, build_sandbox,
    _AGENT_VISIBLE_EXTS, _AGENT_DENIED_NAMES,
)


class _FakeScenario:
    def __init__(self, scenario_dir, id_="scen_a"):
        self.id = id_
        self.scenario_dir = str(scenario_dir)
        self.source_path = ""


def _seed_scenario_dir(d: Path):
    """Populate a scenario dir with a mix of agent-visible source files
    and Ground-Truth-bearing files."""
    d.mkdir(parents=True, exist_ok=True)
    (d / "main.c").write_text("int main(void) { return 0; }\n")
    (d / "helper.h").write_text("#pragma once\n")
    (d / "scenario.md").write_text(
        "## Ground Truth\nSENTINEL_GT_MARKER root cause is X.\n"
    )
    (d / "scenario.yaml").write_text("status: verified\n")
    (d / ".hidden").write_text("dotfile\n")
    (d / "notes.bin").write_text("binary noise\n")  # unsupported ext


def test_sandbox_copies_only_agent_visible_files(tmp_path):
    sdir = tmp_path / "scn"
    _seed_scenario_dir(sdir)
    scn = _FakeScenario(sdir)

    sbx = build_sandbox(scn)
    try:
        copied = sorted(p.name for p in sbx.source.iterdir())
        # Source files made it in
        assert "main.c" in copied
        assert "helper.h" in copied
        # Ground-Truth-bearing files did NOT
        assert "scenario.md" not in copied
        assert "scenario.yaml" not in copied
        # Hidden files and unsupported extensions did NOT
        assert ".hidden" not in copied
        assert "notes.bin" not in copied
    finally:
        sbx.cleanup()


def test_sandbox_scenario_md_unreadable_via_source_root(tmp_path):
    """Belt-and-braces: even if an agent tries to read
    ``$BHDR_SOURCE_ROOT/scenario.md``, the file isn't in the sandbox."""
    sdir = tmp_path / "scn"
    _seed_scenario_dir(sdir)
    scn = _FakeScenario(sdir)

    sbx = build_sandbox(scn)
    try:
        forbidden = sbx.source / "scenario.md"
        assert not forbidden.exists()
        # Reading the source dir does NOT find scenario.md anywhere
        for entry in sbx.source.rglob("*"):
            assert "scenario.md" not in entry.name
    finally:
        sbx.cleanup()


def test_sandbox_env_overrides_redirect_home_and_source(tmp_path):
    sdir = tmp_path / "scn"
    _seed_scenario_dir(sdir)
    scn = _FakeScenario(sdir)

    sbx = build_sandbox(scn)
    try:
        overrides = sbx.env_overrides
        assert overrides["HOME"] == str(sbx.home)
        assert overrides["BHDR_SOURCE_ROOT"] == str(sbx.source)
        # Snapshot not provided → not in overrides
        assert "BHDR_UPSTREAM_ROOT" not in overrides
    finally:
        sbx.cleanup()


def test_sandbox_env_strip_targets_leaky_vars(tmp_path):
    """env_strip lists vars whose values would leak the real project
    location to the agent."""
    scn = _FakeScenario(tmp_path / "scn")
    (tmp_path / "scn").mkdir()
    sbx = build_sandbox(scn)
    try:
        strip = set(sbx.env_strip)
        # Claude Code's project-pointer must be stripped
        assert "CLAUDE_PROJECT_DIR" in strip
        # Beholder session vars must be stripped
        assert "BHDR_SESSION" in strip
    finally:
        sbx.cleanup()


def test_sandbox_snapshot_symlinked_when_provided(tmp_path):
    sdir = tmp_path / "scn"
    _seed_scenario_dir(sdir)
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "src" / "renderer").mkdir(parents=True)
    (snap / "src" / "renderer" / "foo.cpp").write_text("// upstream\n")

    scn = _FakeScenario(sdir)
    sbx = build_sandbox(scn, snapshot_root=snap)
    try:
        assert sbx.snapshot is not None
        assert sbx.snapshot.is_symlink()
        # Reading through the symlink works
        assert (sbx.snapshot / "src/renderer/foo.cpp").read_text() == "// upstream\n"
        # Env override points at the symlink
        assert sbx.env_overrides["BHDR_UPSTREAM_ROOT"] == str(sbx.snapshot)
    finally:
        sbx.cleanup()


def test_sandbox_cleanup_removes_tree_but_not_snapshot(tmp_path):
    """rmtree on the sandbox must not delete the snapshot it symlinks
    to — the snapshot lives in a shared cache."""
    sdir = tmp_path / "scn"
    _seed_scenario_dir(sdir)
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "marker.txt").write_text("snap\n")

    scn = _FakeScenario(sdir)
    sbx = build_sandbox(scn, snapshot_root=snap)
    sbx_root = sbx.root
    sbx.cleanup()

    assert not sbx_root.exists()
    # Snapshot still there
    assert (snap / "marker.txt").read_text() == "snap\n"


def test_sandbox_cleanup_idempotent(tmp_path):
    sdir = tmp_path / "scn"
    _seed_scenario_dir(sdir)
    sbx = build_sandbox(_FakeScenario(sdir))
    sbx.cleanup()
    # Second cleanup is a no-op (doesn't raise)
    sbx.cleanup()


def test_sandbox_handles_missing_scenario_dir(tmp_path):
    """If a scenario has no scenario_dir (e.g. legacy synthetic), the
    sandbox still builds — just with an empty source dir."""
    scn = _FakeScenario(tmp_path / "nonexistent")
    sbx = build_sandbox(scn)
    try:
        assert sbx.source.exists()
        assert sbx.home.exists()
        # No source files
        assert list(sbx.source.iterdir()) == []
    finally:
        sbx.cleanup()


def test_sandbox_visible_exts_includes_common_source_types():
    """Sanity check: the visible-extension whitelist covers the file
    types scenarios use in the corpus."""
    needed = {".c", ".cpp", ".h", ".glsl", ".vert", ".frag", ".js", ".html", ".json"}
    assert needed <= _AGENT_VISIBLE_EXTS


def test_sandbox_denied_names_includes_scenario_yaml():
    """scenario.yaml has mining metadata + verifier verdict; not strictly
    Ground Truth but downstream signal the agent shouldn't have."""
    assert "scenario.yaml" in _AGENT_DENIED_NAMES
    assert "scenario.md" in _AGENT_DENIED_NAMES
