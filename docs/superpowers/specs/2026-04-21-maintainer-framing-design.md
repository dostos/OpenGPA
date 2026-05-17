# Maintainer-framing Eval — R10+ Scenario & Mining Redesign

**Date:** 2026-04-21
**Status:** design; not yet implemented
**Supersedes portions of:** `2026-04-17-eval-set-real-world-design.md` (scenario schema), `2026-04-18-framework-integration-design.md` (agent task framing for framework-consumer scenarios)

## Why this spec exists

R5–R9 evaluated agents in an artificial hybrid framing: the agent saw (a) the user's issue body, (b) a distilled minimal C repro that does NOT resemble what the user or the maintainer actually runs, (c) a hand-picked subtree of "relevant files" from the framework source, and was asked to produce a narrative diagnosis scored via keyword overlap.

That framing distorts findings in two directions:
- **State-collision wins are real** (the captured GL state literally contains the bug signature); these would survive any reasonable reframing.
- **Framework-consumer results are noise.** The agent was rewarded for pattern recognition on the user's issue body, not for identifying the actual fix location. R9's +$0.39/pair carryover regression and R9's "6/8 source-logical solved without trace" both need to be re-measured under a cleaner framing before we trust them.

**Correct framing:** the agent plays the framework maintainer. Input = the verbatim issue. Output = a concrete fix proposal keyed to the framework's source tree. Ground truth = the actual merged fix PR's diff.

This is the realistic task. The user files an issue; the maintainer diagnoses and patches. GPA is a tool the maintainer might use during reproduction — not a substitute for reading source.

## Goals

- **Score against the real fix.** File-overlap with the merged PR + semantic-match of the change description. Keyword overlap demoted to sanity check.
- **Bug-class segmentation at mining time.** Distinguish framework-internal, consumer-misuse, and user-config bugs; scoring + prompt differ per class.
- **Realistic tool surface.** Full repo access via `Read`/`Grep`/`Glob` on the pre-fix-SHA snapshot, not a hand-picked subtree.
- **Deterministic repro.** Every scenario must reproduce the bug under `gpa run --` (native C repro) or `gpa run-browser --` (browser pilot) before entering the eval set.
- **Retrofit-friendly.** Most existing scenarios should survive (with added `## Fix` metadata); a subset without clear fix PRs drops out.

## Non-goals

- Changing the underlying scoring rubric for synthetic (`e*`) scenarios — those have no upstream fix PR and will continue to use the legacy narrative scorer.
- Changing browser-eval Phase 1 infrastructure — `gpa run-browser` stays as-is; only the scenario schema changes.
- Restricting to "patches ≤ 5 lines" or other arbitrary fix-size cutoffs. Mining will prefer localized fixes but scoring handles multi-file fixes correctly.

## Scenario schema changes

### New required section: `## Fix`

Machine-readable YAML block plus prose:

```markdown
## Fix

```yaml
fix_pr_url: https://github.com/mrdoob/three.js/pull/27456
fix_sha: a1b2c3d4e5f6                    # merge commit SHA
fix_parent_sha: 1234abcd5678               # parent of merge (= upstream_snapshot.sha)
bug_class: framework-internal              # framework-internal | consumer-misuse | user-config
files:
  - src/renderers/webgl/WebGLBackground.js
  - src/renderers/webgl/WebGLRenderer.js   # optional, for multi-file fixes
change_summary: >
  WebGLBackground.render() called before autoClear, causing sky to paint
  over user geometry instead of behind it. Move the background draw to
  after the main clear.
  ```

Optional: `diff_excerpt` with the key 3-5 lines of the patch, for scorer debugging.
```

**Scoring uses this section:**
- `files` is the authoritative file-overlap ground truth.
- `change_summary` feeds the LLM-judged semantic-match scorer.
- `bug_class` picks the scoring rubric (see below).

### Deprecated sections (still allowed, ignored by scorer)

- `## Ground Truth` — stays for human-readable context; scoring doesn't touch it.
- `## Bug Signature` — still used by `capture_validate` (does the repro actually produce the symptom?), but not by diagnosis scoring.
- `## Upstream Snapshot.relevant_files` — becomes a **hint** list, not a restriction. The agent has access to the full repo.

### Section ordering

```
# TITLE
## User Report                    ← verbatim issue body
## Expected Correct Output
## Actual Broken Output
## Fix                            ← NEW, required for R10+
## Bug Class
## Difficulty Rating
## Adversarial Principles
## How OpenGPA Helps
## Source
## Tier / API / Framework
## Bug Signature
## Upstream Snapshot
```

## Bug-class segmentation

Three classes with different task shapes:

| Class | Agent output format | Scored against |
|---|---|---|
| `framework-internal` | `{proposed_patches: [{file, change_summary}]}` | File-overlap + semantic match against fix PR |
| `consumer-misuse` | `{user_code_change: {api, correct_usage}}` | Natural-language match against the maintainer's "you should use X instead" response |
| `user-config` | `{setting_change: {key, value, context}}` | Exact match of config key + semantic match of value |

In practice most mined issues are `framework-internal` (the maintainer patches the framework). `consumer-misuse` fires when the maintainer's response is "that's not a bug, use `renderer.setAnimationLoop()` instead of `requestAnimationFrame`." `user-config` fires on "set `renderer.physicallyCorrectLights = true`."

Classification happens at triage time via a triage-prompt update.

## Mining process changes

### Stage 1: discovery (existing `discover.py`)

No change. Same GitHub issue / Stack Overflow queries.

### Stage 2: fix-PR resolution (NEW)

For each `is:issue is:closed reason:completed` candidate, resolve the linked fix PR:

1. `gh api repos/{owner}/{repo}/issues/{number}/timeline` → look for `CrossReferencedEvent` with source being a merged PR in the same repo, OR a commit on the default branch referencing `Fixes #N` / `Closes #N`.
2. If multiple candidate PRs: pick the most recent merged one that touched rendering-related paths.
3. If none found: mark the candidate `no_fix_pr`; skip.
4. If PR found: fetch its diff via `gh api repos/{owner}/{repo}/pulls/{num}/files`; extract file list + total changed-line count.

Budget filter: reject if fix diff > 50 total changed lines OR > 10 files. Anything larger is a refactor-bundled-with-fix and the diff won't cleanly score.

### Stage 3: triage (existing `triage.py`)

Extended prompt output schema:

```json
{
  "triage_verdict": "in_scope | out_of_scope | ambiguous",
  "bug_class": "framework-internal | consumer-misuse | user-config",
  "root_cause_fingerprint": "...",
  "rejection_reason": null | "...",
  "summary": "...",
  "fix_localized": true | false   // NEW: is the fix touching a single logical unit?
}
```

### Stage 4: draft (existing `draft.py`)

Emits scenario.md with the new `## Fix` section populated from the resolved fix PR:
- `fix_pr_url` / `fix_sha` / `fix_parent_sha` → from GitHub API
- `bug_class` → from triage output
- `files` → from fix PR diff
- `change_summary` → LLM-extracted from PR body + diff

### Stage 5: validate (existing `validate.py`)

Extended contamination check:
- `## Fix` section must be present and parse as valid YAML
- `files` list must be non-empty
- Each `files` entry must exist in the upstream snapshot at `fix_parent_sha`

Capture validator (the existing one) unchanged.

## Harness changes

### Agent role in the system prompt

Current R9-era prompt:
> You are diagnosing a real-world graphics rendering bug. Your goal is to identify the root cause.

New R10+ prompt:
> You are a maintainer of this framework. A user has filed the issue below. You have full read access to the repository at the pre-fix commit. Reproduce, diagnose, and propose a concrete fix.

### Tool surface

Keep existing GPA tools (`gpa report`, `gpa check`, `gpa trace`, `gpa dump`). Change the "read upstream" tools:

- `read_upstream(path)` → `Read(snapshot_root + "/" + path)` on any file in the full repo (not just the hint list)
- `list_upstream_files(subdir)` → recursive walk of any subdir
- `grep_upstream(pattern, glob)` → ripgrep over the full repo
- NEW: `build_repro()` / `run_repro()` for scenarios where the agent wants to re-run with a tentative patch applied (future work, not R10 MVP)

### Output schema (JSON tail required)

Agent must end with a JSON object keyed on `bug_class`:

```json
{
  "bug_class": "framework-internal",
  "proposed_patches": [
    {"file": "src/renderers/webgl/WebGLBackground.js",
     "change_summary": "Move autoClear call before background render."}
  ],
  "confidence": "high",
  "reasoning": "..."
}
```

Different schemas per class; enforced at score time.

## Scoring rubric

Two-stage scorer:

### Stage 1: file-overlap (cheap, deterministic)

For `framework-internal`:
```
score_file = |proposed_files ∩ ground_truth_files| / |ground_truth_files|
```

Perfect match → 1.0; missing half → 0.5; wrong file → 0.0. Partial credit matters: a 2-file fix where agent got 1 is 0.5, scored as a partial solve.

### Stage 2: semantic-match (LLM-judged, sampled)

For pairs where `score_file >= 0.5` (file is at least plausibly right), a judge LLM compares:
- `proposed_changes[i].change_summary` vs `ground_truth.change_summary`
- Asks: "does this proposed change address the same root cause and produce the same behavioral effect?"
- Returns `semantic_match: full | partial | none`

### Final verdict

- `solved`: `score_file >= 0.5 AND semantic_match in {full, partial}`
- `wrong`: `score_file < 0.5 OR semantic_match == none`
- `timeout`: agent hit max-turns with no parseable JSON tail
- `infra`: capture/build/engine failure

(Consumer-misuse and user-config classes use a simpler match-against-gold-response scheme.)

## Retrofit plan for existing scenarios

Of the 130+ currently-mined scenarios:
- ~40 have a clear `upstream_snapshot` already pointing at the pre-fix parent SHA. For these, `gh api repos/.../pulls/{N}/files` can auto-populate `## Fix`.
- ~50 have issue URLs but no resolved fix PR. A batch agent can resolve via `gh api timeline`, flag the ones without fix PRs for exclusion.
- ~40 don't have upstream snapshot refs (Stack Overflow, synthetic). These stay on the legacy scorer.

Retrofit runs as one parallel batch: each scenario dir gets a `## Fix` section appended, scenarios without resolvable fix PRs get excluded from the R10 eligible set (but stay in the repo).

## Implementation phases

### Phase 1 — schema + drafter + validator (2 days)

Files:
- `src/python/bhdr/eval/scenario.py` — extend parser to read `## Fix` YAML
- `src/python/bhdr/eval/curation/prompts/draft_core_system.md` — add `## Fix` to output template; update drafter to emit it
- `src/python/bhdr/eval/curation/validate.py` — extend `check_contamination` to require `## Fix` section with non-empty `files`
- Tests: `test_scenario_fix_section_parse`, `test_drafter_emits_fix_section`, `test_validator_requires_fix_section`

Deliverable: new scenarios drafted from here on carry `## Fix`; existing ones still parse but are flagged `legacy_scorer`.

### Phase 2 — retrofit (1 day, mostly dispatch + wait)

Parallel agent batches process existing scenarios:
- Resolve issue → fix PR via `gh api`
- Parse diff → `files[]` + `change_summary`
- Append `## Fix` section to scenario.md
- Scenarios without resolvable fix PRs get marked with `bug_class: legacy` (excluded from R10)

Deliverable: retrofit report + updated scenarios.

### Phase 3 — scorer (2 days)

Files:
- `src/python/bhdr/eval/scorer.py` (NEW) — replaces keyword scorer for `## Fix`-carrying scenarios
- `src/python/bhdr/eval/judge.py` (NEW) — LLM-judge for semantic-match stage
- `src/python/bhdr/eval/telemetry.py` — extend `classify_verdict` to use new scorer output
- Tests: `test_scorer_file_overlap`, `test_judge_semantic_match`, `test_classify_verdict_with_fix_scoring`

Deliverable: scorer produces file-overlap + semantic-match + verdict; round runners switch to it.

### Phase 4 — harness + prompt (1 day)

Files:
- `docs/superpowers/eval/round10/run_subagent.sh` (new template) — agent-role prompt change
- `src/python/bhdr/eval/harness.py` — full-repo tool surface (not just relevant_files)
- `scripts/round_runner_template.sh` — updated for new scoring output

Deliverable: R10 runner ready.

### Phase 5 — R10 eval (one evening)

Select 15–20 scenarios from the R10 eligible pool (post-retrofit), run full matrix (haiku + sonnet + opus × 2 modes), measure:
- Does state-collision still win? (Expected: yes, with sharper numbers)
- Does framework-consumer still regress? (Expected: yes, and the regression will be quantitatively larger under file-level scoring because the agent must actually identify the right framework file)
- Does `gpa trace` get used now that the task is "find a specific source location"? (Hypothesis: yes, because literal values → file locations is exactly trace's job)
- Does Opus's reliability advantage hold? (Expected: yes, possibly widens)

Compare R10 numbers to R9 for each subset. Write up findings.

## Open questions

1. **How to handle fix PRs with test-only changes?** Some PRs only add a regression test after a prior commit did the real fix. The "fix" is the prior commit, but the PR merges the test. Need to detect this (diff touches only `test/` / `tests/`) and walk back to the actual fix commit.
2. **How to score consumer-misuse "fixes" that are natural-language advice, not a diff?** Maintainer replies "just call `renderer.clear()` between frames" without a patch. These are real bugs but the scoring rubric can't use file-overlap. LLM-judge compares the user-code-change proposal against the maintainer's reply text.
3. **How to handle cross-repo fixes?** Mapbox issue in `mapbox-gl-js` is sometimes fixed in the related `maplibre-gl` fork, or vice-versa. Out of scope for R10; flag as `cross_repo_fix` and exclude.
4. **Should legacy scenarios also be re-scored under the new rubric?** R5–R9 results are under the old scorer. Retroactively re-running them would cost another $100+. Proposal: don't re-run, but explicitly note in all future comparison tables that R10 numbers use a different (stricter) scorer.
5. **How strict to be on `files` match?** A fix PR often refactors + fixes in the same commit. If the agent identifies the core-fix file but misses a refactor-cleanup file, should that count as full or partial? Proposal: partial (score_file = 0.5+), LLM-judge decides from there.

## Success criteria for R10

- ≥ 80 % of existing scenarios retrofit cleanly (have resolvable fix PRs)
- R10 eval completes in < 2 hours at < $100
- File-overlap scoring gives non-trivial (0.5+) credit on ≥ 50 % of scenarios for at least one model × mode
- Subset numbers (state-collision vs consumer-misuse vs source-logical) are distinguishable at p < 0.1 on pairwise comparison
- At least one scenario where `gpa trace` demonstrably helped (invocation + correct file identification)

## What R10 does NOT change

- `gpa trace` itself — still the same CLI + REST + MCP surface. We're testing whether the reframed task exercises it.
- Existing `e*` (synthetic) scenarios — these have no upstream fix PR; keep legacy scorer.
- Browser eval pipeline — unchanged.
- Opus / Sonnet / Haiku tier comparison — unchanged.
