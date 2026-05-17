#!/usr/bin/env python3
"""Score Round 7 eval outputs.

Ingests each ``<scenario>_<mode>_<model>.jsonl`` transcript, parses it with
the stream-json parser, extracts the final diagnosis JSON, and scores
correctness against the Round 5/6 keyword table.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/jingyulee/gh/gla/src/python")
from gpa.eval.telemetry import parse_stream_json

RESULTS_DIR = Path("/tmp/eval_round7")

# Reuse the Round 6 ground-truth table verbatim (same 20 scenarios).
GT_SOURCE = Path("/tmp/eval_round6/score.py").read_text()
# Pull GT dict via exec
_ns: dict = {}
exec(GT_SOURCE, _ns)
GT = _ns["GT"]
find_json_object = _ns["find_json_object"]


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
        })

    (RESULTS_DIR / "scored.json").write_text(json.dumps(rows, indent=2))

    # ---------------- Summary ----------------
    total = len(rows)
    by_cell: dict[tuple[str, str], list[dict]] = {}
    by_scen: dict[str, list[dict]] = {}
    total_cost = 0.0
    for r in rows:
        k = (r["mode"], r["model"])
        by_cell.setdefault(k, []).append(r)
        by_scen.setdefault(r["scenario"], []).append(r)
        total_cost += r["cost_usd"]

    out = []
    out.append(f"Total runs: {total}  Total cost: ${total_cost:.2f}")

    out.append("\n## Mode x Model Accuracy")
    out.append(f"{'Mode':<12} {'Model':<8} {'N':>3} {'Correct':>8} {'Acc':>7} {'AvgCost':>10} {'AvgTurns':>9} {'AvgCacheRd':>12} {'AvgOutTok':>11}")
    for (mode, model) in sorted(by_cell):
        rs = by_cell[(mode, model)]
        n = len(rs)
        c = sum(int(r["correct"]) for r in rs)
        avg_cost = sum(r["cost_usd"] for r in rs) / n if n else 0
        avg_turns = sum(r["turns"] for r in rs) / n if n else 0
        avg_cache = sum(r["cache_read"] for r in rs) / n if n else 0
        avg_out = sum(r["total_output_tokens"] for r in rs) / n if n else 0
        out.append(f"{mode:<12} {model:<8} {n:>3} {c:>8} {c/n*100 if n else 0:>6.1f}% "
                   f"${avg_cost:>9.4f} {avg_turns:>9.1f} {avg_cache:>12.0f} {avg_out:>11.0f}")

    out.append("\n## Per-Scenario")
    out.append(f"{'scenario':<50} {'co_h':>5} {'co_s':>5} {'gp_h':>5} {'gp_s':>5}")
    for scen in sorted(by_scen):
        d = {(r["mode"], r["model"]): r["correct"] for r in by_scen[scen]}
        co_h = "Y" if d.get(("code_only","haiku")) else "N" if ("code_only","haiku") in d else "-"
        co_s = "Y" if d.get(("code_only","sonnet")) else "N" if ("code_only","sonnet") in d else "-"
        gp_h = "Y" if d.get(("with_bhdr","haiku")) else "N" if ("with_bhdr","haiku") in d else "-"
        gp_s = "Y" if d.get(("with_bhdr","sonnet")) else "N" if ("with_bhdr","sonnet") in d else "-"
        out.append(f"{scen:<50} {co_h:>5} {co_s:>5} {gp_h:>5} {gp_s:>5}")

    # -------- Tool counts per cell --------
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

    # -------- Paired deltas (both correct) --------
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

    text = "\n".join(out) + "\n"
    (RESULTS_DIR / "summary.txt").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
