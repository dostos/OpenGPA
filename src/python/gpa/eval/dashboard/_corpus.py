"""Corpus statistics: count scenarios by taxonomy / backend / source / status.

This lives separate from the eval-result aggregation because it answers a
different question — *what does the dataset look like?* — rather than
*what did the agent do with it?* It walks ``tests/eval/`` and reads
``scenario.yaml`` files, plus the ``ScenarioLoader`` (which parses the
companion ``scenario.md``) for fix metadata.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from gpa.eval.scenario import ScenarioLoader
from gpa.eval.scenario_metadata import iter_scenarios


def compute_corpus_stats(eval_root: Path) -> dict[str, Any]:
    """Walk ``eval_root`` and return aggregate counts.

    Returns a dict with these keys:
      - ``total``: total scenario count
      - ``by_status``: scenario.yaml ``status`` field (verified / quarantined / drafted / …)
      - ``by_category``: ``taxonomy.category``
      - ``by_framework``: ``taxonomy.framework``
      - ``by_yaml_bug_class``: ``taxonomy.bug_class`` (often ``unknown``)
      - ``by_md_bug_class``: ``fix.bug_class`` parsed from scenario.md
      - ``by_backend_api``: ``backend.api``
      - ``by_backend_status``: ``backend.status``
      - ``by_source_type``: ``source.type``
      - ``with_fix_metadata``: count of scenarios with a parseable fix block
      - ``with_expected_failure``: count of scenarios flagged stable-failure
      - ``with_upstream_snapshot``: count of scenarios pointing at an upstream repo+sha
      - ``fix_scope_distribution``: count by ``fix.files`` cardinality bucket
        (``single`` / ``few`` / ``many`` / ``none``)

    Each *by_* counter is a sorted ``dict[str, int]`` so JSON output is
    deterministic.
    """
    if not eval_root.exists() or not eval_root.is_dir():
        return {"total": 0}

    yaml_status: Counter[str] = Counter()
    category: Counter[str] = Counter()
    framework: Counter[str] = Counter()
    yaml_bug_class: Counter[str] = Counter()
    backend_api: Counter[str] = Counter()
    backend_status: Counter[str] = Counter()
    source_type: Counter[str] = Counter()

    total = 0
    for s in iter_scenarios(eval_root):
        total += 1
        yaml_status[s.status or "unknown"] += 1
        category[s.taxonomy.category or "unknown"] += 1
        framework[s.taxonomy.framework or "unknown"] += 1
        yaml_bug_class[s.taxonomy.bug_class or "unknown"] += 1
        backend_api[s.backend.api or "unknown"] += 1
        backend_status[s.backend.status or "unknown"] += 1
        source_type[s.source.type or "unknown"] += 1

    # Second pass via ScenarioLoader for fix metadata. The loader is
    # tolerant — scenarios without a fix block return ``fix=None`` rather
    # than raising — so this is safe to run over the same root.
    md_bug_class: Counter[str] = Counter()
    fix_scope: Counter[str] = Counter()
    with_fix = 0
    with_expected_failure = 0
    with_snapshot = 0

    loader = ScenarioLoader(eval_dir=str(eval_root))
    for meta in loader.load_all(include_quarantined=True):
        if meta.fix is not None:
            with_fix += 1
            md_bug_class[meta.fix.bug_class or "unknown"] += 1
            n_files = len(meta.fix.files or [])
            if n_files == 0:
                fix_scope["none"] += 1
            elif n_files == 1:
                fix_scope["single"] += 1
            elif n_files <= 5:
                fix_scope["few"] += 1
            else:
                fix_scope["many"] += 1
        if meta.expected_failure is not None:
            with_expected_failure += 1
        if meta.upstream_snapshot_repo and meta.upstream_snapshot_sha:
            with_snapshot += 1

    def _sorted_counter(c: Counter[str]) -> dict[str, int]:
        # Sort by count descending, then key for ties — gives stable
        # human-readable ordering in the JSON output.
        return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))

    return {
        "total": total,
        "by_status": _sorted_counter(yaml_status),
        "by_category": _sorted_counter(category),
        "by_framework": _sorted_counter(framework),
        "by_yaml_bug_class": _sorted_counter(yaml_bug_class),
        "by_md_bug_class": _sorted_counter(md_bug_class),
        "by_backend_api": _sorted_counter(backend_api),
        "by_backend_status": _sorted_counter(backend_status),
        "by_source_type": _sorted_counter(source_type),
        "fix_scope_distribution": _sorted_counter(fix_scope),
        "with_fix_metadata": with_fix,
        "with_expected_failure": with_expected_failure,
        "with_upstream_snapshot": with_snapshot,
    }
