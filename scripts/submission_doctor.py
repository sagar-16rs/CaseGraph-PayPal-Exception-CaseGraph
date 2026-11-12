from __future__ import annotations
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from submission.submission import ROOT, CLAIMS_PATH, RULES_PATH, SUBMISSION_PATH, is_placeholder, lint_claims, load_json, safe_public_file, scan_text_for_secrets

LICENSE_NAMES=("LICENSE","LICENSE.md","LICENSE.txt","COPYING")

def report(repo: Path, strict: bool=False):
    checks={}; details={}; warnings=[]
    rules=load_json(RULES_PATH); claims=load_json(CLAIMS_PATH); submission=load_json(SUBMISSION_PATH)
    checks['rules_snapshot']=rules.get('submission_requirements',{}).get('demo_video',{}).get('max_seconds')==180 and len(rules.get('judging_criteria',[]))==5
    claim_errors=lint_claims(claims); checks['claim_ledger']=not claim_errors; details['claim_errors']=claim_errors
    checks['validation_framework']=(repo/'docs/VALIDATION_PROTOCOL.md').is_file() and (repo/'validation').is_dir()
    checks['readme']=(repo/'README.md').is_file() or (repo/'README_SUBMISSION.md').is_file()
    license_file=next((x for x in LICENSE_NAMES if (repo/x).is_file()),None); checks['open_source_license']=bool(license_file); details['license_file']=license_file
    duration=int(submission.get('demo_video_duration_seconds') or 0)
    checks['video_duration']=duration==0 or duration<180
    checks['video_url']=not is_placeholder(submission.get('youtube_video_url'))
    checks['repo_url']=not is_placeholder(submission.get('repo_url'))
    mode=submission.get('functional_demo_mode')
    checks['demo_mode']=mode in {'hosted','source'}
    checks['hosted_demo_url']= mode!='hosted' or not is_placeholder(submission.get('hosted_demo_url'))
    checks['license_declared']=not is_placeholder(submission.get('open_source_license'))
    scan_hits=[]
    for p in repo.rglob('*'):
        if not p.is_file(): continue
        ok,reason=safe_public_file(p,repo)
        if not ok and reason in {'environment secret file','credential/private key file'}:
            scan_hits.append(f'{p.relative_to(repo)}: {reason}'); continue
        if not ok: continue
        if p.stat().st_size>2_000_000: continue
        try: text=p.read_text(encoding='utf-8')
        except Exception: continue
        hits=scan_text_for_secrets(text)
        if hits: scan_hits.append(f'{p.relative_to(repo)}: secret-like content')
    checks['secret_scan']=not scan_hits; details['secret_hits']=scan_hits
    if submission.get('live_gate_status')!='PASS': warnings.append('integration live external freeze is not recorded PASS.')
    if submission.get('user_study_status')!='PASS': warnings.append('validation study real user study is not recorded PASS; do not claim measured user benefit.')
    required=['rules_snapshot','claim_ledger','validation_framework','video_duration','demo_mode','secret_scan']
    if strict: required += ['readme','open_source_license','video_url','repo_url','hosted_demo_url','license_declared']
    status='PASS' if all(checks.get(k,False) for k in required) else 'FAIL'
    return {'status':status,'strict':strict,'checks':checks,'details':details,'warnings':warnings}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--repo',default='.'); ap.add_argument('--submission-ready',action='store_true'); args=ap.parse_args()
    out=report(Path(args.repo).resolve(),args.submission_ready); print(json.dumps(out,indent=2,sort_keys=True)); return 0 if out['status']=='PASS' else 1
if __name__=='__main__': raise SystemExit(main())
