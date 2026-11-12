from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from validation.io import dump_json, sha256_file

DEFAULT_FILES = [
    'data/validation/scenarios.jsonl',
    'data/validation/gold.jsonl',
    'data/validation/practice.jsonl',
    'docs/VALIDATION_PROTOCOL.md',
    'docs/VALIDATION_PLAN.md',
    'validation/scoring.py',
    'scripts/analyze_validation_study.py',
    'scripts/serve_validation_study.py',
    'study/user_validation/web/app.js',
]


def main() -> int:
    parser = argparse.ArgumentParser(description='Freeze validation study protocol inputs before confirmatory user testing')
    parser.add_argument('--assignments', type=Path, default=ROOT / 'study_runs/assignments.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'study_runs/PROTOCOL_LOCK.json')
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--casegraph-map', type=Path, default=None, help='Live-product scenario URL map to include in the protocol lock')
    args = parser.parse_args()
    run_dir=args.output.resolve().parent
    responses=run_dir/'responses.jsonl'
    if responses.is_file() and responses.read_text(encoding='utf-8').strip():
        print(json.dumps({'status':'FAIL','reason':'cannot create or replace protocol lock after scored responses exist; start a new run directory/version'}, indent=2))
        return 1
    if args.output.exists() and not args.force:
        print(json.dumps({'status':'FAIL','reason':'protocol lock already exists; use --force only before any confirmatory participant starts'}, indent=2))
        return 1
    files = [ROOT / rel for rel in DEFAULT_FILES] + [args.assignments.resolve()]
    if args.casegraph_map is not None:
        files.append(args.casegraph_map.resolve())
    missing = [str(p) for p in files if not p.is_file()]
    if missing:
        print(json.dumps({'status':'FAIL','missing':missing}, indent=2))
        return 1
    payload = {
        'study_version':'casegraph_validation_v1',
        'frozen_at_utc':datetime.now(timezone.utc).isoformat(),
        # POSIX separators keep the protocol lock identical regardless of the OS
        # that froze it; a Windows backslash path would not match the recorded
        # artifact names when the lock is verified elsewhere.
        'files':{
            (p.relative_to(ROOT).as_posix() if p.is_relative_to(ROOT) else str(p)):sha256_file(p)
            for p in files
        },
        'study_mode':'live_product' if args.casegraph_map is not None else 'packet_pilot',
        'rule':'Do not change scenario content, gold labels, assignments, live case mapping, primary endpoint, runner, or analysis rules after confirmatory data collection begins.',
    }
    dump_json(args.output, payload)
    print(json.dumps({'status':'PASS','output':str(args.output),'file_count':len(files)}, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
