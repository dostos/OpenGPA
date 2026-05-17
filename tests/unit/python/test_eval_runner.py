"""Tests for ScenarioRunner.build_and_capture."""
from unittest.mock import MagicMock, patch

import pytest

from bhdr.eval.runner import ScenarioRunner
from bhdr.eval.scenario import ScenarioMetadata


def _make_scenario(repo_root, *, slug="my_scenario",
                   pkg="tests/eval/native-engine/godot/my_scenario"):
    """Build a ScenarioMetadata pinned to a real path under repo_root.

    `_bazel_target_for` derives the Bazel package from
    ``source_path.parent.relative_to(repo_root)``, so the path must
    resolve under repo_root for target derivation to succeed.
    """
    src_dir = repo_root / pkg
    src_dir.mkdir(parents=True, exist_ok=True)
    src = src_dir / "main.c"
    src.write_text("")
    return ScenarioMetadata(
        id=slug, title="t", bug_description="b", expected_output="e",
        actual_output="a", ground_truth_diagnosis="g", ground_truth_fix="f",
        difficulty=1, adversarial_principles=[], gpa_advantage="",
        source_path=str(src), binary_name=slug,
    )


def test_build_and_capture_returns_framebuffer_and_metadata(tmp_path):
    scen = _make_scenario(tmp_path, slug="r1_test",
                          pkg="tests/eval/native-engine/godot/r1_test")
    with patch("subprocess.run") as mock_run, \
         patch("bhdr.eval.runner._capture_via_rest") as mock_capture:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_capture.return_value = {
            "framebuffer_png": b"PNGDATA",
            "metadata": {"draw_call_count": 2, "draw_calls": []},
        }
        r = ScenarioRunner(
            gpa_base_url="http://127.0.0.1:18080",
            gpa_token="t",
            shim_path="/path/libgpa_gl.so",
            bazel_bin="bazel",
            repo_root=str(tmp_path),
        )
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.terminate.return_value = None
            mock_proc.wait.return_value = None
            mock_popen.return_value = mock_proc
            result = r.build_and_capture(scen)

    assert result["framebuffer_png"] == b"PNGDATA"
    assert result["metadata"]["draw_call_count"] == 2


def test_build_and_capture_uses_nested_taxonomy_target(tmp_path):
    """Regression: scenarios live at //tests/eval/<cat>/<fw>/<slug>:<slug>,
    not the legacy //tests/eval:<slug>. R12 archived eval reported "live
    capture unavailable" for all 14 with_gla scenarios because the runner
    asked for the wrong package."""
    scen = _make_scenario(tmp_path, slug="my_scenario",
                          pkg="tests/eval/native-engine/godot/my_scenario")
    with patch("subprocess.run") as mock_run, \
         patch("bhdr.eval.runner._capture_via_rest") as mock_capture:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_capture.return_value = {
            "framebuffer_png": b"",
            "metadata": {"draw_call_count": 0, "draw_calls": []},
        }
        r = ScenarioRunner(
            gpa_base_url="http://127.0.0.1:18080",
            gpa_token="tok",
            shim_path="/shim.so",
            bazel_bin="bazel",
            repo_root=str(tmp_path),
        )
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            r.build_and_capture(scen)

    mock_run.assert_called_once_with(
        ["bazel", "build",
         "//tests/eval/native-engine/godot/my_scenario:my_scenario"],
        cwd=str(tmp_path),
        check=True,
    )

    popen_cmd = mock_popen.call_args[0][0]
    assert popen_cmd[0] == "xvfb-run"
    assert popen_cmd[-1].endswith(
        "bazel-bin/tests/eval/native-engine/godot/my_scenario/my_scenario"
    )

    mock_capture.assert_called_once_with("http://127.0.0.1:18080", "tok")


def test_build_and_capture_terminates_proc_on_success(tmp_path):
    scen = _make_scenario(tmp_path, slug="s1",
                          pkg="tests/eval/native-engine/godot/s1")
    with patch("subprocess.run") as mock_run, \
         patch("bhdr.eval.runner._capture_via_rest") as mock_capture:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_capture.return_value = {
            "framebuffer_png": b"X",
            "metadata": {"draw_call_count": 1, "draw_calls": []},
        }
        r = ScenarioRunner(repo_root=str(tmp_path))
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_popen.return_value = mock_proc
            r.build_and_capture(scen)

    mock_proc.terminate.assert_called_once()
    mock_proc.wait.assert_called_once()


def test_build_scenario_uses_nested_taxonomy_target(tmp_path):
    """`build_scenario` (used by the eval harness's run_with_capture) must
    also derive the nested taxonomy package — not just `build_and_capture`."""
    scen = _make_scenario(tmp_path, slug="harness_test",
                          pkg="tests/eval/web-3d/three.js/harness_test")
    bin_path = (tmp_path / "bazel-bin" / "tests" / "eval" / "web-3d" /
                "three.js" / "harness_test" / "harness_test")
    bin_path.parent.mkdir(parents=True, exist_ok=True)
    bin_path.write_text("")  # pretend the build emitted the binary

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        r = ScenarioRunner(repo_root=str(tmp_path))
        out = r.build_scenario(scen)

    mock_run.assert_called_once()
    target = mock_run.call_args[0][0][2]
    assert target == "//tests/eval/web-3d/three.js/harness_test:harness_test"
    assert out == str(bin_path)


def test_build_scenario_raises_clearly_when_no_source_path(tmp_path):
    """Mined scenarios without synthetic reproducers (no main.c) carry
    source_path="" — the runner should raise FileNotFoundError with a
    clear message rather than failing inside Bazel."""
    s = ScenarioMetadata(
        id="rfc2ac5_no_source", title="t", bug_description="b",
        expected_output="e", actual_output="a", ground_truth_diagnosis="g",
        ground_truth_fix="f", difficulty=1, adversarial_principles=[],
        gpa_advantage="", source_path="", binary_name="rfc2ac5_no_source",
    )
    r = ScenarioRunner(repo_root=str(tmp_path))
    with pytest.raises(FileNotFoundError, match="no source_path"):
        r.build_scenario(s)
