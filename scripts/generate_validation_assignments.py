from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from validation.design import build_assignments, validate_assignment_balance
from validation.io import load_jsonl, dump_json


def main() -> int:
    parser = argparse.ArgumentParser(description='Generate counterbalanced CaseGraph validation study participant assignments')
    parser.add_argument('--participants', type=int, default=10)
    parser.add_argument('--seed', type=int, default=20261025)
    parser.add_argument('--scenarios', type=Path, default=ROOT / 'data/validation/scenarios.jsonl')
    parser.add_argument('--output', type=Path, default=ROOT / 'study_runs/assignments.json')
    args = parser.parse_args()

    result = build_assignments(load_jsonl(args.scenarios), participant_count=args.participants, seed=args.seed)
    result['balance'] = validate_assignment_balance(result)
    dump_json(args.output, result)
    print(json.dumps({'status':'PASS','output':str(args.output),'participants':args.participants,'tasks_per_participant':result['tasks_per_participant'],'balance':result['balance']}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
