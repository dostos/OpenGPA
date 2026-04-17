import json
import subprocess
from unittest.mock import patch, MagicMock
from gla.eval.curation.discover import GitHubSearch, DiscoveryCandidate, Discoverer, DEFAULT_QUERIES
from gla.eval.curation.coverage_log import CoverageLog, CoverageEntry

def _fake_gh_result():
    return json.dumps({
        "total_count": 2,
        "items": [
            {"html_url": "https://github.com/mrdoob/three.js/issues/111",
             "title": "Texture broken", "labels": [{"name": "Rendering"}],
             "created_at": "2024-02-01T00:00:00Z"},
            {"html_url": "https://github.com/mrdoob/three.js/issues/222",
             "title": "Shader z-fight", "labels": [{"name": "Rendering"}],
             "created_at": "2024-02-02T00:00:00Z"},
        ],
    })

def test_github_search_issues_parses_gh_output():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=_fake_gh_result(), returncode=0)
        search = GitHubSearch()
        results = search.search_issues('repo:mrdoob/three.js label:"Rendering"', per_page=5)
    assert len(results) == 2
    assert results[0].url == "https://github.com/mrdoob/three.js/issues/111"
    assert results[0].source_type == "issue"
    assert results[0].title == "Texture broken"

def test_github_search_uses_gh_api():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=_fake_gh_result(), returncode=0)
        GitHubSearch().search_issues("q", per_page=5)
        call = mock_run.call_args
        argv = call.args[0]
        assert argv[0] == "gh"
        assert argv[1] == "api"
        assert any("search/issues" in a for a in argv)

def test_discoverer_dedupes_already_reviewed_urls(tmp_path):
    log = CoverageLog(tmp_path / "log.jsonl")
    log.append(CoverageEntry(
        issue_url="https://github.com/x/y/issues/1",
        reviewed_at="2026-04-17T10:00:00Z", source_type="issue",
        triage_verdict="out_of_scope", root_cause_fingerprint=None,
        outcome="rejected", scenario_id=None, tier=None,
        rejection_reason="out_of_scope_compile_error",
        predicted_helps=None, observed_helps=None,
        failure_mode=None, eval_summary=None))

    class FakeSearch:
        def search_issues(self, q, per_page=30):
            return [
                DiscoveryCandidate(url="https://github.com/x/y/issues/1",
                                   source_type="issue", title="dup"),
                DiscoveryCandidate(url="https://github.com/x/y/issues/2",
                                   source_type="issue", title="new"),
            ]
        def search_commits(self, q, per_page=30):
            return []

    d = Discoverer(search=FakeSearch(), coverage_log=log,
                   queries={"issue": ["q1"], "commit": []}, batch_quota=10)
    candidates = d.run()
    urls = [c.url for c in candidates]
    assert "https://github.com/x/y/issues/2" in urls
    assert "https://github.com/x/y/issues/1" not in urls

def test_discoverer_respects_batch_quota(tmp_path):
    class FakeSearch:
        def search_issues(self, q, per_page=30):
            return [DiscoveryCandidate(url=f"https://x/{i}",
                                        source_type="issue", title="t")
                    for i in range(100)]
        def search_commits(self, q, per_page=30):
            return []

    log = CoverageLog(tmp_path / "log.jsonl")
    d = Discoverer(search=FakeSearch(), coverage_log=log,
                   queries={"issue": ["q1"], "commit": []}, batch_quota=5)
    candidates = d.run()
    assert len(candidates) == 5
