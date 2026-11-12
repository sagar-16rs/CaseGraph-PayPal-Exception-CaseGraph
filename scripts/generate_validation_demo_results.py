from __future__ import annotations
import argparse, json, random, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from validation.io import load_json,load_jsonl,write_jsonl

def main():
 p=argparse.ArgumentParser(description='Generate synthetic validation study responses ONLY to validate the analysis pipeline');p.add_argument('--run-dir',type=Path,default=ROOT/'study_runs/demo');p.add_argument('--seed',type=int,default=7);a=p.parse_args();rng=random.Random(a.seed)
 assignments=load_json(ROOT/'study_runs/assignments.json');sc={x['scenario_id']:x for x in load_jsonl(ROOT/'data/validation/scenarios.jsonl')};gold={x['scenario_id']:x for x in load_jsonl(ROOT/'data/validation/gold.jsonl')};responses=[];qs=[]
 for person in assignments['assignments']:
  for task in person['tasks']:
   sid=task['scenario_id'];g=gold[sid];s=sc[sid];cg=task['condition']=='casegraph';good=rng.random()<(0.88 if cg else 0.68)
   diag=g['diagnosis_id'] if good else next(x['id'] for x in s['diagnosis_options'] if x['id']!=g['diagnosis_id'])
   action=g['safe_action_ids'][0] if good else (g.get('unsafe_action_ids') or [s['action_options'][0]['id']])[0]
   responses.append({'participant_id':person['participant_id'],'scenario_id':sid,'pair_id':task['pair_id'],'variant':task['variant'],'condition':task['condition'],'block':task['block'],'elapsed_seconds':rng.uniform(45,130)*(0.78 if cg else 1.0),'diagnosis_id':diag,'action_id':action,'selected_sources':g['required_source_ids'] if good else g['required_source_ids'][:1],'selected_contradictions':g['required_contradiction_ids'] if good else [],'established_statement_ids':g['established_statement_ids'] if good else g['established_statement_ids']+['F999'],'confidence':rng.randint(60,95),'rationale':'SYNTHETIC DEMO RESPONSE — NOT USER DATA'})
  for block,condition in [(1,person['tasks'][0]['condition']),(2,person['tasks'][-1]['condition'])]:
   base=42 if condition=='casegraph' else 58;qs.append({'participant_id':person['participant_id'],'kind':'block_questionnaire','block':block,'condition':condition,'raw_tlx':{k:max(0,min(100,base+rng.randint(-8,8))) for k in ['mental','physical','temporal','performance','effort','frustration']},'ux_pulse':{k:(6 if condition=='casegraph' else 4) for k in ['fact_claim_clarity','source_traceability','action_reasoning','appropriate_trust','gap_detection']}})
 a.run_dir.mkdir(parents=True,exist_ok=True);write_jsonl(a.run_dir/'responses.jsonl',responses);write_jsonl(a.run_dir/'questionnaires.jsonl',qs);print(json.dumps({'status':'PASS','warning':'Synthetic demo only. Never report these as product results.','responses':len(responses),'run_dir':str(a.run_dir)},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
