from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from .adapter import run_casegraph_live, run_raw_llm_baseline
from .io import benchmark_hash, load_cases, load_gold, load_predictions, prediction_to_dict, write_jsonl
from .report import build_report
from .score import score_prediction


def _filter_cases(cases, split: str | None, limit: int | None):
    selected = [c for c in cases if split is None or c.split == split]
    if limit is not None:
        selected = selected[:limit]
    return selected


async def _run(args) -> int:
    root = Path(args.data_dir)
    cases = load_cases(root / "cases.jsonl")
    gold = load_gold(root / "gold.jsonl")
    gold_map = {g.scenario_id: g for g in gold}
    if set(gold_map) != {c.scenario_id for c in cases}:
        raise SystemExit("cases/gold scenario IDs differ")
    bench_hash = benchmark_hash(cases, gold)
    selected = _filter_cases(cases, getattr(args, "split", None), getattr(args, "limit", None))
    if args.command == "run" and getattr(args, "split", None) == "holdout" and not getattr(args, "allow_holdout", False):
        raise SystemExit("Holdout execution is locked by default. Re-run with --allow-holdout only for a frozen evaluation.")

    if args.command == "run":
        output_path = Path(args.output)
        rows = []
        for case in selected:
            for repeat in range(args.repeats):
                if args.mode == "casegraph_live":
                    pred = await run_casegraph_live(case, run_index=repeat)
                elif args.mode == "raw_llm":
                    pred = await run_raw_llm_baseline(case, run_index=repeat, model=args.model)
                else:
                    raise SystemExit(f"unsupported mode {args.mode}")
                rows.append(prediction_to_dict(pred))
                print(json.dumps({"scenario_id": case.scenario_id, "run": repeat, "status": pred.analysis_status, "error": pred.error}))
        write_jsonl(output_path, rows)
        print(json.dumps({"status": "DONE", "output": str(output_path), "benchmark_hash": bench_hash, "predictions": len(rows)}, indent=2))
        return 0

    if args.command == "score":
        predictions = []
        for prediction_path in args.predictions:
            predictions.extend(load_predictions(Path(prediction_path)))
        case_map = {c.scenario_id: c for c in cases}
        scores = []
        for pred in predictions:
            if pred.scenario_id not in case_map:
                raise SystemExit(f"prediction references unknown scenario {pred.scenario_id}")
            scores.append(score_prediction(case_map[pred.scenario_id], gold_map[pred.scenario_id], pred))
        report = build_report(scores, benchmark_hash=bench_hash)
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        score_jsonl = out.with_suffix(".scores.jsonl")
        write_jsonl(score_jsonl, [x.to_dict() for x in scores])
        print(json.dumps({"status": "DONE", "report": str(out), "score_rows": str(score_jsonl), "benchmark_hash": bench_hash}, indent=2))
        return 0

    if args.command == "describe":
        by_split = {}
        by_category = {}
        for case in cases:
            by_split[case.split] = by_split.get(case.split, 0) + 1
            by_category[case.category] = by_category.get(case.category, 0) + 1
        print(json.dumps({"benchmark_hash": bench_hash, "cases": len(cases), "by_split": by_split, "by_category": dict(sorted(by_category.items()))}, indent=2))
        return 0

    raise SystemExit("unknown command")


def main() -> int:
    parser = argparse.ArgumentParser(description="CaseGraph evaluation benchmark")
    default_data = Path(__file__).resolve().parents[2] / "data" / "benchmark"
    parser.add_argument("--data-dir", default=str(default_data))
    sub = parser.add_subparsers(dest="command", required=True)

    describe = sub.add_parser("describe")

    run = sub.add_parser("run")
    run.add_argument("--mode", choices=["casegraph_live", "raw_llm"], required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--split", choices=["dev", "holdout", "redteam"], default="dev")
    run.add_argument("--allow-holdout", action="store_true")
    run.add_argument("--limit", type=int)
    run.add_argument("--repeats", type=int, default=1)
    run.add_argument("--model")

    score = sub.add_parser("score")
    score.add_argument("--predictions", required=True, nargs="+")
    score.add_argument("--report", required=True)

    args = parser.parse_args()
    if getattr(args, "repeats", 1) < 1:
        parser.error("--repeats must be >= 1")
    if getattr(args, "limit", None) is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
