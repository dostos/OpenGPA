#ifndef BHDR_PC_TO_DIE_H
#define BHDR_PC_TO_DIE_H

/* PC → (module, subprogram) index for Phase 2's stack-local scanner.
 *
 * Built once at shim init by walking every non-system module's DWARF
 * subprograms. Queried per-frame on gated GL calls. The lookup is a
 * binary search over a flat, PC-sorted array. */

#include <stddef.h>
#include <stdint.h>

#include "dwarf_parser.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uintptr_t low_pc;    /* inclusive, load-bias adjusted */
    uintptr_t high_pc;   /* exclusive, load-bias adjusted */
    const BhdrDwarfSubprogram* sub; /* borrowed; owner is the Subprograms table */
} BhdrPcRange;

typedef struct {
    BhdrPcRange*  ranges;   /* sorted by low_pc asc */
    size_t       count;
    size_t       cap;
} BhdrPcIndex;

void bhdr_pc_index_init(BhdrPcIndex* idx);

/* Add every subprogram from `subs` to the index. Safe to call multiple
 * times for multiple modules. Sort before the first query. */
void bhdr_pc_index_add_module(BhdrPcIndex* idx, const BhdrDwarfSubprograms* subs);

/* Sort ranges in ascending low_pc order. Must be called after all
 * modules are added and before the first bhdr_pc_index_lookup(). */
void bhdr_pc_index_sort(BhdrPcIndex* idx);

/* Binary-search for the subprogram covering `pc`. Returns NULL if none. */
const BhdrDwarfSubprogram* bhdr_pc_index_lookup(const BhdrPcIndex* idx,
                                              uintptr_t pc);

void bhdr_pc_index_free(BhdrPcIndex* idx);

#ifdef __cplusplus
}
#endif

#endif /* BHDR_PC_TO_DIE_H */
