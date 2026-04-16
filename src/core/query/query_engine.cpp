#include "src/core/query/query_engine.h"

namespace gla {

QueryEngine::QueryEngine(gla::store::FrameStore& store, gla::Normalizer& normalizer)
    : store_(store), normalizer_(normalizer) {}

// ─── Private helpers ──────────────────────────────────────────────────────────

const NormalizedFrame* QueryEngine::get_normalized(uint64_t frame_id) const {
    // 1. Check cache
    auto it = cache_.find(frame_id);
    if (it != cache_.end()) {
        return &it->second;
    }

    // 2. Look up raw frame
    const gla::store::RawFrame* raw = store_.get(frame_id);
    if (!raw) {
        return nullptr;
    }

    // 3. Normalize and cache
    NormalizedFrame nf = normalizer_.normalize(*raw);
    auto [ins_it, _] = cache_.emplace(frame_id, std::move(nf));

    // 4. Periodic eviction every 10 normalizations
    ++normalize_count_;
    if (normalize_count_ % 10 == 0) {
        evict_stale_cache();
    }

    return &ins_it->second;
}

void QueryEngine::evict_stale_cache() const {
    for (auto it = cache_.begin(); it != cache_.end(); ) {
        if (!store_.get(it->first)) {
            it = cache_.erase(it);
        } else {
            ++it;
        }
    }
}

// ─── Frame queries ────────────────────────────────────────────────────────────

std::optional<QueryEngine::FrameOverview> QueryEngine::frame_overview(uint64_t frame_id) const {
    const NormalizedFrame* nf = get_normalized(frame_id);
    if (!nf) return std::nullopt;

    uint32_t dc_count = 0;
    for (const auto& rp : nf->render_passes) {
        dc_count += static_cast<uint32_t>(rp.draw_calls.size());
    }

    return FrameOverview{
        .frame_id       = nf->frame_id,
        .draw_call_count = dc_count,
        .fb_width       = nf->fb_width,
        .fb_height      = nf->fb_height,
        .timestamp      = nf->timestamp,
    };
}

std::optional<QueryEngine::FrameOverview> QueryEngine::latest_frame_overview() const {
    const gla::store::RawFrame* raw = store_.latest();
    if (!raw) return std::nullopt;
    return frame_overview(raw->frame_id);
}

// ─── Draw call queries ────────────────────────────────────────────────────────

std::vector<NormalizedDrawCall> QueryEngine::list_draw_calls(
        uint64_t frame_id, uint32_t limit, uint32_t offset) const {
    const NormalizedFrame* nf = get_normalized(frame_id);
    if (!nf) return {};

    // Collect all draw calls across render passes
    std::vector<const NormalizedDrawCall*> all;
    for (const auto& rp : nf->render_passes) {
        for (const auto& dc : rp.draw_calls) {
            all.push_back(&dc);
        }
    }

    std::vector<NormalizedDrawCall> result;
    uint32_t size = static_cast<uint32_t>(all.size());
    if (offset >= size) return result;

    uint32_t end = std::min(offset + limit, size);
    result.reserve(end - offset);
    for (uint32_t i = offset; i < end; ++i) {
        result.push_back(*all[i]);
    }
    return result;
}

std::optional<NormalizedDrawCall> QueryEngine::get_draw_call(
        uint64_t frame_id, uint32_t dc_id) const {
    const NormalizedFrame* nf = get_normalized(frame_id);
    if (!nf) return std::nullopt;

    for (const auto& rp : nf->render_passes) {
        for (const auto& dc : rp.draw_calls) {
            if (dc.id == dc_id) {
                return dc;
            }
        }
    }
    return std::nullopt;
}

// ─── Pixel queries ────────────────────────────────────────────────────────────

std::optional<QueryEngine::PixelResult> QueryEngine::get_pixel(
        uint64_t frame_id, uint32_t x, uint32_t y) const {
    const NormalizedFrame* nf = get_normalized(frame_id);
    if (!nf) return std::nullopt;

    if (x >= nf->fb_width || y >= nf->fb_height) return std::nullopt;

    uint32_t idx = y * nf->fb_width + x;
    uint32_t color_idx = idx * 4;

    if (color_idx + 3 >= nf->fb_color.size()) return std::nullopt;

    PixelResult result{};
    result.r = nf->fb_color[color_idx + 0];
    result.g = nf->fb_color[color_idx + 1];
    result.b = nf->fb_color[color_idx + 2];
    result.a = nf->fb_color[color_idx + 3];

    if (idx < nf->fb_depth.size()) {
        result.depth = nf->fb_depth[idx];
    } else {
        result.depth = 0.0f;
    }

    if (idx < nf->fb_stencil.size()) {
        result.stencil = nf->fb_stencil[idx];
    } else {
        result.stencil = 0;
    }

    return result;
}

}  // namespace gla
