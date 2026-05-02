import pytest
from gpa.eval.agents.factory import build_agent_fn


def test_build_api_returns_callable():
    fn = build_agent_fn("api", model="claude-haiku-4-5")
    assert callable(fn)


def test_build_claude_cli_returns_callable():
    fn = build_agent_fn("claude-cli")
    assert callable(fn)


def test_build_codex_cli_returns_callable():
    fn = build_agent_fn("codex-cli")
    assert callable(fn)


def test_build_unknown_backend_raises():
    with pytest.raises(ValueError, match="unknown agent backend"):
        build_agent_fn("gpt-cli")
