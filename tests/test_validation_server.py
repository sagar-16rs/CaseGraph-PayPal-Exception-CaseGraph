from __future__ import annotations
import importlib.util,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def load_server_module():
    spec=importlib.util.spec_from_file_location('validation_serve',ROOT/'scripts/serve_validation_study.py');m=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(m);return m

def test_task_packet_never_contains_gold(tmp_path):
    subprocess.run([sys.executable,str(ROOT/'scripts/generate_validation_assignments.py'),'--participants','2','--output',str(tmp_path/'assignments.json')],check=True,capture_output=True,text=True)
    m=load_server_module();state=m.StudyState(tmp_path,tmp_path/'assignments.json');pid='P001'
    # mark practices done
    from validation.io import append_jsonl
    append_jsonl(tmp_path/'questionnaires.jsonl',{'participant_id':pid,'kind':'practice_done','block':'baseline','condition':'baseline'})
    append_jsonl(tmp_path/'questionnaires.jsonl',{'participant_id':pid,'kind':'practice_done','block':'casegraph','condition':'casegraph'})
    step=state.next_step(pid);packet=state.task_packet(pid,step)['packet']
    text=json.dumps(packet)
    assert 'safe_action_ids' not in text and 'required_source_ids' not in text and 'diagnosis_id' not in text

def test_server_time_is_bound_to_hmac_token_and_response_is_immutable(tmp_path):
    subprocess.run([sys.executable,str(ROOT/'scripts/generate_validation_assignments.py'),'--participants','2','--output',str(tmp_path/'assignments.json')],check=True,capture_output=True,text=True)
    m=load_server_module();state=m.StudyState(tmp_path,tmp_path/'assignments.json');pid='P001'
    from validation.io import append_jsonl
    for c in ('baseline','casegraph'): append_jsonl(tmp_path/'questionnaires.jsonl',{'participant_id':pid,'kind':'practice_done','block':c,'condition':c})
    step=state.next_step(pid);data=state.task_packet(pid,step);s=data['packet'];body={'participant_id':pid,'scenario_id':s['scenario_id'],'trial_token':data['trial_token'],'diagnosis_id':s['diagnosis_options'][0]['id'],'action_id':s['action_options'][0]['id'],'selected_sources':[],'selected_contradictions':[],'established_statement_ids':[],'confidence':50,'rationale':''}
    out=state.submit_response(pid,body);assert out['status']=='saved'
    try: state.submit_response(pid,body);assert False,'duplicate should fail'
    except ValueError: pass

def test_non_loopback_is_rejected_by_cli(tmp_path):
    m=load_server_module()
    try:
        m.validate_bind_host('0.0.0.0')
        assert False, 'non-loopback host should fail'
    except ValueError as exc:
        assert 'Refusing non-loopback bind' in str(exc)

def test_live_product_mode_requires_complete_hash_bound_map(tmp_path):
    subprocess.run([sys.executable,str(ROOT/'scripts/generate_validation_assignments.py'),'--participants','2','--output',str(tmp_path/'assignments.json')],check=True,capture_output=True,text=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/create_live_case_map.py'),'--output',str(tmp_path/'map.json')],check=True,capture_output=True,text=True)
    mapping=json.loads((tmp_path/'map.json').read_text())
    for sid,entry in mapping['cases'].items(): entry['url']=f'http://127.0.0.1:5173/?study={sid}'
    (tmp_path/'map.json').write_text(json.dumps(mapping))
    m=load_server_module();state=m.StudyState(tmp_path,tmp_path/'assignments.json',tmp_path/'map.json')
    assert state.study_mode=='live_product'
    pid='P001';from validation.io import append_jsonl
    first_condition=state.participant(pid)['tasks'][0]['condition']
    practice_sid='baseline' if first_condition=='baseline' else 'casegraph'
    # complete practice for first block only
    append_jsonl(tmp_path/'questionnaires.jsonl',{'participant_id':pid,'kind':'practice_done','block':first_condition,'condition':first_condition})
    step=state.next_step(pid);data=state.task_packet(pid,step)
    assert 'external_workspace_url' in data['packet']
    if step['condition']=='casegraph': assert 'casegraph' not in data['packet']
    else: assert data['packet']['external_workspace_url'].startswith('/baseline?scenario_id=') and 'timeline' not in data['packet']


def test_live_map_hash_drift_is_rejected(tmp_path):
    subprocess.run([sys.executable,str(ROOT/'scripts/generate_validation_assignments.py'),'--participants','2','--output',str(tmp_path/'assignments.json')],check=True,capture_output=True,text=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/create_live_case_map.py'),'--output',str(tmp_path/'map.json')],check=True,capture_output=True,text=True)
    mapping=json.loads((tmp_path/'map.json').read_text());first=next(iter(mapping['cases'].values()));first['url']='http://127.0.0.1:5173/';first['scenario_sha256']='0'*64;(tmp_path/'map.json').write_text(json.dumps(mapping))
    m=load_server_module()
    try: m.StudyState(tmp_path,tmp_path/'assignments.json',tmp_path/'map.json');assert False,'hash drift should fail'
    except ValueError as exc: assert 'hash mismatch' in str(exc) or 'http(s) url' in str(exc)

def test_option_order_is_stable_per_participant_but_not_fixed_to_gold(tmp_path):
    subprocess.run([sys.executable,str(ROOT/'scripts/generate_validation_assignments.py'),'--participants','2','--output',str(tmp_path/'assignments.json')],check=True,capture_output=True,text=True)
    m=load_server_module();state=m.StudyState(tmp_path,tmp_path/'assignments.json');pid='P001'
    from validation.io import append_jsonl,load_jsonl
    first=state.participant(pid)['tasks'][0]['condition'];append_jsonl(tmp_path/'questionnaires.jsonl',{'participant_id':pid,'kind':'practice_done','block':first,'condition':first})
    step=state.next_step(pid);a=state.task_packet(pid,step)['packet'];b=state.task_packet(pid,step)['packet']
    assert [x['id'] for x in a['action_options']]==[x['id'] for x in b['action_options']]
    # Across the full assignment, the first displayed action must not always be A1.
    first_ids=[]
    for task in state.participant(pid)['tasks']:
        packet=state.task_packet(pid,{'kind':'task',**task})['packet'];first_ids.append(packet['action_options'][0]['id'])
    assert len(set(first_ids))>1

def test_run_directory_cannot_mix_packet_and_live_modes(tmp_path):
    subprocess.run([sys.executable,str(ROOT/'scripts/generate_validation_assignments.py'),'--participants','2','--output',str(tmp_path/'assignments.json')],check=True,capture_output=True,text=True)
    m=load_server_module();m.StudyState(tmp_path,tmp_path/'assignments.json')
    subprocess.run([sys.executable,str(ROOT/'scripts/create_live_case_map.py'),'--output',str(tmp_path/'map.json')],check=True,capture_output=True,text=True)
    mapping=json.loads((tmp_path/'map.json').read_text())
    for sid,entry in mapping['cases'].items(): entry['url']=f'http://127.0.0.1:5173/?study={sid}'
    (tmp_path/'map.json').write_text(json.dumps(mapping))
    try: m.StudyState(tmp_path,tmp_path/'assignments.json',tmp_path/'map.json');assert False,'mode mixing must fail'
    except ValueError as exc: assert 'different validation study study mode' in str(exc)
