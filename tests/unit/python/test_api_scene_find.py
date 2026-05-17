"""Tests for ``GET /api/v1/frames/{frame_id}/scene/find`` and the
fallback ``POST /frames/{frame_id}/links`` endpoint."""
from __future__ import annotations

import struct

from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from bhdr.api.app import create_app
from bhdr.api.routes_scene_find import parse_predicates, PredicateError
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
# Predicate parser
# ---------------------------------------------------------------------------


class TestParsePredicates:
    def test_single_simple(self):
        r = parse_predicates(["material:transparent"])
        assert r == [("material:transparent", None)]

    def test_csv_and(self):
        r = parse_predicates(["material:transparent,uniform-has-nan"])
        assert ("material:transparent", None) in r
        assert ("uniform-has-nan", None) in r

    def test_repeated_args(self):
        r = parse_predicates(["material:transparent", "uniform-has-nan"])
        assert len(r) == 2

    def test_with_argument(self):
        r = parse_predicates(["material-name:Glass"])
        assert r == [("material-name", "Glass")]

    def test_unknown_raises(self):
        with pytest.raises(PredicateError):
            parse_predicates(["badpred:foo"])

    def test_empty_pieces_skipped(self):
        r = parse_predicates(["material:transparent,,"])
        assert r == [("material:transparent", None)]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


def _annotation_with(nodes):
    return {"threejs-link": {"scene": list(nodes)}}


class TestSceneFindBasics:
    def test_no_annotation_empty_match(self):
        client = _client_with(_qe_with_draws([_make_drawcall(0)]))
        r = client.get(
            "/api/v1/frames/1/scene/find?predicate=material:transparent",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["match_count"] == 0
        assert data["annotation_present"] is False

    def test_unknown_predicate_400(self):
        client = _client_with(_qe_with_draws([_make_drawcall(0)]))
        r = client.get(
            "/api/v1/frames/1/scene/find?predicate=badpred",
            headers=AUTH_HEADERS,
        )
        assert r.status_code == 400

    def test_no_predicate_400(self):
        client = _client_with(_qe_with_draws([_make_drawcall(0)]))
        r = client.get("/api/v1/frames/1/scene/find", headers=AUTH_HEADERS)
        assert r.status_code == 400


class TestPredicateMatching:
    def test_material_transparent_positive(self):
        dc = _make_drawcall(dc_id=0)
        dc.debug_groups = ["Scene", "Helmet"]
        annotation = _annotation_with([
            {"path": "Scene/Helmet", "type": "Mesh",
             "material": {"name": "Helmet", "transparent": True}},
            {"path": "Scene/Body", "type": "Mesh",
             "material": {"name": "Body", "transparent": False}},
        ])
        client = _client_with(_qe_with_draws([dc]), annotation=annotation)
        r = client.get(
            "/api/v1/frames/1/scene/find?predicate=material:transparent",
            headers=AUTH_HEADERS,
        )
        data = r.json()
        assert data["match_count"] == 1
        assert data["matches"][0]["path"] == "Scene/Helmet"
        assert data["matches"][0]["draw_call_ids"] == [0]

    def test_material_transparent_negative(self):
        annotation = _annotation_with([
            {"path": "X", "material": {"transparent": False}},
        ])
        client = _client_with(_qe_with_draws([]), annotation=annotation)
        r = client.get(
            "/api/v1/frames/1/scene/find?predicate=material:transparent",
            headers=AUTH_HEADERS,
        )
        assert r.json()["match_count"] == 0

    def test_material_name_substr(self):
        annotation = _annotation_with([
            {"path": "X", "material": {"name": "GlassPanel"}},
            {"path": "Y", "material": {"name": "Floor"}},
        ])
        client = _client_with(_qe_with_draws([]), annotation=annotation)
        r = client.get(
            "/api/v1/frames/1/scene/find?predicate=material-name:Glass",
            headers=AUTH_HEADERS,
        )
        data = r.json()
        assert data["match_count"] == 1
        assert data["matches"][0]["path"] == "X"

    def test_name_contains(self):
        annotation = _annotation_with([
            {"path": "Scene/Visor", "name": "Visor"},
            {"path": "Scene/Helmet", "name": "Helmet"},
        ])
        client = _client_with(_qe_with_draws([]), annotation=annotation)
        r = client.get(
            "/api/v1/frames/1/scene/find?predicate=name-contains:vis",
            headers=AUTH_HEADERS,
        )
        assert r.json()["match_count"] == 1

    def test_type_exact(self):
        annotation = _annotation_with([
            {"path": "Cam", "type": "PerspectiveCamera"},
            {"path": "Helmet", "type": "Mesh"},
        ])
        client = _client_with(_qe_with_draws([]), annotation=annotation)
        r = client.get(
            "/api/v1/frames/1/scene/find?predicate=type:Mesh",
            headers=AUTH_HEADERS,
        )
        assert r.json()["match_count"] == 1

    def test_uniform_has_nan_positive(self):
        # The default _make_drawcall() already includes a uniform with NaN.
        dc = _make_drawcall(dc_id=0)
        dc.debug_groups = ["Scene", "Helmet"]
        annotation = _annotation_with([
            {"path": "Scene/Helmet", "type": "Mesh"},
        ])
        client = _client_with(_qe_with_draws([dc]), annotation=annotation)
        r = client.get(
            "/api/v1/frames/1/scene/find?predicate=uniform-has-nan",
            headers=AUTH_HEADERS,
        )
        data = r.json()
        assert data["match_count"] == 1

    def test_uniform_has_nan_negative_when_finite(self):
        dc = _make_drawcall(dc_id=0)
        dc.debug_groups = ["Scene", "Helmet"]
        # Strip the bad NaN uniform; keep only finite uColor.
        finite = MagicMock()
        finite.name = "uColor"
        finite.type = 0x8B52
        finite.data = struct.pack("<4f", 1.0, 0.0, 0.0, 1.0)
        dc.params = [finite]
        annotation = _annotation_with([
            {"path": "Scene/Helmet", "type": "Mesh"},
        ])
        client = _client_with(_qe_with_draws([dc]), annotation=annotation)
        r = client.get(
            "/api/v1/frames/1/scene/find?predicate=uniform-has-nan",
            headers=AUTH_HEADERS,
        )
        assert r.json()["match_count"] == 0

    def test_texture_missing_positive(self):
        # Material references texture id 999 which is never bound.
        annotation = _annotation_with([
            {"path": "X", "type": "Mesh",
             "material": {"name": "X", "map_texture_id": 999}},
        ])
        # Provide a draw with texture_id 7 only (not 999).
        dc = _make_drawcall(dc_id=0)
        client = _client_with(_qe_with_draws([dc]), annotation=annotation)
        r = client.get(
            "/api/v1/frames/1/scene/find?predicate=texture:missing",
            headers=AUTH_HEADERS,
        )
        assert r.json()["match_count"] == 1

    def test_texture_missing_negative_when_present(self):
        # Material references texture id 7 which IS in the draw's bindings.
        annotation = _annotation_with([
            {"path": "X", "type": "Mesh",
             "material": {"name": "X", "map_texture_id": 7}},
        ])
        dc = _make_drawcall(dc_id=0)
        client = _client_with(_qe_with_draws([dc]), annotation=annotation)
        r = client.get(
            "/api/v1/frames/1/scene/find?predicate=texture:missing",
            headers=AUTH_HEADERS,
        )
        assert r.json()["match_count"] == 0

    def test_csv_and(self):
        # Match must satisfy BOTH transparent and name-contains:Helmet.
        annotation = _annotation_with([
            {"path": "Helmet", "name": "Helmet",
             "material": {"transparent": True}},
            {"path": "Body", "name": "Body",
             "material": {"transparent": True}},
            {"path": "OtherHelmet", "name": "OtherHelmet",
             "material": {"transparent": False}},
        ])
        client = _client_with(_qe_with_draws([]), annotation=annotation)
        r = client.get(
            "/api/v1/frames/1/scene/find?"
            "predicate=material:transparent,name-contains:Helmet",
            headers=AUTH_HEADERS,
        )
        data = r.json()
        assert data["match_count"] == 1
        assert data["matches"][0]["path"] == "Helmet"

    def test_limit_truncates(self):
        annotation = _annotation_with([
            {"path": f"X{i}", "type": "Mesh"} for i in range(20)
        ])
        client = _client_with(_qe_with_draws([]), annotation=annotation)
        r = client.get(
            "/api/v1/frames/1/scene/find?predicate=type:Mesh&limit=3",
            headers=AUTH_HEADERS,
        )
        data = r.json()
        assert data["match_count"] == 3
        assert data["truncated"] is True

    def test_path_with_slash_in_name(self):
        # Regression for the precondition fix: list-form debug_groups must
        # preserve names containing literal '/'.
        dc = _make_drawcall(dc_id=0)
        dc.debug_groups = ["Scene", "Player/Two", "Helmet"]
        # Plugin annotation joins with '/' for display, but uses the same
        # list-form when emitting markers.
        annotation = _annotation_with([
            {"path": "Scene/Player/Two/Helmet", "type": "Mesh"},
        ])
        client = _client_with(_qe_with_draws([dc]), annotation=annotation)
        r = client.get(
            "/api/v1/frames/1/scene/find?predicate=type:Mesh",
            headers=AUTH_HEADERS,
        )
        # The simple '/'-join cannot disambiguate; this regression test
        # documents the limitation. Accept that the response includes the
        # node (via path equality after join) AND that draw_call_ids are
        # populated.
        data = r.json()
        assert data["match_count"] == 1
        assert data["matches"][0]["draw_call_ids"] == [0]


# ---------------------------------------------------------------------------
# POST /frames/{id}/links — fallback for non-debug-marker plugins.
# ---------------------------------------------------------------------------


class TestLinksFallback:
    def test_records_dict_form(self):
        client = _client_with(_qe_with_draws([_make_drawcall(0)]))
        r = client.post(
            "/api/v1/frames/1/links",
            headers=AUTH_HEADERS,
            json={
                "records": [
                    {"drawcall_id": 0, "scene_node_uuid": "u",
                     "scene_node_path": "Scene/Helmet", "framework": "three.js"},
                ],
            },
        )
        assert r.status_code == 200
        assert r.json()["record_count"] == 1

    def test_records_list_form(self):
        client = _client_with(_qe_with_draws([_make_drawcall(0)]))
        r = client.post(
            "/api/v1/frames/1/links",
            headers=AUTH_HEADERS,
            json=[{"drawcall_id": 0, "scene_node_uuid": "u",
                   "scene_node_path": "Scene/Helmet", "framework": "three.js"}],
        )
        assert r.status_code == 200

    def test_records_single_form(self):
        client = _client_with(_qe_with_draws([_make_drawcall(0)]))
        r = client.post(
            "/api/v1/frames/1/links",
            headers=AUTH_HEADERS,
            json={"drawcall_id": 0, "scene_node_path": "X"},
        )
        assert r.status_code == 200

    def test_invalid_payload_400(self):
        client = _client_with(_qe_with_draws([_make_drawcall(0)]))
        r = client.post(
            "/api/v1/frames/1/links", headers=AUTH_HEADERS, json="oops",
        )
        assert r.status_code == 400
