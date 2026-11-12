from __future__ import annotations

import random
from collections import Counter
from typing import Any

CONDITIONS = ("baseline", "casegraph")


def participant_id(index: int) -> str:
    return f"P{index + 1:03d}"


def build_assignments(
    scenarios: list[dict[str, Any]],
    participant_count: int = 10,
    seed: int = 20261025,
) -> dict[str, Any]:
    if participant_count < 2:
        raise ValueError("participant_count must be at least 2")
    by_pair: dict[str, dict[str, dict[str, Any]]] = {}
    for scenario in scenarios:
        pair_id = str(scenario["pair_id"])
        variant = str(scenario["variant"])
        by_pair.setdefault(pair_id, {})[variant] = scenario
    pair_ids = sorted(by_pair)
    if len(pair_ids) % 2:
        raise ValueError("validation study scored pair count must be even so each participant receives equal conditions")
    for pair_id, variants in by_pair.items():
        if set(variants) != {"A", "B"}:
            raise ValueError(f"pair {pair_id} must contain exactly variants A and B")

    rng = random.Random(seed)
    assignments: list[dict[str, Any]] = []
    for p_idx in range(participant_count):
        pid = participant_id(p_idx)
        first_condition = "baseline" if p_idx % 2 == 0 else "casegraph"
        second_condition = "casegraph" if first_condition == "baseline" else "baseline"
        condition_for_pair: dict[str, str] = {}
        variant_for_pair: dict[str, str] = {}
        base_variant_cycle = ("A", "B", "B", "A")
        for j, pair_id in enumerate(pair_ids):
            condition_for_pair[pair_id] = "baseline" if (p_idx + j) % 2 == 0 else "casegraph"
            base_variant = base_variant_cycle[p_idx % len(base_variant_cycle)]
            variant_for_pair[pair_id] = base_variant if j % 2 == 0 else ("B" if base_variant == "A" else "A")

        tasks: list[dict[str, Any]] = []
        for block_idx, condition in enumerate((first_condition, second_condition), start=1):
            ids = [pair_id for pair_id in pair_ids if condition_for_pair[pair_id] == condition]
            block_rng = random.Random(rng.randrange(1 << 30))
            block_rng.shuffle(ids)
            for order_in_block, pair_id in enumerate(ids, start=1):
                variant = variant_for_pair[pair_id]
                scenario = by_pair[pair_id][variant]
                tasks.append(
                    {
                        "block": block_idx,
                        "order_in_block": order_in_block,
                        "condition": condition,
                        "pair_id": pair_id,
                        "scenario_id": scenario["scenario_id"],
                        "variant": variant,
                    }
                )
        assignments.append(
            {
                "participant_id": pid,
                "sequence": f"{first_condition}->{second_condition}",
                "tasks": tasks,
            }
        )

    result = {
        "study_version": "casegraph_validation_v1",
        "seed": seed,
        "participant_count": participant_count,
        "pair_count": len(pair_ids),
        "tasks_per_participant": len(pair_ids),
        "assignments": assignments,
    }
    validate_assignment_balance(result)
    return result


def validate_assignment_balance(assignments: dict[str, Any]) -> dict[str, Any]:
    rows = assignments.get("assignments", [])
    if not rows:
        raise ValueError("assignments are empty")
    sequences = Counter(row["sequence"] for row in rows)
    pair_condition: dict[str, Counter[str]] = {}
    pair_variant: dict[str, Counter[str]] = {}
    pair_condition_variant: dict[tuple[str,str], Counter[str]] = {}
    for row in rows:
        seen_pairs: set[str] = set()
        conditions = Counter()
        for task in row["tasks"]:
            pair_id = task["pair_id"]
            if pair_id in seen_pairs:
                raise ValueError(f"{row['participant_id']} sees pair {pair_id} more than once")
            seen_pairs.add(pair_id)
            condition = task["condition"]
            if condition not in CONDITIONS:
                raise ValueError(f"invalid condition {condition}")
            conditions[condition] += 1
            pair_condition.setdefault(pair_id, Counter())[condition] += 1
            pair_variant.setdefault(pair_id, Counter())[task["variant"]] += 1
            pair_condition_variant.setdefault((pair_id, condition), Counter())[task["variant"]] += 1
        if conditions["baseline"] != conditions["casegraph"]:
            raise ValueError(f"{row['participant_id']} does not receive equal condition counts")
    if abs(sequences["baseline->casegraph"] - sequences["casegraph->baseline"]) > 1:
        raise ValueError("condition order is not counterbalanced")
    for pair_id, counts in pair_condition.items():
        if abs(counts["baseline"] - counts["casegraph"]) > 1:
            raise ValueError(f"pair {pair_id} is imbalanced across conditions: {dict(counts)}")
    for pair_id, counts in pair_variant.items():
        if abs(counts["A"] - counts["B"]) > 1:
            raise ValueError(f"pair {pair_id} is imbalanced across variants: {dict(counts)}")
    for (pair_id, condition), counts in pair_condition_variant.items():
        if abs(counts['A'] - counts['B']) > 1:
            raise ValueError(f'pair {pair_id}/{condition} variants are confounded: {dict(counts)}')
    return {
        "sequence_counts": dict(sequences),
        "pair_condition_counts": {k: dict(v) for k, v in sorted(pair_condition.items())},
        "pair_variant_counts": {k: dict(v) for k, v in sorted(pair_variant.items())},
        "pair_condition_variant_counts": {f'{k[0]}:{k[1]}': dict(v) for k, v in sorted(pair_condition_variant.items())},
    }
