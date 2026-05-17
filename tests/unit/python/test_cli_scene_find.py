"""Tests for ``gpa scene-find`` and ``gpa scene-explain`` CLI commands."""
from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from bhdr.api.app import create_app
from bhdr.backends.native import NativeBackend
from bhdr.cli.commands import scene_explain as se_cmd
from bhdr.cli.commands import scene_find as sf_cmd
from bhdr.cli.rest_client import RestClient, RestError

from conftest import AUTH_TOKEN, _make_drawcall


@pytest.fixture
def session_dir(tmp_path) -> Path:
    d = tmp_path / "sess"
    d.mkdir()
    (d / "token").write_text(AUTH_TOKEN)
    (d / "port").write_text("18080")
    (d / "shm-name").write_text("/bhdr-test")
    return d


def _qe_with(draws):
    qe = MagicMock()
    ov = MagicMock()
    ov.frame_id = 1; ov.draw_call_count = len(draws)
    ov.fb_width = 800; ov.fb_height = 600
    ov.timestamp = 0.0; ov.clear_count = 0
    qe.latest_frame_overview.return_value = ov
    qe.frame_overview.side_effect = lambda fid: ov if fid == 1 else None
    qe.list_draw_calls.side_effect = lambda fid, limit=50, offset=0: (
        list(draws) if fid == 1 else []
    )
    qe.get_draw_call.side_effect = lambda fid, did: (
        draws[did] if fid == 1 and 0 <= did < len(draws) else None
    )
    pr = MagicMock()
    pr.r = 100; pr.g = 150; pr.b = 200; pr.a = 255
    pr.depth = 0.5; pr.stencil = 0
    qe.get_pixel.side_effect = lambda fid, x, y: pr if fid == 1 else None
    return qe


def _make_test_client(draws, annotation=None):
    provider = NativeBackend(_qe_with(draws), engine=None)
    app = create_app(provider=provider, auth_token=AUTH_TOKEN)
    if annotation is not None:
        app.state.annotations.put(1, annotation)
    return TestClient(app, raise_server_exceptions=True)


def _injected(http_client):
    def http_callable(method, path, headers, body=None):
        if method == "GET":
            resp = http_client.get(path, headers=headers)
        elif method == "POST":
            resp = http_client.post(path, headers=headers, content=body)
        else:  # pragma: no cover
            raise AssertionError(f"unsupported method {method}")
        if resp.status_code >= 400:
            raise RestError(
                f"{method} {path} → HTTP {resp.status_code}",
                status=resp.status_code,
            )
        if not resp.content:
            return None
        return resp.json()
    return RestClient(token=AUTH_TOKEN, http_callable=http_callable)


# ---------------------------------------------------------------------------
# scene-find
# ---------------------------------------------------------------------------


def _annotation(nodes):
    return {"threejs-link": {"scene": list(nodes)}}


class TestSceneFindCli:
    def test_missing_predicate_exit_2(self, session_dir, monkeypatch):
        monkeypatch.setenv("BHDR_SESSION", str(session_dir))
        rc = sf_cmd.run(predicates=[])
        assert rc == 2

    def test_negative_limit_exit_2(self, session_dir, monkeypatch):
        monkeypatch.setenv("BHDR_SESSION", str(session_dir))
        rc = sf_cmd.run(predicates=["material:transparent"], limit=0)
        assert rc == 2

    def test_invalid_frame_exit_2(self, session_dir, monkeypatch):
        monkeypatch.setenv("BHDR_SESSION", str(session_dir))
        rc = sf_cmd.run(predicates=["material:transparent"], frame="abc")
        assert rc == 2

    def test_no_annotation_exit_1(self, session_dir, monkeypatch):
        monkeypatch.setenv("BHDR_SESSION", str(session_dir))
        http_client = _make_test_client([_make_drawcall(0)])
        rc = sf_cmd.run(
            predicates=["material:transparent"],
            client=_injected(http_client), print_stream=io.StringIO(),
        )
        assert rc == 1

    def test_match_human(self, session_dir, monkeypatch):
        monkeypatch.setenv("BHDR_SESSION", str(session_dir))
        dc = _make_drawcall(0); dc.debug_groups = ["Helmet"]
        annotation = _annotation([
            {"path": "Helmet", "type": "Mesh",
             "material": {"name": "Helmet", "transparent": True}},
        ])
        http_client = _make_test_client([dc], annotation=annotation)
        buf = io.StringIO()
        rc = sf_cmd.run(
            predicates=["material:transparent"],
            client=_injected(http_client), print_stream=buf,
        )
        assert rc == 0
        assert "Helmet" in buf.getvalue()

    def test_match_json(self, session_dir, monkeypatch):
        monkeypatch.setenv("BHDR_SESSION", str(session_dir))
        dc = _make_drawcall(0); dc.debug_groups = ["Helmet"]
        annotation = _annotation([
            {"path": "Helmet", "type": "Mesh",
             "material": {"name": "Helmet", "transparent": True}},
        ])
        http_client = _make_test_client([dc], annotation=annotation)
        buf = io.StringIO()
        rc = sf_cmd.run(
            predicates=["material:transparent"], json_output=True,
            client=_injected(http_client), print_stream=buf,
        )
        assert rc == 0
        data = json.loads(buf.getvalue())
        assert data["match_count"] == 1

    def test_unknown_predicate_exit_2(self, session_dir, monkeypatch):
        monkeypatch.setenv("BHDR_SESSION", str(session_dir))
        annotation = _annotation([{"path": "X"}])
        http_client = _make_test_client([_make_drawcall(0)],
                                        annotation=annotation)
        rc = sf_cmd.run(
            predicates=["bogus:foo"],
            client=_injected(http_client), print_stream=io.StringIO(),
        )
        # Server returns 400; CLI maps that to exit 2.
        assert rc == 2


# ---------------------------------------------------------------------------
# scene-explain --pixel
# ---------------------------------------------------------------------------


def _draw_at(dc_id, x, y, w, h, debug_groups=None):
    dc = _make_drawcall(dc_id); dc.id = dc_id
    dc.pipeline.viewport = (x, y, w, h)
    dc.debug_groups = list(debug_groups or [])
    return dc


class TestSceneExplainCli:
    def test_basic_human(self, session_dir, monkeypatch):
        monkeypatch.setenv("BHDR_SESSION", str(session_dir))
        dc = _draw_at(0, 0, 0, 800, 600, debug_groups=["A"])
        http_client = _make_test_client([dc])
        buf = io.StringIO()
        rc = se_cmd.run(
            pixel="100,100", client=_injected(http_client), print_stream=buf,
        )
        assert rc == 0
        assert "draw      0" in buf.getvalue()

    def test_basic_json(self, session_dir, monkeypatch):
        monkeypatch.setenv("BHDR_SESSION", str(session_dir))
        dc = _draw_at(0, 0, 0, 800, 600, debug_groups=["A"])
        http_client = _make_test_client([dc])
        buf = io.StringIO()
        rc = se_cmd.run(
            pixel="100,100", json_output=True,
            client=_injected(http_client), print_stream=buf,
        )
        data = json.loads(buf.getvalue())
        assert data["draw_call_id"] == 0
        assert data["resolved"] == "approximate"

    def test_invalid_pixel_format_exit_2(self, session_dir, monkeypatch):
        monkeypatch.setenv("BHDR_SESSION", str(session_dir))
        rc = se_cmd.run(pixel="abc")
        assert rc == 2

    def test_negative_pixel_exit_2(self, session_dir, monkeypatch):
        monkeypatch.setenv("BHDR_SESSION", str(session_dir))
        rc = se_cmd.run(pixel="-1,5")
        assert rc == 2

    def test_out_of_viewport_exit_3(self, session_dir, monkeypatch):
        monkeypatch.setenv("BHDR_SESSION", str(session_dir))
        dc = _draw_at(0, 0, 0, 800, 600)
        http_client = _make_test_client([dc])
        rc = se_cmd.run(
            pixel="999,200",
            client=_injected(http_client), print_stream=io.StringIO(),
        )
        assert rc == 3

    def test_no_match_exit_1(self, session_dir, monkeypatch):
        monkeypatch.setenv("BHDR_SESSION", str(session_dir))
        # Draw covers x<400; pixel at (700, 300) misses.
        dc = _draw_at(0, 0, 0, 400, 600)
        http_client = _make_test_client([dc])
        rc = se_cmd.run(
            pixel="700,300",
            client=_injected(http_client), print_stream=io.StringIO(),
        )
        assert rc == 1
