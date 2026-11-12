from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.benchmark.report import build_report
from evaluation.benchmark.score import CaseScore


def score(scenario: str, run: str, mode: str, value: float) -> CaseScore:
    return CaseScore(
        scenario_id=scenario, run_id=run, mode=mode, split="dev", category="x", difficulty="easy", completed=True,
        claim_precision=value, claim_recall=value, claim_f1=value,
        missing_precision=value, missing_recall=value, missing_f1=value,
        contradiction_precision=value, contradiction_recall=value, contradiction_f1=value,
        action_correct=value, abstention_correct=value,
        authoritative_source_integrity=1.0, human_quote_integrity=1.0,
        safety_violation=0.0, case_pass=value,
        recommended_action="SEND_MESSAGE", effective_action="SEND_MESSAGE", safety_status="PASS", model_name="model-x", prompt_version="p1", error=None,
    )


def test_repeats_are_macro_averaged_by_scenario_not_counted_as_independent_cases():
    rows = [score("A", f"r{i}", "m", 1.0) for i in range(20)] + [score("B", "r0", "m", 0.0)]
    report = build_report(rows, benchmark_hash="x")
    assert report["overall"]["scenarios"] == 2
    assert report["overall"]["prediction_rows"] == 21
    assert report["overall"]["case_pass"]["mean"] == 0.5


def test_paired_comparison_uses_shared_scenarios():
    rows = [
        score("A", "1", "casegraph_live", 1.0), score("B", "1", "casegraph_live", 1.0),
        score("A", "1", "raw_llm", 0.0), score("B", "1", "raw_llm", 0.5),
    ]
    report = build_report(rows, benchmark_hash="x")
    comp = report["paired_comparisons"][0]
    assert comp["paired_scenarios"] == 2
    assert comp["metrics"]["case_pass"]["mean_difference_a_minus_b"] == 0.75
