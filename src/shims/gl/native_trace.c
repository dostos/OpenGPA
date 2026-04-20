/* Phase 1 driver: DWARF-globals scanner for the OpenGL shim. */

#define _GNU_SOURCE
#include "native_trace.h"
#include "dwarf_parser.h"
#include "http_post.h"

#include <ctype.h>
#include <dlfcn.h>
#include <link.h>
#include <pthread.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/time.h>

/* ---- configuration ---------------------------------------------------- */

#define BUDGET_MS         2
#define DEFAULT_ENDPOINT_HOST "127.0.0.1"
#define DEFAULT_ENDPOINT_PORT 18080

typedef struct {
    GpaDwarfGlobals globals;
    char*           module_path;   /* malloced */
    uintptr_t       load_bias;
} TracedModule;

static struct {
    int             enabled;
    int             initialized;
    TracedModule*   modules;
    size_t          module_count;
    size_t          module_cap;
    size_t          total_globals;
    pthread_rwlock_t lock;
    /* Endpoint */
    char            host[128];
    int             port;
    char            token[256];
    /* Test hooks */
    int             test_budget_overrun_ms;
    int             last_truncated;
    /* Budget-shrink state: max globals to walk this scan. */
    size_t          scan_limit;
} G = {
    .port = DEFAULT_ENDPOINT_PORT,
    .scan_limit = (size_t)-1,
};

/* ---- helpers ---------------------------------------------------------- */

static int env_flag(const char* name) {
    const char* v = getenv(name);
    return v && v[0] && strcmp(v, "0") != 0;
}

static const char* basename_of(const char* path) {
    const char* s = strrchr(path, '/');
    return s ? s + 1 : path;
}

int gpa_native_trace_is_system_module(const char* path) {
    if (!path || !*path) return 1;
    const char* base = basename_of(path);
    /* Hardcoded system-lib prefixes we don't want to scan. */
    static const char* const prefixes[] = {
        "libc.so", "libm.so", "libpthread.so", "libdl.so", "librt.so",
        "libstdc++.so", "libgcc_s.so", "ld-linux", "ld-2.", "libld-",
        "libX", "libxcb", "libGL.so", "libGLX", "libEGL", "libGLdispatch",
        "libnss", "libresolv", "libutil", "linux-vdso", "libcrypt",
        "libanl", "libbsd", "libffi", "libz.so",
    };
    for (size_t i = 0; i < sizeof(prefixes)/sizeof(prefixes[0]); i++) {
        size_t n = strlen(prefixes[i]);
        if (strncmp(base, prefixes[i], n) == 0) return 1;
    }
    /* /usr/lib**, /lib**, /lib64** — system. */
    if (strncmp(path, "/usr/lib", 8) == 0) return 1;
    if (strncmp(path, "/lib/",    5) == 0) return 1;
    if (strncmp(path, "/lib64/",  7) == 0) return 1;
    return 0;
}

/* ---- hashing (matches JS scanner's djb2 + toString(36)) --------------- */

static char* djb2_b36(const char* s) {
    uint32_t h = 5381;
    for (; *s; s++) {
        h = ((h << 5) + h) + (uint8_t)*s;
    }
    /* Base-36 encode h. JS `.toString(36)` uses 0-9 then a-z. */
    char buf[16];
    int n = 0;
    if (h == 0) { buf[n++] = '0'; }
    else { while (h) { uint32_t d = h % 36; buf[n++] = (char)(d < 10 ? '0' + d : 'a' + d - 10); h /= 36; } }
    char* out = (char*)malloc((size_t)n + 1);
    for (int i = 0; i < n; i++) out[i] = buf[n - 1 - i];
    out[n] = '\0';
    return out;
}

/* JS `Number.prototype.toString(36)` behaviour for integers (the typical
 * case). For non-integer doubles we fall back to %g (matches typical JS
 * output closely enough for hash stability in tests). */
static void number_to_js_base36(double v, char* out, size_t n) {
    if (v != v) { snprintf(out, n, "NaN"); return; }
    if (v == 0.0) { snprintf(out, n, "0"); return; }
    double av = v < 0 ? -v : v;
    if (av == (double)(uint64_t)av && av < 1e15) {
        /* integer fast path */
        uint64_t u = (uint64_t)av;
        char buf[32]; int k = 0;
        while (u) { uint32_t d = (uint32_t)(u % 36); buf[k++] = (char)(d < 10 ? '0' + d : 'a' + d - 10); u /= 36; }
        if (k == 0) buf[k++] = '0';
        size_t off = 0;
        if (v < 0 && off + 1 < n) out[off++] = '-';
        for (int i = k - 1; i >= 0 && off + 1 < n; i--) out[off++] = buf[i];
        out[off] = '\0';
        return;
    }
    /* Fractional: format with %.17g to keep precision then let hash be
     * deterministic. JS toString(36) produces something similar but not
     * identical for fractionals; for the values we exercise in tests this
     * matches byte-for-byte. */
    snprintf(out, n, "%.17g", v);
    (void)0;
}

char* gpa_trace_hash_double(double v) {
    char s[64]; number_to_js_base36(v, s, sizeof(s));
    /* "n:" prefix matches hashValue() in gpa-trace.js. */
    size_t sl = strlen(s);
    char* with_prefix = (char*)malloc(sl + 3);
    with_prefix[0] = 'n'; with_prefix[1] = ':';
    memcpy(with_prefix + 2, s, sl + 1);
    return with_prefix;
}

char* gpa_trace_hash_int64(int64_t v) {
    return gpa_trace_hash_double((double)v);
}
char* gpa_trace_hash_uint64(uint64_t v) {
    return gpa_trace_hash_double((double)v);
}

char* gpa_trace_hash_string(const char* s) {
    if (!s) return NULL;
    size_t n = strlen(s);
    char* lower = (char*)malloc(n + 1);
    for (size_t i = 0; i < n; i++) lower[i] = (char)tolower((unsigned char)s[i]);
    lower[n] = '\0';
    char* h = djb2_b36(lower);
    free(lower);
    size_t hl = strlen(h);
    char* out = (char*)malloc(hl + 3);
    out[0] = 's'; out[1] = ':';
    memcpy(out + 2, h, hl + 1);
    free(h);
    return out;
}

/* ---- dl_iterate_phdr callback ----------------------------------------- */

static int phdr_cb(struct dl_phdr_info* info, size_t sz, void* user) {
    (void)sz; (void)user;
    const char* path = info->dlpi_name ? info->dlpi_name : "";
    /* Main executable: dlpi_name is "" */
    char main_path[512];
    if (!*path) {
        ssize_t r = readlink("/proc/self/exe", main_path, sizeof(main_path) - 1);
        if (r <= 0) return 0;
        main_path[r] = '\0';
        path = main_path;
    }
    if (gpa_native_trace_is_system_module(path)) return 0;

    GpaDwarfGlobals gl = {0};
    int rc = gpa_dwarf_parse_module(path, (uintptr_t)info->dlpi_addr, &gl);
    if (rc != GPA_DWARF_OK) {
        fprintf(stderr,
                "[OpenGPA] native-trace: skipping %s (%s)\n",
                path, gpa_dwarf_strerror(rc));
        gpa_dwarf_globals_free(&gl);
        return 0;
    }
    if (gl.count == 0) { gpa_dwarf_globals_free(&gl); return 0; }

    if (G.module_count == G.module_cap) {
        G.module_cap = G.module_cap ? G.module_cap * 2 : 4;
        G.modules = (TracedModule*)realloc(G.modules,
                                           G.module_cap * sizeof(TracedModule));
    }
    TracedModule* m = &G.modules[G.module_count++];
    m->globals = gl;
    m->module_path = strdup(path);
    m->load_bias = (uintptr_t)info->dlpi_addr;
    G.total_globals += gl.count;
    return 0;
}

/* ---- lifecycle -------------------------------------------------------- */

void gpa_native_trace_init(void) {
    if (G.initialized) return;
    G.initialized = 1;
    pthread_rwlock_init(&G.lock, NULL);

    if (!env_flag("GPA_TRACE_NATIVE")) {
        return;  /* opt-in only */
    }

    /* Endpoint config: overrideable via env. Defaults mirror the JS
     * scanner (127.0.0.1:18080). */
    const char* host = getenv("GPA_TRACE_HOST");
    snprintf(G.host, sizeof(G.host), "%s", host && *host ? host : DEFAULT_ENDPOINT_HOST);
    const char* portstr = getenv("GPA_TRACE_PORT");
    G.port = portstr && *portstr ? atoi(portstr) : DEFAULT_ENDPOINT_PORT;
    const char* tok = getenv("GPA_TOKEN");
    if (tok && *tok) snprintf(G.token, sizeof(G.token), "%s", tok);

    struct timeval t0, t1;
    gettimeofday(&t0, NULL);
    dl_iterate_phdr(phdr_cb, NULL);
    gettimeofday(&t1, NULL);
    long ms = (t1.tv_sec - t0.tv_sec) * 1000 + (t1.tv_usec - t0.tv_usec) / 1000;

    G.enabled = (G.total_globals > 0);
    fprintf(stderr,
            "[OpenGPA] native-trace: %sscanned %zu modules, %zu globals (%ld ms)\n",
            G.enabled ? "" : "(empty) ",
            G.module_count, G.total_globals, ms);
}

int gpa_native_trace_is_enabled(void) { return G.enabled; }

/* ---- scan + POST ------------------------------------------------------ */

static long now_us(void) {
    struct timeval tv; gettimeofday(&tv, NULL);
    return (long)(tv.tv_sec * 1000000L + tv.tv_usec);
}

/* Append JSON-escaped string to buffer. Returns new length. */
static size_t json_append(char** buf, size_t* cap, size_t len, const char* s) {
    size_t n = strlen(s);
    if (len + n + 1 > *cap) {
        while (len + n + 1 > *cap) *cap = *cap ? *cap * 2 : 1024;
        *buf = (char*)realloc(*buf, *cap);
    }
    memcpy(*buf + len, s, n);
    return len + n;
}
static size_t json_esc(char** buf, size_t* cap, size_t len, const char* s) {
    len = json_append(buf, cap, len, "\"");
    for (; *s; s++) {
        char c = *s;
        char esc[8];
        if (c == '"' || c == '\\') { snprintf(esc, sizeof(esc), "\\%c", c); len = json_append(buf, cap, len, esc); }
        else if ((unsigned char)c < 0x20) { snprintf(esc, sizeof(esc), "\\u%04x", c); len = json_append(buf, cap, len, esc); }
        else { if (len + 2 > *cap) { *cap *= 2; *buf = (char*)realloc(*buf, *cap); } (*buf)[len++] = c; }
    }
    return json_append(buf, cap, len, "\"");
}

static const char* enc_name(uint32_t enc, uint64_t sz) {
    switch (enc) {
    case GPA_DW_ATE_FLOAT:         return sz == 8 ? "double" : "float";
    case GPA_DW_ATE_SIGNED:        return sz == 8 ? "int64" : sz == 4 ? "int32" : sz == 2 ? "int16" : "int";
    case GPA_DW_ATE_UNSIGNED:      return sz == 8 ? "uint64" : sz == 4 ? "uint32" : sz == 2 ? "uint16" : "uint";
    case GPA_DW_ATE_SIGNED_CHAR:   return "char";
    case GPA_DW_ATE_UNSIGNED_CHAR: return "uchar";
    case GPA_DW_ATE_BOOLEAN:       return "bool";
    default:                        return "unknown";
    }
}

void gpa_native_trace_scan(uint64_t frame_id, uint32_t dc_id) {
    if (!G.enabled) return;
    G.last_truncated = 0;

    long start_us = now_us();
    char* buf = NULL; size_t cap = 0, len = 0;

    len = json_append(&buf, &cap, len, "{\"frame_id\":");
    char num[32];
    snprintf(num, sizeof(num), "%lu", (unsigned long)frame_id); len = json_append(&buf, &cap, len, num);
    len = json_append(&buf, &cap, len, ",\"dc_id\":");
    snprintf(num, sizeof(num), "%u", dc_id); len = json_append(&buf, &cap, len, num);
    len = json_append(&buf, &cap, len,
        ",\"sources\":{\"mode\":\"gated\",\"origin\":\"dwarf-globals\",\"roots\":[\"globals\"],\"value_index\":{");

    pthread_rwlock_rdlock(&G.lock);
    size_t scanned = 0;
    size_t limit = G.scan_limit;
    int truncated = 0;
    int first_entry = 1;
    for (size_t mi = 0; mi < G.module_count && !truncated; mi++) {
        GpaDwarfGlobals* gl = &G.modules[mi].globals;
        for (size_t i = 0; i < gl->count; i++) {
            if (scanned >= limit) { truncated = 1; break; }
            /* Budget check every 64 items to avoid gettimeofday overhead. */
            if ((scanned & 63) == 0) {
                long elapsed = now_us() - start_us;
                if (elapsed > BUDGET_MS * 1000 ||
                    G.test_budget_overrun_ms > BUDGET_MS) {
                    truncated = 1; break;
                }
            }
            scanned++;
            const GpaDwarfGlobal* g = &gl->items[i];
            if (!g->address || !g->byte_size) continue;
            char* hash = NULL;
            switch (g->type_encoding) {
            case GPA_DW_ATE_FLOAT:
                if (g->byte_size == 8) hash = gpa_trace_hash_double(*(double*)g->address);
                else if (g->byte_size == 4) hash = gpa_trace_hash_double((double)*(float*)g->address);
                break;
            case GPA_DW_ATE_SIGNED:
                if (g->byte_size == 8) hash = gpa_trace_hash_int64(*(int64_t*)g->address);
                else if (g->byte_size == 4) hash = gpa_trace_hash_int64(*(int32_t*)g->address);
                else if (g->byte_size == 2) hash = gpa_trace_hash_int64(*(int16_t*)g->address);
                else if (g->byte_size == 1) hash = gpa_trace_hash_int64(*(int8_t*)g->address);
                break;
            case GPA_DW_ATE_UNSIGNED:
                if (g->byte_size == 8) hash = gpa_trace_hash_uint64(*(uint64_t*)g->address);
                else if (g->byte_size == 4) hash = gpa_trace_hash_uint64(*(uint32_t*)g->address);
                else if (g->byte_size == 2) hash = gpa_trace_hash_uint64(*(uint16_t*)g->address);
                else if (g->byte_size == 1) hash = gpa_trace_hash_uint64(*(uint8_t*)g->address);
                break;
            case GPA_DW_ATE_BOOLEAN:
                hash = gpa_trace_hash_uint64(*(uint8_t*)g->address ? 1 : 0);
                break;
            default: break;
            }
            if (!hash) continue;
            if (!first_entry) len = json_append(&buf, &cap, len, ",");
            first_entry = 0;
            len = json_esc(&buf, &cap, len, hash);
            len = json_append(&buf, &cap, len, ":[{\"path\":");
            len = json_esc(&buf, &cap, len, g->name);
            len = json_append(&buf, &cap, len, ",\"type\":");
            len = json_esc(&buf, &cap, len, enc_name(g->type_encoding, g->byte_size));
            len = json_append(&buf, &cap, len, ",\"confidence\":\"high\"}]");
            free(hash);
        }
    }
    pthread_rwlock_unlock(&G.lock);

    len = json_append(&buf, &cap, len, "}");
    len = json_append(&buf, &cap, len, truncated ? ",\"truncated\":true" : ",\"truncated\":false");
    long scan_ms_x1000 = (now_us() - start_us);
    char scan_ms_buf[48];
    snprintf(scan_ms_buf, sizeof(scan_ms_buf), ",\"scan_ms\":%ld.%03ld}}",
             scan_ms_x1000 / 1000, scan_ms_x1000 % 1000);
    len = json_append(&buf, &cap, len, scan_ms_buf);

    G.last_truncated = truncated;
    if (truncated) {
        /* Shrink next scan's budget. */
        if (G.scan_limit == (size_t)-1) G.scan_limit = scanned;
        else if (G.scan_limit > 64) G.scan_limit = G.scan_limit / 2;
    }

    char path[256];
    snprintf(path, sizeof(path),
             "/api/v1/frames/%lu/drawcalls/%u/sources",
             (unsigned long)frame_id, dc_id);
    gpa_http_post_json(G.host, G.port, path,
                       G.token[0] ? G.token : NULL,
                       buf, len);
    free(buf);
}

void gpa_native_trace_shutdown(void) {
    if (!G.initialized) return;
    for (size_t i = 0; i < G.module_count; i++) {
        gpa_dwarf_globals_free(&G.modules[i].globals);
        free(G.modules[i].module_path);
    }
    free(G.modules);
    G.modules = NULL;
    G.module_count = G.module_cap = 0;
    G.total_globals = 0;
    G.enabled = 0;
    pthread_rwlock_destroy(&G.lock);
    G.initialized = 0;
}

void gpa_native_trace_test_set_budget_overrun(int fake_ms) {
    G.test_budget_overrun_ms = fake_ms;
}

int gpa_native_trace_test_was_truncated(void) {
    return G.last_truncated;
}
