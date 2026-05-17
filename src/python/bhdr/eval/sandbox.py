"""Per-scenario filesystem sandbox for the eval agent.

Each scenario invocation gets its own temporary directory containing only
the files the agent is *meant* to see. The agent CLI is run with
``cwd=<sandbox>`` and ``HOME=<sandbox>/home``, which:

1. **Prevents Ground Truth leakage.** ``scenario.md`` is never copied into
   the sandbox, so an agent that gets curious about
   ``$BHDR_SOURCE_ROOT/scenario.md`` finds nothing.
2. **Prevents prior-eval leakage.** ``docs/eval-rounds/*.md``,
   ``/data3/bhdr-eval-results/``, and the dashboard's ``index.json`` are
   all outside the sandbox tree.
3. **Prevents cross-scenario leakage.** No symlink or copy connects to
   *other* scenario directories.
4. **Prevents Claude memory leakage.** The user's
   ``~/.claude/CLAUDE.md`` and project ``.claude/`` are not reachable
   from a fresh ``$HOME``.

The agent can still hit absolute paths (e.g. ``Read('/etc/passwd')``) —
this is a soft sandbox, not a kernel-level jail. Its purpose is to make
*incidental* Ground Truth discovery impossible, not to block a
deliberately adversarial agent.

Snapshot directories are exposed via symlink so the agent can still
``read_upstream`` / ``grep_upstream`` across the framework's pre-fix
tree. Symlinking (vs copying) avoids duplicating the multi-GB godot
snapshot per scenario invocation.
"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from bhdr.eval.scenario import ScenarioMetadata


# Filenames that may live alongside scenario.md but are agent-readable.
# scenario.md and scenario.yaml carry Ground Truth / mining metadata —
# excluded. Hidden dotfiles excluded.
_AGENT_VISIBLE_EXTS = frozenset({
    ".c", ".cpp", ".cc", ".cxx",
    ".h", ".hpp",
    ".glsl", ".vert", ".frag", ".comp", ".geom", ".tesc", ".tese",
    ".js", ".ts", ".mjs",
    ".html", ".css",
    ".json", ".txt",
})
_AGENT_DENIED_NAMES = frozenset({
    "scenario.md", "scenario.yaml",
})


@dataclass
class ScenarioSandbox:
    """A per-scenario sandbox directory tree.

    Layout::

        <root>/
          source/         # copied agent-visible files from the scenario dir
          home/           # HOME override (fresh, no .claude/CLAUDE.md)
          snapshot/       # symlink → upstream snapshot dir (read-only)

    Call :meth:`cleanup` when done — it ``shutil.rmtree``s the whole
    sandbox. The snapshot symlink is not followed by rmtree, so the
    cached snapshot itself is safe.
    """

    root: Path
    source: Path
    home: Path
    snapshot: Optional[Path]

    @property
    def env_overrides(self) -> dict:
        """Env vars to set on the agent subprocess. Override-only,
        i.e. *replaces* anything already in env for these keys."""
        out = {
            "HOME": str(self.home),
            "BHDR_SOURCE_ROOT": str(self.source),
        }
        if self.snapshot is not None:
            out["BHDR_UPSTREAM_ROOT"] = str(self.snapshot)
        return out

    @property
    def env_strip(self) -> tuple[str, ...]:
        """Env vars to *remove* from the agent's environment.

        These point at the orchestrator's project / claude state and
        would leak it back to the agent. Anything that names the real
        repo or its sub-paths must be stripped.
        """
        return (
            # Claude Code points its memory + project state via these.
            # Letting them through means the agent loads our project's
            # CLAUDE.md (project instructions = giant hint).
            "CLAUDE_PROJECT_DIR",
            "CLAUDECODE",
            "CLAUDE_CODE_ENTRYPOINT",
            # Beholder session vars from the orchestrator's bhdr session
            # would point at /tmp/bhdr-session-current — fine in principle
            # but a leaky channel. Strip to be safe.
            "BHDR_SESSION",
            "BHDR_SESSION_CURRENT",
        )

    def cleanup(self) -> None:
        """Remove the sandbox tree. Safe to call multiple times."""
        try:
            shutil.rmtree(self.root, ignore_errors=True)
        except Exception:
            pass


def build_sandbox(
    scenario: ScenarioMetadata,
    snapshot_root: Optional[Path] = None,
) -> ScenarioSandbox:
    """Materialise a fresh sandbox for ``scenario``.

    Copies (not symlinks) agent-visible scenario source files into
    ``<sandbox>/source/`` so the original scenario directory stays
    pristine. The snapshot is symlinked (not copied) — they're huge.

    The ``home`` subdir is created empty; no ``.claude/`` etc. is
    populated, so the user's user-memory never reaches the agent.

    Args:
      scenario: the loaded scenario metadata.
      snapshot_root: optional path to a pre-fetched upstream snapshot.
        When provided, ``<sandbox>/snapshot`` becomes a symlink to it
        and ``BHDR_UPSTREAM_ROOT`` points at the symlink.

    Returns:
      A :class:`ScenarioSandbox`. Caller must call ``cleanup()`` when
      done (or use a try/finally pattern in the harness).
    """
    root = Path(tempfile.mkdtemp(prefix=f"bhdr-sandbox-{scenario.id}-"))
    source = root / "source"
    home = root / "home"
    source.mkdir()
    home.mkdir()

    # Copy agent-visible files from the scenario directory.
    scenario_dir = getattr(scenario, "scenario_dir", None)
    if scenario_dir:
        sdir = Path(scenario_dir)
        if sdir.is_dir():
            for entry in sdir.iterdir():
                if not entry.is_file():
                    continue
                if entry.name in _AGENT_DENIED_NAMES:
                    continue
                if entry.name.startswith("."):
                    continue
                if entry.suffix.lower() not in _AGENT_VISIBLE_EXTS:
                    continue
                shutil.copy2(entry, source / entry.name)

    snapshot: Optional[Path] = None
    if snapshot_root is not None:
        # Symlink so we don't duplicate the multi-GB snapshot per
        # scenario. The agent's `Read` / `Grep` follow symlinks, so
        # this is transparent.
        snap_link = root / "snapshot"
        try:
            snap_link.symlink_to(snapshot_root)
            snapshot = snap_link
        except OSError:
            # Filesystem doesn't support symlinks (rare) — fall back
            # to no snapshot exposure. The agent prompt will still
            # reference the upstream repo via its remote URL.
            snapshot = None

    return ScenarioSandbox(
        root=root, source=source, home=home, snapshot=snapshot,
    )
