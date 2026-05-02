"""Env-rooted path resolution shared by ``gpa source`` and ``gpa upstream``.

Both commands operate inside a per-scenario root directory communicated
via an env var (``GPA_SOURCE_ROOT``, ``GPA_UPSTREAM_ROOT``). All path
inputs are validated against that root before any filesystem access:

- absolute paths must resolve inside the root
- relative paths are resolved against the root
- ``..`` traversal that escapes the root is rejected
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class LocalRootError(Exception):
    """Bad env var, missing root, or rejected path."""


@dataclass(frozen=True)
class LocalRoot:
    env_name: str
    path: Path

    @classmethod
    def from_env(cls, env_name: str) -> "LocalRoot":
        raw = os.environ.get(env_name)
        if not raw:
            raise LocalRootError(f"{env_name} is not set")
        p = Path(raw).expanduser()
        if not p.exists():
            raise LocalRootError(f"{env_name}={raw!r} does not exist")
        if not p.is_dir():
            raise LocalRootError(f"{env_name}={raw!r} is not a directory")
        return cls(env_name=env_name, path=p)


def resolve_relative(root: LocalRoot, user_path: str) -> Path:
    """Resolve ``user_path`` against ``root``; reject anything escaping."""
    if not user_path:
        raise LocalRootError("path is empty")
    p = Path(user_path).expanduser()
    if p.is_absolute():
        candidate = p
    else:
        candidate = root.path / p
    resolved = candidate.resolve()
    root_resolved = root.path.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        if p.is_absolute():
            raise LocalRootError(
                f"absolute path {user_path!r} is outside {root.env_name}"
            )
        raise LocalRootError(f"path {user_path!r} escapes root {root_resolved}")
    return resolved
