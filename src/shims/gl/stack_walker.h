#ifndef BHDR_STACK_WALKER_H
#define BHDR_STACK_WALKER_H

/* Thin wrapper around libunwind for Phase 2 of `gpa trace`.
 *
 * Captures a snapshot of the current thread's call stack — one PC plus a
 * live cursor state per frame — and gives the DWARF location interpreter
 * enough information to evaluate local-variable location expressions.
 *
 * Scope:
 *   - x86-64 System V only (that's all `gpa trace` Phase 2 targets).
 *   - Up to `BHDR_STACK_MAX_FRAMES` (32) frames; deeper stacks are truncated.
 *   - Single-threaded: callers must not invoke concurrently.
 *   - Graceful degradation: any libunwind failure just returns a shorter
 *     (or empty) stack; never crashes the host.
 *
 * The walker never dereferences arbitrary memory on the stack; that's the
 * caller's job once they have `BhdrStackFrame.registers` + a memory reader. */

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define BHDR_STACK_MAX_FRAMES 32

/* x86-64 System V general-purpose registers in DWARF register-number order
 * (see System V AMD64 ABI Draft 0.99.8 §3.6.2 table 3.36). */
typedef enum {
    BHDR_REG_RAX = 0,
    BHDR_REG_RDX = 1,
    BHDR_REG_RCX = 2,
    BHDR_REG_RBX = 3,
    BHDR_REG_RSI = 4,
    BHDR_REG_RDI = 5,
    BHDR_REG_RBP = 6,
    BHDR_REG_RSP = 7,
    BHDR_REG_R8  = 8,
    BHDR_REG_R9  = 9,
    BHDR_REG_R10 = 10,
    BHDR_REG_R11 = 11,
    BHDR_REG_R12 = 12,
    BHDR_REG_R13 = 13,
    BHDR_REG_R14 = 14,
    BHDR_REG_R15 = 15,
    BHDR_REG_RIP = 16,
    BHDR_STACK_REG_COUNT = 17,
} BhdrDwarfRegNum;

typedef struct {
    /* Program counter for this frame — where execution would resume once
     * the callee returns. For frame 0 it's the current PC. */
    uintptr_t pc;

    /* Canonical Frame Address (CFA). DWARF's `DW_OP_fbreg` is offset from
     * this on most compilers (clang + gcc both emit frame_base = CFA). */
    uintptr_t cfa;

    /* Snapshot of the 17 GP registers the interpreter may reference.
     * Indexed by BhdrDwarfRegNum. Entries for registers libunwind couldn't
     * recover are set to 0 and `reg_valid[i]` is 0. */
    uintptr_t registers[BHDR_STACK_REG_COUNT];
    uint8_t   reg_valid[BHDR_STACK_REG_COUNT];

    /* Best-effort symbol name of the function for this frame (libunwind's
     * unw_get_proc_name). Owned by the caller via the containing
     * BhdrStackSnapshot's string pool — do not free individually. Can be
     * NULL if unknown. */
    const char* proc_name;
    uintptr_t   proc_offset; /* PC - function_start, if proc_name known */
} BhdrStackFrame;

typedef struct {
    BhdrStackFrame frames[BHDR_STACK_MAX_FRAMES];
    size_t        frame_count;
    /* Owns the string storage for every frame's `proc_name`. */
    char*         strpool;
    size_t        strpool_len;
    size_t        strpool_cap;
} BhdrStackSnapshot;

/* Capture the current thread's stack trace into `out`. On return,
 * `out->frame_count` is the number of frames actually captured (0 on total
 * failure). Always safe to call; always returns 0. Caller must later call
 * bhdr_stack_snapshot_free() to release the string pool. */
int bhdr_stack_walk_current(BhdrStackSnapshot* out);

/* Release the string pool owned by a snapshot. Safe on zero-init. */
void bhdr_stack_snapshot_free(BhdrStackSnapshot* s);

#ifdef __cplusplus
}
#endif

#endif /* BHDR_STACK_WALKER_H */
