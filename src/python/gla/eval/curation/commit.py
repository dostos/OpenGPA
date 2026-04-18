from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

from gla.eval.curation.coverage_log import CoverageLog, CoverageEntry


def _append_to_build_bazel(eval_dir: Path, scenario_id: str) -> None:
    """No-op shim kept for backward compatibility.

    Scenario directories are now auto-discovered by a ``glob()`` in
    ``tests/eval/BUILD.bazel``, so there is no hardcoded list to maintain.
    This helper is kept (as a no-op) so any callers that still reference
    it continue to work.
    """
    return


def commit_scenario(
    *,
    eval_dir: Path | str,
    scenario_id: str,
    c_source: str,
    md_body: str,
    coverage_log: CoverageLog,
    summary_path: Path | str,
    issue_url: str,
    source_type: str,
    triage_verdict: str,
    fingerprint: Optional[str],
    tier: str,
    predicted_helps: Optional[str],
    observed_helps: Optional[str],
    failure_mode: Optional[str],
    eval_summary: Optional[dict[str, Any]],
) -> None:
    eval_dir = Path(eval_dir)
    scenario_dir = eval_dir / scenario_id
    scenario_dir.mkdir(parents=True, exist_ok=True)
    (scenario_dir / "main.c").write_text(c_source)
    (scenario_dir / "scenario.md").write_text(md_body)
    # BUILD.bazel is now glob-driven — no explicit append needed. The no-op
    # call is retained for backward compatibility with any external callers.
    _append_to_build_bazel(eval_dir, scenario_id)

    coverage_log.append(CoverageEntry(
        issue_url=issue_url,
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        source_type=source_type,
        triage_verdict=triage_verdict,
        root_cause_fingerprint=fingerprint,
        outcome="scenario_committed",
        scenario_id=scenario_id,
        tier=tier,
        rejection_reason=None,
        predicted_helps=predicted_helps,
        observed_helps=observed_helps,
        failure_mode=failure_mode,
        eval_summary=eval_summary,
    ))

    coverage_log.regenerate_summary(summary_path)


def log_rejection(
    *,
    coverage_log: CoverageLog,
    summary_path: Path | str,
    issue_url: str,
    source_type: str,
    triage_verdict: str,
    fingerprint: Optional[str],
    rejection_reason: str,
) -> None:
    coverage_log.append(CoverageEntry(
        issue_url=issue_url,
        reviewed_at=datetime.now(timezone.utc).isoformat(),
        source_type=source_type,
        triage_verdict=triage_verdict,
        root_cause_fingerprint=fingerprint,
        outcome="rejected",
        scenario_id=None,
        tier=None,
        rejection_reason=rejection_reason,
        predicted_helps=None,
        observed_helps=None,
        failure_mode=None,
        eval_summary=None,
    ))
    coverage_log.regenerate_summary(summary_path)
