"""bug_class finalisation in run.py — framework-path fallback + LLM Triage.

The R12 codex-mined cohort surfaced that the regex in `infer_bug_class`
mis-labels framework-internal bugs as `consumer-misuse`/`user-config`
because the issue body uses tokens like "use" / "enable" loosely. Two
overrides land here:

1. **Framework-path fallback (deterministic).** If every entry in
   `expected_files` looks like framework source (i.e. not under
   examples/, docs/, tests/, fixtures/, etc.), force `bug_class =
   "framework-internal"`. Reasoning: the fix-PR is patching framework
   code; the body-text guess was wrong.
2. **LLM Triage override (opt-in via `--llm-triage`).** When the flag
   is set, the existing `Triage` LLM is called and its `bug_class` wins
   over the regex guess. The framework-path fallback still applies as
   belt-and-suspenders even when triage returns None.

`graphics-lib-dev` is preserved untouched because the drafter routing
depends on it (different prompt path, see iter-9 bifurcation).
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# _is_framework_source_path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "src/render/draw_fill.ts",                  # maplibre
        "servers/rendering/renderer_rd/effects.cpp",  # godot
        "packages/engine/Source/Scene/Picking.js",  # cesium
        "src/objects/Mesh.js",                      # three.js
        "core/io/marshalls.cpp",                    # godot
        "packages/widgets/Source/Viewer.js",
        "lib/foo.rb",
        "crates/bevy_pbr/src/render/mesh.rs",
    ],
)
def test_framework_source_paths_recognised(path):
    from gpa.eval.curation.run import _is_framework_source_path
    assert _is_framework_source_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "tests/integration/foo.ts",
        "src/__tests__/foo.test.ts",
        "examples/three/loader.html",
        "docs/api.md",
        "examples/example1/main.cpp",
        "fixtures/golden.png",
        "demos/spinning-cube.html",
        "packages/engine/Specs/Renderer/BufferSpec.js",  # Jasmine
        "packages/engine/Specs/Scene/PickingSpec.js",
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "README.md",
        "src/foo.test.ts",
        "src/foo_test.go",
        "test/test_foo.py",
    ],
)
def test_non_framework_paths_rejected(path):
    from gpa.eval.curation.run import _is_framework_source_path
    assert _is_framework_source_path(path) is False


def test_empty_path_rejected():
    from gpa.eval.curation.run import _is_framework_source_path
    assert _is_framework_source_path("") is False


# ---------------------------------------------------------------------------
# _finalize_bug_class
# ---------------------------------------------------------------------------


def test_framework_path_fallback_overrides_consumer_misuse():
    """The R12 maplibre case: rec said consumer-misuse, fix-PR patches
    src/render/*.ts → final bug_class is framework-internal."""
    from gpa.eval.curation.run import _finalize_bug_class
    out = _finalize_bug_class(
        rec_guess="consumer-misuse",
        expected_files=[
            "src/render/draw_fill.ts",
            "src/render/draw_line.ts",
            "src/render/painter.ts",
        ],
        triage_bug_class=None,
    )
    assert out == "framework-internal"


def test_framework_path_fallback_overrides_user_config():
    """The R12 godot world_environment_glow case: rec said user-config,
    fix-PR patches servers/rendering/* → framework-internal."""
    from gpa.eval.curation.run import _finalize_bug_class
    out = _finalize_bug_class(
        rec_guess="user-config",
        expected_files=["servers/rendering/renderer_rd/effects/copy_effects.cpp"],
        triage_bug_class=None,
    )
    assert out == "framework-internal"


def test_framework_path_fallback_no_op_when_files_empty():
    """If expected_files is empty (e.g. fix-PR was all docs and got
    filtered to nothing), the fallback must not fire — stays at
    rec.bug_class_guess."""
    from gpa.eval.curation.run import _finalize_bug_class
    out = _finalize_bug_class(
        rec_guess="consumer-misuse",
        expected_files=[],
        triage_bug_class=None,
    )
    assert out == "consumer-misuse"


def test_framework_path_fallback_no_op_when_any_file_excluded():
    """If even one entry isn't recognised as framework source, the
    fallback shouldn't fire (be conservative — prefer rec_guess over
    a wrong override)."""
    from gpa.eval.curation.run import _finalize_bug_class
    out = _finalize_bug_class(
        rec_guess="consumer-misuse",
        expected_files=[
            "src/render/draw_fill.ts",
            "examples/usage/demo.html",
        ],
        triage_bug_class=None,
    )
    assert out == "consumer-misuse"


def test_graphics_lib_dev_never_overridden():
    """graphics-lib-dev gates the drafter routing (C-repro vs maintainer
    framing). Overriding it would silently change the drafter path —
    never do that."""
    from gpa.eval.curation.run import _finalize_bug_class
    out = _finalize_bug_class(
        rec_guess="graphics-lib-dev",
        expected_files=["src/render/draw_fill.ts"],
        triage_bug_class="framework-internal",
    )
    assert out == "graphics-lib-dev"


def test_triage_result_overrides_rec_guess():
    """When --llm-triage is on and the triager classifies the issue,
    its verdict beats the regex guess."""
    from gpa.eval.curation.run import _finalize_bug_class
    out = _finalize_bug_class(
        rec_guess="consumer-misuse",
        expected_files=[],
        triage_bug_class="framework-internal",
    )
    assert out == "framework-internal"


def test_triage_result_beats_framework_path_fallback():
    """When both triggers fire, triager wins. (In practice they agree;
    this test pins the priority order.)"""
    from gpa.eval.curation.run import _finalize_bug_class
    out = _finalize_bug_class(
        rec_guess="consumer-misuse",
        expected_files=["src/render/draw_fill.ts"],
        triage_bug_class="user-config",
    )
    assert out == "user-config"


def test_triage_none_falls_through_to_fallback():
    """When triager returns None (e.g. parse failure), framework-path
    fallback still applies."""
    from gpa.eval.curation.run import _finalize_bug_class
    out = _finalize_bug_class(
        rec_guess="consumer-misuse",
        expected_files=["src/render/draw_fill.ts"],
        triage_bug_class=None,
    )
    assert out == "framework-internal"


def test_no_triggers_returns_rec_guess():
    """No triager, no framework-path match → rec_guess is the answer."""
    from gpa.eval.curation.run import _finalize_bug_class
    out = _finalize_bug_class(
        rec_guess="user-config",
        expected_files=[],
        triage_bug_class=None,
    )
    assert out == "user-config"


# ---------------------------------------------------------------------------
# _run_produce integration: the override actually lands in draft.extras
# ---------------------------------------------------------------------------


class _FakeRec:
    def __init__(self, bug_class_guess: str, taxonomy_cell: str):
        self.bug_class_guess = bug_class_guess
        self.taxonomy_cell = taxonomy_cell
        self.url = "https://github.com/maplibre/maplibre-gl-js/issues/1"
        self.score = 8
        self.score_reasons: list[str] = []


class _FakeOk:
    ok = True


def _make_thread():
    from gpa.eval.curation.triage import IssueThread
    return IssueThread(
        url="https://github.com/maplibre/maplibre-gl-js/issues/1",
        title="3D terrain with partially transparent",
        body="Use a custom 3D terrain source — bug is visible.",
        comments=["Closes #5746"],
    )


class _FakeCand:
    def __init__(self):
        self.url = "https://github.com/maplibre/maplibre-gl-js/issues/1"
        self.source_type = "issue"
        self.title = "x"
        self.metadata = {"body": "x", "source_query": "q",
                         "source_query_kind": "issue"}


def test_run_produce_applies_framework_path_fallback(monkeypatch, tmp_path):
    """End-to-end: regex-guessed `consumer-misuse` flips to
    `framework-internal` because all fix.files are framework source."""
    from gpa.eval.curation import run as run_mod
    from gpa.eval.curation.journey import JourneyWriter

    monkeypatch.setattr(
        run_mod, "_fetch_fix_pr_metadata",
        lambda thread, url: {
            "url": "https://github.com/maplibre/maplibre-gl-js/pull/5746",
            "commit_sha": "abc1234",
            "files_changed": [
                "src/render/draw_fill.ts",
                "src/render/draw_line.ts",
                "src/render/painter.ts",
            ],
        },
    )
    monkeypatch.setattr(run_mod, "_validate_draft", lambda d, e: _FakeOk())

    cand = _FakeCand()
    thread = _make_thread()
    rec = _FakeRec(
        bug_class_guess="consumer-misuse",
        taxonomy_cell="framework-maintenance.web-map.maplibre-gl-js",
    )
    writer = JourneyWriter(tmp_path / "j.jsonl")

    drafted = run_mod._run_produce(
        selected=[(cand, thread, rec)],
        eval_dir=tmp_path / "eval",
        run_id="rid", discovered_at="2026-05-04T00:00:00Z",
        writer=writer,
    )
    assert len(drafted) == 1
    _, _, _, draft, _ = drafted[0]
    assert draft.extras["bug_class"] == "framework-internal"


def test_run_produce_keeps_rec_guess_when_no_override_fires(monkeypatch, tmp_path):
    """Demo/sample paths: `_filter_source_files` doesn't filter them
    (a fix-PR can legitimately add a demo as the fix), but our
    framework-path check does. The file survives extract_draft and
    arrives at _finalize_bug_class, which leaves rec.bug_class_guess
    intact because `_is_framework_source_path` returns False."""
    from gpa.eval.curation import run as run_mod
    from gpa.eval.curation.journey import JourneyWriter

    monkeypatch.setattr(
        run_mod, "_fetch_fix_pr_metadata",
        lambda thread, url: {
            "url": "https://github.com/o/r/pull/2",
            "commit_sha": "abc1234",
            "files_changed": ["demos/usage_demo.cpp"],
        },
    )
    monkeypatch.setattr(run_mod, "_validate_draft", lambda d, e: _FakeOk())

    cand = _FakeCand()
    thread = _make_thread()
    rec = _FakeRec(
        bug_class_guess="consumer-misuse",
        taxonomy_cell="framework-maintenance.web-map.maplibre-gl-js",
    )
    writer = JourneyWriter(tmp_path / "j.jsonl")

    drafted = run_mod._run_produce(
        selected=[(cand, thread, rec)],
        eval_dir=tmp_path / "eval",
        run_id="rid", discovered_at="2026-05-04T00:00:00Z",
        writer=writer,
    )
    assert len(drafted) == 1
    _, _, _, draft, _ = drafted[0]
    assert draft.extras["bug_class"] == "consumer-misuse"


def test_run_produce_applies_triage_fn_when_provided(monkeypatch, tmp_path):
    """When a `triage_fn` is wired in (via --llm-triage), its verdict
    beats both the regex `bug_class_guess` and the framework-path
    fallback."""
    from gpa.eval.curation import run as run_mod
    from gpa.eval.curation.journey import JourneyWriter

    monkeypatch.setattr(
        run_mod, "_fetch_fix_pr_metadata",
        lambda thread, url: {
            "url": "https://github.com/o/r/pull/2",
            "commit_sha": "abc1234",
            # framework source → fallback would say framework-internal
            "files_changed": ["src/render/draw_fill.ts"],
        },
    )
    monkeypatch.setattr(run_mod, "_validate_draft", lambda d, e: _FakeOk())

    cand = _FakeCand()
    thread = _make_thread()
    rec = _FakeRec(
        bug_class_guess="consumer-misuse",
        taxonomy_cell="framework-maintenance.web-map.maplibre-gl-js",
    )
    writer = JourneyWriter(tmp_path / "j.jsonl")

    triage_called = []
    def _triage_fn(t):
        triage_called.append(t.url)
        # Different from rec_guess and from fallback so we can pin the
        # winner.
        return "user-config"

    drafted = run_mod._run_produce(
        selected=[(cand, thread, rec)],
        eval_dir=tmp_path / "eval",
        run_id="rid", discovered_at="2026-05-04T00:00:00Z",
        writer=writer,
        triage_fn=_triage_fn,
    )
    assert len(drafted) == 1
    _, _, _, draft, _ = drafted[0]
    assert draft.extras["bug_class"] == "user-config"
    assert triage_called == [thread.url]


def test_run_produce_swallows_triage_errors(monkeypatch, tmp_path):
    """If the triage call blows up (network error, parse failure), the
    pipeline must not crash — fall through to rec.bug_class_guess +
    framework-path fallback."""
    from gpa.eval.curation import run as run_mod
    from gpa.eval.curation.journey import JourneyWriter

    monkeypatch.setattr(
        run_mod, "_fetch_fix_pr_metadata",
        lambda thread, url: {
            "url": "https://github.com/o/r/pull/2",
            "commit_sha": "abc1234",
            "files_changed": ["src/render/draw_fill.ts"],
        },
    )
    monkeypatch.setattr(run_mod, "_validate_draft", lambda d, e: _FakeOk())

    cand = _FakeCand()
    thread = _make_thread()
    rec = _FakeRec(
        bug_class_guess="consumer-misuse",
        taxonomy_cell="framework-maintenance.web-map.maplibre-gl-js",
    )
    writer = JourneyWriter(tmp_path / "j.jsonl")

    def _broken_triage(t):
        raise RuntimeError("LLM unreachable")

    drafted = run_mod._run_produce(
        selected=[(cand, thread, rec)],
        eval_dir=tmp_path / "eval",
        run_id="rid", discovered_at="2026-05-04T00:00:00Z",
        writer=writer,
        triage_fn=_broken_triage,
    )
    assert len(drafted) == 1
    _, _, _, draft, _ = drafted[0]
    # framework-path fallback still applies
    assert draft.extras["bug_class"] == "framework-internal"
