# OpenGPA CLI + Multi-Backend Eval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the OpenGPA eval pipeline backend-agnostic (api / claude-cli / codex-cli) by abstracting the agent loop, exposing a complete `gpa` CLI with consistent `noun verb` naming so CLI agents can call OpenGPA over their built-in shell tool, and marking the MCP server deprecated.

**Architecture:** Three layers change. The `gpa` CLI grows new noun-verb commands and harness-local `source`/`upstream` namespaces. The eval agent splits into a package with three backends (`api`, `claude-cli`, `codex-cli`) selected by a factory. The curation LLM client gains a parallel `codex-cli` backend. MCP gets a deprecation header but stays callable.

**Tech Stack:** Python 3.11, argparse, pytest, anthropic SDK, subprocess (for CLI backends). Existing `gpa.cli.rest_client.RestClient` and the `add_subparser(subparsers) / run(...)` command pattern are reused.

**Spec:** `docs/superpowers/specs/2026-05-02-gpa-cli-eval-codex-design.md`

---

## Phase 1 — CLI extension: harness-local commands

These commands unblock the agent backend (Phase 3) by exposing source/upstream snapshot access. Phase 1 is independent of Phase 2+ and can ship alone.

### Task 1: `local_roots.py` — env-rooted path resolver

**Files:**
- Create: `src/python/bhdr/cli/local_roots.py`
- Test: `tests/unit/python/test_cli_local_roots.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/python/test_cli_local_roots.py
import os
import pytest
from pathlib import Path
from gpa.cli.local_roots import (
    LocalRoot,
    LocalRootError,
    resolve_relative,
)


def test_resolve_relative_inside_root(tmp_path):
    root = LocalRoot("BHDR_SOURCE_ROOT", tmp_path)
    target = tmp_path / "sub" / "file.c"
    target.parent.mkdir()
    target.write_text("hello")
    resolved = resolve_relative(root, "sub/file.c")
    assert resolved == target.resolve()


def test_resolve_rejects_absolute_outside(tmp_path):
    root = LocalRoot("BHDR_SOURCE_ROOT", tmp_path)
    with pytest.raises(LocalRootError, match="absolute path"):
        resolve_relative(root, "/etc/passwd")


def test_resolve_rejects_traversal(tmp_path):
    root = LocalRoot("BHDR_SOURCE_ROOT", tmp_path)
    with pytest.raises(LocalRootError, match="escapes root"):
        resolve_relative(root, "../../etc/passwd")


def test_resolve_accepts_absolute_inside_root(tmp_path):
    root = LocalRoot("BHDR_SOURCE_ROOT", tmp_path)
    target = tmp_path / "x.c"
    target.write_text("")
    resolved = resolve_relative(root, str(target))
    assert resolved == target.resolve()


def test_localroot_from_env_missing(monkeypatch):
    monkeypatch.delenv("BHDR_SOURCE_ROOT", raising=False)
    with pytest.raises(LocalRootError, match="not set"):
        LocalRoot.from_env("BHDR_SOURCE_ROOT")


def test_localroot_from_env_present(monkeypatch, tmp_path):
    monkeypatch.setenv("BHDR_SOURCE_ROOT", str(tmp_path))
    root = LocalRoot.from_env("BHDR_SOURCE_ROOT")
    assert root.path == tmp_path
```

- [ ] **Step 2: Run tests, expect fail**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_cli_local_roots.py -q
```
Expected: ImportError / collection error.

- [ ] **Step 3: Implement `local_roots.py`**

```python
# src/python/bhdr/cli/local_roots.py
"""Env-rooted path resolution shared by ``gpa source`` and ``gpa upstream``.

Both commands operate inside a per-scenario root directory communicated
via an env var (``BHDR_SOURCE_ROOT``, ``BHDR_UPSTREAM_ROOT``). All path
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
```

- [ ] **Step 4: Run tests, expect pass**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_cli_local_roots.py -q
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/python/bhdr/cli/local_roots.py tests/unit/python/test_cli_local_roots.py
git commit -m "feat(cli): env-rooted path resolver for source/upstream commands"
```

---

### Task 2: `gpa source` namespace (read, grep)

**Files:**
- Create: `src/python/bhdr/cli/commands/source.py`
- Modify: `src/python/bhdr/cli/main.py` (register subparser)
- Test: `tests/unit/python/test_cli_source.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/python/test_cli_source.py
import io
import json
import pytest
from pathlib import Path
from gpa.cli.commands import source as source_cmd


def _make_root(tmp_path: Path) -> Path:
    root = tmp_path / "src"
    root.mkdir()
    (root / "main.c").write_text("int main(){return 0;}\n// hello\n")
    (root / "lib").mkdir()
    (root / "lib" / "util.c").write_text("void f(){} // hello\n")
    return root


def test_source_read_returns_json(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    monkeypatch.setenv("BHDR_SOURCE_ROOT", str(root))
    buf = io.StringIO()
    rc = source_cmd.run_read(path="main.c", max_bytes=200000, print_stream=buf)
    assert rc == 0
    obj = json.loads(buf.getvalue())
    assert obj["path"] == "main.c"
    assert obj["bytes"] == len((root / "main.c").read_bytes())
    assert "int main" in obj["text"]


def test_source_read_max_bytes(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    monkeypatch.setenv("BHDR_SOURCE_ROOT", str(root))
    buf = io.StringIO()
    rc = source_cmd.run_read(path="main.c", max_bytes=5, print_stream=buf)
    assert rc == 0
    obj = json.loads(buf.getvalue())
    assert obj["truncated"] is True
    assert len(obj["text"].encode("utf-8")) <= 5


def test_source_read_traversal_rejected(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    monkeypatch.setenv("BHDR_SOURCE_ROOT", str(root))
    buf = io.StringIO()
    err = io.StringIO()
    rc = source_cmd.run_read(
        path="../../etc/passwd", max_bytes=200000,
        print_stream=buf, err_stream=err,
    )
    assert rc == 2
    assert "escapes root" in err.getvalue()


def test_source_grep_finds_pattern(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    monkeypatch.setenv("BHDR_SOURCE_ROOT", str(root))
    buf = io.StringIO()
    rc = source_cmd.run_grep(
        pattern="hello", subdir="", glob="", max_matches=50, print_stream=buf,
    )
    assert rc == 0
    obj = json.loads(buf.getvalue())
    paths = sorted({m["path"] for m in obj["matches"]})
    assert paths == ["lib/util.c", "main.c"]
    assert obj["truncated"] is False


def test_source_grep_max_matches(tmp_path, monkeypatch):
    root = _make_root(tmp_path)
    monkeypatch.setenv("BHDR_SOURCE_ROOT", str(root))
    buf = io.StringIO()
    rc = source_cmd.run_grep(
        pattern="hello", subdir="", glob="", max_matches=1, print_stream=buf,
    )
    assert rc == 0
    obj = json.loads(buf.getvalue())
    assert len(obj["matches"]) == 1
    assert obj["truncated"] is True


def test_source_no_root_set(monkeypatch):
    monkeypatch.delenv("BHDR_SOURCE_ROOT", raising=False)
    buf = io.StringIO()
    err = io.StringIO()
    rc = source_cmd.run_read(
        path="main.c", max_bytes=200000,
        print_stream=buf, err_stream=err,
    )
    assert rc == 2
    assert "BHDR_SOURCE_ROOT" in err.getvalue()
```

- [ ] **Step 2: Run, expect fail**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_cli_source.py -q
```

- [ ] **Step 3: Implement `source.py`**

```python
# src/python/bhdr/cli/commands/source.py
"""``gpa source read|grep`` — harness-local source access.

Operates inside ``$BHDR_SOURCE_ROOT``. All paths are validated by
``gpa.cli.local_roots`` before any filesystem access.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable, TextIO

from gpa.cli.local_roots import (
    LocalRoot,
    LocalRootError,
    resolve_relative,
)


_DEFAULT_MAX_BYTES = 200_000
_DEFAULT_MAX_MATCHES = 50
_HARD_MAX_MATCHES = 500
_ENV_NAME = "BHDR_SOURCE_ROOT"


def add_subparser(subparsers) -> None:
    p = subparsers.add_parser(
        "source",
        help="Harness-local source access (under $BHDR_SOURCE_ROOT)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="source_cmd", required=True)

    p_read = sub.add_parser("read", help="Read a source file as JSON")
    p_read.add_argument("path", help="Path relative to $BHDR_SOURCE_ROOT")
    p_read.add_argument(
        "--max-bytes", type=int, default=_DEFAULT_MAX_BYTES,
        help=f"Truncation cap (default {_DEFAULT_MAX_BYTES})",
    )

    p_grep = sub.add_parser("grep", help="Regex search across the source root")
    p_grep.add_argument("pattern", help="Python regex")
    p_grep.add_argument("--subdir", default="", help="Restrict to a subdir")
    p_grep.add_argument("--glob", default="", help="Filename glob, e.g. '*.c'")
    p_grep.add_argument(
        "--max-matches", type=int, default=_DEFAULT_MAX_MATCHES,
        help=f"Cap (default {_DEFAULT_MAX_MATCHES}, hard cap {_HARD_MAX_MATCHES})",
    )


def run_read(
    *, path: str, max_bytes: int,
    print_stream: TextIO = sys.stdout,
    err_stream: TextIO = sys.stderr,
) -> int:
    try:
        root = LocalRoot.from_env(_ENV_NAME)
        target = resolve_relative(root, path)
    except LocalRootError as e:
        print(str(e), file=err_stream)
        return 2
    if not target.is_file():
        print(f"not a file: {path}", file=err_stream)
        return 2
    raw = target.read_bytes()
    truncated = len(raw) > max_bytes
    payload = raw[:max_bytes]
    text = payload.decode("utf-8", errors="replace")
    obj = {
        "path": path,
        "bytes": len(raw),
        "truncated": truncated,
        "text": text,
    }
    print(json.dumps(obj, ensure_ascii=False), file=print_stream)
    return 0


def run_grep(
    *, pattern: str, subdir: str, glob: str, max_matches: int,
    print_stream: TextIO = sys.stdout,
    err_stream: TextIO = sys.stderr,
) -> int:
    try:
        root = LocalRoot.from_env(_ENV_NAME)
        base = resolve_relative(root, subdir) if subdir else root.path
    except LocalRootError as e:
        print(str(e), file=err_stream)
        return 2
    cap = min(max(1, max_matches), _HARD_MAX_MATCHES)
    try:
        regex = re.compile(pattern)
    except re.error as e:
        print(f"bad pattern: {e}", file=err_stream)
        return 2
    matches: list[dict] = []
    truncated = False
    iterator: Iterable[Path] = (
        base.rglob(glob) if glob else base.rglob("*")
    )
    for path in iterator:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                rel = path.relative_to(root.path).as_posix()
                matches.append(
                    {"path": rel, "line": lineno, "text": line[:500]}
                )
                if len(matches) >= cap:
                    truncated = True
                    break
        if truncated:
            break
    obj = {"matches": matches, "truncated": truncated}
    print(json.dumps(obj, ensure_ascii=False), file=print_stream)
    return 0


def run(args: argparse.Namespace) -> int:
    sub = args.source_cmd
    if sub == "read":
        return run_read(path=args.path, max_bytes=args.max_bytes)
    if sub == "grep":
        return run_grep(
            pattern=args.pattern, subdir=args.subdir, glob=args.glob,
            max_matches=args.max_matches,
        )
    raise AssertionError(sub)
```

- [ ] **Step 4: Wire `add_subparser` into `gpa.cli.main`**

```python
# src/python/bhdr/cli/main.py — at the import block
from gpa.cli.commands import source as source_cmd

# in build_parser(), near the existing add_subparser calls:
source_cmd.add_subparser(sub)

# in main()'s dispatch table (look for the if/elif chain on args.cmd):
elif args.cmd == "source":
    return source_cmd.run(args)
```

- [ ] **Step 5: Run tests, expect pass**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_cli_source.py -q
```

- [ ] **Step 6: Commit**

```bash
git add src/python/bhdr/cli/commands/source.py src/python/bhdr/cli/main.py tests/unit/python/test_cli_source.py
git commit -m "feat(cli): gpa source read/grep over BHDR_SOURCE_ROOT"
```

---

### Task 3: `gpa upstream` namespace (read, list, grep)

**Files:**
- Create: `src/python/bhdr/cli/commands/upstream.py`
- Modify: `src/python/bhdr/cli/main.py`
- Test: `tests/unit/python/test_cli_upstream.py`

- [ ] **Step 1: Write tests modelled on `test_cli_source.py`**

Mirror the source tests; add `test_upstream_list_returns_entries` covering directory listing.

```python
def test_upstream_list_returns_entries(tmp_path, monkeypatch):
    root = tmp_path / "up"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.c").write_text("")
    (root / "src" / "b.c").write_text("")
    (root / "src" / "lib").mkdir()
    monkeypatch.setenv("BHDR_UPSTREAM_ROOT", str(root))
    buf = io.StringIO()
    rc = upstream_cmd.run_list(subdir="src", print_stream=buf)
    assert rc == 0
    obj = json.loads(buf.getvalue())
    names = sorted((e["name"], e["type"]) for e in obj["entries"])
    assert names == [("a.c", "file"), ("b.c", "file"), ("lib", "dir")]
```

- [ ] **Step 2: Implement `upstream.py`**

Identical structure to `source.py` with:
- `_ENV_NAME = "BHDR_UPSTREAM_ROOT"`
- `run_list(subdir)` returning `{"subdir": subdir, "entries": [{"name": str, "type": "file"|"dir"}]}`
- read/grep otherwise identical (consider extracting common helpers later — defer to keep DRY decisions for after both land).

- [ ] **Step 3: Wire into `main.py`**

- [ ] **Step 4: Run tests, expect pass**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_cli_upstream.py -q
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(cli): gpa upstream read/list/grep over BHDR_UPSTREAM_ROOT"
```

---

### Task 4: DRY pass — extract shared read/grep helpers

After Tasks 2 and 3, both `source.py` and `upstream.py` have near-identical `run_read` and `run_grep`. Extract to `local_roots.py` as `read_file_json(root, path, max_bytes)` and `grep_root_json(root, pattern, subdir, glob, max_matches)`. Each command file becomes ~40 lines.

- [ ] **Step 1: Update `local_roots.py` with the shared helpers**
- [ ] **Step 2: Refactor both command files to call them**
- [ ] **Step 3: Run all CLI tests**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_cli_local_roots.py tests/unit/python/test_cli_source.py tests/unit/python/test_cli_upstream.py -q
```

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor(cli): hoist shared read/grep helpers into local_roots"
```

---

## Phase 2 — CLI extension: REST-backed noun-verb commands

Each task here registers one noun namespace (`drawcalls`, `pixel`, `scene`, etc.). Pattern is identical: `add_subparser(subparsers)` → `run(args, *, client, print_stream)`. Tests use the existing `injected_rest` fixture pattern from `test_cli_dump.py`.

### Task 5: Frame-resolver helper with BHDR_FRAME_ID precedence

**Files:**
- Create: `src/python/bhdr/cli/frame_resolver.py`
- Test: `tests/unit/python/test_cli_frame_resolver.py`

- [ ] **Step 1: Write tests**

```python
def test_resolve_explicit_int(monkeypatch):
    monkeypatch.delenv("BHDR_FRAME_ID", raising=False)
    assert resolve_frame(client=_FakeClient({}), explicit=7) == 7

def test_resolve_uses_env(monkeypatch):
    monkeypatch.setenv("BHDR_FRAME_ID", "42")
    assert resolve_frame(client=_FakeClient({}), explicit=None) == 42

def test_explicit_wins_over_env(monkeypatch):
    monkeypatch.setenv("BHDR_FRAME_ID", "42")
    assert resolve_frame(client=_FakeClient({}), explicit=7) == 7

def test_falls_back_to_latest_via_rest(monkeypatch):
    monkeypatch.delenv("BHDR_FRAME_ID", raising=False)
    fake = _FakeClient({"/api/v1/frames/current/overview": {"frame_id": 99}})
    assert resolve_frame(client=fake, explicit=None) == 99

def test_latest_string_resolves_via_rest(monkeypatch):
    monkeypatch.delenv("BHDR_FRAME_ID", raising=False)
    fake = _FakeClient({"/api/v1/frames/current/overview": {"frame_id": 5}})
    assert resolve_frame(client=fake, explicit="latest") == 5
```

- [ ] **Step 2: Implement `frame_resolver.py`**

```python
"""Resolve --frame for CLI commands.

Precedence: explicit --frame > BHDR_FRAME_ID env > REST 'current'.
"""
from __future__ import annotations
import os
from typing import Optional, Union
from gpa.cli.rest_client import RestClient


def resolve_frame(
    *, client: RestClient,
    explicit: Optional[Union[int, str]],
) -> int:
    if explicit is not None and explicit != "latest":
        return int(explicit)
    if explicit is None:
        env = os.environ.get("BHDR_FRAME_ID", "").strip()
        if env:
            return int(env)
    overview = client.get_json("/api/v1/frames/current/overview")
    return int(overview["frame_id"])
```

- [ ] **Step 3: Run, expect pass**
- [ ] **Step 4: Commit**

```bash
git commit -m "feat(cli): frame_resolver honors BHDR_FRAME_ID env"
```

---

### Task 6: `gpa frames` — list/overview/check-config consolidation

**Files:**
- Modify: `src/python/bhdr/cli/commands/frames.py` (add `list` subverb; current bare `gpa frames` becomes deprecated alias for `gpa frames list`)
- Modify: `src/python/bhdr/cli/main.py` (replace bare `frames` parser with namespaced one)
- Modify or create: `tests/unit/python/test_cli_frames.py`

Add subcommands:
```
gpa frames list [--json]                       — replaces bare `gpa frames`
gpa frames overview [--frame N] [--json]        — replaces `gpa dump frame`
gpa frames check-config [--frame N] [--json]    — alias for current `gpa check-config`
```

- [ ] **Step 1: Write tests for `frames list` and `frames overview`** using the `injected_rest` fixture pattern.
- [ ] **Step 2: Refactor `commands/frames.py`** to a sub-parser with `list`/`overview` subverbs that share rest-client wiring. Use `subparsers = p.add_subparsers(dest="frames_cmd", required=False)` (NOT `required=True`) so bare `gpa frames` can be intercepted as a deprecated alias. Argparse with `required=True` exits 2 before any handler runs, defeating the alias.
- [ ] **Step 3: Wire bare-form deprecation alias** in `main.py` *or* `commands/frames.py`'s `run`: when `args.cmd == "frames"` and `args.frames_cmd is None`, log a one-line stderr deprecation note and dispatch to the `list` handler. Verify by running `gpa frames` (no subverb) and confirming both the warning and the list output appear.
- [ ] **Step 4: Update existing `test_cli_dump.py::test_dump_frame_*` to also test the new `gpa frames overview` path.**
- [ ] **Step 5: Run all CLI tests, expect pass.**
- [ ] **Step 6: Commit**

```bash
git commit -m "feat(cli): gpa frames list/overview namespace + bare alias deprecation"
```

---

### Task 7: `gpa drawcalls` namespace

**Files:**
- Create: `src/python/bhdr/cli/commands/drawcalls.py`
- Modify: `src/python/bhdr/cli/main.py`
- Test: `tests/unit/python/test_cli_drawcalls.py`

Subcommands:
```
gpa drawcalls list  [--frame N] [--limit N] [--offset N] [--json]
gpa drawcalls get   [--frame N] --dc N [--json]
gpa drawcalls shader [--frame N] --dc N [--json]
gpa drawcalls textures [--frame N] --dc N [--json]
gpa drawcalls vertices [--frame N] --dc N [--json]
gpa drawcalls attachments [--frame N] --dc N [--json]
gpa drawcalls nan-uniforms [--frame N] --dc N [--json]
gpa drawcalls feedback-loops [--frame N] --dc N [--json]
gpa drawcalls explain [--frame N] --dc N [--json]
gpa drawcalls diff [--frame N] --a N --b N [--scope state|uniforms|textures|all] [--json]
gpa drawcalls sources get [--frame N] --dc N [--json]
gpa drawcalls sources set [--frame N] --dc N (--file PATH | --body-json TEXT)
```

- [ ] **Step 1: Write minimal smoke tests** — one test per subverb hitting a fake rest endpoint via `injected_rest`. Don't expand to full coverage; integration tests in Phase 6 catch the rest.
- [ ] **Step 2: Implement `drawcalls.py`** as a flat dispatch table. Build path strings inline (no helper); each subverb resolves `frame_id` via `frame_resolver.resolve_frame` then constructs its REST path:

```python
def _run_list(client, args):
    fid = resolve_frame(client=client, explicit=args.frame)
    return client.get_json(
        f"/api/v1/frames/{fid}/drawcalls?limit={args.limit}&offset={args.offset}"
    )

def _run_get(client, args):
    fid = resolve_frame(client=client, explicit=args.frame)
    return client.get_json(f"/api/v1/frames/{fid}/drawcalls/{args.dc}")

# ... one function per subverb, dispatched via:
_DISPATCH = {
    "list": _run_list, "get": _run_get, "shader": _run_shader,
    "textures": _run_textures, "vertices": _run_vertices,
    "attachments": _run_attachments, "nan-uniforms": _run_nan_uniforms,
    "feedback-loops": _run_feedback_loops, "explain": _run_explain,
    "diff": _run_diff,
}
```

JSON-default printer (`json.dumps(result)`); pass-through API JSON verbatim.

- [ ] **Step 3: Wire the existing `explain-draw` and `diff-draws` top-level commands as deprecated aliases that dispatch to `gpa drawcalls explain` / `gpa drawcalls diff`** with a stderr deprecation note. Don't move logic; the alias just rewrites argv.

- [ ] **Step 4: Run tests, expect pass.**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(cli): gpa drawcalls namespace covering MCP parity"
```

---

### Task 8: `gpa pixel` namespace

```
gpa pixel get     [--frame N] --x N --y N [--json]
gpa pixel explain [--frame N] --x N --y N [--json]
```

Same pattern as Task 7.

- [ ] **Step 1: Tests** — two smoke tests; one for `pixel get` (uses `/api/v1/frames/{f}/pixel/{x}/{y}`) and one for `pixel explain` (uses `/api/v1/frames/{f}/explain-pixel?x&y`).
- [ ] **Step 2: Implement.**
- [ ] **Step 3: Add `gpa dump pixel` deprecation alias.**
- [ ] **Step 4: Run, commit.**

```bash
git commit -m "feat(cli): gpa pixel get/explain namespace"
```

---

### Task 9: `gpa scene` namespace

```
gpa scene get     [--frame N] [--json]
gpa scene camera  [--frame N] [--json]
gpa scene objects [--frame N] [--limit N] [--offset N] [--json]
gpa scene find    [--frame N] --predicate ... [--limit N] [--json]
gpa scene explain [--frame N] --x N --y N [--json]
```

- [ ] **Step 1: Tests for all five subverbs.**
- [ ] **Step 2: Implement.**
- [ ] **Step 3: Add `scene-find` and `scene-explain` deprecation aliases.**
- [ ] **Step 4: Commit.**

---

### Task 10: `gpa diff frames`

```
gpa diff frames --a N --b N [--depth summary|drawcalls|pixels] [--json]
```

Note: `gpa drawcalls diff` (Task 7) already covers draw-vs-draw; this task only adds the frame-vs-frame variant.

- [ ] **Steps 1–4** as before.
- [ ] **Commit** as `feat(cli): gpa diff frames`.

---

### Task 11: `gpa passes` namespace

```
gpa passes list [--frame N] [--json]
gpa passes get  NAME [--frame N] [--json]
```

---

### Task 12: `gpa annotations` namespace

```
gpa annotations list [--frame N] [--json]
gpa annotations add  [--frame N] (--file PATH | --body-json TEXT)
```

---

### Task 13: `gpa control` namespace

```
gpa control status
gpa control pause
gpa control resume
gpa control step
```

POST endpoints — use `client.post_json(path, body=None)`.

---

### Task 14: `gpa frames metadata` get/set

```
gpa frames metadata get [--frame N] [--json]
gpa frames metadata set [--frame N] (--file PATH | --body-json TEXT)
```

Add as a third sub-verb under `gpa frames` (alongside `list` and `overview`).

---

### Task 15: `gpa dump` deprecation alias

The whole `gpa dump` family is replaced by `gpa frames overview`, `gpa drawcalls list`, and `gpa pixel get`. Convert `gpa dump` to a thin compat shim that prints a one-line stderr deprecation note and rewrites argv to the new form.

- [ ] **Step 1: Write tests** ensuring `gpa dump frame --frame 7` and `gpa frames overview --frame 7` produce identical stdout (modulo stderr deprecation).
- [ ] **Step 2: Implement** by intercepting in `main.py`:

```python
elif args.cmd == "dump":
    print(
        "warning: 'gpa dump' is deprecated; use 'gpa frames overview', "
        "'gpa drawcalls list', or 'gpa pixel get'.",
        file=sys.stderr,
    )
    return _redirect_dump(args)
```

- [ ] **Step 3: Run all CLI tests.**
- [ ] **Step 4: Commit.**

```bash
git commit -m "refactor(cli): deprecate gpa dump in favor of noun-verb commands"
```

---

## Phase 3 — Eval-agent backend abstraction

### Task 16: New `gpa.eval.agents` package skeleton

**Note on test paths:** `tests/unit/python/` is flat in this repo (no nested package dirs). All new tests below use `tests/unit/python/test_<name>.py` flat naming.

**Files:**
- Create: `src/python/bhdr/eval/agents/__init__.py`
- Create: `src/python/bhdr/eval/agents/base.py`
- Test: `tests/unit/python/test_agents_base.py`

`base.py` defines:
- `AgentResult` dataclass (moved from `llm_agent.py`)
- `AgentBackend` ABC with one method: `run(scenario, mode: str, tools: dict) -> AgentResult`
- `AgentFn` type alias matching today's `harness.AgentFn` signature

`__init__.py` re-exports `AgentResult`, `AgentBackend`.

- [ ] **Step 1: Write a contract test**

```python
def test_agent_backend_is_abstract():
    with pytest.raises(TypeError):
        AgentBackend()  # type: ignore[abstract]


def test_agent_result_immutable_fields():
    r = AgentResult(diagnosis="x", input_tokens=1, output_tokens=2,
                    total_tokens=3, tool_calls=4, num_turns=5,
                    time_seconds=0.1, conversation=[])
    assert r.diagnosis == "x"
    assert r.tool_sequence == []
```

- [ ] **Step 2: Implement `base.py`.**
- [ ] **Step 3: Run, commit.**

```bash
git commit -m "feat(eval): create gpa.eval.agents package with AgentBackend ABC"
```

---

### Task 17: Move `EvalAgent` → `agents.api_agent.ApiAgent`

**Files:**
- Create: `src/python/bhdr/eval/agents/api_agent.py`
- Modify: `src/python/bhdr/eval/llm_agent.py` (becomes shim)

Move the existing `EvalAgent`, `BhdrToolExecutor`, `BHDR_TOOLS`, `CODE_ONLY_TOOLS`, `SNAPSHOT_TOOLS`, `build_agent_fn` constants into `api_agent.py`. Rename `EvalAgent` → `ApiAgent` and have it implement `AgentBackend`.

`llm_agent.py` becomes:

```python
"""Compatibility shim — moved to gpa.eval.agents.api_agent."""
from __future__ import annotations
import warnings
from gpa.eval.agents.api_agent import (
    ApiAgent as EvalAgent,
    BhdrToolExecutor,
    BHDR_TOOLS,
    CODE_ONLY_TOOLS,
    SNAPSHOT_TOOLS,
    build_agent_fn,
)
from gpa.eval.agents.base import AgentResult

warnings.warn(
    "gpa.eval.llm_agent is deprecated; import from gpa.eval.agents",
    DeprecationWarning, stacklevel=2,
)
__all__ = [
    "EvalAgent", "BhdrToolExecutor", "BHDR_TOOLS", "CODE_ONLY_TOOLS",
    "SNAPSHOT_TOOLS", "build_agent_fn", "AgentResult",
]
```

- [ ] **Step 1: Run existing harness tests, capture baseline.**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/ -k "eval or harness or llm_agent" -q
```

- [ ] **Step 2: Audit external callers of `gpa.eval.llm_agent`.**

```bash
grep -rn "from gpa.eval.llm_agent\|import gpa.eval.llm_agent" src/ tests/
```

Confirmed callers (as of plan writing): `tests/unit/python/test_eval_agent.py` imports `EvalAgent`, `BhdrToolExecutor`, `BHDR_TOOLS`, `CODE_ONLY_TOOLS`, `SNAPSHOT_TOOLS`, `build_agent_fn`. `tests/unit/python/test_eval_no_ground_truth_leak.py` imports `EvalAgent` and `build_agent_fn`. The shim's `__all__` must cover every symbol grep finds.

- [ ] **Step 3: Move file content** to `gpa.eval.agents.api_agent`. No behaviour changes.
- [ ] **Step 4: Convert `llm_agent.py` to shim** with `__all__` covering every symbol the audit identified, including `AgentResult`.
- [ ] **Step 5: Re-run baseline tests, expect identical results.**
- [ ] **Step 6: Commit.**

```bash
git commit -m "refactor(eval): move EvalAgent to gpa.eval.agents.api_agent (shim left)"
```

---

### Task 18: `CliBackendSpec` and `CliRunMetrics`

**Files:**
- Create: `src/python/bhdr/eval/agents/cli_spec.py`
- Test: `tests/unit/python/test_cli_spec.py`

```python
@dataclass(frozen=True)
class CliRunMetrics:
    diagnosis: str
    input_tokens: int
    output_tokens: int
    tool_calls: int
    num_turns: int
    tool_sequence: list[str]


@dataclass(frozen=True)
class CliBackendSpec:
    name: str                    # "claude-cli" | "codex-cli"
    binary: str
    base_args: tuple[str, ...]
    parse_run: Callable[[str, str], CliRunMetrics]
    timeout_sec: int = 1800
```

- [ ] **Step 1: Tests** — minimal: spec is hashable/frozen; `parse_run` is callable.
- [ ] **Step 2: Implement.**
- [ ] **Step 3: Commit.**

---

### Task 19: claude-cli stream-json parser

**Files:**
- Create: `src/python/bhdr/eval/agents/cli_parsers.py`
- Test: `tests/unit/python/test_cli_parsers_claude.py`
- Fixture: `tests/unit/python/fixtures/claude_stream.jsonl`

The parser reads NDJSON events from `claude -p --output-format stream-json`. For each event:
- `type: "assistant"` with `content` containing `tool_use` blocks → increment `tool_calls`, append name to `tool_sequence`
- `type: "assistant"` `usage.input_tokens` / `usage.output_tokens` → sum
- final `type: "result"` event → `result.text` is the diagnosis

- [ ] **Step 1: Capture a minimal stream-json fixture** by running claude on a tiny prompt. Trim to 10 events. Save to fixture file.
- [ ] **Step 2: Write tests** asserting parser yields correct `CliRunMetrics`.
- [ ] **Step 3: Implement `parse_claude_stream_json(stdout: str, stderr: str) -> CliRunMetrics`.**
- [ ] **Step 4: Run, commit.**

```bash
git commit -m "feat(eval): claude-cli stream-json parser for CliAgent"
```

---

### Task 20: codex-cli NDJSON parser

**Files:**
- Modify: `src/python/bhdr/eval/agents/cli_parsers.py`
- Test: `tests/unit/python/test_cli_parsers_codex.py`
- Fixture: `tests/unit/python/fixtures/codex_events.jsonl`

Parser handles codex's `--json` event stream:
- `local_shell_call` events whose argv starts with `gpa` → increment `tool_calls`, append `"gpa <subcommand>"` to `tool_sequence`
- token-usage events → sum
- final assistant message → diagnosis

If the codex event format differs from the claude shape, parsers stay separate; sharing happens only in the dispatcher.

- [ ] **Step 1: Capture fixture** by running `codex exec --json -s read-only --skip-git-repo-check "echo test"` and trimming.
- [ ] **Step 2: Inspect fixture; document the actual event names in a docstring.**
- [ ] **Step 3: Write tests.**
- [ ] **Step 4: Implement `parse_codex_ndjson(stdout, stderr)`.**
- [ ] **Step 5: If stream isn't usable for tokens, fall back to extracting from stderr summary lines (codex prints a token tally).**
- [ ] **Step 6: Run, commit.**

```bash
git commit -m "feat(eval): codex-cli NDJSON parser for CliAgent"
```

---

### Task 21: `CliAgent.run` implementation

**Files:**
- Create: `src/python/bhdr/eval/agents/cli_agent.py`
- Test: `tests/unit/python/test_cli_agent.py`

Skeleton:

```python
class CliAgent(AgentBackend):
    def __init__(self, spec: CliBackendSpec, *, model: str | None = None):
        self._spec = spec
        self._model = model

    def run(self, scenario, mode, tools):
        env = os.environ.copy()
        # Pin frame_id (with-gla mode runs the binary first)
        if mode == "with_bhdr":
            frame_id = tools["run_with_capture"]()
            env["BHDR_FRAME_ID"] = str(frame_id)
        env["BHDR_BASE_URL"] = env.get("BHDR_BASE_URL", "http://127.0.0.1:18080")
        if "BHDR_TOKEN" not in env and "token" in tools:
            env["BHDR_TOKEN"] = tools["token"]
        if scenario.source_path:
            env["BHDR_SOURCE_ROOT"] = str(Path(scenario.source_path).parent)
        if tools.get("snapshot_root"):
            env["BHDR_UPSTREAM_ROOT"] = str(tools["snapshot_root"])

        prompt = self._render_prompt(scenario, mode, tools)
        argv = [self._spec.binary, *self._spec.base_args]
        if self._model:
            argv = self._inject_model(argv, self._model)

        t0 = time.time()
        proc = subprocess.run(
            argv, input=prompt, capture_output=True, text=True,
            env=env, timeout=self._spec.timeout_sec,
        )
        elapsed = time.time() - t0
        metrics = self._spec.parse_run(proc.stdout, proc.stderr)
        return AgentResult(
            diagnosis=metrics.diagnosis,
            input_tokens=metrics.input_tokens,
            output_tokens=metrics.output_tokens,
            total_tokens=metrics.input_tokens + metrics.output_tokens,
            tool_calls=metrics.tool_calls,
            num_turns=metrics.num_turns,
            time_seconds=elapsed,
            conversation=[],            # CLI loop is opaque — empty
            tool_sequence=metrics.tool_sequence,
            pixel_queries=metrics.tool_sequence.count("gpa pixel get"),
            state_queries=(metrics.tool_sequence.count("gpa drawcalls explain")
                           + metrics.tool_sequence.count("gpa scene get")),
            framebuffer_first=_fb_first(metrics.tool_sequence),
        )

    def _render_prompt(self, scenario, mode, tools) -> str: ...
    def _inject_model(self, argv, model) -> list[str]: ...
```

- [ ] **Step 1: Write tests** — fake subprocess via `monkeypatch.setattr(subprocess, "run", ...)`, fake spec, assert `AgentResult` is built correctly.
- [ ] **Step 2: Implement** the class plus `_render_prompt(scenario, mode, tools)`. Prompt content:

```
You are debugging an OpenGL application that has a rendering bug.

Available tools (run via your shell):
- gpa frames overview                    — current frame summary
- gpa drawcalls list                     — list draw calls
- gpa drawcalls explain --dc N           — deep dive on a draw call
- gpa pixel get --x X --y Y              — read pixel color/depth/stencil
- gpa scene find --predicate STRING      — predicate-driven scene search
- gpa scene explain --x X --y Y          — pixel→draw→node trace
- gpa source read PATH                   — read a file from the buggy app
- gpa upstream read PATH                 — read a file from the upstream snapshot
- gpa upstream grep PATTERN              — grep the upstream snapshot
- gpa --help                             — discover more

BHDR_FRAME_ID is set so --frame is automatic.

Problem:
{scenario.description}

Source file: {scenario.source_path}

Investigate and end your final response with:
DIAGNOSIS: <one-sentence root cause>
FIX: <specific code change>
```

For `mode == "code_only"`, omit the OpenGPA tools and only list `gpa source` / `gpa upstream` plus the buggy-app source path.

- [ ] **Step 3: Test prompt rendering** — verify the right tool list is selected per mode.
- [ ] **Step 4: Run tests, commit.**

```bash
git commit -m "feat(eval): CliAgent driving CLI subprocess + prompt rendering"
```

---

### Task 22: Spec presets

**Files:**
- Modify: `src/python/bhdr/eval/agents/cli_agent.py` — append module-level `CLAUDE_CLI_SPEC` and `CODEX_CLI_SPEC`.

```python
CLAUDE_CLI_SPEC = CliBackendSpec(
    name="claude-cli",
    binary="claude",
    base_args=("-p", "--output-format", "stream-json", "--verbose"),
    parse_run=parse_claude_stream_json,
)

CODEX_CLI_SPEC = CliBackendSpec(
    name="codex-cli",
    binary="codex",
    base_args=(
        "exec", "--json",
        "-s", "workspace-write",
        "--skip-git-repo-check",
    ),
    parse_run=parse_codex_ndjson,
)
```

For codex, `-s workspace-write` is required because the agent writes nothing — but `read-only` blocks `gpa source read`'s file IO inside the sandbox. Verify which sandbox mode actually allows the eval to read the harness-rooted files; if `read-only` works, prefer it.

- [ ] **Step 1: Write a smoke test** that constructs each preset and asserts `parse_run` returns reasonable defaults on the empty-string input (no events).
- [ ] **Step 2: Implement.**
- [ ] **Step 3: Commit.**

```bash
git commit -m "feat(eval): claude-cli and codex-cli backend presets"
```

---

### Task 23: `factory.build_agent_fn`

**Files:**
- Create: `src/python/bhdr/eval/agents/factory.py`
- Test: `tests/unit/python/test_agents_factory.py`

```python
def build_agent_fn(
    backend: str,
    *,
    model: str | None = None,
    max_turns: int = 20,
    api_key: str | None = None,
) -> AgentFn:
    if backend == "api":
        from gpa.eval.agents.api_agent import build_agent_fn as _api
        return _api(model=model or "claude-sonnet-4-5", max_turns=max_turns,
                    api_key=api_key)
    if backend == "claude-cli":
        agent = CliAgent(spec=CLAUDE_CLI_SPEC, model=model)
        return _wrap(agent)
    if backend == "codex-cli":
        agent = CliAgent(spec=CODEX_CLI_SPEC, model=model)
        return _wrap(agent)
    raise ValueError(f"unknown agent backend: {backend!r}")


def _wrap(agent: AgentBackend) -> AgentFn:
    def fn(scenario, mode, tools):
        result = agent.run(scenario, mode, tools)
        return (result.diagnosis, result.input_tokens, result.output_tokens,
                result.tool_calls, result.num_turns, result.time_seconds)
    return fn
```

- [ ] **Step 1: Tests** — assert each backend value yields a callable, assert unknown backend raises.
- [ ] **Step 2: Implement.**
- [ ] **Step 3: Commit.**

```bash
git commit -m "feat(eval): factory.build_agent_fn dispatches api/claude-cli/codex-cli"
```

---

## Phase 4 — Curation LLM client codex backend

### Task 24: Extract `_CliLLMClient` base + add `CodexCliLLMClient`

**Files:**
- Modify: `src/python/bhdr/eval/curation/llm_client.py`
- Test: `tests/unit/python/test_curation_llm_client.py`

The current `ClaudeCodeLLMClient.complete()` is ~30 lines of subprocess plumbing. Extract a `_CliLLMClient` base whose `complete()` shells out to `[binary, *extra_args]` with the combined system+user prompt on stdin.

- [ ] **Step 1: Add tests for `CodexCliLLMClient`** mirroring the `ClaudeCodeLLMClient` tests; mock `subprocess.run`.
- [ ] **Step 2: Refactor:**

```python
class _CliLLMClient:
    def __init__(self, binary: str, *, extra_args=(), timeout=300):
        self._bin = binary
        self._extra = list(extra_args)
        self._timeout = timeout

    def complete(self, system, messages, cache_system=True, max_tokens=None):
        prompt = self._render_prompt(system, messages)
        argv = self._build_argv()
        # ... subprocess.run, return LLMResponse with zero token counts ...

    def _build_argv(self) -> list[str]: ...   # subclass override


class ClaudeCodeLLMClient(_CliLLMClient):
    def __init__(self, claude_bin="claude", timeout=300, extra_args=None):
        super().__init__(
            claude_bin,
            extra_args=("-p", "--output-format", "text", *(extra_args or ())),
            timeout=timeout,
        )

    def _build_argv(self):
        return [self._bin, *self._extra]


class CodexCliLLMClient(_CliLLMClient):
    def __init__(self, codex_bin="codex", timeout=300, extra_args=None):
        super().__init__(
            codex_bin,
            extra_args=(
                "exec",
                "--skip-git-repo-check",
                "-s", "read-only",
                *(extra_args or ()),
            ),
            timeout=timeout,
        )

    def _build_argv(self):
        return [self._bin, *self._extra]
```

- [ ] **Step 3: Run all curation tests, expect pass.**
- [ ] **Step 4: Commit.**

```bash
git commit -m "feat(curation): CodexCliLLMClient + _CliLLMClient base"
```

---

### Task 25: Wire `codex-cli` into `gen_queries`

**Files:**
- Modify: `src/python/bhdr/eval/curation/gen_queries.py`
- Test: `tests/unit/python/test_curation_gen_queries.py` (extend existing tests if present, else new)

Change `--llm-backend` choices to `["api", "claude-cli", "codex-cli"]`. Add the `codex-cli` branch to `_build_llm_client`.

- [ ] **Step 1: Tests** — assert the factory returns a `CodexCliLLMClient` for `--llm-backend codex-cli`.
- [ ] **Step 2: Update CLI argparse and factory.**
- [ ] **Step 3: Commit.**

```bash
git commit -m "feat(curation): gen_queries --llm-backend codex-cli"
```

---

## Phase 5 — Wire backend selection through entry points

### Task 26: `gpa.eval.cli` adopts factory

**Files:**
- Modify: `src/python/bhdr/eval/cli.py`

Replace the `_stub_agent` default with `factory.build_agent_fn(backend, model=...)`. Add CLI flags:

```python
run_p.add_argument(
    "--agent-backend", default="api",
    choices=["api", "claude-cli", "codex-cli"],
    help="Which agent backend to drive (default: api)",
)
run_p.add_argument(
    "--agent-model", default=None,
    help="Model identifier passed to the backend (default: backend-specific)",
)
```

Resolve `agent_fn` as:

```python
from gpa.eval.agents.factory import build_agent_fn as build_real_agent
agent_fn = build_real_agent(
    backend=args.agent_backend,
    model=args.agent_model,
    api_key=os.environ.get("ANTHROPIC_API_KEY"),
)
```

`_stub_agent` stays only as a fallback for `--dry-run` if we want one — defer that flag.

- [ ] **Step 1: Unit test** — patch `gpa.eval.cli.build_real_agent` to return a stub callable; assert `--agent-backend codex-cli` reaches the factory with the correct backend kwarg, *without* invoking any real CLI or API. The existing `_stub_agent` is preserved as the test default so `--dry-run` style usage continues to work.
- [ ] **Step 2: Live smoke test** (skipif `ANTHROPIC_API_KEY` missing): `python -m bhdr.eval.cli run --scenario X --mode code_only --agent-backend api`. Assert exit 0 on a tiny scenario.
- [ ] **Step 3: Implement.** Keep `_stub_agent` reachable via an unused `--dry-run` flag (or just leave it defined; it's small and harmless).
- [ ] **Step 4: Commit.**

```bash
git commit -m "feat(eval): gpa.eval.cli --agent-backend selects api/claude-cli/codex-cli"
```

---

### Task 27: `gpa.eval.curation.run` wires `--backend`

**Files:**
- Modify: `src/python/bhdr/eval/curation/run.py`

The existing `--backend` flag currently does nothing (line ~128 in run.py). Wire it through to `factory.build_agent_fn` when `--evaluate` is passed.

- [ ] **Step 1: Find where `RunEval` is constructed in `run.py`.** Replace any default `agent_fn` with `factory.build_agent_fn(backend=args.backend, ...)`.
- [ ] **Step 2: Update `--backend` choices to `["auto", "api", "claude-cli", "codex-cli"]`** (where `auto` resolves to `api` if `ANTHROPIC_API_KEY` else `claude-cli`).
- [ ] **Step 3: Test** with a small fake scenario via `--max-phase select`-style guarding to keep the test fast.
- [ ] **Step 4: Commit.**

```bash
git commit -m "feat(curation): wire --backend through to factory.build_agent_fn"
```

---

## Phase 6 — MCP deprecation + companion skill

### Task 28: MCP deprecation notice

**Files:**
- Modify: `src/python/bhdr/mcp/server.py` (top docstring)
- Modify: `src/python/bhdr/mcp/README.md` (top banner)

Add to `server.py` module docstring:

```
.. deprecated:: 0.x
   The OpenGPA MCP server is deprecated in favor of the ``gpa`` CLI,
   which agents can call via their built-in shell tool with much lower
   per-turn token cost. See ``docs/cli/agent-integration.md``. The MCP
   server remains importable but is no longer the recommended agent
   integration. Physical removal scheduled in 4 weeks.
```

Add equivalent banner to `mcp/README.md`.

- [ ] **Step 1: Edit the two files.**
- [ ] **Step 2: Audit `import gpa.mcp` callers** — `grep -rn "from gpa.mcp\|import gpa.mcp" src/ tests/`. None should be in default code paths; document any that are.
- [ ] **Step 3: Commit.**

```bash
git commit -m "docs(mcp): mark MCP server deprecated; cli is the new agent integration"
```

---

### Task 29: Companion skill content

**Files:**
- Create: `docs/cli/agent-integration.md`
- Create: `.codex/skills/gpa/SKILL.md`
- Create: `.claude/skills/gpa/SKILL.md`

Write `docs/cli/agent-integration.md` covering: when to use, env (`BHDR_BASE_URL`, `BHDR_TOKEN`, `BHDR_FRAME_ID`, `BHDR_SOURCE_ROOT`, `BHDR_UPSTREAM_ROOT`), frame workflow, drawcall workflow, pixel/scene workflow, source/upstream workflow, "do not do without approval" list (`gpa control pause/resume/step`, `gpa annotations add`, `gpa frames metadata set`, `gpa drawcalls sources set`), three example invocations.

Skill stubs at `.codex/skills/gpa/SKILL.md` and `.claude/skills/gpa/SKILL.md`:

```markdown
---
name: gpa
description: Use when debugging an OpenGPA-captured graphics scenario via the gpa CLI.
---

See [docs/cli/agent-integration.md](../../../docs/cli/agent-integration.md).
```

- [ ] **Step 1: Write the doc.** Mirror the structure codex's `cli-creator` skill suggested (under §"Companion Skill Outline" of the spec).
- [ ] **Step 2: Write the two skill stubs.**
- [ ] **Step 3: Commit.**

```bash
git commit -m "docs(cli): companion skill + agent-integration guide"
```

---

### Task 30: End-to-end smoke test

**Files:**
- Create: `tests/integration/test_eval_codex_smoke.py`

Pick the smallest existing eval scenario. Run it end-to-end with `--agent-backend codex-cli --mode code_only`. Skip if `codex` binary missing. Skip if `CI` env var not set (the test is heavy).

```python
@pytest.mark.skipif(
    shutil.which("codex") is None,
    reason="codex CLI not installed",
)
@pytest.mark.slow
def test_codex_eval_e1_state_leak_code_only(tmp_path, monkeypatch):
    from gpa.eval.harness import EvalHarness
    from gpa.eval.agents.factory import build_agent_fn

    harness = EvalHarness(config={...})
    agent_fn = build_agent_fn(backend="codex-cli", model=None)
    result = harness.run_scenario(
        "e1_state_leak", "code_only", agent_fn,
    )
    assert result.diagnosis_text  # non-empty
    assert result.tool_calls >= 1  # agent called at least one gpa command
```

- [ ] **Step 1: Write test.**
- [ ] **Step 2: Run it.** Iterate on the prompt or parser until it works on at least one scenario.
- [ ] **Step 3: Commit.**

```bash
git commit -m "test(eval): smoke test for codex-cli backend on e1_state_leak"
```

---

## Verification checklist

After completing all tasks:

- [ ] `bazel test //tests/unit/core/... //tests/unit/shims/...` passes.
- [ ] `PYTHONPATH=src/python python -m pytest tests/unit/python/ -q` passes.
- [ ] `gpa --help` shows the new noun-verb commands; old commands print stderr deprecation warnings but still work.
- [ ] `python -m bhdr.eval.cli run --scenario e1_state_leak --mode code_only --agent-backend codex-cli` produces a diagnosis.
- [ ] `python -m bhdr.eval.curation.gen_queries --instruction "..." --llm-backend codex-cli ...` produces a queries file.
- [ ] `src/python/bhdr/mcp/server.py` and `src/python/bhdr/mcp/README.md` carry deprecation notices.
- [ ] `docs/cli/agent-integration.md` exists and lists every new command with a one-line example.

## Open questions resolved during implementation

- BC aliases for renamed CLI commands: kept for one release with stderr deprecation, removed in next.
- `gpa doctor` / `gpa request`: deferred — not in this plan.
- MCP physical removal: 4-week follow-up via `/schedule`.
- Codex `exec` event format: verified during Task 20 against a real fixture; parser implementation is fixture-driven.

## Risks

- **CLI parser fragility:** stream-json/codex log parsing depends on undocumented output formats. Tasks 19 and 20 each pin against a fixture; a CLI-version assertion at the spec level catches drift.
- **Subprocess timeouts:** default 1800 s per scenario via `CliBackendSpec.timeout_sec`. Tune as needed.
- **`gpa source` env-var coupling:** the harness must set `BHDR_SOURCE_ROOT` on every CLI-agent invocation. Test 21 checks this contract.
