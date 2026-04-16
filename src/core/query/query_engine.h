#pragma once
#include "src/core/normalize/normalized_types.h"
#include "src/core/normalize/normalizer.h"
#include "src/core/store/frame_store.h"
#include <cstdint>
#include <optional>
#include <unordered_map>
#include <vector>

namespace gla {

class QueryEngine {
public:
    QueryEngine(gla::store::FrameStore& store, gla::Normalizer& normalizer);

    struct FrameOverview {
        uint64_t frame_id;
        uint32_t draw_call_count;
        uint32_t fb_width, fb_height;
        double timestamp;
    };

    struct PixelResult {
        uint8_t r, g, b, a;
        float depth;
        uint8_t stencil;
    };

    // Frame queries
    std::optional<FrameOverview> frame_overview(uint64_t frame_id) const;
    std::optional<FrameOverview> latest_frame_overview() const;

    // Draw call queries (paginated)
    std::vector<NormalizedDrawCall> list_draw_calls(
        uint64_t frame_id, uint32_t limit = 50, uint32_t offset = 0) const;
    std::optional<NormalizedDrawCall> get_draw_call(
        uint64_t frame_id, uint32_t dc_id) const;

    // Pixel queries
    std::optional<PixelResult> get_pixel(
        uint64_t frame_id, uint32_t x, uint32_t y) const;

    // Normalized frame access (for semantic analysis)
    const NormalizedFrame* get_normalized_frame(uint64_t frame_id) const;

private:
    gla::store::FrameStore& store_;
    gla::Normalizer& normalizer_;

    // Deferred normalization cache: frame_id -> NormalizedFrame
    mutable std::unordered_map<uint64_t, NormalizedFrame> cache_;
    mutable uint32_t normalize_count_ = 0;

    // Get or compute normalized frame. Returns nullptr if frame not in store.
    const NormalizedFrame* get_normalized(uint64_t frame_id) const;

    // Evict cache entries for frames no longer in store
    void evict_stale_cache() const;
};

}  // namespace gla
