#!/usr/bin/env python3
"""
Multi-model eval runner for Beholder.

Tests each scenario across model tiers (haiku/sonnet/opus) in both modes
(code-only / with-gpa). Measures accuracy, tokens, and tool usage patterns.

Usage:
    # With Anthropic API key:
    ANTHROPIC_API_KEY=sk-... python scripts/run-multi-model-eval.py

    # With Claude Code (dispatches subagents):
    # See docs for Claude Code integration

    # Dry run (no API calls, just list scenarios):
    python scripts/run-multi-model-eval.py --dry-run
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).parent.parent
EVAL_DIR = REPO / "tests" / "eval"
RESULTS_DIR = REPO / "docs" / "eval-runs"


@dataclass
class EvalRun:
    scenario: str
    model: str          # haiku, sonnet, opus
    mode: str           # code_only, with_bhdr
    correct: Optional[bool] = None
    diagnosis: str = ""
    fix: str = ""
    confidence: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    tool_calls: int = 0
    tool_sequence: list = field(default_factory=list)
    pixel_queries: int = 0
    state_queries: int = 0
    framebuffer_first: bool = False
    time_seconds: float = 0.0
    error: str = ""


def discover_scenarios() -> list[dict]:
    """Find all eval scenarios with their .c and .md files."""
    scenarios = []
    for c_file in sorted(EVAL_DIR.glob("*.c")):
        name = c_file.stem
        md_file = EVAL_DIR / f"{name}.md"
        scenarios.append({
            "name": name,
            "source": str(c_file),
            "description": str(md_file) if md_file.exists() else None,
            "has_description": md_file.exists(),
        })
    return scenarios


def load_ground_truth(scenario_name: str) -> dict:
    """Load ground truth from .md file for scoring."""
    md_file = EVAL_DIR / f"{scenario_name}.md"
    if not md_file.exists():
        return {"keywords": [], "root_cause": "unknown"}

    text = md_file.read_text()
    # Extract key concepts for keyword matching
    keywords = []
    for line in text.split("\n"):
        line_lower = line.lower()
        # Look for root cause indicators
        if any(w in line_lower for w in ["root cause", "bug", "diagnosis", "fix"]):
            words = line.split()
            keywords.extend(w.lower().strip(".,;:()") for w in words if len(w) > 3)

    return {"keywords": list(set(keywords)), "text": text}


def score_diagnosis(diagnosis: str, ground_truth: dict) -> bool:
    """Score whether a diagnosis matches ground truth using keyword overlap."""
    if not diagnosis or not ground_truth.get("keywords"):
        return False

    diag_lower = diagnosis.lower()
    matched = sum(1 for kw in ground_truth["keywords"] if kw in diag_lower)
    total = len(ground_truth["keywords"])

    # Require at least 20% keyword overlap
    return (matched / max(total, 1)) >= 0.2


def print_summary(results: list[EvalRun]):
    """Print a summary table of results."""
    print("\n" + "=" * 100)
    print("MULTI-MODEL EVAL RESULTS")
    print("=" * 100)

    # Group by model
    models = sorted(set(r.model for r in results))
    modes = ["code_only", "with_bhdr"]

    # Accuracy table
    print(f"\n{'Scenario':<45} ", end="")
    for model in models:
        print(f"| {model:^20} ", end="")
    print()

    print(f"{'':45} ", end="")
    for model in models:
        print(f"| {'code':>8} {'gpa':>8}   ", end="")
    print()

    print("-" * (45 + 23 * len(models)))

    scenarios = sorted(set(r.scenario for r in results))
    for scenario in scenarios:
        print(f"{scenario:<45} ", end="")
        for model in models:
            for mode in modes:
                runs = [r for r in results if r.scenario == scenario
                        and r.model == model and r.mode == mode]
                if runs:
                    r = runs[0]
                    mark = "OK" if r.correct else "FAIL" if r.correct is False else "?"
                    print(f"  {mark:>6}", end="")
                else:
                    print(f"  {'--':>6}", end="")
            print("   ", end="")
        print()

    # Token comparison
    print(f"\n{'TOKENS (avg per scenario)':<45} ", end="")
    for model in models:
        print(f"| {model:^20} ", end="")
    print()
    print("-" * (45 + 23 * len(models)))

    for mode in modes:
        mode_results = [r for r in results if r.mode == mode]
        print(f"  {mode:<43} ", end="")
        for model in models:
            model_runs = [r for r in mode_results if r.model == model]
            if model_runs:
                avg_tokens = sum(r.total_tokens for r in model_runs) / len(model_runs)
                print(f"| {avg_tokens:>18.0f}   ", end="")
            else:
                print(f"| {'--':>18}   ", end="")
        print()

    # Framebuffer trap analysis
    bhdr_runs = [r for r in results if r.mode == "with_bhdr"]
    if bhdr_runs:
        fb_first_count = sum(1 for r in bhdr_runs if r.framebuffer_first)
        total_gla = len(bhdr_runs)
        print(f"\nFramebuffer trap: {fb_first_count}/{total_gla} GPA runs queried pixels before state inspection")

    # Failure analysis
    failures = [r for r in results if r.correct is False]
    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for r in failures:
            print(f"  {r.scenario} [{r.model}/{r.mode}]: {r.diagnosis[:80]}...")


def main():
    parser = argparse.ArgumentParser(description="Beholder Multi-Model Eval")
    parser.add_argument("--dry-run", action="store_true", help="List scenarios without running")
    parser.add_argument("--models", nargs="+", default=["haiku", "sonnet"],
                        help="Models to test (haiku, sonnet, opus)")
    parser.add_argument("--scenarios", nargs="+", help="Specific scenarios to run")
    parser.add_argument("--output", default=None, help="Output JSON file")
    args = parser.parse_args()

    scenarios = discover_scenarios()
    if args.scenarios:
        scenarios = [s for s in scenarios if s["name"] in args.scenarios]

    print(f"Found {len(scenarios)} scenarios")
    for s in scenarios:
        desc = "+" if s["has_description"] else "-"
        print(f"  {desc} {s['name']}")

    if args.dry_run:
        print("\nDry run — no eval executed.")
        return

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\nNo ANTHROPIC_API_KEY set.")
        print("For Claude Code eval, dispatch subagents per scenario instead.")
        print("See docs/eval-results.md for the subagent methodology.")
        return

    # Import eval agent
    sys.path.insert(0, str(REPO / "src" / "python"))
    from bhdr.eval.llm_agent import EvalAgent, BhdrToolExecutor

    results = []

    for scenario in scenarios:
        source_code = Path(scenario["source"]).read_text()
        description = ""
        if scenario["description"]:
            description = Path(scenario["description"]).read_text()

        ground_truth = load_ground_truth(scenario["name"])

        for model_tier in args.models:
            model_id = {
                "haiku": "claude-haiku-4-5-20251001",
                "sonnet": "claude-sonnet-4-20250514",
                "opus": "claude-opus-4-20250514",
            }.get(model_tier, model_tier)

            for mode in ["code_only", "with_bhdr"]:
                print(f"\n--- {scenario['name']} | {model_tier} | {mode} ---")

                run = EvalRun(
                    scenario=scenario["name"],
                    model=model_tier,
                    mode=mode,
                )

                try:
                    agent = EvalAgent(model=model_id, max_turns=15)

                    problem_desc = f"Problem: {description[:500]}" if description else "A rendering bug."

                    if mode == "with_bhdr":
                        # Need frame_id — check if captured
                        # For now, use frame_id=0 as placeholder
                        executor = BhdrToolExecutor(
                            base_url="http://127.0.0.1:18080",
                            token=os.environ.get("BHDR_TOKEN", "eval-test"),
                            frame_id=0,
                        )
                        result = agent.run_with_bhdr(
                            scenario_description=problem_desc,
                            source_code=source_code,
                            source_path=scenario["source"],
                            tool_executor=executor,
                        )
                    else:
                        result = agent.run_code_only(
                            scenario_description=problem_desc,
                            source_code=source_code,
                            source_path=scenario["source"],
                        )

                    run.diagnosis = result.diagnosis
                    run.input_tokens = result.input_tokens
                    run.output_tokens = result.output_tokens
                    run.total_tokens = result.total_tokens
                    run.tool_calls = result.tool_calls
                    run.tool_sequence = result.tool_sequence
                    run.pixel_queries = result.pixel_queries
                    run.state_queries = result.state_queries
                    run.framebuffer_first = result.framebuffer_first
                    run.time_seconds = result.time_seconds
                    run.correct = score_diagnosis(result.diagnosis, ground_truth)

                    print(f"  Tokens: {run.total_tokens}, Correct: {run.correct}")

                except Exception as ex:
                    run.error = str(ex)
                    print(f"  ERROR: {ex}")

                results.append(run)

    # Print summary
    print_summary(results)

    # Save results
    output = args.output or str(RESULTS_DIR / f"eval-{int(time.time())}.json")
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)
    print(f"\nResults saved to {output}")


if __name__ == "__main__":
    main()
