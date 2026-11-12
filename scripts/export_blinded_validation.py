from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from validation.io import load_jsonl


def blind_id(pid:str,sid:str)->str:
    return 'B-'+hashlib.sha256(f'{pid}|{sid}|casegraph-validation'.encode()).hexdigest()[:12].upper()


def main()->int:
    p=argparse.ArgumentParser(description='Export free-text validation study responses without condition labels for blinded qualitative coding')
    p.add_argument('--run-dir',type=Path,default=ROOT/'study_runs')
    p.add_argument('--output',type=Path,default=ROOT/'study_runs/blinded_qualitative.csv')
    a=p.parse_args(); rows=[]
    for r in load_jsonl(a.run_dir/'responses.jsonl'):
        text=(r.get('rationale') or '').strip()
        if text:
            rows.append({'blind_id':blind_id(str(r['participant_id']),str(r['scenario_id'])),'rationale':text})
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['blind_id','rationale']); w.writeheader(); w.writerows(rows)
    print(json.dumps({'status':'PASS','output':str(a.output),'rows':len(rows)}))
    return 0
if __name__=='__main__': raise SystemExit(main())
