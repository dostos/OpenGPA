"""Backend spec + metrics dataclasses for CLI-driven eval agents."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class CliRunMetrics:
    diagnosis: str
    input_tokens: int
    output_tokens: int
    tool_calls: int
    num_turns: int
    tool_sequence: tuple[str, ...] = ()


@dataclass(frozen=True)
class CliBackendSpec:
    name: str                                  # "claude-cli" | "codex-cli"
    binary: str
    base_args: tuple[str, ...]
    parse_run: Callable[[str, str], CliRunMetrics]
    timeout_sec: int = 1800
