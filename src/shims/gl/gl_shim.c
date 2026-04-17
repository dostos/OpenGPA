#define _GNU_SOURCE
#include <stdio.h>
#include <unistd.h>
#include "gl_wrappers.h"
#include "shadow_state.h"
#include "ipc_client.h"

GlaRealGlFuncs gla_real_gl = {0};
GlaShadowState gla_shadow = {0};
static int gla_initialized = 0;
static pid_t gla_init_pid = 0;

pid_t gla_get_init_pid(void) {
    return gla_init_pid;
}

void gla_init(void) {
    if (gla_initialized) return;
    gla_initialized = 1;

    gla_init_pid = getpid();
    gla_wrappers_init();
    gla_shadow_init(&gla_shadow);
    gla_ipc_connect();   /* connect to engine (no-op if env vars not set) */

    fprintf(stderr, "[GLA] Shim initialized (pid=%d)\n", getpid());
}

__attribute__((constructor))
static void gla_preload_constructor(void) {
    gla_init();
}
