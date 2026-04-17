#include <gtest/gtest.h>
#include "src/core/semantic/object_grouper.h"
#include "src/core/semantic/scene_reconstructor.h"
#include "src/core/normalize/normalized_types.h"

#include <cstring>
#include <cmath>

namespace gla {

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// GL_FLOAT_MAT4 = 0x8B5C
static constexpr uint32_t kMat4Type  = 0x8B5C;
// GL_FLOAT = 0x1406
static constexpr uint32_t kGLFloat   = 0x1406;

// Build a ShaderParameter carrying a mat4 value (column-major, 16 floats).
static ShaderParameter make_mat4_param(const std::string& name, const float* data) {
    ShaderParameter p;
    p.name = name;
    p.type = kMat4Type;
    p.data.resize(16 * sizeof(float));
    std::memcpy(p.data.data(), data, 16 * sizeof(float));
    return p;
}

// Identity matrix (column-major).
static const float kIdentity[16] = {
    1,0,0,0,
    0,1,0,0,
    0,0,1,0,
    0,0,0,1
};

// Translation matrix: translate by (tx, ty, tz).
static void make_translate(float* out, float tx, float ty, float tz) {
    std::memcpy(out, kIdentity, sizeof(kIdentity));
    out[12] = tx;
    out[13] = ty;
    out[14] = tz;
}

// Add a single draw call to a frame (into the first render pass, creating it if needed).
static NormalizedDrawCall& add_draw_call(NormalizedFrame& frame, uint32_t id) {
    if (frame.render_passes.empty()) {
        frame.render_passes.push_back(RenderPass{});
    }
    NormalizedDrawCall dc{};
    dc.id = id;
    frame.render_passes[0].draw_calls.push_back(std::move(dc));
    return frame.render_passes[0].draw_calls.back();
}

// Standard OpenGL perspective matrix (from fov, aspect, near, far).
// Used to build a recognisable projection for SceneReconstructor tests.
static void make_perspective(float* out, float fov_y_rad, float aspect,
                              float near_z, float far_z) {
    std::memset(out, 0, 16 * sizeof(float));
    float f = 1.0f / std::tan(fov_y_rad * 0.5f);
    out[0]  = f / aspect;
    out[5]  = f;
    out[10] = (far_z + near_z) / (near_z - far_z);
    out[11] = -1.0f;
    out[14] = (2.0f * far_z * near_z) / (near_z - far_z);
}

// Orthonormal view matrix (look-at style; rows are axes).
// For simplicity we just use identity (camera at origin looking down -Z).
static void make_view_identity(float* out) {
    std::memcpy(out, kIdentity, 16 * sizeof(float));
}

// ---------------------------------------------------------------------------
// Test fixture
// ---------------------------------------------------------------------------

class ObjectGrouperTest : public ::testing::Test {
protected:
    ObjectGrouper grouper_;
};

// ---------------------------------------------------------------------------
// Test 1: EmptyFrame
// No draw calls → empty result.
// ---------------------------------------------------------------------------
TEST_F(ObjectGrouperTest, EmptyFrame) {
    NormalizedFrame frame;
    frame.frame_id = 1;
    frame.timestamp = 0.0;

    auto result = grouper_.group(frame);
    EXPECT_TRUE(result.empty());
}

// ---------------------------------------------------------------------------
// Test 2: SingleDrawCall
// 1 draw call with a named model matrix → 1 SceneObject.
// ---------------------------------------------------------------------------
TEST_F(ObjectGrouperTest, SingleDrawCall) {
    NormalizedFrame frame;
    frame.frame_id = 2;

    float model[16];
    make_translate(model, 1.0f, 2.0f, 3.0f);

    auto& dc = add_draw_call(frame, 10);
    dc.params.push_back(make_mat4_param("uModelMatrix", model));

    auto result = grouper_.group(frame);
    ASSERT_EQ(result.size(), 1u);
    EXPECT_EQ(result[0].draw_call_ids.size(), 1u);
    EXPECT_EQ(result[0].draw_call_ids[0], 10u);
    EXPECT_TRUE(result[0].visible);
}

// ---------------------------------------------------------------------------
// Test 3: GroupBySharedMatrix
// 3 draw calls: first two share the same model matrix, third is different.
// → 2 SceneObjects.
// ---------------------------------------------------------------------------
TEST_F(ObjectGrouperTest, GroupBySharedMatrix) {
    NormalizedFrame frame;
    frame.frame_id = 3;

    float model_a[16], model_b[16];
    make_translate(model_a, 1.0f, 0.0f, 0.0f);
    make_translate(model_b, 5.0f, 0.0f, 0.0f);

    // DC 0 and DC 1 share model_a; DC 2 has model_b.
    auto& dc0 = add_draw_call(frame, 0);
    dc0.params.push_back(make_mat4_param("uModelMatrix", model_a));

    auto& dc1 = add_draw_call(frame, 1);
    dc1.params.push_back(make_mat4_param("uModelMatrix", model_a));

    auto& dc2 = add_draw_call(frame, 2);
    dc2.params.push_back(make_mat4_param("uModelMatrix", model_b));

    auto result = grouper_.group(frame);
    ASSERT_EQ(result.size(), 2u);

    // First object should contain draw calls 0 and 1.
    EXPECT_EQ(result[0].draw_call_ids.size(), 2u);
    EXPECT_EQ(result[0].draw_call_ids[0], 0u);
    EXPECT_EQ(result[0].draw_call_ids[1], 1u);

    // Second object should contain draw call 2.
    EXPECT_EQ(result[1].draw_call_ids.size(), 1u);
    EXPECT_EQ(result[1].draw_call_ids[0], 2u);
}

// ---------------------------------------------------------------------------
// Test 4: AllDifferentMatrices
// 3 draw calls with distinct model matrices → 3 SceneObjects.
// ---------------------------------------------------------------------------
TEST_F(ObjectGrouperTest, AllDifferentMatrices) {
    NormalizedFrame frame;
    frame.frame_id = 4;

    for (uint32_t i = 0; i < 3; ++i) {
        float model[16];
        make_translate(model, static_cast<float>(i) * 10.0f, 0.0f, 0.0f);
        auto& dc = add_draw_call(frame, i);
        dc.params.push_back(make_mat4_param("uModelMatrix", model));
    }

    auto result = grouper_.group(frame);
    ASSERT_EQ(result.size(), 3u);
    for (size_t k = 0; k < 3; ++k) {
        EXPECT_EQ(result[k].draw_call_ids.size(), 1u);
        EXPECT_EQ(result[k].draw_call_ids[0], static_cast<uint32_t>(k));
    }
}

// ---------------------------------------------------------------------------
// Test 5: NoModelMatrix
// Draw calls without any mat4 param → 1 SceneObject per draw call,
// confidence = 0.
// ---------------------------------------------------------------------------
TEST_F(ObjectGrouperTest, NoModelMatrix) {
    NormalizedFrame frame;
    frame.frame_id = 5;

    for (uint32_t i = 0; i < 3; ++i) {
        // Add a non-mat4 param so the draw call is not empty.
        auto& dc = add_draw_call(frame, i);
        ShaderParameter p;
        p.name = "uColor";
        p.type = 0x8B50;  // GL_FLOAT_VEC4
        p.data.resize(4 * sizeof(float), 0);
        dc.params.push_back(p);
    }

    auto result = grouper_.group(frame);
    // Each draw call becomes its own object because they all fall through to
    // identity (same matrix) BUT since none has a "found" model matrix the
    // grouper treats each as standalone.
    ASSERT_EQ(result.size(), 3u);
    for (const auto& obj : result) {
        EXPECT_FLOAT_EQ(obj.confidence, 0.0f);
        EXPECT_EQ(obj.draw_call_ids.size(), 1u);
    }
}

// ---------------------------------------------------------------------------
// Test 6: BoundingBoxFromTranslation
// Object with model matrix translating to (5,0,3) but no vertex data.
// → bbox_min == bbox_max == translation.
// ---------------------------------------------------------------------------
TEST_F(ObjectGrouperTest, BoundingBoxFromTranslation) {
    NormalizedFrame frame;
    frame.frame_id = 6;

    float model[16];
    make_translate(model, 5.0f, 0.0f, 3.0f);

    auto& dc = add_draw_call(frame, 42);
    dc.params.push_back(make_mat4_param("uModelMatrix", model));
    // No vertex_data, no attributes.

    auto result = grouper_.group(frame);
    ASSERT_EQ(result.size(), 1u);
    const auto& obj = result[0];

    EXPECT_NEAR(obj.bbox_min[0], 5.0f, 1e-4f);
    EXPECT_NEAR(obj.bbox_min[1], 0.0f, 1e-4f);
    EXPECT_NEAR(obj.bbox_min[2], 3.0f, 1e-4f);
    EXPECT_NEAR(obj.bbox_max[0], 5.0f, 1e-4f);
    EXPECT_NEAR(obj.bbox_max[1], 0.0f, 1e-4f);
    EXPECT_NEAR(obj.bbox_max[2], 3.0f, 1e-4f);
}

// ---------------------------------------------------------------------------
// SceneReconstructor integration tests
// ---------------------------------------------------------------------------

class SceneReconstructorTest : public ::testing::Test {
protected:
    SceneReconstructor reconstructor_;
};

// ---------------------------------------------------------------------------
// Test 7: FullReconstruction
// Frame containing view + projection + model matrices → quality = "full".
// ---------------------------------------------------------------------------
TEST_F(SceneReconstructorTest, FullReconstruction) {
    NormalizedFrame frame;
    frame.frame_id = 100;

    float view[16], proj[16], model[16];
    make_view_identity(view);
    make_perspective(proj, 3.14159265f / 4.0f, 16.0f / 9.0f, 0.1f, 100.0f);
    make_translate(model, 0.0f, 0.0f, -5.0f);

    // Two draw calls: share the model matrix so they form one high-confidence object.
    for (uint32_t i = 0; i < 2; ++i) {
        auto& dc = add_draw_call(frame, i);
        dc.params.push_back(make_mat4_param("uViewMatrix",       view));
        dc.params.push_back(make_mat4_param("uProjectionMatrix", proj));
        dc.params.push_back(make_mat4_param("uModelMatrix",      model));
    }

    auto scene = reconstructor_.reconstruct(frame);
    EXPECT_TRUE(scene.camera.has_value());
    EXPECT_FALSE(scene.objects.empty());
    EXPECT_EQ(scene.reconstruction_quality, "full");
}

// ---------------------------------------------------------------------------
// Test 8: RawOnly
// Frame with no mat4 params → camera not found, objects have zero confidence.
// → quality = "raw_only".
// ---------------------------------------------------------------------------
TEST_F(SceneReconstructorTest, RawOnly) {
    NormalizedFrame frame;
    frame.frame_id = 101;

    // Add a draw call with only a non-matrix param.
    auto& dc = add_draw_call(frame, 0);
    ShaderParameter p;
    p.name = "uColor";
    p.type = 0x8B50;  // GL_FLOAT_VEC4
    p.data.resize(4 * sizeof(float), 0);
    dc.params.push_back(p);

    auto scene = reconstructor_.reconstruct(frame);
    EXPECT_FALSE(scene.camera.has_value());
    EXPECT_EQ(scene.reconstruction_quality, "raw_only");
}

}  // namespace gla
