#define _GNU_SOURCE
#include <stdio.h>
#include <unistd.h>
#include "gl_wrappers.h"
#include "shadow_state.h"
#include "ipc_client.h"
#include "native_trace.h"

GpaRealGlFuncs gpa_real_gl = {0};
GpaShadowState gpa_shadow = {0};
static int gpa_wrappers_ready = 0;
static int gpa_ipc_ready = 0;

pid_t gpa_get_init_pid(void) {
    /* No longer used for fork guard — kept for ABI compat */
    return getpid();
}

/* Phase 1: resolve real GL function pointers + init shadow state.
 * Called from every wrapper function. Safe to call from any process. */
void gpa_init(void) {
    if (gpa_wrappers_ready) return;
    gpa_wrappers_ready = 1;
    gpa_wrappers_init();
    gpa_shadow_init(&gpa_shadow);
    /* Phase 1 of `gpa trace` native side: opt-in via GPA_TRACE_NATIVE=1.
     * No-op otherwise. */
    gpa_native_trace_init();
}

/* Phase 2: connect IPC to engine. Only called from glXSwapBuffers,
 * which is only hit by the process that actually does rendering.
 * This naturally avoids the fork problem — child processes that
 * never render never connect to the engine. */
void gpa_ensure_ipc(void) {
    if (gpa_ipc_ready) return;
    gpa_ipc_ready = 1;
    gpa_ipc_connect();
    fprintf(stderr, "[OpenGPA] Shim active (pid=%d)\n", getpid());
}

/* NO constructor — init is lazy on first GL call.
 * This avoids the fork issue where X11/DRI child processes
 * would initialize and connect to the engine unnecessarily. */
