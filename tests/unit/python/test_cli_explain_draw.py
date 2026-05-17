"""Tests for ``gpa explain-draw`` and ``gpa diff-draws`` CLI commands."""
from __future__ import annotations

import io
import json
import struct
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from bhdr.api.app import create_app
from bhdr.backends.native import NativeBackend
from bhdr.cli.commands import diff_draws as diff_cmd
from bhdr.cli.commands import explain_draw as ed_cmd
from bhdr.cli.rest_client import RestClient, RestError

from conftest import AUTH_TOKEN, _make_drawcall


@pytest.fixture
def session_dir(tmp_path) -> Path:
    d = tmp_path / "sess"
    d.mkdir()
    (d / "token").write_text(AUTH_TOKEN)
    (d / "port").write_text("18080")
    (d / "shm-name").write_text("/gpa-test")
    return d


def _qe_with(draws):
    qe = MagicMock()
    ov = MagicMock()
    ov.frame_id = 1
    ov.draw_call_count = len(draws)
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
    qe.get_pixel.return_value = None
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
# explain-draw
# ---------------------------------------------------------------------------


class TestExplainDrawCli:
    def test_basic_human(self, session_dir, monkeypatch):
        monkeypatch.setenv("GPA_SESSION", str(session_dir))
        dc = _make_drawcall(0); dc.debug_groups = ["Scene", "Helmet"]
        http_client = _make_test_client([dc])
        buf = io.StringIO()
        rc = ed_cmd.run(
            draw_id=0, client=_injected(http_client), print_stream=buf,
        )
        assert rc == 0
        out = buf.getvalue()
        assert "draw 0" in out
        assert "Scene/Helmet" in out

    def test_json_output(self, session_dir, monkeypatch):
        monkeypatch.setenv("GPA_SESSION", str(session_dir))
        dc = _make_drawcall(0); dc.debug_groups = ["A"]
        http_client = _make_test_client([dc])
        buf = io.StringIO()
        rc = ed_cmd.run(
            draw_id=0, client=_injected(http_client), print_stream=buf,
            json_output=True,
        )
        assert rc == 0
        data = json.loads(buf.getvalue())
        assert data["draw_call_id"] == 0
        assert data["scene_node_path"] == "A"

    def test_field_filter(self, session_dir, monkeypatch):
        monkeypatch.setenv("GPA_SESSION", str(session_dir))
        dc = _make_drawcall(0); dc.debug_groups = ["A"]
        http_client = _make_test_client([dc])
        buf = io.StringIO()
        rc = ed_cmd.run(
            draw_id=0, field="state", client=_injected(http_client),
            print_stream=buf,
        )
        assert rc == 0
        out = buf.getvalue()
        # 'name' line should NOT appear (since field=state only).
        assert "node " not in out
        assert "state" in out

    def test_unknown_field_exit_2(self, session_dir, monkeypatch, capsys):
        monkeypatch.setenv("GPA_SESSION", str(session_dir))
        rc = ed_cmd.run(draw_id=0, field="bogus")
        assert rc == 2

    def test_invalid_frame_exit_2(self, session_dir, monkeypatch):
        monkeypatch.setenv("GPA_SESSION", str(session_dir))
        rc = ed_cmd.run(draw_id=0, frame="abc")
        assert rc == 2

    def test_missing_session_exit_2(self, tmp_path, monkeypatch):
        from bhdr.cli import session as session_mod
        monkeypatch.delenv("GPA_SESSION", raising=False)
        monkeypatch.setattr(
            session_mod, "CURRENT_SESSION_LINK",
            str(tmp_path / "no-such-link"),
        )
        rc = ed_cmd.run(draw_id=0)
        assert rc == 2

    def test_missing_draw_exit_1(self, session_dir, monkeypatch):
        monkeypatch.setenv("GPA_SESSION", str(session_dir))
        http_client = _make_test_client([_make_drawcall(0)])
        rc = ed_cmd.run(
            draw_id=999, client=_injected(http_client),
            print_stream=io.StringIO(),
        )
        assert rc == 1

    def test_stdin_pipeline(self, session_dir, monkeypatch):
        monkeypatch.setenv("GPA_SESSION", str(session_dir))
        dc = _make_drawcall(0); dc.debug_groups = ["A"]
        http_client = _make_test_client([dc])
        buf = io.StringIO()
        rc = ed_cmd.run(
            draw_id=0, client=_injected(http_client), print_stream=buf,
            frame="-", stdin_stream=io.StringIO("1\n"),
        )
        assert rc == 0


# ---------------------------------------------------------------------------
# diff-draws
# ---------------------------------------------------------------------------


def _draw(dc_id, *, blend=False, depth_test=True, prog=7, debug_groups=None):
    dc = _make_drawcall(dc_id)
    dc.id = dc_id
    dc.shader_id = prog
    dc.pipeline.blend_enabled = blend
    dc.pipeline.depth_test = depth_test
    dc.debug_groups = list(debug_groups or [])
    return dc


class TestDiffDrawsCli:
    def test_state_default(self, session_dir, monkeypatch):
        monkeypatch.setenv("GPA_SESSION", str(session_dir))
        a = _draw(0, blend=False)
        b = _draw(1, blend=True)
        http_client = _make_test_client([a, b])
        buf = io.StringIO()
        rc = diff_cmd.run(
            a=0, b=1, client=_injected(http_client), print_stream=buf,
        )
        assert rc == 0
        assert "GL_BLEND" in buf.getvalue()

    def test_uniforms_scope(self, session_dir, monkeypatch):
        monkeypatch.setenv("GPA_SESSION", str(session_dir))
        u_a = MagicMock(); u_a.name = "uOpacity"; u_a.type = 0x1406
        u_a.data = struct.pack("<f", 1.0)
        u_b = MagicMock(); u_b.name = "uOpacity"; u_b.type = 0x1406
        u_b.data = struct.pack("<f", 0.4)
        a = _draw(0); a.params = [u_a]
        b = _draw(1); b.params = [u_b]
        http_client = _make_test_client([a, b])
        buf = io.StringIO()
        rc = diff_cmd.run(
            a=0, b=1, scope="uniforms",
            client=_injected(http_client), print_stream=buf,
        )
        assert rc == 0
        assert "uOpacity" in buf.getvalue()

    def test_same_draw_empty(self, session_dir, monkeypatch):
        monkeypatch.setenv("GPA_SESSION", str(session_dir))
        a = _draw(0)
        http_client = _make_test_client([a])
        buf = io.StringIO()
        rc = diff_cmd.run(
            a=0, b=0, client=_injected(http_client), print_stream=buf,
        )
        assert rc == 0
        assert "no differences" in buf.getvalue()

    def test_missing_draw_exit_1(self, session_dir, monkeypatch):
        monkeypatch.setenv("GPA_SESSION", str(session_dir))
        a = _draw(0)
        http_client = _make_test_client([a])
        rc = diff_cmd.run(
            a=0, b=99, client=_injected(http_client),
            print_stream=io.StringIO(),
        )
        assert rc == 1

    def test_invalid_scope_exit_2(self, session_dir, monkeypatch):
        monkeypatch.setenv("GPA_SESSION", str(session_dir))
        rc = diff_cmd.run(a=0, b=1, scope="xyz")
        assert rc == 2

    def test_json_output(self, session_dir, monkeypatch):
        monkeypatch.setenv("GPA_SESSION", str(session_dir))
        a = _draw(0, blend=False); b = _draw(1, blend=True)
        http_client = _make_test_client([a, b])
        buf = io.StringIO()
        rc = diff_cmd.run(
            a=0, b=1, json_output=True,
            client=_injected(http_client), print_stream=buf,
        )
        assert rc == 0
        data = json.loads(buf.getvalue())
        assert data["a"] == 0 and data["b"] == 1
