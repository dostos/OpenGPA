#include "src/core/semantic/camera_extractor.h"
#include <cmath>
#include <cstring>
#include <string>
#include <algorithm>

namespace gla {

// ---------------------------------------------------------------------------
// Internal mat4 math (column-major, OpenGL convention)
// Element at column c, row r = data[c*4 + r]
// ---------------------------------------------------------------------------

static void vec3_normalize(float* v) {
    float len = std::sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2]);
    if (len > 1e-9f) {
        v[0] /= len; v[1] /= len; v[2] /= len;
    }
}

// Cofactor-expansion 4x4 inverse (returns false if singular).
static bool mat4_inverse(const float* m, float* inv) {
    // Use the adjugate/cofactor method.
    float tmp[16];

    tmp[0]  =  m[5]*m[10]*m[15] - m[5]*m[11]*m[14] - m[9]*m[6]*m[15]
             + m[9]*m[7]*m[14]  + m[13]*m[6]*m[11]  - m[13]*m[7]*m[10];
    tmp[4]  = -m[4]*m[10]*m[15] + m[4]*m[11]*m[14] + m[8]*m[6]*m[15]
             - m[8]*m[7]*m[14]  - m[12]*m[6]*m[11]  + m[12]*m[7]*m[10];
    tmp[8]  =  m[4]*m[9]*m[15]  - m[4]*m[11]*m[13] - m[8]*m[5]*m[15]
             + m[8]*m[7]*m[13]  + m[12]*m[5]*m[11]  - m[12]*m[7]*m[9];
    tmp[12] = -m[4]*m[9]*m[14]  + m[4]*m[10]*m[13] + m[8]*m[5]*m[14]
             - m[8]*m[6]*m[13]  - m[12]*m[5]*m[10]  + m[12]*m[6]*m[9];

    tmp[1]  = -m[1]*m[10]*m[15] + m[1]*m[11]*m[14] + m[9]*m[2]*m[15]
             - m[9]*m[3]*m[14]  - m[13]*m[2]*m[11]  + m[13]*m[3]*m[10];
    tmp[5]  =  m[0]*m[10]*m[15] - m[0]*m[11]*m[14] - m[8]*m[2]*m[15]
             + m[8]*m[3]*m[14]  + m[12]*m[2]*m[11]  - m[12]*m[3]*m[10];
    tmp[9]  = -m[0]*m[9]*m[15]  + m[0]*m[11]*m[13] + m[8]*m[1]*m[15]
             - m[8]*m[3]*m[13]  - m[12]*m[1]*m[11]  + m[12]*m[3]*m[9];
    tmp[13] =  m[0]*m[9]*m[14]  - m[0]*m[10]*m[13] - m[8]*m[1]*m[14]
             + m[8]*m[2]*m[13]  + m[12]*m[1]*m[10]  - m[12]*m[2]*m[9];

    tmp[2]  =  m[1]*m[6]*m[15]  - m[1]*m[7]*m[14]  - m[5]*m[2]*m[15]
             + m[5]*m[3]*m[14]  + m[13]*m[2]*m[7]   - m[13]*m[3]*m[6];
    tmp[6]  = -m[0]*m[6]*m[15]  + m[0]*m[7]*m[14]  + m[4]*m[2]*m[15]
             - m[4]*m[3]*m[14]  - m[12]*m[2]*m[7]   + m[12]*m[3]*m[6];
    tmp[10] =  m[0]*m[5]*m[15]  - m[0]*m[7]*m[13]  - m[4]*m[1]*m[15]
             + m[4]*m[3]*m[13]  + m[12]*m[1]*m[7]   - m[12]*m[3]*m[5];
    tmp[14] = -m[0]*m[5]*m[14]  + m[0]*m[6]*m[13]  + m[4]*m[1]*m[14]
             - m[4]*m[2]*m[13]  - m[12]*m[1]*m[6]   + m[12]*m[2]*m[5];

    tmp[3]  = -m[1]*m[6]*m[11]  + m[1]*m[7]*m[10]  + m[5]*m[2]*m[11]
             - m[5]*m[3]*m[10]  - m[9]*m[2]*m[7]    + m[9]*m[3]*m[6];
    tmp[7]  =  m[0]*m[6]*m[11]  - m[0]*m[7]*m[10]  - m[4]*m[2]*m[11]
             + m[4]*m[3]*m[10]  + m[8]*m[2]*m[7]    - m[8]*m[3]*m[6];
    tmp[11] = -m[0]*m[5]*m[11]  + m[0]*m[7]*m[9]   + m[4]*m[1]*m[11]
             - m[4]*m[3]*m[9]   - m[8]*m[1]*m[7]    + m[8]*m[3]*m[5];
    tmp[15] =  m[0]*m[5]*m[10]  - m[0]*m[6]*m[9]   - m[4]*m[1]*m[10]
             + m[4]*m[2]*m[9]   + m[8]*m[1]*m[6]    - m[8]*m[2]*m[5];

    float det = m[0]*tmp[0] + m[1]*tmp[4] + m[2]*tmp[8] + m[3]*tmp[12];
    if (std::abs(det) < 1e-10f) return false;

    float inv_det = 1.0f / det;
    for (int i = 0; i < 16; ++i) inv[i] = tmp[i] * inv_det;
    return true;
}

// ---------------------------------------------------------------------------
// Heuristics
// ---------------------------------------------------------------------------

// Case-insensitive substring search.
static bool name_contains_ci(const std::string& name, const std::string& pattern) {
    std::string a = name, b = pattern;
    std::transform(a.begin(), a.end(), a.begin(), ::tolower);
    std::transform(b.begin(), b.end(), b.begin(), ::tolower);
    return a.find(b) != std::string::npos;
}

// Column-major: element at column c, row r = data[c*4 + r]
// GL perspective: m[2][3] = data[11] == -1, m[3][2] = data[14] != 0
static bool heuristic_is_perspective(const float* m, float eps = 0.01f) {
    return std::abs(m[11] + 1.0f) < eps && std::abs(m[14]) > eps;
}

// Orthographic: last row is [0,0,0,1], no perspective divide.
// m[3][3] = data[15] == 1, m[2][3] = data[11] == 0
static bool heuristic_is_orthographic(const float* m, float eps = 0.01f) {
    return std::abs(m[11]) < eps && std::abs(m[15] - 1.0f) < eps
        && std::abs(m[3]) < eps && std::abs(m[7]) < eps;
}

// Upper-left 3x3 orthonormal (each column is unit, columns are orthogonal).
static bool is_orthonormal_3x3(const float* m, float eps = 0.02f) {
    // Column vectors of upper 3x3
    float c0[3] = { m[0], m[1], m[2] };
    float c1[3] = { m[4], m[5], m[6] };
    float c2[3] = { m[8], m[9], m[10] };

    auto dot3 = [](const float* a, const float* b) {
        return a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
    };
    auto len2 = [&](const float* v) { return dot3(v, v); };

    // Unit length check
    if (std::abs(len2(c0) - 1.0f) > eps) return false;
    if (std::abs(len2(c1) - 1.0f) > eps) return false;
    if (std::abs(len2(c2) - 1.0f) > eps) return false;
    // Orthogonality
    if (std::abs(dot3(c0, c1)) > eps) return false;
    if (std::abs(dot3(c0, c2)) > eps) return false;
    if (std::abs(dot3(c1, c2)) > eps) return false;
    return true;
}

// ---------------------------------------------------------------------------
// Main implementation
// ---------------------------------------------------------------------------

std::optional<CameraInfo> CameraExtractor::extract(const NormalizedFrame& frame) const {
    // Collect all mat4 candidates (params with exactly 64 bytes of data).
    struct Mat4Candidate {
        std::string name;
        float data[16];
    };
    std::vector<Mat4Candidate> candidates;

    for (const auto& dc_ref : frame.all_draw_calls()) {
        const NormalizedDrawCall& dc = dc_ref.get();
        for (const auto& param : dc.params) {
            if (param.data.size() == 64) {
                Mat4Candidate c;
                c.name = param.name;
                std::memcpy(c.data, param.data.data(), 64);
                candidates.push_back(c);
            }
        }
    }

    if (candidates.empty()) return std::nullopt;

    // --- Identify view matrix ---
    const float* view_mat = nullptr;
    bool view_named = false;
    for (const auto& c : candidates) {
        if (name_contains_ci(c.name, "view") && !name_contains_ci(c.name, "proj")) {
            view_mat = c.data;
            view_named = true;
            break;
        }
    }
    if (!view_mat) {
        // Fallback: find a mat4 that is orthonormal 3x3 (likely a view matrix).
        for (const auto& c : candidates) {
            if (is_orthonormal_3x3(c.data)) {
                view_mat = c.data;
                break;
            }
        }
    }

    // --- Identify projection matrix ---
    const float* proj_mat = nullptr;
    bool proj_named = false;
    for (const auto& c : candidates) {
        if (name_contains_ci(c.name, "proj")) {
            proj_mat = c.data;
            proj_named = true;
            break;
        }
    }
    if (!proj_mat) {
        for (const auto& c : candidates) {
            if (heuristic_is_perspective(c.data) || heuristic_is_orthographic(c.data)) {
                proj_mat = c.data;
                break;
            }
        }
    }

    // If we found neither, nothing to extract.
    if (!view_mat && !proj_mat) return std::nullopt;

    CameraInfo info{};
    float confidence = 0.4f;

    // --- Extract from view matrix ---
    if (view_mat) {
        float inv[16];
        if (mat4_inverse(view_mat, inv)) {
            // position = camera_world_transform * (0,0,0,1) = column 3
            info.position[0] = inv[3*4+0]; // col 3, row 0
            info.position[1] = inv[3*4+1];
            info.position[2] = inv[3*4+2];

            // forward = -normalize(col 2 upper 3) [camera looks down -Z in view space]
            float fwd[3] = { -inv[2*4+0], -inv[2*4+1], -inv[2*4+2] };
            vec3_normalize(fwd);
            info.forward[0] = fwd[0];
            info.forward[1] = fwd[1];
            info.forward[2] = fwd[2];

            // up = normalize(col 1 upper 3)
            float up[3] = { inv[1*4+0], inv[1*4+1], inv[1*4+2] };
            vec3_normalize(up);
            info.up[0] = up[0];
            info.up[1] = up[1];
            info.up[2] = up[2];

            confidence += view_named ? 0.3f : 0.1f;
        }
    } else {
        // No view matrix: default camera at origin looking down -Z
        info.position[0] = info.position[1] = info.position[2] = 0.0f;
        info.forward[0]  = 0.0f; info.forward[1]  = 0.0f; info.forward[2]  = -1.0f;
        info.up[0]       = 0.0f; info.up[1]       = 1.0f; info.up[2]       = 0.0f;
    }

    // --- Extract from projection matrix ---
    if (proj_mat) {
        const float* P = proj_mat;
        info.is_perspective = heuristic_is_perspective(P);

        if (info.is_perspective) {
            // P[1][1] = data[1*4+1] = data[5] = cot(fov_y/2)
            float cot_half_fov = P[5];
            if (std::abs(cot_half_fov) > 1e-6f) {
                info.fov_y_degrees = 2.0f * std::atan(1.0f / cot_half_fov)
                                   * (180.0f / 3.14159265358979f);
            }
            // aspect = P[1][1] / P[0][0] = data[5] / data[0]
            if (std::abs(P[0]) > 1e-6f) {
                info.aspect = P[5] / P[0];
            }
            // Standard GL: P[2][2] = data[10] = -(far+near)/(far-near)
            //              P[3][2] = data[14] = -2*near*far/(far-near)
            // Solving: near = data[14]/(data[10]-1), far = data[14]/(data[10]+1)
            float d10 = P[10], d14 = P[14];
            if (std::abs(d10 - 1.0f) > 1e-6f)
                info.near_plane = d14 / (d10 - 1.0f);
            if (std::abs(d10 + 1.0f) > 1e-6f)
                info.far_plane  = d14 / (d10 + 1.0f);
        } else {
            // Orthographic
            info.fov_y_degrees = 0.0f;
            info.aspect = 1.0f;
            // Ortho near/far from data[10] = -2/(far-near), data[14] = -(far+near)/(far-near)
            // data[10] = -2/(far-near)  → far-near = -2/data[10]
            // data[14] = -(far+near)/(far-near)
            float d10 = P[10], d14 = P[14];
            if (std::abs(d10) > 1e-6f) {
                float range = -2.0f / d10;
                float sum   = -d14 * range; // far + near
                info.near_plane = (sum - range) / 2.0f;
                info.far_plane  = (sum + range) / 2.0f;
            }
        }
        confidence += proj_named ? 0.2f : 0.1f;
    }

    info.confidence = std::min(confidence, 1.0f);
    return info;
}

}  // namespace gla
