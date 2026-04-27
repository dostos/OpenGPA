"""Tests for ``GET /api/v1/frames/{frame_id}/explain-pixel``."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from gpa.api.app import create_app
from gpa.backends.native import NativeBackend

from conftest import AUTH_HEADERS, AUTH_TOKEN, _make_drawcall


def _client_with(qe: MagicMock, *, annotation=None) -> TestClient:
    provider = NativeBackend(qe, engine=None)
    app = create_app(provider=provider, auth_token=AUTH_TOKEN)
    if annotation is not None:
        app.state.annotations.put(1, annotation)
    return TestClient(app, raise_server_exceptions=True)


def _qe_with_draws(draws, fb=(800, 600)):
    qe = MagicMock()
    ov = MagicMock()
    ov.frame_id = 1
    ov.draw_call_count = len(draws)
    ov.fb_width = fb[0]
    ov.fb_height = fb[1]
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
    pr = MagicMock()
    pr.r = 200; pr.g = 200; pr.b = 100; pr.a = 255
    pr.depth = 0.5; pr.stencil = 0
    qe.get_pixel.side_effect = lambda fid, x, y: pr if fid == 1 else None
    return qe


def _draw_with_viewport(dc_id, x, y, w, h, debug_groups=None):
    dc = _make_drawcall(dc_id=dc_id)
    dc.id = dc_id
    dc.pipeline.viewport = (x, y, w, h)
    dc.debug_groups = list(debug_groups or [])
    return dc


# ---------------------------------------------------------------------------
# Hit-test cases (spec asks for ≥4)
# ---------------------------------------------------------------------------


class TestPixelHitTest:
    def test_single_match(self):
        a = _draw_with_viewport(0, 0, 0, 800, 600, debug_groups=["A"])
        client = _client_with(_qe_with_draws([a]))
        r = client.get("/api/v1/frames/1/explain-pixel?x=100&y=100",
                       headers=AUTH_HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert data["draw_call_id"] == 0
        assert data["resolved"] == "approximate"
        assert data["scene_node_path"] == "A"

    def test_multi_match_topmost_wins(self):
        a = _draw_with_viewport(0, 0, 0, 800, 600, debug_groups=["Bottom"])
        b = _draw_with_viewport(1, 0, 0, 800, 600, debug_groups=["Top"])
        client = _client_with(_qe_with_draws([a, b]))
        r = client.get("/api/v1/frames/1/explain-pixel?x=400&y=300",
                       headers=AUTH_HEADERS)
        data = r.json()
        # Highest draw_id wins.
        assert data["draw_call_id"] == 1
        assert data["scene_node_path"] == "Top"

    def test_no_match_returns_miss(self):
        # Draw covers only x<400; pixel at (700, 300) misses.
        a = _draw_with_viewport(0, 0, 0, 400, 600, debug_groups=["Half"])
        client = _client_with(_qe_with_draws([a]))
        r = client.get("/api/v1/frames/1/explain-pixel?x=700&y=300",
                       headers=AUTH_HEADERS)
        data = r.json()
        assert data["draw_call_id"] is None
        assert data["resolved"] == "miss"

    def test_viewport_edge_inclusive_left_exclusive_right(self):
        # 0..800 covers x=0 (inclusive) but not x=800 (exclusive).
        a = _draw_with_viewport(0, 0, 0, 800, 600, debug_groups=["E"])
        client = _client_with(_qe_with_draws([a]))
        r1 = client.get("/api/v1/frames/1/explain-pixel?x=0&y=0",
                        headers=AUTH_HEADERS)
        assert r1.json()["draw_call_id"] == 0
        r2 = client.get("/api/v1/frames/1/explain-pixel?x=799&y=599",
                        headers=AUTH_HEADERS)
        assert r2.json()["draw_call_id"] == 0


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TestExplainPixelErrors:
    def test_out_of_viewport_400(self):
        a = _draw_with_viewport(0, 0, 0, 800, 600)
        client = _client_with(_qe_with_draws([a], fb=(800, 600)))
        r = client.get("/api/v1/frames/1/explain-pixel?x=999&y=200",
                       headers=AUTH_HEADERS)
        assert r.status_code == 400

    def test_negative_coords_400(self):
        client = _client_with(_qe_with_draws([_draw_with_viewport(0, 0, 0, 100, 100)]))
        r = client.get("/api/v1/frames/1/explain-pixel?x=-1&y=10",
                       headers=AUTH_HEADERS)
        assert r.status_code == 400

    def test_unknown_frame_404(self):
        client = _client_with(_qe_with_draws([_draw_with_viewport(0, 0, 0, 100, 100)]))
        r = client.get("/api/v1/frames/9999/explain-pixel?x=10&y=10",
                       headers=AUTH_HEADERS)
        assert r.status_code == 404

    def test_missing_auth_401(self):
        client = _client_with(_qe_with_draws([_draw_with_viewport(0, 0, 0, 100, 100)]))
        r = client.get("/api/v1/frames/1/explain-pixel?x=10&y=10")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Annotation enrichment
# ---------------------------------------------------------------------------


class TestExplainPixelAnnotation:
    def test_material_resolves(self):
        a = _draw_with_viewport(0, 0, 0, 800, 600,
                                debug_groups=["Scene", "Helmet"])
        annotation = {"threejs-link": {"scene": [
            {"path": "Scene/Helmet", "type": "Mesh",
             "material": {"name": "Helmet", "transparent": True}},
        ]}}
        client = _client_with(_qe_with_draws([a]), annotation=annotation)
        r = client.get("/api/v1/frames/1/explain-pixel?x=50&y=50",
                       headers=AUTH_HEADERS)
        data = r.json()
        assert data["material_name"] == "Helmet"
