import subprocess
from unittest.mock import patch, MagicMock
import pytest
from gpa.eval.curation.llm_client import LLMClient, ClaudeCodeLLMClient, CodexCliLLMClient, LLMResponse

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


def test_claude_code_client_invokes_cli():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="Response text\n", returncode=0,
                                           stderr="")
        client = ClaudeCodeLLMClient()
        resp = client.complete(
            system="sys",
            messages=[{"role": "user", "content": "hello"}],
        )
    assert isinstance(resp, LLMResponse)
    assert resp.text == "Response text"
    assert resp.input_tokens == 0
    call = mock_run.call_args
    argv = call.args[0]
    assert argv[0] == "claude"
    assert "-p" in argv


def test_claude_code_client_handles_multi_block_user_content():
    """Multi-modal content lists: only text blocks are extracted (images skipped)."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="ok", returncode=0, stderr="")
        client = ClaudeCodeLLMClient()
        client.complete(
            system="sys",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "t1"},
                {"type": "image", "source": {"type": "base64", "data": "..."}},
                {"type": "text", "text": "t2"},
            ]}],
        )
        # The prompt passed as stdin should include t1 and t2 but not the image.
        kwargs = mock_run.call_args.kwargs
        stdin = kwargs.get("input", "")
        assert "t1" in stdin and "t2" in stdin
        assert "base64" not in stdin


def test_codex_cli_client_shells_out(monkeypatch):
    captured = {}
    def fake_run(argv, *, input, capture_output, text, timeout, check):
        captured["argv"] = argv
        captured["input"] = input
        return subprocess.CompletedProcess(argv, 0, "hello world\n", "")
    monkeypatch.setattr(subprocess, "run", fake_run)
    client = CodexCliLLMClient()
    resp = client.complete(
        system="be brief",
        messages=[{"role": "user", "content": "say hi"}],
    )
    assert resp.text == "hello world"
    assert captured["argv"][0] == "codex"
    assert "exec" in captured["argv"]
    assert "--skip-git-repo-check" in captured["argv"]
    assert "be brief" in captured["input"]
    assert "say hi" in captured["input"]


def test_codex_cli_client_propagates_failure(monkeypatch):
    def fake_run(*a, **kw):
        raise subprocess.CalledProcessError(2, ["codex"], stderr="boom")
    monkeypatch.setattr(subprocess, "run", fake_run)
    client = CodexCliLLMClient()
    with pytest.raises(RuntimeError, match="codex CLI failed"):
        client.complete(system="", messages=[{"role": "user", "content": "x"}])
