#include "src/core/query/frame_diff.h"
#include <algorithm>
#include <cstring>
#include <unordered_map>

namespace gla {

// ─── Private helpers ──────────────────────────────────────────────────────────

bool FrameDiffer::pipeline_equal(const NormalizedPipelineState& a,
                                  const NormalizedPipelineState& b) const {
    return std::memcmp(a.viewport, b.viewport, sizeof(a.viewport)) == 0
        && std::memcmp(a.scissor,  b.scissor,  sizeof(a.scissor))  == 0
        && a.scissor_enabled == b.scissor_enabled
        && a.depth_test      == b.depth_test
        && a.depth_write     == b.depth_write
        && a.depth_func      == b.depth_func
        && a.blend_enabled   == b.blend_enabled
        && a.blend_src       == b.blend_src
        && a.blend_dst       == b.blend_dst
        && a.cull_enabled    == b.cull_enabled
        && a.cull_mode       == b.cull_mode
        && a.front_face      == b.front_face;
}

bool FrameDiffer::params_equal(const std::vector<ShaderParameter>& a,
                                const std::vector<ShaderParameter>& b) const {
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); ++i) {
        if (a[i].name != b[i].name) return false;
        if (a[i].type != b[i].type) return false;
        if (a[i].data != b[i].data) return false;
    }
    return true;
}

bool FrameDiffer::textures_equal(const std::vector<TextureBinding>& a,
                                  const std::vector<TextureBinding>& b) const {
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); ++i) {
        if (a[i].slot       != b[i].slot)       return false;
        if (a[i].texture_id != b[i].texture_id) return false;
        if (a[i].width      != b[i].width)      return false;
        if (a[i].height     != b[i].height)     return false;
        if (a[i].format     != b[i].format)     return false;
    }
    return true;
}

DrawCallDiff FrameDiffer::compare_draw_calls(const NormalizedDrawCall& a,
                                              const NormalizedDrawCall& b) const {
    DrawCallDiff d{};
    d.dc_id    = a.id;
    d.added    = false;
    d.removed  = false;
    d.modified = false;

    bool shader_same   = (a.shader_id == b.shader_id);
    bool params_same   = params_equal(a.params, b.params);
    bool pipeline_same = pipeline_equal(a.pipeline, b.pipeline);
    bool textures_same = textures_equal(a.textures, b.textures);

    if (!shader_same || !params_same || !pipeline_same || !textures_same) {
        d.modified        = true;
        d.shader_changed  = !shader_same;
        d.params_changed  = !params_same;
        d.pipeline_changed= !pipeline_same;
        d.textures_changed= !textures_same;

        // Identify which param names differ (by name lookup)
        if (!params_same) {
            // Build map of name->data for B
            std::unordered_map<std::string, const ShaderParameter*> b_map;
            for (const auto& p : b.params) {
                b_map[p.name] = &p;
            }
            for (const auto& pa : a.params) {
                auto it = b_map.find(pa.name);
                if (it == b_map.end()) {
                    d.changed_param_names.push_back(pa.name);
                } else if (pa.data != it->second->data || pa.type != it->second->type) {
                    d.changed_param_names.push_back(pa.name);
                }
            }
            // Params in B but not A
            std::unordered_map<std::string, const ShaderParameter*> a_map;
            for (const auto& p : a.params) {
                a_map[p.name] = &p;
            }
            for (const auto& pb : b.params) {
                if (a_map.find(pb.name) == a_map.end()) {
                    d.changed_param_names.push_back(pb.name);
                }
            }
        }
    }

    return d;
}

// ─── Public diff ──────────────────────────────────────────────────────────────

FrameDiff FrameDiffer::diff(const NormalizedFrame& a, const NormalizedFrame& b,
                             DiffDepth depth, uint32_t pixel_diff_limit) const {
    FrameDiff result{};
    result.frame_id_a = a.frame_id;
    result.frame_id_b = b.frame_id;

    // --- Collect flat draw call lists ---
    auto all_a = a.all_draw_calls();
    auto all_b = b.all_draw_calls();

    // Build map id -> draw_call for A and B
    std::unordered_map<uint32_t, const NormalizedDrawCall*> map_a, map_b;
    for (const auto& dc_ref : all_a) {
        map_a[dc_ref.get().id] = &dc_ref.get();
    }
    for (const auto& dc_ref : all_b) {
        map_b[dc_ref.get().id] = &dc_ref.get();
    }

    // Removed: in A but not B
    for (const auto& [id, dc] : map_a) {
        if (map_b.find(id) == map_b.end()) {
            ++result.draw_calls_removed;
            if (depth == DiffDepth::DrawCalls || depth == DiffDepth::Pixels) {
                DrawCallDiff d{};
                d.dc_id   = id;
                d.removed = true;
                d.added   = false;
                d.modified= false;
                result.draw_call_diffs.push_back(std::move(d));
            }
        }
    }

    // Added: in B but not A
    for (const auto& [id, dc] : map_b) {
        if (map_a.find(id) == map_a.end()) {
            ++result.draw_calls_added;
            if (depth == DiffDepth::DrawCalls || depth == DiffDepth::Pixels) {
                DrawCallDiff d{};
                d.dc_id   = id;
                d.added   = true;
                d.removed = false;
                d.modified= false;
                result.draw_call_diffs.push_back(std::move(d));
            }
        }
    }

    // Present in both: compare
    for (const auto& [id, dc_a] : map_a) {
        auto it_b = map_b.find(id);
        if (it_b == map_b.end()) continue;

        DrawCallDiff d = compare_draw_calls(*dc_a, *it_b->second);
        if (d.modified) {
            ++result.draw_calls_modified;
            if (depth == DiffDepth::DrawCalls || depth == DiffDepth::Pixels) {
                result.draw_call_diffs.push_back(std::move(d));
            }
        } else {
            ++result.draw_calls_unchanged;
        }
    }

    // --- Pixel diff ---
    // Count pixel differences using the framebuffer data
    uint32_t w = std::min(a.fb_width,  b.fb_width);
    uint32_t h = std::min(a.fb_height, b.fb_height);

    if (w > 0 && h > 0
        && a.fb_color.size() >= w * h * 4u
        && b.fb_color.size() >= w * h * 4u) {

        for (uint32_t y = 0; y < h; ++y) {
            for (uint32_t x = 0; x < w; ++x) {
                uint32_t base = (y * w + x) * 4;
                uint8_t ar = a.fb_color[base+0], ag = a.fb_color[base+1],
                        ab = a.fb_color[base+2], aa = a.fb_color[base+3];
                uint8_t br = b.fb_color[base+0], bg = b.fb_color[base+1],
                        bb = b.fb_color[base+2], ba = b.fb_color[base+3];
                if (ar != br || ag != bg || ab != bb || aa != ba) {
                    ++result.pixels_changed;
                    if (depth == DiffDepth::Pixels
                        && result.pixel_diffs.size() < pixel_diff_limit) {
                        PixelDiff pd{};
                        pd.x   = x;  pd.y   = y;
                        pd.a_r = ar; pd.a_g = ag; pd.a_b = ab; pd.a_a = aa;
                        pd.b_r = br; pd.b_g = bg; pd.b_b = bb; pd.b_a = ba;
                        result.pixel_diffs.push_back(pd);
                    }
                }
            }
        }
    }

    return result;
}

}  // namespace gla
