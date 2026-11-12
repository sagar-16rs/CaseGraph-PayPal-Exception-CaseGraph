from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import html
import json
import mimetypes
import os
import random
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from validation.io import append_jsonl, load_json, load_jsonl, dump_json, canonical_json_bytes, sha256_bytes, sha256_file

WEB_ROOT=ROOT/'study/user_validation/web'

class StudyState:
    def __init__(self,run_dir:Path,assignments_path:Path,casegraph_map_path:Path|None=None):
        self.run_dir=run_dir; self.run_dir.mkdir(parents=True,exist_ok=True)
        self.assignments=load_json(assignments_path)
        dump_json(self.run_dir/'assignments_snapshot.json', self.assignments)
        self.by_participant={r['participant_id']:r for r in self.assignments['assignments']}
        self.scenarios={r['scenario_id']:r for r in load_jsonl(ROOT/'data/validation/scenarios.jsonl')}
        self.practice={r['scenario_id']:r for r in load_jsonl(ROOT/'data/validation/practice.jsonl')}
        raw_map = load_json(casegraph_map_path) if casegraph_map_path else None
        self.casegraph_map = raw_map.get('cases', {}) if isinstance(raw_map, dict) and 'cases' in raw_map else raw_map
        if self.casegraph_map is not None:
            missing = sorted(set(self.scenarios) - set(self.casegraph_map))
            if missing:
                raise ValueError(f'live CaseGraph map is missing {len(missing)} scenarios: {missing[:5]}')
            for sid, scenario in self.scenarios.items():
                entry = self.casegraph_map.get(sid)
                if not isinstance(entry, dict) or not str(entry.get('url','')).startswith(('http://','https://')):
                    raise ValueError(f'live CaseGraph map entry for {sid} must contain an http(s) url')
                expected = sha256_bytes(canonical_json_bytes(scenario))
                if entry.get('scenario_sha256') != expected:
                    raise ValueError(f'live CaseGraph map scenario hash mismatch for {sid}')
        self.study_mode = 'live_product' if self.casegraph_map is not None else 'packet_pilot'
        metadata={'study_mode':self.study_mode,'casegraph_map_sha256':sha256_file(casegraph_map_path) if casegraph_map_path else None,'assignments_sha256':sha256_file(assignments_path)}
        metadata_path=self.run_dir/'run_metadata.json'
        if metadata_path.exists() and load_json(metadata_path) != metadata:
            raise ValueError('run directory is already bound to a different validation study study mode or live-case map')
        dump_json(metadata_path, metadata)
        self.responses_path=self.run_dir/'responses.jsonl'
        self.questionnaires_path=self.run_dir/'questionnaires.jsonl'
        self.active_path=self.run_dir/'active_trials.json'
        self.secret_path=self.run_dir/'.study_secret'
        if not self.secret_path.exists():
            self.secret_path.write_text(secrets.token_hex(32),encoding='ascii')
            try: os.chmod(self.secret_path,0o600)
            except OSError: pass
        self.secret=bytes.fromhex(self.secret_path.read_text(encoding='ascii').strip())
        self.lock=threading.Lock()
        self.active=load_json(self.active_path) if self.active_path.exists() else {}

    def completed_keys(self):
        return {(r['participant_id'],r['scenario_id']) for r in load_jsonl(self.responses_path)}

    def questionnaire_keys(self):
        return {(r['participant_id'],r.get('kind'),r.get('block')) for r in load_jsonl(self.questionnaires_path)}

    def participant(self,pid:str):
        if pid not in self.by_participant: raise ValueError('Unknown participant ID')
        return self.by_participant[pid]

    def _token(self,pid:str,sid:str,started:float)->str:
        payload=json.dumps({'p':pid,'s':sid,'t':started},separators=(',',':'),sort_keys=True).encode()
        sig=hmac.new(self.secret,payload,hashlib.sha256).digest()
        return base64.urlsafe_b64encode(payload+sig).decode().rstrip('=')

    def _verify_token(self,token:str,pid:str,sid:str)->float:
        pad='='*((4-len(token)%4)%4)
        try: raw=base64.urlsafe_b64decode(token+pad)
        except Exception as exc: raise ValueError('Invalid trial token') from exc
        if len(raw)<32: raise ValueError('Invalid trial token')
        payload,sig=raw[:-32],raw[-32:]
        expected=hmac.new(self.secret,payload,hashlib.sha256).digest()
        if not hmac.compare_digest(sig,expected): raise ValueError('Invalid trial token signature')
        data=json.loads(payload)
        if data.get('p')!=pid or data.get('s')!=sid: raise ValueError('Trial token does not match task')
        return float(data['t'])

    def next_step(self,pid:str):
        participant=self.participant(pid); completed=self.completed_keys(); qkeys=self.questionnaire_keys()
        for block in (1,2):
            block_tasks=[t for t in participant['tasks'] if int(t['block'])==block]
            condition=block_tasks[0]['condition']
            practice_sid='S12-PRACTICE-BASELINE' if condition=='baseline' else 'S12-PRACTICE-CASEGRAPH'
            if (pid,'practice_done',condition) not in qkeys:
                return {'kind':'practice','condition':condition,'scenario_id':practice_sid,'block':block}
            for task in block_tasks:
                if (pid,task['scenario_id']) not in completed:
                    return {'kind':'task',**task}
            if (pid,'block_questionnaire',block) not in qkeys:
                condition=block_tasks[0]['condition']
                return {'kind':'block_questionnaire','block':block,'condition':condition}
        if (pid,'final_questionnaire',None) not in qkeys:
            return {'kind':'final_questionnaire'}
        return {'kind':'complete'}

    def task_packet(self,pid:str,step:dict):
        sid=step['scenario_id']; condition=step['condition']
        source=self.practice[sid] if step['kind']=='practice' else self.scenarios[sid]
        packet={k:v for k,v in source.items() if k not in {'timeline','casegraph'}}
        packet['condition']=condition
        packet['workspace_label']='Workspace'
        for field in ('diagnosis_options','action_options','source_options','contradiction_options','statement_check_options'):
            values=list(packet.get(field,[]))
            seed_bytes=hashlib.sha256(f'{pid}|{sid}|{field}|casegraph-validation'.encode()).digest()
            random.Random(int.from_bytes(seed_bytes[:8],'big')).shuffle(values)
            packet[field]=values
        if self.study_mode=='live_product' and step['kind']=='task':
            if condition=='baseline':
                packet['external_workspace_url']=f'/baseline?scenario_id={sid}'
            else:
                packet['external_workspace_url']=self.casegraph_map[sid]['url']
        elif condition=='baseline':
            packet['timeline']=source.get('timeline',[])
        else:
            packet['casegraph']=source.get('casegraph',{})
        if step['kind']=='practice':
            return {'step':step,'packet':packet,'trial_token':None}
        key=f'{pid}|{sid}'
        with self.lock:
            active=self.active.get(key)
            if not active:
                started=time.time(); active={'started_epoch':started,'trial_token':self._token(pid,sid,started)}
                self.active[key]=active; dump_json(self.active_path,self.active)
        return {'step':step,'packet':packet,'trial_token':active['trial_token']}

    def submit_response(self,pid:str,body:dict):
        step=self.next_step(pid)
        if step.get('kind')!='task': raise ValueError('No scored task is currently awaiting submission')
        sid=step['scenario_id']
        if body.get('scenario_id')!=sid: raise ValueError('Scenario does not match assigned next task')
        token=str(body.get('trial_token') or '')
        started=self._verify_token(token,pid,sid)
        scenario=self.scenarios[sid]
        valid={
            'diagnosis_id':{x['id'] for x in scenario['diagnosis_options']},
            'action_id':{x['id'] for x in scenario['action_options']},
            'selected_sources':{x['id'] for x in scenario['source_options']},
            'selected_contradictions':{x['id'] for x in scenario['contradiction_options']},
            'established_statement_ids':{x['id'] for x in scenario['statement_check_options']},
        }
        if body.get('diagnosis_id') not in valid['diagnosis_id']: raise ValueError('Invalid diagnosis option')
        if body.get('action_id') not in valid['action_id']: raise ValueError('Invalid action option')
        for field in ('selected_sources','selected_contradictions','established_statement_ids'):
            values=body.get(field,[])
            if not isinstance(values,list) or any(v not in valid[field] for v in values): raise ValueError(f'Invalid {field}')
        confidence=float(body.get('confidence',0))
        if confidence<0 or confidence>100: raise ValueError('confidence must be 0..100')
        now=time.time(); row={
            'participant_id':pid,'scenario_id':sid,'pair_id':step['pair_id'],'variant':step['variant'],'condition':step['condition'],'block':step['block'],
            'submitted_epoch':now,'elapsed_seconds':round(max(0.0,now-started),3),
            'diagnosis_id':body['diagnosis_id'],'action_id':body['action_id'],'selected_sources':sorted(set(body.get('selected_sources',[]))),
            'selected_contradictions':sorted(set(body.get('selected_contradictions',[]))),
            'established_statement_ids':sorted(set(body.get('established_statement_ids',[]))),
            'confidence':confidence,'rationale':str(body.get('rationale',''))[:4000],
        }
        with self.lock:
            if (pid,sid) in self.completed_keys(): raise ValueError('Response already submitted; validation study responses are immutable')
            append_jsonl(self.responses_path,row)
            self.active.pop(f'{pid}|{sid}',None); dump_json(self.active_path,self.active)
        return {'status':'saved','next':self.next_step(pid)}

    def submit_questionnaire(self,pid:str,body:dict):
        step=self.next_step(pid); kind=step.get('kind')
        if kind=='practice':
            if body.get('kind')!='practice_done' or body.get('condition')!=step['condition']: raise ValueError('Practice completion mismatch')
            row={'participant_id':pid,'kind':'practice_done','block':step['condition'],'condition':step['condition'],'submitted_epoch':time.time()}
        elif kind=='block_questionnaire':
            if body.get('kind')!='block_questionnaire' or int(body.get('block',-1))!=int(step['block']): raise ValueError('Block questionnaire mismatch')
            tlx=body.get('raw_tlx') or {}; pulse=body.get('ux_pulse') or {}
            required_tlx={'mental','physical','temporal','performance','effort','frustration'}
            required_pulse={'fact_claim_clarity','source_traceability','action_reasoning','appropriate_trust','gap_detection'}
            if set(tlx)!=required_tlx or any(not (0<=float(v)<=100) for v in tlx.values()): raise ValueError('Raw TLX requires six 0..100 ratings')
            if set(pulse)!=required_pulse or any(not (1<=float(v)<=7) for v in pulse.values()): raise ValueError('UX pulse requires five 1..7 ratings')
            row={'participant_id':pid,'kind':'block_questionnaire','block':step['block'],'condition':step['condition'],'raw_tlx':tlx,'ux_pulse':pulse,'submitted_epoch':time.time()}
        elif kind=='final_questionnaire':
            if body.get('kind')!='final_questionnaire': raise ValueError('Final questionnaire mismatch')
            pref=body.get('preference')
            if pref not in {'first_workspace','second_workspace','no_preference'}: raise ValueError('Invalid preference')
            row={'participant_id':pid,'kind':'final_questionnaire','block':None,'condition':None,'preference':pref,'comments':str(body.get('comments',''))[:8000],'submitted_epoch':time.time()}
        else:
            raise ValueError('No questionnaire is currently awaiting submission')
        with self.lock:
            key=(row['participant_id'],row['kind'],row.get('block'))
            if key in self.questionnaire_keys(): raise ValueError('Questionnaire already submitted')
            append_jsonl(self.questionnaires_path,row)
        return {'status':'saved','next':self.next_step(pid)}

def validate_bind_host(host:str)->None:
    if host not in {'127.0.0.1','localhost','::1'}:
        raise ValueError('Refusing non-loopback bind: this study server is intentionally local-only and has no remote participant authentication.')


class Handler(BaseHTTPRequestHandler):
    state:StudyState
    server_version='CaseGraphValidation/1.0'
    def log_message(self,format,*args):
        # Intentionally omit client IP/user-agent from study logs.
        return
    def _json(self,status,payload):
        data=json.dumps(payload,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def _body(self):
        n=int(self.headers.get('Content-Length','0') or 0)
        if n>200_000: raise ValueError('Request body too large')
        return json.loads(self.rfile.read(n) or b'{}')
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/api/next':
            pid=parse_qs(u.query).get('participant_id',[''])[0]
            try:
                step=self.state.next_step(pid)
                if step['kind'] in {'task','practice'}: self._json(200,self.state.task_packet(pid,step))
                else: self._json(200,{'step':step})
            except ValueError as exc: self._json(400,{'error':str(exc)})
            return
        if u.path=='/baseline':
            sid=parse_qs(u.query).get('scenario_id',[''])[0]
            scenario=self.state.scenarios.get(sid)
            if not scenario: self._json(404,{'error':'unknown scenario'}); return
            rows=''.join(f'<div style="border-left:3px solid #999;padding:10px;margin:10px 0"><b>{html.escape(str(x["actor"]))} · {html.escape(str(x["id"]))}</b><div>{html.escape(str(x["text"]))}</div></div>' for x in scenario.get('timeline',[]))
            doc=f'<!doctype html><meta charset="utf-8"><title>Workspace</title><main style="font-family:system-ui;max-width:900px;margin:30px auto;padding:0 16px"><h2>Workspace</h2><p>Review the chronological evidence below, then return to the study response tab.</p>{rows}</main>'.encode()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(doc)));self.end_headers();self.wfile.write(doc);return
        path='index.html' if u.path in {'','/'} else u.path.lstrip('/')
        target=(WEB_ROOT/path).resolve()
        if WEB_ROOT.resolve() not in target.parents and target!=WEB_ROOT.resolve(): self._json(404,{'error':'not found'}); return
        if not target.is_file(): self._json(404,{'error':'not found'}); return
        data=target.read_bytes(); self.send_response(200); self.send_header('Content-Type',mimetypes.guess_type(target.name)[0] or 'application/octet-stream'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        try: body=self._body(); pid=str(body.get('participant_id',''))
        except Exception as exc: self._json(400,{'error':str(exc)}); return
        try:
            if self.path=='/api/response': out=self.state.submit_response(pid,body)
            elif self.path=='/api/questionnaire': out=self.state.submit_questionnaire(pid,body)
            else: self._json(404,{'error':'not found'}); return
            self._json(200,out)
        except ValueError as exc: self._json(409,{'error':str(exc)})

def main()->int:
    p=argparse.ArgumentParser(description='Run the local, self-guided CaseGraph validation study study interface')
    p.add_argument('--run-dir',type=Path,default=ROOT/'study_runs')
    p.add_argument('--assignments',type=Path,default=ROOT/'study_runs/assignments.json')
    p.add_argument('--host',default='127.0.0.1'); p.add_argument('--port',type=int,default=8120)
    p.add_argument('--casegraph-map',type=Path,default=None,help='JSON mapping scenario_id -> real CaseGraph URL. Supplying this enables confirmatory live-product mode.')
    a=p.parse_args()
    if not a.assignments.is_file():
        print('Assignments missing. Run: python scripts/generate_validation_assignments.py',file=sys.stderr); return 1
    try:
        validate_bind_host(a.host)
    except ValueError as exc:
        print(str(exc),file=sys.stderr); return 1
    try:
        state=StudyState(a.run_dir.resolve(),a.assignments.resolve(),a.casegraph_map.resolve() if a.casegraph_map else None)
    except ValueError as exc:
        print(str(exc), file=sys.stderr); return 1
    Handler.state=state
    server=ThreadingHTTPServer((a.host,a.port),Handler)
    print(json.dumps({'status':'READY','url':f'http://{a.host}:{a.port}','run_dir':str(a.run_dir.resolve()),'privacy':'No client IP/user-agent is written to study result files.'},indent=2))
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0
if __name__=='__main__': raise SystemExit(main())
