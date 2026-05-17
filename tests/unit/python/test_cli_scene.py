"""Tests for ``gpa scene`` CLI namespace.

Uses a _CapturingClient that records (method, path) tuples so we can
assert the right REST path is constructed, without spinning up a real HTTP
server.  The run_* helpers in scene.py accept an injected ``client``
kwarg so tests never touch argparse or Session discovery.
"""
from __future__ import annotations

import io
import json
from typing import Any, Dict, Optional

import pytest

from bhdr.cli.commands import scene as scene_mod


# --------------------------------------------------------------------------- #
# Fake client
# --------------------------------------------------------------------------- #


class _CapturingClient:
    """Records every REST call and returns a canned response."""

    def __init__(self, responses: Optional[Dict[str, Any]] = None):
        self._responses: Dict[str, Any] = responses or {}
        self.calls: list = []

    def get_json(self, path: str):
        self.calls.append(("GET", path))
        return self._responses.get(path, {"ok": True})


# Fixed frame_id returned by the "current" overview fallback.
_CURRENT_FID = 7
_CURRENT_OV_PATH = "/api/v1/frames/current/overview"


def _client(**extra_paths) -> _CapturingClient:
    """Return a client that resolves frame=7 via the current-overview fallback."""
    responses: Dict[str, Any] = {_CURRENT_OV_PATH: {"frame_id": _CURRENT_FID}}
    responses.update(extra_paths)
    return _CapturingClient(responses)


# --------------------------------------------------------------------------- #
# scene get
# --------------------------------------------------------------------------- #


def test_get_hits_correct_url(monkeypatch):
    monkeypatch.delenv("BHDR_FRAME_ID", raising=False)
    client = _client()
    buf = io.StringIO()
    rc = scene_mod.run_get(client=client, frame=None, print_stream=buf)
    assert rc == 0
    assert ("GET", f"/api/v1/frames/{_CURRENT_FID}/scene") in client.calls


def test_get_output_is_json_passthrough(monkeypatch):
    monkeypatch.delenv("BHDR_FRAME_ID", raising=False)
    payload = {"camera": {"fov": 45}, "objects": []}
    path = f"/api/v1/frames/{_CURRENT_FID}/scene"
    client = _client(**{path: payload})
    buf = io.StringIO()
    scene_mod.run_get(client=client, frame=None, print_stream=buf)
    parsed = json.loads(buf.getvalue())
    assert parsed == payload


# --------------------------------------------------------------------------- #
# scene camera
# --------------------------------------------------------------------------- #


def test_camera_hits_correct_url(monkeypatch):
    monkeypatch.delenv("BHDR_FRAME_ID", raising=False)
    client = _client()
    buf = io.StringIO()
    rc = scene_mod.run_camera(client=client, frame=None, print_stream=buf)
    assert rc == 0
    assert ("GET", f"/api/v1/frames/{_CURRENT_FID}/scene/camera") in client.calls


# --------------------------------------------------------------------------- #
# scene objects
# --------------------------------------------------------------------------- #


def test_objects_hits_correct_url(monkeypatch):
    monkeypatch.delenv("BHDR_FRAME_ID", raising=False)
    client = _client()
    buf = io.StringIO()
    rc = scene_mod.run_objects(client=client, frame=None, print_stream=buf)
    assert rc == 0
    assert ("GET", f"/api/v1/frames/{_CURRENT_FID}/scene/objects") in client.calls


def test_objects_limit_offset_query_params(monkeypatch):
    monkeypatch.delenv("BHDR_FRAME_ID", raising=False)
    path = f"/api/v1/frames/{_CURRENT_FID}/scene/objects?limit=5&offset=10"
    client = _client(**{path: {"objects": []}})
    buf = io.StringIO()
    rc = scene_mod.run_objects(
        client=client, frame=None, limit=5, offset=10, print_stream=buf
    )
    assert rc == 0
    assert ("GET", path) in client.calls


# --------------------------------------------------------------------------- #
# scene find
# --------------------------------------------------------------------------- #


def test_find_hits_correct_url(monkeypatch):
    monkeypatch.delenv("BHDR_FRAME_ID", raising=False)
    from urllib.parse import urlencode
    qs = urlencode({"predicate": "material:transparent", "limit": 10})
    path = f"/api/v1/frames/{_CURRENT_FID}/scene/find?{qs}"
    client = _client(**{path: {"matches": []}})
    buf = io.StringIO()
    rc = scene_mod.run_find(
        client=client, frame=None, predicate="material:transparent",
        limit=10, print_stream=buf,
    )
    assert rc == 0
    assert ("GET", path) in client.calls


def test_find_default_limit(monkeypatch):
    monkeypatch.delenv("BHDR_FRAME_ID", raising=False)
    client = _client()
    buf = io.StringIO()
    # Should not raise; default limit=10 appended
    rc = scene_mod.run_find(
        client=client, frame=None, predicate="type:Mesh", print_stream=buf
    )
    assert rc == 0
    # Verify limit=10 appears in the URL
    urls = [path for (_, path) in client.calls if "scene/find" in path]
    assert len(urls) == 1
    assert "limit=10" in urls[0]


# --------------------------------------------------------------------------- #
# scene explain
# --------------------------------------------------------------------------- #


def test_explain_hits_correct_url(monkeypatch):
    monkeypatch.delenv("BHDR_FRAME_ID", raising=False)
    client = _client()
    buf = io.StringIO()
    rc = scene_mod.run_explain(client=client, frame=None, x=200, y=150, print_stream=buf)
    assert rc == 0
    assert ("GET", f"/api/v1/frames/{_CURRENT_FID}/explain-pixel?x=200&y=150") in client.calls


# --------------------------------------------------------------------------- #
# --frame env-var fallback (shared across subverbs)
# --------------------------------------------------------------------------- #


def test_get_frame_env_fallback(monkeypatch):
    monkeypatch.setenv("BHDR_FRAME_ID", "3")
    path = "/api/v1/frames/3/scene"
    client = _client(**{path: {"camera": None, "objects": []}})
    buf = io.StringIO()
    rc = scene_mod.run_get(client=client, frame=None, print_stream=buf)
    assert rc == 0
    assert ("GET", path) in client.calls


def test_explicit_frame_overrides_env(monkeypatch):
    monkeypatch.setenv("BHDR_FRAME_ID", "3")
    path = "/api/v1/frames/5/scene/camera"
    client = _client(**{path: {"fov": 60}})
    buf = io.StringIO()
    rc = scene_mod.run_camera(client=client, frame="5", print_stream=buf)
    assert rc == 0
    assert ("GET", path) in client.calls
