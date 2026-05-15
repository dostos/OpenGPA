"""Result loading, merging, enrichment for the dashboard build."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator, Optional

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
