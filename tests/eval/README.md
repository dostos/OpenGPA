# Eval Scenarios

Adversarial rendering bug scenarios for OpenGPA's eval harness.
Organized by taxonomy: `<category>/<framework>/<slug>/` for mined
real-world bugs, `synthetic/<topic>/<slug>/` for hand-authored ones.
See `docs/superpowers/specs/2026-05-02-eval-scenario-taxonomy-layout-design.md`
for the full design.

## Layout

    tests/eval/
    ├── synthetic/                  # hand-authored, e1..e33
    │   ├── state-leak/
    │   ├── uniform/
    │   ├── depth/
    │   ├── culling/
    │   ├── stencil/
    │   ├── nan/
    │   └── misc/
    ├── native-engine/              # mined: godot, bevy
    ├── web-3d/                     # mined: three.js, babylon.js, ...
    ├── web-2d/                     # mined: pixijs, p5.js
    ├── web-map/                    # mined: mapbox-gl-js, itowns, qwc2
    └── graphics-lib/               # mined: webgl

## Per-Scenario Files

| File | Required | Description |
|------|----------|-------------|
| `scenario.md` | yes | Prose: user report, expected vs actual, ground truth, difficulty rating. No hint comments. |
| `scenario.yaml` | yes | Machine-readable metadata (round, source URL, taxonomy, backend, status). Schema in `src/python/bhdr/eval/scenario_metadata.py`. |
| `*.c` / `main.c` | no | Buggy GL/Vulkan C app, when a runnable repro has been built. |
| `BUILD.bazel` | only when `*.c` | Single `cc_binary(name=<leaf-slug>, ...)`. |

## Slug Rules

| Source | Slug form |
|--------|-----------|
| GitHub issue | `<repo>_<issue-num>_<slug>` |
| GitHub PR | `<repo>_pull_<num>_<slug>` |
| StackOverflow | `so_<question-id>_<slug>` |
| Synthetic | `e{N}_<slug>` |

`<repo>` is the basename, normalized to lowercase + alphanum
(`three.js` → `threejs`, `mapbox-gl-js` → `mapbox_gl_js`).

## Adding a Scenario

For mined scenarios, the curation pipeline (`gpa.eval.curation.run`)
emits into the new layout automatically — no manual placement needed.

For synthetic scenarios:
1. Pick a topic bucket (or add one in `migrate_layout.py:_SYNTHETIC_BUCKETS`).
2. Create `tests/eval/synthetic/<topic>/e{N}_<slug>/`.
3. Write `scenario.md` (no hint comments) and a corresponding
   `scenario.yaml` with `source.type: synthetic`.
4. Add `main.c` if the bug needs a runnable repro.
5. `bazel build //tests/eval/synthetic/<topic>/e{N}_<slug>` should
   succeed when a `.c` file is present.

## Querying the Index

    gpa-eval index --by taxonomy        # category × framework counts
    gpa-eval index --by backend         # api × status counts

## See Also

- `src/python/bhdr/eval/scenario_metadata.py` — schema + validator
- `src/python/bhdr/eval/migrate_layout.py` — migration tool
- `docs/superpowers/specs/2026-05-02-eval-scenario-taxonomy-layout-design.md` — design
- `docs/superpowers/plans/2026-05-02-eval-scenario-taxonomy-layout.md` — implementation plan
