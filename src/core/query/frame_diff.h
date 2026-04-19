#pragma once
#include "src/core/normalize/normalized_types.h"
#include <cstdint>
#include <string>
#include <vector>

namespace gpa {

struct DrawCallDiff {
    uint32_t dc_id;
    bool added;      // present in B but not A
    bool removed;    // present in A but not B
    bool modified;   // present in both but different
    // What changed (only if modified):
    bool shader_changed    = false;
    bool params_changed    = false;
    bool pipeline_changed  = false;
    bool textures_changed  = false;
    std::vector<std::string> changed_param_names;  // which params differ
};

struct PixelDiff {
    uint32_t x, y;
    uint8_t a_r, a_g, a_b, a_a;   // frame A pixel
    uint8_t b_r, b_g, b_b, b_a;   // frame B pixel
};

struct FrameDiff {
    uint64_t frame_id_a, frame_id_b;

    // Summary
    uint32_t draw_calls_added     = 0;
    uint32_t draw_calls_removed   = 0;
    uint32_t draw_calls_modified  = 0;
    uint32_t draw_calls_unchanged = 0;
    uint32_t pixels_changed       = 0;

    // Details (populated based on depth)
    std::vector<DrawCallDiff> draw_call_diffs;
    std::vector<PixelDiff>    pixel_diffs;   // only first N (limit)
};

class FrameDiffer {
public:
    enum class DiffDepth { Summary, DrawCalls, Pixels };

    FrameDiff diff(const NormalizedFrame& a, const NormalizedFrame& b,
                   DiffDepth depth        = DiffDepth::Summary,
                   uint32_t pixel_diff_limit = 100) const;

private:
    DrawCallDiff compare_draw_calls(const NormalizedDrawCall& a,
                                    const NormalizedDrawCall& b) const;
    bool pipeline_equal(const NormalizedPipelineState& a,
                        const NormalizedPipelineState& b) const;
    bool params_equal(const std::vector<ShaderParameter>& a,
                      const std::vector<ShaderParameter>& b) const;
    bool textures_equal(const std::vector<TextureBinding>& a,
                        const std::vector<TextureBinding>& b) const;
};

}  // namespace gpa
