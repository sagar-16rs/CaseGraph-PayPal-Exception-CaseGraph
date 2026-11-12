from __future__ import annotations

import random
from collections import defaultdict
from statistics import mean
from typing import Any

from .score import CaseScore

METRICS = (
    "claim_f1",
    "missing_f1",
    "contradiction_f1",
    "action_correct",
    "abstention_correct",
    "authoritative_source_integrity",
    "human_quote_integrity",
    "safety_violation",
    "case_pass",
)


def _bootstrap_ci(values: list[float], *, seed: int = 1007, samples: int = 2000) -> tuple[float, float]:
    if not values:
        return (float("nan"), float("nan"))
    if len(values) == 1:
        return (values[0], values[0])
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        sample = [values[rng.randrange(len(values))] for _ in range(len(values))]
        estimates.append(mean(sample))
    estimates.sort()
    low = estimates[int(0.025 * (len(estimates) - 1))]
    high = estimates[int(0.975 * (len(estimates) - 1))]
    return (low, high)


def _scenario_metric_values(scores: list[CaseScore], metric: str) -> list[float]:
    """Macro-average repeated runs within scenario before uncertainty estimation.

    Repeated stochastic calls for the same scenario are correlated and must not be
    treated as independent benchmark examples.
    """
    grouped: dict[str, list[float]] = defaultdict(list)
    for score in scores:
        grouped[score.scenario_id].append(float(getattr(score, metric)))
    return [mean(values) for _, values in sorted(grouped.items())]


def _summarize_group(scores: list[CaseScore]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "prediction_rows": len(scores),
        "scenarios": len({x.scenario_id for x in scores}),
    }
    for metric in METRICS:
        values = _scenario_metric_values(scores, metric)
        avg = mean(values) if values else float("nan")
        low, high = _bootstrap_ci(values)
        out[metric] = {"mean": avg, "ci95": [low, high]}
    completed = _scenario_metric_values(
        [CaseScore(**{**x.to_dict(), "case_pass": 1.0 if x.completed else 0.0}) for x in scores],
        "case_pass",
    ) if scores else []
    out["completed_rate"] = mean(completed) if completed else float("nan")
    return out


def _paired_comparison(a: list[CaseScore], b: list[CaseScore], *, a_name: str, b_name: str) -> dict[str, Any]:
    by_a: dict[str, list[CaseScore]] = defaultdict(list)
    by_b: dict[str, list[CaseScore]] = defaultdict(list)
    for x in a: by_a[x.scenario_id].append(x)
    for x in b: by_b[x.scenario_id].append(x)
    shared = sorted(set(by_a) & set(by_b))
    result: dict[str, Any] = {"a": a_name, "b": b_name, "paired_scenarios": len(shared), "metrics": {}}
    for metric in METRICS:
        diffs = []
        for scenario_id in shared:
            av = mean(float(getattr(x, metric)) for x in by_a[scenario_id])
            bv = mean(float(getattr(x, metric)) for x in by_b[scenario_id])
            diffs.append(av - bv)
        low, high = _bootstrap_ci(diffs, seed=2017)
        result["metrics"][metric] = {
            "mean_difference_a_minus_b": mean(diffs) if diffs else float("nan"),
            "ci95": [low, high],
        }
    return result


def build_report(scores: list[CaseScore], *, benchmark_hash: str) -> dict[str, Any]:
    by_split: dict[str, list[CaseScore]] = defaultdict(list)
    by_category: dict[str, list[CaseScore]] = defaultdict(list)
    by_mode: dict[str, list[CaseScore]] = defaultdict(list)
    for score in scores:
        by_split[score.split].append(score)
        by_category[score.category].append(score)
        by_mode[score.mode].append(score)

    failures = [
        {
            "scenario_id": x.scenario_id,
            "run_id": x.run_id,
            "mode": x.mode,
            "split": x.split,
            "category": x.category,
            "recommended_action": x.recommended_action,
            "effective_action": x.effective_action,
            "safety_status": x.safety_status,
            "safety_violation": x.safety_violation,
            "error": x.error,
        }
        for x in scores
        if x.case_pass < 1.0
    ]

    modes = sorted(by_mode)
    comparisons = []
    if "casegraph_live" in by_mode and "raw_llm" in by_mode:
        comparisons.append(_paired_comparison(
            by_mode["casegraph_live"], by_mode["raw_llm"], a_name="casegraph_live", b_name="raw_llm"
        ))

    warnings: list[str] = []
    if any(x.mode == "smoke_fixture" for x in scores):
        warnings.append("smoke_fixture is scorer validation only and must never be reported as model performance")
    if "casegraph_live" in by_mode and "raw_llm" in by_mode:
        cg_models = {x.model_name for x in by_mode["casegraph_live"] if x.model_name != "unknown"}
        raw_models = {x.model_name for x in by_mode["raw_llm"] if x.model_name != "unknown"}
        if cg_models and raw_models and cg_models != raw_models:
            warnings.append(
                f"baseline fairness warning: CaseGraph models {sorted(cg_models)} differ from raw baseline models {sorted(raw_models)}"
            )

    return {
        "benchmark_hash": benchmark_hash,
        "overall": _summarize_group(scores),
        "by_split": {k: _summarize_group(v) for k, v in sorted(by_split.items())},
        "by_category": {k: _summarize_group(v) for k, v in sorted(by_category.items())},
        "by_mode": {k: _summarize_group(v) for k, v in sorted(by_mode.items())},
        "paired_comparisons": comparisons,
        "warnings": warnings,
        "failure_count": len(failures),
        "failures": failures,
    }
