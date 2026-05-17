import os
import pytest
from pathlib import Path
from bhdr.cli.local_roots import (
    LocalRoot,
    LocalRootError,
    resolve_relative,
)


def test_resolve_relative_inside_root(tmp_path):
    root = LocalRoot("GPA_SOURCE_ROOT", tmp_path)
    target = tmp_path / "sub" / "file.c"
    target.parent.mkdir()
    target.write_text("hello")
    resolved = resolve_relative(root, "sub/file.c")
    assert resolved == target.resolve()


def test_resolve_rejects_absolute_outside(tmp_path):
    root = LocalRoot("GPA_SOURCE_ROOT", tmp_path)
    with pytest.raises(LocalRootError, match="absolute path"):
        resolve_relative(root, "/etc/passwd")


def test_resolve_rejects_traversal(tmp_path):
    root = LocalRoot("GPA_SOURCE_ROOT", tmp_path)
    with pytest.raises(LocalRootError, match="escapes root"):
        resolve_relative(root, "../../etc/passwd")


def test_resolve_accepts_absolute_inside_root(tmp_path):
    root = LocalRoot("GPA_SOURCE_ROOT", tmp_path)
    target = tmp_path / "x.c"
    target.write_text("")
    resolved = resolve_relative(root, str(target))
    assert resolved == target.resolve()


def test_localroot_from_env_missing(monkeypatch):
    monkeypatch.delenv("GPA_SOURCE_ROOT", raising=False)
    with pytest.raises(LocalRootError, match="not set"):
        LocalRoot.from_env("GPA_SOURCE_ROOT")


def test_localroot_from_env_present(monkeypatch, tmp_path):
    monkeypatch.setenv("GPA_SOURCE_ROOT", str(tmp_path))
    root = LocalRoot.from_env("GPA_SOURCE_ROOT")
    assert root.path == tmp_path
