# Eval Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Local-only static HTML dashboard that visualizes per-round OpenGPA eval results, with `code_only` vs `with_bhdr` as the primary comparison axis per scenario type, across model tiers, across rounds.

**Architecture:** A Python build script (`src/python/bhdr/eval/dashboard/build.py`) walks `/data3/bhdr-eval-results/*` and `docs/eval-rounds/*.md`, folds rerun/resume directories, and emits a single `dashboard/index.json`. A static `dashboard/index.html` (with vendored `app.js` + `index.css`) loads `index.json` and renders three sections: per-scenario-type Plotly chart panels, a scenario × round timeline grid, and expandable round-log narrative cards. Markdown rendering via marked.js. Plotly via CDN.

**Tech Stack:** Python 3.10+ (build script, uses existing `EvalResult` / `ScenarioLoader`). Plotly.js 2.x via CDN. marked.js via CDN. Plain vanilla JS for grid + cards. No build pipeline for the HTML side.

**Spec:** `docs/superpowers/specs/2026-05-15-eval-dashboard-design.md`

---

## File Structure

```
src/python/bhdr/eval/dashboard/__init__.py        # package marker
src/python/bhdr/eval/dashboard/build.py           # build aggregator entry point
src/python/bhdr/eval/dashboard/_layout.py         # round-dir parsing, rerun folding, file picking
src/python/bhdr/eval/dashboard/_results.py        # result loading, merging, enrichment, meta.json
src/python/bhdr/eval/dashboard/_narrative.py      # markdown discovery + headline extraction
scripts/build-eval-dashboard.sh                  # PYTHONPATH + module shim

dashboard/index.html                             # static page template
dashboard/index.css                              # styles (dark, high-contrast)
dashboard/app.js                                 # render logic (panels, grid, cards)
dashboard/index.json                             # build output, gitignored

tests/unit/python/test_dashboard_layout.py       # round-id parsing, fold, file picking
tests/unit/python/test_dashboard_results.py      # merge, enrich, meta.json seeding
tests/unit/python/test_dashboard_narrative.py    # narrative discovery + headline
tests/unit/python/test_dashboard_build.py        # end-to-end build script test
tests/fixtures/dashboard/sample-index.json       # for offline HTML dev

.gitignore                                       # add dashboard/index.json
```

Files split by responsibility so each module stays under ~150 lines and tests stay focused.

---

## Task 1: Package skeleton + scripts shim

**Files:**
- Create: `src/python/bhdr/eval/dashboard/__init__.py`
- Create: `scripts/build-eval-dashboard.sh`
- Modify: `.gitignore`

- [ ] **Step 1: Create package marker**

```python
# src/python/bhdr/eval/dashboard/__init__.py
"""Eval dashboard: aggregate per-round results into dashboard/index.json.

Entry point: ``python -m bhdr.eval.dashboard.build``. See
``docs/superpowers/specs/2026-05-15-eval-dashboard-design.md``.
"""
```

- [ ] **Step 2: Create the shell shim**

```bash
#!/usr/bin/env bash
# scripts/build-eval-dashboard.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=src/python exec python3 -m bhdr.eval.dashboard.build "$@"
```

Then `chmod +x scripts/build-eval-dashboard.sh`.

- [ ] **Step 3: Gitignore dashboard build output**

Append to `.gitignore`:
```
dashboard/index.json
```

- [ ] **Step 4: Commit**

```bash
git add src/python/bhdr/eval/dashboard/__init__.py scripts/build-eval-dashboard.sh .gitignore
git commit -m "feat(dashboard): package skeleton + build shim"
```

---

## Task 2: Round-dir layout parsing (`_layout.py`)

**Files:**
- Create: `src/python/bhdr/eval/dashboard/_layout.py`
- Create: `tests/unit/python/test_dashboard_layout.py`

Pure functions: round-id extraction, rerun/resume folding, result-file priority. No I/O beyond `pathlib.Path` introspection so tests don't need fixtures.

- [ ] **Step 1: Write failing tests for `extract_round_id`**

```python
# tests/unit/python/test_dashboard_layout.py
import pytest

from gpa.eval.dashboard._layout import extract_round_id


@pytest.mark.parametrize("dirname,expected", [
    ("2026-05-14-r18", "r18"),
    ("2026-05-05-r17", "r17"),
    ("2026-05-05-r17-resume", "r17"),
    ("2026-05-05-r16-rerun", "r16"),
    ("2026-05-05-iter-r12c-rerun", "r12c"),
    ("2026-05-05-iter-r12d-json", "r12d"),
    ("2026-05-05-r13-scope-hint", "r13"),
    ("2026-05-04-round4-claude-cli", "r4"),
    ("2026-05-04-round12b-smoke", "r12b"),
    ("2026-05-04-round12b-with-gla", "r12b"),
    ("malformed", None),
])
def test_extract_round_id(dirname, expected):
    assert extract_round_id(dirname) == expected
```

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=src/python python3 -m pytest tests/unit/python/test_dashboard_layout.py -v`
Expected: ModuleNotFoundError / collection error.

- [ ] **Step 3: Implement `extract_round_id`**

```python
# src/python/bhdr/eval/dashboard/_layout.py
"""Round directory layout: id parsing, rerun folding, result-file picking."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


# Match `r12c`, `r13`, ..., `r18` (lowercase r + digits + optional letter).
# Also matches `round4` / `round12b` legacy form by alternation.
_ROUND_ID_RE = re.compile(r"(?:r|round)(\d+[a-z]?)")


def extract_round_id(dirname: str) -> Optional[str]:
    """Extract the round id from a /data3/bhdr-eval-results/<dirname> basename.

    Examples:
      "2026-05-14-r18" -> "r18"
      "2026-05-05-r17-resume" -> "r17" (resume/rerun fold into parent)
      "2026-05-05-iter-r12c-rerun" -> "r12c"
      "2026-05-04-round4-claude-cli" -> "r4"
      "malformed" -> None
    """
    m = _ROUND_ID_RE.search(dirname.lower())
    if not m:
        return None
    return "r" + m.group(1)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `PYTHONPATH=src/python python3 -m pytest tests/unit/python/test_dashboard_layout.py -v`
Expected: 11 passed.

- [ ] **Step 5: Add failing tests for `fold_rerun_dirs`**

```python
from gpa.eval.dashboard._layout import fold_rerun_dirs


def test_fold_rerun_dirs_groups_by_round_id(tmp_path):
    base = tmp_path / "data3"
    base.mkdir()
    for name in ("2026-05-05-r17", "2026-05-05-r17-resume",
                 "2026-05-14-r18", "malformed"):
        (base / name).mkdir()
    folded = fold_rerun_dirs(base)
    assert sorted(folded.keys()) == ["r17", "r18"]
    # r17 group has both dirs, sorted lexicographically (base < resume)
    assert [p.name for p in folded["r17"]] == [
        "2026-05-05-r17", "2026-05-05-r17-resume",
    ]
    assert [p.name for p in folded["r18"]] == ["2026-05-14-r18"]
    # malformed dropped silently — no Exception


def test_fold_rerun_dirs_missing_root_returns_empty(tmp_path):
    assert fold_rerun_dirs(tmp_path / "nope") == {}
```

- [ ] **Step 6: Implement `fold_rerun_dirs`**

Append to `_layout.py`:

```python
def fold_rerun_dirs(root: Path) -> dict[str, list[Path]]:
    """Group round directories under ``root`` by extracted round id.

    Resume/rerun directories collapse into their parent's group. Returns
    a dict keyed by round id; values are sorted Path lists (base dir
    first, resumes/reruns after — lexical order is sufficient given the
    naming convention). Returns empty dict when ``root`` doesn't exist.
    """
    if not root.exists() or not root.is_dir():
        return {}
    grouped: dict[str, list[Path]] = {}
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        rid = extract_round_id(d.name)
        if rid is None:
            continue
        grouped.setdefault(rid, []).append(d)
    return grouped
```

- [ ] **Step 7: Run tests, verify pass**

Run: `PYTHONPATH=src/python python3 -m pytest tests/unit/python/test_dashboard_layout.py -v`
Expected: all green.

- [ ] **Step 8: Add failing tests for `pick_result_files`**

```python
from gpa.eval.dashboard._layout import pick_result_files


def test_pick_prefers_merged_over_full(tmp_path):
    (tmp_path / "code_only.json").write_text("[]")
    (tmp_path / "code_only_merged.json").write_text("[]")
    picked = pick_result_files(tmp_path)
    assert [p.name for p in picked] == ["code_only_merged.json"]


def test_pick_returns_both_modes(tmp_path):
    (tmp_path / "code_only.json").write_text("[]")
    (tmp_path / "with_bhdr.json").write_text("[]")
    picked = pick_result_files(tmp_path)
    assert sorted(p.name for p in picked) == ["code_only.json", "with_bhdr.json"]


def test_pick_legacy_results_json(tmp_path):
    (tmp_path / "results.json").write_text("[]")
    picked = pick_result_files(tmp_path)
    assert [p.name for p in picked] == ["results.json"]


def test_pick_empty_when_no_match(tmp_path):
    (tmp_path / "garbage.txt").write_text("")
    assert pick_result_files(tmp_path) == []
```

- [ ] **Step 9: Implement `pick_result_files`**

Append to `_layout.py`:

```python
def pick_result_files(round_dir: Path) -> list[Path]:
    """Return the preferred result-JSON files inside ``round_dir``.

    Priority: per-mode merged > per-mode full > legacy ``results.json``.
    A round can have multiple files when both ``code_only`` and
    ``with_bhdr`` ran; both are returned. Merged variants supersede
    their non-merged counterpart for the same mode.
    """
    files = {p.name: p for p in round_dir.iterdir() if p.is_file()}
    picked: list[Path] = []
    for mode in ("code_only", "with_bhdr"):
        merged = files.get(f"{mode}_merged.json")
        full = files.get(f"{mode}.json")
        if merged is not None:
            picked.append(merged)
        elif full is not None:
            picked.append(full)
    if picked:
        return picked
    legacy = files.get("results.json")
    return [legacy] if legacy is not None else []
```

- [ ] **Step 10: Run tests, verify pass**

Run: `PYTHONPATH=src/python python3 -m pytest tests/unit/python/test_dashboard_layout.py -v`
Expected: all green.

- [ ] **Step 11: Add test for `extract_date`**

```python
from gpa.eval.dashboard._layout import extract_date


@pytest.mark.parametrize("dirname,expected", [
    ("2026-05-14-r18", "2026-05-14"),
    ("2026-05-05-r17-resume", "2026-05-05"),
    ("malformed", None),
])
def test_extract_date(dirname, expected):
    assert extract_date(dirname) == expected
```

- [ ] **Step 12: Implement `extract_date`**

Append:

```python
_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def extract_date(dirname: str) -> Optional[str]:
    """Extract the ISO date prefix from a round directory basename."""
    m = _DATE_RE.match(dirname)
    return m.group(1) if m else None
```

- [ ] **Step 13: Run, verify, commit**

Run: `PYTHONPATH=src/python python3 -m pytest tests/unit/python/test_dashboard_layout.py -v`
Expected: all green.

```bash
git add src/python/bhdr/eval/dashboard/_layout.py tests/unit/python/test_dashboard_layout.py
git commit -m "feat(dashboard): round-dir layout parsing (id, fold, pick)"
```

---

## Task 3: Result loading, merging, enrichment (`_results.py`)

**Files:**
- Create: `src/python/bhdr/eval/dashboard/_results.py`
- Create: `tests/unit/python/test_dashboard_results.py`

Loads `EvalResult` rows from one or more JSON files for the same round, merges by `(scenario_id, mode)`, enriches with `scenario_type` + `expected_failure` from `ScenarioLoader`, applies a tier from `meta.json`. Drops pre-verdict rows.

- [ ] **Step 1: Failing test for `load_and_merge_results`**

```python
# tests/unit/python/test_dashboard_results.py
import json
from pathlib import Path

import pytest

from gpa.eval.dashboard._results import (
    load_and_merge_results, load_tier_meta, derive_scenario_type,
    enrich_results,
)
from gpa.eval.metrics import EvalResult


def _make_result_dict(sid="scen_a", mode="code_only", solved=True, **kw):
    return {
        "scenario_id": sid, "mode": mode,
        "diagnosis_text": "x", "input_tokens": 100, "output_tokens": 200,
        "total_tokens": 300, "tool_calls": 1, "num_turns": 1,
        "time_seconds": 1.0, "model": "unknown",
        "timestamp": "2026-05-14T00:00:00Z",
        "verdict": {"solved": solved, "scorer": "file_level", "confidence": "high"},
        **kw,
    }


def test_merge_overlays_by_scenario_and_mode(tmp_path):
    base = tmp_path / "code_only.json"
    base.write_text(json.dumps([
        _make_result_dict("scen_a", solved=False),
        _make_result_dict("scen_b", solved=True),
    ]))
    resume = tmp_path / "code_only_merged.json"
    resume.write_text(json.dumps([
        _make_result_dict("scen_a", solved=True),  # overrides
        _make_result_dict("scen_c", solved=True),
    ]))
    merged = load_and_merge_results([base, resume])
    # By (scenario_id, mode), latest write wins
    by_sid = {r.scenario_id: r for r in merged}
    assert by_sid["scen_a"].verdict["solved"] is True  # from resume
    assert by_sid["scen_b"].verdict["solved"] is True  # only in base
    assert by_sid["scen_c"].verdict["solved"] is True  # only in resume
    assert len(merged) == 3


def test_merge_drops_pre_verdict_rows(tmp_path):
    legacy = tmp_path / "results.json"
    legacy.write_text(json.dumps([
        # Pre-R12c shape: correct_diagnosis instead of verdict.
        # EvalResult.from_dict tolerates this; we drop verdict-less rows.
        {**_make_result_dict("scen_a"), "verdict": None},
        _make_result_dict("scen_b", solved=False),
    ]))
    merged = load_and_merge_results([legacy])
    # scen_a dropped (no verdict), scen_b kept
    assert [r.scenario_id for r in merged] == ["scen_b"]


def test_merge_empty_paths_returns_empty():
    assert load_and_merge_results([]) == []
```

- [ ] **Step 2: Run, verify failure**

Run: `PYTHONPATH=src/python python3 -m pytest tests/unit/python/test_dashboard_results.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `load_and_merge_results`**

```python
# src/python/bhdr/eval/dashboard/_results.py
"""Result loading, merging, enrichment for the dashboard build."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from gpa.eval.metrics import EvalResult


def load_and_merge_results(paths: list[Path]) -> list[EvalResult]:
    """Load result rows from ``paths`` in order; overlay by (scenario_id, mode).

    Rows whose ``verdict`` is None are dropped — they're pre-R12c legacy
    rows whose ``correct_diagnosis`` schema R17 retired. Including them
    would silently miscount history.
    """
    merged: dict[tuple[str, str], EvalResult] = {}
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, list):
            continue
        for row in data:
            try:
                result = EvalResult.from_dict(row)
            except (TypeError, KeyError):
                continue
            if result.verdict is None:
                continue
            merged[(result.scenario_id, result.mode)] = result
    return list(merged.values())
```

- [ ] **Step 4: Run, verify pass**

Expected: 3 passed.

- [ ] **Step 5: Failing test for `load_tier_meta`**

```python
def test_load_tier_meta_reads_existing(tmp_path):
    (tmp_path / "meta.json").write_text(json.dumps({
        "tier": "sonnet", "model": "claude-sonnet-4-6",
    }))
    tier, model = load_tier_meta(tmp_path)
    assert tier == "sonnet"
    assert model == "claude-sonnet-4-6"


def test_load_tier_meta_seeds_opus_when_absent(tmp_path):
    tier, model = load_tier_meta(tmp_path)
    assert tier == "opus"
    assert "opus" in model
    # And the file is now seeded on disk
    written = json.loads((tmp_path / "meta.json").read_text())
    assert written == {"tier": "opus", "model": "claude-opus-4-7[1m]"}


def test_load_tier_meta_handles_malformed(tmp_path):
    (tmp_path / "meta.json").write_text("not json")
    tier, model = load_tier_meta(tmp_path)
    # Malformed → treat as missing; re-seed opus
    assert tier == "opus"
```

- [ ] **Step 6: Implement `load_tier_meta`**

Append:

```python
_DEFAULT_TIER = "opus"
_DEFAULT_MODEL = "claude-opus-4-7[1m]"


def load_tier_meta(round_dir: Path) -> tuple[str, str]:
    """Read (or seed) ``round_dir/meta.json``. Returns (tier, model).

    Every existing eval JSON carries ``model: "unknown"`` because the
    claude-cli backend doesn't capture the model identifier; the per-
    round meta is the authoritative source. Seeded as opus for the
    current cohort the first time the build runs; future multi-tier
    eval rounds (R19+) populate this from the eval CLI itself.
    """
    meta_path = round_dir / "meta.json"
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            tier = data.get("tier")
            model = data.get("model")
            if isinstance(tier, str) and isinstance(model, str):
                return tier, model
        except (OSError, json.JSONDecodeError):
            pass
    # Seed and return
    seeded = {"tier": _DEFAULT_TIER, "model": _DEFAULT_MODEL}
    try:
        meta_path.write_text(json.dumps(seeded, indent=2), encoding="utf-8")
    except OSError:
        pass
    return _DEFAULT_TIER, _DEFAULT_MODEL
```

- [ ] **Step 7: Run, verify pass**

- [ ] **Step 8: Failing test for `derive_scenario_type`**

```python
def test_derive_scenario_type_from_eval_path():
    sd = "/home/x/gh/gla/tests/eval/web-map/cesium/r5211bd_camera_jumps"
    assert derive_scenario_type(sd) == "web-map/cesium"


def test_derive_scenario_type_godot():
    sd = "/x/tests/eval/native-engine/godot/rfc2ac5_glow"
    assert derive_scenario_type(sd) == "native-engine/godot"


def test_derive_scenario_type_no_eval_in_path():
    assert derive_scenario_type("/x/random/path/slug") == "unknown"


def test_derive_scenario_type_empty():
    assert derive_scenario_type(None) == "unknown"
    assert derive_scenario_type("") == "unknown"
```

- [ ] **Step 9: Implement `derive_scenario_type`**

Append:

```python
def derive_scenario_type(scenario_dir: Optional[str]) -> str:
    """Return ``<category>/<framework>`` from a scenario's absolute dir.

    Mirrors the slice logic in
    :func:`gpa.eval.scenario.is_browser_tier_scenario` (scenario.py:46):
    find the ``"eval"`` part and take the next two. Returns ``"unknown"``
    on any failure (missing path, wrong shape, top-level eval, etc.).
    """
    if not scenario_dir:
        return "unknown"
    parts = Path(scenario_dir).parts
    try:
        i = parts.index("eval")
    except ValueError:
        return "unknown"
    if i + 2 >= len(parts):
        return "unknown"
    return f"{parts[i + 1]}/{parts[i + 2]}"
```

- [ ] **Step 10: Run, verify pass**

- [ ] **Step 11: Failing test for `enrich_results`**

The enricher needs `ScenarioLoader`; we'll fake it via a minimal stub class.

```python
class _FakeScenario:
    def __init__(self, scenario_dir, expected_failure=None):
        self.scenario_dir = scenario_dir
        self.expected_failure = expected_failure


class _FakeLoader:
    def __init__(self, scenarios):
        self._by_id = {sid: scen for sid, scen in scenarios.items()}

    def load(self, sid):
        return self._by_id[sid]


def test_enrich_results_attaches_type_and_expected_failure():
    rows = [
        EvalResult.from_dict(_make_result_dict("scen_a")),
        EvalResult.from_dict(_make_result_dict("scen_b")),
    ]
    loader = _FakeLoader({
        "scen_a": _FakeScenario("/x/tests/eval/web-map/cesium/scen_a"),
        "scen_b": _FakeScenario(
            "/x/tests/eval/native-engine/godot/scen_b",
            expected_failure={"reason": "model-tier ceiling"},
        ),
    })
    enriched = list(enrich_results(rows, tier="opus", scenario_loader=loader))
    assert enriched[0]["scenario_id"] == "scen_a"
    assert enriched[0]["scenario_type"] == "web-map/cesium"
    assert enriched[0]["tier"] == "opus"
    assert enriched[0]["expected_failure"] is None
    assert enriched[1]["scenario_type"] == "native-engine/godot"
    assert enriched[1]["expected_failure"] == {"reason": "model-tier ceiling"}


def test_enrich_results_handles_loader_failure_gracefully():
    rows = [EvalResult.from_dict(_make_result_dict("missing_scenario"))]

    class _FailingLoader:
        def load(self, sid):
            raise FileNotFoundError(sid)

    enriched = list(enrich_results(rows, tier="opus", scenario_loader=_FailingLoader()))
    # Loader failure → scenario_type "unknown", expected_failure None,
    # row still kept (it has eval data even without metadata)
    assert enriched[0]["scenario_type"] == "unknown"
    assert enriched[0]["expected_failure"] is None
```

- [ ] **Step 12: Implement `enrich_results`**

Append:

```python
from typing import Iterable, Iterator


def enrich_results(
    results: Iterable[EvalResult],
    *,
    tier: str,
    scenario_loader,
) -> Iterator[dict]:
    """Yield JSON-serialisable dicts with scenario_type / tier / expected_failure.

    Loader errors for a given scenario_id are non-fatal: the row is still
    emitted with ``scenario_type = "unknown"`` so the dashboard can still
    render it under an "unknown" trace.
    """
    for r in results:
        try:
            meta = scenario_loader.load(r.scenario_id)
            stype = derive_scenario_type(getattr(meta, "scenario_dir", None))
            efailure = getattr(meta, "expected_failure", None)
        except Exception:
            stype = "unknown"
            efailure = None
        verdict = r.verdict or {}
        yield {
            "scenario_id": r.scenario_id,
            "scenario_type": stype,
            "mode": r.mode,
            "tier": tier,
            "solved": bool(verdict.get("solved")),
            "scorer": verdict.get("scorer", "no_signal"),
            "confidence": verdict.get("confidence", "low"),
            "output_tokens": r.output_tokens,
            "tool_calls": r.tool_calls,
            "expected_failure": efailure,
        }
```

- [ ] **Step 13: Run all, commit**

Run: `PYTHONPATH=src/python python3 -m pytest tests/unit/python/test_dashboard_results.py -v`
Expected: all green (10 tests).

```bash
git add src/python/bhdr/eval/dashboard/_results.py tests/unit/python/test_dashboard_results.py
git commit -m "feat(dashboard): result loading, merging, enrichment"
```

---

## Task 4: Narrative discovery (`_narrative.py`)

**Files:**
- Create: `src/python/bhdr/eval/dashboard/_narrative.py`
- Create: `tests/unit/python/test_dashboard_narrative.py`

- [ ] **Step 1: Failing tests**

```python
# tests/unit/python/test_dashboard_narrative.py
from pathlib import Path

from gpa.eval.dashboard._narrative import find_narrative, extract_headline


def test_find_narrative_by_round_id(tmp_path):
    (tmp_path / "2026-05-14-r18.md").write_text("# R18\n")
    (tmp_path / "2026-05-05-r17.md").write_text("# R17\n")
    (tmp_path / "README.md").write_text("not a round")
    assert find_narrative(tmp_path, "r18").name == "2026-05-14-r18.md"
    assert find_narrative(tmp_path, "r17").name == "2026-05-05-r17.md"
    assert find_narrative(tmp_path, "r99") is None


def test_find_narrative_handles_missing_dir(tmp_path):
    assert find_narrative(tmp_path / "nope", "r1") is None


def test_extract_headline_basic():
    md = (
        "# Round R18 (2026-05-14)\n\n"
        "Three audit-driven changes shipped: expected_failure scenario\n"
        "slot (P0), prompt-rendering consolidation (P1), and...\n\n"
        "## Ran\n"
    )
    assert "Three audit-driven changes" in extract_headline(md)


def test_extract_headline_skips_blockquote_and_lists():
    md = (
        "# Round R12c\n\n"
        "> Pre-amble blockquote.\n\n"
        "- list item one\n"
        "- list item two\n\n"
        "Actual headline paragraph here.\n"
    )
    assert extract_headline(md) == "Actual headline paragraph here."


def test_extract_headline_none_when_no_paragraph():
    md = "# Round R0\n\n## Ran\n\nbody\n"
    assert extract_headline(md) is None
```

- [ ] **Step 2: Run, verify failure**

- [ ] **Step 3: Implement**

```python
# src/python/bhdr/eval/dashboard/_narrative.py
"""Round-log narrative discovery + headline extraction."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


def find_narrative(rounds_dir: Path, round_id: str) -> Optional[Path]:
    """Find ``<rounds_dir>/*-<round_id>.md`` (case-insensitive on id)."""
    if not rounds_dir.exists() or not rounds_dir.is_dir():
        return None
    rid = round_id.lower()
    for p in sorted(rounds_dir.glob("*.md")):
        # Match suffix `-<rid>` before .md, e.g. "2026-05-14-r18.md".
        stem = p.stem.lower()
        if stem.endswith(f"-{rid}"):
            return p
    return None


_H1_RE = re.compile(r"^#\s+Round\s+R\w+", re.IGNORECASE)
_HEADING_RE = re.compile(r"^#{1,6}\s+")
_LIST_RE = re.compile(r"^\s*[-*+]\s+")
_BLOCKQUOTE_RE = re.compile(r"^\s*>")


def extract_headline(markdown_text: str) -> Optional[str]:
    """Return the first prose paragraph under the ``# Round R##`` heading.

    Skips other headings, list items, blockquotes, and blank lines.
    Returns the trimmed single-line paragraph (newlines collapsed to
    spaces) or None if no such paragraph exists.
    """
    lines = markdown_text.splitlines()
    in_h1 = False
    para: list[str] = []
    for line in lines:
        if _H1_RE.match(line):
            in_h1 = True
            continue
        if not in_h1:
            continue
        stripped = line.strip()
        if not stripped:
            if para:
                break
            continue
        if (_HEADING_RE.match(line) or _LIST_RE.match(line)
                or _BLOCKQUOTE_RE.match(line)):
            if para:
                break
            continue
        para.append(stripped)
    if not para:
        return None
    return " ".join(para)
```

- [ ] **Step 4: Run, verify pass, commit**

```bash
git add src/python/bhdr/eval/dashboard/_narrative.py tests/unit/python/test_dashboard_narrative.py
git commit -m "feat(dashboard): narrative discovery + headline extraction"
```

---

## Task 5: End-to-end build script (`build.py`)

**Files:**
- Create: `src/python/bhdr/eval/dashboard/build.py`
- Create: `tests/unit/python/test_dashboard_build.py`

- [ ] **Step 1: Failing end-to-end test**

```python
# tests/unit/python/test_dashboard_build.py
import json
from pathlib import Path

import pytest

from gpa.eval.dashboard.build import build_index


def _write_result(path, scenario_id, mode, solved, **kw):
    rows = [{
        "scenario_id": scenario_id, "mode": mode,
        "diagnosis_text": "x", "input_tokens": 100, "output_tokens": 200,
        "total_tokens": 300, "tool_calls": 1, "num_turns": 1,
        "time_seconds": 1.0, "model": "unknown",
        "timestamp": "2026-05-14T00:00:00Z",
        "verdict": {"solved": solved, "scorer": "file_level", "confidence": "high"},
        **kw,
    }]
    path.write_text(json.dumps(rows))


class _StubLoader:
    """ScenarioLoader stub for tests — returns a fake scenario per id."""

    def load(self, sid):
        class _S:
            scenario_dir = f"/x/tests/eval/web-map/cesium/{sid}"
            expected_failure = None
        return _S()


def test_build_index_minimal_round(tmp_path):
    data3 = tmp_path / "data3"
    rounds = data3 / "2026-05-14-r18"
    rounds.mkdir(parents=True)
    _write_result(rounds / "code_only.json", "scen_a", "code_only", True)

    rounds_md = tmp_path / "rounds"
    rounds_md.mkdir()
    (rounds_md / "2026-05-14-r18.md").write_text(
        "# Round R18\n\nTest headline.\n"
    )

    out = tmp_path / "out.json"
    build_index(
        data3_root=data3,
        rounds_dir=rounds_md,
        output_path=out,
        scenario_loader=_StubLoader(),
    )
    payload = json.loads(out.read_text())
    assert payload["rounds"][0]["id"] == "r18"
    assert payload["rounds"][0]["headline"] == "Test headline."
    assert payload["rounds"][0]["results"][0]["scenario_id"] == "scen_a"
    assert payload["scenario_types"] == ["web-map/cesium"]
    assert "built_at" in payload


def test_build_index_folds_rerun(tmp_path):
    data3 = tmp_path / "data3"
    base = data3 / "2026-05-05-r17"
    resume = data3 / "2026-05-05-r17-resume"
    base.mkdir(parents=True)
    resume.mkdir(parents=True)
    _write_result(base / "code_only.json", "scen_a", "code_only", False)
    _write_result(resume / "code_only.json", "scen_a", "code_only", True)

    out = tmp_path / "out.json"
    build_index(
        data3_root=data3,
        rounds_dir=tmp_path,  # no narratives
        output_path=out,
        scenario_loader=_StubLoader(),
    )
    payload = json.loads(out.read_text())
    assert len(payload["rounds"]) == 1
    rnd = payload["rounds"][0]
    assert rnd["id"] == "r17"
    # The resume's solved=True overrode the base's solved=False
    assert rnd["results"][0]["solved"] is True


def test_build_index_skips_round_with_no_verdict_data(tmp_path):
    data3 = tmp_path / "data3"
    legacy = data3 / "2026-05-04-round4-claude-cli"
    legacy.mkdir(parents=True)
    # Pre-verdict legacy row
    (legacy / "results.json").write_text(json.dumps([{
        "scenario_id": "scen_a", "mode": "code_only",
        "diagnosis_text": "x", "input_tokens": 100, "output_tokens": 200,
        "total_tokens": 300, "tool_calls": 1, "num_turns": 1,
        "time_seconds": 1.0, "model": "unknown",
        "timestamp": "2026-05-14T00:00:00Z",
        "verdict": None,
    }]))

    out = tmp_path / "out.json"
    build_index(
        data3_root=data3,
        rounds_dir=tmp_path,
        output_path=out,
        scenario_loader=_StubLoader(),
    )
    payload = json.loads(out.read_text())
    assert payload["rounds"] == []


def test_build_index_missing_data3_raises(tmp_path):
    with pytest.raises(SystemExit):
        build_index(
            data3_root=tmp_path / "nope",
            rounds_dir=tmp_path,
            output_path=tmp_path / "out.json",
            scenario_loader=_StubLoader(),
        )
```

- [ ] **Step 2: Run, verify failure**

- [ ] **Step 3: Implement `build.py`**

```python
# src/python/bhdr/eval/dashboard/build.py
"""Aggregate per-round eval results into dashboard/index.json.

Entry point: ``python -m bhdr.eval.dashboard.build``.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gpa.eval.dashboard._layout import (
    extract_date, fold_rerun_dirs, pick_result_files,
)
from gpa.eval.dashboard._narrative import extract_headline, find_narrative
from gpa.eval.dashboard._results import (
    enrich_results, load_and_merge_results, load_tier_meta,
)
from gpa.eval.scenario import ScenarioLoader


_DATA3_ROOT = Path("/data3/bhdr-eval-results")
_ROUNDS_DIR = Path("docs/eval-rounds")
_OUTPUT_PATH = Path("dashboard/index.json")


def build_index(
    *,
    data3_root: Path,
    rounds_dir: Path,
    output_path: Path,
    scenario_loader,
) -> None:
    """Build ``output_path`` from ``data3_root`` + ``rounds_dir``.

    Exits the process with code 1 when ``data3_root`` doesn't exist —
    that's a user error worth surfacing, not an empty dashboard.
    """
    if not data3_root.exists():
        print(
            f"error: data3 root {data3_root} does not exist",
            file=sys.stderr,
        )
        raise SystemExit(1)

    grouped = fold_rerun_dirs(data3_root)
    rounds_out: list[dict[str, Any]] = []
    scenario_types: set[str] = set()

    for round_id, dirs in grouped.items():
        primary = dirs[0]
        result_paths: list[Path] = []
        for d in dirs:
            result_paths.extend(pick_result_files(d))
        results = load_and_merge_results(result_paths)
        if not results:
            # Round had no chartable data — skip entirely.
            continue
        tier, _model = load_tier_meta(primary)
        enriched = list(enrich_results(
            results, tier=tier, scenario_loader=scenario_loader,
        ))
        for row in enriched:
            scenario_types.add(row["scenario_type"])

        narrative_path = find_narrative(rounds_dir, round_id)
        narrative_md = None
        headline = None
        if narrative_path is not None:
            try:
                narrative_md = narrative_path.read_text(encoding="utf-8")
                headline = extract_headline(narrative_md)
            except OSError:
                pass
        if not headline:
            headline = round_id

        rounds_out.append({
            "id": round_id,
            "date": extract_date(primary.name),
            "results_path": str(primary),
            "aux_paths": [str(d) for d in dirs[1:]],
            "narrative_path": str(narrative_path) if narrative_path else None,
            "narrative_md": narrative_md,
            "headline": headline,
            "results": enriched,
        })

    # Sort rounds chronologically by date (ascending).
    rounds_out.sort(key=lambda r: r["date"] or "")

    payload = {
        "built_at": datetime.now(tz=timezone.utc).isoformat(),
        "rounds": rounds_out,
        "scenario_types": sorted(scenario_types),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"Wrote {len(rounds_out)} round(s) to {output_path}",
        file=sys.stderr,
    )


def main() -> int:
    build_index(
        data3_root=_DATA3_ROOT,
        rounds_dir=_ROUNDS_DIR,
        output_path=_OUTPUT_PATH,
        scenario_loader=ScenarioLoader(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run all tests, verify pass**

Run: `PYTHONPATH=src/python python3 -m pytest tests/unit/python/test_dashboard_build.py -v`
Expected: 4 passed.

- [ ] **Step 5: Smoke test against real /data3**

Run: `scripts/build-eval-dashboard.sh`
Expected: prints `Wrote 8 round(s) to dashboard/index.json` (or similar; depending on which rounds have verdict data). The file exists and is valid JSON. Inspect with:

```bash
python3 -c "import json; d=json.load(open('dashboard/index.json')); print(len(d['rounds']), 'rounds,', d['scenario_types'])"
```

- [ ] **Step 6: Commit**

```bash
git add src/python/bhdr/eval/dashboard/build.py tests/unit/python/test_dashboard_build.py
git commit -m "feat(dashboard): end-to-end build script (build_index)"
```

---

## Task 6: Static HTML + CSS

**Files:**
- Create: `dashboard/index.html`
- Create: `dashboard/index.css`

The HTML is one document. CSS lives separately so app.js doesn't have to inject styles.

- [ ] **Step 1: Write `index.html`**

```html
<!-- dashboard/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>OpenGPA Eval Dashboard</title>
  <link rel="stylesheet" href="index.css">
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js" defer></script>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js" defer></script>
  <script src="app.js" defer></script>
</head>
<body>
  <header>
    <h1>OpenGPA Eval Dashboard</h1>
    <div id="meta">
      <span id="built-at">—</span>
      <label>Metric
        <select id="metric-select">
          <option value="solve_pct" selected>solve %</option>
          <option value="tok_per_solve">tok / ✓</option>
        </select>
      </label>
      <label>Tier
        <select id="tier-select">
          <option value="all" selected>all</option>
          <option value="haiku">haiku</option>
          <option value="sonnet">sonnet</option>
          <option value="opus">opus</option>
        </select>
      </label>
      <label><input type="checkbox" id="include-stable"> include expected_failure</label>
    </div>
  </header>

  <main>
    <section id="panels">
      <h2>Per-type comparison</h2>
      <div id="panel-grid"></div>
    </section>

    <section id="grid">
      <h2>Scenario × round timeline</h2>
      <div id="grid-container"></div>
    </section>

    <section id="cards">
      <h2>Round narrative</h2>
      <div id="card-container"></div>
    </section>
  </main>

  <div id="tooltip" hidden></div>
</body>
</html>
```

- [ ] **Step 2: Write `index.css`**

Dark theme, high-contrast (matches the brainstorming visual companion's saturated palette).

```css
/* dashboard/index.css */
:root {
  --bg-primary: #0f172a;
  --bg-secondary: #1e293b;
  --bg-tertiary: #334155;
  --border: #475569;
  --text-primary: #e2e8f0;
  --text-secondary: #94a3b8;
  --accent: #38bdf8;
  --co: #60a5fa;            /* code_only */
  --gla: #fb923c;           /* with_bhdr */
  --solve-hi: #15803d;
  --solve-mid: #a16207;
  --solve-lo: #991b1b;
  --pre-stable: #1e3a8a;
}

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: var(--bg-primary); color: var(--text-primary); font-family: system-ui, sans-serif; }
header { padding: 14px 20px; background: var(--bg-secondary); border-bottom: 1px solid var(--border); display: flex; flex-wrap: wrap; gap: 16px; align-items: center; }
header h1 { margin: 0; font-size: 18px; color: var(--accent); }
#meta { display: flex; gap: 14px; align-items: center; font-size: 13px; color: var(--text-secondary); }
#meta select, #meta input { background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border); padding: 4px 6px; border-radius: 4px; }
main { padding: 20px; max-width: 1400px; margin: 0 auto; }
section { margin-bottom: 36px; }
section h2 { color: var(--accent); font-size: 16px; margin: 0 0 12px; }

/* Panels */
#panel-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 14px; }
.panel { background: var(--bg-secondary); border-radius: 6px; padding: 12px; }
.panel-title { font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; font-family: ui-monospace, Menlo, monospace; }

/* Grid */
#grid-container { overflow-x: auto; }
table.timeline { border-collapse: collapse; font-family: ui-monospace, Menlo, monospace; font-size: 12px; }
table.timeline th, table.timeline td { border: 1px solid var(--border); padding: 4px 8px; text-align: center; }
table.timeline th { background: var(--bg-secondary); color: var(--text-secondary); font-weight: 600; }
table.timeline td.cell { cursor: help; min-width: 56px; }
.cell-hi { background: var(--solve-hi); color: #fff; font-weight: 600; }
.cell-mid { background: var(--solve-mid); color: #fff; }
.cell-lo { background: var(--solve-lo); color: #fff; }
.cell-skipped { color: var(--text-secondary); }
.type-header td { background: var(--bg-tertiary); color: var(--text-primary); text-align: left; font-weight: 600; padding-left: 8px; }
tr.stable td:first-child::after { content: " ⊘"; color: var(--text-secondary); font-size: 10px; }

/* Cards */
.card { background: var(--bg-secondary); border-radius: 6px; margin-bottom: 8px; border: 1px solid var(--border); }
.card-header { padding: 10px 14px; cursor: pointer; display: flex; gap: 12px; align-items: baseline; }
.card-header .id { font-family: ui-monospace, Menlo, monospace; color: var(--accent); font-weight: 600; }
.card-header .date { color: var(--text-secondary); font-size: 12px; }
.card-header .headline { flex: 1; color: var(--text-primary); }
.card-header .toggle { color: var(--text-secondary); font-size: 12px; }
.card-body { padding: 0 14px 14px; display: none; border-top: 1px solid var(--border); }
.card-body.expanded { display: block; }
.card-body h1 { font-size: 18px; }
.card-body h2 { font-size: 15px; margin-top: 16px; color: var(--accent); }
.card-body h3 { font-size: 13px; margin-top: 12px; }
.card-body pre { background: var(--bg-primary); padding: 8px; border-radius: 4px; overflow-x: auto; font-size: 12px; }
.card-body table { border-collapse: collapse; margin: 8px 0; }
.card-body th, .card-body td { border: 1px solid var(--border); padding: 4px 8px; font-size: 12px; }

/* Tooltip */
#tooltip { position: fixed; background: var(--bg-tertiary); border: 1px solid var(--border); border-radius: 4px; padding: 6px 10px; font-family: ui-monospace, Menlo, monospace; font-size: 11px; pointer-events: none; z-index: 100; }
```

- [ ] **Step 3: Commit**

```bash
git add dashboard/index.html dashboard/index.css
git commit -m "feat(dashboard): static HTML + dark-theme CSS"
```

---

## Task 7: Test fixture for offline HTML dev

*(Renumbered: done before the JS task so app.js can be developed against this fixture instead of rebuilding from `/data3` each iteration.)*

**Files:**
- Create: `tests/fixtures/dashboard/sample-index.json`

Just enough rows that opening `dashboard/index.html` against this fixture exercises each cell state.

- [ ] **Step 1: Write the fixture**

```json
{
  "built_at": "2026-05-15T02:13:00+00:00",
  "scenario_types": ["native-engine/godot", "web-map/cesium"],
  "rounds": [
    {
      "id": "r17",
      "date": "2026-05-05",
      "results_path": "/data3/bhdr-eval-results/2026-05-05-r17/",
      "aux_paths": ["/data3/bhdr-eval-results/2026-05-05-r17-resume/"],
      "narrative_path": "docs/eval-rounds/2026-05-05-r17.md",
      "narrative_md": "# Round R17 (test)\n\nFixture round.\n",
      "headline": "Fixture round.",
      "results": [
        {
          "scenario_id": "sample_godot_solved",
          "scenario_type": "native-engine/godot",
          "mode": "code_only",
          "tier": "opus",
          "solved": true,
          "scorer": "file_level",
          "confidence": "high",
          "output_tokens": 6116,
          "tool_calls": 13,
          "expected_failure": null
        },
        {
          "scenario_id": "sample_godot_stable_failure",
          "scenario_type": "native-engine/godot",
          "mode": "code_only",
          "tier": "opus",
          "solved": false,
          "scorer": "no_signal",
          "confidence": "low",
          "output_tokens": 48117,
          "tool_calls": 45,
          "expected_failure": {"reason": "reasoning-depth ceiling", "first_observed_round": "r15"}
        },
        {
          "scenario_id": "sample_cesium_judge",
          "scenario_type": "web-map/cesium",
          "mode": "code_only",
          "tier": "opus",
          "solved": true,
          "scorer": "judge",
          "confidence": "medium",
          "output_tokens": 30030,
          "tool_calls": 61,
          "expected_failure": null
        }
      ]
    },
    {
      "id": "r18",
      "date": "2026-05-14",
      "results_path": "/data3/bhdr-eval-results/2026-05-14-r18/",
      "aux_paths": [],
      "narrative_path": "docs/eval-rounds/2026-05-14-r18.md",
      "narrative_md": "# Round R18 (test)\n\nSecond fixture round. bug_class dispatch deleted.\n",
      "headline": "Second fixture round. bug_class dispatch deleted.",
      "results": [
        {
          "scenario_id": "sample_godot_solved",
          "scenario_type": "native-engine/godot",
          "mode": "code_only",
          "tier": "opus",
          "solved": true,
          "scorer": "file_level",
          "confidence": "high",
          "output_tokens": 6116,
          "tool_calls": 13,
          "expected_failure": null
        },
        {
          "scenario_id": "sample_godot_stable_failure",
          "scenario_type": "native-engine/godot",
          "mode": "code_only",
          "tier": "opus",
          "solved": false,
          "scorer": "no_signal",
          "confidence": "low",
          "output_tokens": 50000,
          "tool_calls": 45,
          "expected_failure": {"reason": "reasoning-depth ceiling", "first_observed_round": "r15"}
        },
        {
          "scenario_id": "sample_cesium_judge",
          "scenario_type": "web-map/cesium",
          "mode": "code_only",
          "tier": "opus",
          "solved": true,
          "scorer": "file_level",
          "confidence": "high",
          "output_tokens": 12000,
          "tool_calls": 8,
          "expected_failure": null
        }
      ]
    }
  ]
}
```

- [ ] **Step 2: Add a README hint**

Create `tests/fixtures/dashboard/README.md`:

```markdown
# Dashboard fixture

To verify `dashboard/index.html` without rebuilding from `/data3`,
symlink this file to `dashboard/index.json`:

```bash
ln -sf $(pwd)/tests/fixtures/dashboard/sample-index.json dashboard/index.json
```

Then open `dashboard/index.html` in a browser.
```

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/dashboard/
git commit -m "test(dashboard): sample index.json fixture for HTML dev"
```

---

## Task 8: Dashboard JS rendering (`app.js`)

*(Renumbered: do the fixture (Task 7 above) first so app.js can be developed against `sample-index.json` without rebuilding from `/data3` each iteration.)*

**Setup**: before starting, symlink the fixture so the browser has data to render:

```bash
ln -sf $(pwd)/tests/fixtures/dashboard/sample-index.json dashboard/index.json
```

This file is gitignored — the symlink isn't checked in. After all three substeps land, replace it by running `scripts/build-eval-dashboard.sh` (Task 9 covers this).

The full file is shown in one block below for reference; **implement it in three substeps** (Steps 1a, 1b, 1c) with a browser check between each so issues surface incrementally.

**Files:**
- Create: `dashboard/app.js`

The script fetches `index.json`, then renders panels (Plotly), grid (plain table), cards (marked.js). Controls re-render on change.

- [ ] **Step 1a: Skeleton + fetch + control wiring (no rendering yet)**

Write only the IIFE wrapper, `state`, the `fetch` of `index.json`, the
control-event wiring, and stubs `renderPanels = renderGrid = renderCards = () => {}`.
Open `dashboard/index.html` in a browser; verify the header timestamp
appears and the dropdowns are wired (open devtools, change selects,
nothing crashes). Commit:

```bash
git add dashboard/app.js
git commit -m "feat(dashboard): app.js skeleton + control wiring"
```

- [ ] **Step 1b: Plotly per-type panels (`renderPanels` + helpers)**

Implement `renderPanels`, `buildTraces`, `perRoundMetric` from the
reference code below. Browser-check: panels render with at least one
trace per type. Switch the metric dropdown; chart updates. Commit:

```bash
git add dashboard/app.js
git commit -m "feat(dashboard): per-type Plotly chart panels"
```

- [ ] **Step 1c: Grid + narrative cards (`renderGrid` + `renderCards` + tooltip)**

Implement `renderGrid` (incl. `shortenSid`, `attachTooltip`, `elem`) and
`renderCards`. Browser-check: scenario × round table appears with
colored cells; hover shows tooltip; newest round's card expands by
default; clicking other headers toggles them. Commit:

```bash
git add dashboard/app.js
git commit -m "feat(dashboard): scenario grid + narrative cards"
```

**Reference (the full file, for context across the three substeps above):**

```javascript
// dashboard/app.js
(async function main() {
  const state = {
    data: null,
    metric: "solve_pct",
    tier: "all",
    includeStable: false,
  };

  try {
    const resp = await fetch("index.json", { cache: "no-store" });
    state.data = await resp.json();
  } catch (e) {
    document.querySelector("main").innerHTML =
      `<p style="color:#fca5a5">Failed to load index.json — run scripts/build-eval-dashboard.sh first.</p>`;
    return;
  }

  document.getElementById("built-at").textContent =
    "built " + state.data.built_at;

  const metricSel = document.getElementById("metric-select");
  const tierSel = document.getElementById("tier-select");
  const stableChk = document.getElementById("include-stable");
  metricSel.addEventListener("change", e => { state.metric = e.target.value; renderAll(); });
  tierSel.addEventListener("change", e => { state.tier = e.target.value; renderAll(); });
  stableChk.addEventListener("change", e => { state.includeStable = e.target.checked; renderAll(); });

  renderAll();

  function renderAll() {
    renderPanels();
    renderGrid();
    renderCards();
  }

  /* ===== Per-type panels (Plotly) ===== */

  function renderPanels() {
    const types = state.data.scenario_types.filter(t => t !== "unknown");
    const grid = document.getElementById("panel-grid");
    grid.innerHTML = "";
    for (const type of types) {
      const panel = document.createElement("div");
      panel.className = "panel";
      const title = document.createElement("div");
      title.className = "panel-title";
      title.textContent = `${type} — ${state.metric === "solve_pct" ? "solve %" : "output tokens / solved"}`;
      panel.appendChild(title);
      const chartDiv = document.createElement("div");
      panel.appendChild(chartDiv);
      grid.appendChild(panel);

      const traces = buildTraces(type);
      const layout = {
        height: 260,
        margin: { l: 40, r: 12, t: 8, b: 32 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        font: { color: "#e2e8f0", size: 11 },
        xaxis: { color: "#94a3b8", gridcolor: "#334155" },
        yaxis: {
          color: "#94a3b8",
          gridcolor: "#334155",
          rangemode: "tozero",
          ticksuffix: state.metric === "solve_pct" ? "%" : "",
        },
        legend: { font: { size: 10 }, orientation: "h", y: -0.25 },
      };
      Plotly.newPlot(chartDiv, traces, layout, {
        displayModeBar: false,
        responsive: true,
      });
    }
  }

  function buildTraces(type) {
    const modes = ["code_only", "with_bhdr"];
    const tiers = state.tier === "all"
      ? ["haiku", "sonnet", "opus"]
      : [state.tier];
    const traces = [];
    for (const mode of modes) {
      for (const tier of tiers) {
        const pts = perRoundMetric(type, mode, tier);
        if (pts.x.length === 0) continue;
        traces.push({
          x: pts.x,
          y: pts.y,
          mode: "lines+markers",
          name: `${mode === "code_only" ? "CO" : "GLA"} · ${tier}`,
          line: {
            color: mode === "code_only" ? "#60a5fa" : "#fb923c",
            dash: tier === "haiku" ? "solid" : (tier === "sonnet" ? "dash" : "dot"),
            width: 2,
          },
          marker: { size: 6 },
          hovertemplate:
            `<b>%{x}</b><br>${mode} · ${tier}<br>` +
            (state.metric === "solve_pct" ? "solve: %{y:.0f}%" : "tok/✓: %{y:.0f}") +
            " (n=%{customdata})<extra></extra>",
          customdata: pts.n,
          connectgaps: false,
        });
      }
    }
    return traces;
  }

  function perRoundMetric(type, mode, tier) {
    const x = [], y = [], n = [];
    for (const round of state.data.rounds) {
      const rows = round.results.filter(r =>
        r.scenario_type === type && r.mode === mode && r.tier === tier
        && (state.includeStable || !r.expected_failure)
      );
      if (rows.length === 0) continue;
      x.push(round.id);
      n.push(rows.length);
      if (state.metric === "solve_pct") {
        const solved = rows.filter(r => r.solved).length;
        y.push((solved / rows.length) * 100);
      } else {
        const solvedRows = rows.filter(r => r.solved);
        if (solvedRows.length === 0) { y.push(null); continue; }
        const total = solvedRows.reduce((s, r) => s + r.output_tokens, 0);
        y.push(total / solvedRows.length);
      }
    }
    return { x, y, n };
  }

  /* ===== Scenario × round grid ===== */

  function renderGrid() {
    const container = document.getElementById("grid-container");
    container.innerHTML = "";
    const table = document.createElement("table");
    table.className = "timeline";

    // Group scenarios by latest scenario_type
    const byScenario = new Map(); // sid -> { type, byRound: { round_id: row } }
    for (const round of state.data.rounds) {
      for (const r of round.results) {
        if (state.tier !== "all" && r.tier !== state.tier) continue;
        if (!state.includeStable && r.expected_failure) {
          // still show row but flag it
        }
        let s = byScenario.get(r.scenario_id);
        if (!s) {
          s = { type: r.scenario_type, byRound: {}, isStable: false };
          byScenario.set(r.scenario_id, s);
        }
        // Latest seen wins for type
        s.type = r.scenario_type;
        if (r.expected_failure) s.isStable = true;
        // Use code_only as default mode for the grid; with_bhdr shown next to it via cell-label
        const key = `${round.id}|${r.mode}`;
        s.byRound[key] = r;
      }
    }

    // Header row: blank | round_co | round_gla per round (only render modes that have any data)
    const thead = document.createElement("thead");
    const trMode = document.createElement("tr");
    trMode.appendChild(elem("th", "scenario"));
    const roundColumns = []; // [{round_id, mode}]
    for (const round of state.data.rounds) {
      for (const mode of ["code_only", "with_bhdr"]) {
        const anyRow = round.results.some(r =>
          r.mode === mode && (state.tier === "all" || r.tier === state.tier)
        );
        if (!anyRow) continue;
        roundColumns.push({ round_id: round.id, mode });
        trMode.appendChild(elem("th", `${round.id} · ${mode === "code_only" ? "CO" : "GLA"}`));
      }
    }
    thead.appendChild(trMode);
    table.appendChild(thead);

    // Body, grouped by type
    const tbody = document.createElement("tbody");
    const byType = new Map();
    for (const [sid, s] of byScenario.entries()) {
      if (!byType.has(s.type)) byType.set(s.type, []);
      byType.get(s.type).push({ sid, ...s });
    }
    for (const [type, scenarios] of [...byType.entries()].sort()) {
      const tr = document.createElement("tr");
      tr.className = "type-header";
      const td = elem("td", type);
      td.colSpan = roundColumns.length + 1;
      tr.appendChild(td);
      tbody.appendChild(tr);
      for (const s of scenarios.sort((a, b) => a.sid.localeCompare(b.sid))) {
        const tr = document.createElement("tr");
        if (s.isStable) tr.className = "stable";
        const sidCell = elem("td", shortenSid(s.sid));
        sidCell.style.textAlign = "left";
        sidCell.title = s.sid;
        tr.appendChild(sidCell);
        for (const col of roundColumns) {
          const cell = document.createElement("td");
          cell.className = "cell";
          const r = s.byRound[`${col.round_id}|${col.mode}`];
          if (!r) {
            cell.textContent = "";
            cell.classList.add("cell-skipped");
          } else if (r.solved && r.scorer === "file_level" && r.confidence === "high") {
            cell.textContent = "✓";
            cell.classList.add("cell-hi");
            attachTooltip(cell, r);
          } else if (r.solved) {
            cell.textContent = "✓";
            cell.classList.add("cell-mid");
            attachTooltip(cell, r);
          } else {
            cell.textContent = "✗";
            cell.classList.add("cell-lo");
            attachTooltip(cell, r);
          }
          tr.appendChild(cell);
        }
        tbody.appendChild(tr);
      }
    }
    table.appendChild(tbody);
    container.appendChild(table);
  }

  function shortenSid(sid) {
    // Trim the long taxonomy-prefix to last segment
    const parts = sid.split("_");
    return parts.slice(-3).join("_");
  }

  function attachTooltip(el, r) {
    el.addEventListener("mouseenter", e => {
      const tt = document.getElementById("tooltip");
      tt.innerHTML =
        `<b>${r.scenario_id}</b><br>` +
        `mode=${r.mode} tier=${r.tier}<br>` +
        `verdict=${r.scorer}/${r.confidence}<br>` +
        `tok=${r.output_tokens} tools=${r.tool_calls}` +
        (r.expected_failure ? `<br>⊘ ${r.expected_failure.reason || ""}` : "");
      tt.hidden = false;
      tt.style.left = (e.pageX + 12) + "px";
      tt.style.top = (e.pageY + 12) + "px";
    });
    el.addEventListener("mouseleave", () => {
      document.getElementById("tooltip").hidden = true;
    });
  }

  function elem(tag, text) {
    const e = document.createElement(tag);
    e.textContent = text;
    return e;
  }

  /* ===== Per-round narrative cards ===== */

  function renderCards() {
    const container = document.getElementById("card-container");
    container.innerHTML = "";
    // Reverse: newest round first
    const ordered = [...state.data.rounds].reverse();
    for (let i = 0; i < ordered.length; i++) {
      const round = ordered[i];
      const card = document.createElement("div");
      card.className = "card";
      const header = document.createElement("div");
      header.className = "card-header";
      header.innerHTML =
        `<span class="id">${round.id}</span>` +
        `<span class="date">${round.date || ""}</span>` +
        `<span class="headline">${round.headline}</span>` +
        `<span class="toggle">▼</span>`;
      const body = document.createElement("div");
      body.className = "card-body";
      if (round.narrative_md) {
        body.innerHTML = marked.parse(round.narrative_md);
      } else {
        body.innerHTML = "<p>(no round log)</p>";
      }
      if (i === 0) body.classList.add("expanded");
      header.addEventListener("click", () => body.classList.toggle("expanded"));
      card.appendChild(header);
      card.appendChild(body);
      container.appendChild(card);
    }
  }
})();
```

- [ ] **Step 2: Final cross-check against real /data3 data**

Drop the fixture symlink and rebuild from the real source:

```bash
rm dashboard/index.json
scripts/build-eval-dashboard.sh
```

Reload `dashboard/index.html` in the browser. Verify R12c..R18 render
with no console errors. Each substep's commit covers its own diff; no
additional commit needed here unless final tweaks were made.

---

## Task 9: Wrap-up + documentation

- [ ] **Step 1: Run the full suite**

Run: `PYTHONPATH=src/python python3 -m pytest tests/unit/python/test_dashboard_*.py -v`
Expected: all green.

- [ ] **Step 2: Build against real /data3**

Run: `scripts/build-eval-dashboard.sh`
Expected: prints `Wrote N round(s) to dashboard/index.json` for N ≥ 8.

- [ ] **Step 3: Smoke-open the dashboard in a browser**

```bash
# Linux
xdg-open dashboard/index.html
# macOS
open dashboard/index.html
```

Verify the live R12c..R18 data renders without console errors.

- [ ] **Step 4: Update eval-next-steps.md**

Append the following section to `docs/eval-next-steps.md` (after the
"## Snapshot pipeline invariants" block, near the end):

```markdown
## Tooling: local eval dashboard

`scripts/build-eval-dashboard.sh` aggregates
`/data3/bhdr-eval-results/*` + `docs/eval-rounds/*.md` into
`dashboard/index.json`, then open `dashboard/index.html` in a
browser. Primary view: per-scenario-type Plotly panels comparing
`code_only` vs `with_bhdr` across rounds. Scope: R12c+ (rounds with
`verdict` field). Pre-R12 legacy rounds excluded — see
`docs/superpowers/specs/2026-05-15-eval-dashboard-design.md`.
```

- [ ] **Step 5: Commit doc updates**

```bash
git add docs/eval-next-steps.md
git commit -m "docs(eval): note local dashboard in eval-next-steps"
```

- [ ] **Step 6: Tag plan completion**

```bash
git tag dashboard-r18 HEAD
```

Done. The dashboard reads `/data3/bhdr-eval-results/*` + `docs/eval-rounds/*.md` and renders the comparison view. As R19's pipeline-fix work lands (multi-tier eval, with_bhdr restored), no code changes are needed — the dashboard picks up the new modes/tiers automatically from the result JSON via the meta.json tier override.
