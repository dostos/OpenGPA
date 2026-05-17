"""Tests for CliBackendSpec and CliRunMetrics dataclasses."""
import pytest
from bhdr.eval.agents.cli_spec import CliBackendSpec, CliRunMetrics


def _dummy_parser(stdout: str, stderr: str) -> CliRunMetrics:
    return CliRunMetrics(
        diagnosis="ok",
        input_tokens=1,
        output_tokens=2,
        tool_calls=0,
        num_turns=1,
    )


class TestCliRunMetrics:
    def test_defaults_tool_sequence_to_empty_tuple(self):
        m = CliRunMetrics(
            diagnosis="x", input_tokens=0, output_tokens=0, tool_calls=0, num_turns=0
        )
        assert m.tool_sequence == ()

    def test_is_frozen(self):
        m = CliRunMetrics(
            diagnosis="x", input_tokens=0, output_tokens=0, tool_calls=0, num_turns=0
        )
        with pytest.raises(Exception):
            m.diagnosis = "y"  # type: ignore[misc]

    def test_hashable(self):
        m = CliRunMetrics(
            diagnosis="d",
            input_tokens=10,
            output_tokens=5,
            tool_calls=2,
            num_turns=1,
            tool_sequence=("gpa frames", "gpa drawcalls"),
        )
        assert hash(m) is not None
        s = {m}
        assert m in s

    def test_tool_sequence_stored(self):
        m = CliRunMetrics(
            diagnosis="d",
            input_tokens=0,
            output_tokens=0,
            tool_calls=1,
            num_turns=1,
            tool_sequence=("gpa frames",),
        )
        assert m.tool_sequence == ("gpa frames",)


class TestCliBackendSpec:
    def test_parse_run_is_callable(self):
        spec = CliBackendSpec(
            name="claude-cli",
            binary="claude",
            base_args=("-p", "--output-format", "stream-json"),
            parse_run=_dummy_parser,
        )
        assert callable(spec.parse_run)
        result = spec.parse_run("", "")
        assert isinstance(result, CliRunMetrics)

    def test_is_frozen(self):
        spec = CliBackendSpec(
            name="codex-cli",
            binary="codex",
            base_args=("exec", "--json"),
            parse_run=_dummy_parser,
        )
        with pytest.raises(Exception):
            spec.name = "other"  # type: ignore[misc]

    def test_hashable(self):
        spec = CliBackendSpec(
            name="claude-cli",
            binary="claude",
            base_args=("-p",),
            parse_run=_dummy_parser,
        )
        assert hash(spec) is not None

    def test_default_timeout(self):
        spec = CliBackendSpec(
            name="claude-cli",
            binary="claude",
            base_args=(),
            parse_run=_dummy_parser,
        )
        assert spec.timeout_sec == 1800

    def test_custom_timeout(self):
        spec = CliBackendSpec(
            name="claude-cli",
            binary="claude",
            base_args=(),
            parse_run=_dummy_parser,
            timeout_sec=600,
        )
        assert spec.timeout_sec == 600
