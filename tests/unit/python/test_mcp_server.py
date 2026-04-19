"""Tests for the MCP server's ``gpa_report`` / ``gpa_check`` tools.

We reuse the same TestClient-backed REST app the rest of the suite uses
and wrap it in a thin ``APIClient`` stand-in so the MCP dispatcher code
path runs unchanged.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

from gpa.api.app import create_app
from gpa.backends.native import NativeBackend
from gpa.mcp import server as mcp_server
from starlette.testclient import TestClient


AUTH_TOKEN = "test-token"


class _TestClientAPI:
    """APIClient shape (``.get``/``.post``) routed through a TestClient."""

    def __init__(self, test_client: TestClient):
        self._tc = test_client
        self.base_url = "http://testserver/api/v1"
        self.token = AUTH_TOKEN

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {AUTH_TOKEN}"}

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = "/api/v1" + path
        resp = self._tc.get(url, params=params or None, headers=self._headers())
        if resp.status_code >= 400:
            return {"error": resp.status_code, "detail": resp.text}
        return resp.json()

    def post(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = "/api/v1" + path
        resp = self._tc.post(url, params=params or None, headers=self._headers())
        if resp.status_code >= 400:
            return {"error": resp.status_code, "detail": resp.text}
        return resp.json()


# --------------------------------------------------------------------------- #
# Fixtures: a full mock QueryEngine + app we can tweak per-test
# --------------------------------------------------------------------------- #


def _make_app_client(qe: MagicMock) -> TestClient:
    eng = MagicMock()
    eng.is_running.return_value = True
    provider = NativeBackend(qe, engine=eng)
    app = create_app(provider=provider, auth_token=AUTH_TOKEN)
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def api_client(client) -> _TestClientAPI:
    """Wrap the default conftest TestClient as an APIClient stand-in."""
    return _TestClientAPI(client)


# --------------------------------------------------------------------------- #
# gpa_report
# --------------------------------------------------------------------------- #


def test_gpa_report_tool_is_registered():
    names = [t["name"] for t in mcp_server.TOOLS]
    assert "gpa_report" in names
    assert "gpa_check" in names
    assert "gpa_report" in mcp_server._DISPATCH
    assert "gpa_check" in mcp_server._DISPATCH


def test_gpa_report_tool_returns_structured_json(api_client):
    """Default mock frame has a feedback loop (tex 7 bound as sampler AND
    COLOR_ATTACHMENT0) and a NaN uniform. Run the tool and assert the
    report surfaces both findings in a machine-readable shape."""
    text = mcp_server._tool_gpa_report(api_client, {"frame_id": 1})
    payload = json.loads(text)

    assert payload["frame"] == 1
    assert payload["warning_count"] >= 1

    check_by_name = {c["name"]: c for c in payload["checks"]}
    assert "feedback-loops" in check_by_name
    fl = check_by_name["feedback-loops"]
    assert fl["status"] == "warn"
    assert any(
        f.get("texture_id") == 7 and f.get("dc_id") == 0
        for f in fl["findings"]
    )
    # NaN uniforms flagged too.
    assert check_by_name["nan-uniforms"]["status"] == "warn"


def test_gpa_report_handles_empty_capture():
    """Frame with zero draw calls: empty-capture check must warn."""
    qe = MagicMock()
    ov = MagicMock()
    ov.frame_id = 1
    ov.draw_call_count = 0
    ov.clear_count = 0
    ov.fb_width = 800
    ov.fb_height = 600
    ov.timestamp = 0.0
    qe.latest_frame_overview.return_value = ov
    qe.frame_overview.side_effect = lambda fid: ov if fid == 1 else None
    qe.list_draw_calls.side_effect = lambda fid, limit=50, offset=0: []
    qe.get_draw_call.side_effect = lambda fid, dcid: None

    api = _TestClientAPI(_make_app_client(qe))
    text = mcp_server._tool_gpa_report(api, {"frame_id": 1})
    payload = json.loads(text)

    assert payload["frame"] == 1
    by_name = {c["name"]: c for c in payload["checks"]}
    assert by_name["empty-capture"]["status"] == "warn"


def test_gpa_report_latest_resolves(api_client):
    """`latest` should resolve to the current frame via /frames/current/overview."""
    text = mcp_server._tool_gpa_report(api_client, {"frame_id": "latest"})
    payload = json.loads(text)
    assert payload["frame"] == 1  # conftest latest_frame_overview → frame_id=1


def test_gpa_report_only_filter(api_client):
    text = mcp_server._tool_gpa_report(
        api_client, {"frame_id": 1, "only": ["empty-capture"]}
    )
    payload = json.loads(text)
    names = {c["name"] for c in payload["checks"]}
    assert names == {"empty-capture"}


def test_gpa_report_skip_filter(api_client):
    text = mcp_server._tool_gpa_report(
        api_client,
        {"frame_id": 1, "skip": ["feedback-loops", "nan-uniforms"]},
    )
    payload = json.loads(text)
    names = {c["name"] for c in payload["checks"]}
    assert "feedback-loops" not in names
    assert "nan-uniforms" not in names
    assert "empty-capture" in names


# --------------------------------------------------------------------------- #
# gpa_check
# --------------------------------------------------------------------------- #


def test_gpa_check_tool_returns_detail(api_client):
    text = mcp_server._tool_gpa_check(
        api_client, {"check_name": "feedback-loops", "frame_id": 1}
    )
    payload = json.loads(text)
    assert payload["frame"] == 1
    assert payload["check"] == "feedback-loops"
    assert payload["status"] == "warn"
    assert payload["findings"]
    # The finding for the colliding texture should expose machine-readable
    # fields (summary + texture_id + dc_id).
    first = payload["findings"][0]
    assert "summary" in first
    assert first.get("texture_id") == 7
    assert first.get("dc_id") == 0


def test_gpa_check_unknown_name_returns_error(api_client):
    text = mcp_server._tool_gpa_check(
        api_client, {"check_name": "does-not-exist", "frame_id": 1}
    )
    payload = json.loads(text)
    assert "error" in payload
    assert "does-not-exist" in payload["error"]
    assert "known" in payload
    # Builtin checks must all be advertised so agents can self-correct.
    assert "feedback-loops" in payload["known"]


def test_gpa_check_empty_capture_ok(api_client):
    text = mcp_server._tool_gpa_check(
        api_client, {"check_name": "empty-capture", "frame_id": 1}
    )
    payload = json.loads(text)
    assert payload["check"] == "empty-capture"
    assert payload["status"] == "ok"


def test_gpa_check_missing_check_name_returns_error(api_client):
    text = mcp_server._tool_gpa_check(api_client, {"frame_id": 1})
    payload = json.loads(text)
    assert "error" in payload
    assert "known" in payload


def test_gpa_check_with_dc_id(api_client):
    """Passing dc_id should restrict the drill-down to that draw call."""
    text = mcp_server._tool_gpa_check(
        api_client,
        {"check_name": "feedback-loops", "frame_id": 1, "dc_id": 0},
    )
    payload = json.loads(text)
    assert payload["status"] == "warn"
    assert payload["findings"]
    assert payload["findings"][0]["dc_id"] == 0
