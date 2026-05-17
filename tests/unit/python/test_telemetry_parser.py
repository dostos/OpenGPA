"""Tests for :mod:`bhdr.eval.telemetry`.

The parser consumes ``claude -p --output-format stream-json`` transcripts.
The fixture in ``fixtures/stream_json_sample.jsonl`` was hand-crafted to match
a real transcript captured with:

    echo hi | claude -p --output-format stream-json --verbose \
        --dangerously-skip-permissions

Schema details (Claude Code 2.1.x):
  - ``system`` / ``subtype=init`` opens the session.
  - ``assistant`` events carry ``message.content`` (list of content blocks) and
    ``message.usage`` with ``input_tokens``, ``output_tokens``,
    ``cache_read_input_tokens``, ``cache_creation_input_tokens``.
  - A ``tool_use`` content block has ``name`` and ``input``.
  - ``result`` (subtype=success) closes the stream with ``total_cost_usd`` and
    ``num_turns``.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from bhdr.eval.telemetry import parse_stream_json


FIXTURE = Path(__file__).parent / "fixtures" / "stream_json_sample.jsonl"


def _write_lines(tmp_path: Path, name: str, lines: list[str]) -> Path:
    p = tmp_path / name
    p.write_text("\n".join(lines) + ("\n" if lines else ""))
    return p


def test_empty_stream_returns_zeros(tmp_path):
    p = _write_lines(tmp_path, "empty.jsonl", [])
    out = parse_stream_json(str(p))
    assert out["num_turns"] == 0
    assert out["total_cost_usd"] == 0.0
    assert out["tool_calls"] == []
    assert out["tool_counts"] == {}
    assert out["total_tokens_in"] == 0
    assert out["total_tokens_out"] == 0
    assert out["cache_read"] == 0
    assert out["cache_creation"] == 0
    assert out["result_seen"] is False


def test_missing_file_returns_zeros(tmp_path):
    out = parse_stream_json(str(tmp_path / "nope.jsonl"))
    assert out["num_turns"] == 0
    assert out["tool_calls"] == []


def test_single_tool_call_counted(tmp_path):
    lines = [
        json.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "id": "a", "name": "Read",
                             "input": {"file_path": "/tmp/x"}}],
                "usage": {"input_tokens": 1, "output_tokens": 2,
                           "cache_read_input_tokens": 3,
                           "cache_creation_input_tokens": 4},
            },
        }),
        json.dumps({"type": "result", "subtype": "success", "num_turns": 1,
                     "total_cost_usd": 0.5, "result": "ok"}),
    ]
    p = _write_lines(tmp_path, "single.jsonl", lines)
    out = parse_stream_json(str(p))
    assert out["tool_counts"] == {"Read": 1}
    assert out["tool_calls"] == [{"tool": "Read", "input_summary": "/tmp/x"}]
    assert out["num_turns"] == 1
    assert out["total_cost_usd"] == 0.5
    assert out["total_tokens_in"] == 1
    assert out["total_tokens_out"] == 2
    assert out["cache_read"] == 3
    assert out["cache_creation"] == 4
    assert out["result_seen"] is True
    assert out["result_text"] == "ok"


def test_bhdr_bash_classified_as_gpa(tmp_path):
    lines = [
        json.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Bash",
                             "input": {"command": "gpa report --frame 1 --json"}}],
                "usage": {},
            },
        }),
    ]
    p = _write_lines(tmp_path, "gpa.jsonl", lines)
    out = parse_stream_json(str(p))
    assert out["tool_counts"] == {"gpa": 1}
    assert out["tool_calls"][0]["tool"] == "gpa"


def test_bhdr_piped_still_classified_as_gpa(tmp_path):
    # gpa appearing inside a compound command — subcommand regex still catches it.
    lines = [
        json.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Bash",
                             "input": {"command": "cd /tmp && gpa check feedback --frame 3"}}],
                "usage": {},
            },
        }),
    ]
    p = _write_lines(tmp_path, "bhdr_pipe.jsonl", lines)
    out = parse_stream_json(str(p))
    assert out["tool_counts"] == {"gpa": 1}


def test_curl_bhdr_bash_classified_as_curl(tmp_path):
    lines = [
        json.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Bash",
                             "input": {"command": "curl -sH \"Authorization: Bearer X\" http://127.0.0.1:18080/api/v1/frames/1"}}],
                "usage": {},
            },
        }),
    ]
    p = _write_lines(tmp_path, "curl.jsonl", lines)
    out = parse_stream_json(str(p))
    assert out["tool_counts"] == {"curl": 1}


def test_unrelated_bash_stays_bash(tmp_path):
    lines = [
        json.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Bash",
                             "input": {"command": "ls -la"}}],
                "usage": {},
            },
        }),
    ]
    p = _write_lines(tmp_path, "bash.jsonl", lines)
    out = parse_stream_json(str(p))
    assert out["tool_counts"] == {"Bash": 1}


def test_curl_without_bhdr_port_stays_bash(tmp_path):
    # curl to some other site — not counted as bhdr-curl.
    lines = [
        json.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Bash",
                             "input": {"command": "curl https://example.com"}}],
                "usage": {},
            },
        }),
    ]
    p = _write_lines(tmp_path, "curl_other.jsonl", lines)
    out = parse_stream_json(str(p))
    # falls through to Bash
    assert out["tool_counts"] == {"Bash": 1}


def test_malformed_lines_skipped(tmp_path):
    lines = [
        "not json at all",
        json.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Grep",
                             "input": {"pattern": "foo"}}],
                "usage": {},
            },
        }),
        "also not json",
        json.dumps({"type": "result", "subtype": "success", "num_turns": 1,
                     "total_cost_usd": 0.0}),
    ]
    p = _write_lines(tmp_path, "mal.jsonl", lines)
    out = parse_stream_json(str(p))
    assert out["tool_counts"] == {"Grep": 1}
    assert out["num_turns"] == 1


def test_fixture_parses(tmp_path):
    """End-to-end check on the hand-crafted fixture."""
    out = parse_stream_json(str(FIXTURE))
    # 5 tool_use blocks: gpa report, Read, curl, Grep, Bash ls
    assert out["tool_counts"] == {"gpa": 1, "Read": 1, "curl": 1,
                                    "Grep": 1, "Bash": 1}
    assert out["num_turns"] == 4
    assert out["total_cost_usd"] == pytest.approx(0.0123)
    assert out["session_id"] == "sess-abc"
    # Fixture's result-event usage block is authoritative (overrides the
    # per-turn accumulators). Values chosen to equal the per-turn sums so
    # the fixture remains consistent.
    assert out["total_tokens_in"] == 35
    assert out["total_tokens_out"] == 63
    assert out["cache_read"] == 500
    assert out["cache_creation"] == 200
    # ordering preserved
    tools_in_order = [t["tool"] for t in out["tool_calls"]]
    assert tools_in_order == ["gpa", "Read", "curl", "Grep", "Bash"]


def test_multi_assistant_tokens_accumulate(tmp_path):
    lines = [
        json.dumps({"type": "assistant",
                     "message": {"content": [],
                                   "usage": {"input_tokens": 10, "output_tokens": 5,
                                              "cache_read_input_tokens": 1,
                                              "cache_creation_input_tokens": 2}}}),
        json.dumps({"type": "assistant",
                     "message": {"content": [],
                                   "usage": {"input_tokens": 7, "output_tokens": 3,
                                              "cache_read_input_tokens": 4,
                                              "cache_creation_input_tokens": 8}}}),
    ]
    p = _write_lines(tmp_path, "multi.jsonl", lines)
    out = parse_stream_json(str(p))
    assert out["total_tokens_in"] == 17
    assert out["total_tokens_out"] == 8
    assert out["cache_read"] == 5
    assert out["cache_creation"] == 10
