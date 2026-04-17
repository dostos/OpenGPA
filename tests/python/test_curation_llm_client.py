from unittest.mock import MagicMock
from gla.eval.curation.llm_client import LLMClient, LLMResponse

def test_llm_client_calls_anthropic_with_cache_control():
    fake_sdk = MagicMock()
    fake_sdk.messages.create.return_value = MagicMock(
        content=[MagicMock(text="response text")],
        usage=MagicMock(input_tokens=100, output_tokens=50,
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=0),
        stop_reason="end_turn",
    )

    client = LLMClient(sdk=fake_sdk, model="claude-opus-4-7")
    resp = client.complete(
        system="sys prompt",
        messages=[{"role": "user", "content": "user msg"}],
        cache_system=True,
    )

    assert isinstance(resp, LLMResponse)
    assert resp.text == "response text"
    assert resp.input_tokens == 100
    call = fake_sdk.messages.create.call_args
    kwargs = call.kwargs
    # System prompt was passed with cache_control ephemeral
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
