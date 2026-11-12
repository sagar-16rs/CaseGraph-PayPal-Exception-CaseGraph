import json
from pathlib import Path
from submission.submission import lint_claims
ROOT=Path(__file__).resolve().parent.parent

def test_no_pending_claim_is_submission_enabled():
    c=json.loads((ROOT/'data/submission/claim_ledger.json').read_text())
    assert lint_claims(c)==[]
    assert not [x for x in c['claims'] if x['status']=='PENDING' and x.get('include_in_submission')]

def test_known_pending_claims_remain_pending():
    c={x['id']:x for x in json.loads((ROOT/'data/submission/claim_ledger.json').read_text())['claims']}
    assert c['user_study_benefit']['status']=='PENDING'
    assert c['production_ready']['status']=='PENDING'
