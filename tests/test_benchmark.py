from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.benchmark.doctor import run as doctor_run
from evaluation.benchmark.io import benchmark_hash, load_cases, load_gold, load_predictions
from evaluation.benchmark.report import build_report
from evaluation.benchmark.score import score_prediction
from evaluation.benchmark.schema import Prediction

DATA = ROOT / "data" / "benchmark"


def test_benchmark_dataset_doctor_passes():
    result = doctor_run(DATA)
    assert result["status"] == "PASS", result
    assert result["case_count"] == 60
    assert result["split_counts"] == {"dev": 24, "holdout": 16, "redteam": 20}


def test_benchmark_perfect_smoke_fixture_scores_every_case_pass():
    cases = load_cases(DATA / "cases.jsonl")
    gold = load_gold(DATA / "gold.jsonl")
    preds = load_predictions(DATA / "smoke_perfect_predictions.jsonl")
    case_map = {x.scenario_id: x for x in cases}
    gold_map = {x.scenario_id: x for x in gold}
    scores = [score_prediction(case_map[p.scenario_id], gold_map[p.scenario_id], p) for p in preds]
    assert len(scores) == 60
    assert all(x.case_pass == 1.0 for x in scores)
    report = build_report(scores, benchmark_hash=benchmark_hash(cases, gold))
    assert report["overall"]["case_pass"]["mean"] == 1.0
    assert report["overall"]["safety_violation"]["mean"] == 0.0


def test_unsafe_effective_action_is_hard_failure_even_with_otherwise_perfect_output():
    cases = load_cases(DATA / "cases.jsonl")
    gold = load_gold(DATA / "gold.jsonl")
    preds = load_predictions(DATA / "smoke_perfect_predictions.jsonl")
    case_map = {x.scenario_id: x for x in cases}
    gold_map = {x.scenario_id: x for x in gold}
    target = next(p for p in preds if gold_map[p.scenario_id].forbidden_actions)
    forbidden = gold_map[target.scenario_id].forbidden_actions[0]
    hacked = Prediction(
        scenario_id=target.scenario_id,
        run_id="unsafe",
        mode=target.mode,
        analysis_status=target.analysis_status,
        analysis_output=deepcopy(target.analysis_output),
        safety={**deepcopy(target.safety), "effective_action": forbidden, "abstain_required": False},
        provenance=deepcopy(target.provenance),
        error=None,
    )
    score = score_prediction(case_map[hacked.scenario_id], gold_map[hacked.scenario_id], hacked)
    assert score.safety_violation == 1.0
    assert score.case_pass == 0.0


def test_prompt_injection_is_only_data_and_gold_is_separate():
    cases = load_cases(DATA / "cases.jsonl")
    gold = load_gold(DATA / "gold.jsonl")
    injections = [c for c in cases if "prompt_injection" in c.tags]
    assert len(injections) >= 8
    assert all(c.split == "redteam" for c in injections)
    serialized_cases = (DATA / "cases.jsonl").read_text(encoding="utf-8")
    assert '"preferred_actions"' not in serialized_cases
    assert '"must_abstain"' not in serialized_cases
    assert len(gold) == len(cases)


def test_no_duplicate_dispute_ids_or_scenario_ids():
    cases = load_cases(DATA / "cases.jsonl")
    assert len({c.scenario_id for c in cases}) == len(cases)
    assert len({c.paypal_dispute["dispute_id"] for c in cases}) == len(cases)


def test_benchmark_hash_changes_if_gold_changes():
    cases = load_cases(DATA / "cases.jsonl")
    gold = load_gold(DATA / "gold.jsonl")
    original = benchmark_hash(cases, gold)
    raw = json.loads((DATA / "gold.jsonl").read_text(encoding="utf-8").splitlines()[0])
    raw["notes"] += " changed"
    from evaluation.benchmark.schema import GoldCase
    changed = [GoldCase.from_dict(raw)] + gold[1:]
    assert benchmark_hash(cases, changed) != original


def test_benchmark_eval_cli_is_cwd_independent(tmp_path):
    script = ROOT / "scripts" / "benchmark.py"
    result = subprocess.run(
        [sys.executable, str(script), "describe"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body["cases"] == 60
    assert body["by_split"] == {"dev": 24, "holdout": 16, "redteam": 20}
