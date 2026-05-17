# `gpa trace` — Usage

Reverse-look up a captured graphics value (uniform, texture id, or
literal) to the **app-level JS field** that currently holds it. Narrows
"which of 300K lines produced this value" to "these three fields."

For design context see
[`docs/superpowers/specs/2026-04-20-gpa-trace-design.md`](superpowers/specs/2026-04-20-gpa-trace-design.md).

## Enabling capture in the browser

The reflection scanner lives in
`src/shims/webgl/extension/gpa-trace.js`. It ships as an opt-in module
— no work is done unless the page enables it.

### Option A — auto-enable via `localStorage`

```js
localStorage.BHDR_TRACE_MODE = 'gated';       // or 'lazy' | 'eager'
localStorage.BHDR_TRACE_ENDPOINT = 'http://127.0.0.1:18080/api/v1';
localStorage.BHDR_TRACE_TOKEN = '<bearer>';   // engine auth token
// Reload. The module auto-calls gpa.trace.enable() on load.
```

### Option B — manual enable from devtools

```js
window.gpa.trace.enable();
window.gpa.trace.addRoot(window.map, 'map');   // expose extra roots
```

Default roots: `THREE`, `mapboxgl`, `PIXI`, `scene`, `map`, `renderer`,
`camera`, `app`. Any `window.<name>` that is a live object is picked up
automatically. For state hidden in closures, use `addRoot()` manually.

## CLI

```
# Trace a uniform to the field that set it.
$ gpa trace uniform uZoom --frame 2 --dc 3

uZoom (frame 2, dc 3) = 16.58
  candidates:
    [high  ] sourceCache.maxzoom             (1 hop)
    [high  ] map._transform._maxZoom         (2 hops)
    [medium] style._sources.terrain.maxzoom  (3 hops)

# Trace a texture id to the JS object field(s) holding it.
$ gpa trace texture 7 --frame 2 --dc 3

# Frame-wide reverse-lookup on a literal value.
$ gpa trace value 16.58 --frame 2

# Structured output for programmatic consumers.
$ gpa trace uniform uZoom --frame 2 --dc 3 --json
```

Exit codes mirror the rest of the CLI: `0` success, `1` transport
error, `2` bad args / no session, `4` no frames captured yet.

## MCP

A single tool `bhdr_trace_value(frame_id, field?, value?, dc_id?)` wraps
the three subcommands. Pass either `field` (uniform name) *or* `value`
(literal). Returns the same JSON as `--json`.

## Extending the default root list

The JS-side default roots are a tuple inside `gpa-trace.js`. Prefer
`addRoot()` over editing the defaults — the allowlist is intentionally
short to avoid scanning irrelevant globals. Ranking hints (the
Phase-3 "prefix → confidence bump" rules) live in
`src/python/bhdr/api/trace_ranking.py::FRAMEWORK_HINT_PATTERNS`. Any
additions must carry evidence that the prefix reliably holds
app-visible state.

## Interpreting the candidates block

- `[high]` — strong match. Short hop count, rare value, or a framework
  hint pattern (e.g. `map._transform.*`).
- `[medium]` — plausible; worth reading the field.
- `[low]` — likely noise. The value is common (integers 0/1, empty
  string) or lives in a deeply-buried private cache.

Empty candidates with a `hint` line means the value was not present in
any scanned object. Typical cause: the value is computed inline at the
call site (e.g. `gl.uniform1f(loc, someExpr())`) and never stored.
