/* Tiny DWARF location-expression interpreter for Phase 2 of `gpa trace`.
 *
 * Deliberately a ~200-line subset. Anything outside the supported opcodes
 * returns GPA_LOCEVAL_UNSUPPORTED and the caller silently skips the
 * variable — we prefer graceful degradation over wrong answers. */

#define _GNU_SOURCE
#include "dwarf_locations.h"

#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <setjmp.h>

/* ---- DWARF opcode constants (subset) ---------------------------------- */

#define DW_OP_addr              0x03
#define DW_OP_deref             0x06
#define DW_OP_const1u           0x08
#define DW_OP_const1s           0x09
#define DW_OP_plus_uconst       0x23
#define DW_OP_reg0              0x50
#define DW_OP_reg31             0x6f
#define DW_OP_breg0             0x70
#define DW_OP_breg31            0x8f
#define DW_OP_regx              0x90
#define DW_OP_fbreg             0x91
#define DW_OP_piece             0x93
#define DW_OP_implicit_value    0x9e

/* ---- minimal LEB128 readers ------------------------------------------- */

static int rd_uleb(const uint8_t** p, const uint8_t* end, uint64_t* out) {
    uint64_t r = 0; int shift = 0;
    while (*p < end) {
        uint8_t b = *(*p)++;
        r |= (uint64_t)(b & 0x7f) << shift;
        if ((b & 0x80) == 0) { *out = r; return 1; }
        shift += 7;
        if (shift > 63) return 0;
    }
    return 0;
}

static int rd_sleb(const uint8_t** p, const uint8_t* end, int64_t* out) {
    int64_t r = 0; int shift = 0; uint8_t b = 0;
    while (*p < end) {
        b = *(*p)++;
        r |= (int64_t)(b & 0x7f) << shift;
        shift += 7;
        if ((b & 0x80) == 0) break;
        if (shift > 63) return 0;
    }
    if (shift < 64 && (b & 0x40)) r |= -((int64_t)1 << shift);
    *out = r; return 1;
}

/* ---- safe dereference ------------------------------------------------- */
/* Caller-supplied memory is arbitrary — guard against wild pointers by
 * wrapping the load in a SIGSEGV-resistant probe. We route through
 * /proc/self/mem so a bad address becomes an I/O error rather than a
 * crashed process. (This is the same trick RenderDoc and perf use.) */

#include <fcntl.h>
#include <unistd.h>

static int safe_read(uintptr_t addr, void* buf, size_t n) {
    static int pm_fd = -1;
    if (pm_fd < 0) {
        pm_fd = open("/proc/self/mem", O_RDONLY | O_CLOEXEC);
        if (pm_fd < 0) return -1;
    }
    ssize_t r = pread(pm_fd, buf, n, (off_t)addr);
    return (r == (ssize_t)n) ? 0 : -1;
}

/* ---- evaluator -------------------------------------------------------- */

#define STACK_MAX 32

int gpa_dwarf_eval_location(const uint8_t* expr, size_t expr_len,
                            const GpaLocCtx* ctx,
                            GpaLocResult* out) {
    memset(out, 0, sizeof(*out));
    if (expr_len == 0) return GPA_LOCEVAL_EMPTY;

    const uint8_t* p   = expr;
    const uint8_t* end = expr + expr_len;

    int64_t st[STACK_MAX];
    int     sp = 0;
    int     have_regloc = 0;
    int     regloc_no   = -1;

    while (p < end) {
        uint8_t op = *p++;

        if (op == DW_OP_addr) {
            /* DWARF 4 on x86-64 = 8-byte addr. */
            if (p + 8 > end) return GPA_LOCEVAL_MALFORMED;
            uint64_t a = 0;
            memcpy(&a, p, 8);
            p += 8;
            if (sp >= STACK_MAX) return GPA_LOCEVAL_MALFORMED;
            st[sp++] = (int64_t)a;
        }
        else if (op >= DW_OP_reg0 && op <= DW_OP_reg31) {
            /* Whole value in register — must be the only op (or followed
             * by piece). */
            have_regloc = 1;
            regloc_no = op - DW_OP_reg0;
        }
        else if (op == DW_OP_regx) {
            uint64_t r;
            if (!rd_uleb(&p, end, &r)) return GPA_LOCEVAL_MALFORMED;
            have_regloc = 1;
            regloc_no = (int)r;
        }
        else if (op >= DW_OP_breg0 && op <= DW_OP_breg31) {
            int reg = op - DW_OP_breg0;
            int64_t off;
            if (!rd_sleb(&p, end, &off)) return GPA_LOCEVAL_MALFORMED;
            if (reg >= (int)ctx->reg_count || !ctx->reg_valid[reg])
                return GPA_LOCEVAL_UNSUPPORTED;
            if (sp >= STACK_MAX) return GPA_LOCEVAL_MALFORMED;
            st[sp++] = (int64_t)ctx->registers[reg] + off;
        }
        else if (op == DW_OP_fbreg) {
            int64_t off;
            if (!rd_sleb(&p, end, &off)) return GPA_LOCEVAL_MALFORMED;
            if (sp >= STACK_MAX) return GPA_LOCEVAL_MALFORMED;
            st[sp++] = (int64_t)ctx->frame_base + off;
        }
        else if (op == DW_OP_const1u) {
            if (p + 1 > end) return GPA_LOCEVAL_MALFORMED;
            if (sp >= STACK_MAX) return GPA_LOCEVAL_MALFORMED;
            st[sp++] = (int64_t)*p++;
        }
        else if (op == DW_OP_const1s) {
            if (p + 1 > end) return GPA_LOCEVAL_MALFORMED;
            if (sp >= STACK_MAX) return GPA_LOCEVAL_MALFORMED;
            st[sp++] = (int64_t)(int8_t)*p++;
        }
        else if (op == DW_OP_plus_uconst) {
            uint64_t v;
            if (!rd_uleb(&p, end, &v)) return GPA_LOCEVAL_MALFORMED;
            if (sp < 1) return GPA_LOCEVAL_MALFORMED;
            st[sp - 1] += (int64_t)v;
        }
        else if (op == DW_OP_deref) {
            if (sp < 1) return GPA_LOCEVAL_MALFORMED;
            uintptr_t a = (uintptr_t)st[sp - 1];
            uintptr_t v;
            if (safe_read(a, &v, sizeof(v)) < 0) return GPA_LOCEVAL_UNREADABLE;
            st[sp - 1] = (int64_t)v;
        }
        else if (op == DW_OP_piece) {
            /* Stop at first piece — V1 limitation. If there's already a
             * full result on the stack / in a register, return it. */
            break;
        }
        else if (op == DW_OP_implicit_value) {
            uint64_t len;
            if (!rd_uleb(&p, end, &len)) return GPA_LOCEVAL_MALFORMED;
            if (p + len > end) return GPA_LOCEVAL_MALFORMED;
            out->kind = GPA_LOCKIND_IMPLICIT;
            out->implicit.data = p;
            out->implicit.len  = (size_t)len;
            return GPA_LOCEVAL_OK;
        }
        else {
            /* Opcode outside our subset — bail. */
            return GPA_LOCEVAL_UNSUPPORTED;
        }
    }

    if (have_regloc) {
        out->kind  = GPA_LOCKIND_REGISTER;
        out->regno = regloc_no;
        return GPA_LOCEVAL_OK;
    }
    if (sp >= 1) {
        out->kind    = GPA_LOCKIND_ADDRESS;
        out->address = (uintptr_t)st[sp - 1];
        return GPA_LOCEVAL_OK;
    }
    return GPA_LOCEVAL_MALFORMED;
}

int gpa_dwarf_read_value(const GpaLocResult* loc, size_t byte_size,
                         const GpaLocCtx* ctx,
                         void* buf, size_t buf_cap) {
    if (byte_size == 0 || byte_size > buf_cap) return -1;
    switch (loc->kind) {
    case GPA_LOCKIND_ADDRESS: {
        if (safe_read(loc->address, buf, byte_size) < 0) return -1;
        return (int)byte_size;
    }
    case GPA_LOCKIND_REGISTER: {
        if (!ctx || loc->regno < 0 ||
            (size_t)loc->regno >= ctx->reg_count ||
            !ctx->reg_valid[loc->regno]) return -1;
        uintptr_t rv = ctx->registers[loc->regno];
        size_t n = byte_size <= sizeof(rv) ? byte_size : sizeof(rv);
        memset(buf, 0, byte_size);
        memcpy(buf, &rv, n);
        return (int)byte_size;
    }
    case GPA_LOCKIND_IMPLICIT: {
        size_t n = byte_size <= loc->implicit.len ? byte_size : loc->implicit.len;
        memset(buf, 0, byte_size);
        memcpy(buf, loc->implicit.data, n);
        return (int)byte_size;
    }
    }
    return -1;
}
