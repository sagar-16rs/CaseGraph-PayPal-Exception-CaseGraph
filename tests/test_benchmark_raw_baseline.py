from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.benchmark import adapter


def test_raw_baseline_uses_structured_outputs_and_never_calls_casegraph_actions():
    source = inspect.getsource(adapter.run_raw_llm_baseline)
    assert '"json_schema"' in source
    assert '"strict": True' in source
    assert "action_engine" not in source
    assert "execute(" not in source
    assert "load_gold" not in source
    assert "gold.jsonl" not in source


def test_live_casegraph_eval_never_approves_or_executes_paypal_actions():
    source = inspect.getsource(adapter.run_casegraph_live)
    assert "action_engine" not in source
    assert ".approve(" not in source
    assert ".execute(" not in source
    assert "ai_reasoning_service.analyze" in source
    assert "safety_service.get" in source
