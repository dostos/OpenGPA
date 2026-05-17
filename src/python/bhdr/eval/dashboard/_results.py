"""Result loading, merging, enrichment for the dashboard build."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator, Optional

from bhdr.eval.metrics import EvalResult


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


def load_or_seed_tier_meta(round_dir: Path) -> tuple[str, str]:
    """Read ``round_dir/meta.json`` if present; otherwise seed it with the
    opus defaults and write it to disk. Returns (tier, model).

    The function name signals the write side-effect — callers should not
    treat this as a pure read. Every existing eval JSON carries
    ``model: "unknown"`` because the claude-cli backend doesn't capture
    the model identifier; the per-round meta is the authoritative source.
    Seeded as opus for the current cohort the first time the build runs;
    future multi-tier eval rounds (R19+) populate this from the eval CLI
    itself.
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
    :func:`bhdr.eval.scenario.is_browser_tier_scenario` (scenario.py:46):
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


def derive_inferred_api(scenario_type: str) -> str:
    """Map scenario_type to the graphics API the bug exercises.

    The mined cohort doesn't populate scenario.backend.api reliably
    (``unknown`` for ~all rounds), so we infer from the framework
    bucket. Returns one of ``webgl``, ``vulkan``, ``opengl``, ``unknown``.
    """
    if scenario_type.startswith("web-"):
        return "webgl"
    if scenario_type.startswith("native-engine/"):
        framework = scenario_type.split("/", 1)[1]
        # Godot 4.x defaults to Vulkan; bevy / wgpu also Vulkan;
        # everything else assume opengl until proven otherwise.
        if framework in ("godot", "bevy", "wgpu"):
            return "vulkan"
        return "opengl"
    if scenario_type.startswith("graphics-lib/"):
        return "opengl"
    return "unknown"


def derive_depth_bucket(tool_calls: int) -> str:
    """Bucket by agent investigation effort. Boundaries from R17/R18 data:
    median solved scenario lands around 13 tool calls; the long tail
    (45+ calls) clusters around scenarios that grind without converging.
    """
    if tool_calls < 10:
        return "shallow"
    if tool_calls < 30:
        return "moderate"
    return "deep"


def derive_fix_scope_bucket(fix_files_count: int) -> str:
    """Bucket by canonical-fix file count. A 1-file fix is a config /
    pointed-edit; 6+ files is a cross-module refactor. The split is
    load-bearing: maintainer-prompt depth language was tuned for the
    refactor case and over-steers single-file scenarios."""
    if fix_files_count == 0:
        return "unknown"
    if fix_files_count == 1:
        return "single"
    if fix_files_count <= 5:
        return "few"
    return "many"


def enrich_results(
    results: Iterable[EvalResult],
    *,
    tier: str,
    scenario_loader,
) -> Iterator[dict]:
    """Yield JSON-serialisable dicts enriched with capability + quality fields.

    Per-result, in addition to mode/tier/scorer/etc:
    - ``scenario_type``: ``<category>/<framework>`` (always)
    - ``inferred_api``: graphics API derived from scenario_type
    - ``bug_nature``: mined ``fix.bug_class`` (framework-internal / consumer-misuse / user-config / legacy / unknown)
    - ``fix_scope``: bucketed ``len(fix.files)`` — single / few / many
    - ``depth_bucket``: bucketed ``tool_calls`` — shallow / moderate / deep
    - ``qualified``: solved AND scorer=file_level AND confidence=high
      (the dashboard's false-positive proxy: solved but NOT qualified
      = rescued by judge/prose or low-confidence file_level — likely
      wrong fix accepted by the scoring pipeline)
    - ``expected_failure``: from scenario.yaml backfill

    Loader errors are non-fatal: the row is still emitted with all
    capability fields defaulting to ``"unknown"`` so the dashboard can
    surface even orphaned rows.
    """
    for r in results:
        try:
            meta = scenario_loader.load(r.scenario_id)
            stype = derive_scenario_type(getattr(meta, "scenario_dir", None))
            efailure = getattr(meta, "expected_failure", None)
            fix = getattr(meta, "fix", None)
            bug_nature = (getattr(fix, "bug_class", None) or "unknown") if fix else "unknown"
            fix_files_count = len(getattr(fix, "files", []) or []) if fix else 0
        except Exception:
            stype = "unknown"
            efailure = None
            bug_nature = "unknown"
            fix_files_count = 0
        verdict = r.verdict or {}
        solved = bool(verdict.get("solved"))
        scorer = verdict.get("scorer", "no_signal")
        confidence = verdict.get("confidence", "low")
        qualified = solved and scorer == "file_level" and confidence == "high"
        yield {
            "scenario_id": r.scenario_id,
            "scenario_type": stype,
            "inferred_api": derive_inferred_api(stype),
            "bug_nature": bug_nature,
            "fix_scope": derive_fix_scope_bucket(fix_files_count),
            "fix_files_count": fix_files_count,
            "depth_bucket": derive_depth_bucket(r.tool_calls),
            "mode": r.mode,
            "tier": tier,
            "solved": solved,
            "qualified": qualified,
            "scorer": scorer,
            "confidence": confidence,
            "output_tokens": r.output_tokens,
            "tool_calls": r.tool_calls,
            "expected_failure": efailure,
        }
