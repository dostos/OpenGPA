# Eval Dashboard — Design

**Status**: Draft

**Date**: 2026-05-15

**Owner**: Jingyu

## Summary

A static, local-only HTML dashboard that curates per-round Beholder eval
results. Primary axis: `code_only` vs `with_bhdr` per scenario type,
across model tiers, across rounds. Lives in `dashboard/`; built by a
Python script that aggregates `/data3/bhdr-eval-results/*/*.json` and
`docs/eval-rounds/*.md` into a single `index.json` consumed by one
HTML file with Plotly charts.

## Motivation

The round logs in `docs/eval-rounds/` already capture per-round
results, audit findings, and backlog items, but read as separate
text files. There's no single view to:

- Compare `code_only` vs `with_bhdr` per scenario type at a glance.
- See how solve% and cost-per-solve trend round-over-round per type.
- Spot recoveries (R18 `world_environment` ✗→✓) or regressions
  visually.
- Surface model-tier differences (haiku/sonnet/opus) when multi-tier
  eval lands (R19+).

The dashboard fills that gap without prescribing how rounds are
authored — markdown stays the source of truth for narrative; the
dashboard reads it as-is.

## Non-Goals

- **Multi-tier eval orchestration**. The dashboard renders whatever
  data exists; running with_bhdr across haiku/sonnet/opus is a separate
  pipeline-fix spec (R19 backlog).
- **Auto-rebuild**. No git hook, no watcher. Run the build script
  after each round.
- **Round-vs-round picker**. The line traces convey trends already;
  no UI to "compare R18 to R13 specifically".
- **Scenario search / filter**. The cohort is small enough to scan.
- **Hosted version, auth, multi-user**. Local-only.

## Constraints

- One static HTML file output, openable from `file://` in a browser.
- Markdown narrative stays in `docs/eval-rounds/*.md`. The build
  script does not parse it into structured fields; it attaches the
  raw text and lets the dashboard render via `marked.js`.
- Python 3.10+ for the build script (matches existing eval tooling).
- Plotly.js loaded from CDN initially; vendoring is a follow-up if
  offline use becomes necessary.

## Scope: Which Rounds Are Rendered

**Only rounds whose result JSON carries a `verdict` field are rendered.**
That's R12c-onward (8 rounds: R12c, R12d, R13, R14, R15, R16, R17, R18).
Pre-R12 rounds used the keyword-based `correct_diagnosis`/`correct_fix`
schema that R17 deleted; faking a verdict from those would silently
miscount history. They stay accessible via the narrative cards if a
round log exists, but they don't appear in chart panels.

`EvalResult.from_dict` (`src/python/bhdr/eval/metrics.py:57`) already
tolerates legacy keys; the build script uses it for safe loading but
treats `verdict is None` as "skip this row from charts".

### Round directories on disk: real shapes

| Layout | Example | Handling |
|---|---|---|
| `code_only.json` + `with_bhdr.json` | `2026-05-05-r13-scope-hint/` | Load both; `mode` per file |
| `code_only_merged.json` | `2026-05-05-r17/` | Prefer over `code_only.json` (merged = partial + resume) |
| `results.json` only | `2026-05-04-round4-claude-cli/` | Legacy; verdict absent → exclude from charts |
| `<round>-rerun` / `<round>-resume` | `2026-05-05-r17-resume/` | **Fold into parent round**: see merge rule below |

### Rerun/resume merge rule

`<base>-resume` and `<base>-rerun` directories belong to the same
round as `<base>`. When folding:

1. Round id is the base id (`r17`, not `r17-resume`).
2. Result rows from the resume/rerun overlay the base by
   `(scenario_id, mode)` — last write wins.
3. The result dir with the most data (post-merge) is exposed as
   `results_path`; resume/rerun paths listed in `aux_paths`.

Without this, R17 and R17-resume render as separate points on the
chart and the round-over-round series doesn't line up.

## Architecture

```
docs/eval-rounds/*.md          ─┐
                                 ├─> scripts/build-eval-dashboard.py
/data3/bhdr-eval-results/*/.json ─┘                  │
                                                     ▼
                                          dashboard/index.json
                                                     │
                                                     ▼
                                          dashboard/index.html
                                          (open in browser)
```

The build script is the only piece that knows about the directory
layouts. The HTML is dumb — it fetches `index.json` and renders.

### Files

```
src/python/bhdr/eval/dashboard/__init__.py
src/python/bhdr/eval/dashboard/build.py           # build aggregator (new)
scripts/build-eval-dashboard.sh                  # thin PYTHONPATH+module shim
dashboard/index.html                             # static page template (new)
dashboard/index.json                             # build output (gitignored)
dashboard/index.css                              # styles (new)
dashboard/app.js                                 # render logic (new)
tests/unit/python/test_dashboard_build.py        # unit tests (new)
tests/fixtures/dashboard/sample-index.json       # for offline HTML dev (new)
.gitignore                                       # add dashboard/index.json
```

Run after each round:
```bash
scripts/build-eval-dashboard.sh
# then open dashboard/index.html in a browser
```

## Data Model

`dashboard/index.json` shape:

```json
{
  "built_at": "2026-05-15T02:13:00+00:00",
  "scenario_types": ["native-engine/godot", "web-map/cesium", "..."],
  "rounds": [
    {
      "id": "r18",
      "date": "2026-05-14",
      "tag": "round-r18-end",
      "results_path": "/data3/bhdr-eval-results/2026-05-14-r18/",
      "aux_paths": [],
      "narrative_path": "docs/eval-rounds/2026-05-14-r18.md",
      "narrative_md": "...full file contents...",
      "headline": "11/13 solved — bug_class prompt dispatch deleted",
      "results": [
        {
          "scenario_id": "rfc2ac5_..._world_environment_glow_eff",
          "scenario_type": "native-engine/godot",
          "mode": "code_only",
          "tier": "opus",
          "solved": true,
          "scorer": "file_level",
          "confidence": "high",
          "output_tokens": 20155,
          "tool_calls": 44,
          "expected_failure": null
        }
      ]
    }
  ]
}
```

### Field derivations

| Field | Source |
|---|---|
| `scenario_type` | Slice the path after `tests/eval/`: `<category>/<framework>`. Same parts logic as `is_browser_tier_scenario` (`scenario.py:46-56`) — slice `Path(scenario_dir).parts` after the `"eval"` index, take 2 parts |
| `tier` | **Per-round override file** (see below). NOT derived from `model` — that's `"unknown"` in every existing result file |
| `mode` | Each `EvalResult.mode` |
| `solved`, `scorer`, `confidence` | `EvalResult.verdict.{solved, scorer, confidence}` |
| `expected_failure` | `ScenarioMetadata.expected_failure` (R18-P0 backfill) |
| `narrative_md` | `Path(narrative_path).read_text()` — verbatim |
| `headline` | First non-heading sentence under `# Round R##`; fallback `round_id` only (no synthesized N/M math) |

### Tier source (corrects reviewer issue #1)

Every existing eval result JSON has `model: "unknown"` because the
claude-cli backend doesn't capture the model identifier into result
records. Deriving tier from that field gives 100% `unknown`.

Two-step resolution:

1. **Per-round meta override**: optional `meta.json` next to the
   result file:
   ```json
   { "tier": "opus", "model": "claude-opus-4-7[1m]" }
   ```
   The build script seeds these for R12c..R18 (all opus) the first
   time it runs and writes them adjacent to the result JSON. Future
   multi-tier rounds (R19+) populate this from the eval CLI itself
   (separate spec).
2. **Fallback**: if no meta and `model` regex fails, tier = `"unknown"`
   and the row is rendered under an "unknown" trace (gray, dotted).

Until R19's multi-tier eval lands, every panel will show only the
`opus` traces. The 6-trace design (`{CO,GLA} × {haiku,sonnet,opus}`)
is forward-compatible, not currently-utilized.

### Same scenario_id across rounds with different scenario_type

Scenarios moved during the R10 taxonomy migration. The grid groups
by `scenario_id` and uses the **latest** `scenario_type` seen for
that id (most recent round wins). Cells from earlier rounds with
the old taxonomy path still render — the grouping just uses the
new type label.

### Aggregation (computed client-side)

For each (round, scenario_type, mode, tier):
- `solve_pct`: solved / n × 100
- `tok_per_solve`: avg output_tokens across solved scenarios in the group
- `n`: count of results in the group

`expected_failure` scenarios excluded from `solve_pct` by default;
controls bar toggle includes them.

## Page Layout

Single scrollable page, top to bottom:

### Header + Controls

- Last build timestamp
- Metric switcher: `solve%` / `tok/✓`
- Tier filter: `all` (default) / `haiku` / `sonnet` / `opus`
- Include-expected-failures toggle

### Section 1 — Per-type chart panels (primary)

One Plotly subplot per scenario type. Grid layout, ≤3 columns.

- X-axis: round (categorical; ordered by date)
- Y-axis: selected metric
- Up to 6 traces per panel: `{code_only, with_bhdr} × {haiku, sonnet, opus}`
- Color encodes mode: code_only = blue, with_bhdr = orange
- Dash pattern encodes tier: solid = haiku, dashed = sonnet, dotted = opus
- Missing data → gap in line (Plotly's `connectgaps: false`)
- Hover tooltip: `round · mode · tier · value · n=K`
- Click legend trace to toggle; legend shared across panels via Plotly's
  built-in legend grouping
- All x-axes linked (Plotly `matches: 'x'`)

### Section 2 — Scenario × round timeline grid

Plain HTML table. Rows grouped by scenario_type (latest taxonomy
wins per scenario_id). Columns = rounds left-to-right (oldest →
newest). Cell encoding:

| Cell content | Meaning |
|---|---|
| ✓ `file_level` (green) | solved, file_level high confidence |
| ✓ `judge` / `prose` (amber) | solved via judge or prose fallback |
| ✗ `no_signal` (red) | unsolved, no scoring signal |
| ✗ `low` (red) | unsolved, file_level low-confidence |
| blank | round didn't run this scenario (or skipped it) |

Hover any cell for tokens and tool_calls. No JS framework needed —
plain `<table>` + `data-*` attributes + a tiny tooltip handler.

**No "⊘ skipped" state**: synthesizing skipped cells would require
the build script to join each round against `ScenarioLoader.load_all()`
to know what *would* have been run. Not worth the complexity for the
current data. Absence renders as blank; the per-type panels already
show the auto-skip via missing GLA traces.

### Section 3 — Per-round narrative cards

Newest round first. Each card:

```
┌─ R18 · 2026-05-14 · 11/13 solved · 22.7k tok/✓ ───── [▼]
│  <headline>
│
│  (collapsed by default; click header to expand)
│
│  When expanded: marked.js renders narrative_md inline.
└──────────────────────────────────────────────────────
```

Current/newest round is expanded by default.

## Build Script

**Location**: `src/python/bhdr/eval/dashboard/build.py`, invoked as
`python -m bhdr.eval.dashboard.build` from the project root with
`PYTHONPATH=src/python`. A thin shim at `scripts/build-eval-dashboard.sh`
sets the path and calls the module. Lives inside the gpa.eval package
so it can import `ScenarioLoader` / `EvalResult` directly without
sys.path hacks.

```python
def main():
    raw_rounds = _collect_round_dirs(Path("/data3/bhdr-eval-results"))
    rounds_by_id = _fold_reruns(raw_rounds)  # r17-resume → r17
    rounds = []
    for round_id, dirs in sorted(rounds_by_id.items()):
        primary, aux = dirs[0], dirs[1:]
        result_paths = [_pick_result_file(d) for d in dirs]
        result_paths = [p for p in result_paths if p is not None]
        if not result_paths:
            continue
        merged_results = _merge_results(result_paths)  # by (scenario_id, mode)
        # Drop pre-verdict legacy rows; rounds with zero verdicts → no
        # chart contribution, but the narrative card still renders
        verdict_results = [r for r in merged_results if r.verdict is not None]
        narrative = _find_narrative(round_id)
        tier_meta = _load_tier_meta(primary)  # reads meta.json or seeds opus
        rounds.append({
            "id": round_id,
            "date": _extract_date(primary.name),
            "results_path": str(primary),
            "aux_paths": [str(d) for d in aux],
            "narrative_path": str(narrative) if narrative else None,
            "narrative_md": narrative.read_text() if narrative else None,
            "headline": _extract_headline(narrative) if narrative else round_id,
            "results": list(_enrich_results(verdict_results, tier_meta)),
        })
    output = {
        "built_at": datetime.now(tz=timezone.utc).isoformat(),
        "rounds": rounds,
        "scenario_types": sorted({r["scenario_type"] for rd in rounds for r in rd["results"]}),
    }
    Path("dashboard/index.json").write_text(json.dumps(output, indent=2))
```

Each helper is one function with one clear responsibility; all are
testable without I/O when given a fake filesystem fixture.

### Critical helpers

- `_extract_round_id(name)`: regex on dir basename. `2026-05-14-r18`
  → `r18`. `2026-05-05-iter-r12c-rerun` → `r12c`. `2026-05-05-r17-resume`
  → `r17`. `2026-05-04-round4-claude-cli` → `r4` (legacy form).
- `_fold_reruns(raw_rounds)`: group by extracted id; preserve all
  directories per group so `_merge_results` can fold them.
- `_pick_result_file(dir)`: prefer `*_merged.json` > `code_only.json`
  > `with_bhdr.json` > `results.json`. Returns None if none exist.
- `_merge_results(paths)`: load every path via `EvalResult.from_dict`;
  fold by `(scenario_id, mode)` with last-write-wins.
- `_load_tier_meta(dir)`: read `dir/meta.json` if present; else seed
  `{"tier": "opus", "model": "claude-opus-4-7[1m]"}` and write it
  (manual override after first run for non-opus rounds).
- `_extract_headline(narrative_path)`: scan for the first paragraph
  that isn't a heading or list marker under the `# Round R##` H1.
  Return `None` on failure; caller substitutes `round_id`.

## Testing

- **Build script unit tests** (`tests/unit/python/test_dashboard_build.py`):
  - `_extract_round_id`: covers `2026-05-14-r18` → `r18`,
    `2026-05-05-iter-r12c-rerun` → `r12c`, `2026-05-05-r17-resume`
    → `r17`, `2026-05-04-round4-claude-cli` → `r4`, malformed → None
  - `_fold_reruns`: r17 + r17-resume merge into one group
  - `_pick_result_file` priority: `*_merged.json` > `code_only.json`
    > `with_bhdr.json` > `results.json`; None when nothing matches
  - `_merge_results`: overlay by `(scenario_id, mode)`, last write
    wins, no duplicate rows
  - Verdict-absent rows excluded from chart-bound output but the
    round itself is still included if narrative exists
  - `_enrich_results`: scenario_type derived via path-slice after
    `tests/eval/`; expected_failure backfilled from scenario.yaml
  - `_load_tier_meta`: existing meta.json honored; missing meta
    seeds opus + writes the file
  - Missing /data3 root → empty rounds list, no crash
  - Round dir without matching markdown → narrative_md = null,
    headline = round_id
- **Dashboard HTML**: open `dashboard/index.html` against the fixture
  `tests/fixtures/dashboard/sample-index.json` and verify panels +
  table + cards render. The fixture must include at least one row of
  each: code_only solve, with_bhdr solve, expected_failure, missing
  verdict (excluded), legacy taxonomy path. No JS unit tests; visual
  + click checks.

## Failure Modes

| Condition | Behavior |
|---|---|
| `/data3/bhdr-eval-results/` absent | Build script exits 1 with message |
| Round data exists but no round log | Round included; `narrative_md: null`; card shows "(no round log)" |
| Round log exists but no eval data | Round skipped (nothing to chart, no narrative card either — narratives only render for rounds with rendered data) |
| `verdict` field missing on a result row | **Row excluded from charts and grid** (legacy pre-R12c rounds). If all rows are pre-verdict, the round is excluded entirely |
| `meta.json` absent in a round dir | Build script seeds `{"tier":"opus","model":"claude-opus-4-7[1m]"}` and writes it next to the result file (overridable post-hoc) |
| Per-result `model` populated AND meta says different tier | meta wins (explicit override) |
| All rows in a (round, type, mode, tier) tuple absent | Line trace has no points at that round; legend item still visible |
| Plotly CDN unreachable | Dashboard logs error; panels show empty; table + cards still work |
| Same scenario_id has two different scenario_type values across rounds | Group by id, use latest scenario_type as display label |

## Open Questions

None for v1. Follow-ups recorded in the Beholder strategic backlog:

- **Vendoring Plotly** (Q1 follow-up): bundle a copy for offline use
  when this becomes the daily-driver.
- **Multi-tier eval orchestration** (R19 backlog Q2): once with_bhdr
  + tier multiplexing land, dashboard automatically picks them up —
  no schema changes needed.

## References

- R18 round log: `docs/eval-rounds/2026-05-14-r18.md`
- Strategic direction: `docs/eval-next-steps.md`
- Round-log convention: `docs/eval-rounds/README.md`
- Scenario loader: `src/python/bhdr/eval/scenario.py`
