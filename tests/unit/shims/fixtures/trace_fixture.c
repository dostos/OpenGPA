/* Tiny program with known globals across primitive types.
 * Compiled with -g -O0 so DWARF contains DW_TAG_variable entries for each.
 * Used by tests/unit/shims/test_native_trace.c to verify the hand-rolled
 * DWARF parser can round-trip name + address + encoding. */

#include <stdint.h>

static double  g_test_double = 16.58;
static int32_t g_test_int    = 42;
static float   g_test_float  = 3.14f;

/* External linkage — exercises non-static globals too. */
double g_public_double = 100.0;

int main(void) {
    /* Force the compiler to keep these addresses observable. */
    volatile uintptr_t keep;
    keep  = (uintptr_t)&g_test_double;
    keep ^= (uintptr_t)&g_test_int;
    keep ^= (uintptr_t)&g_test_float;
    keep ^= (uintptr_t)&g_public_double;
    (void)keep;
    return 0;
}
