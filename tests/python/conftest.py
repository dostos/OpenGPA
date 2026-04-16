"""Shared pytest fixtures for GLA REST API tests.

All C++ (_gla_core) types are mocked — no native extension needed at test time.
"""
import base64
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from gla.api.app import create_app

AUTH_TOKEN = "test-token"
AUTH_HEADERS = {"Authorization": f"Bearer {AUTH_TOKEN}"}


@pytest.fixture
def auth_headers() -> dict:
    """Authorization headers with the test Bearer token."""
    return AUTH_HEADERS.copy()


# ---------------------------------------------------------------------------
# Helpers to build realistic mock objects
# ---------------------------------------------------------------------------


def _make_overview(frame_id: int = 1) -> MagicMock:
    ov = MagicMock()
    ov.frame_id = frame_id
    ov.draw_call_count = 42
    ov.framebuffer_width = 800
    ov.framebuffer_height = 600
    ov.timestamp = 1234.5
    return ov


def _make_drawcall(dc_id: int = 0, frame_id: int = 1) -> MagicMock:
    dc = MagicMock()
    dc.id = dc_id
    dc.draw_call_index = dc_id
    dc.primitive_type = "TRIANGLES"
    dc.vertex_count = 3
    dc.instance_count = 1
    dc.index_count = 0
    dc.base_vertex = 0
    dc.program_id = 7
    ps = MagicMock()
    ps.blend_enabled = False
    ps.depth_test_enabled = True
    ps.depth_write_enabled = True
    ps.stencil_test_enabled = False
    ps.cull_face_enabled = True
    ps.cull_face_mode = "BACK"
    ps.blend_src_rgb = "ONE"
    ps.blend_dst_rgb = "ZERO"
    ps.depth_func = "LESS"
    dc.pipeline_state = ps
    return dc


def _make_pixel_result() -> MagicMock:
    pr = MagicMock()
    pr.r = 255
    pr.g = 0
    pr.b = 128
    pr.a = 255
    pr.depth = 0.5
    pr.stencil = 0
    return pr


def _make_shader() -> MagicMock:
    shader = MagicMock()
    shader.vertex_source = "void main(){}"
    shader.fragment_source = "void main(){}"
    param = MagicMock()
    param.name = "uColor"
    param.type = "vec4"
    param.value = [1.0, 0.0, 0.0, 1.0]
    shader.parameters = [param]
    return shader


def _make_texture() -> MagicMock:
    tex = MagicMock()
    tex.unit = 0
    tex.texture_id = 3
    tex.target = "TEXTURE_2D"
    tex.width = 512
    tex.height = 512
    tex.internal_format = "RGBA8"
    return tex


def _make_vertices() -> MagicMock:
    verts = MagicMock()
    verts.vao_id = 1
    attr = MagicMock()
    attr.index = 0
    attr.size = 3
    attr.type = "FLOAT"
    attr.normalized = False
    attr.stride = 12
    attr.offset = 0
    verts.attributes = [attr]
    return verts


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_query_engine() -> MagicMock:
    """QueryEngine mock with preset return values covering the happy path."""
    qe = MagicMock()

    # Frame overview
    qe.get_current_frame_overview.return_value = _make_overview(frame_id=1)
    qe.get_frame_overview.side_effect = lambda fid: (
        _make_overview(frame_id=fid) if fid == 1 else None
    )

    # Framebuffer
    fb = MagicMock()
    fb.width = 800
    fb.height = 600
    fb.rgba_bytes = bytes(800 * 600 * 4)
    qe.get_framebuffer.side_effect = lambda fid: fb if fid == 1 else None

    depth_fb = MagicMock()
    depth_fb.width = 800
    depth_fb.height = 600
    depth_fb.depth_bytes = bytes(800 * 600 * 4)  # float32 per pixel
    qe.get_framebuffer_depth.side_effect = lambda fid: depth_fb if fid == 1 else None

    # Draw calls
    dc = _make_drawcall(dc_id=0)
    qe.get_drawcalls.side_effect = lambda fid, limit=50, offset=0: (
        [dc] if fid == 1 else None
    )
    qe.get_drawcall_count.side_effect = lambda fid: 1 if fid == 1 else 0
    qe.get_drawcall.side_effect = lambda fid, dcid: (
        dc if (fid == 1 and dcid == 0) else None
    )

    # Shader / textures / vertices
    qe.get_shader.return_value = _make_shader()
    qe.get_textures.return_value = [_make_texture()]
    qe.get_vertices.return_value = _make_vertices()

    # Pixel
    qe.query_pixel.side_effect = lambda fid, x, y: (
        _make_pixel_result()
        if (fid == 1 and 0 <= x < 800 and 0 <= y < 600)
        else None
    )

    return qe


@pytest.fixture
def mock_engine() -> MagicMock:
    """Engine mock for pause/resume/step/status control operations."""
    eng = MagicMock()
    eng.is_running.return_value = True
    return eng


@pytest.fixture
def client(mock_query_engine, mock_engine) -> TestClient:
    """TestClient with Bearer token pre-configured."""
    app = create_app(
        query_engine=mock_query_engine,
        engine=mock_engine,
        auth_token=AUTH_TOKEN,
    )
    return TestClient(app, raise_server_exceptions=True)
