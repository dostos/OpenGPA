# Single-Path Mining Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace four overlapping curation CLIs (`mine_hard_cases`, `mine_taxonomy`, `pipeline`, `measure_yield`) with a single `gpa.eval.curation.run` entry point that runs the discover → commit DAG end-to-end with no human gate, persists every candidate's per-phase outcome to a queryable per-run JSONL, and uses LLMs only for the `evaluate` agent step (opt-in).

**Architecture:** A new `run.py` orchestrates 3 public phases (`SELECT`, `PRODUCE`, `JUDGE`) that internally call existing per-stage modules (`discover`, `triage` → repurposed as rules-only `classify_score`, `draft` → repurposed as deterministic `extract_draft`, `validate`, `run_eval`, `classify`, `commit`). The pipeline writes a per-run directory under `.eval-pipeline/runs/<run_id>/` containing a frozen `config.yaml`, a `journey.jsonl` (one row per discovered candidate with phase outcomes + token spend), the existing `IssueWorkdir` per-sub-step cache, and an auto-generated `summary.md`. Failures-as-steering: dropped candidates carry a specific `terminal_reason` so rule improvement is data-driven.

**Tech Stack:** Python 3.11 (Bazel-managed) for the production CLI; system Python 3.10 OK for pytest. Bazel for the build, pytest for tests, `pyyaml` for config, `dataclasses` + `json` for journey rows. No new third-party deps.

**Spec:** [`docs/superpowers/specs/2026-05-01-single-path-mining-design.md`](../specs/2026-05-01-single-path-mining-design.md)

---

## File Structure

**Create:**

| File | Responsibility |
|---|---|
| `src/python/bhdr/eval/curation/journey.py` | `JourneyRow` dataclass, per-run JSONL writer, terminal-reason vocabulary |
| `src/python/bhdr/eval/curation/run_dir.py` | Per-run directory layout (`.eval-pipeline/runs/<id>/…`), config-freezing, run-id generation |
| `src/python/bhdr/eval/curation/extract_draft.py` | Deterministic field extraction from issue body + fix-PR (replaces LLM `draft`) |
| `src/python/bhdr/eval/curation/summary.py` | Auto-rollup of `journey.jsonl` into `summary.md` |
| `src/python/bhdr/eval/curation/run.py` | The single CLI entry point; orchestrates SELECT → PRODUCE → JUDGE |
| `tests/unit/python/test_curation_journey.py` | Journey row + writer tests |
| `tests/unit/python/test_curation_run_dir.py` | Dir layout + run-id tests |
| `tests/unit/python/test_curation_extract_draft.py` | Extractor tests against real issue-body fixtures |
| `tests/unit/python/test_curation_summary.py` | Summary rollup tests |
| `tests/unit/python/test_curation_run.py` | End-to-end CLI tests |
| `docs/superpowers/eval/single-path-mining-smoke-test.md` | Smoke-test results + O1 decision record |

**Modify:**

| File | Change |
|---|---|
| `src/python/bhdr/eval/curation/mining_rules.yaml` | Add `triage_required` and `triage_reject` keyword rule sections (subsumes today's LLM triage) |
| `src/python/bhdr/eval/curation/classify.py` | Confirm rule-only (already is per its docstring); add `classify_helps` re-export if missing |
| `src/python/bhdr/eval/curation/coverage_log.py` | No code change; tests verify shape unchanged |
| `docs/superpowers/eval/framework-app-dev-hard-cases.md` | Replace `mine_taxonomy` invocation with `run` invocation |

**Delete:**

| File | Reason |
|---|---|
| `src/python/bhdr/eval/curation/mine_hard_cases.py` | Folded into `run.py` SELECT phase + new `extract_draft.py` |
| `src/python/bhdr/eval/curation/mine_taxonomy.py` | 4-line shim — gone with `mine_hard_cases` |
| `src/python/bhdr/eval/curation/measure_yield.py` | Yield reporting is now `summary.md` from a `--max-phase select` run |
| `src/python/bhdr/eval/curation/pipeline.py` | Replaced by `run.py` (per O7 decision: clean break, distinct file name) |
| `tests/unit/python/test_curation_mine_hard_cases.py` | Tests targeting deleted CLI |
| `tests/unit/python/test_curation_pipeline.py` | Tests targeting deleted CLI; replaced by `test_curation_run.py` |

---

## Sequencing Rationale

The plan front-loads schema/layout (Tasks 1–2), then builds the new deterministic stages bottom-up (Tasks 3–4), wires the orchestrator (Task 5), runs the smoke test that gates the O1 decision (Task 6), then performs the hard cut (Tasks 7–8) in one contiguous PR. Each task ends in a commit that leaves the tree green.

**Important:** Tasks 1–6 are additive — the existing pipeline keeps working throughout. The hard cut happens in Tasks 7–8 after smoke tests confirm the new path is viable.

---

### Task 1: Journey row + JSONL writer

**Files:**
- Create: `src/python/bhdr/eval/curation/journey.py`
- Test: `tests/unit/python/test_curation_journey.py`

- [ ] **Step 1.1: Write the failing test for `JourneyRow.to_dict()` shape**

```python
# tests/unit/python/test_curation_journey.py
from gpa.eval.curation.journey import JourneyRow, SelectOutcome, ProduceOutcome, JudgeOutcome, TokenSpend, TerminalReason

def test_journey_row_full_commit_shape():
    row = JourneyRow(
        url="https://github.com/x/y/issues/1",
        run_id="2026-05-01-143022-a3f2b1",
        discovered_at="2026-05-01T14:30:24Z",
        discovery_query="depthWrite transparent",
        select=SelectOutcome(deduped=True, fetched=True,
                              taxonomy_cell="web-3d/three.js",
                              score=7, score_reasons=["visual_symptom"],
                              selected=True),
        produce=ProduceOutcome(extracted=True, validated=True),
        judge=JudgeOutcome(with_gla_score=1.0, code_only_score=0.0,
                            helps_verdict="yes",
                            committed_as="r20_threejs_depth_write_transparent"),
        tokens=TokenSpend(triage=0, draft=0, evaluate=12500),
        cache_hit=False,
        terminal_phase="judge",
        terminal_reason=TerminalReason.COMMITTED.value,
    )
    d = row.to_dict()
    assert d["url"] == "https://github.com/x/y/issues/1"
    assert d["select"]["score"] == 7
    assert d["produce"]["extracted"] is True
    assert d["judge"]["committed_as"] == "r20_threejs_depth_write_transparent"
    assert d["tokens"]["total"] == 12500  # auto-computed
    assert d["terminal_phase"] == "judge"
    assert d["terminal_reason"] == "committed"

def test_journey_row_select_dropped_has_null_phases():
    row = JourneyRow.dropped_at_select(
        url="https://example.com/issue/2",
        run_id="r1",
        discovered_at="2026-05-01T14:30:24Z",
        discovery_query="q",
        select=SelectOutcome(deduped=True, fetched=True,
                              taxonomy_cell="web-3d/three.js",
                              score=1, score_reasons=["visual_symptom"],
                              selected=False),
        terminal_reason=TerminalReason.BELOW_MIN_SCORE.value,
    )
    d = row.to_dict()
    assert d["produce"] is None
    assert d["judge"] is None
    assert d["tokens"]["total"] == 0
    assert d["terminal_phase"] == "select"
    assert d["terminal_reason"] == "below_min_score"
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_journey.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'gpa.eval.curation.journey'`.

- [ ] **Step 1.3: Implement `JourneyRow` and dataclasses**

```python
# src/python/bhdr/eval/curation/journey.py
"""Per-candidate journey records for a single mining run.

One JourneyRow per discovered URL. Phase outcomes for skipped phases are
None. The row is the source of truth for both per-run reporting and
cross-run analysis (cat runs/*/journey.jsonl | jq).
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional


class TerminalReason(str, Enum):
    # SELECT terminal reasons
    DUPLICATE_URL = "duplicate_url"
    FETCH_FAILED = "fetch_failed"
    BELOW_MIN_SCORE = "below_min_score"
    NOT_SELECTED = "not_selected"  # ranked too low for top_k / per_cell_cap
    TRIAGE_REJECTED = "triage_rejected"  # caught by classify_score reject rules
    # PRODUCE terminal reasons
    EXTRACTION_FAILED = "extraction_failed"
    VALIDATION_FAILED = "validation_failed"
    # JUDGE terminal reasons
    EVALUATE_TIMEOUT = "evaluate_timeout"
    EVALUATE_ERROR = "evaluate_error"
    NOT_HELPFUL = "not_helpful"  # helps_verdict=no
    COMMITTED = "committed"
    # global
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass
class SelectOutcome:
    deduped: bool
    fetched: bool
    taxonomy_cell: Optional[str]
    score: int
    score_reasons: list[str] = field(default_factory=list)
    selected: bool = False


@dataclass
class ProduceOutcome:
    extracted: bool = False
    validated: bool = False


@dataclass
class JudgeOutcome:
    with_gla_score: Optional[float] = None
    code_only_score: Optional[float] = None
    helps_verdict: Optional[str] = None  # "yes" | "no" | "ambiguous"
    committed_as: Optional[str] = None


@dataclass
class TokenSpend:
    triage: int = 0
    draft: int = 0
    evaluate: int = 0

    @property
    def total(self) -> int:
        return self.triage + self.draft + self.evaluate


@dataclass
class JourneyRow:
    url: str
    run_id: str
    discovered_at: str
    discovery_query: str
    select: SelectOutcome
    produce: Optional[ProduceOutcome] = None
    judge: Optional[JudgeOutcome] = None
    tokens: TokenSpend = field(default_factory=TokenSpend)
    cache_hit: bool = False
    terminal_phase: str = "select"  # "select" | "produce" | "judge"
    terminal_reason: str = TerminalReason.NOT_SELECTED.value

    @classmethod
    def dropped_at_select(cls, *, url, run_id, discovered_at, discovery_query,
                           select, terminal_reason) -> "JourneyRow":
        return cls(url=url, run_id=run_id, discovered_at=discovered_at,
                   discovery_query=discovery_query, select=select,
                   produce=None, judge=None,
                   terminal_phase="select", terminal_reason=terminal_reason)

    def to_dict(self) -> dict:
        d = {
            "url": self.url,
            "run_id": self.run_id,
            "discovered_at": self.discovered_at,
            "discovery_query": self.discovery_query,
            "select": asdict(self.select),
            "produce": asdict(self.produce) if self.produce else None,
            "judge": asdict(self.judge) if self.judge else None,
            "tokens": {**asdict(self.tokens), "total": self.tokens.total},
            "cache_hit": self.cache_hit,
            "terminal_phase": self.terminal_phase,
            "terminal_reason": self.terminal_reason,
        }
        return d


class JourneyWriter:
    """Append-only JSONL writer. One file per run."""
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, row: JourneyRow) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row.to_dict()) + "\n")

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
```

- [ ] **Step 1.4: Run test to verify pass**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_journey.py -v
```

Expected: PASS, 2 tests pass.

- [ ] **Step 1.5: Write writer round-trip test**

```python
# Append to tests/unit/python/test_curation_journey.py
def test_journey_writer_roundtrip(tmp_path):
    from gpa.eval.curation.journey import JourneyWriter
    p = tmp_path / "journey.jsonl"
    w = JourneyWriter(p)
    w.append(JourneyRow(
        url="u1", run_id="r1", discovered_at="t",
        discovery_query="q",
        select=SelectOutcome(deduped=True, fetched=True,
                              taxonomy_cell="c", score=5, selected=True),
        terminal_phase="select", terminal_reason="not_selected",
    ))
    rows = w.read_all()
    assert len(rows) == 1
    assert rows[0]["url"] == "u1"
    assert rows[0]["select"]["score"] == 5
```

- [ ] **Step 1.6: Run test, confirm pass**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_journey.py -v
```

Expected: PASS, 3 tests pass.

- [ ] **Step 1.7: Commit**

```bash
git add src/python/bhdr/eval/curation/journey.py tests/unit/python/test_curation_journey.py
git commit -m "feat(curation): JourneyRow + per-run JSONL writer"
```

---

### Task 2: Per-run directory layout

**Files:**
- Create: `src/python/bhdr/eval/curation/run_dir.py`
- Test: `tests/unit/python/test_curation_run_dir.py`

- [ ] **Step 2.1: Write failing tests for run-id generation + dir layout**

```python
# tests/unit/python/test_curation_run_dir.py
import re
from pathlib import Path
from gpa.eval.curation.run_dir import RunDir, generate_run_id

def test_generate_run_id_format():
    rid = generate_run_id(config_text="queries: []\nrules: foo")
    # YYYY-MM-DD-HHMMSS-<8-hex>
    assert re.match(r"^\d{4}-\d{2}-\d{2}-\d{6}-[0-9a-f]{8}$", rid), rid

def test_generate_run_id_is_stable_for_same_config():
    a = generate_run_id(config_text="x", clock=lambda: "2026-05-01-120000")
    b = generate_run_id(config_text="x", clock=lambda: "2026-05-01-120000")
    assert a == b

def test_run_dir_freezes_config(tmp_path):
    rd = RunDir.create(root=tmp_path, run_id="r1",
                       config_payload="queries:\n  - q1\n")
    assert (tmp_path / "runs" / "r1" / "config.yaml").read_text() == "queries:\n  - q1\n"
    assert rd.journey_path == tmp_path / "runs" / "r1" / "journey.jsonl"
    assert rd.issues_dir == tmp_path / "runs" / "r1" / "issues"
    assert rd.summary_path == tmp_path / "runs" / "r1" / "summary.md"
    assert rd.issues_dir.is_dir()

def test_run_dir_create_is_idempotent(tmp_path):
    rd1 = RunDir.create(root=tmp_path, run_id="r1", config_payload="x")
    rd2 = RunDir.create(root=tmp_path, run_id="r1", config_payload="x")
    assert rd1.root == rd2.root
```

- [ ] **Step 2.2: Run test to verify it fails**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_run_dir.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 2.3: Implement run_dir.py**

```python
# src/python/bhdr/eval/curation/run_dir.py
"""Per-run directory layout: .eval-pipeline/runs/<run_id>/{config.yaml,journey.jsonl,issues/,summary.md}.

run_id format: YYYY-MM-DD-HHMMSS-<8-hex hash of config>. Stable for a given
(timestamp, config) pair so identical inputs from the same second collapse
into one run dir.
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional


def _default_clock() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")


def generate_run_id(*, config_text: str,
                     clock: Optional[Callable[[], str]] = None) -> str:
    ts = (clock or _default_clock)()
    h = hashlib.sha256(config_text.encode("utf-8")).hexdigest()[:8]
    return f"{ts}-{h}"


@dataclass
class RunDir:
    root: Path
    run_id: str

    @property
    def config_path(self) -> Path: return self.root / "config.yaml"
    @property
    def journey_path(self) -> Path: return self.root / "journey.jsonl"
    @property
    def issues_dir(self) -> Path: return self.root / "issues"
    @property
    def summary_path(self) -> Path: return self.root / "summary.md"

    @classmethod
    def create(cls, *, root: Path, run_id: str, config_payload: str) -> "RunDir":
        run_root = root / "runs" / run_id
        run_root.mkdir(parents=True, exist_ok=True)
        rd = cls(root=run_root, run_id=run_id)
        rd.config_path.write_text(config_payload, encoding="utf-8")
        rd.issues_dir.mkdir(exist_ok=True)
        return rd
```

- [ ] **Step 2.4: Run tests, confirm pass**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_run_dir.py -v
```

Expected: PASS, 4 tests pass.

- [ ] **Step 2.5: Commit**

```bash
git add src/python/bhdr/eval/curation/run_dir.py tests/unit/python/test_curation_run_dir.py
git commit -m "feat(curation): per-run directory layout helper"
```

---

### Task 3: Deterministic `extract_draft`

**Context:** Today's `draft.py` uses an LLM. The new `extract_draft.py` produces the same output shape (a `DraftResult` with all the scenario.md sections) but using only deterministic extraction from the issue body + fix-PR diff. Required input fields:
- `user_report` ← cleaned issue body
- `expected` / `actual` ← parsed sections from issue body if present
- `fix_commit_sha`, `fix_pr_url`, `expected_files` ← from fix-PR fetched via `gh` CLI
- `bug_signature` ← derived from `expected_files` + `taxonomy_cell`

Failures land in `journey.terminal_reason = "extraction_failed"` with details in `IssueWorkdir.write_stage("extract_draft", ...)`.

**Files:**
- Create: `src/python/bhdr/eval/curation/extract_draft.py`
- Test: `tests/unit/python/test_curation_extract_draft.py`
- Reference: `src/python/bhdr/eval/curation/draft.py` (existing LLM version — keep until Task 8)

- [ ] **Step 3.1: Write failing test against a real fixture**

Use the existing fixture corpus under `tests/unit/python/fixtures/curation/issue_threads/`. Pick one with structured user_report/expected/actual.

```python
# tests/unit/python/test_curation_extract_draft.py
import json
from pathlib import Path
from gpa.eval.curation.extract_draft import extract_draft, ExtractionFailure

FIXTURES = Path(__file__).parent / "fixtures" / "curation" / "issue_threads"

def test_extract_well_structured_issue():
    # Pick a fixture that has clear "Expected" / "Actual" sections
    thread_text = (FIXTURES / "bevy_18608_invisible_after_material_swap.json").read_text()
    fix_pr = {
        "url": "https://github.com/bevyengine/bevy/pull/18631",
        "commit_sha": "17e3efac12fb",
        "files_changed": ["crates/bevy_pbr/src/render/mesh.rs"],
    }
    result = extract_draft(thread=json.loads(thread_text),
                            fix_pr=fix_pr,
                            taxonomy_cell="game-3d/bevy")
    assert result.user_report.strip() != ""
    assert "expected" in result.user_report.lower() or result.expected_section
    assert result.fix_commit_sha == "17e3efac12fb"
    assert result.expected_files == ["crates/bevy_pbr/src/render/mesh.rs"]
    assert result.bug_signature_yaml.startswith("type: code_location")

def test_extract_unparseable_raises():
    # An issue body that's just a code dump with no sections
    thread = {
        "title": "Renderer broken",
        "body": "```\nundefined is not a function\n  at foo (bar.js:10)\n```",
        "comments": [],
    }
    fix_pr = {"url": "https://example/pr/1", "commit_sha": "abc", "files_changed": ["x.rs"]}
    try:
        extract_draft(thread=thread, fix_pr=fix_pr, taxonomy_cell="web-3d/three.js")
        assert False, "expected ExtractionFailure"
    except ExtractionFailure as e:
        assert "user_report" in str(e) or "expected" in str(e)
```

(Note: the fixture filename is illustrative — Step 3.3 will list available fixtures and pick a real one.)

- [ ] **Step 3.2: Inventory existing fixtures**

```bash
ls tests/unit/python/fixtures/curation/issue_threads/
```

Expected: a list of `*.json` files. Pick one whose body contains explicit "Expected" / "Actual" sections; if none, save a synthetic fixture under that path (just the JSON the test loads — body text from the original issue, comments as empty list).

- [ ] **Step 3.3: Run test to verify it fails**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_extract_draft.py -v
```

Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3.4: Implement extract_draft.py**

```python
# src/python/bhdr/eval/curation/extract_draft.py
"""Deterministic field extraction from an issue thread + fix-PR.

Replaces the LLM-based draft.py for routine mining: produces the same
DraftResult shape using only regex + parsing. If required fields can't
be extracted, raises ExtractionFailure (the caller records this in the
journey row with terminal_reason="extraction_failed").

Required output fields (all must be derivable from the inputs):
  - user_report: cleaned body text (stripping HTML, normalising whitespace)
  - expected_section: text under "## Expected" / "Expected behaviour" / etc.
  - actual_section:   text under "## Actual" / "Actual behaviour" / etc.
  - fix_commit_sha:   from fix_pr["commit_sha"]
  - fix_pr_url:       from fix_pr["url"]
  - expected_files:   from fix_pr["files_changed"], filtered to source files
  - bug_signature_yaml: derived ground-truth block built from
                        expected_files + taxonomy_cell + fix_commit_sha
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Optional


_SECTION_HEADERS = {
    "expected": [r"^#+\s*Expected", r"^\*\*Expected", r"^Expected\s+(behaviou?r|output|result)", r"^What I expected"],
    "actual":   [r"^#+\s*Actual",   r"^\*\*Actual",   r"^Actual\s+(behaviou?r|output|result)",   r"^What actually"],
}


class ExtractionFailure(Exception):
    """Raised when required fields cannot be extracted from the issue thread."""


@dataclass
class DraftResult:
    user_report: str
    expected_section: str
    actual_section: str
    fix_commit_sha: str
    fix_pr_url: str
    expected_files: list[str]
    bug_signature_yaml: str
    extras: dict[str, Any] = field(default_factory=dict)


def _clean_body(body: str) -> str:
    # Strip HTML comment blocks Bevy/three use as PR templates
    cleaned = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    # Normalise CRLF
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    # Strip leading/trailing whitespace per line, collapse 3+ blank lines to 2
    lines = [line.rstrip() for line in cleaned.split("\n")]
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_section(body: str, kind: str) -> str:
    """Find a section by header (any of the patterns for `kind`) and
    return the text up to the next # heading or EOF."""
    patterns = _SECTION_HEADERS[kind]
    for pat in patterns:
        m = re.search(pat, body, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            start = m.end()
            tail = body[start:]
            next_h = re.search(r"^#+\s", tail, flags=re.MULTILINE)
            return (tail[:next_h.start()] if next_h else tail).strip()
    return ""


def _build_bug_signature(*, expected_files: list[str], fix_commit_sha: str) -> str:
    files_yaml = "\n".join(f"    - {f}" for f in expected_files)
    return (
        "type: code_location\n"
        "spec:\n"
        "  expected_files:\n"
        f"{files_yaml}\n"
        f"  fix_commit: {fix_commit_sha}\n"
    )


def _filter_source_files(files: list[str]) -> list[str]:
    """Drop test, doc, and example files from fix-PR's files_changed."""
    keep = []
    for f in files:
        low = f.lower()
        if any(seg in low for seg in ("/tests/", "/test/", "/docs/", "/examples/", "/example/", "changelog", ".md")):
            continue
        keep.append(f)
    return keep


def extract_draft(*, thread: dict, fix_pr: dict, taxonomy_cell: str) -> DraftResult:
    body = thread.get("body") or ""
    body = _clean_body(body)
    if not body:
        raise ExtractionFailure("issue body is empty after cleaning")

    expected = _extract_section(body, "expected")
    actual   = _extract_section(body, "actual")
    if not expected and not actual:
        # Heuristic fallback: short bodies (<1500 chars) without sections are
        # acceptable as the whole user_report; longer ones must have structure.
        if len(body) > 1500:
            raise ExtractionFailure(
                "issue body lacks Expected/Actual sections and is too long to use raw")

    expected_files = _filter_source_files(fix_pr.get("files_changed") or [])
    if not expected_files:
        raise ExtractionFailure("fix-PR files_changed had no source files after filtering")

    fix_sha = fix_pr.get("commit_sha")
    fix_url = fix_pr.get("url")
    if not fix_sha or not fix_url:
        raise ExtractionFailure("fix-PR missing commit_sha or url")

    sig = _build_bug_signature(expected_files=expected_files, fix_commit_sha=fix_sha)

    return DraftResult(
        user_report=body,
        expected_section=expected,
        actual_section=actual,
        fix_commit_sha=fix_sha,
        fix_pr_url=fix_url,
        expected_files=expected_files,
        bug_signature_yaml=sig,
        extras={"taxonomy_cell": taxonomy_cell},
    )
```

- [ ] **Step 3.5: Run tests, confirm pass**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_extract_draft.py -v
```

Expected: PASS, 2 tests pass. If a fixture wasn't available, the first test was skipped or used a synthetic fixture written in 3.2.

- [ ] **Step 3.6: Add test for source-file filtering**

```python
def test_filter_source_files_drops_tests_docs_examples():
    from gpa.eval.curation.extract_draft import _filter_source_files
    raw = [
        "crates/bevy_pbr/src/render/mesh.rs",
        "crates/bevy_pbr/src/render/mesh_test.rs",
        "tests/integration/render.rs",
        "examples/3d/repro.rs",
        "docs/changelog.md",
        "CHANGELOG.md",
    ]
    assert _filter_source_files(raw) == ["crates/bevy_pbr/src/render/mesh.rs"]
```

- [ ] **Step 3.7: Run tests, confirm pass**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_extract_draft.py -v
```

Expected: PASS, 3 tests pass.

- [ ] **Step 3.8: Commit**

```bash
git add src/python/bhdr/eval/curation/extract_draft.py tests/unit/python/test_curation_extract_draft.py
git commit -m "feat(curation): deterministic extract_draft (replaces LLM draft for routine mining)"
```

---

### Task 4: Stricter `classify_score` rules (subsumes LLM triage)

**Context:** Today's LLM triage gates a lot of bad candidates. The new design folds triage into `classify_score`'s rule set with `triage_required` (must-match) and `triage_reject` (must-not-match) keyword rules. The existing `mining_rules.yaml` gets two new top-level sections.

**Files:**
- Modify: `src/python/bhdr/eval/curation/mining_rules.yaml`
- Modify: `src/python/bhdr/eval/curation/mine_hard_cases.py:_match_codes` (extend rules engine to honor required/reject groups; will be moved into `run.py` in Task 5)
- Test: `tests/unit/python/test_curation_mine_hard_cases.py` (extend, since the rules engine still lives here for now)

- [ ] **Step 4.1: Write failing test for required + reject rule semantics**

Add to existing `tests/unit/python/test_curation_mine_hard_cases.py`:

```python
def test_classify_score_drops_when_triage_required_unmet():
    from gpa.eval.curation.mine_hard_cases import score_candidate, load_rules
    rules = load_rules()  # default rules file
    # Synthetic candidate: visual symptom present, but no fix PR linked
    cand = make_synthetic_candidate(
        body="Cubes flicker on Vulkan. Repro: …",
        url="https://github.com/x/y/issues/99",
        has_fix_pr_linked=False,
    )
    rec = score_candidate(cand, rules)
    assert rec.terminal_reason == "triage_rejected"
    assert "missing_fix_pr_link" in rec.score_reasons

def test_classify_score_drops_feature_request_via_reject_rule():
    from gpa.eval.curation.mine_hard_cases import score_candidate, load_rules
    rules = load_rules()
    cand = make_synthetic_candidate(
        body="Feature request: please add a depth-of-field shader.",
        url="https://github.com/x/y/issues/100",
        has_fix_pr_linked=True,
    )
    rec = score_candidate(cand, rules)
    assert rec.terminal_reason == "triage_rejected"
    assert "feature_request" in rec.score_reasons
```

(The helper `make_synthetic_candidate` should already exist or be a 5-line helper at the top of the test file — add if missing, modeled on existing test patterns.)

- [ ] **Step 4.2: Run test to verify it fails**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_mine_hard_cases.py::test_classify_score_drops_when_triage_required_unmet -v
```

Expected: FAIL.

- [ ] **Step 4.3: Add `triage_required` and `triage_reject` sections to `mining_rules.yaml`**

Append to `src/python/bhdr/eval/curation/mining_rules.yaml`:

```yaml
# Triage replacement: rules folded in from the deleted LLM triage step.
# An unmet "required" or matched "reject" pattern drops the candidate
# at SELECT phase with terminal_reason="triage_rejected".

triage_required:
  fix_pr_linked:
    # Body must contain a closing PR URL pattern.
    patterns:
      - "(?i)closed by .*?#\\d+"
      - "(?i)fixed (in|by) .*?#\\d+"
      - "(?i)pull/\\d+"
  visual_keyword_present:
    patterns:
      - "(?i)\\b(invisible|disappear|flicker|glitch|black|wrong|missing|leak)\\b"

triage_reject:
  feature_request:
    patterns:
      - "(?i)^feature request"
      - "(?i)please add"
      - "(?i)would be nice if"
  documentation_only:
    patterns:
      - "(?i)\\bdocs?\\b.*\\bmissing\\b"
      - "(?i)broken link"
  installation_issue:
    patterns:
      - "(?i)cargo (build|install) (fail|error)"
      - "(?i)cannot find package"
```

- [ ] **Step 4.4: Extend `score_candidate` to honor required + reject**

Modify `src/python/bhdr/eval/curation/mine_hard_cases.py`:

```python
# Inside score_candidate(...), after the existing pattern matching:
def score_candidate(cand, rules):
    # ... existing scoring ...
    text = _norm_text(cand.title, cand.body)

    # Required: every required group must match at least one pattern
    for group_name, group in (rules.triage_required or {}).items():
        if not _match_codes(group["patterns"], text):
            rec.terminal_reason = "triage_rejected"
            rec.score_reasons.append(f"missing_{group_name}")
            return rec

    # Reject: any matched reject group drops the candidate
    for group_name, group in (rules.triage_reject or {}).items():
        if _match_codes(group["patterns"], text):
            rec.terminal_reason = "triage_rejected"
            rec.score_reasons.append(group_name)
            return rec

    # ... existing scoring continues ...
```

(Exact placement depends on the current shape of `score_candidate`; read it first and integrate without breaking existing assertions.)

Also extend `MiningRules` dataclass at the top of the file to hold `triage_required: Optional[dict]`, `triage_reject: Optional[dict]` and update `load_rules` to populate them.

- [ ] **Step 4.5: Run test, confirm pass**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_mine_hard_cases.py -v
```

Expected: PASS, all existing + 2 new tests pass.

- [ ] **Step 4.6: Commit**

```bash
git add src/python/bhdr/eval/curation/mining_rules.yaml src/python/bhdr/eval/curation/mine_hard_cases.py tests/unit/python/test_curation_mine_hard_cases.py
git commit -m "feat(curation): triage_required/reject rules subsume LLM triage"
```

---

### Task 5: Wire the unified `run.py` orchestrator

**Context:** `run.py` brings together SELECT (rules-only), PRODUCE (`extract_draft` + `validate`), JUDGE (`evaluate` opt-in + `classify` + `commit`). It writes per-candidate journey rows after each phase boundary. It honors `--max-phase`, `--evaluate`, `--budget-tokens`, `--batch-quota`.

**Files:**
- Create: `src/python/bhdr/eval/curation/run.py`
- Test: `tests/unit/python/test_curation_run.py`
- Reuses: `discover.py`, `triage.py` (only `fetch_thread` helper — the LLM verdict path is unused now), `extract_draft.py` (Task 3), `validate.py`, `run_eval.py`, `classify.py`, `commit.py`, `journey.py` (Task 1), `run_dir.py` (Task 2), `coverage_log.py`, `workdir.py`

- [ ] **Step 5.1: Write failing test for SELECT-only path**

```python
# tests/unit/python/test_curation_run.py
import json
from pathlib import Path
from gpa.eval.curation.run import main

def test_run_max_phase_select_writes_journey_no_llm(tmp_path, monkeypatch):
    queries_path = tmp_path / "q.yaml"
    queries_path.write_text(
        "queries:\n"
        "  - source: github\n"
        "    repo: bevyengine/bevy\n"
        "    query: invisible cube\n"
    )
    rules_path = Path("src/python/bhdr/eval/curation/mining_rules.yaml")

    # Stub Discoverer so we don't hit the network
    from gpa.eval.curation import run as run_mod
    monkeypatch.setattr(run_mod, "build_discoverer", lambda *a, **kw:
        FakeDiscoverer([
            FakeCand(url="https://github.com/x/y/issues/1",
                     title="Cubes invisible", body="Closed by #2"),
        ]))

    # Stub fetch_thread to return canned text
    monkeypatch.setattr(run_mod, "fetch_thread",
        lambda url: {"title": "Cubes invisible", "body": "Closed by #2", "comments": []})

    rc = main([
        "--queries", str(queries_path),
        "--rules", str(rules_path),
        "--workdir", str(tmp_path / "wd"),
        "--max-phase", "select",
    ])
    assert rc == 0
    runs = list((tmp_path / "wd" / "runs").iterdir())
    assert len(runs) == 1
    journey = (runs[0] / "journey.jsonl").read_text().splitlines()
    assert len(journey) == 1
    row = json.loads(journey[0])
    assert row["select"]["fetched"] is True
    assert row["produce"] is None
    assert row["tokens"]["total"] == 0
```

(The `FakeDiscoverer` / `FakeCand` helpers should be defined at the top of this test file with the minimal surface that `run.py` consumes.)

- [ ] **Step 5.2: Run test to verify it fails**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_run.py -v
```

Expected: FAIL with `ModuleNotFoundError` or `AttributeError`.

- [ ] **Step 5.3: Implement `run.py` SELECT phase**

```python
# src/python/bhdr/eval/curation/run.py
"""Single-path mining orchestrator.

Runs SELECT → PRODUCE → JUDGE end-to-end. No human gate. Writes one
journey row per discovered candidate to runs/<run_id>/journey.jsonl.

CLI:
    python -m bhdr.eval.curation.run \
        --queries Q.yaml --rules R.yaml \
        [--workdir .eval-pipeline] \
        [--max-phase {select,produce,judge}] \
        [--evaluate] [--budget-tokens N] [--batch-quota M] \
        [--eval-dir tests/eval] [--backend auto] [--run-id ID]
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from gpa.eval.curation.coverage_log import CoverageLog
from gpa.eval.curation.discover import Discoverer, GitHubSearch, StackExchangeSearch
from gpa.eval.curation.journey import (
    JourneyRow, JourneyWriter, SelectOutcome, ProduceOutcome, JudgeOutcome,
    TokenSpend, TerminalReason,
)
from gpa.eval.curation.mine_hard_cases import (
    load_rules, score_candidate, infer_taxonomy, infer_bug_class,
    select_stratified,
)
from gpa.eval.curation.run_dir import RunDir, generate_run_id
from gpa.eval.curation.triage import fetch_thread


PHASES = ("select", "produce", "judge")


def build_discoverer(queries: dict) -> Discoverer:
    """Test seam: real implementation builds GitHubSearch + StackExchangeSearch."""
    return Discoverer(
        github=GitHubSearch(),
        stack=StackExchangeSearch(),
        queries=queries,
    )


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="gpa.eval.curation.run",
                                 description="Single-path mining pipeline.")
    p.add_argument("--queries", required=True)
    p.add_argument("--rules", required=True)
    p.add_argument("--workdir", default=".eval-pipeline")
    p.add_argument("--max-phase", choices=PHASES, default="judge")
    p.add_argument("--evaluate", action="store_true")
    p.add_argument("--budget-tokens", type=int, default=0)  # 0 = no cap
    p.add_argument("--batch-quota", type=int, default=20)
    p.add_argument("--eval-dir", default="tests/eval")
    p.add_argument("--backend", default="auto")
    p.add_argument("--run-id", default=None)
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    queries = yaml.safe_load(Path(args.queries).read_text())
    rules = load_rules(args.rules)

    # Frozen config payload = both files concatenated
    cfg_payload = (
        Path(args.queries).read_text() +
        "\n# ---\n" +
        Path(args.rules).read_text()
    )
    run_id = args.run_id or generate_run_id(config_text=cfg_payload)
    rd = RunDir.create(root=Path(args.workdir), run_id=run_id,
                        config_payload=cfg_payload)
    writer = JourneyWriter(rd.journey_path)

    discoverer = build_discoverer(queries)
    coverage = CoverageLog(Path("docs/superpowers/eval/coverage-log.jsonl"))

    discovered_at = datetime.now(timezone.utc).isoformat()
    candidates = list(discoverer.discover(quota=args.batch_quota * 5))
    selected_records = []

    # SELECT phase
    for cand in candidates:
        # dedup
        if coverage.contains(cand.url):
            writer.append(JourneyRow.dropped_at_select(
                url=cand.url, run_id=run_id,
                discovered_at=discovered_at,
                discovery_query=cand.query,
                select=SelectOutcome(deduped=False, fetched=False,
                                      taxonomy_cell=None, score=0,
                                      selected=False),
                terminal_reason=TerminalReason.DUPLICATE_URL.value,
            ))
            continue

        # fetch
        try:
            thread = fetch_thread(cand.url)
        except Exception as e:
            writer.append(JourneyRow.dropped_at_select(
                url=cand.url, run_id=run_id,
                discovered_at=discovered_at,
                discovery_query=cand.query,
                select=SelectOutcome(deduped=True, fetched=False,
                                      taxonomy_cell=None, score=0,
                                      selected=False),
                terminal_reason=TerminalReason.FETCH_FAILED.value,
            ))
            continue

        # classify + score (subsumes triage)
        rec = score_candidate(cand, rules, thread=thread)
        if rec.terminal_reason == "triage_rejected":
            writer.append(JourneyRow.dropped_at_select(
                url=cand.url, run_id=run_id,
                discovered_at=discovered_at,
                discovery_query=cand.query,
                select=SelectOutcome(deduped=True, fetched=True,
                                      taxonomy_cell=rec.taxonomy_cell,
                                      score=rec.score,
                                      score_reasons=rec.score_reasons,
                                      selected=False),
                terminal_reason=TerminalReason.TRIAGE_REJECTED.value,
            ))
            continue

        if rec.score < rules.min_score:
            writer.append(JourneyRow.dropped_at_select(
                url=cand.url, run_id=run_id,
                discovered_at=discovered_at,
                discovery_query=cand.query,
                select=SelectOutcome(deduped=True, fetched=True,
                                      taxonomy_cell=rec.taxonomy_cell,
                                      score=rec.score,
                                      score_reasons=rec.score_reasons,
                                      selected=False),
                terminal_reason=TerminalReason.BELOW_MIN_SCORE.value,
            ))
            continue

        selected_records.append((cand, thread, rec))

    # stratified select cap
    selected = select_stratified(selected_records, rules,
                                  top_k=args.batch_quota,
                                  per_cell_cap=rules.per_cell_cap)
    selected_urls = {r.cand.url for r in selected}
    for cand, thread, rec in selected_records:
        if cand.url not in selected_urls:
            writer.append(JourneyRow.dropped_at_select(
                url=cand.url, run_id=run_id,
                discovered_at=discovered_at,
                discovery_query=cand.query,
                select=SelectOutcome(deduped=True, fetched=True,
                                      taxonomy_cell=rec.taxonomy_cell,
                                      score=rec.score,
                                      score_reasons=rec.score_reasons,
                                      selected=False),
                terminal_reason=TerminalReason.NOT_SELECTED.value,
            ))

    # If max-phase=select, write journey rows for every selected candidate
    # too, with produce/judge=null and terminal_reason=committed→not yet.
    if args.max_phase == "select":
        for cand, thread, rec in selected:
            writer.append(JourneyRow(
                url=cand.url, run_id=run_id,
                discovered_at=discovered_at,
                discovery_query=cand.query,
                select=SelectOutcome(deduped=True, fetched=True,
                                      taxonomy_cell=rec.taxonomy_cell,
                                      score=rec.score,
                                      score_reasons=rec.score_reasons,
                                      selected=True),
                terminal_phase="select",
                terminal_reason=TerminalReason.NOT_SELECTED.value,  # i.e. stopped at select
            ))
        return 0

    # PRODUCE / JUDGE: implemented in Step 5.5
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5.4: Run test, confirm SELECT-only path passes**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_run.py -v
```

Expected: PASS, 1 test passes.

- [ ] **Step 5.5: Write failing test for PRODUCE phase (extract_draft + validate)**

```python
def test_run_max_phase_produce_extracts_and_validates(tmp_path, monkeypatch):
    # ... wire fakes for discover + fetch_thread + a stub fix_pr lookup
    # Run with --max-phase produce
    # Expect journey row has produce.extracted = True, produce.validated = True,
    # judge = None, terminal_phase = "produce"
    ...
```

(Fill in the stubs analogously to Step 5.1; the test ensures the produce branch fires and exits before judge.)

- [ ] **Step 5.6: Run test, expect fail**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_run.py::test_run_max_phase_produce_extracts_and_validates -v
```

Expected: FAIL — `produce` branch not yet wired.

- [ ] **Step 5.7: Implement PRODUCE phase in `run.py`**

After the SELECT loop in `main`, add a PRODUCE block:

```python
    from gpa.eval.curation.extract_draft import extract_draft, ExtractionFailure
    from gpa.eval.curation.validate import validate_draft  # existing

    drafted = []
    for cand, thread, rec in selected:
        try:
            fix_pr = _fetch_fix_pr_metadata(thread, cand.url)  # gh CLI + parse
        except Exception:
            writer.append(_make_row(cand, rec, run_id, discovered_at,
                                     produce_extracted=False,
                                     terminal_phase="produce",
                                     terminal_reason=TerminalReason.EXTRACTION_FAILED.value))
            continue

        try:
            draft = extract_draft(thread=thread, fix_pr=fix_pr,
                                   taxonomy_cell=rec.taxonomy_cell)
        except ExtractionFailure:
            writer.append(_make_row(cand, rec, run_id, discovered_at,
                                     produce_extracted=False,
                                     terminal_phase="produce",
                                     terminal_reason=TerminalReason.EXTRACTION_FAILED.value))
            continue

        v = validate_draft(draft)
        if not v.ok:
            writer.append(_make_row(cand, rec, run_id, discovered_at,
                                     produce_extracted=True,
                                     produce_validated=False,
                                     terminal_phase="produce",
                                     terminal_reason=TerminalReason.VALIDATION_FAILED.value))
            continue

        drafted.append((cand, thread, rec, draft, fix_pr))

    if args.max_phase == "produce":
        for cand, thread, rec, draft, fix_pr in drafted:
            writer.append(_make_row(cand, rec, run_id, discovered_at,
                                     produce_extracted=True,
                                     produce_validated=True,
                                     terminal_phase="produce",
                                     terminal_reason="produce_done"))
        return 0
```

(Add `_make_row` helper at module level for journey-row construction; add `_fetch_fix_pr_metadata` helper that uses `gh api repos/.../pulls/...` and returns `{url, commit_sha, files_changed}`.)

- [ ] **Step 5.8: Run test, confirm pass**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_run.py -v
```

Expected: PASS for SELECT + PRODUCE tests.

- [ ] **Step 5.9: Write failing test for JUDGE phase (commit, no --evaluate)**

```python
def test_run_judge_commits_without_evaluate_when_flag_not_set(tmp_path, monkeypatch):
    # default behaviour: --evaluate not passed → skip agent eval, commit
    # if validate passed. Journey row has judge.committed_as set,
    # judge.with_gla_score is None.
    ...
```

- [ ] **Step 5.10: Run test, expect fail**

Expected: FAIL.

- [ ] **Step 5.11: Implement JUDGE phase**

```python
    from gpa.eval.curation.commit import commit_scenario

    for cand, thread, rec, draft, fix_pr in drafted:
        scenario_id = _make_scenario_id(cand.url, rec.taxonomy_cell)

        if args.evaluate:
            from gpa.eval.curation.run_eval import run_eval
            from gpa.eval.curation.classify import classify_observed_helps
            ev = run_eval(draft=draft, scenario_id=scenario_id,
                          backend=args.backend, eval_dir=args.eval_dir)
            verdict = classify_observed_helps(ev.with_gla, ev.code_only).verdict
            judge = JudgeOutcome(
                with_gla_score=ev.with_gla.score,
                code_only_score=ev.code_only.score,
                helps_verdict=verdict,
                committed_as=None,
            )
            if verdict == "no":
                writer.append(_make_row(cand, rec, run_id, discovered_at,
                                         produce_extracted=True,
                                         produce_validated=True,
                                         judge=judge,
                                         terminal_phase="judge",
                                         terminal_reason=TerminalReason.NOT_HELPFUL.value))
                continue
        else:
            judge = JudgeOutcome(
                with_gla_score=None, code_only_score=None,
                helps_verdict=None, committed_as=None,
            )

        commit_scenario(scenario_id=scenario_id, draft=draft,
                        eval_dir=Path(args.eval_dir),
                        coverage_log=coverage)
        judge.committed_as = scenario_id
        writer.append(_make_row(cand, rec, run_id, discovered_at,
                                 produce_extracted=True,
                                 produce_validated=True,
                                 judge=judge,
                                 terminal_phase="judge",
                                 terminal_reason=TerminalReason.COMMITTED.value))

    return 0
```

- [ ] **Step 5.12: Run all tests, confirm pass**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_run.py -v
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_extract_draft.py tests/unit/python/test_curation_journey.py tests/unit/python/test_curation_run_dir.py -v
```

Expected: PASS, all of the above.

- [ ] **Step 5.13: Commit**

```bash
git add src/python/bhdr/eval/curation/run.py tests/unit/python/test_curation_run.py
git commit -m "feat(curation): unified run.py orchestrator (SELECT/PRODUCE/JUDGE)"
```

---

### Task 6: Auto-summary writer

**Files:**
- Create: `src/python/bhdr/eval/curation/summary.py`
- Test: `tests/unit/python/test_curation_summary.py`
- Modify: `src/python/bhdr/eval/curation/run.py` to call `write_summary` at end of `main`

- [ ] **Step 6.1: Write failing test**

```python
# tests/unit/python/test_curation_summary.py
from pathlib import Path
from gpa.eval.curation.summary import write_summary

def test_summary_counts_by_terminal_reason(tmp_path):
    journey = tmp_path / "journey.jsonl"
    journey.write_text(
        '{"url":"u1","terminal_phase":"select","terminal_reason":"duplicate_url","tokens":{"total":0}}\n'
        '{"url":"u2","terminal_phase":"select","terminal_reason":"below_min_score","tokens":{"total":0}}\n'
        '{"url":"u3","terminal_phase":"judge","terminal_reason":"committed","tokens":{"total":12500},"select":{"taxonomy_cell":"web-3d/three.js"}}\n'
    )
    summary_path = tmp_path / "summary.md"
    write_summary(journey_path=journey, summary_path=summary_path)
    text = summary_path.read_text()
    assert "duplicate_url: 1" in text
    assert "below_min_score: 1" in text
    assert "committed: 1" in text
    assert "12500" in text  # token total
```

- [ ] **Step 6.2: Run test, expect fail**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_summary.py -v
```

Expected: FAIL.

- [ ] **Step 6.3: Implement summary.py**

```python
# src/python/bhdr/eval/curation/summary.py
"""Auto-rollup of journey.jsonl into summary.md.

Counts by terminal_reason, taxonomy_cell histogram, total tokens. No
LLM, no external commands — pure read-aggregate-write.
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path


def write_summary(*, journey_path: Path, summary_path: Path) -> None:
    rows = [json.loads(line) for line in journey_path.read_text().splitlines() if line.strip()]
    by_reason = Counter(r.get("terminal_reason", "unknown") for r in rows)
    by_cell = Counter()
    for r in rows:
        cell = (r.get("select") or {}).get("taxonomy_cell")
        if cell:
            by_cell[cell] += 1
    total_tokens = sum((r.get("tokens") or {}).get("total", 0) for r in rows)

    lines = []
    lines.append(f"# Mining run summary")
    lines.append("")
    lines.append(f"- Total candidates: {len(rows)}")
    lines.append(f"- Total tokens spent: {total_tokens}")
    lines.append("")
    lines.append("## By terminal_reason")
    for reason, count in by_reason.most_common():
        lines.append(f"- {reason}: {count}")
    lines.append("")
    lines.append("## By taxonomy_cell")
    for cell, count in by_cell.most_common():
        lines.append(f"- {cell}: {count}")
    lines.append("")
    summary_path.write_text("\n".join(lines), encoding="utf-8")
```

- [ ] **Step 6.4: Run test, confirm pass**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_summary.py -v
```

Expected: PASS.

- [ ] **Step 6.5: Wire `write_summary` at end of `run.main`**

In `run.py`, before `return 0`:

```python
    from gpa.eval.curation.summary import write_summary
    write_summary(journey_path=rd.journey_path, summary_path=rd.summary_path)
```

- [ ] **Step 6.6: Run all curation tests**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_*.py -v
```

Expected: PASS for all that don't reference deleted modules. Tests for `mine_hard_cases` / `pipeline` / `measure_yield` keep passing — we haven't deleted them yet.

- [ ] **Step 6.7: Commit**

```bash
git add src/python/bhdr/eval/curation/summary.py src/python/bhdr/eval/curation/run.py tests/unit/python/test_curation_summary.py
git commit -m "feat(curation): auto-summary writer wired into run.py"
```

---

### Task 7: Smoke test (gates O1 decision)

**Context:** Run the new pipeline end-to-end against the existing 22-URL `framework_app_dev_hard_cases.yaml` corpus plus a sampled chunk of `coverage-log.jsonl`. Measure extraction success rate. Document the result. If ≥ 70%, proceed to hard cut; otherwise reopen O1 and add a bounded LLM fallback.

**Files:**
- Create: `docs/superpowers/eval/single-path-mining-smoke-test.md`
- Use existing: `src/python/bhdr/eval/curation/queries/framework_app_dev_hard_cases.yaml`

- [ ] **Step 7.1: Sample the existing coverage log**

```bash
shuf -n 30 docs/superpowers/eval/coverage-log.jsonl > /tmp/smoke_coverage_sample.jsonl
# Extract URLs as a synthetic queries pack
python -c "
import json, sys
urls = []
for line in open('/tmp/smoke_coverage_sample.jsonl'):
    d = json.loads(line)
    if d.get('url'): urls.append(d['url'])
print('queries:')
for u in urls: print(f'  - {{ source: direct_url, url: {u!r} }}')
" > /tmp/smoke_coverage.yaml
```

(If the discoverer doesn't currently support a `direct_url` source, either add a small stub or just point at the real `framework_app_dev_hard_cases.yaml` for the smoke run and skip the coverage sample. Document whichever path you took.)

- [ ] **Step 7.2: Run the smoke test, SELECT phase only**

```bash
PYTHONPATH=src/python python -m bhdr.eval.curation.run \
  --queries src/python/bhdr/eval/curation/queries/framework_app_dev_hard_cases.yaml \
  --rules src/python/bhdr/eval/curation/mining_rules.yaml \
  --workdir /tmp/smoke-eval-pipeline \
  --max-phase select
```

Expected: exit 0, journey.jsonl populated.

- [ ] **Step 7.3: Run the smoke test, PRODUCE phase**

```bash
PYTHONPATH=src/python python -m bhdr.eval.curation.run \
  --queries src/python/bhdr/eval/curation/queries/framework_app_dev_hard_cases.yaml \
  --rules src/python/bhdr/eval/curation/mining_rules.yaml \
  --workdir /tmp/smoke-eval-pipeline \
  --max-phase produce
```

- [ ] **Step 7.4: Compute extraction success rate**

```bash
RUN_DIR=$(ls -d /tmp/smoke-eval-pipeline/runs/*/ | tail -1)
jq -s '
  map(select(.select.selected == true)) as $sel
  | ($sel | length) as $total
  | ($sel | map(select(.produce.extracted == true)) | length) as $ok
  | { total_selected: $total, extracted_ok: $ok,
      success_rate: ($ok / $total) }
' "$RUN_DIR/journey.jsonl"
```

- [ ] **Step 7.5: Document result + decision**

Write `docs/superpowers/eval/single-path-mining-smoke-test.md`:

```markdown
# Single-Path Mining — Smoke Test Results

_Date: <run date>_

## Setup
- Corpus: `framework_app_dev_hard_cases.yaml` (22 URLs)
- Coverage sample: <skipped|N URLs>
- Run dir: <path>

## Results

| Metric | Value |
|---|---|
| Total candidates discovered | N |
| Selected after SELECT | N |
| Extraction success rate | X% |

### Failure breakdown (terminal_reason)

| reason | count |
|---|---|

## O1 decision

- Threshold: ≥ 70% extraction success
- Observed: X%
- Decision: <ship strict | add LLM fallback>

## Failure samples (steering data)

For each failure, link to `runs/<id>/issues/<id>/`:
- ...
```

- [ ] **Step 7.6: Commit smoke-test doc + any rule additions made during the test**

```bash
git add docs/superpowers/eval/single-path-mining-smoke-test.md
# If you tuned mining_rules.yaml during the smoke test:
git add src/python/bhdr/eval/curation/mining_rules.yaml
git commit -m "test(curation): single-path mining smoke test + O1 decision"
```

---

### Task 8: Hard cut — delete old CLIs, update docs

**Context:** With the new path proven by the smoke test, delete the four old CLIs and their tests. Update docs to point at `gpa.eval.curation.run`.

**Files:**
- Delete: `src/python/bhdr/eval/curation/mine_hard_cases.py`, `mine_taxonomy.py`, `measure_yield.py`, `pipeline.py`
- Delete: `tests/unit/python/test_curation_mine_hard_cases.py`, `test_curation_pipeline.py`
- Modify: `docs/superpowers/eval/framework-app-dev-hard-cases.md`

- [ ] **Step 8.1: Move rule-engine helpers from `mine_hard_cases.py` into `run.py` (or a new `rules.py`)**

`run.py` currently imports `score_candidate`, `infer_taxonomy`, `infer_bug_class`, `select_stratified`, `MiningRules`, `load_rules` from `mine_hard_cases`. Move these into `src/python/bhdr/eval/curation/rules.py` (a new file) so the deletion in 8.2 is clean. Update `run.py` import paths.

```bash
git mv src/python/bhdr/eval/curation/mine_hard_cases.py src/python/bhdr/eval/curation/rules.py
# Then strip the argparse/main/CLI parts; keep only:
#   - MiningRules dataclass
#   - load_rules
#   - score_candidate
#   - infer_taxonomy / infer_bug_class
#   - select_stratified
# Update run.py: from gpa.eval.curation.rules import (...)
# Update tests/unit/python/test_curation_mine_hard_cases.py:
#   rename to test_curation_rules.py and update imports
git mv tests/unit/python/test_curation_mine_hard_cases.py tests/unit/python/test_curation_rules.py
```

- [ ] **Step 8.2: Run all tests, confirm green after the rename**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_*.py -v
```

Expected: PASS for everything that doesn't reference `mine_taxonomy` / `measure_yield` / `pipeline`.

- [ ] **Step 8.3: Delete the three remaining old CLIs and their tests**

```bash
git rm src/python/bhdr/eval/curation/mine_taxonomy.py
git rm src/python/bhdr/eval/curation/measure_yield.py
git rm src/python/bhdr/eval/curation/pipeline.py
git rm tests/unit/python/test_curation_pipeline.py
```

- [ ] **Step 8.4: Run full curation test suite**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_*.py -v
```

Expected: PASS. If anything imports a deleted module, fix the import (likely just removing dead code paths).

- [ ] **Step 8.5: Update `framework-app-dev-hard-cases.md`**

Replace the `Planner Command` section in `docs/superpowers/eval/framework-app-dev-hard-cases.md`:

```markdown
## Planner Command

Use:

```bash
PYTHONPATH=src/python python3 -m bhdr.eval.curation.run \
  --queries src/python/bhdr/eval/curation/queries/framework_app_dev_hard_cases.yaml \
  --rules   src/python/bhdr/eval/curation/mining_rules.yaml \
  --max-phase select \
  --workdir .eval-pipeline
```

This is read-only against the production coverage log. The selected
candidates land in `.eval-pipeline/runs/<run_id>/journey.jsonl`. To
proceed end-to-end (extract + commit, no agent eval), drop the
`--max-phase` flag. To run the agent-eval measurement loop, add
`--evaluate`.
```

- [ ] **Step 8.6: Update CLAUDE.md if it references the old commands**

```bash
grep -nE "mine_taxonomy|mine_hard_cases|measure_yield|pipeline" CLAUDE.md docs/**/*.md 2>/dev/null
```

Expected: zero hits to the four old module names. If hits, update each.

- [ ] **Step 8.7: Final test pass + manual sanity run**

```bash
PYTHONPATH=src/python python -m pytest tests/unit/python/test_curation_*.py -v
PYTHONPATH=src/python python -m bhdr.eval.curation.run --queries src/python/bhdr/eval/curation/queries/framework_app_dev_hard_cases.yaml --rules src/python/bhdr/eval/curation/mining_rules.yaml --max-phase select --workdir /tmp/sanity
```

Expected: tests PASS, run exits 0, `/tmp/sanity/runs/<id>/journey.jsonl` exists.

- [ ] **Step 8.8: Commit the hard cut**

```bash
git add -A
git commit -m "refactor(curation): hard cut to single-path mining (delete 4 old CLIs)"
```

---

## Open points handled in-plan

| Open point | Where decided |
|---|---|
| O1 — strict-CLI vs hybrid-LLM extraction | Task 7 (smoke test gates the call) |
| O2 — triage rule strictness | Task 4, refined by Task 7 |
| O3 — run_id format | Task 2 (chose `YYYY-MM-DD-HHMMSS-<8hex>`) |
| O4 — auto vs hand-written summary | Task 6 (chose auto) |
| O5 — cache hit policy across runs | Deferred (per-run isolated for v1; revisit if cost demands) |
| O6 — embed vs shell-out for `evaluate` | Task 5 (chose in-process import) |
| O7 — pipeline.py deletion vs rewrite | Task 8 (chose deletion + new `run.py` for clean git history) |

## Acceptance Criteria

- [ ] `python -m bhdr.eval.curation.run --max-phase select` exits 0 with no LLM cost; journey.jsonl populated.
- [ ] `python -m bhdr.eval.curation.run` (default) commits scenarios end-to-end without invoking the agent eval.
- [ ] `python -m bhdr.eval.curation.run --evaluate` runs the agent eval and writes `with_gla_score` / `code_only_score` / `helps_verdict` per candidate.
- [ ] `runs/<id>/journey.jsonl` is queryable: `jq 'select(.terminal_phase=="select")'` gives a sane sub-list per slice.
- [ ] `runs/<id>/summary.md` rolls up terminal_reason / taxonomy_cell / tokens.
- [ ] All four old CLI modules are deleted; no test references them.
- [ ] `docs/superpowers/eval/framework-app-dev-hard-cases.md` invokes `run` (not `mine_taxonomy`).
- [ ] Smoke-test doc records the O1 outcome.
