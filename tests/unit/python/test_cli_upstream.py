import io
import json
import pytest
from pathlib import Path
from gpa.cli.commands import upstream as upstream_cmd


def _make_root(tmp_path: Path) -> Path:
    root = tmp_path / "src"
    root.mkdir()
    (root / "main.c").write_text("int main(){return 0;}\n// hello\n")
    (root / "lib").mkdir()
    (root / "lib" / "util.c").write_text("void f(){} // hello\n")
    return root


def test_upstream_read_returns_json(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    monkeypatch.setenv("GPA_UPSTREAM_ROOT", str(root))
    buf = io.StringIO()
    rc = upstream_cmd.run_read(path="main.c", max_bytes=200000, print_stream=buf)
    assert rc == 0
    obj = json.loads(buf.getvalue())
    assert obj["path"] == "main.c"
    assert obj["bytes"] == len((root / "main.c").read_bytes())
    assert "int main" in obj["text"]


def test_upstream_read_max_bytes(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    monkeypatch.setenv("GPA_UPSTREAM_ROOT", str(root))
    buf = io.StringIO()
    rc = upstream_cmd.run_read(path="main.c", max_bytes=5, print_stream=buf)
    assert rc == 0
    obj = json.loads(buf.getvalue())
    assert obj["truncated"] is True
    assert len(obj["text"].encode("utf-8")) <= 5


def test_upstream_read_traversal_rejected(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    monkeypatch.setenv("GPA_UPSTREAM_ROOT", str(root))
    buf = io.StringIO()
    err = io.StringIO()
    rc = upstream_cmd.run_read(
        path="../../etc/passwd", max_bytes=200000,
        print_stream=buf, err_stream=err,
    )
    assert rc == 2
    assert "escapes root" in err.getvalue()


def test_upstream_grep_finds_pattern(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    monkeypatch.setenv("GPA_UPSTREAM_ROOT", str(root))
    buf = io.StringIO()
    rc = upstream_cmd.run_grep(
        pattern="hello", subdir="", glob="", max_matches=50, print_stream=buf,
    )
    assert rc == 0
    obj = json.loads(buf.getvalue())
    paths = sorted({m["path"] for m in obj["matches"]})
    assert paths == ["lib/util.c", "main.c"]
    assert obj["truncated"] is False


def test_upstream_grep_max_matches(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    monkeypatch.setenv("GPA_UPSTREAM_ROOT", str(root))
    buf = io.StringIO()
    rc = upstream_cmd.run_grep(
        pattern="hello", subdir="", glob="", max_matches=1, print_stream=buf,
    )
    assert rc == 0
    obj = json.loads(buf.getvalue())
    assert len(obj["matches"]) == 1
    assert obj["truncated"] is True


def test_upstream_no_root_set(monkeypatch):
    monkeypatch.delenv("GPA_UPSTREAM_ROOT", raising=False)
    buf = io.StringIO()
    err = io.StringIO()
    rc = upstream_cmd.run_read(
        path="main.c", max_bytes=200000,
        print_stream=buf, err_stream=err,
    )
    assert rc == 2
    assert "GPA_UPSTREAM_ROOT" in err.getvalue()


def test_upstream_list_returns_entries(tmp_path, monkeypatch):
    root = tmp_path / "up"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.c").write_text("")
    (root / "src" / "b.c").write_text("")
    (root / "src" / "lib").mkdir()
    monkeypatch.setenv("GPA_UPSTREAM_ROOT", str(root))
    buf = io.StringIO()
    rc = upstream_cmd.run_list(subdir="src", print_stream=buf)
    assert rc == 0
    obj = json.loads(buf.getvalue())
    names = sorted((e["name"], e["type"]) for e in obj["entries"])
    assert names == [("a.c", "file"), ("b.c", "file"), ("lib", "dir")]


def test_upstream_list_empty_subdir(tmp_path, monkeypatch):
    root = tmp_path / "up"
    root.mkdir()
    (root / "README").write_text("hi")
    (root / "src").mkdir()
    monkeypatch.setenv("GPA_UPSTREAM_ROOT", str(root))
    buf = io.StringIO()
    rc = upstream_cmd.run_list(subdir="", print_stream=buf)
    assert rc == 0
    obj = json.loads(buf.getvalue())
    assert obj["subdir"] == ""
    names = sorted((e["name"], e["type"]) for e in obj["entries"])
    assert names == [("README", "file"), ("src", "dir")]
