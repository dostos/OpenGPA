"""Taxonomy-aware mining planner.

This is a cheap front-end to the curation pipeline. It discovers candidates,
fetches enough thread text for non-LLM feature extraction, ranks candidates by
taxonomy cell and evidence quality, and writes auditable JSONL/Markdown reports.

It does not draft, validate, commit, or mutate the production coverage log.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from gpa.eval.curation.coverage_log import CoverageLog
from gpa.eval.curation.discover import (
    DEFAULT_QUERIES,
    Discoverer,
    DiscoveryCandidate,
    GitHubSearch,
    StackExchangeSearch,
)
from gpa.eval.curation.measure_yield import _NoOpCoverageLog
from gpa.eval.curation.triage import IssueThread, fetch_thread


DEFAULT_RULES_PATH = Path(__file__).with_name("mining_rules.yaml")


_FRAMEWORK_REPOS = {
    "mrdoob/three.js": ("web-3d", "three.js"),
    "BabylonJS/Babylon.js": ("web-3d", "babylon.js"),
    "playcanvas/engine": ("web-3d", "playcanvas"),
    "aframevr/aframe": ("web-3d", "a-frame"),
    "pmndrs/react-three-fiber": ("web-3d", "react-three-fiber"),
    "pmndrs/drei": ("web-3d", "drei"),
    "pmndrs/postprocessing": ("web-3d", "postprocessing"),
    "pixijs/pixijs": ("web-2d", "pixijs"),
    "konvajs/konva": ("web-2d", "konva"),
    "fabricjs/fabric.js": ("web-2d", "fabric.js"),
    "processing/p5.js": ("web-2d", "p5.js"),
    "mapbox/mapbox-gl-js": ("web-map", "mapbox-gl-js"),
    "maplibre/maplibre-gl-js": ("web-map", "maplibre-gl-js"),
    "openlayers/openlayers": ("web-map", "openlayers"),
    "Leaflet/Leaflet": ("web-map", "leaflet"),
    "visgl/deck.gl": ("web-map", "deck.gl"),
    "CesiumGS/cesium": ("web-map", "cesium"),
    "godotengine/godot": ("native-engine", "godot"),
    "godotengine/godot-docs": ("native-engine", "godot"),
    "Kitware/vtk-js": ("scientific", "vtk-js"),
    "bokeh/bokeh": ("scientific", "bokeh"),
    "KhronosGroup/glTF-Sample-Viewer": ("scientific", "gltf-sample-viewer"),
}

_TAG_FRAMEWORKS = {
    "three.js": ("web-3d", "three.js"),
    "react-three-fiber": ("web-3d", "react-three-fiber"),
    "babylon.js": ("web-3d", "babylon.js"),
    "pixi.js": ("web-2d", "pixijs"),
    "konvajs": ("web-2d", "konva"),
    "p5.js": ("web-2d", "p5.js"),
    "mapbox-gl-js": ("web-map", "mapbox-gl-js"),
    "openlayers": ("web-map", "openlayers"),
    "leaflet": ("web-map", "leaflet"),
    "godot": ("native-engine", "godot"),
    "godot4": ("native-engine", "godot"),
    "bokeh": ("scientific", "bokeh"),
    "open3d": ("scientific", "open3d"),
    "webgl": ("graphics-lib", "webgl"),
    "opengl": ("graphics-lib", "opengl"),
    "vulkan": ("graphics-lib", "vulkan"),
}

_VISUAL_PATTERNS = {
    "wrong_color": r"\bwrong color|too bright|too dark|washed|grey|gray|sRGB|gamma|colorSpace|toneMapping\b",
    "invisible_or_black": r"\binvisible|not showing|missing|black screen|blank|transparent background\b",
    "flicker_or_temporal": r"\bflicker|flickering|one frame|previous frame|trail|ghost|smear\b",
    "depth_or_order": r"\bdepth|z-fighting|behind|in front|order|sorting|overlap|below|above\b",
    "shadow": r"\bshadow|shadow.camera|shadow-camera|cropped\b",
    "artifact_geometry": r"\bartifact|extra polygon|hole|triangulation|seam|bleed|clipped\b",
}

_GPU_STATE_PATTERNS = {
    "depth_blend_state": r"\bdepthWrite|depth write|depthTest|depth test|blend|alpha|transparent|premultiplied\b",
    "color_pipeline": r"\bsRGBEncoding|outputEncoding|colorSpace|toneMapping|gamma|linear|premultiplyAlpha|colorSpaceConversion\b",
    "render_target_clear": r"\bEffectComposer|RenderPass|renderTarget|WebGLRenderTarget|autoClear|clearAlpha|clearColor|preserveDrawingBuffer\b",
    "texture_upload": r"\btexture|sampler|mipmap|ImageBitmap|TextureLoader|canvas texture|PNG|gAMA|cHRM\b",
    "draw_order": r"\blayer order|draw order|rendered below|rendered above|sorting|beforeId|z-index\b",
    "shadow_config": r"\bshadow.camera|shadow-camera|castShadow|receiveShadow|DirectionalLightShadow|shadow map\b",
    "shader_uniform": r"\bshader|uniform|WGSL|GLSL|TSL|node material|compile\b",
}

_RESOLUTION_PATTERNS = {
    "accepted_answer": r"=== Accepted Answer",
    "maintainer_resolution": r"\bclosing|fixed by|duplicate of|workaround|try|use|set|enable|disable|configure|not a bug|works as expected\b",
    "fix_reference": r"github\.com/.+/(pull|commit)/|#[0-9]+",
}

_REJECT_PATTERNS = {
    "host_build_or_types": r"\bTypeScript|typings|type error|build error|npm install|vite|webpack|rollup|CI\b",
    "docs_or_question_only": r"\bdocumentation|docs|tutorial|readme|how to\b",
    "dom_event_css": r"\bCSS|DOM|pointer event|mouse event|keyboard|focus|lifecycle|useEffect\b",
    "performance_only": r"\bperformance|fps|slow|memory leak|benchmark\b",
}


@dataclass
class MiningRules:
    framework_repos: dict[str, tuple[str, str]]
    tag_frameworks: dict[str, tuple[str, str]]
    patterns: dict[str, Any]
    scoring: dict[str, int]
    # Triage replacement: required/reject pattern groups folded in from the
    # deleted LLM triage step. Shape: {group_name: [pattern_str, ...]}.
    # An unmet "required" or matched "reject" group drops the candidate at
    # SELECT phase with terminal_reason="triage_rejected".
    triage_required: Optional[dict[str, list[str]]] = None
    triage_reject: Optional[dict[str, list[str]]] = None


@dataclass
class MiningPlanRecord:
    url: str
    source_type: str
    title: str
    taxonomy_cell: str
    category: str
    subcategory: str
    framework: Optional[str]
    bug_class_guess: str
    score: int
    reason_codes: list[str]
    stage: str
    rejection_reason: Optional[str] = None
    source_query_kind: Optional[str] = None
    source_query: Any = None
    selected: bool = False
    thread_chars: int = 0
    notes: Optional[str] = None
    # Set by triage gates in score_candidate. None = passed gates (or gates
    # not run). "triage_rejected" = dropped by triage_required/triage_reject
    # rules. The orchestrator (Task 5) maps this onto JourneyRow.terminal_reason.
    terminal_reason: Optional[str] = None

    @property
    def score_reasons(self) -> list[str]:
        """Alias for reason_codes — name used by triage gates and JourneyRow."""
        return self.reason_codes

    def to_dict(self) -> dict:
        return asdict(self)


def load_rules(path: str | Path = DEFAULT_RULES_PATH) -> MiningRules:
    """Load taxonomy/scoring rules from YAML.

    The module-level dictionaries remain as fallback defaults so tests and
    downstream callers can use the scorer without shipping a custom rules file.
    """
    p = Path(path)
    if not p.exists():
        return MiningRules(
            framework_repos=_FRAMEWORK_REPOS,
            tag_frameworks=_TAG_FRAMEWORKS,
            patterns={
                "visual": _VISUAL_PATTERNS,
                "gpu_state": _GPU_STATE_PATTERNS,
                "resolution": _RESOLUTION_PATTERNS,
                "reject": _REJECT_PATTERNS,
                "repro_artifact": r"\b(jsfiddle|codepen|codesandbox|reproduction|steps to|minimal|live example)\b",
                "expected_actual": r"\bexpected behavior|actual behavior|expected output|actual output\b",
                "app_resolution": r"\baccepted answer|use |set |enable |disable |configure |workaround|not a bug|works as expected|by design\b",
                "config_terms": r"\bautoClear|depthWrite|depthTest|toneMapping|colorSpace|encoding|shadow.camera|clearAlpha|renderTarget|premultiplyAlpha\b",
                "not_planned": r"\bnot_planned|won't fix|wontfix|help \(please use the forum\)|browser issue\b",
            },
            scoring={
                "visual_base": 1,
                "visual_max": 4,
                "gpu_state_each": 2,
                "gpu_state_max": 6,
                "resolution_base": 1,
                "resolution_max": 4,
                "repro_artifact": 2,
                "expected_actual": 2,
                "app_dev_bonus": 2,
                "framework_repo_bonus": 1,
                "reject_each": -2,
                "reject_max_abs": 6,
                "weak_visual": -2,
                "weak_resolution": -2,
            },
        )

    with p.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    taxonomy = data.get("taxonomy") or {}

    def _tuple_map(raw: dict[str, list[str]]) -> dict[str, tuple[str, str]]:
        out: dict[str, tuple[str, str]] = {}
        for key, val in (raw or {}).items():
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                out[key] = (str(val[0]), str(val[1]))
        return out

    def _flatten_triage(raw: Any, *, section: str) -> Optional[dict[str, list[str]]]:
        # Accepts: {group_name: {patterns: [...]}} → {group_name: [...]}
        # or already-flat {group_name: [...]}. Returns None if absent.
        # Validates every pattern by compiling at load time so a typo in
        # mining_rules.yaml fails fast instead of silently breaking gates.
        if not raw or not isinstance(raw, dict):
            return None
        out: dict[str, list[str]] = {}
        for group, val in raw.items():
            if isinstance(val, dict) and "patterns" in val:
                pats = val.get("patterns") or []
            elif isinstance(val, list):
                pats = val
            else:
                continue
            compiled: list[str] = []
            for p in pats:
                p_str = str(p)
                try:
                    re.compile(p_str)
                except re.error as exc:
                    raise ValueError(
                        f"mining_rules.yaml: invalid regex in {section}."
                        f"{group}: {p_str!r}: {exc}"
                    ) from exc
                compiled.append(p_str)
            out[str(group)] = compiled
        return out or None

    return MiningRules(
        framework_repos=_tuple_map(taxonomy.get("framework_repos") or {}),
        tag_frameworks=_tuple_map(taxonomy.get("tag_frameworks") or {}),
        patterns=data.get("patterns") or {},
        scoring={k: int(v) for k, v in (data.get("scoring") or {}).items()},
        triage_required=_flatten_triage(
            data.get("triage_required"), section="triage_required"
        ),
        triage_reject=_flatten_triage(
            data.get("triage_reject"), section="triage_reject"
        ),
    )


def _norm_text(*parts: str) -> str:
    return "\n".join(p or "" for p in parts)


def _match_codes(patterns: dict[str, str], text: str) -> list[str]:
    return [
        code for code, pattern in patterns.items()
        if re.search(pattern, text, flags=re.IGNORECASE)
    ]


def _repo_full_name(url: str) -> Optional[str]:
    m = re.search(r"github\.com/([^/]+/[^/]+)/", url)
    return m.group(1) if m else None


def infer_taxonomy(
    cand: DiscoveryCandidate,
    text: str,
    rules: Optional[MiningRules] = None,
) -> tuple[str, str, Optional[str]]:
    """Return (category, subcategory, framework_or_api)."""
    rules = rules or load_rules()
    repo = _repo_full_name(cand.url)
    if repo in rules.framework_repos:
        subcat, framework = rules.framework_repos[repo]
        metadata_text = _norm_text(
            str(cand.metadata.get("state_reason") or ""),
            str(cand.metadata.get("source_query") or ""),
            " ".join(cand.labels or []),
            text,
        )
        not_planned_re = rules.patterns.get("not_planned", "")
        app_resolution_re = rules.patterns.get("app_resolution", "")
        if (
            not_planned_re
            and re.search(not_planned_re, metadata_text, flags=re.IGNORECASE)
            and app_resolution_re
            and re.search(app_resolution_re, metadata_text, flags=re.IGNORECASE)
        ):
            return ("framework-app-dev", subcat, framework)
        return ("framework-maintenance", subcat, framework)

    labels = {label.lower() for label in (cand.labels or [])}
    for tag, (subcat, framework) in rules.tag_frameworks.items():
        if tag.lower() in labels:
            if subcat == "graphics-lib":
                return ("graphics-lib-dev", framework, framework)
            return ("framework-app-dev", subcat, framework)

    lower = text.lower()
    for token, api in (("vulkan", "vulkan"), ("webgl", "webgl"), ("opengl", "gl")):
        if token in lower:
            return ("graphics-lib-dev", api, api)
    for name, (subcat, framework) in rules.tag_frameworks.items():
        if name.lower() in lower and subcat != "graphics-lib":
            return ("framework-app-dev", subcat, framework)
    return ("unknown", "unknown", None)


def infer_bug_class(
    category: str,
    source_type: str,
    text: str,
    url: str,
    rules: Optional[MiningRules] = None,
) -> str:
    rules = rules or load_rules()
    if category == "graphics-lib-dev":
        return "graphics-lib-dev"
    app_resolution_re = rules.patterns.get("app_resolution", "")
    config_re = rules.patterns.get("config_terms", "")
    app_side = (
        re.search(app_resolution_re, text, flags=re.IGNORECASE)
        if app_resolution_re else None
    )
    config = (
        re.search(config_re, text, flags=re.IGNORECASE)
        if config_re else None
    )
    if source_type == "stackoverflow" or app_side:
        return "user-config" if config else "consumer-misuse"
    if category == "framework-maintenance":
        # Closed-as-not-planned issues in framework repos often document app
        # misuse, but completed/fix-linked issues are maintenance by default.
        if "reason:not_planned" in str(url) and app_side:
            return "consumer-misuse"
        return "framework-internal"
    if category == "framework-app-dev":
        return "user-config" if config else "consumer-misuse"
    return "unknown"


def _match_any_pattern(patterns: list[str], text: str) -> bool:
    """Return True if any of ``patterns`` matches anywhere in ``text``.

    Patterns are full Python regex strings; case-insensitive flag is encoded
    inline (``(?i)``) in the rules file rather than passed here.

    ``load_rules`` validates patterns at load time, so re.error here means
    a caller bypassed load_rules with a hand-built MiningRules. We surface
    such cases via warnings.warn — failing the gate open is the wrong
    default (it would let every candidate through reject gates and reject
    every candidate at required gates).
    """
    for pat in patterns or []:
        try:
            if re.search(pat, text):
                return True
        except re.error as exc:
            warnings.warn(
                f"invalid regex in mining rules: {pat!r}: {exc}",
                stacklevel=2,
            )
            continue
    return False


def _candidate_body(cand: DiscoveryCandidate, thread: Optional[IssueThread]) -> str:
    """Return the joined body+comments text for triage-gate matching.

    Prefers the live ``IssueThread`` (3-arg call) and falls back to
    ``cand.metadata["body"]`` (2-arg call from the orchestrator or tests
    that only have a synthetic candidate without a fetched thread).
    """
    if thread is not None:
        comments = "\n".join(thread.comments) if thread.comments else ""
        return _norm_text(thread.body or "", comments)
    return str((cand.metadata or {}).get("body") or "")


def _triage_rejected_record(
    cand: DiscoveryCandidate, reason_code: str, text: str
) -> MiningPlanRecord:
    """Build a uniform triage_rejected record. Single source of truth so
    the required-gate and reject-gate paths cannot drift apart."""
    return MiningPlanRecord(
        url=cand.url,
        source_type=cand.source_type,
        title=cand.title,
        taxonomy_cell="unknown.unknown",
        category="unknown",
        subcategory="unknown",
        framework=None,
        bug_class_guess="unknown",
        score=0,
        reason_codes=[reason_code],
        stage="scored",
        source_query_kind=(cand.metadata or {}).get("source_query_kind"),
        source_query=(cand.metadata or {}).get("source_query"),
        thread_chars=len(text),
        terminal_reason="triage_rejected",
    )


def _run_triage_gates(
    cand: DiscoveryCandidate,
    thread: Optional[IssueThread],
    rules: MiningRules,
) -> Optional[MiningPlanRecord]:
    """Return a triage_rejected record if any gate fails, else None.

    Required gates run first: every required group must match at least
    one pattern, otherwise the candidate is dropped with reason
    ``missing_<group>``. Then reject gates: any matched reject group
    drops the candidate with reason ``<group>``.
    """
    text = _norm_text(getattr(cand, "title", "") or "", _candidate_body(cand, thread))
    for group_name, patterns in (rules.triage_required or {}).items():
        if not _match_any_pattern(patterns, text):
            return _triage_rejected_record(cand, f"missing_{group_name}", text)
    for group_name, patterns in (rules.triage_reject or {}).items():
        if _match_any_pattern(patterns, text):
            return _triage_rejected_record(cand, group_name, text)
    return None


def score_candidate(
    cand: DiscoveryCandidate,
    thread: Optional[IssueThread],
    rules: Optional[MiningRules] = None,
) -> MiningPlanRecord:
    rules = rules or load_rules()

    # Triage gates run before the existing scorer. If any required group is
    # unmet or any reject group matches, the candidate is dropped here with
    # terminal_reason="triage_rejected" (subsumes the deleted LLM triage step).
    triage_dropped = _run_triage_gates(cand, thread, rules)
    if triage_dropped is not None:
        return triage_dropped

    body = thread.body if thread else ""
    comments = "\n".join(thread.comments) if thread else ""
    text = _norm_text(cand.title, body, comments)

    category, subcategory, framework = infer_taxonomy(cand, text, rules)
    bug_class = infer_bug_class(category, cand.source_type, text, cand.url, rules)

    visual = _match_codes(rules.patterns.get("visual") or {}, text)
    gpu_state = _match_codes(rules.patterns.get("gpu_state") or {}, text)
    resolution = _match_codes(rules.patterns.get("resolution") or {}, text)
    rejects = _match_codes(rules.patterns.get("reject") or {}, text)
    scoring = rules.scoring

    score = 0
    reasons: list[str] = []

    if visual:
        score += min(
            scoring.get("visual_max", 4),
            len(visual) + scoring.get("visual_base", 1),
        )
        reasons.extend(f"visual:{c}" for c in visual)
    if gpu_state:
        score += min(
            scoring.get("gpu_state_max", 6),
            scoring.get("gpu_state_each", 2) * len(gpu_state),
        )
        reasons.extend(f"gpu:{c}" for c in gpu_state)
    if resolution:
        score += min(
            scoring.get("resolution_max", 4),
            len(resolution) + scoring.get("resolution_base", 1),
        )
        reasons.extend(f"resolution:{c}" for c in resolution)
    repro_re = rules.patterns.get("repro_artifact", "")
    if repro_re and re.search(repro_re, text, re.IGNORECASE):
        score += scoring.get("repro_artifact", 2)
        reasons.append("repro_artifact")
    expected_actual_re = rules.patterns.get("expected_actual", "")
    if expected_actual_re and re.search(expected_actual_re, text, re.IGNORECASE):
        score += scoring.get("expected_actual", 2)
        reasons.append("expected_actual")
    if bug_class in {"consumer-misuse", "user-config"}:
        score += scoring.get("app_dev_bonus", 2)
        reasons.append(f"app_dev:{bug_class}")
    if category == "framework-maintenance":
        score += scoring.get("framework_repo_bonus", 1)
        reasons.append("framework_repo")
    if rejects:
        penalty = min(
            scoring.get("reject_max_abs", 6),
            abs(scoring.get("reject_each", -2)) * len(rejects),
        )
        score -= penalty
        reasons.extend(f"reject:{c}" for c in rejects)
    if not visual:
        score += scoring.get("weak_visual", -2)
        reasons.append("weak_visual_signal")
    if not resolution:
        score += scoring.get("weak_resolution", -2)
        reasons.append("weak_resolution_signal")

    taxonomy_cell = f"{category}.{subcategory}"
    if framework:
        taxonomy_cell = f"{taxonomy_cell}.{framework}"

    return MiningPlanRecord(
        url=cand.url,
        source_type=cand.source_type,
        title=cand.title,
        taxonomy_cell=taxonomy_cell,
        category=category,
        subcategory=subcategory,
        framework=framework,
        bug_class_guess=bug_class,
        score=score,
        reason_codes=reasons,
        stage="scored",
        source_query_kind=cand.metadata.get("source_query_kind"),
        source_query=cand.metadata.get("source_query"),
        thread_chars=len(text),
    )


def select_stratified(
    records: list[MiningPlanRecord],
    *,
    top_k: int,
    min_score: int,
    per_cell_cap: int,
) -> list[MiningPlanRecord]:
    eligible = [r for r in records if r.stage == "scored" and r.score >= min_score]
    by_cell: dict[str, list[MiningPlanRecord]] = defaultdict(list)
    for rec in sorted(eligible, key=lambda r: r.score, reverse=True):
        by_cell[rec.taxonomy_cell].append(rec)

    selected: list[MiningPlanRecord] = []
    while len(selected) < top_k:
        progressed = False
        for cell in sorted(by_cell):
            if len(selected) >= top_k:
                break
            already = sum(1 for r in selected if r.taxonomy_cell == cell)
            if already >= per_cell_cap or not by_cell[cell]:
                continue
            selected.append(by_cell[cell].pop(0))
            progressed = True
        if not progressed:
            break

    selected_urls = {r.url for r in selected}
    for rec in records:
        rec.selected = rec.url in selected_urls
    return selected


def load_configs(paths: list[str]) -> tuple[dict, int]:
    if not paths:
        return DEFAULT_QUERIES, 20

    merged = {"issue": [], "commit": [], "stackoverflow": []}
    batch_quota = 0
    for path in paths:
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        queries = cfg.get("queries", {})
        for key in merged:
            merged[key].extend(queries.get(key, []))
        batch_quota += int(cfg.get("batch_quota") or 0)
    return merged, batch_quota or 20


def write_jsonl(records: list[MiningPlanRecord], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec.to_dict()) + "\n")


def render_report(records: list[MiningPlanRecord], selected: list[MiningPlanRecord]) -> str:
    counts = Counter(r.taxonomy_cell for r in records if r.stage == "scored")
    selected_counts = Counter(r.taxonomy_cell for r in selected)
    rejection_counts = Counter(r.rejection_reason for r in records if r.rejection_reason)

    lines: list[str] = []
    lines.append("# Taxonomy-Aware Mining Plan")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Candidates scored: {sum(1 for r in records if r.stage == 'scored')}")
    lines.append(f"- Candidates selected: {len(selected)}")
    if rejection_counts:
        lines.append(f"- Candidates skipped: {sum(rejection_counts.values())}")
    lines.append("")

    if selected:
        lines.append("## Selected Candidates")
        lines.append("| Score | Cell | Bug Class | URL | Reason Codes |")
        lines.append("| ---: | --- | --- | --- | --- |")
        for rec in sorted(selected, key=lambda r: r.score, reverse=True):
            reasons = ", ".join(rec.reason_codes[:6])
            lines.append(
                f"| {rec.score} | `{rec.taxonomy_cell}` | `{rec.bug_class_guess}` | "
                f"{rec.url} | {reasons} |"
            )
        lines.append("")

    if counts:
        lines.append("## Taxonomy Coverage")
        lines.append("| Cell | Scored | Selected |")
        lines.append("| --- | ---: | ---: |")
        for cell, count in counts.most_common():
            lines.append(f"| `{cell}` | {count} | {selected_counts.get(cell, 0)} |")
        lines.append("")

    if rejection_counts:
        lines.append("## Skipped")
        for reason, count in rejection_counts.most_common():
            lines.append(f"- `{reason}`: {count}")
        lines.append("")

    lines.append("## Next Step")
    lines.append(
        "Feed selected URLs into the existing triage/draft pipeline, or review "
        "the JSONL reason codes to tune query packs before spending LLM budget."
    )
    return "\n".join(lines) + "\n"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover and rank mining candidates by taxonomy cell.",
    )
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        help="YAML query pack. May be passed multiple times.",
    )
    parser.add_argument(
        "--coverage-log",
        default="docs/superpowers/eval/coverage-log.jsonl",
        help="Coverage log used for read-only URL dedup.",
    )
    parser.add_argument(
        "--rules",
        default=str(DEFAULT_RULES_PATH),
        help="YAML taxonomy/scoring rules file.",
    )
    parser.add_argument(
        "--batch-quota",
        type=int,
        default=None,
        help="Override combined config batch_quota.",
    )
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--min-score", type=int, default=4)
    parser.add_argument("--per-cell-cap", type=int, default=4)
    parser.add_argument(
        "--jsonl",
        default="/tmp/mining-candidates.jsonl",
        help="Path for scored candidate JSONL.",
    )
    parser.add_argument(
        "--report",
        default="/tmp/mining-ranked.md",
        help="Path for Markdown report.",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Score title/query metadata only. Faster but less accurate.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    queries, config_quota = load_configs(args.config)
    batch_quota = args.batch_quota or config_quota
    rules = load_rules(args.rules)

    discoverer = Discoverer(
        search=GitHubSearch(),
        so_search=StackExchangeSearch(),
        coverage_log=_NoOpCoverageLog(),
        queries=queries,
        batch_quota=batch_quota,
    )
    coverage = CoverageLog(args.coverage_log)
    known_urls = {entry.issue_url for entry in coverage.read_all()}

    records: list[MiningPlanRecord] = []
    candidates = discoverer.run()
    for i, cand in enumerate(candidates, 1):
        if cand.url in known_urls:
            records.append(
                MiningPlanRecord(
                    url=cand.url,
                    source_type=cand.source_type,
                    title=cand.title,
                    taxonomy_cell="unknown.unknown",
                    category="unknown",
                    subcategory="unknown",
                    framework=None,
                    bug_class_guess="unknown",
                    score=0,
                    reason_codes=[],
                    stage="skipped",
                    rejection_reason="url_dedup",
                    source_query_kind=cand.metadata.get("source_query_kind"),
                    source_query=cand.metadata.get("source_query"),
                )
            )
            continue

        thread: Optional[IssueThread] = None
        if not args.no_fetch:
            try:
                thread = fetch_thread(cand.url)
            except Exception as exc:
                records.append(
                    MiningPlanRecord(
                        url=cand.url,
                        source_type=cand.source_type,
                        title=cand.title,
                        taxonomy_cell="unknown.unknown",
                        category="unknown",
                        subcategory="unknown",
                        framework=None,
                        bug_class_guess="unknown",
                        score=0,
                        reason_codes=[],
                        stage="skipped",
                        rejection_reason="fetch_failed",
                        source_query_kind=cand.metadata.get("source_query_kind"),
                        source_query=cand.metadata.get("source_query"),
                        notes=type(exc).__name__,
                    )
                )
                continue
        rec = score_candidate(cand, thread, rules)
        records.append(rec)
        print(
            f"[mine] {i}/{len(candidates)} score={rec.score} "
            f"cell={rec.taxonomy_cell} {rec.url}",
            flush=True,
        )

    selected = select_stratified(
        records,
        top_k=args.top_k,
        min_score=args.min_score,
        per_cell_cap=args.per_cell_cap,
    )
    write_jsonl(records, args.jsonl)
    report = render_report(records, selected)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(report)
    print(report)
    print(f"[mine] Wrote JSONL: {args.jsonl}", file=sys.stderr)
    print(f"[mine] Wrote report: {args.report}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
