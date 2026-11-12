from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, TypeVar, Callable

from .schema import BenchmarkCase, GoldCase, Prediction, BenchmarkValidationError, unique_ids

T = TypeVar("T")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BenchmarkValidationError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            if not isinstance(raw, dict):
                raise BenchmarkValidationError(f"{path}:{line_no}: each JSONL row must be an object")
            rows.append(raw)
    return rows


def load_cases(path: Path) -> list[BenchmarkCase]:
    out = [BenchmarkCase.from_dict(row) for row in _read_jsonl(path)]
    unique_ids(out, "scenario_id")
    return out


def load_gold(path: Path) -> list[GoldCase]:
    out = [GoldCase.from_dict(row) for row in _read_jsonl(path)]
    unique_ids(out, "scenario_id")
    return out


def load_predictions(path: Path) -> list[Prediction]:
    out = [Prediction.from_dict(row) for row in _read_jsonl(path)]
    seen: set[tuple[str, str, str]] = set()
    for item in out:
        key = (item.scenario_id, item.run_id, item.mode)
        if key in seen:
            raise BenchmarkValidationError(f"duplicate prediction key {key}")
        seen.add(key)
    return out


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def benchmark_hash(cases: list[BenchmarkCase], gold: list[GoldCase]) -> str:
    payload = {
        "cases": [case_to_dict(x) for x in cases],
        "gold": [gold_to_dict(x) for x in gold],
    }
    return sha256_json(payload)


def case_to_dict(case: BenchmarkCase) -> dict[str, Any]:
    return {
        "scenario_id": case.scenario_id,
        "split": case.split,
        "category": case.category,
        "difficulty": case.difficulty,
        "description": case.description,
        "paypal_dispute": case.paypal_dispute,
        "transcript": [{"speaker": x.speaker, "message": x.message} for x in case.transcript],
        "merchant_notes": case.merchant_notes,
        "tags": list(case.tags),
    }


def gold_to_dict(gold: GoldCase) -> dict[str, Any]:
    return {
        "scenario_id": gold.scenario_id,
        "required_claims": [{"node_type": x.node_type, "excerpt": x.excerpt} for x in gold.required_claims],
        "missing_evidence": [
            {"label": x.label, "keyword_groups": [list(group) for group in x.keyword_groups]} for x in gold.missing_evidence
        ],
        "contradictions": [
            {"left_excerpt": x.left_excerpt, "right_excerpt": x.right_excerpt} for x in gold.contradictions
        ],
        "preferred_actions": list(gold.preferred_actions),
        "forbidden_actions": list(gold.forbidden_actions),
        "must_abstain": gold.must_abstain,
        "notes": gold.notes,
    }


def prediction_to_dict(prediction: Prediction) -> dict[str, Any]:
    return {
        "scenario_id": prediction.scenario_id,
        "run_id": prediction.run_id,
        "mode": prediction.mode,
        "analysis_status": prediction.analysis_status,
        "analysis_output": prediction.analysis_output,
        "safety": prediction.safety,
        "provenance": prediction.provenance,
        "error": prediction.error,
    }
