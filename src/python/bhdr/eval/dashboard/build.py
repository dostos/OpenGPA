"""Aggregate per-round eval results into dashboard/index.json.

Entry point: ``python -m bhdr.eval.dashboard.build``.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bhdr.eval.dashboard._layout import (
    extract_date, fold_rerun_dirs, pick_result_files,
)
from bhdr.eval.dashboard._corpus import compute_corpus_stats
from bhdr.eval.dashboard._narrative import extract_headline, find_narrative
from bhdr.eval.dashboard._results import (
    enrich_results, load_and_merge_results, load_or_seed_tier_meta,
)
from bhdr.eval.scenario import ScenarioLoader


_DATA3_ROOT = Path("/data3/gla-eval-results")
_ROUNDS_DIR = Path("docs/eval-rounds")
_EVAL_ROOT = Path("tests/eval")
_OUTPUT_PATH = Path("dashboard/index.json")


def build_index(
    *,
    data3_root: Path,
    rounds_dir: Path,
    output_path: Path,
    scenario_loader,
    eval_root: Path | None = None,
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
        tier, _model = load_or_seed_tier_meta(primary)
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

    # Corpus stats — independent walk of tests/eval/ for dataset overview.
    # Best-effort: if the eval root is absent (e.g. running from a stripped
    # checkout), emit an empty corpus block rather than failing the build.
    corpus = {"total": 0}
    if eval_root is not None:
        try:
            corpus = compute_corpus_stats(eval_root)
        except Exception as exc:
            print(
                f"warning: corpus stats unavailable ({type(exc).__name__}: {exc})",
                file=sys.stderr,
            )

    payload = {
        "built_at": datetime.now(tz=timezone.utc).isoformat(),
        "rounds": rounds_out,
        "scenario_types": sorted(scenario_types),
        "corpus": corpus,
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
        eval_root=_EVAL_ROOT,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
