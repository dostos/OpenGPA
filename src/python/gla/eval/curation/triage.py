from __future__ import annotations
import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional

from gla.eval.curation.llm_client import LLMClient
from gla.eval.curation.prompts import load_prompt

_VALID_CATEGORIES = {
    "state_leak", "uniform_lifecycle", "matrix_math", "numeric_precision",
    "depth_precision", "winding_culling", "sync", "shader_compile",
    "bind_point_collision", "other",
}

_VALID_VERDICTS = {"in_scope", "out_of_scope", "ambiguous"}

_VALID_REJECTIONS = {
    None, "out_of_scope_compile_error", "out_of_scope_not_rendering_bug",
    "out_of_scope_insufficient_info", "not_reproducible", "non_english",
}


@dataclass
class IssueThread:
    url: str
    title: str
    body: str
    comments: list[str] = field(default_factory=list)


@dataclass
class TriageResult:
    verdict: str
    fingerprint: str
    rejection_reason: Optional[str]
    summary: str


class Triage:
    def __init__(self, llm_client: LLMClient, model: str = "claude-opus-4-7"):
        self._llm = llm_client
        self._system = load_prompt("triage_system")

    def triage(self, thread: IssueThread) -> TriageResult:
        user = self._format_thread(thread)
        resp = self._llm.complete(
            system=self._system,
            messages=[{"role": "user", "content": user}],
        )
        parsed = self._parse_json_block(resp.text)
        return self._normalize(parsed)

    def _format_thread(self, t: IssueThread) -> str:
        parts = [f"URL: {t.url}", f"Title: {t.title}", "", "Body:", t.body]
        for i, c in enumerate(t.comments):
            parts.extend(["", f"Comment {i+1}:", c])
        return "\n".join(parts)

    @staticmethod
    def _parse_json_block(text: str) -> dict:
        m = re.search(r"```json\s*\n(.+?)\n```", text, re.DOTALL)
        raw = m.group(1) if m else text
        return json.loads(raw)

    def _normalize(self, d: dict) -> TriageResult:
        verdict = d.get("triage_verdict", "ambiguous")
        if verdict not in _VALID_VERDICTS:
            verdict = "ambiguous"
        fp = d.get("root_cause_fingerprint", "other:unknown")
        category, _, spec = fp.partition(":")
        if category not in _VALID_CATEGORIES:
            category, spec = "other", spec or "unknown"
        fp = f"{category}:{spec or 'unknown'}"
        reason = d.get("rejection_reason")
        if reason not in _VALID_REJECTIONS:
            reason = None
        return TriageResult(verdict=verdict, fingerprint=fp,
                            rejection_reason=reason,
                            summary=d.get("summary", "")[:200])


def fetch_thread(url: str) -> IssueThread:
    """Dispatch to fetch_issue_thread or fetch_commit_thread based on URL."""
    if "/commit/" in url:
        return fetch_commit_thread(url)
    return fetch_issue_thread(url)


def fetch_issue_thread(url: str) -> IssueThread:
    m = re.search(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", url)
    if not m:
        raise ValueError(f"Not a GitHub issue URL: {url}")
    owner, repo, number = m.group(1), m.group(2), m.group(3)

    issue_proc = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/issues/{number}"],
        capture_output=True, text=True, check=True,
    )
    issue = json.loads(issue_proc.stdout)

    comments_proc = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/issues/{number}/comments"],
        capture_output=True, text=True, check=True,
    )
    comments = json.loads(comments_proc.stdout)

    return IssueThread(
        url=url,
        title=issue.get("title", ""),
        body=issue.get("body", "") or "",
        comments=[c.get("body", "") for c in comments],
    )


def fetch_commit_thread(url: str) -> IssueThread:
    """Fetch a commit's message + diff as an IssueThread.

    Commit URL format: https://github.com/owner/repo/commit/<sha>
    Uses `gh api repos/{owner}/{repo}/commits/{sha}` which returns
    {sha, commit: {message, author}, files: [{filename, patch, ...}], ...}
    """
    m = re.search(r"github\.com/([^/]+)/([^/]+)/commit/([a-f0-9]+)", url)
    if not m:
        raise ValueError(f"Not a GitHub commit URL: {url}")
    owner, repo, sha = m.group(1), m.group(2), m.group(3)

    proc = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/commits/{sha}"],
        capture_output=True, text=True, check=True,
    )
    commit_data = json.loads(proc.stdout)

    message = commit_data.get("commit", {}).get("message", "")
    # Title is first line of message; body is rest
    lines = message.split("\n", 1)
    title = lines[0][:200]
    body = lines[1].strip() if len(lines) > 1 else ""

    # Extract diffs from `files`, but truncate aggressively — we only need enough
    # for Claude to see the fix pattern. Cap total diff to ~20KB.
    files = commit_data.get("files") or []
    diff_parts: list[str] = []
    total_size = 0
    MAX_DIFF_BYTES = 20000
    for f in files:
        patch = f.get("patch") or ""
        if not patch:
            continue
        filename = f.get("filename", "?")
        chunk = f"--- {filename}\n{patch}\n"
        if total_size + len(chunk) > MAX_DIFF_BYTES:
            remaining = MAX_DIFF_BYTES - total_size
            if remaining > 200:
                chunk = chunk[:remaining] + "\n... [truncated]"
                diff_parts.append(chunk)
            break
        diff_parts.append(chunk)
        total_size += len(chunk)

    diff = "\n".join(diff_parts)
    # Use "body" for commit message body, put diff into comments[] so the
    # existing Triage._format_thread renders it cleanly.
    comments = [f"=== Diff ===\n{diff}"] if diff else []

    return IssueThread(url=url, title=title, body=body, comments=comments)
