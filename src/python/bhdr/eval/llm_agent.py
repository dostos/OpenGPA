"""Compatibility shim — moved to bhdr.eval.agents.api_agent.

This module exists to keep existing imports of ``bhdr.eval.llm_agent``
working after Task 17 of the cli/eval refactor. New code should import
from ``bhdr.eval.agents`` directly.

Note: patch targets for unit tests have been updated to point at
``bhdr.eval.agents.api_agent`` where the actual implementations live.
"""
from __future__ import annotations

import warnings

from bhdr.eval.agents.api_agent import (
    ApiAgent as EvalAgent,
    GpaToolExecutor,
    GPA_TOOLS,
    CODE_ONLY_TOOLS,
    SNAPSHOT_TOOLS,
    build_agent_fn,
)
from bhdr.eval.agents.base import AgentResult

warnings.warn(
    "bhdr.eval.llm_agent is deprecated; import from bhdr.eval.agents",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "EvalAgent",
    "GpaToolExecutor",
    "GPA_TOOLS",
    "CODE_ONLY_TOOLS",
    "SNAPSHOT_TOOLS",
    "build_agent_fn",
    "AgentResult",
]
