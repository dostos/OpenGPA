#include "src/core/store/frame_store.h"
#include <algorithm>

namespace gpa::store {

FrameStore::FrameStore(size_t capacity)
    : capacity_(capacity) {
    buffer_.reserve(capacity_);
}

void FrameStore::store(RawFrame frame) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (buffer_.size() < capacity_) {
        buffer_.push_back(std::move(frame));
        write_pos_ = buffer_.size() % capacity_;
    } else {
        buffer_[write_pos_] = std::move(frame);
        write_pos_ = (write_pos_ + 1) % capacity_;
    }
    ++total_stored_;
}

const RawFrame* FrameStore::get(uint64_t frame_id) const {
    std::lock_guard<std::mutex> lock(mutex_);
    for (const auto& f : buffer_) {
        if (f.frame_id == frame_id) {
            return &f;
        }
    }
    return nullptr;
}

const RawFrame* FrameStore::latest() const {
    std::lock_guard<std::mutex> lock(mutex_);
    if (buffer_.empty()) {
        return nullptr;
    }
    // write_pos_ points to the next write slot.
    // The last written slot is (write_pos_ - 1 + size) % size when full,
    // or buffer_.size() - 1 when not yet full.
    size_t last_idx;
    if (buffer_.size() < capacity_) {
        last_idx = buffer_.size() - 1;
    } else {
        last_idx = (write_pos_ == 0) ? capacity_ - 1 : write_pos_ - 1;
    }
    return &buffer_[last_idx];
}

size_t FrameStore::count() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return buffer_.size();
}

uint64_t FrameStore::total_stored() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return total_stored_;
}

}  // namespace gpa::store
