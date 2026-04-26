from __future__ import annotations
import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from gpa.eval.curation.coverage_log import CoverageLog


DEFAULT_QUERIES: dict[str, list[str]] = {
    "issue": [
        # === Framework bugs (original) ===
        'repo:mrdoob/three.js is:issue is:closed reason:completed "z-fighting" OR "winding" OR "culling"',
        'repo:mrdoob/three.js is:issue is:closed reason:completed "shader" "uniform"',
        'repo:mrdoob/three.js is:issue is:closed reason:completed "NaN" OR "Inf" texture',
        'repo:godotengine/godot is:issue is:closed reason:completed label:"topic:rendering" shader',
        'repo:godotengine/godot is:issue is:closed reason:completed label:"topic:rendering" "z-fighting" OR "depth"',
        'repo:BabylonJS/Babylon.js is:issue is:closed reason:completed label:"bug" shader precision',

        # === User project bugs (projects USING the frameworks) ===
        # Three.js user projects — rendering issues from misusing the API
        '"three.js" "rendering" "wrong color" OR "invisible" OR "black screen" is:issue is:closed -repo:mrdoob/three.js',
        '"three.js" "texture" "not showing" OR "flickering" OR "missing" is:issue is:closed -repo:mrdoob/three.js',
        '"three.js" "depth" OR "z-fighting" OR "transparent" "bug" is:issue is:closed -repo:mrdoob/three.js',
        # Godot user projects
        '"godot" "rendering" "wrong" OR "broken" OR "glitch" is:issue is:closed -repo:godotengine/godot',
        '"godot" "shader" "not working" OR "visual bug" is:issue is:closed -repo:godotengine/godot',
        # Open3D user projects
        'repo:isl-org/Open3D is:issue is:closed "rendering" "wrong" OR "broken" OR "black"',
        '"open3d" "visualization" "not rendering" OR "wrong color" OR "missing" is:issue is:closed',
        # Babylon.js user projects
        '"babylon.js" "rendering" "wrong" OR "glitch" OR "artifact" is:issue is:closed -repo:BabylonJS/Babylon.js',
        # p5.js / Processing user projects
        '"p5.js" "webgl" "rendering" "bug" OR "wrong" OR "broken" is:issue is:closed -repo:processing/p5.js',
        # General WebGL/OpenGL user issues
        '"webgl" "state" "leak" OR "not reset" OR "wrong texture" is:issue is:closed',
        '"opengl" "rendering" "bug" "uniform" OR "texture" OR "blend" is:issue is:closed',
    ],
    "commit": [
        'repo:mrdoob/three.js "fix:" "z-fighting" OR "culling" OR "precision"',
        'repo:godotengine/godot "fix:" "shader" OR "depth buffer"',
    ],
    # SO queries are lists of tags combined AND-wise (SO search restricts
    # to questions tagged with ALL provided tags).
    "stackoverflow": [
        # Framework consumers — rendering bugs from misusing APIs
        ["three.js", "rendering"],
        ["three.js", "texture"],
        ["three.js", "transparency"],
        ["three.js", "shader-material"],
        ["webgl", "glsl"],
        ["webgl", "framebuffer"],
        ["webgl", "depth-buffer"],
        ["webgl", "blending"],
        ["godot", "shader"],
        ["godot", "rendering"],
        ["godot4", "visual-shader"],
        ["babylon.js", "rendering"],
        ["babylon.js", "shader"],
        ["open3d", "visualization"],
        ["opengl", "debug"],
        ["opengl", "texture"],
        ["opengl", "framebuffer-object"],
        ["opengl", "depth-testing"],
        ["opengl", "face-culling"],
        ["vulkan", "rendering"],
        ["vulkan", "descriptor-set"],
        ["p5.js", "webgl"],
        ["unity3d", "shader"],
        ["unity3d", "rendering"],
        ["unreal-engine4", "rendering"],
    ],
}


# Title/label patterns that strongly suggest the issue is NOT a visual rendering bug.
# Matched case-insensitively against candidate.title and (lowercased) label names.
_NON_RENDERING_KEYWORDS = [
    # Type system / API surface
    r"\btypescript\b", r"\btype\s+def", r"\btype\s+error",
    r"\bd\.ts\b", r"\btyping\b",
    # Docs / examples / tutorials
    r"\bdocs?\b", r"\bdocumentation\b", r"\bexample\b", r"\btutorial\b",
    r"\breadme\b", r"\bfaq\b",
    # Build / packaging / ci
    r"\bbuild\s+error\b", r"\bnpm\b", r"\byarn\b", r"\bpnpm\b",
    r"\bbundle\b", r"\bbundler\b", r"\brollup\b", r"\bvite\b",
    r"\bpackage\.json\b", r"\bci\b", r"\bgithub\s+actions\b",
    # Editor / dev tools
    r"\beditor\b", r"\binspector\b", r"\beslint\b", r"\btslint\b",
    r"\bvscode\b", r"\bnode\s+material\s+editor\b", r"\bNME\b",
    # API surface (non-visual)
    r"\bapi\s+change\b", r"\bdeprecation\b", r"\brefactor\b",
    # Input / UI / DOM
    r"\bdom\b", r"\bkeyboard\b", r"\bpointer\s+event\b",
    r"\bfocus\b", r"\btouch\s+event\b", r"\binput\s+focus\b",
    # Support / question
    r"\bquestion\b", r"\bhow\s+to\b", r"\bplease\s+help\b",
]

_NON_RENDERING_LABELS = {
    "documentation", "docs", "typescript", "types", "editor",
    "tooling", "build", "ci", "duplicate", "question",
    "needs-info", "needs info", "workflow", "examples",
}

_NON_RENDERING_RE = re.compile("|".join(_NON_RENDERING_KEYWORDS), re.IGNORECASE)


def _is_obviously_non_rendering_so(q) -> bool:
    """SO-specific pre-filter — mirrors _is_obviously_non_rendering but
    checks tags (not labels) and uses the title heuristic."""
    if _NON_RENDERING_RE.search(getattr(q, "title", "") or ""):
        return True
    tag_set = {t.lower().strip() for t in (getattr(q, "tags", None) or [])}
    return bool(tag_set & _NON_RENDERING_LABELS)


def _is_obviously_non_rendering(cand: "DiscoveryCandidate") -> bool:
    """Cheap pre-triage filter.

    Returns True when the title or any label strongly suggests the issue is NOT
    a visual rendering bug — so we can skip the LLM triage call entirely.

    Conservative: false negatives (letting through non-rendering bugs) are fine,
    triage will catch them; false positives (rejecting real rendering bugs) are
    what we want to avoid, so the patterns only match terms that are
    overwhelmingly non-visual in our source repos.
    """
    if _NON_RENDERING_RE.search(cand.title or ""):
        return True
    label_set = {l.lower().strip() for l in (cand.labels or [])}
    if label_set & _NON_RENDERING_LABELS:
        return True
    return False


@dataclass
class DiscoveryCandidate:
    url: str
    source_type: str                     # "issue" | "fix_commit" | "stackoverflow"
    title: str
    labels: list[str] = field(default_factory=list)
    created_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class GitHubSearch:
    """Runs GitHub Search queries via the `gh api` CLI."""

    def search_issues(self, query: str, per_page: int = 30) -> list[DiscoveryCandidate]:
        proc = subprocess.run(
            ["gh", "api", "-X", "GET", "search/issues",
             "-f", f"q={query}", "-f", f"per_page={per_page}"],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(proc.stdout)
        out: list[DiscoveryCandidate] = []
        for item in data.get("items", []):
            out.append(DiscoveryCandidate(
                url=item["html_url"],
                source_type="issue",
                title=item.get("title", ""),
                labels=[l["name"] for l in item.get("labels", [])],
                created_at=item.get("created_at"),
                metadata={"number": item.get("number")},
            ))
        return out

    def search_commits(self, query: str, per_page: int = 30) -> list[DiscoveryCandidate]:
        proc = subprocess.run(
            ["gh", "api", "-X", "GET", "search/commits",
             "-f", f"q={query}", "-f", f"per_page={per_page}",
             "-H", "Accept: application/vnd.github.cloak-preview+json"],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(proc.stdout)
        out: list[DiscoveryCandidate] = []
        for item in data.get("items", []):
            out.append(DiscoveryCandidate(
                url=item["html_url"],
                source_type="fix_commit",
                title=item.get("commit", {}).get("message", "").split("\n")[0][:120],
                created_at=item.get("commit", {}).get("author", {}).get("date"),
                metadata={"sha": item.get("sha")},
            ))
        return out


class StackExchangeSearch:
    """Thin wrapper over ``stackoverflow.search_questions`` for injection
    symmetry with :class:`GitHubSearch`."""

    def search_questions(self, tags: list[str], per_page: int = 30):
        from gpa.eval.curation.stackoverflow import search_questions
        return search_questions(tags, per_page=per_page)


class Discoverer:
    def __init__(self, search, coverage_log: "CoverageLog",
                 queries: dict, batch_quota: int = 20,
                 so_search=None):
        self._search = search
        self._so_search = so_search
        self._log = coverage_log
        self._queries = queries
        self._quota = batch_quota

    def run(self) -> list[DiscoveryCandidate]:
        """Discover candidates with per-query fairness.

        Iterates all queries (issue + commit + stackoverflow) once each,
        capped at ``per_query_cap = max(1, batch_quota // total_queries)`` URLs
        per query. If the first pass leaves the quota unfilled, a second pass
        re-iterates any queries that hit their cap to absorb the remainder.
        Query order is preserved within each pass so the YAML's intended
        priority is honored.

        This avoids the prior "first query wins all quota" failure mode where
        a single high-yield query at the top of the list would consume the
        full ``batch_quota`` and starve the rest of the cross-family corpus.
        """
        # Collect all queries with their per-type executor. Each entry is
        # (kind, query_payload) where executor knowns how to fetch + adapt.
        issue_qs = list(self._queries.get("issue", []))
        commit_qs = list(self._queries.get("commit", []))
        so_qs = list(self._queries.get("stackoverflow", [])) if self._so_search is not None else []

        all_query_descs: list[tuple[str, object]] = (
            [("issue", q) for q in issue_qs]
            + [("commit", q) for q in commit_qs]
            + [("stackoverflow", tags) for tags in so_qs]
        )
        total_queries = len(all_query_descs)
        if total_queries == 0:
            return []

        per_query_cap = max(1, self._quota // total_queries)

        seen: set[str] = set()
        out: list[DiscoveryCandidate] = []
        # Per-query iterator state across passes: idx -> remaining-cands list,
        # plus how many we've already emitted from that query.
        per_query_pools: list[list[DiscoveryCandidate]] = [
            self._fetch_for_query(kind, payload) for kind, payload in all_query_descs
        ]
        per_query_emitted: list[int] = [0] * total_queries

        def _drain_query(idx: int, cap: int) -> int:
            """Emit up to ``cap`` (relative to current count from this query)
            additional candidates for query ``idx``. Returns how many were
            appended to ``out``. Stops early if the global quota is reached."""
            appended = 0
            pool = per_query_pools[idx]
            while pool and per_query_emitted[idx] < cap:
                if len(out) >= self._quota:
                    return appended
                cand = pool.pop(0)
                accepted = self._consider_candidate(cand, seen)
                if accepted is None:
                    # Filtered (dup / non-rendering) — does not count against cap.
                    continue
                out.append(accepted)
                per_query_emitted[idx] += 1
                appended += 1
            return appended

        # Pass 1: per-query fairness.
        for i in range(total_queries):
            if len(out) >= self._quota:
                break
            _drain_query(i, per_query_cap)

        # Pass 2+: keep cycling through queries that still have material,
        # raising each query's cap one at a time until the global quota is
        # filled or every query is exhausted. Preserves YAML order within
        # each pass.
        while len(out) >= 0:
            if len(out) >= self._quota:
                break
            progress = False
            for i in range(total_queries):
                if len(out) >= self._quota:
                    break
                if not per_query_pools[i]:
                    continue
                # Raise this query's cap by 1 and try to drain.
                added = _drain_query(i, per_query_emitted[i] + 1)
                if added > 0:
                    progress = True
            if not progress:
                # Every query is either exhausted or only producing filtered
                # results — nothing more to do.
                break

        return out

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_for_query(self, kind: str, payload) -> list[DiscoveryCandidate]:
        """Fetch raw candidates for one query.

        Returns a list of ``DiscoveryCandidate`` objects, normalized for
        the in-memory pool. SO questions are converted to candidates here
        (carrying the metadata the rest of the pipeline expects).
        """
        if kind == "issue":
            return list(self._search.search_issues(payload))
        if kind == "commit":
            return list(self._search.search_commits(payload))
        if kind == "stackoverflow":
            cands: list[DiscoveryCandidate] = []
            for q in self._so_search.search_questions(payload):
                cands.append(DiscoveryCandidate(
                    url=q.url,
                    source_type="stackoverflow",
                    title=q.title,
                    labels=list(q.tags or []),
                    created_at=q.creation_date,
                    metadata={"accepted_answer_id": q.accepted_answer_id},
                ))
            return cands
        return []

    def _consider_candidate(
        self,
        cand: "DiscoveryCandidate",
        seen: set[str],
    ) -> Optional["DiscoveryCandidate"]:
        """Apply dedup + non-rendering pre-filter to one candidate.

        Returns the candidate to emit, or ``None`` if it was filtered (dup
        or obviously non-rendering). Records discovery-stage rejections to
        the coverage log to mirror the legacy behavior so per-batch denom
        accounting remains correct.
        """
        if cand.url in seen:
            return None
        if self._log.contains_url(cand.url):
            return None
        if cand.source_type == "stackoverflow":
            # SO uses a tag-aware variant of the non-rendering filter.
            class _ProxyQ:
                def __init__(self, c):
                    self.title = c.title
                    self.tags = c.labels
                    self.url = c.url
            if _is_obviously_non_rendering_so(_ProxyQ(cand)):
                self._log_discovery_rejection(
                    cand, reason="out_of_scope_not_rendering_bug"
                )
                seen.add(cand.url)
                return None
        else:
            if _is_obviously_non_rendering(cand):
                self._log_discovery_rejection(
                    cand, reason="out_of_scope_not_rendering_bug"
                )
                seen.add(cand.url)
                return None
        seen.add(cand.url)
        return cand

    def _log_discovery_rejection(self, cand: "DiscoveryCandidate",
                                  reason: str) -> None:
        """Log a pre-triage rejection to the coverage log.

        Mirrors the shape that `log_rejection` in commit.py produces, but written
        directly here to avoid a circular import from commit.py -> discover.py.
        """
        from gpa.eval.curation.coverage_log import CoverageEntry
        from datetime import datetime, timezone
        self._log.append(CoverageEntry(
            issue_url=cand.url,
            reviewed_at=datetime.now(timezone.utc).isoformat(),
            source_type=cand.source_type,
            triage_verdict="out_of_scope",
            root_cause_fingerprint=None,
            outcome="rejected",
            scenario_id=None,
            tier=None,
            rejection_reason=reason,
            predicted_helps=None,
            observed_helps=None,
            failure_mode=None,
            eval_summary=None,
        ))
