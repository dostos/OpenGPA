"""Score all R10v2+R11 runs and emit scored.json.

Reads /tmp/eval_r10v2_r11/*.jsonl, derives per-run metrics via
gpa.eval.telemetry.parse_stream_json, extracts the JSON tail via
gpa.eval.scorer._extract_json_tail, scores via score_maintainer_patch.
Classifies each verdict with classify_verdict.

Adds R11-specific 'breadcrumb_lookup_attempted' / 'breadcrumb_value_seen'
tool-trace flags so we can answer "did the agent invoke trace value on
the breadcrumb literal?" per scenario.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, "/home/jingyulee/gh/gla/src/python")

from gpa.eval.scenario import ScenarioLoader
from gpa.eval.scorer import _extract_json_tail, score_maintainer_patch
from gpa.eval.telemetry import classify_verdict, parse_stream_json

ROUND_DIR = Path("/tmp/eval_r10v2_r11")
TASKS = (ROUND_DIR / "tasks.txt").read_text().splitlines()
SCEN_DIR = Path("/home/jingyulee/gh/gla/tests/eval")

_SNAPSHOT_MAP = {
    # R10v2 set
    "r2_certain_effects_produce_invalid_alpha_va":      "/data3/opengpa-snapshots/postprocessing",
    "r11_screen_glitch_with_bloom_on_m1_mac":           "/data3/opengpa-snapshots/github_com__mrdoob__three__4c14bb184ca3",
    "r11_webglrenderer_ubo_uniform_buffer_object_":     "/data3/opengpa-snapshots/github_com__mrdoob__three__4c14bb184ca3",
    "r14_webgpurenderer_make_colored_shadows_opti":     "/data3/opengpa-snapshots/github_com__mrdoob__three__4c14bb184ca3",
    "r17_mapbox_gl_js_image_overlay_coordinates_p":     "/data3/opengpa-snapshots/github_com__mapbox__mapbox-gl-js__97fc828fc04e",
    "r18_raster_tiles_aren_t_perfectly_crisp_at_i":     "/data3/opengpa-snapshots/github_com__mapbox__mapbox-gl-js__97fc828fc04e",
    # R11 breadcrumb set
    "r53_hemispherelightprobe_intensity_wrong_":        "/data3/opengpa-snapshots/github_com__mrdoob__three__f8509646d78f",
    "r54_black_squares_when_rendering_glass_ma":        "/data3/opengpa-snapshots/github_com__mrdoob__three__bfe332d9ee70",
    "r55_certain_gltf_models_not_receiving_sha":        "/data3/opengpa-snapshots/github_com__mrdoob__three__f3fa844ba4ca",
    "r56_conegeometry_has_wrong_side_faces_and":        "/data3/opengpa-snapshots/github_com__mrdoob__three__8be6bed537fe",
    "r57_ktx2_texture_with_alphahash_renders_a":        "/data3/opengpa-snapshots/github_com__mrdoob__three__fb28a2e295a5",
}

# Per-scenario breadcrumb literal expected to be queried via trace value.
# Pulled from each scenario.md's "Captured-literal breadcrumb" section.
# Keep numeric prefixes flexible — the scorer matches as substring against
# the raw curl URL emitted by the agent.
_BREADCRUMB_LITERALS = {
    "r53_hemispherelightprobe_intensity_wrong_":     ["1.7724", "3.5449", "0.5641"],
    "r54_black_squares_when_rendering_glass_ma":     ["+inf", "Infinity", "0.0"],
    "r55_certain_gltf_models_not_receiving_sha":     ["NaN", "nan"],
    "r56_conegeometry_has_wrong_side_faces_and":     ["192", "576"],
    "r57_ktx2_texture_with_alphahash_renders_a":     ["33778", "0x83F2", "33779"],
}


def _scan_tool_calls_for_trace(jsonl_path: Path) -> tuple[bool, list[str], int, int]:
    """Return (any_trace_call, urls_used, total_curl_calls, total_gpa_cli_calls).

    Scans every tool-input block in the stream-json output for `curl` and
    `gpa` invocations. The first return value is True iff any tool-input
    contains "/trace/value" — i.e. the agent reverse-looked-up a literal.
    """
    if not jsonl_path.exists():
        return False, [], 0, 0
    any_trace = False
    urls = []
    curl_calls = 0
    gpa_calls = 0
    try:
        with open(jsonl_path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                # Look for any string anywhere in the line containing trace/value
                # (cheap pre-filter), then drill into tool_use messages.
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if ev.get("type") != "assistant":
                    continue
                msg = ev.get("message", {}) or {}
                for block in (msg.get("content") or []):
                    if block.get("type") != "tool_use":
                        continue
                    inp = block.get("input") or {}
                    # Bash invocation: the command is in inp["command"].
                    cmd = inp.get("command", "")
                    if not isinstance(cmd, str):
                        continue
                    if "trace/value" in cmd:
                        any_trace = True
                        urls.append(cmd)
                    if "curl" in cmd:
                        curl_calls += 1
                    # gpa CLI invocations.
                    if re.search(r"\bgpa\b", cmd):
                        gpa_calls += 1
    except Exception:
        pass
    return any_trace, urls, curl_calls, gpa_calls


def _breadcrumb_value_seen(urls: list[str], scenario: str) -> bool:
    """Did the agent query a /trace/value with one of the expected literals?"""
    expected = _BREADCRUMB_LITERALS.get(scenario, [])
    if not expected:
        return False
    for u in urls:
        for lit in expected:
            if lit in u:
                return True
    return False


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

        any_trace, trace_urls, curl_calls, gpa_cli_calls = _scan_tool_calls_for_trace(jsonl_path)
        # GPA-effective calls = trace + raw API calls (we count both curl and gpa).
        gpa_calls = curl_calls + gpa_cli_calls

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
            "trace_value_called": any_trace,
            "breadcrumb_value_seen": _breadcrumb_value_seen(trace_urls, scen),
            "trace_urls": trace_urls,
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
