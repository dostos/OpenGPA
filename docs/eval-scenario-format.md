# Eval Scenario Format

Each scenario lives at `tests/eval/<category>/<framework>/<slug>/` with two
required files (`scenario.md`, `scenario.yaml`) and zero or more source
artifacts. Scenarios that fail static verification are moved aside under
`tests/eval-quarantine/<same-path>/` so the harness can't pick them up.

## Files in a scenario directory

| File | Required | Purpose |
|---|---|---|
| `scenario.md` | yes | Human-readable bug description + ground-truth anchor |
| `scenario.yaml` | yes | Machine-readable metadata (taxonomy, source, status) |
| `BUILD.bazel` | live-capture only | Declares the `cc_binary` target |
| `main.c` (+ `.h`/`.glsl`/`.vert`/`.frag`) | live-capture only | Synthetic GL reproducer |

Mined scenarios that target framework-internal bugs in upstream repos
(Godot, Cesium, MapLibre, etc.) typically ship without `main.c` — the bug
is only reproducible by building the framework itself, so the scenario
serves as advisor-mode evaluation material.

## scenario.md anchors

The verifier requires at least one ground-truth anchor section. Pick the
one that matches the scenario type:

### `## Fix` — mined scenarios with a closing PR

```yaml
fix_pr_url: https://github.com/godotengine/godot/pull/109971
fix_sha: ec62f12862c4cfc76526eaf99afa0a24249f8288
fix_parent_sha: 70f07467bed9cb7952b5523a720fba33bc7abf0e
bug_class: framework-internal
files:
  - servers/rendering/renderer_rd/forward_clustered/render_forward_clustered.cpp
  - servers/rendering/renderer_rd/shaders/forward_mobile/scene_forward_mobile.glsl
```

| Field | Notes |
|---|---|
| `fix_pr_url` | Full GitHub PR URL |
| `fix_sha` | The merge commit SHA — **post-fix** state |
| `fix_parent_sha` | First parent of `fix_sha` — **buggy / pre-fix** state. The harness uses this as the upstream snapshot SHA so the agent investigates the bug, not the fix. Required for any github-hosted fix. |
| `bug_class` | One of `framework-internal`, `consumer-misuse`, `user-config`, `legacy` |
| `files` | Source files changed by the fix PR (filtered to drop `tests/`, `docs/`, `doc/`, `specs/`, `examples/`, etc.) |

`bug_class: legacy` is an explicit escape hatch for issues that closed
without a resolvable fix PR (wontfix / known limitation). For that class
only, empty `files: []` and `(none)` placeholders for `fix_pr_url` /
`fix_sha` / `fix_parent_sha` are tolerated.

### `## Upstream Snapshot` — advisor-mode scenarios

For older mined scenarios that point at an upstream tree without a
specific fix PR. The snapshot SHA gives the agent a buggy upstream tree
to investigate via `gpa upstream` tools (list, grep, find-symbol, read).

```markdown
## Upstream Snapshot
- **Repo**: https://github.com/maplibre/maplibre-gl-js
- **SHA**: 71f44f9d98c6a5c1...
- **Relevant Files**:
  - src/render/draw_terrain.ts
  - src/source/terrain.ts
```

### `## Bug Signature` — synthetic scenarios

For hand-authored synthetic scenarios with a runnable `main.c`. The
signature is checked at curation time against the captured framebuffer
to confirm the reproducer triggers the intended state pattern.

```yaml
type: framebuffer_dominant_color
spec:
  expected_rgba: [0.0, 0.0, 0.0, 1.0]
  tolerance: 0.05
```

### `## Ground Truth` — early-round prose

Pre-`Bug Signature` synthetic scenarios anchor on a free-form prose
description. Accepted by the verifier but not auto-scored by the new
scoring stack.

## scenario.yaml status

```yaml
schema_version: 1
slug: <full slug>
status: drafted | verified | quarantined
verification:
  checked_at: <ISO timestamp>
  checks_run: [static, network, build]
  failures: []
```

`status` controls visibility:

- `drafted` — newly minted by the curation pipeline; visible to the
  loader, not yet verified.
- `verified` — passed all requested verifier tiers; safe to evaluate.
- `quarantined` — failed at least one check; **`ScenarioLoader.load_all()`
  hides these by default** so the harness can't accidentally serve a
  broken scenario. Pass `include_quarantined=True` to include them.

## Source contamination

Source files (`.c .h .cpp .glsl .vert .frag`) must not contain hint
comments. The verifier rejects any of:

- `// BUG`, `// BUGGY`, `// FIX`, `// FIXME`, `// HINT`, `// TODO FIX`
- `// should be`, `// Correct (would|is)`, `// expected`,
  `// actual vs expected`

Hint comments leak ground truth and bias the agent. Document the
expected vs actual behavior in `scenario.md`, never in the source.

## Verifying scenarios

```bash
# Static checks only (default), in-place: just records verdict in scenario.yaml
python -m bhdr.eval.curation.verify tests/eval

# All tiers (network: gh api SHA existence; build: bazel build per scenario)
python -m bhdr.eval.curation.verify tests/eval --network --build

# Move failures to tests/eval-quarantine/<original-taxonomy-path>/
python -m bhdr.eval.curation.verify tests/eval --quarantine-dir tests/eval-quarantine

# Re-verify a quarantined scenario (after fixing the underlying defect)
python -m bhdr.eval.curation.verify tests/eval-quarantine
```

The verifier is also useful as a pre-commit gate when authoring or
mining new scenarios.

## Backfilling fix_parent_sha

Older mined scenarios may have `fix_sha` but no `fix_parent_sha`. Without
the parent SHA the upstream snapshot defaults to the post-fix state and
the agent investigates already-fixed code. Backfill via:

```bash
python -m bhdr.eval.curation.backfill_parent_sha tests/eval [--dry-run]
```

The CLI calls `gh api repos/<o>/<r>/commits/<fix_sha>` to read
`parents[0].sha` and inserts a `fix_parent_sha:` line into the fix block.
