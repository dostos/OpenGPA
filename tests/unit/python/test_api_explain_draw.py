"""Tests for ``GET /api/v1/frames/{frame_id}/draws/{draw_id}/explain``
and ``GET /api/v1/frames/{frame_id}/draws/diff``."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from bhdr.api.app import create_app
from bhdr.backends.native import NativeBackend

from conftest import AUTH_HEADERS, AUTH_TOKEN, _make_drawcall


def _client_with(qe: MagicMock, *, annotation=None) -> TestClient:
    provider = NativeBackend(qe, engine=None)
    app = create_app(provider=provider, auth_token=AUTH_TOKEN)
    if annotation is not None:
        app.state.annotations.put(1, annotation)
    return TestClient(app, raise_server_exceptions=True)


def _qe_with_draws(draws):
    qe = MagicMock()
    ov = MagicMock()
    ov.frame_id = 1
    ov.draw_call_count = len(draws)
    ov.fb_width = 800
    ov.fb_height = 600
    ov.timestamp = 0.0
    ov.clear_count = 0
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


# ---------------------------------------------------------------------------
# explain-draw endpoint
# ---------------------------------------------------------------------------


class TestExplainDrawHappy:
    def test_basic_shape(self):
        dc = _make_drawcall(dc_id=0)
        dc.debug_groups = ["Scene", "Player", "Helmet"]
        client = _client_with(_qe_with_draws([dc]))
        r = client.get("/api/v1/frames/1/draws/0/explain", headers=AUTH_HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert data["frame_id"] == 1
        assert data["draw_call_id"] == 0
        assert data["scene_node_path"] == "Scene/Player/Helmet"
        assert data["debug_groups"] == ["Scene", "Player", "Helmet"]
        assert "uniforms_set" in data
        assert "textures_sampled" in data
        assert "relevant_state" in data

    def test_no_debug_groups(self):
        dc = _make_drawcall(dc_id=0)
        dc.debug_groups = []
        client = _client_with(_qe_with_draws([dc]))
        r = client.get("/api/v1/frames/1/draws/0/explain", headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert r.json()["scene_node_path"] is None

    def test_latest_alias(self):
        dc = _make_drawcall(dc_id=0)
        dc.debug_groups = ["A"]
        client = _client_with(_qe_with_draws([dc]))
        r = client.get("/api/v1/frames/latest/draws/0/explain",
                       headers=AUTH_HEADERS)
        assert r.status_code == 200

    def test_relevant_state_keys(self):
        dc = _make_drawcall(dc_id=0)
        client = _client_with(_qe_with_draws([dc]))
        r = client.get("/api/v1/frames/1/draws/0/explain", headers=AUTH_HEADERS)
        st = r.json()["relevant_state"]
        assert set(st.keys()) == {"GL_DEPTH_TEST", "GL_BLEND", "GL_CULL_FACE"}

    def test_with_annotation_resolves_material(self):
        dc = _make_drawcall(dc_id=0)
        dc.debug_groups = ["Scene", "Helmet"]
        annotation = {
            "threejs-link": {
                "scene": [
                    {"path": "Scene/Helmet", "uuid": "abc",
                     "type": "Mesh",
                     "material": {"name": "Helmet", "transparent": True}},
                ],
            },
        }
        client = _client_with(_qe_with_draws([dc]), annotation=annotation)
        r = client.get("/api/v1/frames/1/draws/0/explain", headers=AUTH_HEADERS)
        data = r.json()
        assert data["material_name"] == "Helmet"
        assert data["scene_node_uuid"] == "abc"

    def test_uniforms_truncation(self):
        dc = _make_drawcall(dc_id=0)
        # Build many decoded uniforms.
        params = []
        import struct
        for i in range(15):
            mp = MagicMock()
            mp.name = f"u{i}"
            mp.type = 0x1406  # GL_FLOAT
            mp.data = struct.pack("<f", float(i))
            params.append(mp)
        dc.params = params
        client = _client_with(_qe_with_draws([dc]))
        r = client.get("/api/v1/frames/1/draws/0/explain", headers=AUTH_HEADERS)
        u = r.json()["uniforms_set"]
        assert u["truncated"] is True
        assert len(u["items"]) == 8


class TestExplainDrawErrors:
    def test_unknown_draw_404(self):
        client = _client_with(_qe_with_draws([_make_drawcall(0)]))
        r = client.get("/api/v1/frames/1/draws/99/explain", headers=AUTH_HEADERS)
        assert r.status_code == 404

    def test_unknown_frame_404(self):
        client = _client_with(_qe_with_draws([_make_drawcall(0)]))
        r = client.get("/api/v1/frames/9999/draws/0/explain", headers=AUTH_HEADERS)
        assert r.status_code == 404

    def test_missing_auth_401(self):
        client = _client_with(_qe_with_draws([_make_drawcall(0)]))
        r = client.get("/api/v1/frames/1/draws/0/explain")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# diff-draws endpoint
# ---------------------------------------------------------------------------


def _drawcall_with(*, dc_id, blend=False, depth_test=True, prog=7,
                   debug_groups=None, params=None):
    """Build a customised mock drawcall (to avoid mutating the shared one)."""
    dc = _make_drawcall(dc_id=dc_id)
    dc.id = dc_id
    dc.shader_id = prog
    dc.pipeline.blend_enabled = blend
    dc.pipeline.depth_test = depth_test
    dc.debug_groups = list(debug_groups or [])
    if params is not None:
        dc.params = params
    return dc


class TestDiffDrawsHappy:
    def test_state_default_scope(self):
        a = _drawcall_with(dc_id=0, blend=False, depth_test=True)
        b = _drawcall_with(dc_id=1, blend=True, depth_test=False)
        client = _client_with(_qe_with_draws([a, b]))
        r = client.get("/api/v1/frames/1/draws/diff?a=0&b=1",
                       headers=AUTH_HEADERS)
        assert r.status_code == 200
        data = r.json()
        keys = [c["key"] for c in data["changes"]]
        assert "GL_BLEND" in keys
        assert "GL_DEPTH_TEST" in keys

    def test_uniforms_scope(self):
        import struct
        u_a = MagicMock(); u_a.name = "uOpacity"; u_a.type = 0x1406
        u_a.data = struct.pack("<f", 1.0)
        u_b = MagicMock(); u_b.name = "uOpacity"; u_b.type = 0x1406
        u_b.data = struct.pack("<f", 0.4)
        a = _drawcall_with(dc_id=0, params=[u_a])
        b = _drawcall_with(dc_id=1, params=[u_b])
        client = _client_with(_qe_with_draws([a, b]))
        r = client.get("/api/v1/frames/1/draws/diff?a=0&b=1&scope=uniforms",
                       headers=AUTH_HEADERS)
        data = r.json()
        keys = [c["key"] for c in data["changes"]]
        assert "uniform:uOpacity" in keys

    def test_textures_scope(self):
        a = _drawcall_with(dc_id=0)
        b = _drawcall_with(dc_id=1)
        # mutate b's first texture id
        b.textures[0].texture_id = 99
        client = _client_with(_qe_with_draws([a, b]))
        r = client.get("/api/v1/frames/1/draws/diff?a=0&b=1&scope=textures",
                       headers=AUTH_HEADERS)
        keys = [c["key"] for c in r.json()["changes"]]
        assert any(k.startswith("texture:unit") for k in keys)

    def test_all_scope(self):
        a = _drawcall_with(dc_id=0, blend=False, depth_test=True)
        b = _drawcall_with(dc_id=1, blend=True, depth_test=False)
        client = _client_with(_qe_with_draws([a, b]))
        r = client.get("/api/v1/frames/1/draws/diff?a=0&b=1&scope=all",
                       headers=AUTH_HEADERS)
        data = r.json()
        assert data["scope"] == "all"
        assert data["changes"]

    def test_same_draw_empty_diff(self):
        a = _drawcall_with(dc_id=0)
        client = _client_with(_qe_with_draws([a]))
        r = client.get("/api/v1/frames/1/draws/diff?a=0&b=0",
                       headers=AUTH_HEADERS)
        assert r.status_code == 200
        assert r.json()["changes"] == []

    def test_a_node_b_node(self):
        a = _drawcall_with(dc_id=0, debug_groups=["A"])
        b = _drawcall_with(dc_id=1, debug_groups=["B"])
        client = _client_with(_qe_with_draws([a, b]))
        r = client.get("/api/v1/frames/1/draws/diff?a=0&b=1",
                       headers=AUTH_HEADERS)
        data = r.json()
        assert data["a_node"] == "A"
        assert data["b_node"] == "B"


class TestDiffDrawsErrors:
    def test_missing_a(self):
        client = _client_with(_qe_with_draws([_make_drawcall(0)]))
        r = client.get("/api/v1/frames/1/draws/diff?b=0", headers=AUTH_HEADERS)
        assert r.status_code == 400

    def test_missing_b(self):
        client = _client_with(_qe_with_draws([_make_drawcall(0)]))
        r = client.get("/api/v1/frames/1/draws/diff?a=0", headers=AUTH_HEADERS)
        assert r.status_code == 400

    def test_unknown_draw_404(self):
        client = _client_with(_qe_with_draws([_make_drawcall(0)]))
        r = client.get("/api/v1/frames/1/draws/diff?a=0&b=99",
                       headers=AUTH_HEADERS)
        assert r.status_code == 404

    def test_invalid_scope_400(self):
        client = _client_with(_qe_with_draws([_make_drawcall(0)]))
        r = client.get("/api/v1/frames/1/draws/diff?a=0&b=0&scope=xyz",
                       headers=AUTH_HEADERS)
        assert r.status_code == 400
