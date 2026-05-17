#ifndef BHDR_DWARF_LOCATIONS_H
#define BHDR_DWARF_LOCATIONS_H

/* Hand-rolled DWARF v4 location-expression interpreter for Phase 2 of
 * `gpa trace`. Supports a deliberately narrow opcode subset — enough for
 * x86-64 System V compiler output on primitive locals/parameters on
 * unoptimised or mildly-optimised builds:
 *
 *   DW_OP_addr        — absolute address (globals fallback)
 *   DW_OP_reg0..31    — value lives entirely in a GP register
 *   DW_OP_regx        — same with ULEB reg number
 *   DW_OP_breg0..31   — mem at [reg + sleb offset]
 *   DW_OP_fbreg       — mem at [frame_base + sleb offset]  (CFA-relative)
 *   DW_OP_const1u/s   — push single-byte unsigned/signed constant
 *   DW_OP_plus_uconst — top-of-stack += ULEB
 *   DW_OP_piece       — delimiter; V1 uses only the first piece
 *   DW_OP_deref       — pop addr, push *(uintptr_t*)addr
 *   DW_OP_implicit_value — fixed-width literal value in the expression
 *
 * Any opcode outside this subset causes the evaluator to return
 * BHDR_LOCEVAL_UNSUPPORTED — the caller skips the variable silently. */

#include <stddef.h>
#include <stdint.h>

#include "stack_walker.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    BHDR_LOCEVAL_OK          = 0,
    BHDR_LOCEVAL_UNSUPPORTED = -1, /* opcode outside the supported subset */
    BHDR_LOCEVAL_EMPTY       = -2, /* zero-length expression */
    BHDR_LOCEVAL_MALFORMED   = -3, /* truncated or invalid bytes */
    BHDR_LOCEVAL_UNREADABLE  = -4, /* dereference of unreadable memory */
} BhdrLocEvalError;

/* Describes what the interpreter resolved the expression to. Two flavours:
 *   - ADDRESS: location is a process-space byte address; caller reads N
 *     bytes from there.
 *   - REGISTER: location is a single DWARF register. Value = registers[regno]
 *     truncated/extended to the declared type size.
 *   - IMPLICIT: the bytes are inline in `implicit_bytes` (DW_OP_implicit_value). */
typedef enum {
    BHDR_LOCKIND_ADDRESS  = 1,
    BHDR_LOCKIND_REGISTER = 2,
    BHDR_LOCKIND_IMPLICIT = 3,
} BhdrLocKind;

typedef struct {
    BhdrLocKind kind;
    union {
        uintptr_t address;
        int       regno;   /* DWARF reg number (0..16) */
        struct {
            const uint8_t* data;
            size_t         len;
        } implicit;
    };
} BhdrLocResult;

/* A minimal "register file" view that the interpreter consults for reg
 * / breg / fbreg lookups. `frame_base` is the function's DWARF frame_base
 * already resolved by the caller (usually = frame->cfa on x86-64 SysV). */
typedef struct {
    const uintptr_t* registers;   /* length must cover all referenced regs */
    const uint8_t*   reg_valid;   /* 1 = valid */
    size_t           reg_count;
    uintptr_t        frame_base;
} BhdrLocCtx;

/* Evaluate a DWARF location expression.
 *   expr / expr_len = location-expression bytes (from DW_AT_location block).
 *   ctx             = live register snapshot + frame_base.
 *   out             = resolved location.
 * Returns 0 on success or a negative BhdrLocEvalError. */
int bhdr_dwarf_eval_location(const uint8_t* expr, size_t expr_len,
                            const BhdrLocCtx* ctx,
                            BhdrLocResult* out);

/* Convenience: given a resolved location plus a declared byte_size, read the
 * value into `buf` (up to `buf_cap` bytes). Returns bytes written or
 * negative on failure. For REGISTER and IMPLICIT locations no memory is
 * read. For ADDRESS locations the read is bounded by `buf_cap`. */
int bhdr_dwarf_read_value(const BhdrLocResult* loc, size_t byte_size,
                         const BhdrLocCtx* ctx,
                         void* buf, size_t buf_cap);

#ifdef __cplusplus
}
#endif

#endif /* BHDR_DWARF_LOCATIONS_H */
