#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>

namespace gla {

// Slot state machine (CAS transitions):
//   FREE (0) -> WRITING (1): writer claims via CAS
//   WRITING (1) -> READY (2): writer commits after filling data
//   READY (2) -> READING (3): reader claims via CAS
//   READING (3) -> FREE (0): reader releases after processing
enum class SlotState : uint32_t {
    FREE    = 0,
    WRITING = 1,
    READY   = 2,
    READING = 3,
};

// Per-slot header placed immediately before the data region.
// Layout (manually verified to be exactly 64 bytes):
//   [0]  state     atomic<uint32_t>  — 4 bytes
//   [4]  _pad0     uint32_t          — 4 bytes (natural alignment pad for frame_id)
//   [8]  frame_id  uint64_t          — 8 bytes
//   [16] data_size uint64_t          — 8 bytes
//   [24] _pad1     uint8_t[40]       — 40 bytes
//                                    = 64 bytes total
struct alignas(64) SlotHeader {
    std::atomic<uint32_t> state{static_cast<uint32_t>(SlotState::FREE)};
    uint32_t              _pad0{0};
    uint64_t              frame_id{0};
    uint64_t              data_size{0};
    uint8_t               _pad1[40]{};
};
static_assert(sizeof(SlotHeader) == 64, "SlotHeader must be exactly one cache line");

// Ring-buffer header placed at the start of the shared memory segment.
struct RingHeader {
    uint64_t magic;       // GLA_SHM_MAGIC — sanity check on open()
    uint32_t num_slots;
    uint32_t _pad;
    uint64_t slot_size;   // usable data bytes per slot
    uint64_t total_size;  // total mmap size (informational)
};

static constexpr uint64_t GLA_SHM_MAGIC = 0x474C415F53484D00ULL; // "GLA_SHM\0"

class ShmRingBuffer {
public:
    // Owner: creates the shm segment (unlinks any stale segment first).
    static std::unique_ptr<ShmRingBuffer> create(
        const std::string& name, uint32_t num_slots, size_t slot_size);

    // Client: opens an existing shm segment for read/write.
    static std::unique_ptr<ShmRingBuffer> open(const std::string& name);

    ~ShmRingBuffer();

    // Opaque handles returned to callers.
    struct WriteSlot {
        void*    data;   // pointer into shm data region; nullptr on failure
        uint32_t index;
    };
    struct ReadSlot {
        const void* data;   // nullptr on failure
        uint64_t    size;
        uint32_t    index;
    };

    // Writer side (GL shim) ------------------------------------------------
    // Claim a FREE slot for writing; returns {nullptr, 0} if none available.
    WriteSlot claim_write_slot();
    // Mark a previously claimed slot as READY after writing `size` bytes.
    void commit_write(uint32_t index, uint64_t size);

    // Reader side (core engine) --------------------------------------------
    // Claim a READY slot for reading; returns {nullptr, 0, 0} if none.
    ReadSlot claim_read_slot();
    // Mark a previously claimed slot as FREE after processing.
    void release_read(uint32_t index);

    // Accessors
    uint32_t num_slots()  const;
    size_t   slot_size()  const;

private:
    ShmRingBuffer() = default;

    // Pointer helpers
    SlotHeader* slot_header(uint32_t index) const;
    void*       slot_data(uint32_t index) const;

    void*       base_{nullptr};    // start of mmap region
    size_t      mapped_size_{0};   // total mmap size
    std::string name_;             // shm name (e.g. "/gla_ipc")
    bool        owner_{false};     // true iff we should call shm_unlink
    uint32_t    num_slots_{0};
    uint64_t    slot_size_{0};
    uint32_t    next_write_{0};    // hint for round-robin write scan
    uint32_t    next_read_{0};     // hint for round-robin read scan
};

} // namespace gla
