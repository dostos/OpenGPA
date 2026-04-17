import json
from unittest.mock import patch, MagicMock
from gla.eval.curation.triage import Triage, TriageResult, IssueThread, fetch_issue_thread
from gla.eval.curation.llm_client import LLMResponse

def _fake_response(text: str) -> LLMResponse:
    return LLMResponse(text=text, input_tokens=100, output_tokens=50,
                       cache_creation_input_tokens=0, cache_read_input_tokens=0,
                       stop_reason="end_turn")

def test_triage_parses_in_scope_response():
    llm = MagicMock()
    llm.complete.return_value = _fake_response(
        '```json\n{"triage_verdict":"in_scope",'
        '"root_cause_fingerprint":"state_leak:tex_binding_persists",'
        '"rejection_reason":null,'
        '"summary":"Texture binding leaks between two draw calls"}\n```'
    )
    t = Triage(llm_client=llm)
    thread = IssueThread(url="https://x/1", title="Tex leak",
                         body="second quad gets first texture",
                         comments=[])
    result = t.triage(thread)
    assert result.verdict == "in_scope"
    assert result.fingerprint == "state_leak:tex_binding_persists"
    assert result.rejection_reason is None

def test_triage_parses_out_of_scope_response():
    llm = MagicMock()
    llm.complete.return_value = _fake_response(
        '```json\n{"triage_verdict":"out_of_scope",'
        '"root_cause_fingerprint":"other:n_a",'
        '"rejection_reason":"out_of_scope_compile_error",'
        '"summary":"GLSL compile error"}\n```'
    )
    t = Triage(llm_client=llm)
    thread = IssueThread(url="https://x/2", title="compile fail",
                         body="syntax error in shader", comments=[])
    result = t.triage(thread)
    assert result.verdict == "out_of_scope"
    assert result.rejection_reason == "out_of_scope_compile_error"

def test_fetch_issue_thread_calls_gh_api():
    issue_json = '{"title":"x","body":"b","number":42}'
    comments_json = '[{"body":"c1"},{"body":"c2"}]'
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(stdout=issue_json, returncode=0),
            MagicMock(stdout=comments_json, returncode=0),
        ]
        thread = fetch_issue_thread("https://github.com/owner/repo/issues/42")

    assert thread.title == "x"
    assert thread.body == "b"
    assert thread.comments == ["c1", "c2"]


def test_triage_rejects_invalid_fingerprint_category():
    llm = MagicMock()
    llm.complete.return_value = _fake_response(
        '```json\n{"triage_verdict":"in_scope",'
        '"root_cause_fingerprint":"invented_category:foo",'
        '"rejection_reason":null,"summary":"x"}\n```'
    )
    t = Triage(llm_client=llm)
    thread = IssueThread(url="https://x/3", title="t", body="b", comments=[])
    result = t.triage(thread)
    # Parser normalizes unknown categories to "other"
    assert result.fingerprint.startswith("other:")
