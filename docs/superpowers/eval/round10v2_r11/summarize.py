"""Summarize R10v2+R11 scoring → /tmp/eval_r10v2_r11/summary.txt.

Two subsets:
  R10v2 — r2, r11×2, r14, r17_mapbox, r18_raster
  R11   — r53, r54, r55, r56, r57

Per subset: per (mode × model) tables for accuracy / file_score / verdict /
gpa_calls / cost / cache_read.

Also dumps R11 per-scenario breadcrumb-trace usage matrix:
  scenario × model: trace_value_called?, breadcrumb_value_seen?, solved?
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROUND_DIR = Path("/tmp/eval_r10v2_r11")

R10V2_SCENARIOS = {
    "r2_certain_effects_produce_invalid_alpha_va",
    "r11_screen_glitch_with_bloom_on_m1_mac",
    "r11_webglrenderer_ubo_uniform_buffer_object_",
    "r14_webgpurenderer_make_colored_shadows_opti",
    "r17_mapbox_gl_js_image_overlay_coordinates_p",
    "r18_raster_tiles_aren_t_perfectly_crisp_at_i",
}

R11_SCENARIOS = {
    "r53_hemispherelightprobe_intensity_wrong_",
    "r54_black_squares_when_rendering_glass_ma",
    "r55_certain_gltf_models_not_receiving_sha",
    "r56_conegeometry_has_wrong_side_faces_and",
    "r57_ktx2_texture_with_alphahash_renders_a",
}

MODELS = ["haiku", "sonnet", "opus"]
MODES = ["code_only", "with_gpa"]


def _summarize_subset(rows, label):
    out = []
    out.append(f"\n=========== {label} ({len(rows)} rows) ===========")

    # mode × model aggregate.
    cells = defaultdict(list)
    for r in rows:
        cells[(r["mode"], r["model"])].append(r)

    out.append("")
    out.append(f"{'MODE':<10} {'MODEL':<8} {'N':>3} "
               f"{'solved%':>8} {'fscore':>7} {'verdict':>20} "
               f"{'gpa_calls':>10} {'trace?':>7} "
               f"{'cost':>7} {'cache_r':>9}")
    out.append("-" * 110)
    for mode in MODES:
        for model in MODELS:
            cell = cells.get((mode, model), [])
            n = len(cell)
            if not n:
                out.append(f"{mode:<10} {model:<8} {0:>3}")
                continue
            solved = sum(1 for r in cell if r.get("maintainer_solved"))
            fscore = sum(r.get("file_score", 0) or 0 for r in cell) / n
            cost = sum(r.get("cost_usd", 0) or 0 for r in cell)
            cache_r = sum(r.get("cache_read", 0) or 0 for r in cell) / 1_000_000
            gpa_calls = sum(r.get("gpa_calls", 0) or 0 for r in cell)
            trace_n = sum(1 for r in cell if r.get("trace_value_called"))

            verdicts = defaultdict(int)
            for r in cell:
                verdicts[r.get("verdict", "?")] += 1
            v = ",".join(f"{k}={v}" for k, v in sorted(verdicts.items()))[:20]

            out.append(
                f"{mode:<10} {model:<8} {n:>3} "
                f"{100*solved/n:>7.1f}% {fscore:>7.2f} {v:>20} "
                f"{gpa_calls:>10d} {trace_n:>4d}/{n:<2d} "
                f"${cost:>5.2f} {cache_r:>7.2f}M"
            )
    return out


def _per_scenario_breadcrumb_matrix(rows, label):
    out = []
    out.append(f"\n=========== {label} per-scenario breadcrumb matrix ===========")
    out.append("")
    out.append(f"{'SCENARIO':<46} {'MODEL':<8} "
               f"{'mode':<10} {'solved':>7} "
               f"{'trace_called':>13} {'breadcrumb_seen':>16} "
               f"{'gpa_calls':>10} "
               f"{'fscore':>7}")
    out.append("-" * 130)
    by_scen = defaultdict(list)
    for r in rows:
        by_scen[r["scenario"]].append(r)
    for scen in sorted(by_scen):
        for model in MODELS:
            for mode in MODES:
                cells = [r for r in by_scen[scen] if r.get("model") == model and r.get("mode") == mode]
                if not cells:
                    continue
                r = cells[0]
                out.append(
                    f"{scen[:46]:<46} {model:<8} {mode:<10} "
                    f"{('Y' if r.get('maintainer_solved') else 'n'):>7} "
                    f"{('Y' if r.get('trace_value_called') else 'n'):>13} "
                    f"{('Y' if r.get('breadcrumb_value_seen') else 'n'):>16} "
                    f"{r.get('gpa_calls',0):>10d} "
                    f"{r.get('file_score',0) or 0:>7.2f}"
                )
        out.append("")
    return out


def main():
    rows = json.loads((ROUND_DIR / "scored.json").read_text())

    # Per-mode per-model totals (overall).
    out_lines = []
    out_lines.append(f"R10v2 + R11 evaluation summary  (66 runs)")
    out_lines.append(f"=" * 80)

    r10v2_rows = [r for r in rows if r["scenario"] in R10V2_SCENARIOS]
    r11_rows = [r for r in rows if r["scenario"] in R11_SCENARIOS]
    other_rows = [r for r in rows if r["scenario"] not in R10V2_SCENARIOS and r["scenario"] not in R11_SCENARIOS]

    out_lines += _summarize_subset(r10v2_rows, "Set A — R10v2 keepers (6 scen × 6 cells = 36)")
    out_lines += _summarize_subset(r11_rows, "Set B — R11 breadcrumb (5 scen × 6 cells = 30)")
    if other_rows:
        out_lines += _summarize_subset(other_rows, "OTHER (unmatched scenario)")

    # Per-scenario breadcrumb matrix for R11.
    out_lines += _per_scenario_breadcrumb_matrix(r11_rows, "R11 breadcrumb")
    out_lines += _per_scenario_breadcrumb_matrix(r10v2_rows, "R10v2 keepers")

    # Aggregate cost.
    total = sum(r.get("cost_usd", 0) or 0 for r in rows)
    out_lines.append("")
    out_lines.append(f"TOTAL cost: ${total:.2f}")

    # Errors.
    errors = [r for r in rows if r.get("error")]
    if errors:
        out_lines.append(f"\n{len(errors)} runs errored:")
        for r in errors[:10]:
            out_lines.append(f"  {r['scenario']} {r['mode']} {r['model']}: {r['error']}")

    text = "\n".join(out_lines) + "\n"
    (ROUND_DIR / "summary.txt").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
