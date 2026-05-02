from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any
import re as _re

from gpa.eval.curation.coverage_log import CoverageLog, CoverageEntry
from gpa.eval.scenario_metadata import (
    Scenario, Source, Taxonomy, Backend, dump_scenario_yaml,
)
from gpa.eval.curation.draft import compute_scenario_dir


_BUILD_BAZEL_TEMPLATE = '''load("@rules_cc//cc:defs.bzl", "cc_binary")

cc_binary(
    name = "{name}",
    srcs = glob(["*.c"]),
    copts = [
        "-g",
        "-gdwarf-4",
        "-fno-omit-frame-pointer",
        "-O0",
    ],
    linkopts = ["-lGL", "-lX11", "-lm"],
    visibility = ["//visibility:public"],
)
'''


def _append_to_build_bazel(scenario_dir: Path, scenario_id: str) -> None:
    """Write a per-leaf BUILD.bazel when *.c files exist in the scenario dir.

    The old top-level BUILD.bazel append is gone (glob-driven). This helper
    now writes a per-leaf BUILD.bazel alongside scenario source files.
    """
    if any(scenario_dir.glob("*.c")):
        (scenario_dir / "BUILD.bazel").write_text(
            _BUILD_BAZEL_TEMPLATE.format(name=scenario_id)
        )


_ROUND_RE = _re.compile(r"^r([0-9a-f]{1,8})_")


def _extract_round(scenario_id: str) -> str:
    """Extract the round prefix (e.g. 'r96fdc7') from a scenario_id."""
    m = _ROUND_RE.match(scenario_id)
    if m:
        return f"r{m.group(1)}"
    return "unknown"


def _tier_to_bug_class(tier: str) -> str:
    """Map a tier/taxonomy_cell string to a valid bug_class."""
    # tier may be a taxonomy_cell like "native-engine.godot" or a plain
    # bug-class hint.
    _MAP = {
        "framework_internal": "framework-internal",
        "framework-internal": "framework-internal",
        "consumer_misuse": "consumer-misuse",
        "consumer-misuse": "consumer-misuse",
        "user_config": "user-config",
        "user-config": "user-config",
        "synthetic": "synthetic",
    }
    # Strip off category.framework prefix if present (e.g. "native-engine.godot")
    if "." in tier:
        return "unknown"
    return _MAP.get(tier, "unknown")


def _source_type_to_meta(source_type: str, issue_url: str) -> Source:
    """Build a Source dataclass from source_type + issue_url."""
    gh_m = _re.search(r"github\.com/([^/]+)/([^/]+)/(issues|pull)/(\d+)", issue_url or "")
    so_m = _re.search(r"stackoverflow\.com/questions/(\d+)", issue_url or "")
    if gh_m:
        org, repo, kind, num = gh_m.groups()
        return Source(
            type="github_issue" if kind == "issues" else "github_pull",
            url=issue_url,
            repo=f"{org}/{repo}",
            issue_id=int(num),
        )
    if so_m:
        return Source(type="stackoverflow", url=issue_url, issue_id=so_m.group(1))
    if source_type in ("issue", "github_issue"):
        return Source(type="github_issue", url=issue_url or None)
    if source_type in ("pull", "github_pull"):
        return Source(type="github_pull", url=issue_url or None)
    return Source(type="legacy", url=issue_url or None)


def commit_scenario(
    *,
    eval_dir: Path | str,
    scenario_id: str,
    files: Optional[dict[str, str]] = None,
    c_source: Optional[str] = None,   # deprecated: use files
    md_body: Optional[str] = None,    # deprecated: use files
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
    category: Optional[str] = None,
    framework: Optional[str] = None,
) -> None:
    if category is None or framework is None:
        raise ValueError(
            "commit_scenario requires non-None category and framework"
        )

    # Backward-compat: if files is None, build from c_source + md_body.
    if files is None:
        if c_source is None or md_body is None:
            raise ValueError(
                "commit_scenario requires either `files` or both `c_source` and `md_body`"
            )
        files = {"main.c": c_source, "scenario.md": md_body}

    eval_dir = Path(eval_dir)
    scenario_dir = compute_scenario_dir(eval_dir, category, framework, scenario_id)
    scenario_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        file_path = scenario_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

    # Write per-leaf BUILD.bazel when C sources are present.
    _append_to_build_bazel(scenario_dir, scenario_id)

    # Write scenario.yaml sidecar.
    round_id = _extract_round(scenario_id)
    source = _source_type_to_meta(source_type, issue_url)
    bug_class = _tier_to_bug_class(tier)
    scenario_obj = Scenario(
        path=scenario_dir,
        slug=scenario_id,
        round=round_id,
        mined_at=datetime.now(timezone.utc).isoformat(),
        source=source,
        taxonomy=Taxonomy(category=category, framework=framework, bug_class=bug_class),
        backend=Backend(),
        status="drafted",
    )
    dump_scenario_yaml(scenario_obj, scenario_dir / "scenario.yaml")

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
