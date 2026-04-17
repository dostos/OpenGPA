"""Classify observed helpfulness of GLA vs code-only from two EvalResult objects.

6-rule decision table (first match wins):
  Rule 1: correct_with_gla AND NOT correct_code_only  -> yes
  Rule 2: NOT correct_with_gla AND correct_code_only   -> no  (GLA regressed)
  Rule 3: both wrong                                   -> no
  Rule 4: both correct AND ratio < 0.5                 -> yes
  Rule 5: both correct AND ratio > 0.8                 -> no
  Rule 6: both correct AND 0.5 <= ratio <= 0.8         -> ambiguous

Guard: code_only.total_tokens <= 0 -> ambiguous (avoid division by zero).
"""
from __future__ import annotations
from dataclasses import dataclass
from gla.eval.metrics import EvalResult


@dataclass
class ObservedClassification:
    verdict: str   # "yes" | "no" | "ambiguous"
    evidence: str


def classify_observed_helps(
    with_gla: EvalResult, code_only: EvalResult
) -> ObservedClassification:
    """Return an ObservedClassification based on the 6-rule decision table."""
    # Rule 1
    if with_gla.correct_diagnosis and not code_only.correct_diagnosis:
        return ObservedClassification(
            "yes",
            "correct_with_gla=True, correct_code_only=False",
        )
    # Rule 2
    if not with_gla.correct_diagnosis and code_only.correct_diagnosis:
        return ObservedClassification(
            "no",
            "GLA regressed vs code_only",
        )
    # Rule 3: both wrong
    if not with_gla.correct_diagnosis and not code_only.correct_diagnosis:
        return ObservedClassification(
            "no",
            "both modes wrong",
        )
    # Both correct from here — guard against degenerate token count first
    if code_only.total_tokens <= 0:
        return ObservedClassification(
            "ambiguous",
            f"code_only tokens degenerate ({code_only.total_tokens})",
        )
    ratio = with_gla.total_tokens / code_only.total_tokens
    # Rule 4
    if ratio < 0.5:
        return ObservedClassification(
            "yes",
            f"both correct, token_ratio={ratio:.2f} < 0.5",
        )
    # Rule 5
    if ratio > 0.8:
        return ObservedClassification(
            "no",
            f"both correct, token_ratio={ratio:.2f} > 0.8",
        )
    # Rule 6
    return ObservedClassification(
        "ambiguous",
        f"both correct, token_ratio={ratio:.2f} in [0.5, 0.8]",
    )
