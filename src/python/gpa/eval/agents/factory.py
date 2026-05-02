"""Factory for selecting eval agent backend by name."""
from __future__ import annotations
from typing import Callable, Optional

from gpa.eval.agents.base import AgentBackend, AgentResult


AgentFn = Callable
"""Six-tuple-returning agent_fn matching gpa.eval.harness.AgentFn."""


def build_agent_fn(
    backend: str,
    *,
    model: Optional[str] = None,
    max_turns: int = 20,
    api_key: Optional[str] = None,
) -> AgentFn:
    """Return an agent_fn for the harness driven by the requested backend.

    Backends:
      - "api"        : Anthropic SDK with native tool use (ApiAgent).
      - "claude-cli" : claude CLI driving its own loop, calling gpa via shell.
      - "codex-cli"  : codex CLI driving its own loop, calling gpa via shell.
    """
    if backend == "api":
        from gpa.eval.agents.api_agent import build_agent_fn as _api_fn
        return _api_fn(
            model=model or "claude-sonnet-4-5",
            max_turns=max_turns,
            api_key=api_key,
        )
    if backend == "claude-cli":
        from gpa.eval.agents.cli_agent import CliAgent, CLAUDE_CLI_SPEC
        return _wrap(CliAgent(spec=CLAUDE_CLI_SPEC, model=model))
    if backend == "codex-cli":
        from gpa.eval.agents.cli_agent import CliAgent, CODEX_CLI_SPEC
        return _wrap(CliAgent(spec=CODEX_CLI_SPEC, model=model))
    raise ValueError(f"unknown agent backend: {backend!r}")


def _wrap(agent: AgentBackend) -> AgentFn:
    def fn(scenario, mode, tools):
        result: AgentResult = agent.run(scenario, mode, tools)
        return (
            result.diagnosis,
            result.input_tokens,
            result.output_tokens,
            result.tool_calls,
            result.num_turns,
            result.time_seconds,
        )
    return fn
