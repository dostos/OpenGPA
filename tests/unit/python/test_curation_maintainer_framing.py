"""Tests for the maintainer-framing drafter bifurcation (iter-9)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gpa.eval.curation.draft import (
    Draft,
    DraftRejectedByModel,
    DraftResult,
    _is_maintainer_framing,
)
from gpa.eval.curation.llm_client import LLMResponse
from gpa.eval.curation.triage import IssueThread, TriageResult
from gpa.eval.curation.validate import (
    Validator,
    _is_maintainer_framing_draft,
)


def _fake_response(text: str) -> LLMResponse:
    return LLMResponse(
        text=text,
        input_tokens=100,
        output_tokens=50,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
        stop_reason="end_turn",
    )


_MAINTAINER_MD = """# R200_TEST: Glass material renders as black squares

## User Report
When I load the AnisotropyBarnLamp.glb model and add a DirectionalLight to
the scene, small black squares appear on the glass material. They grow
larger as roughness increases.

Version: r183. Browser: Chrome.

## Expected Correct Output
A smoothly-shaded anisotropic glass surface with no black patches.

## Actual Broken Output
Scattered fragments read as pure black (0,0,0). The black region grows with
roughness.

## Ground Truth
The PR removed a `saturate()` wrap around the anisotropic visibility term
but did not port the divide-by-zero guard.

> "Removing the `saturate()` was right but it was missed to introduce the
> same guard as `V_GGX_SmithCorrelated()` to prevent division through `0`."

See PR #33205 for the fix.

## Fix
```yaml
fix_pr_url: https://github.com/mrdoob/three.js/pull/33205
fix_sha: 7716cd9415b12c9f29596ca838a7a99814b82787
fix_parent_sha: bfe332d9ee7016ab36dfb79826d421d4487058f4
bug_class: framework-internal
framework: three.js
framework_version: r183
files:
  - src/nodes/functions/BSDF/V_GGX_SmithCorrelated_Anisotropic.js
  - src/renderers/shaders/ShaderChunk/lights_physical_pars_fragment.glsl.js
change_summary: >
  Wrap the anisotropic visibility division with EPSILON in the denominator
  to prevent +Inf when geometric-shadowing terms drop to zero.
```

## Difficulty Rating
4/5

## Adversarial Principles
- bug-lives-inside-framework-not-user-code

## How OpenGPA Helps
A `gpa report` would surface +Inf in the framebuffer; tracing the literal
`0.5` from the fragment shader leads back to the visibility-term file.

## Source
- **URL**: https://github.com/mrdoob/three.js/issues/30000
- **Type**: issue
- **Date**: 2024-09-01
- **Commit SHA**: 7716cd9415b12c9f29596ca838a7a99814b82787
- **Attribution**: Reported by @user; fixed in PR #33205.

## Tier
maintainer-framing

## API
opengl

## Framework
three.js

## Bug Signature
```yaml
type: code_location
spec:
  expected_files:
    - src/nodes/functions/BSDF/V_GGX_SmithCorrelated_Anisotropic.js
  fix_commit: 7716cd94
```

## Predicted OpenGPA Helpfulness
- **Verdict**: yes
- **Reasoning**: The +Inf reaches the framebuffer; trace surfaces the literal.
"""


def _wrap_maintainer_response(md_body: str) -> str:
    """Build an LLM response in the new filename-marked format,
    scenario.md only."""
    return (
        "<!-- filename: scenario.md -->\n"
        "```markdown\n"
        + md_body.rstrip("\n")
        + "\n```\n"
    )


def _maintainer_thread() -> IssueThread:
    return IssueThread(
        url="https://github.com/mrdoob/three.js/issues/30000",
        title="black squares on glass material",
        body="When I add a DirectionalLight black squares appear...",
        comments=[],
    )


def _maintainer_triage() -> TriageResult:
    return TriageResult(
        verdict="in_scope",
        fingerprint="numeric_precision:divide_by_zero",
        rejection_reason=None,
        summary="anisotropic visibility term divides by zero",
        bug_class="framework-internal",
    )


# --- Bug class dispatch ----------------------------------------------------


def test_is_maintainer_framing_for_framework_internal():
    triage = _maintainer_triage()
    assert _is_maintainer_framing(triage) is True


def test_is_maintainer_framing_for_consumer_misuse():
    triage = TriageResult(
        verdict="in_scope", fingerprint="other:x", rejection_reason=None,
        summary="", bug_class="consumer-misuse",
    )
    assert _is_maintainer_framing(triage) is True


def test_is_maintainer_framing_for_user_config():
    triage = TriageResult(
        verdict="in_scope", fingerprint="other:x", rejection_reason=None,
        summary="", bug_class="user-config",
    )
    assert _is_maintainer_framing(triage) is True


def test_is_maintainer_framing_false_for_graphics_lib_dev():
    triage = TriageResult(
        verdict="in_scope", fingerprint="state_leak:x", rejection_reason=None,
        summary="", bug_class="graphics-lib-dev",
    )
    assert _is_maintainer_framing(triage) is False


def test_is_maintainer_framing_false_when_unset():
    """Back-compat: TriageResult constructed without bug_class should NOT route
    to maintainer-framing."""
    triage = TriageResult(
        verdict="in_scope", fingerprint="state_leak:x", rejection_reason=None,
        summary="",
    )
    assert _is_maintainer_framing(triage) is False


def test_is_maintainer_framing_url_fallback_for_known_framework_repo():
    """When bug_class is None but the URL is a known framework repo, fall
    back to maintainer-framing — covers ambiguous-verdict cases where the
    triager doesn't fill in bug_class."""
    triage = TriageResult(
        verdict="ambiguous", fingerprint="other:unknown",
        rejection_reason=None, summary="",
    )
    # No bug_class set, but URL is from a known framework repo
    assert _is_maintainer_framing(
        triage, url="https://github.com/BabylonJS/Babylon.js/issues/9826",
    ) is True
    assert _is_maintainer_framing(
        triage, url="https://github.com/playcanvas/engine/issues/5902",
    ) is True
    assert _is_maintainer_framing(
        triage, url="https://github.com/pmndrs/drei/issues/2583",
    ) is True


def test_is_maintainer_framing_url_fallback_no_match_for_unknown_repo():
    triage = TriageResult(
        verdict="ambiguous", fingerprint="other:unknown",
        rejection_reason=None, summary="",
    )
    # Random repo not in the framework list
    assert _is_maintainer_framing(
        triage, url="https://github.com/some-random/project/issues/1",
    ) is False


def test_is_maintainer_framing_explicit_graphics_lib_overrides_url():
    """An explicit bug_class: graphics-lib-dev classification must take
    precedence over the URL heuristic."""
    triage = TriageResult(
        verdict="in_scope", fingerprint="state_leak:x",
        rejection_reason=None, summary="",
        bug_class="graphics-lib-dev",
    )
    # Even though URL is from a framework repo, explicit graphics-lib-dev wins
    assert _is_maintainer_framing(
        triage, url="https://github.com/BabylonJS/Babylon.js/issues/9826",
    ) is False


# --- Drafter dispatch + parse ---------------------------------------------


def test_draft_dispatches_to_maintainer_framing_path():
    """When triage.bug_class is framework-internal, the drafter must use the
    maintainer-framing prompt and emit scenario.md ONLY."""
    llm = MagicMock()
    llm.complete.return_value = _fake_response(
        _wrap_maintainer_response(_MAINTAINER_MD)
    )
    d = Draft(llm_client=llm)
    result = d.draft(
        _maintainer_thread(), _maintainer_triage(), scenario_id="r200_test",
    )
    assert result.scenario_id == "r200_test"
    # No main.c, only scenario.md
    assert set(result.files.keys()) == {"scenario.md"}
    assert "main.c" not in result.files
    # Verify the maintainer-framing prompt was used by checking the system
    # message that the LLM was called with.
    sys_arg = llm.complete.call_args.kwargs.get("system") or \
        llm.complete.call_args.args[0]
    assert "maintainer-framing" in sys_arg or "framework-bug" in sys_arg


def test_draft_dispatches_to_legacy_path_when_bug_class_unset():
    """Without bug_class, the drafter should use the legacy C-draft prompt."""
    llm = MagicMock()
    # Build a minimal valid C-draft response.
    c_code = (
        "// SOURCE: https://github.com/x/y/issues/1\n"
        "#include <GL/gl.h>\nint main(){return 0;}\n"
    )
    md_body = (
        "# R201_TEST: t\n\n"
        "## Bug\nfoo\n\n## User Report\nfoo\n\n"
        "## Expected Correct Output\nfoo\n\n"
        "## Actual Broken Output\nfoo\n\n"
        "## Ground Truth\n> quote\n\n"
        "## Fix\n```yaml\nfix_pr_url: https://github.com/x/y/pull/2\n"
        "bug_class: legacy\nfiles: []\n```\n\n"
        "## Difficulty Rating\n3/5\n\n"
        "## Adversarial Principles\n- p\n\n"
        "## How OpenGPA Helps\n.\n\n"
        "## Source\n- **URL**: https://github.com/x/y/issues/1\n"
        "- **Type**: issue\n- **Date**: 2024-01-01\n"
        "- **Commit SHA**: (n/a)\n- **Attribution**: u\n\n"
        "## Tier\ncore\n\n## API\nopengl\n\n## Framework\nnone\n\n"
        "## Bug Signature\n```yaml\ntype: unexpected_color\n"
        "spec:\n  region: center\n```\n\n"
        "## Predicted OpenGPA Helpfulness\n- **Verdict**: yes\n"
        "- **Reasoning**: .\n"
    )
    response = (
        "<!-- filename: main.c -->\n```c\n"
        + c_code.rstrip("\n")
        + "\n```\n\n<!-- filename: scenario.md -->\n```markdown\n"
        + md_body.rstrip("\n")
        + "\n```\n"
    )
    llm.complete.return_value = _fake_response(response)
    d = Draft(llm_client=llm)
    triage = TriageResult(
        verdict="in_scope", fingerprint="state_leak:x",
        rejection_reason=None, summary="",
    )
    result = d.draft(
        IssueThread(url="https://github.com/x/y/issues/1", title="t", body="b"),
        triage,
        scenario_id="r201_test",
    )
    assert "main.c" in result.files
    assert "scenario.md" in result.files


def test_maintainer_framing_parser_rejects_main_c_in_response():
    """If the LLM accidentally emits a C file in maintainer-framing mode, the
    parser must reject."""
    llm = MagicMock()
    bad_response = (
        "<!-- filename: main.c -->\n```c\nint main(){return 0;}\n```\n\n"
        + _wrap_maintainer_response(_MAINTAINER_MD)
    )
    llm.complete.return_value = _fake_response(bad_response)
    d = Draft(llm_client=llm)
    with pytest.raises(ValueError, match="must not contain C source"):
        d.draft(
            _maintainer_thread(),
            _maintainer_triage(),
            scenario_id="r202_test",
        )


def test_maintainer_framing_parser_routes_draft_error_marker():
    """The principled-rejection marker still works on the maintainer path."""
    llm = MagicMock()
    bad_response = (
        "<!-- draft_error: thread_too_thin -->\nThread is too short.\n"
    )
    llm.complete.return_value = _fake_response(bad_response)
    d = Draft(llm_client=llm)
    with pytest.raises(DraftRejectedByModel) as exc:
        d.draft(
            _maintainer_thread(),
            _maintainer_triage(),
            scenario_id="r203_test",
        )
    assert exc.value.reason == "thread_too_thin"


# --- Maintainer-framing validation -----------------------------------------


def test_maintainer_framing_validate_happy_path():
    """A well-formed maintainer-framing draft validates green."""
    llm = MagicMock()
    llm.complete.return_value = _fake_response(
        _wrap_maintainer_response(_MAINTAINER_MD)
    )
    d = Draft(llm_client=llm)
    result = d.draft(
        _maintainer_thread(), _maintainer_triage(),
        scenario_id="r210_validate_test",
    )
    assert _is_maintainer_framing_draft(result) is True


def test_maintainer_framing_validate_rejects_user_report_with_pr_number(tmp_path):
    """User report containing the fix PR number must be rejected."""
    md = _MAINTAINER_MD.replace(
        "Version: r183. Browser: Chrome.",
        "Version: r183. Browser: Chrome. Probably PR #33205 broke it.",
    )
    llm = MagicMock()
    llm.complete.return_value = _fake_response(_wrap_maintainer_response(md))
    d = Draft(llm_client=llm)
    with pytest.raises(ValueError, match="PR.*33205"):
        d.draft(
            _maintainer_thread(),
            _maintainer_triage(),
            scenario_id="r211_test",
        )


def test_maintainer_framing_validate_rejects_user_report_with_fix_file(tmp_path):
    """User report containing a fix file path must be rejected."""
    md = _MAINTAINER_MD.replace(
        "Version: r183. Browser: Chrome.",
        "Version: r183. Browser: Chrome. The bug is in "
        "src/nodes/functions/BSDF/V_GGX_SmithCorrelated_Anisotropic.js.",
    )
    llm = MagicMock()
    llm.complete.return_value = _fake_response(_wrap_maintainer_response(md))
    d = Draft(llm_client=llm)
    with pytest.raises(ValueError, match="fix file path"):
        d.draft(
            _maintainer_thread(),
            _maintainer_triage(),
            scenario_id="r212_test",
        )


def test_maintainer_framing_validator_accepts_drafted_scenario(tmp_path):
    """End-to-end: drafter writes scenario.md, Validator runs static checks
    and returns ok=True."""
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()

    llm = MagicMock()
    llm.complete.return_value = _fake_response(
        _wrap_maintainer_response(_MAINTAINER_MD)
    )
    drafter = Draft(llm_client=llm)
    draft = drafter.draft(
        _maintainer_thread(), _maintainer_triage(),
        scenario_id="r220_test",
    )

    # Runner is unused by maintainer-framing validation; pass a stub that would
    # raise if the validator tries to use it.
    runner = MagicMock()
    runner.build_and_capture.side_effect = AssertionError(
        "build_and_capture should NOT be called for maintainer-framing"
    )

    validator = Validator(eval_dir=str(eval_dir), runner=runner)
    vres = validator.validate(draft)
    assert vres.ok, f"validation failed: {vres.reason}"
    # Scenario directory should still exist on success
    assert (eval_dir / "r220_test" / "scenario.md").exists()


def test_maintainer_framing_validator_rejects_empty_files_non_legacy(tmp_path):
    """A non-legacy fix block with empty files: [] must be rejected."""
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    md = _MAINTAINER_MD.replace(
        "files:\n"
        "  - src/nodes/functions/BSDF/V_GGX_SmithCorrelated_Anisotropic.js\n"
        "  - src/renderers/shaders/ShaderChunk/lights_physical_pars_fragment.glsl.js\n",
        "files: []\n",
    )
    # The drafter's own _validate_maintainer_framing rejects this before it
    # gets to the validator, so feed a pre-built DraftResult straight in.
    draft = DraftResult(
        scenario_id="r221_test",
        files={"scenario.md": md},
    )
    runner = MagicMock()
    validator = Validator(eval_dir=str(eval_dir), runner=runner)
    vres = validator.validate(draft)
    # Could fail at multiple gates; make sure "fix_files_empty" or contamination
    # surfaces, NOT "no framebuffer captured".
    assert not vres.ok
    assert "framebuffer" not in vres.reason.lower()


def test_maintainer_framing_validator_accepts_legacy_with_empty_files(tmp_path):
    """A bug_class: legacy fix block with files: [] is the explicit retrofit
    escape hatch — must be accepted."""
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    md = _MAINTAINER_MD.replace(
        "bug_class: framework-internal\n",
        "bug_class: legacy\n",
    ).replace(
        "files:\n"
        "  - src/nodes/functions/BSDF/V_GGX_SmithCorrelated_Anisotropic.js\n"
        "  - src/renderers/shaders/ShaderChunk/lights_physical_pars_fragment.glsl.js\n",
        "files: []\n",
    )
    draft = DraftResult(
        scenario_id="r222_test",
        files={"scenario.md": md},
    )
    runner = MagicMock()
    validator = Validator(eval_dir=str(eval_dir), runner=runner)
    vres = validator.validate(draft)
    assert vres.ok, f"legacy-with-empty-files should validate; got: {vres.reason}"


# --- Triage bug_class round trip ------------------------------------------


def test_triage_bug_class_field_back_compat():
    """TriageResult kwarg-construction without bug_class still works."""
    t = TriageResult(
        verdict="in_scope", fingerprint="x:y", rejection_reason=None, summary="",
    )
    assert t.bug_class is None


def test_triage_normalize_unknown_bug_class_falls_back_to_none():
    """Triage._normalize must defensively reject unknown bug_class strings."""
    from gpa.eval.curation.triage import Triage
    llm = MagicMock()
    triager = Triage(llm_client=llm)
    out = triager._normalize({
        "triage_verdict": "in_scope",
        "root_cause_fingerprint": "state_leak:x",
        "rejection_reason": None,
        "summary": "ok",
        "bug_class": "made-up-class",
    })
    assert out.bug_class is None


def test_triage_normalize_accepts_each_valid_bug_class():
    """All four valid bug_class strings must round-trip through _normalize."""
    from gpa.eval.curation.triage import Triage
    llm = MagicMock()
    triager = Triage(llm_client=llm)
    for bc in (
        "graphics-lib-dev",
        "framework-internal",
        "consumer-misuse",
        "user-config",
    ):
        out = triager._normalize({
            "triage_verdict": "in_scope",
            "root_cause_fingerprint": "state_leak:x",
            "rejection_reason": None,
            "summary": "ok",
            "bug_class": bc,
        })
        assert out.bug_class == bc, f"failed for {bc}"
