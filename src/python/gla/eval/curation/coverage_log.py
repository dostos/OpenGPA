from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Any


@dataclass
class CoverageEntry:
    issue_url: str
    reviewed_at: str                           # ISO-8601
    source_type: str                           # "issue" | "fix_commit" | "stackoverflow"
    triage_verdict: str                        # "in_scope" | "out_of_scope" | "ambiguous"
    root_cause_fingerprint: Optional[str]
    outcome: str                               # "scenario_committed" | "rejected"
    scenario_id: Optional[str]
    tier: Optional[str]
    rejection_reason: Optional[str]
    predicted_helps: Optional[str]
    observed_helps: Optional[str]
    failure_mode: Optional[str]
    eval_summary: Optional[dict[str, Any]]


class CoverageLog:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: CoverageEntry) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry)) + "\n")

    def read_all(self) -> list[CoverageEntry]:
        if not self.path.exists():
            return []
        out: list[CoverageEntry] = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                out.append(CoverageEntry(**json.loads(line)))
        return out

    def contains_url(self, url: str) -> bool:
        return any(e.issue_url == url for e in self.read_all())

    def contains_fingerprint(self, fingerprint: str) -> bool:
        return any(
            e.root_cause_fingerprint == fingerprint
            and e.outcome == "scenario_committed"
            for e in self.read_all()
        )
