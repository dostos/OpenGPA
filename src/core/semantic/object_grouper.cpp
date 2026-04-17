#include "src/core/semantic/object_grouper.h"
#include "src/core/semantic/matrix_classifier.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>

namespace gla {

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

// GL_FLOAT_MAT4 = 0x8B5C
static constexpr uint32_t kMat4Type  = 0x8B5C;
static constexpr size_t   kMat4Bytes = 16 * sizeof(float);

// GL_FLOAT = 0x1406, GL_HALF_FLOAT = 0x140B
static constexpr uint32_t kGLFloat     = 0x1406;
static constexpr uint32_t kGLHalfFloat = 0x140B;

// Identity matrix (column-major)
static const float kIdentity[16] = {
    1,0,0,0,  // col 0
    0,1,0,0,  // col 1
    0,0,1,0,  // col 2
    0,0,0,1   // col 3
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Extract translation from column-major mat4: column 3, rows 0-2 = indices 12,13,14
static void mat4_translation(const float* m, float* tx, float* ty, float* tz) {
    *tx = m[12];
    *ty = m[13];
    *tz = m[14];
}

// Transform a 3D point by a mat4 (column-major).
static void transform_point(const float* mat, const float* pt, float* out) {
    float x = pt[0], y = pt[1], z = pt[2];
    out[0] = mat[0]*x + mat[4]*y + mat[8]*z  + mat[12];
    out[1] = mat[1]*x + mat[5]*y + mat[9]*z  + mat[13];
    out[2] = mat[2]*x + mat[6]*y + mat[10]*z + mat[14];
    // w = mat[3]*x + mat[7]*y + mat[11]*z + mat[15], ignoring for affine matrices
}

// Compare two mat4 values for near-equality.
static bool mat4_equal(const float* a, const float* b, float eps = 1e-4f) {
    for (int i = 0; i < 16; ++i) {
        if (std::fabs(a[i] - b[i]) > eps) return false;
    }
    return true;
}

// ---------------------------------------------------------------------------
// Find model matrix for a draw call.
//
// Strategy:
//   1. Use frame-level classify_frame() results (passed in as a map).
//   2. If a param is classified as Model → use it.
//   3. Fallback: first mat4 whose data changed across at least one draw call
//      (caller detects this via the change-set passed in, but here we just
//      pick the first mat4 with unknown semantics that isn't clearly view/proj).
//   4. If none found → use identity, confidence = 0.
// ---------------------------------------------------------------------------

struct ModelMatResult {
    float data[16];
    float confidence;
    bool found;
};

static ModelMatResult find_model_matrix(
    const NormalizedDrawCall& dc,
    const std::unordered_map<std::string, MatrixClassifier::Classification>& frame_class)
{
    ModelMatResult res{};
    res.found = false;
    res.confidence = 0.0f;
    std::memcpy(res.data, kIdentity, sizeof(kIdentity));

    // Pass 1: look for a param explicitly classified as Model.
    for (const auto& p : dc.params) {
        if (p.type != kMat4Type || p.data.size() != kMat4Bytes) continue;
        auto it = frame_class.find(p.name);
        if (it != frame_class.end() &&
            it->second.semantic == MatrixClassifier::MatrixSemantic::Model) {
            std::memcpy(res.data, p.data.data(), kMat4Bytes);
            res.confidence = it->second.confidence;
            res.found = true;
            return res;
        }
    }

    // Pass 2: find the first mat4 not classified as View or Projection.
    // Prefer Unknown over MVP (MVP contains model transform, but is ambiguous).
    for (const auto& p : dc.params) {
        if (p.type != kMat4Type || p.data.size() != kMat4Bytes) continue;
        auto it = frame_class.find(p.name);
        MatrixClassifier::MatrixSemantic sem = MatrixClassifier::MatrixSemantic::Unknown;
        if (it != frame_class.end()) sem = it->second.semantic;

        if (sem == MatrixClassifier::MatrixSemantic::View ||
            sem == MatrixClassifier::MatrixSemantic::Projection ||
            sem == MatrixClassifier::MatrixSemantic::Normal) {
            continue;
        }
        // Not view/proj/normal — use as model (low confidence)
        std::memcpy(res.data, p.data.data(), kMat4Bytes);
        res.confidence = (sem == MatrixClassifier::MatrixSemantic::MVP) ? 0.3f : 0.2f;
        res.found = true;
        return res;
    }

    // No mat4 at all: identity, confidence 0.
    return res;
}

// ---------------------------------------------------------------------------
// Bounding box computation
// ---------------------------------------------------------------------------

// Try to compute an AABB in local space from vertex data, then transform it.
// Returns false if vertex data is unavailable or has no usable positions.
static bool compute_bbox_from_vertices(
    const NormalizedDrawCall& dc,
    const float* world_transform,
    float* bbox_min,
    float* bbox_max)
{
    if (dc.vertex_data.empty() || dc.vertex_count == 0 || dc.attributes.empty()) {
        return false;
    }

    // Find a position attribute (components >= 3, format is GL_FLOAT or GL_HALF_FLOAT,
    // or just pick the first attribute with 3+ components).
    const VertexAttribute* pos_attr = nullptr;
    for (const auto& attr : dc.attributes) {
        if (attr.components >= 3) {
            // Prefer GL_FLOAT
            if (attr.format == kGLFloat) {
                pos_attr = &attr;
                break;
            }
            if (!pos_attr) pos_attr = &attr;
        }
    }
    if (!pos_attr) return false;
    if (pos_attr->format != kGLFloat) return false;  // only handle float for now

    uint32_t stride   = pos_attr->stride;
    uint32_t offset   = pos_attr->offset;
    uint32_t comps    = pos_attr->components;
    uint32_t n_verts  = dc.vertex_count;

    // Minimum stride if zero: components * sizeof(float)
    if (stride == 0) stride = comps * sizeof(float);

    size_t required = static_cast<size_t>(offset) + static_cast<size_t>(n_verts) * stride;
    if (dc.vertex_data.size() < required) return false;

    float local_min[3] = {  std::numeric_limits<float>::max(),
                             std::numeric_limits<float>::max(),
                             std::numeric_limits<float>::max() };
    float local_max[3] = { -std::numeric_limits<float>::max(),
                           -std::numeric_limits<float>::max(),
                           -std::numeric_limits<float>::max() };

    const uint8_t* base = dc.vertex_data.data() + offset;
    for (uint32_t v = 0; v < n_verts; ++v) {
        const float* p = reinterpret_cast<const float*>(base + static_cast<size_t>(v) * stride);
        local_min[0] = std::min(local_min[0], p[0]);
        local_min[1] = std::min(local_min[1], p[1]);
        local_min[2] = std::min(local_min[2], p[2]);
        local_max[0] = std::max(local_max[0], p[0]);
        local_max[1] = std::max(local_max[1], p[1]);
        local_max[2] = std::max(local_max[2], p[2]);
    }

    // Transform 8 corners of the local AABB to world space, then re-compute AABB.
    float world_min[3] = {  std::numeric_limits<float>::max(),
                             std::numeric_limits<float>::max(),
                             std::numeric_limits<float>::max() };
    float world_max[3] = { -std::numeric_limits<float>::max(),
                           -std::numeric_limits<float>::max(),
                           -std::numeric_limits<float>::max() };

    for (int cx = 0; cx < 2; ++cx) {
        for (int cy = 0; cy < 2; ++cy) {
            for (int cz = 0; cz < 2; ++cz) {
                float corner[3] = {
                    cx ? local_max[0] : local_min[0],
                    cy ? local_max[1] : local_min[1],
                    cz ? local_max[2] : local_min[2]
                };
                float wc[3];
                transform_point(world_transform, corner, wc);
                world_min[0] = std::min(world_min[0], wc[0]);
                world_min[1] = std::min(world_min[1], wc[1]);
                world_min[2] = std::min(world_min[2], wc[2]);
                world_max[0] = std::max(world_max[0], wc[0]);
                world_max[1] = std::max(world_max[1], wc[1]);
                world_max[2] = std::max(world_max[2], wc[2]);
            }
        }
    }

    std::memcpy(bbox_min, world_min, 3 * sizeof(float));
    std::memcpy(bbox_max, world_max, 3 * sizeof(float));
    return true;
}

// ---------------------------------------------------------------------------
// ObjectGrouper::group()
// ---------------------------------------------------------------------------

std::vector<SceneObject> ObjectGrouper::group(const NormalizedFrame& frame) const {
    auto all_dcs = frame.all_draw_calls();
    if (all_dcs.empty()) return {};

    // Run frame-level classification to get model-matrix candidates.
    MatrixClassifier classifier;
    auto frame_class = classifier.classify_frame(frame);

    // Build a list of (draw_call, model_matrix, confidence) entries.
    struct DCEntry {
        const NormalizedDrawCall* dc;
        float model[16];
        float confidence;
        bool has_model;
    };

    std::vector<DCEntry> entries;
    entries.reserve(all_dcs.size());
    for (const auto& dc_ref : all_dcs) {
        const NormalizedDrawCall& dc = dc_ref.get();
        DCEntry e;
        e.dc = &dc;
        auto res = find_model_matrix(dc, frame_class);
        std::memcpy(e.model, res.data, kMat4Bytes);
        e.confidence = res.confidence;
        e.has_model  = res.found;
        entries.push_back(e);
    }

    // Group consecutive draw calls that share the same model matrix.
    std::vector<SceneObject> objects;
    uint32_t next_id = 0;

    size_t i = 0;
    while (i < entries.size()) {
        // Start a new group.
        size_t j = i + 1;
        // Only group if both have found model matrices; otherwise each stands alone.
        if (entries[i].has_model) {
            while (j < entries.size() &&
                   entries[j].has_model &&
                   mat4_equal(entries[i].model, entries[j].model)) {
                ++j;
            }
        }

        // Build SceneObject for entries[i..j).
        SceneObject obj{};
        obj.id = next_id++;
        obj.visible = true;
        std::memcpy(obj.world_transform, entries[i].model, kMat4Bytes);

        // Confidence: minimum across the group (weakest link).
        float min_conf = entries[i].confidence;
        for (size_t k = i; k < j; ++k) {
            obj.draw_call_ids.push_back(entries[k].dc->id);
            min_conf = std::min(min_conf, entries[k].confidence);
        }
        obj.confidence = min_conf;

        // Compute bounding box.
        bool bbox_ok = false;
        // Accumulate world-space AABB across all draw calls in the group.
        float grp_min[3] = {  std::numeric_limits<float>::max(),
                               std::numeric_limits<float>::max(),
                               std::numeric_limits<float>::max() };
        float grp_max[3] = { -std::numeric_limits<float>::max(),
                             -std::numeric_limits<float>::max(),
                             -std::numeric_limits<float>::max() };

        for (size_t k = i; k < j; ++k) {
            float dc_min[3], dc_max[3];
            if (compute_bbox_from_vertices(*entries[k].dc, obj.world_transform,
                                           dc_min, dc_max)) {
                grp_min[0] = std::min(grp_min[0], dc_min[0]);
                grp_min[1] = std::min(grp_min[1], dc_min[1]);
                grp_min[2] = std::min(grp_min[2], dc_min[2]);
                grp_max[0] = std::max(grp_max[0], dc_max[0]);
                grp_max[1] = std::max(grp_max[1], dc_max[1]);
                grp_max[2] = std::max(grp_max[2], dc_max[2]);
                bbox_ok = true;
            }
        }

        if (bbox_ok) {
            std::memcpy(obj.bbox_min, grp_min, sizeof(grp_min));
            std::memcpy(obj.bbox_max, grp_max, sizeof(grp_max));
        } else {
            // Fall back: use translation extracted from world_transform.
            float tx, ty, tz;
            mat4_translation(obj.world_transform, &tx, &ty, &tz);
            obj.bbox_min[0] = tx;
            obj.bbox_min[1] = ty;
            obj.bbox_min[2] = tz;
            obj.bbox_max[0] = tx;
            obj.bbox_max[1] = ty;
            obj.bbox_max[2] = tz;
        }

        objects.push_back(std::move(obj));
        i = j;
    }

    return objects;
}

}  // namespace gla
