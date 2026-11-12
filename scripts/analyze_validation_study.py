from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from validation.io import load_jsonl, dump_json, load_json, sha256_file
from validation.scoring import score_response, build_report


def verify_protocol_lock(run_dir: Path) -> tuple[bool,list[str]]:
    lock=run_dir/'PROTOCOL_LOCK.json'
    if not lock.is_file(): return False,['protocol lock missing']
    data=load_json(lock); drift=[]
    for rel,digest in data.get('files',{}).items():
        p=Path(rel)
        if not p.is_absolute(): p=ROOT/p
        if not p.is_file() or sha256_file(p)!=digest: drift.append(rel)
    return not drift,drift


def main() -> int:
    parser=argparse.ArgumentParser(description='Analyze paired CaseGraph validation study user study results')
    parser.add_argument('--run-dir',type=Path,default=ROOT/'study_runs')
    parser.add_argument('--output',type=Path,default=None)
    parser.add_argument('--allow-unlocked-pilot',action='store_true')
    args=parser.parse_args(); run=args.run_dir.resolve()
    ok,drift=verify_protocol_lock(run)
    if not ok and not args.allow_unlocked_pilot:
        print(json.dumps({'status':'FAIL','reason':'confirmatory analysis requires an intact protocol lock','drift':drift}, indent=2)); return 1
    gold={r['scenario_id']:r for r in load_jsonl(ROOT/'data/validation/gold.jsonl')}
    responses=load_jsonl(run/'responses.jsonl'); questionnaires=load_jsonl(run/'questionnaires.jsonl')
    seen=Counter((r.get('participant_id'),r.get('scenario_id')) for r in responses)
    dup=[list(k) for k,v in seen.items() if v>1]
    if dup:
        print(json.dumps({'status':'FAIL','reason':'duplicate immutable task responses detected','duplicates':dup[:20]}, indent=2)); return 1
    unknown=sorted({r.get('scenario_id') for r in responses if r.get('scenario_id') not in gold})
    if unknown:
        print(json.dumps({'status':'FAIL','reason':'responses contain unknown scenario IDs','unknown':unknown}, indent=2)); return 1
    scored=[score_response(r,gold[r['scenario_id']]) for r in responses]
    report=build_report(scored,questionnaires)
    metadata=load_json(run/'run_metadata.json') if (run/'run_metadata.json').is_file() else {'study_mode':'unknown'}
    report['study_mode']=metadata.get('study_mode','unknown')
    lock_mode=None
    lock_path=run/'PROTOCOL_LOCK.json'
    if lock_path.is_file(): lock_mode=load_json(lock_path).get('study_mode')
    if ok and lock_mode and lock_mode != report['study_mode']:
        print(json.dumps({'status':'FAIL','reason':'run study_mode does not match frozen protocol','run_mode':report['study_mode'],'lock_mode':lock_mode}, indent=2)); return 1
    report['product_claim_status']=report['primary_gate'] if (ok and report['study_mode']=='live_product') else 'PILOT_INTERFACE_ONLY'
    report['protocol_locked']=ok
    report['protocol_drift']=drift
    report['pilot_mode']=not ok
    report['warning']='Pilot/unlocked results must not be used as confirmatory product claims.' if not ok else None
    assignments_path=run/'assignments_snapshot.json'
    preference={'baseline':0,'casegraph':0,'no_preference':0,'unmapped':0}
    if assignments_path.is_file():
        amap={x['participant_id']:x for x in load_json(assignments_path).get('assignments',[])}
        for q in questionnaires:
            if q.get('kind')!='final_questionnaire': continue
            pref=q.get('preference'); participant=amap.get(q.get('participant_id'))
            if pref=='no_preference': preference['no_preference']+=1; continue
            if not participant: preference['unmapped']+=1; continue
            first,second=participant['sequence'].split('->')
            chosen=first if pref=='first_workspace' else second if pref=='second_workspace' else None
            if chosen in {'baseline','casegraph'}: preference[chosen]+=1
            else: preference['unmapped']+=1
    report['workspace_preference_counts']=preference
    output=args.output or run/'validation_report.json'; dump_json(output,report)
    csv_path=output.with_suffix('.scored.csv')
    if scored:
        with csv_path.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(scored[0].keys())); w.writeheader(); w.writerows(scored)
    print(json.dumps({'status':'PASS','report':str(output),'scored_csv':str(csv_path),'primary_gate':report['primary_gate'],'participants':report['complete_paired_participant_count']}, indent=2))
    return 0

if __name__=='__main__': raise SystemExit(main())
