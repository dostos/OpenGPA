from datetime import datetime, timezone
from gla.eval.curation.classify import classify_observed_helps, ObservedClassification
from gla.eval.metrics import EvalResult

def _mk(mode, correct, total_tokens):
    return EvalResult(scenario_id="r1", mode=mode, correct_diagnosis=correct,
                      correct_fix=correct, diagnosis_text="",
                      input_tokens=0, output_tokens=0, total_tokens=total_tokens,
                      tool_calls=0, num_turns=0, time_seconds=0.0,
                      model="x", timestamp=datetime.now(timezone.utc).isoformat())

def test_rule_1_gla_correct_code_wrong():
    r = classify_observed_helps(_mk("with_gla", True, 1000), _mk("code_only", False, 1000))
    assert r.verdict == "yes"

def test_rule_2_gla_wrong_code_correct():
    r = classify_observed_helps(_mk("with_gla", False, 1000), _mk("code_only", True, 1000))
    assert r.verdict == "no"

def test_rule_3_both_wrong():
    r = classify_observed_helps(_mk("with_gla", False, 1000), _mk("code_only", False, 1000))
    assert r.verdict == "no"

def test_rule_4_both_correct_low_ratio():
    # ratio 0.25 < 0.5 -> yes
    r = classify_observed_helps(_mk("with_gla", True, 1000), _mk("code_only", True, 4000))
    assert r.verdict == "yes"

def test_rule_5_both_correct_high_ratio():
    # ratio 0.9 > 0.8 -> no
    r = classify_observed_helps(_mk("with_gla", True, 3600), _mk("code_only", True, 4000))
    assert r.verdict == "no"

def test_rule_6_both_correct_mid_ratio_ambiguous():
    # ratio 0.65 in [0.5, 0.8] -> ambiguous
    r = classify_observed_helps(_mk("with_gla", True, 2600), _mk("code_only", True, 4000))
    assert r.verdict == "ambiguous"

def test_code_only_zero_tokens_degenerate():
    # Degenerate case: code_only has 0 tokens (shouldn't happen but guard)
    r = classify_observed_helps(_mk("with_gla", True, 1000), _mk("code_only", True, 0))
    assert r.verdict == "ambiguous"
