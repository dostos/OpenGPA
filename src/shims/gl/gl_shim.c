#define _GNU_SOURCE
#include <stdio.h>
#include <unistd.h>
#include "gl_wrappers.h"
#include "shadow_state.h"
#include "ipc_client.h"
#include "native_trace.h"

BhdrRealGlFuncs bhdr_real_gl = {0};
BhdrShadowState bhdr_shadow = {0};
static int bhdr_wrappers_ready = 0;
static int bhdr_ipc_ready = 0;

pid_t bhdr_get_init_pid(void) {
    /* No longer used for fork guard — kept for ABI compat */
    return getpid();
}

/* Phase 1: resolve real GL function pointers + init shadow state.
 * Called from every wrapper function. Safe to call from any process. */
void bhdr_init(void) {
    if (bhdr_wrappers_ready) return;
    bhdr_wrappers_ready = 1;
    bhdr_wrappers_init();
    bhdr_shadow_init(&bhdr_shadow);
    /* Phase 1 of `gpa trace` native side: opt-in via BHDR_TRACE_NATIVE=1.
     * No-op otherwise. */
    bhdr_native_trace_init();
}

/* Phase 2: connect IPC to engine. Only called from glXSwapBuffers,
 * which is only hit by the process that actually does rendering.
 * This naturally avoids the fork problem — child processes that
 * never render never connect to the engine. */
void bhdr_ensure_ipc(void) {
    if (bhdr_ipc_ready) return;
    bhdr_ipc_ready = 1;
    bhdr_ipc_connect();
    fprintf(stderr, "[Beholder] Shim active (pid=%d)\n", getpid());
}

/* NO constructor — init is lazy on first GL call.
 * This avoids the fork issue where X11/DRI child processes
 * would initialize and connect to the engine unnecessarily. */
