"""Build the maintainer-framing prompt for R10v2 + R11.

Usage: python3 build_prompt.py <scenario_id> <mode>

Same shape as round10/build_prompt.py but with the R11 stronger
breadcrumb hint injected per-run for the with_gla mode (without
modifying the in-repo template).

Mode values: 'with_gla' | 'code_only'.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, "/home/jingyulee/gh/gla/src/python")

from gpa.eval.prompts import render_maintainer_prompt
from gpa.eval.scenario import ScenarioLoader


# Per-run patch for the WITH_GPA_ONLY block — replaces the existing tool block
# with a stronger breadcrumb-style workflow that R10's smoke showed agents
# actually need.
WITH_GPA_BLOCK_REPLACEMENT = """- OpenGPA live capture. The user report describes a visual symptom but
  does NOT name a specific numeric value. OpenGPA has captured the running
  scenario's GL state. The symptom is a numeric value whose origin matters.

  **Recommended workflow:**

  1. `curl -s -H "Authorization: Bearer $GPA_TOKEN" http://127.0.0.1:$GPA_PORT/api/v1/frames/current/overview` —
     see the captured frame summary.
  2. Look at the captured uniforms / matrices / draw calls / textures for any
     value that looks suspicious or doesn't match what you'd expect for a
     correct render. Useful endpoints:
     - `…/api/v1/frames/<id>/drawcalls` — list draw calls.
     - `…/api/v1/frames/<id>/drawcalls/<dc_id>` — per-draw uniforms, vertex/index
       counts, primitive type, shader id.
     - `…/api/v1/frames/<id>/drawcalls/<dc_id>/textures` — texture formats /
       internalformat / dimensions.
  3. For any suspicious literal (a uniform value, an index count, a texture
     format constant), run
     `curl ".../api/v1/frames/<id>/trace/value?query=<literal>"`
     to reverse-lookup which framework source field holds that value. This
     narrows the search radius from the whole repo to a handful of files.
  4. Read the candidate files; propose a fix.

  If the framework source already makes the bug obvious without consulting
  GPA, that's fine — but the breadcrumb workflow above is faster on bugs
  whose root is a wrong computed value (factor-of-PI scalars, off-by-half
  index counts, mis-mapped texture format constants, etc.)."""


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
    mode = sys.argv[2]  # 'with_gla' or 'code_only'

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

    # Per-run patch: stronger breadcrumb hint for with_gla.
    # Replace the original "OpenGPA live capture" bullet block with the
    # breadcrumb-style block.
    if mode == "with_gla":
        # Match the OpenGPA bullet that the renderer emitted.  The bullet
        # spans multiple lines, ending right before "# Task".
        new_prompt = re.sub(
            r"- OpenGPA live capture\..*?(?=\n# Task)",
            WITH_GPA_BLOCK_REPLACEMENT,
            prompt,
            count=1,
            flags=re.DOTALL,
        )
        if new_prompt != prompt:
            prompt = new_prompt

    sys.stdout.write(prompt)


if __name__ == "__main__":
    main()
