#ifndef GPA_DWARF_PARSER_H
#define GPA_DWARF_PARSER_H

/* Minimal hand-rolled DWARF parser for OpenGPA native trace (Phase 1).
 *
 * Goal: extract {name, address, byte_size, type_encoding} for every global
 * / file-scoped-static variable in a loaded ELF module. Enough to let the
 * shim reflect user globals at glUniform* / glBindTexture time.
 *
 * Scope: DWARF v3 and v4 only. DWARF v5 is rejected with a clear error.
 * We only care about `DW_TAG_variable` DIEs that carry a
 * `DW_AT_location = DW_OP_addr <addr>` (true globals/statics). Stack locals
 * live in Phase 2.
 *
 * No libdw / libdwfl dependency. ~500 lines of C. */

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Error codes returned by the parse entry points. */
typedef enum {
    GPA_DWARF_OK = 0,
    GPA_DWARF_ERR_OPEN = -1,          /* couldn't open/stat/mmap the ELF file */
    GPA_DWARF_ERR_NOT_ELF = -2,       /* not a 64-bit ELF we understand */
    GPA_DWARF_ERR_NO_DEBUG_INFO = -3, /* no .debug_info section (stripped?) */
    GPA_DWARF_UNSUPPORTED_VERSION = -4, /* DWARF v5 (or other unsupported) */
    GPA_DWARF_ERR_MALFORMED = -5,     /* truncated / unreadable DIE tree */
} GpaDwarfError;

/* A single extracted global/static.
 * `name` points into a dynamically-allocated pool owned by the GpaDwarfGlobals
 * container; do not free individually. `address` is the load-adjusted
 * absolute address in the process's address space (caller must supply
 * `load_bias` to `gpa_dwarf_parse_module`). */
typedef struct {
    const char* name;
    uintptr_t   address;
    uint64_t    byte_size;    /* 0 if unknown */
    uint32_t    type_encoding;/* DW_ATE_* enum; 0 if not a primitive */
} GpaDwarfGlobal;

typedef struct {
    GpaDwarfGlobal* items;
    size_t          count;
    size_t          cap;
    /* Internal: backing string pool so `name` pointers stay valid. */
    char*           strpool;
    size_t          strpool_len;
    size_t          strpool_cap;
} GpaDwarfGlobals;

/* DWARF base-type encodings we care about (subset of DW_ATE_*). */
#define GPA_DW_ATE_ADDRESS        0x01
#define GPA_DW_ATE_BOOLEAN        0x02
#define GPA_DW_ATE_FLOAT          0x04
#define GPA_DW_ATE_SIGNED         0x05
#define GPA_DW_ATE_SIGNED_CHAR    0x06
#define GPA_DW_ATE_UNSIGNED       0x07
#define GPA_DW_ATE_UNSIGNED_CHAR  0x08
#define GPA_DW_ATE_UTF            0x10

/* Parse all globals/statics from the ELF file at `path`, offsetting each
 * absolute address by `load_bias` (typically dlpi_addr from dl_iterate_phdr).
 * On success, fills `*out` (caller must free with gpa_dwarf_globals_free).
 * On failure returns a negative GpaDwarfError. */
int gpa_dwarf_parse_module(const char* path,
                           uintptr_t load_bias,
                           GpaDwarfGlobals* out);

/* Release storage owned by a GpaDwarfGlobals. Safe on a zero-inited struct. */
void gpa_dwarf_globals_free(GpaDwarfGlobals* g);

/* Human-readable error string for a GpaDwarfError (or "unknown" for other). */
const char* gpa_dwarf_strerror(int err);

#ifdef __cplusplus
}
#endif

#endif /* GPA_DWARF_PARSER_H */
