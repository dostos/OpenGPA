from __future__ import annotations
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

from gla.eval.curation.coverage_log import CoverageLog, CoverageEntry


_BUILD_LIST_RE = re.compile(
    r"(for\s+name\s+in\s+\[)([^\]]*)(\])",
    re.DOTALL,
)


def _append_to_build_bazel(eval_dir: Path, scenario_id: str) -> None:
    """Append scenario_id to the hardcoded list in tests/eval/BUILD.bazel, if present.

    Idempotent: skip if scenario_id already appears in the list.
    If BUILD.bazel uses glob() (no hardcoded list), this is a no-op.
    """
    build_path = eval_dir / "BUILD.bazel"
    if not build_path.exists():
        return
    text = build_path.read_text()
    m = _BUILD_LIST_RE.search(text)
    if not m:
        # BUILD.bazel doesn't use the expected pattern; leave it alone
        return
    body = m.group(2)
    if f'"{scenario_id}"' in body:
        return  # already present
    # Preserve trailing newline-indent style of the existing list. Detect the
    # indent from the last non-empty entry line.
    lines = body.rstrip().split("\n")
    last_line = lines[-1] if lines else ""
    indent_match = re.match(r"(\s*)", last_line)
    indent = indent_match.group(1) if indent_match else "    "
    new_entry = f'\n{indent}"{scenario_id}",'
    new_body = body.rstrip() + new_entry + "\n"
    new_text = text[:m.start(2)] + new_body + text[m.end(2):]
    build_path.write_text(new_text)


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
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / f"{scenario_id}.c").write_text(c_source)
    (eval_dir / f"{scenario_id}.md").write_text(md_body)
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
