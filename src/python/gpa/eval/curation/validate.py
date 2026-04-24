from __future__ import annotations
import base64
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from gpa.eval.curation.draft import DraftResult
from gpa.eval.curation.prompts import load_prompt
from gpa.eval.curation.signature_matchers import match_signature
from gpa.eval.scenario import ScenarioLoader


# Valid bug_class values per the maintainer-framing spec
# (docs/superpowers/specs/2026-04-21-maintainer-framing-design.md).
_VALID_BUG_CLASSES = frozenset(
    {"framework-internal", "consumer-misuse", "user-config", "legacy"}
)


@dataclass
class ValidationResult:
    ok: bool
    reason: str
    framebuffer_png: Optional[bytes] = None
    metadata: Optional[dict] = None


# Patterns that reveal the diagnosis if present in source files or
# scenario.md's User Report section. These defeat the eval by leaking the
# answer to the agent. See `prompts/draft_core_system.md` and
# `prompts/synth_core_system.md` for the human-facing rules.
_SOURCE_HINT_PATTERNS = [
    r"//\s*BUG\b",
    r"//\s*FIX\b",
    r"//\s*WRONG\b",
    r"//\s*CORRECT\b",
    r"//\s*BUG\s*PATTERN\b",
    r"//\s*buggy\b",
    r"//\s*intentionally\s+(omitted|wrong)",
    r"//\s*should\s+be\b",
    r"//\s*this\s+is\s+the\s+missing",
    r"<--\s*MISSING",
    r"<--\s*the\s+bug",
    r"/\*[^*]*\bBUG\b",
    r"/\*[^*]*\bshould\s+be\b",
]
_SOURCE_HINT_RE = re.compile("|".join(_SOURCE_HINT_PATTERNS), re.IGNORECASE)

# Forbidden runtime-output strings in source files (printf, fprintf,
# window titles, etc.) that announce the diagnosis at runtime. The
# character classes exclude newlines so the match stays inside a single
# string literal — a following comment on another line containing
# `leaked` or `ACNE` is not a runtime leak.
_RUNTIME_LEAK_PATTERNS = [
    r'"\s*bug\s+reproduced\b',
    r'"\s*bug\s+fixed\b',
    r'"\s*verdict\s*:',
    r'"[^"\n]*\bleaked\b[^"\n]*"',
    r'"[^"\n]*\bACNE\s*\([^"\n]*"',
]
_RUNTIME_LEAK_RE = re.compile("|".join(_RUNTIME_LEAK_PATTERNS), re.IGNORECASE)

def check_contamination(scenario_dir: Path) -> Optional[str]:
    """Return a rejection reason string if the scenario leaks its diagnosis
    to the eval agent, else None. Checked against:

    - All source files in the scenario dir (main.c, *.h, *.glsl, *.vert,
      *.frag) — no hint comments, no runtime-output leak strings.
    - scenario.md must have both `## User Report` and `## Ground Truth`
      sections.

    The User Report text itself is NOT checked for "the bug is"-style
    phrases, because real-world issues mined from GitHub legitimately
    include the reporter's own (possibly partial or wrong) hypothesis.
    Matching how real bug reports read is the point of the eval.
    """
    # Source-file checks
    for ext in (".c", ".h", ".glsl", ".vert", ".frag"):
        for src in scenario_dir.rglob(f"*{ext}"):
            try:
                text = src.read_text()
            except (OSError, UnicodeDecodeError):
                continue
            m = _SOURCE_HINT_RE.search(text)
            if m:
                return (
                    f"source file {src.name} contains hint comment "
                    f"matching pattern '{m.group(0)}' (line "
                    f"{text[:m.start()].count(chr(10)) + 1})"
                )
            m = _RUNTIME_LEAK_RE.search(text)
            if m:
                return (
                    f"source file {src.name} contains runtime-output leak "
                    f"string '{m.group(0)}' (line "
                    f"{text[:m.start()].count(chr(10)) + 1})"
                )

    # scenario.md structural checks
    md_path = scenario_dir / "scenario.md"
    if not md_path.exists():
        return "scenario.md missing"
    md_text = md_path.read_text()

    # Must have both sections. User Report content itself is not policed —
    # real issue reporters often guess at the cause, and exposing that
    # guess to the eval agent is realistic.
    if not re.search(r"^##\s+User Report\s*$", md_text, re.MULTILINE):
        return "scenario.md missing `## User Report` section"
    if not re.search(r"^##\s+Ground Truth\s*$", md_text, re.MULTILINE):
        return "scenario.md missing `## Ground Truth` section"

    # `## Fix` section is required on newly-drafted scenarios per the
    # maintainer-framing spec (Phase 1).  This check runs from the
    # curation Validator only; the scenario loader does NOT call
    # check_contamination, so the 94+ pre-existing on-disk scenarios
    # without a `## Fix` section continue to load normally.
    fix_reason = _check_fix_section(md_text)
    if fix_reason is not None:
        return fix_reason

    return None


def _check_fix_section(md_text: str) -> Optional[str]:
    """Return a rejection-reason string if the scenario.md is missing a
    well-formed `## Fix` section, else None.

    Rules (matching the maintainer-framing spec, Phase 1):
      - Section heading `## Fix` must be present.
      - Section body must contain a ```yaml ... ``` fenced block.
      - YAML must parse as a mapping with fix_pr_url and bug_class.
      - bug_class must be one of the valid values.
      - For non-legacy bug_class, `files` must be a non-empty list.
      - `bug_class: legacy` with an empty files list is allowed (explicit
        retrofit escape hatch).
    """
    if not re.search(r"^##\s+Fix\s*$", md_text, re.MULTILINE):
        return "missing_fix_section"

    # Extract the `## Fix` section body, bounded by the next `## ` heading
    # or end of file.
    m = re.search(
        r"^##\s+Fix\s*\n(.+?)(?=\n##\s+|\Z)",
        md_text, re.MULTILINE | re.DOTALL,
    )
    if not m:
        # Heading at the very end of the file with no body.
        return "fix_section_empty"

    section_body = m.group(1)

    yaml_m = re.search(r"```yaml\s*\n(.+?)\n```", section_body, re.DOTALL)
    if not yaml_m:
        return "fix_section_missing_yaml_block"

    try:
        data = yaml.safe_load(yaml_m.group(1))
    except yaml.YAMLError as e:
        return f"fix_section_yaml_parse_error: {e}"

    if not isinstance(data, dict):
        return "fix_section_yaml_not_mapping"

    if not data.get("fix_pr_url"):
        return "fix_section_missing_fix_pr_url"

    bug_class = data.get("bug_class")
    if not bug_class:
        return "fix_section_missing_bug_class"
    if bug_class not in _VALID_BUG_CLASSES:
        return f"fix_section_invalid_bug_class: {bug_class!r}"

    files_raw = data.get("files")
    files: list = []
    if isinstance(files_raw, list):
        files = [f for f in files_raw if f is not None and str(f).strip()]

    # Empty files permitted iff bug_class is the explicit legacy marker.
    if not files and bug_class != "legacy":
        return "fix_section_files_empty"

    return None


class Validator:
    """Builds, runs, and validates a drafted scenario."""

    def __init__(self, eval_dir: Path | str, runner: Any, llm_fallback: Any = None):
        self.eval_dir = Path(eval_dir)
        self.eval_dir.mkdir(parents=True, exist_ok=True)
        self._runner = runner  # must expose build_and_capture(scenario_id) -> dict
        self._llm_fallback = llm_fallback

    def validate(self, draft: DraftResult) -> ValidationResult:
        # Write artifacts into eval dir, then validate. On failure, clean up
        # so failed drafts don't pollute tests/eval/.
        scenario_dir = self.eval_dir / draft.scenario_id

        # Safety: require the scenario dir to not pre-exist so we can safely
        # rmtree it on failure without clobbering unrelated content.
        if scenario_dir.exists():
            return ValidationResult(
                ok=False,
                reason="scenario dir already exists",
            )

        scenario_dir.mkdir(parents=True, exist_ok=True)
        for filename, content in draft.files.items():
            file_path = scenario_dir / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)

        result = self._validate_inner(draft, scenario_dir)

        if not result.ok:
            # Remove the entire freshly-created scenario directory.
            shutil.rmtree(scenario_dir, ignore_errors=True)

        return result

    def _validate_inner(
        self, draft: DraftResult, scenario_dir: Path
    ) -> ValidationResult:
        # Contamination check runs before anything else — a scenario that
        # leaks its diagnosis to the agent is unusable regardless of whether
        # it builds and captures correctly. Reject early and cheaply.
        contamination_reason = check_contamination(scenario_dir)
        if contamination_reason:
            return ValidationResult(
                ok=False, reason=f"contamination: {contamination_reason}"
            )

        # Parse the md for the signature
        try:
            scenario = ScenarioLoader(eval_dir=str(self.eval_dir)).load(draft.scenario_id)
        except Exception as e:
            return ValidationResult(ok=False, reason=f"scenario parse failed: {e}")
        if not scenario.bug_signature:
            return ValidationResult(ok=False, reason="scenario missing Bug Signature")

        # Build and run
        try:
            capture = self._runner.build_and_capture(draft.scenario_id)
        except Exception as e:
            return ValidationResult(ok=False, reason=f"build/run failed: {e}")

        fb = capture.get("framebuffer_png")
        meta = capture.get("metadata") or {}
        if not fb:
            return ValidationResult(ok=False, reason="no framebuffer captured")

        # Signature match
        m = match_signature(fb, scenario.bug_signature, metadata=meta)
        if m.matched:
            return ValidationResult(ok=True, reason="signature matched",
                                    framebuffer_png=fb, metadata=meta)
        if m.ambiguous and self._llm_fallback:
            judge = self._ask_llm(draft.md_body, fb)
            if judge:
                return ValidationResult(
                    ok=True,
                    reason="LLM fallback confirmed match",
                    framebuffer_png=fb, metadata=meta,
                )
            return ValidationResult(
                ok=False,
                reason="LLM fallback rejected match",
                framebuffer_png=fb, metadata=meta,
            )
        if m.ambiguous:
            return ValidationResult(ok=False,
                reason=f"signature ambiguous (no fallback): {m.reason}",
                framebuffer_png=fb, metadata=meta)
        return ValidationResult(ok=False, reason=f"signature did not match: {m.reason}",
                                framebuffer_png=fb, metadata=meta)

    def _ask_llm(self, md_body: str, fb_png: bytes) -> bool:
        sys = load_prompt("symptom_match_fallback_system")
        b64 = base64.b64encode(fb_png).decode()
        content = [
            {"type": "text", "text": f"Scenario:\n{md_body}"},
            {"type": "image", "source": {"type": "base64",
                "media_type": "image/png", "data": b64}},
        ]
        resp = self._llm_fallback.complete(
            system=sys,
            messages=[{"role": "user", "content": content}])
        m = re.search(r"```json\s*\n(.+?)\n```", resp.text, re.DOTALL)
        raw = m.group(1) if m else resp.text
        try:
            return bool(json.loads(raw).get("matches"))
        except (json.JSONDecodeError, AttributeError):
            return False
