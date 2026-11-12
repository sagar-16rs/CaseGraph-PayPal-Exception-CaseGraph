from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from submission.submission import CLAIMS_PATH,RULES_PATH,SUBMISSION_PATH,load_json,lint_claims,is_placeholder

def main():
    rules=load_json(RULES_PATH); claims=load_json(CLAIMS_PATH); sub=load_json(SUBMISSION_PATH)
    errors=lint_claims(claims)
    if int(sub.get('demo_video_duration_seconds') or 0)>=int(rules['submission_requirements']['demo_video']['max_seconds']): errors.append('demo video must be under 180 seconds')
    if sub.get('functional_demo_mode') not in {'hosted','source'}: errors.append('functional_demo_mode must be hosted or source')
    pending=[c['id'] for c in claims['claims'] if c['status']=='PENDING' and c.get('include_in_submission')]
    if pending: errors.append('pending claims included: '+','.join(pending))
    print(json.dumps({'status':'PASS' if not errors else 'FAIL','errors':errors,'criteria':rules['judging_criteria']},indent=2)); return 0 if not errors else 1
if __name__=='__main__': raise SystemExit(main())
