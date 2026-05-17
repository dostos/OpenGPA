"""Prompt templates for the eval harness agent.

Prompts are plain Markdown files so they're easy to review in a PR and
easy to diff across rounds.  :func:`load_prompt` reads a named template
and returns its text; :func:`render_maintainer_prompt` does the simple
``{placeholder}`` substitution required by the maintainer-framing
prompt.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Return the raw text of ``{name}.md`` from this package."""
    return (_DIR / f"{name}.md").read_text(encoding="utf-8")


def render_prompt(
    template_name: str,
    framework: str,
    user_report: str,
    upstream_snapshot_repo: Optional[str],
    upstream_snapshot_sha: Optional[str],
    mode: str = "code_only",
    scope_hint: Optional[str] = None,
    fix_files_count: Optional[int] = None,
) -> str:
    """Render a bug-class prompt template for a scenario.

    R18-P1 (2026-05-14): unified what used to be three near-identical
    rendering helpers (maintainer / advisor / config_advice). All three
    templates share the same ``{framework}`` / ``{user_report}`` /
    ``{upstream_snapshot.*}`` / ``{scope_hint_block}`` placeholders and
    the same ``<!-- WITH_BHDR_ONLY -->`` gating block; the differences
    live entirely in the role intro, task body, and output JSON schema.

    R19-P0 (2026-05-17): added ``fix_files_count`` to tier the depth
    language. R17→R18 traded +1 solved for 4× tokens because the
    blanket "5-15 files / 13-file refactor" framing over-steered
    single-file scenarios. The depth section is now sized to the
    canonical fix's actual file count.

    Args:
      template_name: Bare name of the .md file under this package, e.g.
        ``"maintainer_framing"``, ``"advisor"``, ``"config_advice"``.
      framework: e.g. ``"three.js"`` or the scenario's framework field.
        Falls back to ``"the framework"`` when empty or unknown.
      user_report: The verbatim issue body from the scenario.
      upstream_snapshot_repo: Repo URL of the framework at the pre-fix SHA.
      upstream_snapshot_sha: The pre-fix parent SHA.
      mode: ``"with_bhdr"`` or ``"code_only"`` — controls whether the
        Beholder tool block is included.
      scope_hint: Optional pre-computed scope-hint text from
        :func:`bhdr.eval.scope_hint.compute_scope_hint`. When provided,
        the ``{scope_hint_block}`` placeholder is filled with a short
        section telling the agent the size+area of the canonical fix.
        When None, the placeholder is dropped.
      fix_files_count: Number of files in the canonical fix. Drives the
        ``{depth_section}`` placeholder: 0/None → moderate default,
        1-2 → focused single/few-file, 3-9 → moderate refactor,
        10+ → deep cross-module refactor framing. The count is
        derived from ``ScenarioMetadata.fix.files`` and is *not* the
        scope_hint string — they're independent calibrations.

    Returns:
      The fully-rendered prompt text.
    """
    template = load_prompt(template_name)
    fw = framework or "the framework"
    repo = upstream_snapshot_repo or "(no snapshot repo configured)"
    sha = upstream_snapshot_sha or "HEAD"

    # Strip the ``<!-- WITH_BHDR_ONLY -->`` gated block for code_only mode.
    # The template uses HTML comments so we can handle the substitution
    # deterministically without a full templating engine.
    if mode == "with_bhdr":
        template = template.replace("<!-- WITH_BHDR_ONLY -->", "").replace(
            "<!-- END_WITH_BHDR_ONLY -->", ""
        )
    else:
        import re as _re
        template = _re.sub(
            r"<!-- WITH_BHDR_ONLY -->.*?<!-- END_WITH_BHDR_ONLY -->\n?",
            "",
            template,
            flags=_re.DOTALL,
        )

    return (
        template
        .replace("{framework}", fw)
        .replace("{user_report}", (user_report or "").strip())
        .replace("{upstream_snapshot.repo}", repo)
        .replace("{upstream_snapshot.sha}", sha)
        .replace("{scope_hint_block}", _build_scope_hint_block(scope_hint))
        .replace("{depth_section}", _build_depth_section(fix_files_count))
    )


def render_maintainer_prompt(
    framework: str,
    user_report: str,
    upstream_snapshot_repo: Optional[str],
    upstream_snapshot_sha: Optional[str],
    mode: str = "code_only",
    scope_hint: Optional[str] = None,
    fix_files_count: Optional[int] = None,
) -> str:
    """Render the maintainer-framing prompt. Thin alias over :func:`render_prompt`."""
    return render_prompt(
        "maintainer_framing",
        framework=framework,
        user_report=user_report,
        upstream_snapshot_repo=upstream_snapshot_repo,
        upstream_snapshot_sha=upstream_snapshot_sha,
        mode=mode,
        scope_hint=scope_hint,
        fix_files_count=fix_files_count,
    )


def _build_depth_section(fix_files_count: Optional[int]) -> str:
    """Render the depth-of-investigation paragraph for the maintainer prompt.

    Three tiers, calibrated to R18 forensic findings:

      * 1-2 files (single / focused): the canonical fix is a pointed
        edit. Investigate deeply within those candidate files; don't
        sprawl across the codebase. Cite the smallest set of files
        that explains the bug.
      * 3-9 files (moderate refactor): a typical surrounding-area fix.
        Trace the call chain; the answer often spans a render-pass
        helper + its callers.
      * 10+ files (deep refactor): cross-module work. The R18-era
        framing applies — name every file the canonical fix touches;
        single-file proposals will score below threshold.

    None or 0 → moderate default (we don't know the scope, so play it
    middle-of-the-road).
    """
    n = fix_files_count or 0
    if 1 <= n <= 2:
        return (
            "The canonical fix is small — likely 1-2 files. Investigate\n"
            "the most likely candidate files thoroughly; the right answer\n"
            "is a pointed edit, not a sprawling refactor. Cite the minimal\n"
            "file set that explains the bug; proposing 5+ files when the\n"
            "fix is 1 will dilute your score, not improve it."
        )
    if n >= 10:
        return (
            "Maintainer-class scenarios in this size class genuinely need\n"
            "extensive investigation — the canonical fix touches 10+\n"
            "files (renderer + shader + storage + headers). Naming only\n"
            "the most obvious file misses the surrounding refactor and\n"
            "the harness will score you below threshold. Don't\n"
            "artificially short-circuit; do enough work to identify\n"
            "every file that should be touched."
        )
    # 0 (unknown) or 3-9: moderate framing.
    return (
        "Locate the bug. Cite the framework files involved in the fix —\n"
        "bugs in this domain typically span a render-pass helper plus a\n"
        "small number of callers / shaders / storage headers. Be\n"
        "thorough but proportional; naming only the most obvious file\n"
        "may miss the surrounding edits."
    )


def _build_scope_hint_block(scope_hint: Optional[str]) -> str:
    """Inline section the agent sees when a scope hint is available.

    Empty string when no hint — the placeholder collapses to nothing
    so the prompt stays clean. The hint is framed as calibration, not
    as the answer: the agent still has to find the specific files.
    """
    if not scope_hint or not scope_hint.strip():
        return ""
    return (
        "\n# Scope hint\n\n"
        f"The canonical fix has scope: **{scope_hint.strip()}**\n\n"
        "Use this to calibrate where to look — it tells you the size "
        "and area of the fix, not the specific files. Don't propose "
        "fixes outside this scope unless you find compelling evidence "
        "that the canonical fix missed something.\n"
    )


__all__ = [
    "load_prompt",
    "render_prompt",
    "render_maintainer_prompt",
]
