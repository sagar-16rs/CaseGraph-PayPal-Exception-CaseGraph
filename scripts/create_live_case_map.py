from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(ROOT))
from validation.io import canonical_json_bytes,sha256_bytes,load_jsonl,dump_json

def main()->int:
 p=argparse.ArgumentParser(description='Create a validation study live CaseGraph mapping template bound to scenario hashes')
 p.add_argument('--output',type=Path,default=ROOT/'study_runs/live_casegraph_map.json');a=p.parse_args()
 cases={}
 for row in load_jsonl(ROOT/'data/validation/scenarios.jsonl'):
  cases[row['scenario_id']]={'url':'REPLACE_WITH_LIVE_CASEGRAPH_URL','scenario_sha256':sha256_bytes(canonical_json_bytes(row))}
 dump_json(a.output,{'study_version':'casegraph_validation_v1','cases':cases,'instruction':'Replace only url values after seeding the corresponding live CaseGraph case from the exact frozen scenario. Do not change scenario_sha256.'})
 print(json.dumps({'status':'PASS','output':str(a.output),'cases':len(cases)},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
