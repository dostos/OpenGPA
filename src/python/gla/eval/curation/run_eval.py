from __future__ import annotations
from dataclasses import dataclass
from gla.eval.metrics import EvalResult

@dataclass
class RunEvalResult:
    with_gla: EvalResult
    code_only: EvalResult
    scorer_ambiguous: bool = False

class RunEval:
    def __init__(self, harness, agent_fn):
        self._harness = harness
        self._agent_fn = agent_fn

    def run(self, scenario_id: str) -> RunEvalResult:
        with_gla = self._harness.run_scenario(scenario_id, "with_gla", self._agent_fn)
        code_only = self._harness.run_scenario(scenario_id, "code_only", self._agent_fn)
        # If both diagnoses are empty / both wrong AND both tokens are very small,
        # the scorer probably cannot interpret them. Flag as ambiguous.
        ambiguous = (
            not with_gla.correct_diagnosis and not code_only.correct_diagnosis and
            with_gla.total_tokens < 100 and code_only.total_tokens < 100
        )
        return RunEvalResult(with_gla=with_gla, code_only=code_only,
                             scorer_ambiguous=ambiguous)
