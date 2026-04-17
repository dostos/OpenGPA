#include <gtest/gtest.h>
#include "src/core/semantic/camera_extractor.h"
#include "src/core/normalize/normalized_types.h"
#include <cmath>
#include <cstring>

namespace gla {

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

// Build a ShaderParameter from 16 floats (column-major mat4).
static ShaderParameter make_mat4_param(const std::string& name, const float data[16]) {
    ShaderParameter p;
    p.name = name;
    p.type = 0x8B5C; // GL_FLOAT_MAT4
    p.data.resize(64);
    std::memcpy(p.data.data(), data, 64);
    return p;
}

// Add a single draw call with the given params to a frame.
static void add_draw_call(NormalizedFrame& frame, std::vector<ShaderParameter> params) {
    if (frame.render_passes.empty()) {
        frame.render_passes.push_back(RenderPass{});
    }
    NormalizedDrawCall dc{};
    dc.id = static_cast<uint32_t>(frame.render_passes[0].draw_calls.size());
    dc.params = std::move(params);
    frame.render_passes[0].draw_calls.push_back(std::move(dc));
}

// Build an OpenGL perspective projection matrix (column-major).
// Standard GL formula: glFrustum-based.
static void make_perspective(float fov_y_deg, float aspect, float near_z, float far_z,
                              float* out) {
    float f = 1.0f / std::tan(fov_y_deg * 3.14159265358979f / 360.0f);
    float nf = 1.0f / (near_z - far_z);
    float m[16] = {};
    // col 0
    m[0] = f / aspect;
    // col 1
    m[5] = f;
    // col 2
    m[10] = (far_z + near_z) * nf;
    m[11] = -1.0f;
    // col 3
    m[14] = 2.0f * far_z * near_z * nf;
    std::memcpy(out, m, 64);
}

// Build an OpenGL orthographic projection matrix (column-major).
static void make_ortho(float left, float right, float bottom, float top,
                       float near_z, float far_z, float* out) {
    float m[16] = {};
    m[0]  =  2.0f / (right - left);
    m[5]  =  2.0f / (top - bottom);
    m[10] = -2.0f / (far_z - near_z);
    m[12] = -(right + left) / (right - left);
    m[13] = -(top + bottom) / (top - bottom);
    m[14] = -(far_z + near_z) / (far_z - near_z);
    m[15] =  1.0f;
    std::memcpy(out, m, 64);
}

// Build a lookAt view matrix (column-major, GL convention).
static void make_look_at(float ex, float ey, float ez,
                          float cx, float cy, float cz,
                          float ux, float uy, float uz,
                          float* out) {
    // f = normalize(center - eye)
    float fx = cx - ex, fy = cy - ey, fz = cz - ez;
    float fl = std::sqrt(fx*fx + fy*fy + fz*fz);
    fx /= fl; fy /= fl; fz /= fl;

    // s = normalize(f x up)
    float sx = fy*uz - fz*uy, sy = fz*ux - fx*uz, sz = fx*uy - fy*ux;
    float sl = std::sqrt(sx*sx + sy*sy + sz*sz);
    sx /= sl; sy /= sl; sz /= sl;

    // u = s x f
    float rx = sy*fz - sz*fy, ry = sz*fx - sx*fz, rz = sx*fy - sy*fx;

    float m[16] = {};
    // col 0
    m[0] = sx; m[1] = rx; m[2] = -fx; m[3] = 0.0f;
    // col 1
    m[4] = sy; m[5] = ry; m[6] = -fy; m[7] = 0.0f;
    // col 2
    m[8] = sz; m[9] = rz; m[10] = -fz; m[11] = 0.0f;
    // col 3: translation = -dot(s,eye), -dot(u,eye), dot(f,eye)
    m[12] = -(sx*ex + sy*ey + sz*ez);
    m[13] = -(rx*ex + ry*ey + rz*ez);
    m[14] =  (fx*ex + fy*ey + fz*ez);
    m[15] = 1.0f;
    std::memcpy(out, m, 64);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

class CameraExtractorTest : public ::testing::Test {
protected:
    CameraExtractor extractor_;
};

// 1. Identity view + identity projection → position (0,0,0), forward (0,0,-1)
TEST_F(CameraExtractorTest, ExtractFromIdentity) {
    NormalizedFrame frame;
    frame.frame_id = 1;
    frame.timestamp = 0.0;

    // Identity view matrix
    float identity[16] = {
        1,0,0,0,
        0,1,0,0,
        0,0,1,0,
        0,0,0,1
    };
    // A minimal perspective projection so the frame has one
    float proj[16];
    make_perspective(60.0f, 1.0f, 0.1f, 100.0f, proj);

    std::vector<ShaderParameter> params;
    params.push_back(make_mat4_param("viewMatrix", identity));
    params.push_back(make_mat4_param("projMatrix", proj));
    add_draw_call(frame, std::move(params));

    auto result = extractor_.extract(frame);
    ASSERT_TRUE(result.has_value());

    EXPECT_NEAR(result->position[0], 0.0f, 1e-4f);
    EXPECT_NEAR(result->position[1], 0.0f, 1e-4f);
    EXPECT_NEAR(result->position[2], 0.0f, 1e-4f);
    EXPECT_NEAR(result->forward[0], 0.0f, 1e-4f);
    EXPECT_NEAR(result->forward[1], 0.0f, 1e-4f);
    EXPECT_NEAR(result->forward[2], -1.0f, 1e-4f);
}

// 2. Camera at (5,3,2) looking at origin, 60-degree FOV, 16:9 aspect, near=0.1, far=100
TEST_F(CameraExtractorTest, ExtractPerspectiveCamera) {
    NormalizedFrame frame;
    frame.frame_id = 2;
    frame.timestamp = 0.0;

    float view[16];
    make_look_at(5, 3, 2,   // eye
                 0, 0, 0,   // center
                 0, 1, 0,   // up
                 view);

    float proj[16];
    make_perspective(60.0f, 16.0f/9.0f, 0.1f, 100.0f, proj);

    std::vector<ShaderParameter> params;
    params.push_back(make_mat4_param("viewMatrix", view));
    params.push_back(make_mat4_param("projMatrix", proj));
    add_draw_call(frame, std::move(params));

    auto result = extractor_.extract(frame);
    ASSERT_TRUE(result.has_value());

    // Position should be (5, 3, 2)
    EXPECT_NEAR(result->position[0], 5.0f, 1e-3f);
    EXPECT_NEAR(result->position[1], 3.0f, 1e-3f);
    EXPECT_NEAR(result->position[2], 2.0f, 1e-3f);

    // FOV ~60 degrees
    EXPECT_NEAR(result->fov_y_degrees, 60.0f, 0.5f);

    // Aspect ~1.777 (16/9)
    EXPECT_NEAR(result->aspect, 16.0f/9.0f, 0.01f);

    // Should be perspective
    EXPECT_TRUE(result->is_perspective);

    // Near/far planes
    EXPECT_NEAR(result->near_plane, 0.1f, 0.01f);
    EXPECT_NEAR(result->far_plane, 100.0f, 1.0f);
}

// 3. Orthographic projection → is_perspective = false
TEST_F(CameraExtractorTest, ExtractOrthographicCamera) {
    NormalizedFrame frame;
    frame.frame_id = 3;
    frame.timestamp = 0.0;

    float identity[16] = {
        1,0,0,0,
        0,1,0,0,
        0,0,1,0,
        0,0,0,1
    };
    float ortho[16];
    make_ortho(-10.0f, 10.0f, -10.0f, 10.0f, 0.1f, 100.0f, ortho);

    std::vector<ShaderParameter> params;
    params.push_back(make_mat4_param("viewMatrix", identity));
    params.push_back(make_mat4_param("projOrtho", ortho));
    add_draw_call(frame, std::move(params));

    auto result = extractor_.extract(frame);
    ASSERT_TRUE(result.has_value());
    EXPECT_FALSE(result->is_perspective);
}

// 4. Frame with no mat4 params → nullopt
TEST_F(CameraExtractorTest, NoMatricesFound) {
    NormalizedFrame frame;
    frame.frame_id = 4;
    frame.timestamp = 0.0;

    // Add a draw call with a non-mat4 param (e.g. 4 bytes)
    ShaderParameter scalar_param;
    scalar_param.name = "uTime";
    scalar_param.type = 0x1406; // GL_FLOAT
    scalar_param.data.resize(4, 0);
    std::vector<ShaderParameter> params = { scalar_param };
    add_draw_call(frame, std::move(params));

    auto result = extractor_.extract(frame);
    EXPECT_FALSE(result.has_value());
}

// 5. Only projection matrix, no view → partial result (projection info, position at origin)
TEST_F(CameraExtractorTest, OnlyProjectionNoView) {
    NormalizedFrame frame;
    frame.frame_id = 5;
    frame.timestamp = 0.0;

    float proj[16];
    make_perspective(45.0f, 4.0f/3.0f, 0.5f, 200.0f, proj);

    std::vector<ShaderParameter> params;
    // Name deliberately doesn't say "view" — only projection
    params.push_back(make_mat4_param("uProjection", proj));
    add_draw_call(frame, std::move(params));

    auto result = extractor_.extract(frame);
    ASSERT_TRUE(result.has_value());

    // No view matrix → camera defaults to origin
    EXPECT_NEAR(result->position[0], 0.0f, 1e-4f);
    EXPECT_NEAR(result->position[1], 0.0f, 1e-4f);
    EXPECT_NEAR(result->position[2], 0.0f, 1e-4f);

    // Projection info should still be extracted
    EXPECT_TRUE(result->is_perspective);
    EXPECT_NEAR(result->fov_y_degrees, 45.0f, 0.5f);
    EXPECT_NEAR(result->aspect, 4.0f/3.0f, 0.01f);
}

// 6. Named params ("viewMatrix"/"projection") → higher confidence than unnamed
TEST_F(CameraExtractorTest, ConfidenceWithNameMatch) {
    // Frame A: named params
    NormalizedFrame frame_named;
    frame_named.frame_id = 6;
    frame_named.timestamp = 0.0;
    {
        float view[16];
        make_look_at(3, 0, 0,  0, 0, 0,  0, 1, 0,  view);
        float proj[16];
        make_perspective(60.0f, 1.0f, 0.1f, 100.0f, proj);
        std::vector<ShaderParameter> params;
        params.push_back(make_mat4_param("viewMatrix", view));
        params.push_back(make_mat4_param("projection", proj));
        add_draw_call(frame_named, std::move(params));
    }

    // Frame B: unnamed params (no "view"/"proj" in name)
    NormalizedFrame frame_unnamed;
    frame_unnamed.frame_id = 7;
    frame_unnamed.timestamp = 0.0;
    {
        float view[16];
        make_look_at(3, 0, 0,  0, 0, 0,  0, 1, 0,  view);
        float proj[16];
        make_perspective(60.0f, 1.0f, 0.1f, 100.0f, proj);
        std::vector<ShaderParameter> params;
        params.push_back(make_mat4_param("uMatrix0", view));
        params.push_back(make_mat4_param("uMatrix1", proj));
        add_draw_call(frame_unnamed, std::move(params));
    }

    auto named_result   = extractor_.extract(frame_named);
    auto unnamed_result = extractor_.extract(frame_unnamed);

    ASSERT_TRUE(named_result.has_value());
    ASSERT_TRUE(unnamed_result.has_value());
    EXPECT_GT(named_result->confidence, unnamed_result->confidence);
}

}  // namespace gla
