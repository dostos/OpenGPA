#pragma once
#include "src/core/store/raw_frame.h"
#include <mutex>
#include <optional>
#include <vector>

namespace gpa::store {

class FrameStore {
public:
    explicit FrameStore(size_t capacity = 60);

    // Store a frame (moves it). If full, evicts oldest.
    void store(RawFrame frame);

    // Get frame by ID. Returns nullptr if not found (evicted or never stored).
    const RawFrame* get(uint64_t frame_id) const;

    // Get the most recently stored frame. Returns nullptr if empty.
    const RawFrame* latest() const;

    // Number of frames currently stored
    size_t count() const;

    // Total frames ever stored
    uint64_t total_stored() const;

private:
    size_t capacity_;
    std::vector<RawFrame> buffer_;
    size_t write_pos_ = 0;
    uint64_t total_stored_ = 0;
    mutable std::mutex mutex_;
};

}  // namespace gpa::store
