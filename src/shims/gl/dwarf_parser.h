#ifndef BHDR_DWARF_PARSER_H
#define BHDR_DWARF_PARSER_H

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
    BHDR_DWARF_OK = 0,
    BHDR_DWARF_ERR_OPEN = -1,          /* couldn't open/stat/mmap the ELF file */
    BHDR_DWARF_ERR_NOT_ELF = -2,       /* not a 64-bit ELF we understand */
    BHDR_DWARF_ERR_NO_DEBUG_INFO = -3, /* no .debug_info section (stripped?) */
    BHDR_DWARF_UNSUPPORTED_VERSION = -4, /* DWARF v5 (or other unsupported) */
    BHDR_DWARF_ERR_MALFORMED = -5,     /* truncated / unreadable DIE tree */
} BhdrDwarfError;

/* A single extracted global/static.
 * `name` points into a dynamically-allocated pool owned by the BhdrDwarfGlobals
 * container; do not free individually. `address` is the load-adjusted
 * absolute address in the process's address space (caller must supply
 * `load_bias` to `bhdr_dwarf_parse_module`). */
typedef struct {
    const char* name;
    uintptr_t   address;
    uint64_t    byte_size;    /* 0 if unknown */
    uint32_t    type_encoding;/* DW_ATE_* enum; 0 if not a primitive */
} BhdrDwarfGlobal;

typedef struct {
    BhdrDwarfGlobal* items;
    size_t          count;
    size_t          cap;
    /* Internal: backing string pool so `name` pointers stay valid. */
    char*           strpool;
    size_t          strpool_len;
    size_t          strpool_cap;
} BhdrDwarfGlobals;

/* DWARF base-type encodings we care about (subset of DW_ATE_*). */
#define BHDR_DW_ATE_ADDRESS        0x01
#define BHDR_DW_ATE_BOOLEAN        0x02
#define BHDR_DW_ATE_FLOAT          0x04
#define BHDR_DW_ATE_SIGNED         0x05
#define BHDR_DW_ATE_SIGNED_CHAR    0x06
#define BHDR_DW_ATE_UNSIGNED       0x07
#define BHDR_DW_ATE_UNSIGNED_CHAR  0x08
#define BHDR_DW_ATE_UTF            0x10

/* Parse all globals/statics from the ELF file at `path`, offsetting each
 * absolute address by `load_bias` (typically dlpi_addr from dl_iterate_phdr).
 * On success, fills `*out` (caller must free with bhdr_dwarf_globals_free).
 * On failure returns a negative BhdrDwarfError. */
int bhdr_dwarf_parse_module(const char* path,
                           uintptr_t load_bias,
                           BhdrDwarfGlobals* out);

/* Release storage owned by a BhdrDwarfGlobals. Safe on a zero-inited struct. */
void bhdr_dwarf_globals_free(BhdrDwarfGlobals* g);

/* Human-readable error string for a BhdrDwarfError (or "unknown" for other). */
const char* bhdr_dwarf_strerror(int err);

/* ----------------------------------------------------------------------
 * Phase 2: subprogram + local-variable index.
 *
 * Separate from the globals scan. A local variable carries a raw DWARF
 * location expression (bytes) that Phase 2's interpreter evaluates against
 * register state at scan time. We do NOT resolve addresses here.
 * ---------------------------------------------------------------------- */

typedef struct {
    const char*    name;           /* points into BhdrDwarfSubprograms strpool */
    const uint8_t* location_expr;  /* points into mmap'd DWARF */
    size_t         location_len;
    uint64_t       byte_size;      /* 0 if unknown */
    uint32_t       type_encoding;  /* DW_ATE_*; 0 if non-primitive */
} BhdrDwarfLocal;

typedef struct {
    const char*       name;         /* demangled? no — linkage_name or name */
    uintptr_t         low_pc;       /* already load-bias adjusted */
    uintptr_t         high_pc;      /* absolute; exclusive */
    BhdrDwarfLocal*    locals;
    size_t            local_count;
    size_t            local_cap;
} BhdrDwarfSubprogram;

typedef struct {
    BhdrDwarfSubprogram* items;
    size_t               count;
    size_t               cap;
    /* Backing mmap for location_expr pointers. Stays mapped for the
     * lifetime of the table. */
    void*                map;
    size_t               map_size;
    int                  fd;
    /* String pool for subprogram / local names. */
    char*                strpool;
    size_t               strpool_len;
    size_t               strpool_cap;
} BhdrDwarfSubprograms;

/* Parse subprograms + their local-variable DIEs from the module at `path`.
 * The mmap used for parsing is retained inside `*out` so the location-
 * expression pointers remain valid until bhdr_dwarf_subprograms_free().
 *
 * `load_bias` is added to every recorded low_pc/high_pc. */
int bhdr_dwarf_parse_subprograms(const char* path,
                                uintptr_t load_bias,
                                BhdrDwarfSubprograms* out);

void bhdr_dwarf_subprograms_free(BhdrDwarfSubprograms* s);

#ifdef __cplusplus
}
#endif

#endif /* BHDR_DWARF_PARSER_H */
