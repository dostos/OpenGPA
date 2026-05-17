# Beholder — Project Instructions

## What This Is

Beholder — a live graphics debugger for AI agents. Intercepts GL/Vulkan calls, captures frame state, exposes via REST API + MCP tools. Named for the D&D creature with many eyes; helps code agents *see* the 3D world.

Internal namespace prefix: `bhdr`. Older artifacts may still carry the legacy `gpa` / `gla` / `OpenGPA` names — those are being phased out. Historical round logs intentionally retain their original mode literals as fact-of-record.

## Build & Test

```bash
bazel build //...                                          # build everything
bazel test //tests/unit/core/... //tests/unit/shims/...     # C++ tests
PYTHONPATH=src/python python -m pytest tests/unit/python/ -q  # Python tests
```

Python 3.11 (Bazel-managed) is required for the pybind11 module. System Python 3.10 works for pytest only.

## Architecture (Three Tiers)

- **Tier 1**: Raw GL capture via LD_PRELOAD shim. No heuristics — exposes raw facts only.
- **Tier 2**: Debug markers (glPushDebugGroup). Free if framework emits them.
- **Tier 3**: Framework metadata sidecar. Plugins POST scene graph JSON to REST API.

See `docs/framework-tiers.md` for full capability matrix.

## Key Design Principles

- **No heuristics in Tier 1.** Never guess which uniform is "the view matrix." Expose raw data, let the querying agent interpret.
- **FrameProvider ABC** (`src/python/bhdr/backends/base.py`) is the interface between capture backends and the query layer. All REST routes use this interface.
- **safe_json_response()** — all routes must return this (not raw dicts) to handle bytes from pybind11.
- **Lazy IPC init** — the shim connects to the engine at the first `glXSwapBuffers`, not at constructor time. This avoids fork issues from X11/DRI.

## Running the Eval

```bash
# 1. Start Xvfb (if headless)
Xvfb :99 -screen 0 800x600x24 &
export DISPLAY=:99

# 2. Build
bazel build //...

# 3. Start engine (use Python 3.11)
PY311="path/to/bazel/python3.11"
PYTHONPATH="src/python:bazel-bin/src/bindings" $PY311 -m bhdr.launcher \
    --socket /tmp/bhdr.sock --shm /bhdr --port 18080 --token TOKEN

# 4. Capture a scenario
LD_PRELOAD=bazel-bin/src/shims/gl/libbhdr_gl.so \
    BHDR_SOCKET_PATH=/tmp/bhdr.sock BHDR_SHM_NAME=/bhdr \
    bazel-bin/tests/eval/synthetic/state-leak/e1_state_leak/e1_state_leak

# 5. Query
curl -H "Authorization: Bearer TOKEN" localhost:18080/api/v1/frames/current/overview
```

## Eval-Driven Development Loop

1. **Mine** — Find real-world graphics bugs from GitHub issues. Curation pipeline writes scenarios with full fix metadata (`fix_pr_url`, `fix_sha`, `fix_parent_sha`, `bug_class`, `files`).
2. **Verify** — `python -m bhdr.eval.curation.verify tests/eval [--network --build]`. Quarantine broken scenarios to `tests/eval-quarantine/`. Skipping this stage = silent signal degradation.
3. **Capture** — Run native scenarios under the GL/Vulkan shim. **Skip for WebGL/JS** — the native shim doesn't intercept browser GL calls.
4. **Evaluate** — Run with/without Beholder across model tiers, compare accuracy × token cost.
5. **Improve** — Fix capture bugs or add new capabilities based on eval gaps. Re-run eval to verify. Write `docs/eval-rounds/YYYY-MM-DD-<round>.md` with Ran / Findings / Added / Removed / Numbers / Open backlog. Append-only — don't rewrite prior rounds.

The full skill: `~/.claude/skills/eval-driven-improvement/SKILL.md` (reference: `docs/skills/eval-driven-improvement.md`). Round-log template: `docs/eval-rounds/README.md`.

Eval scenarios live in `tests/eval/<category>/<framework>/<slug>/`. See `docs/eval-scenario-format.md` for the schema. Source files must NOT contain hint comments (// BUG, // should be, etc.) — the verifier rejects them.

### Snapshot pipeline invariants (load-bearing)

| Invariant | Failure mode if violated |
|---|---|
| `fix_parent_sha` populated | Snapshot serves post-fix tree; agents investigate already-fixed code |
| `SnapshotFetcher` per-cache-key fcntl lock | Parallel modes race on the same cache dir, FileNotFoundError on cwd |
| `--unshallow` only when `.git/shallow` exists | git fatals "--unshallow on a complete repository" after fallback |
| `runner._bazel_target_for(scenario)` for live capture | Old `//tests/eval:<slug>` targets don't exist post-taxonomy migration |

### Mining (single-path pipeline)

```bash
# 1. Generate new queries from an instruction (LLM, deduped against scope-log)
PYTHONPATH=src/python python3 -m bhdr.eval.curation.gen_queries \
  --instruction "WebGPU compute shader artifacts" \
  --scope-log .eval-pipeline/scope-log.jsonl \
  --out /tmp/new_queries.yaml \
  --max-queries 10 --llm-backend claude-cli

# 2. Mine those queries (or any existing query pack)
PYTHONPATH=src/python python3 -m bhdr.eval.curation.run \
  --queries /tmp/new_queries.yaml \
  --rules src/python/bhdr/eval/curation/mining_rules.yaml \
  --workdir .eval-pipeline \
  --batch-quota 30
  # --max-phase {select,produce,judge}: select skips LLM/commit; judge default
  # --evaluate: opt-in, runs agent eval; needs configured harness
```

Outputs: per-run `journey.jsonl` + `summary.md` + cross-run
`scope-log.jsonl`. The scope log is the persistent source of truth
for "what's already been mined" — `gen_queries` reads it on every
call so future LLM proposals avoid re-mined queries/repos.

Spec: `docs/superpowers/specs/2026-05-01-single-path-mining-design.md`.

## Adding a New GL Function to Intercept

1. `src/shims/gl/gl_wrappers.h` — add function pointer to `BhdrRealGlFuncs`
2. `src/shims/gl/gl_wrappers.c` — add dlsym in `bhdr_wrappers_init()`, add wrapper function, add to `bhdr_resolve_wrapper()`
3. `src/shims/gl/shadow_state.h/c` — add state tracking if needed
4. `src/shims/gl/frame_capture.c` — add to `BhdrDrawCallSnapshot` if serialized per draw call
5. `src/core/engine.cpp` — add deserialization in `ingest_frame()`
6. `src/core/normalize/normalized_types.h` — add to `NormalizedDrawCall`
7. `src/bindings/py_bhdr.cpp` — expose to Python

## Adding a New Capture Backend

Implement `FrameProvider` from `src/python/bhdr/backends/base.py`:
- `get_frame_overview()`, `get_latest_overview()`
- `list_draw_calls()`, `get_draw_call()`
- `get_pixel()`
- `compare_frames()`
- Optional: `pause()`, `resume()`, `step()`, `status()`

See `native.py` and `renderdoc.py` for examples.

## Adding a New REST Endpoint

1. Create `src/python/bhdr/api/routes_NAME.py`
2. Use `safe_json_response()` for ALL returns (prevents pydantic bytes crash)
3. Register in `src/python/bhdr/api/app.py`
4. Add tests in `tests/unit/python/test_api_NAME.py`

## Known Issues

- Engine launcher crashes on process exit (`terminate called without an active exception`) — the C++ engine thread's destructor fires during Python shutdown. Use `engine.stop()` before exit.
- Control socket tests use native endian for FrameReadyPayload (not network byte order).
- `r36_opengl_proximity_fade` scenario may need additional GL functions intercepted.

## File Locations

| What | Where |
|------|-------|
| GL shim (C) | `src/shims/gl/` |
| Vulkan layer (C) | `src/shims/vk/` |
| WebGL extension (JS) | `src/shims/webgl/` |
| Core engine (C++) | `src/core/` |
| Python bindings | `src/bindings/py_bhdr.cpp` |
| REST API | `src/python/bhdr/api/` |
| MCP server | `src/python/bhdr/mcp/` |
| Framework integration | `src/python/bhdr/framework/` |
| Capture backends | `src/python/bhdr/backends/` |
| Eval harness | `src/python/bhdr/eval/` |
| C++ unit tests | `tests/unit/core/` |
| Shim unit tests | `tests/unit/shims/` |
| Python unit tests | `tests/unit/python/` |
| Eval scenarios | `tests/eval/` |
| Integration tests | `tests/integration/` |
| Design specs | `docs/superpowers/specs/` |
| Plans | `docs/superpowers/plans/` |
