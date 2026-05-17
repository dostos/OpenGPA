#!/usr/bin/env python3
"""Score Round 8 eval outputs (state-collision scenarios)."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/jingyulee/gh/gla/src/python")
from gpa.eval.telemetry import parse_stream_json

RESULTS_DIR = Path("/tmp/eval_round8")

# Import R6 GT dict for the carryover scenarios (r10 is new; rest present).
GT_R6_SOURCE = Path("/tmp/eval_round6/score.py").read_text()
_ns: dict = {}
exec(GT_R6_SOURCE, _ns)
GT_R6 = _ns["GT"]
find_json_object = _ns["find_json_object"]

# New GT entries for the 10 state-collision scenarios + r10 carryover.
GT_NEW: dict = {
    "r4_msaa_does_not_always_work_when_doing_rtt": {
        "groups": [
            ["RGBA16F", "HalfFloat", "FP16", "half.?float", "UnsignedByteType",
             "float.?type", "hdr", "floating.?point", "precision"],
            ["tone.?map", "reinhard", "saturat", "clamp",
             "non.?linear", "curve"],
            ["resolve", "msaa", "multisampl", "sample", "blit", "glBlitFramebuffer",
             "average", "coverage", "dominant", "bright"],
        ],
        "min_matches": 2,
    },
    "r4_3d_map_black_screen": {
        "groups": [
            ["feedback.?loop", "feedback_loop", "INVALID_OPERATION",
             "framebuffer.*texture.*same", "same.*texture.*framebuffer"],
            ["sampler", "texture.?bind", "bind.?point", "attachment",
             "COLOR_ATTACHMENT", "DRAW_FRAMEBUFFER"],
            ["no-op", "dropped", "black", "clear.color", "stale", "previous",
             "silently"],
        ],
        "min_matches": 2,
    },
    "r7_webglbackend_copytexturetotexture_doesn_": {
        "groups": [
            ["copyTextureToTexture", "copy.?texture", "3D.?texture", "TEXTURE_3D",
             "TEXTURE_2D_ARRAY", "layer", "slice", "depth"],
            ["single.?slice", "only.*layer", "layer.?0", "base.?layer",
             "z=0", "first.?layer", "not.?iterate", "fall?back"],
            ["WebGLBackend", "WebGLTextureUtils", "framebufferTextureLayer",
             "glFramebufferTextureLayer", "2D.?only", "codepath", "divergent",
             "differ"],
        ],
        "min_matches": 2,
    },
    "r9_transparent_objects_brighten_when_using_": {
        "groups": [
            ["sRGB", "gamma", "linear", "color.?space", "colorSpace",
             "GammaCorrection"],
            ["pow\\(", "1/2.2", "encoded?", "encoding", "inline", "shader",
             "fragment.*output", "before.*blend", "pre.?blend"],
            ["blend", "alpha.?blend", "transparent", "opacity", "framebuffer",
             "FRAMEBUFFER_SRGB", "non.?linear"],
        ],
        "min_matches": 2,
    },
    "r13_cubecamera_render_target_displaying_rand": {
        "groups": [
            ["cube.?map", "TEXTURE_CUBE_MAP", "samplerCube", "cube.?texture",
             "envMap", "env.?tex"],
            ["target.?type", "multiple.?targets", "rebind", "different.?target",
             "GL_TEXTURE_2D", "INVALID_OPERATION", "target.typed",
             "target.specific"],
            ["invalid", "no-?op", "wrong.?texture", "previous.?texture",
             "prior", "black", "silently"],
        ],
        "min_matches": 2,
    },
    "r16_lightprobegenerator_does_not_work_with_e": {
        "groups": [
            ["FloatType", "HalfFloat", "Float32Array", "Uint16Array",
             "readPixels", "readback", "buffer.?size"],
            ["mismatch", "wrong.?type", "type.?mismatch", "byte.?length",
             "too.?small", "size", "half.*size", "assumes"],
            ["LightProbeGenerator", "fromCubeRenderTarget", "INVALID_OPERATION",
             "not.*written", "zero", "zeroed"],
        ],
        "min_matches": 2,
    },
    "r17_viewport_rendering_with_postprocessing_r": {
        "groups": [
            ["glClear", "clear", "clear.color", "autoClear", "color.?buffer"],
            ["viewport", "scissor", "GL_SCISSOR_TEST", "sub.?region",
             "small.?viewport", "region", "ignore"],
            ["PostProcessing", "post.?process", "framebuffer", "render.?target",
             "separate", "different.*target", "second.*render"],
        ],
        "min_matches": 2,
    },
    "r18_webglrenderer_reversed_depth_not_working": {
        "groups": [
            ["reversed.?z", "reversed.?depth", "reverse.?depth", "GL_GREATER",
             "DEPTH_TEST", "depthFunc"],
            ["clearDepth", "depth.?clear", "clear.*depth", "autoClear",
             "1.0", "0.0", "not.?cleared", "never.?clear"],
            ["PMREMGenerator", "_sceneToCubeUV", "cube.?UV",
             "render.?target", "attachment"],
        ],
        "min_matches": 2,
    },
    "r19_depthtexture_share_source_after_renderta": {
        "groups": [
            ["DepthTexture", "depth.?texture", "Source", "texture.?source",
             "source.image"],
            ["copy", "clone", "share", "alias", "same.*source", "same.*object",
             "reference"],
            ["feedback.?loop", "ping.?pong", "EffectComposer", "both.*framebuffer",
             "attached.*multiple", "shared"],
        ],
        "min_matches": 2,
    },
    "r28_crash_if_using_scene_background_hdr_volu": {
        "groups": [
            ["depth.?stencil", "Depth24Plus", "attachment.?state",
             "attachment.?format"],
            ["mismatch", "expects", "differ", "pipeline.*pass", "pass.*pipeline",
             "bake"],
            ["WebGPU", "background", "scene.background", "HDR", "volumetric",
             "RGBA16Float", "render.?pipeline"],
        ],
        "min_matches": 2,
    },
    "r10_feedback_loop_error_with_transmission_an": {
        "groups": [
            ["feedback.?loop", "INVALID_OPERATION", "framebuffer.*texture",
             "same.*texture.*framebuffer", "bind.*collision"],
            ["transmission", "transmissionSamplerMap", "antialias", "MSAA",
             "multisampl", "samples", "capabilities.samples"],
            ["attachment", "COLOR_ATTACHMENT", "sampler", "DoubleSide",
             "back.?face", "back.?side"],
        ],
        "min_matches": 2,
    },
}

GT = {**GT_R6, **GT_NEW}


def score_diagnosis(scenario: str, text: str) -> tuple[bool, int]:
    spec = GT[scenario]
    lower = text.lower()
    hits = 0
    for group in spec["groups"]:
        for kw in group:
            if re.search(kw.lower(), lower):
                hits += 1
                break
    return hits >= spec.get("min_matches", 2), hits


STATE_COLLISION = {
    "r4_msaa_does_not_always_work_when_doing_rtt",
    "r4_3d_map_black_screen",
    "r7_webglbackend_copytexturetotexture_doesn_",
    "r9_transparent_objects_brighten_when_using_",
    "r13_cubecamera_render_target_displaying_rand",
    "r16_lightprobegenerator_does_not_work_with_e",
    "r17_viewport_rendering_with_postprocessing_r",
    "r18_webglrenderer_reversed_depth_not_working",
    "r19_depthtexture_share_source_after_renderta",
    "r28_crash_if_using_scene_background_hdr_volu",
}
CARRYOVER = {
    "r10_feedback_loop_error_with_transmission_an",
    "r22_point_sprite_rendering_issues_with_three",
    "r25_filters_with_backbuffers_seem_not_to_wor",
    "r30_incomplete_lines_problem_with_mixing_lay",
    "r33_latest_build_6_38_1_got_glitchy_opacity_",
}


def main() -> None:
    rows = []
    for f in sorted(RESULTS_DIR.glob("*_*.jsonl")):
        name = f.stem
        m = re.match(r"^(.*?)_(code_only|with_bhdr)_(haiku|sonnet)$", name)
        if not m:
            continue
        scen, mode, model = m.group(1), m.group(2), m.group(3)
        if scen not in GT:
            continue

        parsed = parse_stream_json(str(f))
        diag = find_json_object(parsed.get("result_text") or "") or {}
        text = json.dumps(diag) + " " + (parsed.get("result_text") or "")
        correct, hits = score_diagnosis(scen, text)

        # Heuristic timeout detection: no final result_text + turns near max
        timed_out = (
            (not parsed.get("result_text"))
            and parsed.get("num_turns", 0) >= 38
        ) or parsed.get("is_error", False)

        rows.append({
            "scenario": scen,
            "mode": mode,
            "model": model,
            "correct": correct,
            "hits": hits,
            "turns": parsed["num_turns"],
            "cost_usd": parsed["total_cost_usd"],
            "tool_counts": parsed["tool_counts"],
            "cache_read": parsed["cache_read"],
            "cache_creation": parsed["cache_creation"],
            "total_output_tokens": parsed["total_tokens_out"],
            "total_input_tokens": parsed["total_tokens_in"],
            "confidence": diag.get("confidence", ""),
            "offending_symbol": diag.get("offending_symbol", ""),
            "root_cause": (diag.get("root_cause", "") or "")[:300],
            "timed_out": timed_out,
            "category": (
                "state_collision" if scen in STATE_COLLISION
                else "carryover" if scen in CARRYOVER
                else "other"
            ),
        })

    (RESULTS_DIR / "scored.json").write_text(json.dumps(rows, indent=2))

    total = len(rows)
    by_cell: dict[tuple[str, str], list[dict]] = {}
    by_scen: dict[str, list[dict]] = {}
    by_cat_cell: dict[tuple[str, str, str], list[dict]] = {}
    total_cost = 0.0
    for r in rows:
        k = (r["mode"], r["model"])
        by_cell.setdefault(k, []).append(r)
        by_scen.setdefault(r["scenario"], []).append(r)
        by_cat_cell.setdefault((r["category"], r["mode"], r["model"]), []).append(r)
        total_cost += r["cost_usd"]

    out = []
    out.append(f"Total runs: {total}  Total cost: ${total_cost:.2f}")

    out.append("\n## Mode x Model Accuracy")
    out.append(f"{'Mode':<12} {'Model':<8} {'N':>3} {'Correct':>8} {'Acc':>7} {'AvgCost':>10} {'AvgTurns':>9} {'Timeout':>8}")
    for (mode, model) in sorted(by_cell):
        rs = by_cell[(mode, model)]
        n = len(rs)
        c = sum(int(r["correct"]) for r in rs)
        to = sum(int(r["timed_out"]) for r in rs)
        avg_cost = sum(r["cost_usd"] for r in rs) / n if n else 0
        avg_turns = sum(r["turns"] for r in rs) / n if n else 0
        out.append(f"{mode:<12} {model:<8} {n:>3} {c:>8} {c/n*100 if n else 0:>6.1f}% "
                   f"${avg_cost:>9.4f} {avg_turns:>9.1f} {to:>8}")

    out.append("\n## Per-Scenario")
    out.append(f"{'scenario':<50} {'co_h':>5} {'co_s':>5} {'gp_h':>5} {'gp_s':>5}")
    for scen in sorted(by_scen):
        d = {(r["mode"], r["model"]): r["correct"] for r in by_scen[scen]}
        co_h = "Y" if d.get(("code_only","haiku")) else "N" if ("code_only","haiku") in d else "-"
        co_s = "Y" if d.get(("code_only","sonnet")) else "N" if ("code_only","sonnet") in d else "-"
        gp_h = "Y" if d.get(("with_bhdr","haiku")) else "N" if ("with_bhdr","haiku") in d else "-"
        gp_s = "Y" if d.get(("with_bhdr","sonnet")) else "N" if ("with_bhdr","sonnet") in d else "-"
        out.append(f"{scen:<50} {co_h:>5} {co_s:>5} {gp_h:>5} {gp_s:>5}")

    out.append("\n## Mean Tool Calls per Run (mode x model)")
    out.append(f"{'Mode':<12} {'Model':<8} {'gpa':>5} {'curl':>5} {'Read':>5} {'Grep':>5} {'Glob':>5} {'Bash':>5}")
    for (mode, model) in sorted(by_cell):
        rs = by_cell[(mode, model)]
        n = max(len(rs), 1)
        s = {k: 0 for k in ("gpa", "curl", "Read", "Grep", "Glob", "Bash")}
        for r in rs:
            for k in s:
                s[k] += int(r["tool_counts"].get(k, 0))
        out.append(f"{mode:<12} {model:<8} "
                   f"{s['gpa']/n:>5.1f} {s['curl']/n:>5.1f} {s['Read']/n:>5.1f} "
                   f"{s['Grep']/n:>5.1f} {s['Glob']/n:>5.1f} {s['Bash']/n:>5.1f}")

    out.append("\n## Paired Deltas (both modes correct) per model")
    for model in ("haiku", "sonnet"):
        paired = []
        for scen, rs in by_scen.items():
            d = {(r["mode"], r["model"]): r for r in rs}
            co = d.get(("code_only", model))
            gp = d.get(("with_bhdr", model))
            if not co or not gp:
                continue
            if not (co["correct"] and gp["correct"]):
                continue
            paired.append({
                "scen": scen,
                "dcost": gp["cost_usd"] - co["cost_usd"],
                "dcache": gp["cache_read"] - co["cache_read"],
                "dout": gp["total_output_tokens"] - co["total_output_tokens"],
                "dturns": gp["turns"] - co["turns"],
            })
        if paired:
            n = len(paired)
            out.append(f"\n  model={model}  N={n} paired scenarios")
            out.append(f"    mean dcost  (gp - co): ${sum(p['dcost'] for p in paired)/n:+.4f}")
            out.append(f"    mean dcache (gp - co): {sum(p['dcache'] for p in paired)/n:+.0f}")
            out.append(f"    mean dout   (gp - co): {sum(p['dout'] for p in paired)/n:+.0f}")
            out.append(f"    mean dturns (gp - co): {sum(p['dturns'] for p in paired)/n:+.1f}")

    # ------------ Subset analysis: state_collision vs carryover ------------
    out.append("\n## Subset: State-Collision vs Carryover Paired Deltas")
    for cat in ("state_collision", "carryover"):
        out.append(f"\n### {cat}")
        for model in ("haiku", "sonnet"):
            paired = []
            for scen, rs in by_scen.items():
                if not rs:
                    continue
                if rs[0]["category"] != cat:
                    continue
                d = {(r["mode"], r["model"]): r for r in rs}
                co = d.get(("code_only", model))
                gp = d.get(("with_bhdr", model))
                if not co or not gp:
                    continue
                if not (co["correct"] and gp["correct"]):
                    continue
                paired.append({
                    "dcost": gp["cost_usd"] - co["cost_usd"],
                    "dcache": gp["cache_read"] - co["cache_read"],
                    "dturns": gp["turns"] - co["turns"],
                })
            if paired:
                n = len(paired)
                out.append(f"  model={model}  N={n}  mean dcost ${sum(p['dcost'] for p in paired)/n:+.4f}"
                           f"  mean dturns {sum(p['dturns'] for p in paired)/n:+.1f}")
            else:
                out.append(f"  model={model}  N=0 (no paired-correct scenarios)")

    # Per-category accuracy
    out.append("\n## Accuracy by Category x Mode x Model")
    out.append(f"{'Cat':<16} {'Mode':<12} {'Model':<8} {'N':>3} {'Correct':>8} {'Acc':>7}")
    for (cat, mode, model) in sorted(by_cat_cell):
        rs = by_cat_cell[(cat, mode, model)]
        n = len(rs)
        c = sum(int(r["correct"]) for r in rs)
        out.append(f"{cat:<16} {mode:<12} {model:<8} {n:>3} {c:>8} {c/n*100 if n else 0:>6.1f}%")

    # Haiku timeout count
    haiku_gp_to = sum(
        1 for r in rows
        if r["model"] == "haiku" and r["mode"] == "with_bhdr" and r["timed_out"]
    )
    haiku_gp_total = sum(
        1 for r in rows
        if r["model"] == "haiku" and r["mode"] == "with_bhdr"
    )
    out.append(f"\n## Haiku with_bhdr timeout count: {haiku_gp_to} / {haiku_gp_total}")

    text = "\n".join(out) + "\n"
    (RESULTS_DIR / "summary.txt").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
