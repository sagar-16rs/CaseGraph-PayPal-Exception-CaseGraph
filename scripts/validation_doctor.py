from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from validation.design import build_assignments, validate_assignment_balance
from validation.io import load_jsonl, load_json, sha256_file, canonical_json_bytes, sha256_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description='CaseGraph validation study study integrity doctor')
    parser.add_argument('--run-dir', type=Path, default=ROOT / 'study_runs')
    parser.add_argument('--require-lock', action='store_true')
    parser.add_argument('--casegraph-map', type=Path, default=None)
    parser.add_argument('--require-live-map', action='store_true')
    args = parser.parse_args()
    checks = {}
    details = {}
    scenarios = load_jsonl(ROOT/'data/validation/scenarios.jsonl')
    gold = load_jsonl(ROOT/'data/validation/gold.jsonl')
    practice = load_jsonl(ROOT/'data/validation/practice.jsonl')
    checks['scenario_count_20'] = len(scenarios) == 20
    checks['gold_count_20'] = len(gold) == 20
    checks['practice_count_2'] = len(practice) == 2
    scenario_ids = {x['scenario_id'] for x in scenarios}
    gold_ids = {x['scenario_id'] for x in gold}
    checks['gold_scenario_alignment'] = scenario_ids == gold_ids
    checks['gold_not_in_web_root'] = not (ROOT/'study/user_validation/web/gold.jsonl').exists()
    checks['pair_count_10'] = len({x['pair_id'] for x in scenarios}) == 10
    checks['variants_complete'] = all({x['variant'] for x in scenarios if x['pair_id']==p} == {'A','B'} for p in {x['pair_id'] for x in scenarios})
    gold_by_id={x['scenario_id']:x for x in gold}
    reference_errors=[]
    pair_difficulty={}
    for scenario in scenarios:
        sid=scenario['scenario_id'];g=gold_by_id.get(sid,{})
        diag={x['id'] for x in scenario.get('diagnosis_options',[])}
        actions={x['id'] for x in scenario.get('action_options',[])}
        sources={x['id'] for x in scenario.get('source_options',[])}
        contradictions={x['id'] for x in scenario.get('contradiction_options',[])}
        statements={x['id'] for x in scenario.get('statement_check_options',[])}
        safe=set(g.get('safe_action_ids',[]));unsafe=set(g.get('unsafe_action_ids',[]))
        if g.get('diagnosis_id') not in diag: reference_errors.append(f'{sid}:diagnosis')
        if not safe or not safe <= actions or not unsafe <= actions or safe & unsafe: reference_errors.append(f'{sid}:actions')
        if not set(g.get('required_source_ids',[])) <= sources: reference_errors.append(f'{sid}:required_sources')
        if not set(g.get('relevant_source_ids',[])) <= sources: reference_errors.append(f'{sid}:relevant_sources')
        if not set(g.get('required_contradiction_ids',[])) <= contradictions: reference_errors.append(f'{sid}:contradictions')
        if not set(g.get('established_statement_ids',[])) <= statements: reference_errors.append(f'{sid}:statements')
        pair_difficulty.setdefault(scenario['pair_id'],set()).add(scenario.get('difficulty'))
    checks['gold_references_valid']=not reference_errors
    details['gold_reference_errors']=reference_errors
    checks['pair_difficulty_matched']=all(len(v)==1 for v in pair_difficulty.values())

    epistemic_errors=[]
    for item in [*scenarios,*practice]:
        for node in item.get('casegraph',{}).get('nodes',[]):
            if node.get('type')=='VERIFIED_FACT' and not str(node.get('source_id','')).startswith('PP'):
                epistemic_errors.append(f"{item.get('scenario_id')}:{node.get('id')}:{node.get('source_id')}")
    checks['verified_facts_paypal_only']=not epistemic_errors
    details['epistemic_label_errors']=epistemic_errors

    try:
        demo = build_assignments(scenarios, participant_count=10, seed=20261025)
        balance = validate_assignment_balance(demo)
        checks['counterbalance_constructible'] = True
        details['demo_balance'] = balance
    except Exception as exc:
        checks['counterbalance_constructible'] = False
        details['assignment_error'] = str(exc)

    if args.casegraph_map is not None:
        try:
            mapping=load_json(args.casegraph_map)
            cases=mapping.get('cases',{}) if isinstance(mapping,dict) else {}
            map_errors=[]
            for scenario in scenarios:
                entry=cases.get(scenario['scenario_id'])
                expected=sha256_bytes(canonical_json_bytes(scenario))
                if not isinstance(entry,dict) or not str(entry.get('url','')).startswith(('http://','https://')) or entry.get('scenario_sha256')!=expected:
                    map_errors.append(scenario['scenario_id'])
            checks['live_map_valid']=not map_errors and len(cases)==len(scenarios)
            details['live_map_errors']=map_errors
        except Exception as exc:
            checks['live_map_valid']=False;details['live_map_error']=str(exc)
    else:
        checks['live_map_valid']=False

    lock = args.run_dir/'PROTOCOL_LOCK.json'
    checks['protocol_lock_present'] = lock.is_file()
    if lock.is_file():
        try:
            data = load_json(lock)
            drift=[]
            for rel,digest in data.get('files',{}).items():
                p=Path(rel)
                if not p.is_absolute(): p=ROOT/p
                if not p.is_file() or sha256_file(p)!=digest:
                    drift.append(rel)
            checks['protocol_lock_matches'] = not drift
            details['protocol_drift'] = drift
        except Exception as exc:
            checks['protocol_lock_matches'] = False
            details['protocol_lock_error'] = str(exc)
    elif args.require_lock:
        checks['protocol_lock_matches'] = False
    core = ['scenario_count_20','gold_count_20','practice_count_2','gold_scenario_alignment','gold_not_in_web_root','pair_count_10','variants_complete','gold_references_valid','pair_difficulty_matched','verified_facts_paypal_only','counterbalance_constructible']
    if args.require_lock:
        core += ['protocol_lock_present','protocol_lock_matches']
    if args.require_live_map:
        core += ['live_map_valid']
    status='PASS' if all(checks.get(k,False) for k in core) else 'FAIL'
    print(json.dumps({'status':status,'checks':checks,'details':details}, indent=2, sort_keys=True))
    return 0 if status=='PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
