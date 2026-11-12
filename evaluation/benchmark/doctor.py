from __future__ import annotations

import importlib
import json
import os
from collections import Counter
from pathlib import Path

from .io import benchmark_hash, load_cases, load_gold


def run(data_dir: Path, *, require_casegraph: bool = False, require_openai: bool = False, repo_root: Path | None = None) -> dict:
    cases = load_cases(data_dir / "cases.jsonl")
    gold = load_gold(data_dir / "gold.jsonl")
    case_ids = {c.scenario_id for c in cases}
    gold_ids = {g.scenario_id for g in gold}
    checks = {
        "dataset_nonempty": bool(cases),
        "gold_exactly_matches_cases": case_ids == gold_ids,
        "minimum_48_cases": len(cases) >= 48,
        "has_dev_holdout_redteam": {c.split for c in cases} == {"dev", "holdout", "redteam"},
        "redteam_minimum_12": sum(c.split == "redteam" for c in cases) >= 12,
        "category_diversity": len({c.category for c in cases}) >= 10,
        "unique_paypal_dispute_ids": len({c.paypal_dispute["dispute_id"] for c in cases}) == len(cases),
        "prompt_injection_present": any("prompt_injection" in c.tags for c in cases),
        "financial_risk_present": any("critical_financial" in c.tags for c in cases),
        "no_gold_in_case_payload": all("preferred_actions" not in json.dumps(c.paypal_dispute) for c in cases),
    }
    details: dict[str, object] = {}

    if require_casegraph:
        root = (repo_root or Path.cwd()).resolve()
        required_files = [
            "backend/ai/service.py",
            "backend/casegraph/schema.py",
            "backend/safety/service.py",
            "backend/services/cases.py",
            "backend/services/evidence.py",
        ]
        file_results = {rel: (root / rel).is_file() for rel in required_files}
        checks["casegraph_files"] = all(file_results.values())
        details["casegraph_files"] = file_results

        required_modules = [
            "backend.ai.schemas",
            "backend.ai.service",
            "backend.casegraph.schema",
            "backend.safety.service",
            "backend.services.cases",
            "backend.services.evidence",
        ]
        module_results: dict[str, bool] = {}
        for name in required_modules:
            try:
                importlib.import_module(name)
                module_results[name] = True
            except Exception:
                module_results[name] = False
        checks["casegraph_interfaces_import"] = all(module_results.values())
        details["module_imports"] = module_results

    if require_openai:
        checks["openai_api_key_present"] = bool(os.getenv("OPENAI_API_KEY"))
        checks["openai_model_configured"] = bool(os.getenv("OPENAI_MODEL"))

    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "benchmark_hash": benchmark_hash(cases, gold),
        "case_count": len(cases),
        "split_counts": dict(Counter(c.split for c in cases)),
        "category_counts": dict(Counter(c.category for c in cases)),
        "details": details,
    }
