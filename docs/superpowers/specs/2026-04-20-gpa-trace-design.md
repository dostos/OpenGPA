# `gpa trace` — Reverse-Lookup Value Attribution

**Date:** 2026-04-20
**Status:** Phases 1–3 shipped; Phase 4 (Round-9 measurement) pending
**Usage:** see [`docs/gpa-trace-usage.md`](../../gpa-trace-usage.md)
**Motivation:** Rounds 5–8 showed OpenGPA loses on "source-logical" bugs (r27 fractional `maxZoom`, r28 16-bit index overflow, r29 mapbox symbol-layer collision). These bugs have consistent GL state; the error is in app-level logic that *produced* the value. Call-stack attribution alone is insufficient — it points to the call site, but the value itself is typically a N-hop transformation of deeper framework fields. In a 300K-line codebase the agent still has to trace.

`gpa trace` inverts the problem: **given a captured value, list app-level fields that currently equal it.** Narrows the search radius from "entire codebase" to "these 3 fields." The agent spends one query instead of twenty greps.

## Goals

- **Narrow the search radius.** From "300K lines" to "3 fields" per suspect value.
- **One-shot query.** Matches the CLI's `gpa report` token-efficiency philosophy.
- **JS-first.** Three.js, mapbox-gl-js, PIXI are the mined scenarios; browser reflection is tractable.
- **Opt-in.** Off by default. Privacy + perf implications require explicit enablement.
- **Complement, not replace, call-stack attribution.** Both ship, both cite the same captured state.

## Non-goals

- Native (C / C++ / Rust) runtime reflection. Deferred to V2 (requires DWARF + stack introspection).
- Static data-flow analysis. Different product; complements but doesn't overlap.
- Shader-level symbolic execution.
- Deterministic replay.

## Architecture

```
+---------------+        pre-call hook         +-----------------+
| target page   | ---------------------------> | gpa webgl shim  |
| (JS app)      |                              |                 |
| window.THREE  |   reflection scan            |  - scan globals |
| scene, cam    | <--------------------------- |  - hash values  |
| map, ...      |                              |  - POST sidecar |
+---------------+                              +--------+--------+
                                                        |
                                               per-frame sidecar
                                                        |
                                                        v
                                               +-----------------+
                                               |  gpa engine     |
                                               |  /value-index   |
                                               |  keyed by hash  |
                                               +-----------------+

Query side:
  $ gpa trace uniform uZoom --frame 2 --dc 3
         |
         v (REST: /frames/2/drawcalls/3/value-origin?field=uZoom)
  engine returns:
    { value: 16.58, call_site: "terrain.ts:847",
      matches: ["map._transform._maxZoom", "sourceCache.maxzoom"] }
```

## Data model

### Capture-time snapshot

Per draw call (or periodically — see § Open questions):

```json
{
  "frame_id": 2,
  "dc_id": 3,
  "sources": {
    "roots": ["window.THREE", "scene", "map", "renderer"],
    "value_index": {
      "<hash(16.58)>": [
        {"path": "map._transform._maxZoom", "type": "number"},
        {"path": "sourceCache.maxzoom", "type": "number"}
      ],
      "<hash(3)>": [
        {"path": "scene.children.length", "type": "number"}
      ]
    }
  }
}
```

- Keys are hashes of values (exact float bits for numbers; xxhash of string for strings; hash of canonical JSON for arrays).
- Values are lists of paths. Most values won't collide; dedupe trivial values (`0`, `1`, `""`, `false`, `true`) by omitting them entirely — too common to be useful.

### Query response

`GET /frames/{id}/drawcalls/{dc}/value-origin?field={uniform_name|texture|...}` →

```json
{
  "frame_id": 2,
  "dc_id": 3,
  "field": "uZoom",
  "value": 16.58,
  "call_site": "terrain.ts:847 GLRenderer.drawTile",
  "candidates": [
    {"path": "map._transform._maxZoom", "distance_hops": 2, "confidence": "high"},
    {"path": "sourceCache.maxzoom", "distance_hops": 3, "confidence": "high"},
    {"path": "style._sources.terrain.maxzoom", "distance_hops": 5, "confidence": "medium"}
  ]
}
```

- `distance_hops` counts from the declared roots (proxy for "closeness to the calling code")
- `confidence` derived from: path hop count + value rarity (near-unique floats → high; common ints → low)
- If no matches: `candidates: []` with `hint: "no app-level field currently holds this value — value may be computed inline at the call site"`

## Capture-time behavior

### What to scan

1. **Registered roots.** Framework-specific defaults plus a user-extensible list:
   - Three.js: `window.THREE`, discovered `scene`, `renderer`, `camera` via heuristic walk
   - mapbox-gl-js: `window.mapboxgl`, `map`
   - PIXI: `window.PIXI`, `app`
   - User custom: `BHDR_TRACE_ROOTS=map,scene,myApp` env var or `gpa.trace.addRoot("myGlobal")` SDK call

2. **Traversal:** BFS from each root.
   - Depth cap: 4 hops
   - Visited-set by object identity (cycle break)
   - Skip: DOM nodes, functions, private fields (starts with `_` beyond 1st level), huge typed arrays (> 1024 elements)
   - Include: primitives (number, string, bool), flat arrays of ≤16 primitives (matrices, color arrays)

3. **When to scan:** full scan on `glDrawArrays` / `glDrawElements` is too expensive for real-time. Three strategies:
   - **lazy**: scan once per frame (`glXSwapBuffers` / `gl.flush()` boundary). Fast; may miss mid-frame state changes.
   - **gated**: scan only on `glUniform*` and `glBindTexture` (the two state-changing calls that most often need tracing). Balanced.
   - **eager**: scan before every draw call. Slowest; most accurate.

   Default: **gated**. Flag: `BHDR_TRACE_MODE=lazy|gated|eager`.

### Value matching

- **Numbers**: exact `Number.prototype.toFixed(15)` match after normalizing -0 → 0, NaN → "NaN" sentinel. Float tolerance NOT applied at capture time (keeps hash stable); tolerance applied at query time via a fallback pass if exact match empty.
- **Strings**: exact.
- **Arrays (matrices, vec3)**: canonicalize as JSON, hash. No element-wise tolerance in V1.
- **Booleans**: exact.

### Cost control

Per draw call overhead targets:
- < 2 ms walk time on a 10K-object scene
- < 50 KB serialized state per drawcall (ring buffer caps total at 5 MB/frame)

If either budget is exceeded, truncate path list with `"truncated: true"` marker and reduce depth cap by 1 for the next call.

## Query surface

### CLI

```
gpa trace uniform <name> [--frame N] [--dc N]
    # Returns: value, call_site, candidate fields

gpa trace texture <tex_id> [--frame N]
    # Returns: texture dimensions + candidate JS object paths holding this tex_id

gpa trace value <literal> [--frame N]
    # Reverse: find all fields currently equal to this value
    # e.g. `gpa trace value 16.58 --frame 2` → paths holding 16.58
```

Output format: plain-text table (agent-friendly), `--json` for structured.

### REST

```
GET /frames/{id}/drawcalls/{dc}/value-origin?field=<name>
GET /frames/{id}/drawcalls/{dc}/value-origin?value=<literal>
GET /frames/{id}/trace/value?query=<literal>   # frame-wide, any drawcall
```

### MCP

One new tool `bhdr_trace_value(frame_id, field?, value?, dc_id?)` that wraps the CLI. Description:

> "Reverse-lookup app-level fields whose value matches a captured uniform / texture ID / literal. Answers 'where in the framework state did this value come from?' Useful when a uniform looks wrong and you need to find the deeper field that set it."

## Implementation status: shipped

### Phase 1 — WebGL capture (shipped)

- `src/shims/webgl/extension/gpa-trace.js` — BFS scanner with depth/size
  caps, gated/lazy/eager modes, SDK `gpa.trace.addRoot()`, POSTs to
  `/frames/{id}/drawcalls/{dc}/sources`.
- `src/python/bhdr/api/trace_store.py` — in-memory LRU-per-frame store
  (`put` / `get` / `find_value` / `get_frame`).
- `src/python/bhdr/api/routes_trace.py` — POST/GET raw sources endpoint.
- 32 unit tests.

### Phase 2 — query surface (shipped)

- `src/python/bhdr/cli/commands/trace.py` — `gpa trace uniform|texture|value`
  with `--frame / --dc / --json`. Plain-text renderer matches the
  "Query response" section's shape.
- REST endpoints added to `routes_trace.py`:
  - `GET /frames/{id}/drawcalls/{dc}/trace/uniform/{name}`
  - `GET /frames/{id}/drawcalls/{dc}/trace/texture/{tex_id}`
  - `GET /frames/{id}/drawcalls/{dc}/trace/value?query=<literal>`
  - `GET /frames/{id}/trace/value?query=<literal>` (frame-wide)
  Value matching is done by parsing the stored hash-key back into a
  number (IEEE 754 round-trip, float32-tolerant) rather than by
  re-hashing the query literal — re-implementing JS's
  `Number.prototype.toString(36)` exactly is fiddly and unnecessary.
- MCP tool `bhdr_trace_value(frame_id, field?, value?, dc_id?)` in
  `src/python/bhdr/mcp/server.py`.

### Phase 3 — confidence + ranking (shipped)

- `src/python/bhdr/api/trace_ranking.py` — `rank_candidates()` sorts by
  `(tier desc, hops asc, path length asc)`. Inputs:
  - Hop distance: `.`-separated depth from the declared root (bracket
    indexing `foo[0]` counts as a hop).
  - Value rarity: `rank_candidates(..., corpus={"__count__": N})`;
    `N == 1` upgrades one tier, `N > 5` downgrades one tier.
  - Framework hints: a short list of regex prefixes
    (`FRAMEWORK_HINT_PATTERNS`) — three.js `uniforms.*.value`, mapbox-gl
    `map._transform` / `map.style`, PIXI `app.stage`, and the generic
    `scene` / `camera` roots. Match → +1 tier.
- `build_corpus_for_value()` walks the last 10 frames to build the
  rarity count.
- Query routes invoke ranking automatically; CLI JSON output exposes
  both `confidence` (ranked) and `raw_confidence` (from the scanner).

### Phase 4 — measurement (Round 9, pending)

- Re-run R7's 20 scenarios + the 10 state-collision scenarios with
  tracing enabled.
- Target: r27 / r28 / r29 go from 0/4 → ≥ 2/4 correct.
- Measure: query count delta (how often agents actually use
  `gpa trace` vs other tools).

## Divergences from the original design

- **REST path layout**. The original design named the query endpoint
  `/frames/{id}/drawcalls/{dc}/value-origin?field=<name>`. Shipped shape
  is resource-oriented — `/trace/uniform/{name}`, `/trace/texture/{id}`,
  `/trace/value?query=<lit>` — which matches the CLI subcommand naming
  and avoids overloading a single endpoint with three distinct
  semantics.
- **Query-side hashing** replaced with **query-side reverse-parsing** of
  stored hash keys. The JS scanner uses `Number.prototype.toString(36)`
  which has "shortest round-trip" float formatting that is
  painful to re-implement exactly in Python. Parsing the base-36 digits
  back into a Python `float` and comparing with `math.isclose(rel=1e-5)`
  handles both the float32-vs-float64 precision gap (captured uniforms
  are float32) and the JS→Python numeric round-trip in one pass.
- **Vector-uniform lookup** compares the whole array first (via
  canonical JSON → djb2 hash). Per-component fallback was considered
  and dropped for V1 — scenario data so far has not needed it.

## Open questions

1. **Scan cadence default.** Gated is my pick. But three.js sometimes does 1000s of uniform calls per frame; even gated may add meaningful overhead. Consider: adaptive — start gated, drop to lazy if overhead exceeds budget.
2. **Reachability for closure-captured state.** Three.js hides state in closures often invisible from globals. The SDK `gpa.trace.addRoot(closure)` lets users expose these manually. Without it, coverage is partial.
3. **How to handle objects that shouldn't be dumped** (react fibers, DOM trees). Use a size-and-type filter. But a user with a custom scene graph might hit it. Add an `isAppField(path)` user hook.
4. **Collision on common values.** Many fields are `0`, `1`, `null`. Dropping trivial values from the index loses signal when the bug IS "zero where non-zero expected." Middle ground: always include `0` and `1` but tag them `low-confidence`.
5. **Privacy — what if an app has credentials in globals?** Off-by-default + exclude paths matching common secret patterns (`token`, `apikey`, `password`).
6. **Native / Vulkan support.** V2. DWARF-based reflection is viable but much heavier; not scoped here.

## Non-feature: "LLM writes the grep for you"

Early versions of this doc imagined a route where the agent describes the value it's tracing and an LLM writes a grep-over-snapshot query. Dropped: this is exactly what the agent was doing in R5 that blew cache_read to +241K. The point of `gpa trace` is that the answer is pre-computed at capture time — no grepping needed.

## Success criteria — awaiting Round 9 measurement

After Phase 4 (Round 9):

- `gpa trace` invocation count across R9 with_bhdr runs ≥ 1.0/run avg
- At least 2 previously-unsolvable source-logical scenarios (r27/r28/r29/similar) correctly diagnosed with `gpa trace` in the tool trace
- No regression on state-collision scenarios (R8 Sonnet Δ of −$0.088/pair holds)
- Capture-time overhead ≤ 5% on a three.js demo
