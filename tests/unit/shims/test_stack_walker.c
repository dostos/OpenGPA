/* Tests for the libunwind-based stack walker + DWARF location-expression
 * interpreter. No fixture binary needed: we self-walk the test process
 * and exercise the interpreter against hand-rolled expression bytes. */

#define _GNU_SOURCE
#include "src/shims/gl/stack_walker.h"
#include "src/shims/gl/dwarf_locations.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- stack walker ----------------------------------------------------- */

static __attribute__((noinline)) int deep3(BhdrStackSnapshot* out) {
    return bhdr_stack_walk_current(out);
}
static __attribute__((noinline)) int deep2(BhdrStackSnapshot* out) {
    int rc = deep3(out);
    __asm__ volatile("" ::: "memory");
    return rc;
}
static __attribute__((noinline)) int deep1(BhdrStackSnapshot* out) {
    int rc = deep2(out);
    __asm__ volatile("" ::: "memory");
    return rc;
}

static void test_stack_walk_returns_multiple_frames(void) {
    BhdrStackSnapshot s = {0};
    deep1(&s);
    /* We don't assert an exact count — libunwind may elide inlined frames
     * or stop early on libc startup — but we should see at minimum our
     * three deepN frames + main + something libc. */
    assert(s.frame_count >= 3);
    for (size_t i = 0; i < s.frame_count; i++) {
        assert(s.frames[i].pc != 0);
    }
    bhdr_stack_snapshot_free(&s);
    printf("PASS test_stack_walk_returns_multiple_frames\n");
}

static void test_stack_walk_populates_registers(void) {
    BhdrStackSnapshot s = {0};
    deep1(&s);
    /* RSP is always recoverable for a local unwind. */
    int found_rsp = 0;
    for (size_t i = 0; i < s.frame_count; i++) {
        if (s.frames[i].reg_valid[BHDR_REG_RSP] && s.frames[i].registers[BHDR_REG_RSP] != 0) {
            found_rsp = 1;
            break;
        }
    }
    assert(found_rsp);
    bhdr_stack_snapshot_free(&s);
    printf("PASS test_stack_walk_populates_registers\n");
}

static void test_stack_walk_caps_at_max_frames(void) {
    BhdrStackSnapshot s = {0};
    deep1(&s);
    assert(s.frame_count <= BHDR_STACK_MAX_FRAMES);
    bhdr_stack_snapshot_free(&s);
    printf("PASS test_stack_walk_caps_at_max_frames\n");
}

/* ---- deep recursion to force the frame cap --------------------------- */
/* 40 nested frames: deeper than BHDR_STACK_MAX_FRAMES (32) so the walker
 * must stop at the cap. __attribute__((noinline)) keeps the compiler from
 * collapsing the chain; the asm memory clobber keeps the tail non-
 * recursive so each call consumes a real frame. */
static __attribute__((noinline)) int deep_rec(int n, BhdrStackSnapshot* out) {
    if (n == 0) {
        return bhdr_stack_walk_current(out);
    }
    int rc = deep_rec(n - 1, out);
    __asm__ volatile("" ::: "memory");
    return rc;
}

static void test_frame_cap_sets_truncated(void) {
    /* Build a stack with >MAX_FRAMES deep user frames + the libc prelude. */
    BhdrStackSnapshot s = {0};
    deep_rec(40, &s);
    /* Walker must stop at the cap — frame_count is saturated. */
    assert(s.frame_count == BHDR_STACK_MAX_FRAMES);
    /* Every recovered frame still has a valid PC. */
    for (size_t i = 0; i < s.frame_count; i++) {
        assert(s.frames[i].pc != 0);
    }
    bhdr_stack_snapshot_free(&s);
    printf("PASS test_frame_cap_sets_truncated\n");
}

/* ---- location-expression interpreter ---------------------------------- */

static void test_loc_addr_opcode(void) {
    /* DW_OP_addr 0x11223344deadbeef */
    uint8_t expr[9] = {0x03};
    uint64_t addr = 0x11223344deadbeefULL;
    memcpy(expr + 1, &addr, 8);
    BhdrLocCtx ctx = {0};
    BhdrLocResult r = {0};
    int rc = bhdr_dwarf_eval_location(expr, sizeof(expr), &ctx, &r);
    assert(rc == BHDR_LOCEVAL_OK);
    assert(r.kind == BHDR_LOCKIND_ADDRESS);
    assert(r.address == (uintptr_t)addr);
    printf("PASS test_loc_addr_opcode\n");
}

static void test_loc_reg_opcode(void) {
    /* DW_OP_reg3 → whole value in register 3 (RBX on x86-64 SysV DWARF). */
    uint8_t expr[1] = {0x50 + 3};
    uintptr_t regs[BHDR_STACK_REG_COUNT] = {0};
    uint8_t   valid[BHDR_STACK_REG_COUNT] = {0};
    regs[3] = 0xfeedfaceULL; valid[3] = 1;
    BhdrLocCtx ctx = {regs, valid, BHDR_STACK_REG_COUNT, 0};
    BhdrLocResult r = {0};
    int rc = bhdr_dwarf_eval_location(expr, sizeof(expr), &ctx, &r);
    assert(rc == BHDR_LOCEVAL_OK);
    assert(r.kind == BHDR_LOCKIND_REGISTER);
    assert(r.regno == 3);

    uint64_t val = 0;
    int n = bhdr_dwarf_read_value(&r, 8, &ctx, &val, sizeof(val));
    assert(n == 8);
    assert(val == 0xfeedfaceULL);
    printf("PASS test_loc_reg_opcode\n");
}

static void test_loc_regx_opcode(void) {
    /* DW_OP_regx ULEB 5 (→ RDI on SysV). */
    uint8_t expr[2] = {0x90, 5};
    uintptr_t regs[BHDR_STACK_REG_COUNT] = {0};
    uint8_t   valid[BHDR_STACK_REG_COUNT] = {0};
    regs[5] = 0xcafebabeULL; valid[5] = 1;
    BhdrLocCtx ctx = {regs, valid, BHDR_STACK_REG_COUNT, 0};
    BhdrLocResult r = {0};
    int rc = bhdr_dwarf_eval_location(expr, sizeof(expr), &ctx, &r);
    assert(rc == BHDR_LOCEVAL_OK);
    assert(r.kind == BHDR_LOCKIND_REGISTER);
    assert(r.regno == 5);
    printf("PASS test_loc_regx_opcode\n");
}

static void test_loc_breg_reads_memory(void) {
    /* DW_OP_breg6, +sleb 0  →  [RBP + 0]. We point RBP at a stack local. */
    volatile uint64_t stack_slot = 0xAABBCCDD11223344ULL;
    uintptr_t rbp = (uintptr_t)&stack_slot;

    /* SLEB(0) is just a single 0 byte. */
    uint8_t expr[2] = {0x70 + 6, 0};
    uintptr_t regs[BHDR_STACK_REG_COUNT] = {0};
    uint8_t   valid[BHDR_STACK_REG_COUNT] = {0};
    regs[6] = rbp; valid[6] = 1;
    BhdrLocCtx ctx = {regs, valid, BHDR_STACK_REG_COUNT, 0};
    BhdrLocResult r = {0};
    int rc = bhdr_dwarf_eval_location(expr, sizeof(expr), &ctx, &r);
    assert(rc == BHDR_LOCEVAL_OK);
    assert(r.kind == BHDR_LOCKIND_ADDRESS);
    assert(r.address == rbp);

    uint64_t out = 0;
    int n = bhdr_dwarf_read_value(&r, 8, &ctx, &out, sizeof(out));
    assert(n == 8);
    assert(out == 0xAABBCCDD11223344ULL);
    printf("PASS test_loc_breg_reads_memory\n");
}

static void test_loc_fbreg_cfa_relative(void) {
    /* DW_OP_fbreg +sleb -8 → [frame_base - 8]. */
    volatile uint64_t slot = 0x1234567890abcdefULL;
    uintptr_t frame_base = (uintptr_t)&slot + 8;

    /* SLEB(-8) = one byte 0x78 (0x78 has bit7 clear, 7-bit signed = -8). */
    uint8_t expr[2] = {0x91, 0x78};
    BhdrLocCtx ctx = {NULL, NULL, 0, frame_base};
    BhdrLocResult r = {0};
    int rc = bhdr_dwarf_eval_location(expr, sizeof(expr), &ctx, &r);
    assert(rc == BHDR_LOCEVAL_OK);
    assert(r.kind == BHDR_LOCKIND_ADDRESS);
    assert(r.address == (uintptr_t)&slot);

    uint64_t v = 0;
    int n = bhdr_dwarf_read_value(&r, 8, &ctx, &v, sizeof(v));
    assert(n == 8);
    assert(v == 0x1234567890abcdefULL);
    printf("PASS test_loc_fbreg_cfa_relative\n");
}

static void test_loc_plus_uconst(void) {
    /* DW_OP_fbreg +sleb 0 ; DW_OP_plus_uconst 4 */
    volatile uint32_t slot[2] = {0x11111111u, 0x22222222u};
    uintptr_t frame_base = (uintptr_t)&slot[0];
    uint8_t expr[] = {0x91, 0x00, 0x23, 0x04};
    BhdrLocCtx ctx = {NULL, NULL, 0, frame_base};
    BhdrLocResult r = {0};
    int rc = bhdr_dwarf_eval_location(expr, sizeof(expr), &ctx, &r);
    assert(rc == BHDR_LOCEVAL_OK);
    assert(r.kind == BHDR_LOCKIND_ADDRESS);
    assert(r.address == (uintptr_t)&slot[1]);
    printf("PASS test_loc_plus_uconst\n");
}

static void test_loc_deref(void) {
    /* A pointer-to-pointer chain: DW_OP_addr <ptr> ; DW_OP_deref */
    volatile uint64_t target = 0xdeadc0deULL;
    volatile uint64_t ptr = (uint64_t)(uintptr_t)&target;
    uint8_t expr[10] = {0x03};
    memcpy(expr + 1, &(uint64_t){(uint64_t)(uintptr_t)&ptr}, 8);
    expr[9] = 0x06;
    BhdrLocCtx ctx = {0};
    BhdrLocResult r = {0};
    int rc = bhdr_dwarf_eval_location(expr, sizeof(expr), &ctx, &r);
    assert(rc == BHDR_LOCEVAL_OK);
    assert(r.kind == BHDR_LOCKIND_ADDRESS);
    assert(r.address == (uintptr_t)&target);
    printf("PASS test_loc_deref\n");
}

static void test_loc_implicit_value(void) {
    /* DW_OP_implicit_value ULEB 4, <4 bytes>. */
    uint8_t expr[] = {0x9e, 4, 0x78, 0x56, 0x34, 0x12};
    BhdrLocCtx ctx = {0};
    BhdrLocResult r = {0};
    int rc = bhdr_dwarf_eval_location(expr, sizeof(expr), &ctx, &r);
    assert(rc == BHDR_LOCEVAL_OK);
    assert(r.kind == BHDR_LOCKIND_IMPLICIT);
    assert(r.implicit.len == 4);

    uint32_t val = 0;
    int n = bhdr_dwarf_read_value(&r, 4, &ctx, &val, sizeof(val));
    assert(n == 4);
    assert(val == 0x12345678u);
    printf("PASS test_loc_implicit_value\n");
}

static void test_loc_piece_stops_eval(void) {
    /* DW_OP_addr <addr>; DW_OP_piece 4 — first piece = full value for us. */
    uint8_t expr[11] = {0x03};
    uint64_t a = 0xaabbccddULL;
    memcpy(expr + 1, &a, 8);
    expr[9] = 0x93; expr[10] = 0x04;
    BhdrLocCtx ctx = {0};
    BhdrLocResult r = {0};
    int rc = bhdr_dwarf_eval_location(expr, sizeof(expr), &ctx, &r);
    assert(rc == BHDR_LOCEVAL_OK);
    assert(r.kind == BHDR_LOCKIND_ADDRESS);
    assert(r.address == (uintptr_t)a);
    printf("PASS test_loc_piece_stops_eval\n");
}

static void test_loc_const1u_s(void) {
    uint8_t expr_u[2] = {0x08, 0x42};
    BhdrLocCtx ctx = {0};
    BhdrLocResult r = {0};
    int rc = bhdr_dwarf_eval_location(expr_u, sizeof(expr_u), &ctx, &r);
    assert(rc == BHDR_LOCEVAL_OK);
    assert(r.kind == BHDR_LOCKIND_ADDRESS);
    assert(r.address == 0x42);

    uint8_t expr_s[2] = {0x09, 0xff}; /* const1s -1 */
    rc = bhdr_dwarf_eval_location(expr_s, sizeof(expr_s), &ctx, &r);
    assert(rc == BHDR_LOCEVAL_OK);
    assert(r.address == (uintptr_t)-1);
    printf("PASS test_loc_const1u_s\n");
}

static void test_loc_rejects_unsupported_opcode(void) {
    /* 0x10 = DW_OP_constu. Not in our subset. */
    uint8_t expr[2] = {0x10, 0};
    BhdrLocCtx ctx = {0};
    BhdrLocResult r = {0};
    int rc = bhdr_dwarf_eval_location(expr, sizeof(expr), &ctx, &r);
    assert(rc == BHDR_LOCEVAL_UNSUPPORTED);
    printf("PASS test_loc_rejects_unsupported_opcode\n");
}

static void test_loc_empty_expression(void) {
    BhdrLocCtx ctx = {0};
    BhdrLocResult r = {0};
    int rc = bhdr_dwarf_eval_location(NULL, 0, &ctx, &r);
    assert(rc == BHDR_LOCEVAL_EMPTY);
    printf("PASS test_loc_empty_expression\n");
}

int main(void) {
    test_stack_walk_returns_multiple_frames();
    test_stack_walk_populates_registers();
    test_stack_walk_caps_at_max_frames();
    test_frame_cap_sets_truncated();

    test_loc_addr_opcode();
    test_loc_reg_opcode();
    test_loc_regx_opcode();
    test_loc_breg_reads_memory();
    test_loc_fbreg_cfa_relative();
    test_loc_plus_uconst();
    test_loc_deref();
    test_loc_implicit_value();
    test_loc_piece_stops_eval();
    test_loc_const1u_s();
    test_loc_rejects_unsupported_opcode();
    test_loc_empty_expression();

    printf("All stack-walker + DWARF-locations tests passed.\n");
    return 0;
}
