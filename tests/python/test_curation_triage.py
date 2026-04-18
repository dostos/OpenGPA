import json
from unittest.mock import patch, MagicMock
from gla.eval.curation.triage import Triage, TriageResult, IssueThread, fetch_issue_thread, fetch_commit_thread
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


def test_fetch_commit_thread_parses_commit_url():
    commit_json = json.dumps({
        "sha": "abc123",
        "commit": {
            "message": "fix: z-fighting in shadow pass\n\nRoot cause: depth bias was too small.",
            "author": {"date": "2025-01-01T00:00:00Z"},
        },
        "files": [
            {"filename": "src/shadow.c", "patch": "@@ -10,1 +10,1 @@\n-  depth_bias = 0.001;\n+  depth_bias = 0.01;"},
        ],
    })
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=commit_json, returncode=0)
        thread = fetch_commit_thread("https://github.com/owner/repo/commit/abc123")
    assert thread.title == "fix: z-fighting in shadow pass"
    assert "depth bias was too small" in thread.body
    assert any("depth_bias = 0.01" in c for c in thread.comments)


def test_fetch_commit_thread_rejects_non_commit_url():
    import pytest
    with pytest.raises(ValueError, match="Not a GitHub commit URL"):
        fetch_commit_thread("https://github.com/owner/repo/issues/42")


def test_fetch_thread_dispatches_by_url_shape():
    issue_stub = MagicMock()
    commit_stub = MagicMock()
    issue_stub.return_value = IssueThread(url="issue", title="i", body="b")
    commit_stub.return_value = IssueThread(url="commit", title="c", body="b")

    import gla.eval.curation.triage as T
    with patch.object(T, "fetch_issue_thread", issue_stub), \
         patch.object(T, "fetch_commit_thread", commit_stub):
        r1 = T.fetch_thread("https://github.com/o/r/issues/1")
        r2 = T.fetch_thread("https://github.com/o/r/commit/abc")
    assert r1.title == "i"
    assert r2.title == "c"


def test_fetch_commit_thread_truncates_large_diffs():
    huge_patch = "\n".join(f"+ line {i}" for i in range(3000))  # ~36KB
    commit_json = json.dumps({
        "sha": "abc",
        "commit": {"message": "fix", "author": {"date": "..."}},
        "files": [{"filename": "big.c", "patch": huge_patch}],
    })
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=commit_json, returncode=0)
        thread = fetch_commit_thread("https://github.com/o/r/commit/abc")
    # Diff in comments should be capped
    all_comments = "\n".join(thread.comments)
    assert len(all_comments) <= 21000  # 20k cap + some overhead
    assert "truncated" in all_comments
