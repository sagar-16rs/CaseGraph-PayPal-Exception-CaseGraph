from __future__ import annotations
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from validation.io import load_jsonl
from validation.scoring import score_response,build_report,classify_primary_gate

def test_perfect_response_scores_success():
    g=load_jsonl(ROOT/'data/validation/gold.jsonl')[0]
    r={'participant_id':'P001','scenario_id':g['scenario_id'],'pair_id':g['pair_id'],'variant':g['variant'],'condition':'casegraph','block':1,'diagnosis_id':g['diagnosis_id'],'action_id':g['safe_action_ids'][0],'selected_sources':g['required_source_ids'],'selected_contradictions':g['required_contradiction_ids'],'established_statement_ids':g['established_statement_ids'],'confidence':100,'elapsed_seconds':60}
    s=score_response(r,g)
    assert s['strict_success']==1 and s['unsafe_action']==0 and s['source_recall']==1 and s['established_statement_recall']==1

def test_unsafe_action_vetoes_success():
    g=next(x for x in load_jsonl(ROOT/'data/validation/gold.jsonl') if x.get('unsafe_action_ids'))
    r={'participant_id':'P001','scenario_id':g['scenario_id'],'pair_id':g['pair_id'],'variant':g['variant'],'condition':'casegraph','block':1,'diagnosis_id':g['diagnosis_id'],'action_id':g['unsafe_action_ids'][0],'selected_sources':g['required_source_ids'],'selected_contradictions':g['required_contradiction_ids'],'established_statement_ids':g['established_statement_ids'],'confidence':100,'elapsed_seconds':60}
    s=score_response(r,g);assert s['diagnosis_correct']==1 and s['unsafe_action']==1 and s['strict_success']==0

def test_report_clusters_by_participant():
    scored=[]
    for i in range(8):
        pid=f'P{i+1:03d}'
        for cond,val in [('baseline',0),('casegraph',1)]:
            for j in range(5): scored.append({'participant_id':pid,'scenario_id':f'S{j}','pair_id':f'P{j}','variant':'A','condition':cond,'block':1,'diagnosis_correct':val,'action_correct':val,'unsafe_action':0,'strict_success':val,'source_recall':val,'source_precision':1,'contradiction_recall':val,'established_statement_recall':val,'false_established_statement_count':0,'brier':0,'overconfident_failure':0,'elapsed_seconds':100 if cond=='baseline' else 80,'suspicious_fast':0})
    rep=build_report(scored,[])
    assert rep['complete_paired_participant_count']==8
    assert rep['metrics']['strict_success']['paired_improvement_mean']==1
    assert rep['primary_gate']=='EVIDENCE_OF_IMPROVEMENT'

def test_safety_regression_overrides_primary_gain():
    assert classify_primary_gate({'n_complete_participants':10,'paired_improvement_mean':0.2,'paired_improvement_ci95':[0.1,0.3]},{'paired_improvement_mean':-0.1})=='SAFETY_REGRESSION'

def test_incomplete_participant_is_not_counted_as_complete():
    scored=[]
    for cond in ('baseline','casegraph'):
        scored.append({'participant_id':'P001','scenario_id':'S1','pair_id':'P1','variant':'A','condition':cond,'block':1,'diagnosis_correct':1,'action_correct':1,'unsafe_action':0,'strict_success':1,'source_recall':1,'source_precision':1,'contradiction_recall':1,'established_statement_recall':1,'false_established_statement_count':0,'brier':0,'overconfident_failure':0,'elapsed_seconds':50,'suspicious_fast':0})
    rep=build_report(scored,[])
    assert rep['complete_paired_participant_count']==0
    assert rep['primary_gate']=='INSUFFICIENT_SAMPLE'
