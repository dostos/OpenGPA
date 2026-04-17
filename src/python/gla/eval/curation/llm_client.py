from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    stop_reason: str


class LLMClient:
    def __init__(self, sdk: Any, model: str = "claude-opus-4-7",
                 max_tokens: int = 4096):
        self._sdk = sdk
        self._model = model
        self._max_tokens = max_tokens

    def complete(
        self,
        system: str,
        messages: list[dict],
        cache_system: bool = True,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        sys_blocks: list[dict] = [{"type": "text", "text": system}]
        if cache_system:
            sys_blocks[0]["cache_control"] = {"type": "ephemeral"}

        resp = self._sdk.messages.create(
            model=self._model,
            max_tokens=max_tokens or self._max_tokens,
            system=sys_blocks,
            messages=messages,
        )
        text = "".join(
            getattr(c, "text", "") for c in resp.content
            if getattr(c, "type", "text") in ("text", None)
            or not isinstance(getattr(c, "type", "text"), str)
        )
        return LLMResponse(
            text=text,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            cache_creation_input_tokens=getattr(
                resp.usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_input_tokens=getattr(
                resp.usage, "cache_read_input_tokens", 0) or 0,
            stop_reason=resp.stop_reason,
        )

    @classmethod
    def from_env(cls, model: str = "claude-opus-4-7") -> "LLMClient":
        import anthropic
        return cls(sdk=anthropic.Anthropic(), model=model)
