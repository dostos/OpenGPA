"""Tests for SnapshotFetcher — cache semantics + git command orchestration."""
from __future__ import annotations
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from bhdr.eval.snapshot_fetcher import (
    SnapshotFetcher, SnapshotRef, SnapshotError, DEFAULT_CACHE_ROOT,
)


def test_cache_key_github_https():
    ref = SnapshotRef(repo_url="https://github.com/mrdoob/three.js", sha="abc1234def56")
    assert ref.cache_key() == "github_com__mrdoob__three__abc1234def56"

def test_cache_key_truncates_long_sha():
    ref = SnapshotRef(repo_url="https://github.com/o/r",
                       sha="a" * 40)
    assert ref.cache_key().endswith("__" + "a" * 12)

def test_cache_key_lowercases_and_sanitizes():
    ref = SnapshotRef(repo_url="https://GitHub.COM/Foo-Bar/My.Repo",
                       sha="DEADBEEF")
    key = ref.cache_key()
    assert "github" in key
    assert "foo-bar" in key
    assert key.endswith("deadbeef")

def test_cache_key_fallback_for_unparseable_url():
    ref = SnapshotRef(repo_url="ssh://weird/location/thing",
                       sha="abc123")
    key = ref.cache_key()
    assert key.startswith("url_")

def test_fetch_returns_existing_cache_without_cloning(tmp_path):
    """If a .complete sentinel exists, fetch() is a no-op returning the path."""
    cache = tmp_path / "cache"
    ref = SnapshotRef(repo_url="https://github.com/o/r", sha="abc123")
    target = cache / ref.cache_key()
    target.mkdir(parents=True)
    (target / ".complete").write_text("")
    (target / "existing_file.txt").write_text("stays")

    fetcher = SnapshotFetcher(cache_root=cache)
    with patch("subprocess.run") as mock_run:
        result = fetcher.fetch(ref)
    assert result == target
    assert (target / "existing_file.txt").read_text() == "stays"
    mock_run.assert_not_called()

def test_fetch_clones_when_absent(tmp_path):
    """When cache is empty, fetch() runs git init/remote/fetch/reset."""
    cache = tmp_path / "cache"
    ref = SnapshotRef(repo_url="https://github.com/o/r", sha="abc123")

    fetcher = SnapshotFetcher(cache_root=cache)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = fetcher.fetch(ref)

    assert result == cache / ref.cache_key()
    # Verify .complete sentinel was written
    assert (result / ".complete").exists()
    # Verify git commands in order: init, remote add, fetch --depth 1, reset
    argvs = [call.args[0] for call in mock_run.call_args_list]
    kinds = [argv[1] for argv in argvs]
    assert kinds[0] == "init"
    assert kinds[1] == "remote"
    assert kinds[2] == "fetch"
    assert "--depth" in argvs[2]
    assert "abc123" in argvs[2]
    assert kinds[-1] == "reset"  # final command

def test_fetch_falls_back_when_sha_fetch_fails(tmp_path):
    """If `git fetch --depth 1 origin <sha>` fails, fall back to fetching
    the default branch at a deeper depth that covers typical PR histories."""
    cache = tmp_path / "cache"
    ref = SnapshotRef(repo_url="https://github.com/o/r", sha="abc123")
    fetcher = SnapshotFetcher(cache_root=cache)

    def run_mock(argv, **kwargs):
        # First fetch (by SHA) fails; everything else succeeds
        if argv[:2] == ["git", "fetch"] and "abc123" in argv:
            return MagicMock(returncode=1, stderr="Server does not allow request for unadvertised object abc123", stdout="")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=run_mock) as mock_run:
        result = fetcher.fetch(ref)

    # Should succeed via fallback
    assert (result / ".complete").exists()
    # There must be an additional fetch call (deeper fallback, no SHA arg)
    fetch_calls = [c.args[0] for c in mock_run.call_args_list if c.args[0][1] == "fetch"]
    assert len(fetch_calls) >= 2
    # The fallback fetch uses --depth 500 (deep enough to include merge commits)
    assert any("500" in argv for argv in fetch_calls)

def test_fetch_removes_stale_dir_without_sentinel(tmp_path):
    """If target dir exists but has no .complete, treat as stale (crashed
    prior fetch) — remove and clone fresh."""
    cache = tmp_path / "cache"
    ref = SnapshotRef(repo_url="https://github.com/o/r", sha="abc123")
    stale = cache / ref.cache_key()
    stale.mkdir(parents=True)
    (stale / "leftover_from_crash").write_text("garbage")
    # no .complete sentinel

    fetcher = SnapshotFetcher(cache_root=cache)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = fetcher.fetch(ref)

    assert result == stale
    assert (stale / ".complete").exists()
    # The garbage file from the stale fetch should be gone
    assert not (stale / "leftover_from_crash").exists()

def test_fetch_raises_on_complete_clone_failure(tmp_path):
    """If both direct-fetch and fallback-fetch fail, raise SnapshotError
    and leave no half-complete dir behind."""
    cache = tmp_path / "cache"
    ref = SnapshotRef(repo_url="https://github.com/o/r", sha="abc123")
    fetcher = SnapshotFetcher(cache_root=cache)

    def run_mock(argv, **kwargs):
        if argv[:2] == ["git", "fetch"]:
            return MagicMock(returncode=1, stderr="Network failed", stdout="")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=run_mock):
        with pytest.raises(SnapshotError):
            fetcher.fetch(ref)

    # No half-complete dir
    assert not (cache / ref.cache_key()).exists()

def test_is_cached(tmp_path):
    cache = tmp_path / "cache"
    ref = SnapshotRef(repo_url="https://github.com/o/r", sha="abc123")
    fetcher = SnapshotFetcher(cache_root=cache)
    assert fetcher.is_cached(ref) is False

    target = fetcher.cache_path(ref)
    target.mkdir(parents=True)
    (target / ".complete").write_text("")
    assert fetcher.is_cached(ref) is True

def test_purge_removes_cached_snapshot(tmp_path):
    cache = tmp_path / "cache"
    ref = SnapshotRef(repo_url="https://github.com/o/r", sha="abc123")
    target = cache / ref.cache_key()
    target.mkdir(parents=True)
    (target / "file").write_text("content")
    (target / ".complete").write_text("")

    fetcher = SnapshotFetcher(cache_root=cache)
    fetcher.purge(ref)
    assert not target.exists()
    # Purging a non-existent snapshot is a no-op
    fetcher.purge(ref)  # does not raise

def test_two_refs_same_repo_different_sha_use_different_cache_dirs(tmp_path):
    r1 = SnapshotRef(repo_url="https://github.com/o/r", sha="abc123")
    r2 = SnapshotRef(repo_url="https://github.com/o/r", sha="def456")
    assert r1.cache_key() != r2.cache_key()
    # Parent is the same
    fetcher = SnapshotFetcher(cache_root=tmp_path)
    assert fetcher.cache_path(r1).parent == fetcher.cache_path(r2).parent

def test_default_cache_root_is_data3():
    """When no cache_root passed, default is /data3/opengpa-snapshots."""
    f = SnapshotFetcher()
    assert str(f.cache_root) == "/data3/opengpa-snapshots"


def test_resolve_parent_changes_cache_key():
    """Caching `parent of <sha>` separately from `<sha>` itself avoids
    collisions when one scenario asks for the fix-applied tree and another
    asks for its parent (the buggy tree)."""
    direct = SnapshotRef(repo_url="https://github.com/o/r", sha="abc123def456")
    parent = SnapshotRef(
        repo_url="https://github.com/o/r", sha="abc123def456",
        resolve_parent=True,
    )
    assert direct.cache_key() != parent.cache_key()
    assert parent.cache_key().endswith("__parent")


def test_fetch_resolve_parent_uses_depth_2_and_resets_to_caret(tmp_path):
    """When resolve_parent is True, the fetcher needs to see <sha>'s parent
    too — fetch with depth=2 and reset --hard to <sha>^."""
    cache = tmp_path / "cache"
    ref = SnapshotRef(
        repo_url="https://github.com/o/r", sha="abc123",
        resolve_parent=True,
    )
    fetcher = SnapshotFetcher(cache_root=cache)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        fetcher.fetch(ref)
    argvs = [c.args[0] for c in mock_run.call_args_list]
    fetch_calls = [a for a in argvs if a[1] == "fetch"]
    reset_calls = [a for a in argvs if a[1] == "reset"]
    # Direct fetch should use --depth 2 (not 1) to include the parent commit.
    assert any("--depth" in a and "2" in a for a in fetch_calls), fetch_calls
    # Reset target should be <sha>^, not <sha> alone.
    assert any(arg.endswith("^") for argv in reset_calls for arg in argv), reset_calls


def test_fetch_resolve_parent_false_unchanged(tmp_path):
    """Default behavior (resolve_parent=False) must not change."""
    cache = tmp_path / "cache"
    ref = SnapshotRef(repo_url="https://github.com/o/r", sha="abc123")
    fetcher = SnapshotFetcher(cache_root=cache)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        fetcher.fetch(ref)
    argvs = [c.args[0] for c in mock_run.call_args_list]
    reset_calls = [a for a in argvs if a[1] == "reset"]
    assert reset_calls
    assert all(not arg.endswith("^") for argv in reset_calls for arg in argv)


def test_fetch_skips_unshallow_when_repo_is_complete(tmp_path):
    """When fallback 1 (--depth 500 origin) raises but the resulting repo
    is already complete (no .git/shallow), the fetcher must NOT try
    `git fetch --unshallow` — git fatals on that with
    "--unshallow on a complete repository does not make sense"."""
    cache = tmp_path / "cache"
    ref = SnapshotRef(repo_url="https://github.com/o/r", sha="abc123")
    fetcher = SnapshotFetcher(cache_root=cache)

    target = cache / ref.cache_key()

    def run_mock(argv, **kwargs):
        # Both the SHA fetch and the --depth 500 fallback fail
        if argv[:2] == ["git", "fetch"] and "abc123" in argv:
            return MagicMock(returncode=1, stderr="rejected", stdout="")
        if argv[:2] == ["git", "fetch"] and "500" in argv:
            return MagicMock(returncode=1, stderr="timeout", stdout="")
        # When the unshallow-or-plain fetch happens, simulate
        # complete-repo state by NOT having .git/shallow
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=run_mock) as mock_run:
        # Make sure target/.git exists but .git/shallow doesn't, so the
        # branch decides "repo is complete, skip --unshallow"
        result = fetcher.fetch(ref)

    assert (result / ".complete").exists()
    fetch_argvs = [c.args[0] for c in mock_run.call_args_list
                   if c.args[0][1] == "fetch"]
    # When .git/shallow is absent, the fetcher must use plain
    # `git fetch origin`, never `--unshallow`.
    unshallow_calls = [a for a in fetch_argvs if "--unshallow" in a]
    assert unshallow_calls == [], unshallow_calls


def test_fetch_uses_unshallow_when_repo_is_shallow(tmp_path):
    """Conversely, when .git/shallow IS present after the depth fetches,
    --unshallow is the correct command."""
    cache = tmp_path / "cache"
    ref = SnapshotRef(repo_url="https://github.com/o/r", sha="abc123")
    fetcher = SnapshotFetcher(cache_root=cache)

    target = cache / ref.cache_key()
    call_count = {"n": 0}

    def run_mock(argv, **kwargs):
        call_count["n"] += 1
        # Both depth fetches fail
        if argv[:2] == ["git", "fetch"] and "abc123" in argv:
            return MagicMock(returncode=1, stderr="rejected", stdout="")
        if argv[:2] == ["git", "fetch"] and "500" in argv:
            # Simulate a shallow repo state: create .git/shallow before
            # returning failure (mimicking git's behavior when --depth
            # creates shallow markers even on partial fetches)
            git_dir = target / ".git"
            git_dir.mkdir(parents=True, exist_ok=True)
            (git_dir / "shallow").write_text("deadbeef\n")
            return MagicMock(returncode=1, stderr="timeout", stdout="")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=run_mock) as mock_run:
        result = fetcher.fetch(ref)

    assert (result / ".complete").exists()
    fetch_argvs = [c.args[0] for c in mock_run.call_args_list
                   if c.args[0][1] == "fetch"]
    # When .git/shallow exists, --unshallow IS the right call
    unshallow_calls = [a for a in fetch_argvs if "--unshallow" in a]
    assert len(unshallow_calls) == 1, unshallow_calls


def test_fetch_holds_lock_across_concurrent_calls(tmp_path):
    """Two threads calling fetch() on the same SnapshotRef must not race.
    Without per-cache-key locking, one thread's `target.exists()` check
    sees the other's in-progress dir and rmtrees it, killing the in-flight
    clone (subprocess.run then fails with FileNotFoundError on cwd).
    The lock serializes them: the second call returns the first's cache."""
    import threading

    cache = tmp_path / "cache"
    ref = SnapshotRef(repo_url="https://github.com/o/r", sha="abc123")
    fetcher = SnapshotFetcher(cache_root=cache)

    barrier = threading.Barrier(2)
    results = {}
    errors = {}

    # Slow down the clone so the second caller is forced to wait on the
    # lock instead of finishing its own racing clone.
    def run_mock(argv, **kwargs):
        if argv[:2] == ["git", "fetch"]:
            import time
            time.sleep(0.05)
        return MagicMock(returncode=0, stdout="", stderr="")

    def worker(name):
        try:
            barrier.wait()
            with patch("subprocess.run", side_effect=run_mock):
                results[name] = fetcher.fetch(ref)
        except Exception as exc:
            errors[name] = exc

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert errors == {}, errors
    assert results["a"] == results["b"]
    assert (results["a"] / ".complete").exists()
