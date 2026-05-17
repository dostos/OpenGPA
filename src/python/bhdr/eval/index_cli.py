"""Read-only reporter for the eval scenario index."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import List

from bhdr.eval.scenario_metadata import Scenario, iter_scenarios

# Supported dotted paths for --filter
_FILTER_FIELDS = {
    "taxonomy.category",
    "taxonomy.framework",
    "taxonomy.bug_class",
    "backend.api",
    "backend.status",
    "source.type",
    "round",
    "status",
}


def _getattr_dotted(scenario: Scenario, path: str) -> str:
    """Return a nested attribute value given a dotted path string."""
    parts = path.split(".", 1)
    obj = getattr(scenario, parts[0])
    if len(parts) == 1:
        return str(obj)
    return str(getattr(obj, parts[1]))


def apply_filter(scenarios: List[Scenario], expr: str) -> List[Scenario]:
    """Return scenarios matching ALL comma-separated dotted-path=value clauses."""
    clauses = []
    for clause in expr.split(","):
        clause = clause.strip()
        if "=" not in clause:
            raise ValueError(f"invalid filter clause (missing '='): {clause!r}")
        path, _, value = clause.partition("=")
        path = path.strip()
        value = value.strip()
        if path not in _FILTER_FIELDS:
            raise ValueError(f"unknown filter field: {path!r}")
        clauses.append((path, value))

    result = []
    for s in scenarios:
        if all(_getattr_dotted(s, p) == v for p, v in clauses):
            result.append(s)
    return result


def build_taxonomy_table(scenarios: List[Scenario]) -> str:
    counts: Counter = Counter()
    for s in scenarios:
        counts[(s.taxonomy.category, s.taxonomy.framework)] += 1
    rows = sorted(counts.items())
    lines = ["| category | framework | count |", "|---|---|---|"]
    for (cat, fw), n in rows:
        lines.append(f"| {cat} | {fw} | {n} |")
    return "\n".join(lines)


def build_backend_table(scenarios: List[Scenario]) -> str:
    counts: Counter = Counter()
    for s in scenarios:
        counts[(s.backend.api, s.backend.status)] += 1
    rows = sorted(counts.items())
    lines = ["| api | status | count |", "|---|---|---|"]
    for (api, st), n in rows:
        lines.append(f"| {api} | {st} | {n} |")
    return "\n".join(lines)


def build_round_table(scenarios: List[Scenario]) -> str:
    counts: Counter = Counter()
    for s in scenarios:
        counts[s.round] += 1
    rows = sorted(counts.items())
    lines = ["| round | count |", "|---|---|"]
    for rnd, n in rows:
        lines.append(f"| {rnd} | {n} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bhdr-eval")
    sub = p.add_subparsers(dest="cmd", required=True)
    px = sub.add_parser("index")
    px.add_argument("--by", choices=["taxonomy", "backend", "round"], default="taxonomy")
    px.add_argument("--root", type=Path, default=Path("tests/eval"))
    px.add_argument(
        "--filter",
        default=None,
        help=(
            "Comma-separated dotted-path=value clauses, AND-combined. "
            "Example: --filter taxonomy.framework=godot,backend.api=vulkan"
        ),
    )
    args = p.parse_args(argv)
    scenarios = list(iter_scenarios(args.root))
    if args.filter:
        scenarios = apply_filter(scenarios, args.filter)
    builders = {
        "taxonomy": build_taxonomy_table,
        "backend": build_backend_table,
        "round": build_round_table,
    }
    print(builders[args.by](scenarios))
    return 0


if __name__ == "__main__":
    sys.exit(main())
