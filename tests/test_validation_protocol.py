from __future__ import annotations
import json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_protocol_lock_detects_drift(tmp_path):
    run=tmp_path/'run';run.mkdir()
    subprocess.run([sys.executable,str(ROOT/'scripts/generate_validation_assignments.py'),'--participants','10','--output',str(run/'assignments.json')],check=True,capture_output=True,text=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/freeze_validation_protocol.py'),'--assignments',str(run/'assignments.json'),'--output',str(run/'PROTOCOL_LOCK.json')],check=True,capture_output=True,text=True)
    data=json.loads((run/'PROTOCOL_LOCK.json').read_text())
    assert 'data/validation/gold.jsonl' in data['files']

def test_doctor_passes_bundle():
    p=subprocess.run([sys.executable,str(ROOT/'scripts/validation_doctor.py')],capture_output=True,text=True)
    assert p.returncode==0,p.stdout+p.stderr
    assert json.loads(p.stdout)['status']=='PASS'

def test_live_map_doctor_passes_with_hash_bound_urls(tmp_path):
    subprocess.run([sys.executable,str(ROOT/'scripts/create_live_case_map.py'),'--output',str(tmp_path/'map.json')],check=True,capture_output=True,text=True)
    data=json.loads((tmp_path/'map.json').read_text())
    for sid,entry in data['cases'].items(): entry['url']=f'http://127.0.0.1:5173/?case={sid}'
    (tmp_path/'map.json').write_text(json.dumps(data))
    p=subprocess.run([sys.executable,str(ROOT/'scripts/validation_doctor.py'),'--casegraph-map',str(tmp_path/'map.json'),'--require-live-map'],capture_output=True,text=True)
    assert p.returncode==0,p.stdout+p.stderr

def test_unlocked_live_run_cannot_be_reported_as_product_claim(tmp_path):
    # Synthetic complete paired data, but deliberately no protocol lock.
    from validation.io import write_jsonl,dump_json,load_jsonl
    gold={x['scenario_id']:x for x in load_jsonl(ROOT/'data/validation/gold.jsonl')}
    scenarios={x['scenario_id']:x for x in load_jsonl(ROOT/'data/validation/scenarios.jsonl')}
    assignments=__import__('validation.design',fromlist=['build_assignments']).build_assignments(list(scenarios.values()),participant_count=8,seed=1)
    rows=[]
    for p in assignments['assignments']:
        for t in p['tasks']:
            g=gold[t['scenario_id']]
            rows.append({'participant_id':p['participant_id'],'scenario_id':t['scenario_id'],'pair_id':t['pair_id'],'variant':t['variant'],'condition':t['condition'],'block':t['block'],'elapsed_seconds':50,'diagnosis_id':g['diagnosis_id'],'action_id':g['safe_action_ids'][0],'selected_sources':g['required_source_ids'],'selected_contradictions':g['required_contradiction_ids'],'established_statement_ids':g['established_statement_ids'],'confidence':90})
    write_jsonl(tmp_path/'responses.jsonl',rows);write_jsonl(tmp_path/'questionnaires.jsonl',[]);dump_json(tmp_path/'run_metadata.json',{'study_mode':'live_product','casegraph_map_sha256':'x'})
    p=subprocess.run([sys.executable,str(ROOT/'scripts/analyze_validation_study.py'),'--run-dir',str(tmp_path),'--allow-unlocked-pilot'],capture_output=True,text=True)
    assert p.returncode==0,p.stdout+p.stderr
    report=json.loads((tmp_path/'validation_report.json').read_text())
    assert report['primary_gate'] in {'INCONCLUSIVE','EVIDENCE_OF_IMPROVEMENT'}
    assert report['product_claim_status']=='PILOT_INTERFACE_ONLY'

def test_protocol_cannot_be_frozen_after_scored_responses(tmp_path):
    subprocess.run([sys.executable,str(ROOT/'scripts/generate_validation_assignments.py'),'--participants','10','--output',str(tmp_path/'assignments.json')],check=True,capture_output=True,text=True)
    (tmp_path/'responses.jsonl').write_text('{"participant_id":"P001"}\n')
    p=subprocess.run([sys.executable,str(ROOT/'scripts/freeze_validation_protocol.py'),'--assignments',str(tmp_path/'assignments.json'),'--output',str(tmp_path/'PROTOCOL_LOCK.json')],capture_output=True,text=True)
    assert p.returncode!=0
    assert 'after scored responses exist' in p.stdout
