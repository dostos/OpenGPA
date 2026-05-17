"""Scoring and reporting metrics for OpenGPA evaluation harness."""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class EvalResult:
    scenario_id: str
    mode: str                  # "with_bhdr" or "code_only"

    diagnosis_text: str        # LLM's diagnosis

    # Efficiency
    input_tokens: int
    output_tokens: int
    total_tokens: int
    tool_calls: int            # 0 for code_only mode
    num_turns: int             # conversation turns
    time_seconds: float        # wall-clock seconds

    # Details
    model: str
    timestamp: str             # ISO-8601

    # Observed-helpfulness (optional, filled by curation pipeline)
    observed_helps: Optional[str] = None
    observed_helps_evidence: Optional[str] = None
    failure_mode: Optional[str] = None
    failure_mode_details: Optional[str] = None

    # Maintainer-framing scorer output (Phase 4).  When the scenario has
    # a `## Fix` section with a scored bug_class, the harness populates
    # these; otherwise they stay None.
    bug_class: Optional[str] = None            # framework-internal | consumer-misuse | user-config | legacy
    maintainer_solved: Optional[bool] = None   # ScoreResult.solved
    file_score: Optional[float] = None         # ScoreResult.file_score
    file_hits: Optional[list] = None           # ScoreResult.file_hits
    file_misses: Optional[list] = None         # ScoreResult.file_misses
    file_extras: Optional[list] = None         # ScoreResult.file_extras
    out_of_tree: Optional[list] = None         # ScoreResult.out_of_tree
    parsed_json: Optional[bool] = None         # True if agent emitted parseable JSON tail

    # ScoreVerdict v2 (file_level + prose + gave-up orchestrator). Stored
    # as a dict for trivial JSON round-tripping. Keys mirror
    # `bhdr.eval.scorer.ScoreVerdict` fields. The primary "is this solved?"
    # signal — `verdict["solved"]` is what the round logs report.
    verdict: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EvalResult":
        # Tolerate legacy result files that still carry correct_diagnosis /
        # correct_fix — drop them silently. R17 deleted those fields and
        # the keyword-based DiagnosisScorer that populated them; the
        # verdict orchestrator (file_level → prose → judge) is the only
        # scoring path now.
        d = {k: v for k, v in d.items() if k not in ("correct_diagnosis", "correct_fix")}
        return cls(**d)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

class ReportGenerator:
    """Generates comparison reports from a list of EvalResult objects."""

    def generate_summary(
        self,
        results: list[EvalResult],
        stable_failure_ids: Optional[set[str]] = None,
    ) -> dict:
        """Aggregate metrics by scenario and mode.

        ``stable_failure_ids`` (R18-P0): scenario IDs whose ``scenario.yaml``
        carries an ``expected_failure`` block. Those scenarios are still
        scored, but the per-mode overall block gets an extra
        ``solved_rate_regression_only`` figure that excludes them, so
        round-over-round comparisons aren't dominated by known-stable
        failures. ``None`` (default) preserves pre-R18 behavior.

        Returns a dict with keys:
            scenarios: dict[scenario_id -> dict[mode -> aggregated_metrics]]
            overall: overall aggregate statistics
            stable_failure_ids: sorted list of stable-failure scenario IDs
                included in the run (subset of ``stable_failure_ids``).
        """
        from collections import defaultdict

        stable = set(stable_failure_ids or ())

        by_scenario: dict[str, dict[str, list[EvalResult]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for r in results:
            by_scenario[r.scenario_id][r.mode].append(r)

        def _avg(values: list) -> Optional[float]:
            return sum(values) / len(values) if values else None

        def _agg(rs: list[EvalResult]) -> dict:
            # solved: derived from the v2 verdict orchestrator's `solved`
            # field, which reflects file_level → prose → judge scoring.
            # Pre-R17 this row was driven by the keyword-based
            # DiagnosisScorer; R17 deleted that scorer in favour of the
            # verdict orchestrator everywhere.
            return {
                "count": len(rs),
                "solved_rate": _avg([
                    int(bool((r.verdict or {}).get("solved"))) for r in rs
                ]),
                "avg_total_tokens": _avg([r.total_tokens for r in rs]),
                "avg_input_tokens": _avg([r.input_tokens for r in rs]),
                "avg_output_tokens": _avg([r.output_tokens for r in rs]),
                "avg_tool_calls": _avg([r.tool_calls for r in rs]),
                "avg_turns": _avg([r.num_turns for r in rs]),
                "avg_time_seconds": _avg([r.time_seconds for r in rs]),
            }

        summary_scenarios: dict[str, dict] = {}
        for sid, modes in sorted(by_scenario.items()):
            summary_scenarios[sid] = {
                mode: _agg(rs) for mode, rs in sorted(modes.items())
            }

        # Overall aggregation per mode
        all_modes: dict[str, list[EvalResult]] = defaultdict(list)
        regression_modes: dict[str, list[EvalResult]] = defaultdict(list)
        for r in results:
            all_modes[r.mode].append(r)
            if r.scenario_id not in stable:
                regression_modes[r.mode].append(r)

        overall: dict[str, dict] = {}
        for mode, rs in sorted(all_modes.items()):
            agg = _agg(rs)
            reg_rs = regression_modes.get(mode, [])
            agg["solved_rate_regression_only"] = _avg(
                [int(bool((r.verdict or {}).get("solved"))) for r in reg_rs]
            )
            agg["regression_count"] = len(reg_rs)
            overall[mode] = agg

        # Token reduction: with_bhdr vs code_only
        token_reduction: Optional[float] = None
        if "with_bhdr" in overall and "code_only" in overall:
            bhdr_tok = overall["with_bhdr"].get("avg_total_tokens") or 0
            base_tok = overall["code_only"].get("avg_total_tokens") or 0
            if base_tok:
                token_reduction = (base_tok - bhdr_tok) / base_tok

        observed_stable = sorted(
            sid for sid in by_scenario if sid in stable
        )

        return {
            "scenarios": summary_scenarios,
            "overall": overall,
            "token_reduction_fraction": token_reduction,
            "stable_failure_ids": observed_stable,
        }

    def generate_markdown(
        self,
        results: list[EvalResult],
        stable_failure_ids: Optional[set[str]] = None,
    ) -> str:
        """Generate a human-readable markdown comparison report."""
        summary = self.generate_summary(results, stable_failure_ids=stable_failure_ids)
        lines: list[str] = []

        lines.append("# OpenGPA Evaluation Report")
        lines.append("")
        lines.append(
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
        lines.append(f"Total results: {len(results)}")
        lines.append("")

        # Overall summary table
        lines.append("## Overall")
        lines.append("")
        overall = summary["overall"]
        modes = sorted(overall.keys())
        headers = ["Metric"] + modes
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        metrics_display = [
            ("avg_total_tokens", "Avg Total Tokens"),
            ("avg_input_tokens", "Avg Input Tokens"),
            ("avg_output_tokens", "Avg Output Tokens"),
            ("avg_tool_calls", "Avg Tool Calls"),
            ("avg_turns", "Avg Turns"),
            ("avg_time_seconds", "Avg Time (s)"),
            ("solved_rate", "Solved (verdict orchestrator)"),
            ("solved_rate_regression_only", "Solved (regression-only)"),
        ]
        for key, label in metrics_display:
            row = [label]
            for mode in modes:
                val = overall.get(mode, {}).get(key)
                if val is None:
                    row.append("—")
                elif isinstance(val, float):
                    row.append(f"{val:.3f}")
                else:
                    row.append(str(val))
            lines.append("| " + " | ".join(row) + " |")

        if summary["token_reduction_fraction"] is not None:
            pct = summary["token_reduction_fraction"] * 100
            lines.append("")
            lines.append(
                f"**Token reduction (with_bhdr vs code_only): {pct:.1f}%**"
            )

        # R18-P0: surface stable-failure scenarios so readers know which
        # IDs are excluded from the regression-only row.
        stable_ids = summary.get("stable_failure_ids") or []
        if stable_ids:
            lines.append("")
            lines.append(
                f"**Stable failures excluded from regression-only row ({len(stable_ids)}):** "
                + ", ".join(f"`{sid}`" for sid in stable_ids)
            )

        lines.append("")

        # Per-scenario breakdown
        lines.append("## Per-Scenario Results")
        lines.append("")

        for sid, modes_data in summary["scenarios"].items():
            lines.append(f"### {sid}")
            lines.append("")
            mode_names = sorted(modes_data.keys())
            headers = ["Metric"] + mode_names
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

            for key, label in metrics_display:
                row = [label]
                for mode in mode_names:
                    val = modes_data.get(mode, {}).get(key)
                    if val is None:
                        row.append("—")
                    elif isinstance(val, float):
                        row.append(f"{val:.3f}")
                    else:
                        row.append(str(val))
                lines.append("| " + " | ".join(row) + " |")
            lines.append("")

        return "\n".join(lines)
