# Eval Scoring Design — replacing the legacy keyword scorer

## TL;DR

Legacy `DiagnosisScorer` is uncalibrated for advisor-style mined
scenarios. `score_maintainer_patch` is the right primitive but is
gated on `bug_class=="framework-internal"` + JSON tail — neither
holds for round-12. Stack three scorers: (1) file-level, gated only
on `fix.files`; (2) prose path/symbol extractor for non-JSON output;
(3) LLM judge on the ambiguous residual. Veto with a gave-up
detector. Surface a per-scenario `ScoreVerdict` with explicit
`needs_review` for low-confidence rows. ~1 day, ~600 LoC w/ tests.

---

## 1. What the existing scorers can and cannot detect

| signal                | legacy `DiagnosisScorer` | `score_maintainer_patch` | regex hack (round 12b) |
|-----------------------|--------------------------|--------------------------|------------------------|
| input format          | free prose               | JSON `proposed_patches` tail | free prose          |
| compares against      | `ground_truth_diagnosis` / `ground_truth_fix` keyword bag | `fix.files` set | `fix.files` set    |
| precision floor       | none — keyword overlap rewards lexical coincidence | high — exact path match | medium — basenames + symbols can collide |
| recall ceiling        | dependent on GT prose quality (often empty/templatey for mined scenarios) | exact — gt files are the upper bound | exact, same as above |
| handles "gave up"     | no — short bail-out text can still keyword-match | no — empty `proposed_patches` → solved=False, but verdict surface is the same | no            |
| applies to round-12 14? | yes (used) | no — guarded on `framework-internal` and JSON tail | yes (post-hoc only) |

**Concrete failures from round 12 / 12b:**

- *Cesium camera_jumps, code_only:* legacy marked ✓ because prose
  echoes user-report keywords (`pickPosition`, `ScreenSpaceCameraController`);
  agent never found the actual cache-invalidation bug. with_bhdr
  found it (`Picking.update` never called) and cited `Scene.js` +
  `Picking.js` — both in gt — yet legacy marked ✗.
- *Maplibre 3d_terrain, with_bhdr:* sharp, code-grounded diagnosis
  (`getStencilConfigForOverlapAndUpdateStencilID`, exact conditional
  on `painter.renderPass`). gt is 3 files; with_bhdr cited 1, code_only
  cited 2. Recall 0.33 vs 0.67, but the cited file is the actual
  bug-cause; the other two are collateral. File-overlap alone can't
  resolve this — we need a "needs review" outcome.
- *2 round-12 gave-ups* (cesium / deck.gl code_only): "no upstream
  snapshot accessible" boilerplate. Both passed through `DiagnosisScorer`;
  cesium scored ✓ on lexical accident.

---

## 2. Recommended scoring stack

Run these in priority order on every `EvalResult`. First non-`None`
verdict wins, with the gave-up detector vetoing any "solved=True".

### 2a. File-level scoring, loosened trigger

`harness.py:111` currently:

```python
if bug_class == "framework-internal" and scenario.fix is not None:
```

Replace with:

```python
# Fire whenever fix.files is populated, regardless of bug_class.
# Round-12 consumer-misuse / user-config scenarios still patch
# real framework code, so the file-level signal is meaningful
# even when the prompt format is advisor-style.
if scenario.fix is not None and scenario.fix.files:
```

`score_maintainer_patch` already returns `solved=False` when the
JSON tail is missing — fine for prose-only outputs; the router
falls through to 2b. Suppress the `file_score=0.0` write on missing
JSON so the surface stays `None` (don't pollute distributions).

### 2b. Free-form prose path-extractor (new module)

When 2a doesn't return solved (no JSON tail / no hits), extract
candidate identifiers from `diagnosis_text` and intersect with gt.
Pseudo-code:

```python
# gpa.eval.scorer_prose
PATH_RE   = re.compile(r"[`'\"]?([\w./-]+\.(?:c|cc|cpp|h|hpp|ts|tsx|js|jsx|mjs|cjs|glsl|vert|frag|gd|gdshader|py))[`'\"]?")
SYMBOL_RE = re.compile(r"`([A-Za-z_][\w.]{2,})`")        # backticked identifiers
CAMEL_RE  = re.compile(r"\b([A-Z][a-zA-Z0-9]+(?:[A-Z][a-zA-Z0-9]+){1,})\b")  # CamelCase outside backticks
SNAKE_RE  = re.compile(r"\b([a-z][a-z0-9]+(?:_[a-z0-9]+){1,})\b")            # snake_case >= 2 segments

def score_prose(diagnosis_text, gt_files):
    # 1. Mined paths: anything that looks like a relative path with a known extension.
    paths = {normalise(m) for m in PATH_RE.findall(diagnosis_text)}
    # 2. Mined basenames: bare basenames the agent cites without a directory prefix.
    basenames = {p.split("/")[-1] for p in paths} | extract_bare_basenames(diagnosis_text)
    # 3. Mined symbols: backticked identifiers (camelCase / snake_case / dotted).
    symbols = set(SYMBOL_RE.findall(diagnosis_text))

    # Hits: any gt file whose path OR basename appears in the mined sets.
    gt_basenames = {f.split("/")[-1]: f for f in gt_files}
    file_hits = set()
    for f in gt_files:
        if f in paths: file_hits.add(f)
        elif f.split("/")[-1] in basenames: file_hits.add(f)
        # Symbol-derived hits only when the symbol is sufficiently
        # specific — e.g. drop "update", "render", "draw". See
        # FP guards below.

    return ProseScore(
        file_hits=file_hits,
        precision=len(file_hits) / max(len(paths | basenames), 1),
        recall=len(file_hits) / len(gt_files),
        symbols=symbols,
    )
```

**FP guards:**

- Basename stoplist (`index.ts`, `main.c`, `utils.js`, `types.ts`,
  `helper.h`, etc.) — too common to count.
- Symbols must be ≥2 path segments (`foo.bar`), CamelCase with ≥2
  capital words, or snake_case with ≥3 segments. Drop bare
  `update` / `render` / `draw` — collide everywhere.
- Strip the agent's verbatim quote of the user report (anything
  inside the prompt's `## User Report` blob) from `diagnosis_text`
  before extraction. Quoted matches are not the agent's identification.
- Out-of-tree paths (reuse `_is_out_of_tree`) go to `out_of_tree`,
  not `extras`.

**Solve threshold:** recall ≥ 0.5 *and* precision ≥ 0.25. The
recall-1.0 / precision-0.05 ("listed every file") case shouldn't pass.

### 2c. LLM-judge as third leg

**When.** 2a and 2b both `solved=False` AND `any_hit ≥ 1`. That's
"named at least one right file but missed recall threshold" — the
band most likely to be sharper-than-they-look (maplibre 3d_terrain;
godot scenarios where gt is 13–22 files of collateral). Skip on
clear successes, zero-hit failures, and gave-up runs. On
round-12+12b that's ~5–8 of 28 runs.

**Plumbing.** Reuse `gpa.eval.judge.run_semantic_judge` (already
emits `{full, partial, none}`) with `ClaudeCodeLLMClient` from
`gpa.eval.curation.llm_client` — no API key, subprocess. Missing
piece is `fetch_pr_diff_summary(fix, snapshot_root)` that runs
`git show --stat <fix_sha>` against the already-cloned snapshot
and truncates to ~6 KB of diff + commit message.

**Cost bound.** ≤ 8 calls per 14-scenario round, ~5 KB context each,
≤ 1 minute wall. Disk cache keyed `(scenario_id, fix_sha,
sha256(diagnosis_text))`. Default off, opt-in via `--llm-judge` on
the report CLI (mirrors `--evaluate` in mining).

**Model.** Default claude-cli model. Judge prompt is terse;
flips wash out across 14 scenarios. Don't pull in a separate tier.

### 2d. Gave-up detector (veto)

Pre-scoring filter. If any pattern matches the last 600 chars of
`diagnosis_text` (case-insensitive), force `solved=False` regardless
of 2a/2b hits:

```python
GAVE_UP_PATTERNS = [
    r"no upstream snapshot accessible",
    r"cannot investigate without (the )?source",
    r"upstream snapshot is not (accessible|available)",
    r"unable to (read|access) (the )?upstream (repo|source)",
    r"no access to the (framework|source) code",
    r"\bI (cannot|can't) (provide|give) a (specific|concrete) (diagnosis|fix)\b",
    r"\bwithout access to the (codebase|source|repo)\b.*\bcannot\b",
    r"\bthis is (a )?(speculative|guess)\b",
]
```

Set `gave_up=True` on the result. The 2/14 round-12 give-ups
(cesium / deck.gl code_only) match the first two patterns. Cesium
currently scores ✓ legacy; this veto flips it to ✗ correctly.

---

## 3. What to actually report

Per-scenario row schema in `EvalResult`:

```python
@dataclass
class ScoreVerdict:
    scorer: Literal["file_level", "prose", "judge", "gave_up", "no_signal"]
    solved: bool                 # the binding verdict
    confidence: Literal["high", "medium", "low"]
    file_score: Optional[float]  # 2a if available
    prose_recall: Optional[float]   # 2b
    prose_precision: Optional[float]
    judge_verdict: Optional[Literal["full", "partial", "none"]]  # 2c
    gave_up: bool
    needs_review: bool           # see precedence
    reasoning: str
```

**Precedence (top wins):**

1. `gave_up=True` → `scorer=gave_up`, `solved=False`, `confidence=high`.
2. file_level returns `solved=True` → `scorer=file_level`, `solved=True`, `confidence=high`.
3. prose returns `solved=True` (recall ≥ 0.5 and precision ≥ 0.25)
   → `scorer=prose`, `solved=True`, `confidence=medium`.
4. judge returns `full` → `scorer=judge`, `solved=True`, `confidence=medium`.
5. judge returns `partial` *and* prose `any_hit` → `solved=False`,
   `needs_review=True`, `confidence=low`.
6. zero file/prose hits and no judge run → `scorer=no_signal`,
   `solved=False`, `confidence=high` (clear miss).
7. anything else (e.g. low any_hit, prose precision high but recall
   below 0.5, no give-up) → `solved=False`, `needs_review=True`,
   `confidence=low`.

Headline = solved-rate over `confidence != low`. Always print
"needs review N/14" alongside it — don't paper over. Maplibre
3d_terrain lands in bucket 7 (precision 1.0, recall 0.33, no
give-up) and gets `needs_review=True` rather than a false ✗.

---

## 4. Backwards compatibility

- **Rounds 1–11** (no `fix.files`): the new predicate `scenario.fix
  is not None and scenario.fix.files` skips them; keyword scorer
  keeps running as today.
- **Round 12+:** all new paths fire. Keep legacy
  `correct_diagnosis` / `correct_fix` columns in `EvalResult`
  (additive change only) so old rounds re-render.
- **CLI flag:** `--score-version=v2`, default `v1` for one round
  for side-by-side, then flip after round 13.
- **No re-running needed** — `diagnosis_text` is preserved per result;
  re-score round-12 / 12b from disk.

---

## 5. Scope of work

One day, ~600 LoC including tests.

| file | change |
|------|--------|
| `src/python/bhdr/eval/harness.py` | loosen trigger predicate (~3 lines); call new `score_run()` orchestrator that returns `ScoreVerdict`; populate `result.verdict` field. |
| `src/python/bhdr/eval/scorer.py` | add `score_run(result, scenario, *, llm_client=None) -> ScoreVerdict` orchestrator; existing `score_maintainer_patch` unchanged. |
| `src/python/bhdr/eval/scorer_prose.py` (new) | path/symbol/basename extractor + `score_prose()`; ~150 lines. |
| `src/python/bhdr/eval/scorer_giveup.py` (new) | regex pattern bank + `is_gave_up()` ~30 lines. |
| `src/python/bhdr/eval/judge.py` | add `fetch_pr_diff_summary(fix, snapshot_root)` helper that runs `git show --stat --shortstat <fix_sha>` and truncates; ~40 lines. |
| `src/python/bhdr/eval/metrics.py` | add `ScoreVerdict` dataclass; add to `EvalResult` (optional field, backwards-compatible). |
| `src/python/bhdr/eval/cli.py` | add `--llm-judge`, `--score-version` flags; rewire `report` command to print `ScoreVerdict.scorer` column + `needs_review` count. |
| `tests/unit/python/test_scorer_prose.py` (new) | path/symbol extractor unit tests, FP-guard tests, stoplist tests. |
| `tests/unit/python/test_scorer_giveup.py` (new) | each give-up pattern as a parametrized case; non-give-up controls. |
| `tests/unit/python/test_score_run.py` (new) | precedence tests — gave-up vetoes; file_level beats prose; judge fires only when expected. |
| `tests/unit/python/test_harness_score_v2.py` (new) | end-to-end: feed a known result, verify `ScoreVerdict` populated correctly. |

**Out of scope:** agent prompt; the `DiagnosisScorer` keyword path
(leave running, stop using for headline); `correct_diagnosis` /
`correct_fix` columns (kept for backcompat).

**Validation:** re-score 28 round-12+12b results from `/data3/...`
without the judge, eyeball distribution, then enable `--llm-judge`
on the `needs_review` band; expect agreement ≥ 5/8 vs manual
inspection. Acceptance: cesium camera_jumps with_bhdr = ✓,
code_only = ✗ (gave-up); maplibre 3d_terrain with_bhdr =
`needs_review`, not ✗.
