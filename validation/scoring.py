from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from typing import Any, Callable


def _safe_mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _safe_median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def score_response(response: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    diagnosis_correct = int(response.get("diagnosis_id") == gold["diagnosis_id"])
    action_correct = int(response.get("action_id") in set(gold["safe_action_ids"]))
    unsafe_action = int(response.get("action_id") in set(gold.get("unsafe_action_ids", [])))

    selected_sources = set(response.get("selected_sources", []))
    required_sources = set(gold.get("required_source_ids", []))
    relevant_sources = set(gold.get("relevant_source_ids", gold.get("required_source_ids", [])))
    source_recall = 1.0 if not required_sources else len(selected_sources & required_sources) / len(required_sources)
    source_precision = 1.0 if not selected_sources else len(selected_sources & relevant_sources) / len(selected_sources)

    selected_contradictions = set(response.get("selected_contradictions", []))
    required_contradictions = set(gold.get("required_contradiction_ids", []))
    contradiction_recall = (
        1.0
        if not required_contradictions
        else len(selected_contradictions & required_contradictions) / len(required_contradictions)
    )
    contradiction_false_positive_count = len(selected_contradictions - set(gold.get("valid_contradiction_ids", required_contradictions)))

    selected_verified = set(response.get("established_statement_ids", []))
    true_verified = set(gold.get("established_statement_ids", []))
    established_statement_recall = 1.0 if not true_verified else len(selected_verified & true_verified) / len(true_verified)
    false_established_statement_count = len(selected_verified - true_verified)

    strict_success = int(diagnosis_correct and action_correct and not unsafe_action)
    confidence = max(0.0, min(100.0, float(response.get("confidence", 0.0)))) / 100.0
    brier = (confidence - strict_success) ** 2
    overconfident_failure = int(strict_success == 0 and confidence >= 0.80)

    elapsed_seconds = float(response.get("elapsed_seconds", 0.0))
    suspicious_fast = int(elapsed_seconds < float(gold.get("minimum_plausible_seconds", 8.0)))

    return {
        **{k: response.get(k) for k in ("participant_id", "scenario_id", "pair_id", "variant", "condition", "block")},
        "diagnosis_correct": diagnosis_correct,
        "action_correct": action_correct,
        "unsafe_action": unsafe_action,
        "strict_success": strict_success,
        "source_recall": source_recall,
        "source_precision": source_precision,
        "contradiction_recall": contradiction_recall,
        "contradiction_false_positive_count": contradiction_false_positive_count,
        "established_statement_recall": established_statement_recall,
        "false_established_statement_count": false_established_statement_count,
        "confidence": confidence,
        "brier": brier,
        "overconfident_failure": overconfident_failure,
        "elapsed_seconds": elapsed_seconds,
        "suspicious_fast": suspicious_fast,
    }


def aggregate_by_participant(scored: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, float]]]:
    bucket: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in scored:
        bucket[(str(row["participant_id"]), str(row["condition"]))].append(row)
    out: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    metrics = [
        "diagnosis_correct",
        "action_correct",
        "unsafe_action",
        "strict_success",
        "source_recall",
        "source_precision",
        "contradiction_recall",
        "established_statement_recall",
        "false_established_statement_count",
        "brier",
        "overconfident_failure",
        "elapsed_seconds",
    ]
    for (pid, condition), rows in bucket.items():
        out[pid][condition] = {
            metric: float(statistics.fmean(float(r[metric]) for r in rows)) for metric in metrics
        }
        out[pid][condition]["task_count"] = float(len(rows))
    return dict(out)


def paired_differences(
    participant_agg: dict[str, dict[str, dict[str, float]]], metric: str, *, lower_is_better: bool = False
) -> list[float]:
    diffs: list[float] = []
    for pid in sorted(participant_agg):
        conditions = participant_agg[pid]
        if "baseline" not in conditions or "casegraph" not in conditions:
            continue
        raw = conditions["casegraph"][metric] - conditions["baseline"][metric]
        diffs.append(-raw if lower_is_better else raw)
    return diffs


def bootstrap_mean_ci(values: list[float], seed: int = 20261025, draws: int = 5000) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    if len(values) == 1:
        return values[0], values[0]
    rng = random.Random(seed)
    means: list[float] = []
    n = len(values)
    for _ in range(draws):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(statistics.fmean(sample))
    means.sort()
    low_idx = max(0, int(0.025 * draws) - 1)
    high_idx = min(draws - 1, int(0.975 * draws))
    return means[low_idx], means[high_idx]


def sign_flip_pvalue(values: list[float], seed: int = 20261025, draws: int = 10000) -> float | None:
    nonzero = [v for v in values if abs(v) > 1e-12]
    if not nonzero:
        return 1.0 if values else None
    observed = abs(statistics.fmean(nonzero))
    n = len(nonzero)
    if n <= 18:
        total = 1 << n
        extreme = 0
        for mask in range(total):
            mean = statistics.fmean(v if (mask >> i) & 1 else -v for i, v in enumerate(nonzero))
            if abs(mean) >= observed - 1e-12:
                extreme += 1
        return extreme / total
    rng = random.Random(seed)
    extreme = 0
    for _ in range(draws):
        mean = statistics.fmean(v if rng.random() < 0.5 else -v for v in nonzero)
        if abs(mean) >= observed - 1e-12:
            extreme += 1
    return (extreme + 1) / (draws + 1)


def metric_summary(
    participant_agg: dict[str, dict[str, dict[str, float]]],
    metric: str,
    *,
    lower_is_better: bool = False,
    seed: int = 20261025,
    expected_tasks_per_condition: int = 5,
) -> dict[str, Any]:
    baseline: list[float] = []
    casegraph: list[float] = []
    complete: dict[str, dict[str, dict[str, float]]] = {}
    for pid, conditions in participant_agg.items():
        if (
            "baseline" in conditions
            and "casegraph" in conditions
            and int(conditions["baseline"].get("task_count", 0)) == expected_tasks_per_condition
            and int(conditions["casegraph"].get("task_count", 0)) == expected_tasks_per_condition
        ):
            complete[pid] = conditions
            baseline.append(conditions["baseline"][metric])
            casegraph.append(conditions["casegraph"][metric])
    diffs = paired_differences(complete, metric, lower_is_better=lower_is_better)
    lo, hi = bootstrap_mean_ci(diffs, seed=seed)
    return {
        "n_complete_participants": len(diffs),
        "baseline_mean": _safe_mean(baseline),
        "casegraph_mean": _safe_mean(casegraph),
        "baseline_median": _safe_median(baseline),
        "casegraph_median": _safe_median(casegraph),
        "paired_improvement_mean": _safe_mean(diffs),
        "paired_improvement_median": _safe_median(diffs),
        "paired_improvement_ci95": [lo, hi],
        "paired_sign_flip_p_two_sided": sign_flip_pvalue(diffs, seed=seed),
        "direction": "lower_is_better" if lower_is_better else "higher_is_better",
    }


def classify_primary_gate(primary: dict[str, Any], unsafe: dict[str, Any], minimum_participants: int = 8) -> str:
    n = int(primary.get("n_complete_participants") or 0)
    if n < minimum_participants:
        return "INSUFFICIENT_SAMPLE"
    unsafe_improvement = unsafe.get("paired_improvement_mean")
    # unsafe is summarized with lower_is_better=True, so negative means CaseGraph had more unsafe actions.
    if unsafe_improvement is not None and unsafe_improvement < -0.02:
        return "SAFETY_REGRESSION"
    diff = primary.get("paired_improvement_mean")
    ci = primary.get("paired_improvement_ci95") or [None, None]
    lo, hi = ci
    if diff is None:
        return "INSUFFICIENT_DATA"
    if lo is not None and lo > 0:
        return "EVIDENCE_OF_IMPROVEMENT"
    if hi is not None and hi < 0:
        return "EVIDENCE_OF_REGRESSION"
    return "INCONCLUSIVE"



def paired_questionnaire_summary(questionnaires: list[dict[str, Any]], kind: str, *, lower_is_better: bool, seed: int = 20261025) -> dict[str, Any]:
    by_pid: dict[str, dict[str, float]] = defaultdict(dict)
    for row in questionnaires:
        if row.get("kind") != "block_questionnaire":
            continue
        pid=str(row.get("participant_id")); condition=row.get("condition")
        if condition not in {"baseline","casegraph"}:
            continue
        if kind == "raw_tlx":
            vals=row.get("raw_tlx") or {}
            keys=("mental","physical","temporal","performance","effort","frustration")
            if not all(k in vals for k in keys):
                continue
            value=statistics.fmean(float(vals[k]) for k in keys)
        elif kind == "ux_pulse":
            vals=row.get("ux_pulse") or {}
            if not vals:
                continue
            value=statistics.fmean(float(v) for v in vals.values())
        else:
            raise ValueError(kind)
        by_pid[pid][condition]=value
    baseline=[];casegraph=[];diffs=[]
    for pid,conditions in by_pid.items():
        if "baseline" not in conditions or "casegraph" not in conditions:
            continue
        b=conditions["baseline"];c=conditions["casegraph"]
        baseline.append(b);casegraph.append(c)
        raw=c-b;diffs.append(-raw if lower_is_better else raw)
    lo,hi=bootstrap_mean_ci(diffs,seed=seed)
    return {
        "n_complete_participants":len(diffs),
        "baseline_mean":_safe_mean(baseline),
        "casegraph_mean":_safe_mean(casegraph),
        "paired_improvement_mean":_safe_mean(diffs),
        "paired_improvement_ci95":[lo,hi],
        "paired_sign_flip_p_two_sided":sign_flip_pvalue(diffs,seed=seed),
        "direction":"lower_is_better" if lower_is_better else "higher_is_better",
    }

def build_report(
    scored: list[dict[str, Any]],
    questionnaires: list[dict[str, Any]],
    *,
    seed: int = 20261025,
) -> dict[str, Any]:
    participant_agg = aggregate_by_participant(scored)
    metric_specs = {
        "strict_success": False,
        "diagnosis_correct": False,
        "action_correct": False,
        "unsafe_action": True,
        "source_recall": False,
        "source_precision": False,
        "contradiction_recall": False,
        "established_statement_recall": False,
        "false_established_statement_count": True,
        "brier": True,
        "overconfident_failure": True,
        "elapsed_seconds": True,
    }
    metrics = {
        metric: metric_summary(participant_agg, metric, lower_is_better=lower, seed=seed + i)
        for i, (metric, lower) in enumerate(metric_specs.items())
    }

    questionnaire_metrics = {
        "raw_tlx": paired_questionnaire_summary(questionnaires, "raw_tlx", lower_is_better=True, seed=seed+100),
        "ux_pulse": paired_questionnaire_summary(questionnaires, "ux_pulse", lower_is_better=False, seed=seed+101),
    }

    primary = metrics["strict_success"]
    unsafe = metrics["unsafe_action"]
    gate = classify_primary_gate(primary, unsafe)
    suspicious = sum(int(row.get("suspicious_fast", 0)) for row in scored)
    return {
        "study_version": "casegraph_validation_v1",
        "participant_count_with_any_response": len({r["participant_id"] for r in scored}),
        "complete_paired_participant_count": primary["n_complete_participants"],
        "response_count": len(scored),
        "suspicious_fast_response_count": suspicious,
        "primary_endpoint": "participant-level strict safe-resolution success rate",
        "primary_gate": gate,
        "metrics": metrics,
        "questionnaire_metrics": questionnaire_metrics,
        "claim_boundary": (
            "A positive result supports a controlled synthetic-task usability/effectiveness claim only. "
            "It does not establish real merchant business impact without representative operators and live workflows."
        ),
    }
