# Eval Dashboard — Design

**Status**: Draft

**Date**: 2026-05-15

**Owner**: Jingyu

## Summary

A static, local-only HTML dashboard that curates per-round OpenGPA eval
results. Primary axis: `code_only` vs `with_gla` per scenario type,
across model tiers, across rounds. Lives in `dashboard/`; built by a
Python script that aggregates `/data3/gla-eval-results/*/*.json` and
`docs/eval-rounds/*.md` into a single `index.json` consumed by one
HTML file with Plotly charts.

## Motivation

The round logs in `docs/eval-rounds/` already capture per-round
results, audit findings, and backlog items, but read as separate
text files. There's no single view to:

- Compare `code_only` vs `with_gla` per scenario type at a glance.
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
  data exists; running with_gla across haiku/sonnet/opus is a separate
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

## Architecture

```
docs/eval-rounds/*.md          ─┐
                                 ├─> scripts/build-eval-dashboard.py
/data3/gla-eval-results/*/.json ─┘                  │
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
scripts/build-eval-dashboard.py     # build aggregator (new)
dashboard/index.html                 # static page template (new)
dashboard/index.json                 # build output (gitignored)
dashboard/index.css                  # styles (new, vendored)
dashboard/app.js                     # render logic (new, vendored)
tests/fixtures/dashboard/sample-index.json   # for offline HTML dev (new)
.gitignore                           # add dashboard/index.json
```

`scripts/build-eval-dashboard.py` is the entry point; rerun manually
after each round.

## Data Model

`dashboard/index.json` shape:

```json
{
  "built_at": "2026-05-15T11:13:00+09:00",
  "scenario_types": ["native-engine/godot", "web-map/cesium", "..."],
  "rounds": [
    {
      "id": "r18",
      "date": "2026-05-14",
      "tag": "round-r18-end",
      "results_path": "/data3/gla-eval-results/2026-05-14-r18/",
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
| `scenario_type` | `ScenarioLoader.load(sid).scenario_dir` → `<category>/<framework>` |
| `tier` | Regex on `model` field: `claude-(opus|sonnet|haiku)-…` |
| `mode` | Each `EvalResult.mode` |
| `solved`, `scorer`, `confidence` | `EvalResult.verdict.{solved, scorer, confidence}` |
| `expected_failure` | `ScenarioMetadata.expected_failure` (R18-P0 backfill) |
| `narrative_md` | `Path(narrative_path).read_text()` — verbatim |
| `headline` | First non-heading sentence under `# Round R##`; fallback `"r<id> · N/M solved"` |

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
- Up to 6 traces per panel: `{code_only, with_gla} × {haiku, sonnet, opus}`
- Color encodes mode: code_only = blue, with_gla = orange
- Dash pattern encodes tier: solid = haiku, dashed = sonnet, dotted = opus
- Missing data → gap in line (Plotly's `connectgaps: false`)
- Hover tooltip: `round · mode · tier · value · n=K`
- Click legend trace to toggle; legend shared across panels via Plotly's
  built-in legend grouping
- All x-axes linked (Plotly `matches: 'x'`)

### Section 2 — Scenario × round timeline grid

Plain HTML table. Rows grouped by scenario_type. Columns = rounds
left-to-right (oldest → newest). Cell encoding:

| Cell content | Meaning |
|---|---|
| ✓ `file_level` (green) | solved, high-confidence file_level |
| ✓ `judge` (amber) | solved, judge fallback |
| ✓ `prose` (amber) | solved, prose fallback |
| ✗ `no_signal` (red) | unsolved, no scoring signal |
| ✗ `low` (red) | unsolved, file_level low-confidence |
| ⊘ (gray) | mode skipped (e.g. with_gla on source-less) |
| blank | round didn't include scenario |

Hover any cell for tokens and tool_calls. No JS framework needed —
plain `<table>` + `data-*` attributes + a tiny tooltip handler.

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

```python
# scripts/build-eval-dashboard.py
def main():
    rounds = []
    for round_dir in sorted(Path("/data3/gla-eval-results").iterdir()):
        if not round_dir.is_dir():
            continue
        round_id = _extract_round_id(round_dir.name)  # "2026-05-14-r18" → "r18"
        result_json = _pick_result_file(round_dir)    # merged > full > partial
        if result_json is None:
            continue
        narrative = _find_narrative(round_id)         # docs/eval-rounds/*-{round_id}.md
        rounds.append({
            "id": round_id,
            "date": _extract_date(round_dir.name),
            "results_path": str(round_dir),
            "narrative_path": str(narrative) if narrative else None,
            "narrative_md": narrative.read_text() if narrative else None,
            "headline": _extract_headline(narrative) if narrative else f"{round_id}",
            "results": list(_enrich_results(result_json)),
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

## Testing

- **Build script unit tests** (`tests/unit/python/test_build_eval_dashboard.py`):
  - `_parse_tier`: claude-opus-4-7[1m], claude-sonnet-4-6,
    claude-haiku-4-5-20251001, malformed strings
  - `_extract_round_id`: 2026-05-14-r18 → r18; 2026-05-05-iter-r12c-rerun → r12c
  - `_pick_result_file` priority: merged > full > partial
  - `_enrich_results`: scenario_type derivation matches
    `ScenarioLoader._eval_dir`; expected_failure backfilled from
    scenario.yaml
  - Missing /data3 root → empty rounds list, no crash
  - Round dir without matching markdown → narrative_md = null
- **Dashboard HTML**: open `dashboard/index.html` against the fixture
  `tests/fixtures/dashboard/sample-index.json` and verify panels +
  table + cards render. No JS unit tests; visual + click checks.

## Failure Modes

| Condition | Behavior |
|---|---|
| `/data3/gla-eval-results/` absent | Build script exits 1 with message |
| Round data exists but no round log | Round included; `narrative_md: null`; card shows "(no round log)" |
| Round log exists but no eval data | Round skipped (nothing to chart) |
| Per-result `model` unparseable | `tier: "unknown"`; grouped under unknown in panels |
| `verdict` missing | `solved: false, scorer: "no_signal", confidence: "low"` |
| All scenarios skipped for a (round, type, mode, tier) tuple | Line trace has no points; legend item dimmed |
| Plotly CDN unreachable | Dashboard logs error; panels show empty; table + cards still work |

## Open Questions

None for v1. Follow-ups recorded in the OpenGPA strategic backlog:

- **Vendoring Plotly** (Q1 follow-up): bundle a copy for offline use
  when this becomes the daily-driver.
- **Multi-tier eval orchestration** (R19 backlog Q2): once with_gla
  + tier multiplexing land, dashboard automatically picks them up —
  no schema changes needed.

## References

- R18 round log: `docs/eval-rounds/2026-05-14-r18.md`
- Strategic direction: `docs/eval-next-steps.md`
- Round-log convention: `docs/eval-rounds/README.md`
- Scenario loader: `src/python/gpa/eval/scenario.py`
