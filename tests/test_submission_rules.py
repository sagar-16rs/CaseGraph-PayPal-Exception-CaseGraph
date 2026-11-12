import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def test_rules_snapshot_matches_hackathon_constraints():
    r=json.loads((ROOT/'data/submission/rules_snapshot.json').read_text())
    assert r['submission_requirements']['demo_video']['max_seconds']==180
    assert r['submission_requirements']['public_repo'] is True
    assert r['submission_requirements']['open_source_license'] is True
    assert len(r['judging_criteria'])==5
    assert r['judging_weights']=='equal'

def test_deadline_snapshot_is_exact():
    r=json.loads((ROOT/'data/submission/rules_snapshot.json').read_text())
    assert r['submission_deadline_pt']=='2026-11-12T12:00:00-08:00'
    assert r['submission_deadline_ist']=='2026-11-13T01:30:00+05:30'
