"""Score all R10 runs and emit scored.json.

Reads /tmp/eval_round10/*.jsonl, derives per-run metrics via
gpa.eval.telemetry.parse_stream_json, extracts the JSON tail via
gpa.eval.scorer._extract_json_tail, and scores via score_maintainer_patch.
Classifies each verdict with classify_verdict.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, "/home/jingyulee/gh/gla/src/python")

from gpa.eval.scenario import ScenarioLoader
from gpa.eval.scorer import _extract_json_tail, score_maintainer_patch
from gpa.eval.telemetry import classify_verdict, parse_stream_json

ROUND_DIR = Path("/tmp/eval_round10")
TASKS = (ROUND_DIR / "tasks.txt").read_text().splitlines()
SCEN_DIR = Path("/home/jingyulee/gh/gla/tests/eval")

# Snapshot mapping — must mirror snapshot_map.sh.
_SNAPSHOT_MAP = {
    "r2_certain_effects_produce_invalid_alpha_va":      "/data3/opengpa-snapshots/postprocessing",
    "r6_to_create_an_orm_texture_an_incorrect_va":      "/data3/opengpa-snapshots/postprocessing",
    "r11_screen_glitch_with_bloom_on_m1_mac":           "/data3/opengpa-snapshots/github_com__mrdoob__three__4c14bb184ca3",
    "r11_webglrenderer_ubo_uniform_buffer_object_":     "/data3/opengpa-snapshots/github_com__mrdoob__three__4c14bb184ca3",
    "r14_webgpurenderer_make_colored_shadows_opti":     "/data3/opengpa-snapshots/github_com__mrdoob__three__4c14bb184ca3",
    "r17_incorrect_clipping_with_global_clipping_":     "/data3/opengpa-snapshots/github_com__mrdoob__three__7690b5090676",
    "r17_mapbox_gl_js_image_overlay_coordinates_p":     "/data3/opengpa-snapshots/github_com__mapbox__mapbox-gl-js__97fc828fc04e",
    "r18_raster_tiles_aren_t_perfectly_crisp_at_i":     "/data3/opengpa-snapshots/github_com__mapbox__mapbox-gl-js__97fc828fc04e",
    "r24_logarithmicdepthbuffer_causes_reflector_":     "/data3/opengpa-snapshots/github_com__mrdoob__three__cf60b969c46b",
}


def main() -> None:
    loader = ScenarioLoader(SCEN_DIR)
    rows = []
    for line in TASKS:
        line = line.strip()
        if not line:
            continue
        scen, mode, model = line.split()
        jsonl_path = ROUND_DIR / f"{scen}_{mode}_{model}.jsonl"
        parsed = parse_stream_json(str(jsonl_path))
        result_text = parsed.get("result_text") or ""
        tail = _extract_json_tail(result_text)

        try:
            s = loader.load(scen)
        except Exception as e:
            rows.append({
                "scenario": scen, "mode": mode, "model": model,
                "error": f"scenario load: {e}",
            })
            continue

        snap = _SNAPSHOT_MAP.get(scen)
        snapshot_root = Path(snap) if snap else None
        fix = s.fix
        if fix is None:
            rows.append({
                "scenario": scen, "mode": mode, "model": model,
                "error": "no Fix metadata in scenario",
            })
            continue

        score = score_maintainer_patch(tail, fix, snapshot_root=snapshot_root) if tail else None
        score_dict = asdict(score) if score else None

        tool_counts = parsed.get("tool_counts") or {}
        # Call-count for GPA endpoint usage.
        gpa_calls = tool_counts.get("gpa", 0) + tool_counts.get("curl", 0)

        run = {
            "parsed_json": tail is not None,
            "score_result": score_dict,
            "turns": parsed.get("num_turns", 0),
            "result_text": result_text,
        }
        verdict = classify_verdict(run, max_turns_budget=40)

        file_score = 0.0
        file_hits = []
        file_misses = []
        file_extras = []
        out_of_tree = []
        maintainer_solved = False
        if score_dict:
            file_score = score_dict.get("file_score", 0.0)
            file_hits = score_dict.get("file_hits", [])
            file_misses = score_dict.get("file_misses", [])
            file_extras = score_dict.get("file_extras", [])
            out_of_tree = score_dict.get("out_of_tree", [])
            maintainer_solved = score_dict.get("solved", False)

        rows.append({
            "scenario": scen,
            "mode": mode,
            "model": model,
            "turns": parsed.get("num_turns", 0),
            "cost_usd": parsed.get("total_cost_usd", 0.0),
            "total_output_tokens": parsed.get("total_tokens_out", 0),
            "cache_read": parsed.get("cache_read", 0),
            "cache_creation": parsed.get("cache_creation", 0),
            "tool_counts": tool_counts,
            "gpa_calls": gpa_calls,
            "file_score": file_score,
            "file_hits": file_hits,
            "file_misses": file_misses,
            "file_extras": file_extras,
            "out_of_tree": out_of_tree,
            "parsed_json": tail is not None,
            "maintainer_solved": maintainer_solved,
            "verdict": verdict,
        })

    out_path = ROUND_DIR / "scored.json"
    out_path.write_text(json.dumps(rows, indent=2))
    print(f"wrote {out_path} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
