"""Tests for /api/v1/frames/{frame_id}/drawcalls/* endpoints."""


class TestDrawCallList:
    def test_list_drawcalls_200(self, client, auth_headers):
        resp = client.get("/api/v1/frames/1/drawcalls", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["frame_id"] == 1
        assert isinstance(data["items"], list)
        assert len(data["items"]) >= 1
        item = data["items"][0]
        assert "id" in item
        assert "primitive_type" in item

    def test_list_drawcalls_pagination(self, client, auth_headers):
        resp = client.get(
            "/api/v1/frames/1/drawcalls?limit=10&offset=0", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 10
        assert data["offset"] == 0

    def test_list_drawcalls_nonexistent_frame_404(self, client, auth_headers):
        resp = client.get("/api/v1/frames/9999/drawcalls", headers=auth_headers)
        assert resp.status_code == 404


class TestDrawCallDetail:
    def test_get_drawcall_200(self, client, auth_headers):
        resp = client.get("/api/v1/frames/1/drawcalls/0", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 0
        assert data["primitive_type"] == "TRIANGLES"
        assert "pipeline_state" in data
        ps = data["pipeline_state"]
        assert "depth_test_enabled" in ps

    def test_get_drawcall_fbo_attachment(self, client, auth_headers):
        """pipeline_state must include fbo_color_attachment_tex for feedback loop detection."""
        resp = client.get("/api/v1/frames/1/drawcalls/0", headers=auth_headers)
        assert resp.status_code == 200
        ps = resp.json()["pipeline_state"]
        assert "fbo_color_attachment_tex" in ps
        # conftest mock sets fbo_color_attachment_tex = 7
        assert ps["fbo_color_attachment_tex"] == 7

    def test_get_drawcall_index_type(self, client, auth_headers):
        """Detail must include index_type so agents can spot UNSIGNED_SHORT truncation (r28)."""
        resp = client.get("/api/v1/frames/1/drawcalls/0", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "index_type" in data
        # conftest mock sets index_type = 0x1403 (GL_UNSIGNED_SHORT)
        assert data["index_type"] == 0x1403

    def test_get_drawcall_index_type_non_indexed(
        self, client, auth_headers, mock_query_engine
    ):
        """Non-indexed draws (glDrawArrays) report index_type=0."""
        dc = mock_query_engine.get_draw_call(1, 0)
        dc.index_count = 0
        dc.index_type = 0
        resp = client.get("/api/v1/frames/1/drawcalls/0", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["index_count"] == 0
        assert data["index_type"] == 0

    def test_get_nonexistent_drawcall_404(self, client, auth_headers):
        resp = client.get("/api/v1/frames/1/drawcalls/9999", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_drawcall_wrong_frame_404(self, client, auth_headers):
        resp = client.get("/api/v1/frames/9999/drawcalls/0", headers=auth_headers)
        assert resp.status_code == 404


class TestDrawCallShader:
    def test_get_shader_200(self, client, auth_headers):
        resp = client.get(
            "/api/v1/frames/1/drawcalls/0/shader", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["dc_id"] == 0
        assert data["shader_id"] == 7
        assert isinstance(data["parameters"], list)
        assert len(data["parameters"]) >= 1
        p = data["parameters"][0]
        assert p["name"] == "uColor"
        # GL_FLOAT_VEC4 = 0x8B52; native backend must decode bytes to float values
        assert p["type"] == 0x8B52
        assert "value" in p, "vec4 uniform must have a decoded 'value' field"
        assert p["value"] == [1.0, 0.0, 0.0, 1.0], (
            f"vec4(1.0,0.0,0.0,1.0) must decode correctly; got {p['value']}"
        )

    def test_get_shader_nonexistent_drawcall_404(self, client, auth_headers):
        resp = client.get(
            "/api/v1/frames/1/drawcalls/9999/shader", headers=auth_headers
        )
        assert resp.status_code == 404


class TestDrawCallTextures:
    def test_get_textures_200(self, client, auth_headers):
        resp = client.get(
            "/api/v1/frames/1/drawcalls/0/textures", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["textures"], list)
        assert len(data["textures"]) >= 1
        tex = data["textures"][0]
        assert tex["slot"] == 0
        assert tex["texture_id"] == 3

    def test_textures_carry_fbo_collision_flag(self, client, auth_headers):
        """Every bound texture is tagged with collides_with_fbo_attachment."""
        resp = client.get(
            "/api/v1/frames/1/drawcalls/0/textures", headers=auth_headers
        )
        assert resp.status_code == 200
        textures = resp.json()["textures"]
        by_slot = {t["slot"]: t for t in textures}
        # Conftest: slot 0 tex_id=3 (no collide), slot 1 tex_id=7 (== FBO attachment)
        assert by_slot[0]["collides_with_fbo_attachment"] is False
        assert by_slot[1]["collides_with_fbo_attachment"] is True

    def test_get_textures_nonexistent_404(self, client, auth_headers):
        resp = client.get(
            "/api/v1/frames/1/drawcalls/9999/textures", headers=auth_headers
        )
        assert resp.status_code == 404


class TestDrawCallFeedbackLoops:
    def test_returns_only_colliding_textures(self, client, auth_headers):
        resp = client.get(
            "/api/v1/frames/1/drawcalls/0/feedback-loops", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["fbo_color_attachment_tex"] == 7
        # Only the slot-1 texture (id 7) matches the FBO attachment
        assert len(data["textures"]) == 1
        assert data["textures"][0]["slot"] == 1
        assert data["textures"][0]["texture_id"] == 7

    def test_empty_when_no_collision(self, client, auth_headers, mock_query_engine):
        """If no bound texture matches the FBO attachment, textures is empty."""
        # Mutate the mock so neither texture collides
        dc = mock_query_engine.get_draw_call(1, 0)
        dc.fbo_color_attachment_tex = 999  # doesn't match id 3 or 7
        resp = client.get(
            "/api/v1/frames/1/drawcalls/0/feedback-loops", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["fbo_color_attachment_tex"] == 999
        assert data["textures"] == []

    def test_nonexistent_drawcall_404(self, client, auth_headers):
        resp = client.get(
            "/api/v1/frames/1/drawcalls/9999/feedback-loops",
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestDrawCallVertices:
    def test_get_vertices_200(self, client, auth_headers):
        resp = client.get(
            "/api/v1/frames/1/drawcalls/0/vertices", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["vertex_count"] == 3
        assert data["primitive_type"] == "TRIANGLES"

    def test_get_vertices_nonexistent_404(self, client, auth_headers):
        resp = client.get(
            "/api/v1/frames/1/drawcalls/9999/vertices", headers=auth_headers
        )
        assert resp.status_code == 404
