"""Tests for ``gpa passes`` CLI namespace."""
from __future__ import annotations

import io
import json
from typing import Any, Dict, Optional

import pytest

from gpa.cli.commands import passes as passes_mod


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


_CURRENT_FID = 7
_CURRENT_OV_PATH = "/api/v1/frames/current/overview"


def _client(**extra_paths) -> _CapturingClient:
    responses: Dict[str, Any] = {_CURRENT_OV_PATH: {"frame_id": _CURRENT_FID}}
    responses.update(extra_paths)
    return _CapturingClient(responses)


# --------------------------------------------------------------------------- #
# passes list
# --------------------------------------------------------------------------- #


def test_list_hits_correct_url(monkeypatch):
    monkeypatch.delenv("GPA_FRAME_ID", raising=False)
    client = _client()
    buf = io.StringIO()
    rc = passes_mod.run_list(client=client, frame=None, print_stream=buf)
    assert rc == 0
    assert ("GET", f"/api/v1/frames/{_CURRENT_FID}/passes") in client.calls


def test_list_output_is_json_passthrough(monkeypatch):
    monkeypatch.delenv("GPA_FRAME_ID", raising=False)
    payload = {"frame_id": _CURRENT_FID, "passes": [{"name": "shadows"}]}
    path = f"/api/v1/frames/{_CURRENT_FID}/passes"
    client = _client(**{path: payload})
    buf = io.StringIO()
    passes_mod.run_list(client=client, frame=None, print_stream=buf)
    assert json.loads(buf.getvalue()) == payload


# --------------------------------------------------------------------------- #
# passes get
# --------------------------------------------------------------------------- #


def test_get_hits_correct_url(monkeypatch):
    monkeypatch.delenv("GPA_FRAME_ID", raising=False)
    client = _client()
    buf = io.StringIO()
    rc = passes_mod.run_get(client=client, frame=None, name="shadows", print_stream=buf)
    assert rc == 0
    assert ("GET", f"/api/v1/frames/{_CURRENT_FID}/passes/shadows") in client.calls


def test_get_with_explicit_frame(monkeypatch):
    monkeypatch.delenv("GPA_FRAME_ID", raising=False)
    path = "/api/v1/frames/3/passes/opaque"
    client = _client(**{path: {"name": "opaque"}})
    buf = io.StringIO()
    rc = passes_mod.run_get(client=client, frame="3", name="opaque", print_stream=buf)
    assert rc == 0
    assert ("GET", path) in client.calls
