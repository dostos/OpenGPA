"""Build the maintainer-framing prompt for a single scenario/mode.

Usage:
  python3 build_prompt.py <scenario_id> <mode>

Writes the rendered prompt to stdout.  Uses the shared renderer in
gpa.eval.prompts so the harness and the dispatcher stay in sync.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/jingyulee/gh/gla/src/python")

from gpa.eval.prompts import render_maintainer_prompt
from gpa.eval.scenario import ScenarioLoader


def _framework_from_repo(repo_url: str | None) -> str:
    if not repo_url:
        return "the framework"
    return repo_url.rstrip("/").split("/")[-1]


def _extract_user_report(md_text: str) -> str:
    m = re.search(r"^## User Report\n(.+?)(?=\n## )", md_text, re.DOTALL | re.MULTILINE)
    return m.group(1).strip() if m else ""


def main() -> None:
    if len(sys.argv) != 3:
        print("usage: build_prompt.py <scenario_id> <mode>", file=sys.stderr)
        sys.exit(2)
    scenario_id = sys.argv[1]
    mode = sys.argv[2]  # 'with_bhdr' or 'code_only'

    loader = ScenarioLoader(Path("/home/jingyulee/gh/gla/tests/eval"))
    s = loader.load(scenario_id)

    scen_dir = Path(s.scenario_dir) if s.scenario_dir else Path(f"/home/jingyulee/gh/gla/tests/eval/{scenario_id}")
    md_text = (scen_dir / "scenario.md").read_text(encoding="utf-8")
    user_report = _extract_user_report(md_text)

    fw = s.framework if s.framework and s.framework != "none" else _framework_from_repo(s.upstream_snapshot_repo)
    repo = s.upstream_snapshot_repo or ""
    sha = s.upstream_snapshot_sha or ""

    prompt = render_maintainer_prompt(
        framework=fw,
        user_report=user_report,
        upstream_snapshot_repo=repo,
        upstream_snapshot_sha=sha,
        mode=mode,
    )
    sys.stdout.write(prompt)


if __name__ == "__main__":
    main()
