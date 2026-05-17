from __future__ import annotations
import re
from pathlib import Path
from typing import Optional

import yaml

from bhdr.eval.curation.llm_client import LLMClient
from bhdr.eval.curation.prompts import load_prompt
from bhdr.eval.curation.triage import IssueThread, TriageResult


_FILENAME_MARKER_RE = re.compile(r"<!--\s*filename:\s*([^\s]+)\s*-->", re.IGNORECASE)
# Explicit drafter-rejection marker. The drafter prompt instructs the LLM to
# emit this as a top-level HTML comment when a candidate fundamentally cannot
# be drafted (not portable to C, not portable to snapshot, etc.). The reason
# is a slug like `not_portable_to_c_or_snapshot` or `not_a_rendering_bug`.
_DRAFT_ERROR_MARKER_RE = re.compile(
    r"<!--\s*draft_error:\s*([a-z0-9_]+)\s*-->", re.IGNORECASE
)
# Opening fence: ```<lang>\n at the start of a line.
_FENCE_OPEN_RE = re.compile(r"^```([a-zA-Z0-9_+-]*)\s*$", re.MULTILINE)
# Closing fence: ``` (bare) at the start of a line.
_FENCE_CLOSE_RE = re.compile(r"^```\s*$", re.MULTILINE)

_ALLOWED_EXTENSIONS = {".c", ".h", ".md", ".glsl", ".vert", ".frag"}

# Bug classes that route to the maintainer-framing path (no C repro).
# Anything else (None, "graphics-lib-dev") routes to the legacy C-draft path.
_MAINTAINER_FRAMING_BUG_CLASSES = frozenset(
    {"framework-internal", "consumer-misuse", "user-config"}
)


def compute_scenario_dir(
    eval_root: Path,
    category: str,
    framework: str,
    slug: str,
) -> Path:
    """Compute the destination directory for a new mined scenario in the
    taxonomy-tree layout (see spec 2026-05-02-eval-scenario-taxonomy-layout)."""
    if category == "synthetic":
        # Synthetic scenarios are bucketed by topic.
        from bhdr.eval.migrate_layout import synthetic_topic
        # Drop the e{N}_ prefix from slug to derive the topic suffix.
        suffix = slug.split("_", 1)[1] if "_" in slug else slug
        return eval_root / "synthetic" / synthetic_topic(suffix) / slug
    return eval_root / category / framework / slug


class DraftRejectedByModel(ValueError):
    """The drafter LLM explicitly declined to draft a scenario.

    Raised when the LLM emits a `<!-- draft_error: <reason> -->` marker (per the
    drafter prompt's principled-rejection convention). This is distinct from a
    format failure: retrying the LLM will not produce a different answer, and
    the upstream pipeline can route these to a separate bucket from
    'draft_invalid' when reporting yield.

    The `reason` attribute holds the slug from the marker (e.g.,
    `not_portable_to_c_or_snapshot`).
    """

    def __init__(self, reason: str, message: str = ""):
        self.reason = reason
        super().__init__(message or f"drafter declined: {reason}")


class DraftResult:
    """Result of the Draft stage.

    The drafter can emit multiple files per scenario (main.c, scenario.md, plus
    optional additional C/header/shader sources or verbatim upstream snapshots).

    The primary field is ``files``: a mapping from filename (relative to the
    scenario directory) to file contents.

    Backward-compatible ``c_source`` / ``md_body`` properties are kept for
    callers that have not yet migrated (Validator, commit_scenario, cached
    pipeline outputs).  ``DraftResult(c_source=..., md_body=...)`` still works
    and is internally normalized to ``files``.
    """

    __slots__ = ("scenario_id", "files")

    def __init__(
        self,
        scenario_id: str,
        files: Optional[dict] = None,
        *,
        c_source: Optional[str] = None,
        md_body: Optional[str] = None,
    ) -> None:
        if files is None:
            files = {}
            if c_source is not None:
                files["main.c"] = c_source
            if md_body is not None:
                files["scenario.md"] = md_body
        else:
            # Disallow passing both positional files and legacy kwargs.
            if c_source is not None or md_body is not None:
                raise TypeError(
                    "DraftResult: pass either files=... or "
                    "c_source=/md_body=, not both"
                )
            files = dict(files)
        self.scenario_id = scenario_id
        self.files = files

    # --- primary accessors ---

    @property
    def main_c(self) -> str:
        """Primary C source. Returns files['main.c'] or the first .c file."""
        if "main.c" in self.files:
            return self.files["main.c"]
        for name in sorted(self.files):
            if name.endswith(".c"):
                return self.files[name]
        return ""

    @property
    def scenario_md(self) -> str:
        """Scenario markdown body."""
        return self.files.get("scenario.md", "")

    # --- backward-compat aliases ---

    @property
    def c_source(self) -> str:
        return self.main_c

    @property
    def md_body(self) -> str:
        return self.scenario_md

    # Equality / repr for debugging and test ergonomics.
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DraftResult):
            return NotImplemented
        return self.scenario_id == other.scenario_id and self.files == other.files

    def __repr__(self) -> str:
        return (
            f"DraftResult(scenario_id={self.scenario_id!r}, "
            f"files={{{', '.join(repr(k) for k in self.files)}}})"
        )


def _is_maintainer_framing(triage: TriageResult, url: Optional[str] = None) -> bool:
    """Returns True iff this triage routes to the maintainer-framing drafter.

    bug_class in {framework-internal, consumer-misuse, user-config} routes to
    the maintainer-framing drafter. Everything else (None, graphics-lib-dev,
    legacy, unknown) routes to the legacy C-draft path.

    When ``bug_class`` is None and ``url`` is supplied, falls back to a
    URL-based heuristic: any github.com/<known-framework-org>/* issue routes
    to maintainer-framing. This catches cases where the triager left
    bug_class unset on `ambiguous` verdicts but the URL itself is dispositive.
    """
    if triage.bug_class in _MAINTAINER_FRAMING_BUG_CLASSES:
        return True
    if triage.bug_class is None and url:
        return _url_is_framework_repo(url)
    return False


# Known graphics-framework org/repo prefixes. Used as a fallback when the
# triager doesn't classify bug_class explicitly. Conservative — only matches
# repos we've already mined from in R10+ rounds.
_FRAMEWORK_REPO_RE = re.compile(
    r"github\.com/("
    r"BabylonJS/Babylon\.js"
    r"|mrdoob/three\.js"
    r"|playcanvas/engine"
    r"|pixijs/pixijs"
    r"|pmndrs/(?:react-three-fiber|drei|postprocessing|three-mesh-bvh)"
    r"|aframevr/aframe"
    r"|maplibre/maplibre-gl-js"
    r"|visgl/(?:deck\.gl|luma\.gl)"
    r"|keplergl/kepler\.gl"
    r"|processing/p5\.js"
    r"|CesiumGS/cesium"
    r"|Kitware/vtk-js"
    r"|KhronosGroup/glTF-Sample-Viewer"
    r"|gpujs/gpu\.js"
    r"|iTowns/itowns"
    r"|antvis/L7"
    r"|google/filament"
    r"|xeokit/xeokit-sdk"
    r"|Potree/potree"
    r"|cocos/cocos-engine"
    r"|regl-project/regl"
    r"|greggman/twgl\.js"
    r")/(?:issues|pull|commit)/",
    re.IGNORECASE,
)


def _url_is_framework_repo(url: str) -> bool:
    return bool(_FRAMEWORK_REPO_RE.search(url))


class Draft:
    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client
        self._system_lib = load_prompt("draft_core_system")
        self._system_maintainer = load_prompt("draft_maintainer_framing_system")
        # Backward-compatible attribute used by older tests / callers.
        self._system = self._system_lib

    def draft(self, thread: IssueThread, triage: TriageResult,
              scenario_id: str,
              previous_error: Optional[str] = None) -> DraftResult:
        """Generate a scenario draft.

        Bifurcates by triage.bug_class:
          - `framework-internal | consumer-misuse | user-config` → maintainer-framing
            drafter (scenario.md-only, no C repro).
          - anything else (None | graphics-lib-dev | legacy | unknown) → legacy
            C-draft path (main.c + scenario.md).

        If ``previous_error`` is provided, it's included in the user message as
        feedback from a failed prior attempt. The drafter should address the
        specific issue and produce a valid draft on retry.
        """
        if _is_maintainer_framing(triage, url=thread.url):
            return self._draft_maintainer_framing(
                thread, triage, scenario_id, previous_error
            )
        return self._draft_lib(thread, triage, scenario_id, previous_error)

    def _draft_lib(self, thread: IssueThread, triage: TriageResult,
                   scenario_id: str,
                   previous_error: Optional[str]) -> DraftResult:
        """Legacy graphics-lib drafter — emits main.c + scenario.md."""
        user = self._build_user_message(thread, triage, scenario_id, previous_error)

        resp = self._llm.complete(
            system=self._system_lib,
            messages=[{"role": "user", "content": user}],
            max_tokens=8000,
        )

        files = self._parse_files(resp.text)
        self._validate(files, thread.url)
        return DraftResult(scenario_id=scenario_id, files=files)

    def _draft_maintainer_framing(
        self, thread: IssueThread, triage: TriageResult,
        scenario_id: str,
        previous_error: Optional[str],
    ) -> DraftResult:
        """Maintainer-framing drafter — emits scenario.md only."""
        user = self._build_user_message(thread, triage, scenario_id, previous_error)

        resp = self._llm.complete(
            system=self._system_maintainer,
            messages=[{"role": "user", "content": user}],
            max_tokens=8000,
        )

        files = self._parse_files_maintainer_framing(resp.text)
        self._validate_maintainer_framing(files, thread.url)
        return DraftResult(scenario_id=scenario_id, files=files)

    @staticmethod
    def _build_user_message(thread: IssueThread, triage: TriageResult,
                            scenario_id: str,
                            previous_error: Optional[str]) -> str:
        bug_class_line = (
            f"Triage bug_class: {triage.bug_class}\n"
            if triage.bug_class else ""
        )
        base_user = (
            f"Scenario ID: {scenario_id}\n"
            f"Triage fingerprint: {triage.fingerprint}\n"
            f"{bug_class_line}"
            f"Triage summary: {triage.summary}\n\n"
            f"URL: {thread.url}\n"
            f"Title: {thread.title}\n\n"
            f"Body:\n{thread.body}\n\n"
            + "\n".join(f"Comment {i+1}:\n{c}" for i, c in enumerate(thread.comments))
        )

        if previous_error:
            return (
                base_user
                + "\n\n---\n\n"
                + "IMPORTANT: Your previous draft attempt was rejected by validation with this error:\n\n"
                + f"    {previous_error}\n\n"
                + "Please produce a new draft that fixes this specific issue. All other rules still apply."
            )
        return base_user

    @staticmethod
    def _parse_files(text: str) -> dict:
        """Parse LLM response into {filename: content}.

        Expected format: each fenced block is preceded by a
        ``<!-- filename: X -->`` HTML comment marker.  Blocks without a
        preceding filename marker are ignored.

        Raises:
          DraftRejectedByModel: if the LLM emitted a
            ``<!-- draft_error: <reason> -->`` marker AND no filename-marked
            blocks (principled refusal per drafter prompt).
          ValueError: if
            - No filename-marked blocks AND no draft_error marker are found
            - A filename uses an absolute path or contains ``..``
            - A filename has an extension outside the allowed set
            - Duplicate filenames are emitted
            - ``main.c`` (or any ``.c`` file) or ``scenario.md`` is missing
        """
        # Find every filename marker and its position.
        markers = [
            (m.start(), m.end(), m.group(1).strip())
            for m in _FILENAME_MARKER_RE.finditer(text)
        ]
        out: dict = {}
        for i, (start, end, filename) in enumerate(markers):
            # The block for this marker is bounded by the next marker (or EOF).
            segment_end = markers[i + 1][0] if i + 1 < len(markers) else len(text)
            segment = text[end:segment_end]

            # Find the opening fence within the segment.
            m_open = _FENCE_OPEN_RE.search(segment)
            if not m_open:
                raise ValueError(
                    f"filename marker '{filename}' has no following fenced block"
                )

            # The closing fence is the LAST bare ``` line in the segment.  This
            # lets a file's body contain nested fences (e.g. scenario.md
            # contains a ```yaml ... ``` block inside its ```markdown fence).
            body_start = m_open.end() + 1  # skip the newline after the opener
            closes = list(_FENCE_CLOSE_RE.finditer(segment, m_open.end()))
            if not closes:
                raise ValueError(
                    f"filename marker '{filename}' block has no closing fence"
                )
            m_close = closes[-1]
            body = segment[body_start:m_close.start()]
            # Drop trailing newline before the closing fence, if any, to match
            # how the LLM will naturally format output.
            if body.endswith("\n"):
                body = body[:-1]

            # Validate filename.
            if filename.startswith("/"):
                raise ValueError(
                    f"filename '{filename}' is absolute (starts with '/')"
                )
            parts = filename.split("/")
            if ".." in parts:
                raise ValueError(
                    f"filename '{filename}' traverses parents ('..' component)"
                )
            if any(not p for p in parts):
                raise ValueError(
                    f"filename '{filename}' has an empty path component"
                )
            basename = parts[-1]
            if "." not in basename:
                raise ValueError(f"filename '{filename}' has no extension")
            ext = "." + basename.rsplit(".", 1)[1].lower()
            if ext not in _ALLOWED_EXTENSIONS:
                raise ValueError(
                    f"filename '{filename}' extension '{ext}' not allowed; "
                    f"allowed: {sorted(_ALLOWED_EXTENSIONS)}"
                )
            if filename in out:
                raise ValueError(f"duplicate filename '{filename}'")

            out[filename] = body

        if not out:
            # If the LLM emitted an explicit principled-rejection marker,
            # surface it as DraftRejectedByModel so callers can route it to
            # a separate bucket from format failures (and skip the retry,
            # which won't change the model's mind).
            err_match = _DRAFT_ERROR_MARKER_RE.search(text)
            if err_match:
                raise DraftRejectedByModel(
                    reason=err_match.group(1).strip().lower(),
                    message=(
                        f"drafter declined: <!-- draft_error: "
                        f"{err_match.group(1).strip()} -->"
                    ),
                )
            raise ValueError(
                "No filename-marked fenced blocks found. "
                "Expected: <!-- filename: <path> -->\n```<lang>\n...\n```"
            )
        if "main.c" not in out and not any(n.endswith(".c") for n in out):
            raise ValueError("no .c source file in draft output")
        if "scenario.md" not in out:
            raise ValueError("scenario.md missing from draft output")
        return out

    @staticmethod
    def _validate(files: dict, issue_url: str) -> None:
        # At least one .c file must be present, with a SOURCE comment matching
        # the issue URL on the primary source.
        c_sources = {n: content for n, content in files.items() if n.endswith(".c")}
        if not c_sources:
            raise ValueError("no .c source file present")

        primary = files.get("main.c") or c_sources[sorted(c_sources)[0]]
        if "// SOURCE:" not in primary:
            raise ValueError("primary C source missing // SOURCE: <url> comment")
        if issue_url not in primary:
            raise ValueError("primary C source // SOURCE: does not match issue URL")

        md_body = files.get("scenario.md", "")
        if not md_body:
            raise ValueError("scenario.md missing")

        # Ground Truth section must exist (accepts both the new
        # `## Ground Truth` heading and the legacy `## Ground Truth Diagnosis`)
        m = re.search(
            r"##\s+Ground Truth(?:\s+Diagnosis)?\s*\n(.+?)(?=\n##\s+|\Z)",
            md_body, re.DOTALL | re.IGNORECASE,
        )
        if not m:
            raise ValueError("Ground Truth section missing")
        diagnosis_body = m.group(1)

        # Diagnosis must cite upstream via ONE of:
        #   (a) Blockquote (> ...): verbatim quote from issue/PR/commit
        #   (b) PR reference (PR #NNN, pull request #NNN)
        #   (c) Commit reference (commit <hex>, (abc1234), or bare <hex>{7,}
        #       near "commit"/"PR")
        #   (d) GitHub URL to pull/commit
        has_blockquote = bool(re.search(r"^>\s+", diagnosis_body, re.MULTILINE))
        has_pr_ref = bool(re.search(
            r"\b(?:PR|pull\s+request|pull/)\s*#?(\d+)\b",
            diagnosis_body, re.IGNORECASE,
        ))
        has_commit_ref = bool(re.search(
            r"\b(?:commit\s+|/commit/)([a-f0-9]{7,})\b",
            diagnosis_body, re.IGNORECASE,
        ))
        has_github_url = bool(re.search(
            r"github\.com/[\w.-]+/[\w.-]+/(?:pull|commit)/[\w]+",
            diagnosis_body, re.IGNORECASE,
        ))

        if not (has_blockquote or has_pr_ref or has_commit_ref or has_github_url):
            raise ValueError(
                "Ground Truth Diagnosis missing upstream citation. "
                "Cite via (a) a > blockquote, (b) 'PR #NNN' / 'pull request #NNN', "
                "(c) 'commit <sha>' where sha is 7+ hex chars, or "
                "(d) a github.com/.../pull|commit/... URL."
            )
        # Bug Signature must be a well-formed yaml dict with 'type' and 'spec'
        m_sig = re.search(
            r"##\s+Bug Signature\s*\n.*?```yaml\s*\n(.+?)\n```",
            md_body, re.DOTALL | re.IGNORECASE)
        if not m_sig:
            raise ValueError("Bug Signature section missing or YAML block absent")
        try:
            parsed = yaml.safe_load(m_sig.group(1))
        except yaml.YAMLError as e:
            raise ValueError(f"Bug Signature YAML parse failed: {e}")
        if not isinstance(parsed, dict) or "type" not in parsed or "spec" not in parsed:
            raise ValueError("Bug Signature must have 'type' and 'spec' keys")

        # Defense-in-depth path sanity check (also enforced in _parse_files).
        for filename in files:
            parts = filename.split("/")
            if ".." in parts or filename.startswith("/"):
                raise ValueError(f"invalid path '{filename}'")

    @staticmethod
    def _parse_files_maintainer_framing(text: str) -> dict:
        """Parse a maintainer-framing draft response.

        Expected format: exactly ONE filename-marked block, pointing at
        ``scenario.md``. Anything else fails. The relaxed
        ``main.c``-must-exist invariant from `_parse_files` is dropped here
        because maintainer-framing scenarios are scenario.md-only.
        """
        markers = [
            (m.start(), m.end(), m.group(1).strip())
            for m in _FILENAME_MARKER_RE.finditer(text)
        ]
        out: dict = {}
        for i, (start, end, filename) in enumerate(markers):
            segment_end = markers[i + 1][0] if i + 1 < len(markers) else len(text)
            segment = text[end:segment_end]

            m_open = _FENCE_OPEN_RE.search(segment)
            if not m_open:
                raise ValueError(
                    f"filename marker '{filename}' has no following fenced block"
                )
            body_start = m_open.end() + 1
            closes = list(_FENCE_CLOSE_RE.finditer(segment, m_open.end()))
            if not closes:
                raise ValueError(
                    f"filename marker '{filename}' block has no closing fence"
                )
            m_close = closes[-1]
            body = segment[body_start:m_close.start()]
            if body.endswith("\n"):
                body = body[:-1]

            # Validate filename — same rules as graphics-lib path.
            if filename.startswith("/"):
                raise ValueError(
                    f"filename '{filename}' is absolute (starts with '/')"
                )
            parts = filename.split("/")
            if ".." in parts:
                raise ValueError(
                    f"filename '{filename}' traverses parents ('..' component)"
                )
            if any(not p for p in parts):
                raise ValueError(
                    f"filename '{filename}' has an empty path component"
                )
            basename = parts[-1]
            if "." not in basename:
                raise ValueError(f"filename '{filename}' has no extension")
            ext = "." + basename.rsplit(".", 1)[1].lower()
            if ext not in _ALLOWED_EXTENSIONS:
                raise ValueError(
                    f"filename '{filename}' extension '{ext}' not allowed; "
                    f"allowed: {sorted(_ALLOWED_EXTENSIONS)}"
                )
            if filename in out:
                raise ValueError(f"duplicate filename '{filename}'")

            out[filename] = body

        if not out:
            err_match = _DRAFT_ERROR_MARKER_RE.search(text)
            if err_match:
                raise DraftRejectedByModel(
                    reason=err_match.group(1).strip().lower(),
                    message=(
                        f"drafter declined: <!-- draft_error: "
                        f"{err_match.group(1).strip()} -->"
                    ),
                )
            raise ValueError(
                "No filename-marked fenced blocks found. "
                "Expected: <!-- filename: scenario.md -->\n```markdown\n...\n```"
            )

        # Maintainer-framing must NOT include any .c file. Reject if it does
        # so the caller doesn't accidentally feed the file to the C-build path.
        for name in out:
            if name.endswith(".c"):
                raise ValueError(
                    f"maintainer-framing draft must not contain C source "
                    f"files; got '{name}'"
                )
        if "scenario.md" not in out:
            raise ValueError(
                "maintainer-framing draft missing scenario.md"
            )
        return out

    @staticmethod
    def _validate_maintainer_framing(files: dict, issue_url: str) -> None:
        """Static validation of a maintainer-framing draft.

        Checks (in order):
          - scenario.md is present and non-empty.
          - `## User Report` and `## Ground Truth` sections present.
          - `## Ground Truth` cites upstream evidence (blockquote / PR /
            commit / URL).
          - `## Fix` block parses as YAML with required fields.
          - Files list is non-empty (or bug_class == "legacy").
          - User Report does NOT contain forbidden contamination patterns
            (fix PR number, fix file paths, fix SHA).
        """
        md_body = files.get("scenario.md", "")
        if not md_body:
            raise ValueError("scenario.md missing")

        # User Report
        if not re.search(r"^##\s+User Report\s*$", md_body, re.MULTILINE):
            raise ValueError("scenario.md missing `## User Report` section")

        # Ground Truth
        m = re.search(
            r"##\s+Ground Truth(?:\s+Diagnosis)?\s*\n(.+?)(?=\n##\s+|\Z)",
            md_body, re.DOTALL | re.IGNORECASE,
        )
        if not m:
            raise ValueError("Ground Truth section missing")
        diagnosis_body = m.group(1)

        has_blockquote = bool(re.search(r"^>\s+", diagnosis_body, re.MULTILINE))
        has_pr_ref = bool(re.search(
            r"\b(?:PR|pull\s+request|pull/)\s*#?(\d+)\b",
            diagnosis_body, re.IGNORECASE,
        ))
        has_commit_ref = bool(re.search(
            r"\b(?:commit\s+|/commit/)([a-f0-9]{7,})\b",
            diagnosis_body, re.IGNORECASE,
        ))
        has_github_url = bool(re.search(
            r"github\.com/[\w.-]+/[\w.-]+/(?:pull|commit)/[\w]+",
            diagnosis_body, re.IGNORECASE,
        ))
        if not (has_blockquote or has_pr_ref or has_commit_ref or has_github_url):
            raise ValueError(
                "Ground Truth section missing upstream citation. "
                "Cite via (a) a > blockquote, (b) 'PR #NNN' / 'pull request #NNN', "
                "(c) 'commit <sha>' where sha is 7+ hex chars, or "
                "(d) a github.com/.../pull|commit/... URL."
            )

        # ## Fix block
        m_fix = re.search(
            r"##\s+Fix\s*\n(.+?)(?=\n##\s+|\Z)",
            md_body, re.DOTALL | re.IGNORECASE,
        )
        if not m_fix:
            raise ValueError("`## Fix` section missing")
        fix_body = m_fix.group(1)

        m_yaml = re.search(r"```yaml\s*\n(.+?)\n```", fix_body, re.DOTALL)
        if not m_yaml:
            raise ValueError("`## Fix` section missing yaml fenced block")
        try:
            data = yaml.safe_load(m_yaml.group(1))
        except yaml.YAMLError as e:
            raise ValueError(f"`## Fix` YAML parse failed: {e}")
        if not isinstance(data, dict):
            raise ValueError("`## Fix` YAML did not parse as a mapping")

        if not data.get("fix_pr_url"):
            raise ValueError("`## Fix` missing fix_pr_url")
        bug_class = data.get("bug_class")
        if not bug_class:
            raise ValueError("`## Fix` missing bug_class")

        files_raw = data.get("files")
        files_list: list = []
        if isinstance(files_raw, list):
            files_list = [f for f in files_raw if f is not None and str(f).strip()]
        if not files_list and bug_class != "legacy":
            raise ValueError(
                f"`## Fix` files list is empty (only allowed for "
                f"bug_class: legacy; got bug_class: {bug_class!r})"
            )

        # User-Report contamination check — extract just the User Report body.
        ur_m = re.search(
            r"##\s+User Report\s*\n(.+?)(?=\n##\s+|\Z)",
            md_body, re.DOTALL | re.IGNORECASE,
        )
        if ur_m:
            user_report = ur_m.group(1)
            # Forbid mention of the fix PR number (the agent's job is to find it).
            fix_pr_url = str(data.get("fix_pr_url") or "")
            pr_num_m = re.search(r"/pull/(\d+)", fix_pr_url)
            if pr_num_m:
                pr_num = pr_num_m.group(1)
                if re.search(rf"#{pr_num}\b", user_report):
                    raise ValueError(
                        f"User Report contains the fix PR number "
                        f"#{pr_num} (would spoil the eval)"
                    )
                if re.search(rf"PR\s*#?{pr_num}\b", user_report, re.IGNORECASE):
                    raise ValueError(
                        f"User Report references PR {pr_num} (would spoil the eval)"
                    )
            # Forbid the fix SHA (full or short).
            fix_sha = str(data.get("fix_sha") or "")
            if fix_sha and len(fix_sha) >= 7 and not fix_sha.startswith("(auto-resolve"):
                if fix_sha[:7].lower() in user_report.lower():
                    raise ValueError(
                        f"User Report contains the fix SHA prefix "
                        f"{fix_sha[:7]} (would spoil the eval)"
                    )
            # Forbid any of the fix files appearing verbatim in the User Report.
            for f in files_list:
                fstr = str(f).strip()
                if not fstr or len(fstr) < 8:
                    # Avoid false positives on extremely short paths
                    continue
                if fstr in user_report:
                    raise ValueError(
                        f"User Report contains fix file path {fstr!r} "
                        f"(would spoil the eval)"
                    )

        # Defense-in-depth path sanity check.
        for filename in files:
            parts = filename.split("/")
            if ".." in parts or filename.startswith("/"):
                raise ValueError(f"invalid path '{filename}'")
