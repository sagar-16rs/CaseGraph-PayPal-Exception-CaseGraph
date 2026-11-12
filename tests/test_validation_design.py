from __future__ import annotations
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from validation.design import build_assignments,validate_assignment_balance
from validation.io import load_jsonl

def test_assignment_is_counterbalanced():
    a=build_assignments(load_jsonl(ROOT/'data/validation/scenarios.jsonl'),participant_count=10,seed=20261025)
    b=validate_assignment_balance(a)
    assert b['sequence_counts']=={'baseline->casegraph':5,'casegraph->baseline':5}
    for counts in b['pair_condition_counts'].values(): assert counts['baseline']==5 and counts['casegraph']==5
    for p in a['assignments']:
        assert len(p['tasks'])==10
        assert sum(t['condition']=='baseline' for t in p['tasks'])==5
        assert sum(t['condition']=='casegraph' for t in p['tasks'])==5
        assert sum(t['variant']=='A' for t in p['tasks'])==5
        assert sum(t['variant']=='B' for t in p['tasks'])==5

def test_gold_not_mixed_into_scenarios():
    scenarios=load_jsonl(ROOT/'data/validation/scenarios.jsonl')
    forbidden={'diagnosis_id','safe_action_ids','unsafe_action_ids','required_source_ids','established_statement_ids'}
    assert all(not (forbidden & set(s)) for s in scenarios)

def test_every_even_sample_balances_variants_and_conditions():
    scenarios=load_jsonl(ROOT/'data/validation/scenarios.jsonl')
    for n in (2,4,6,10,12):
        a=build_assignments(scenarios,participant_count=n,seed=99+n)
        b=validate_assignment_balance(a)
        for counts in b['pair_condition_counts'].values(): assert counts['baseline']==counts['casegraph']
        for counts in b['pair_variant_counts'].values(): assert counts['A']==counts['B']

def test_validation_python_has_no_production_write_or_model_adapter_imports():
    roots=[ROOT/'validation',ROOT/'scripts']
    forbidden=['action_engine','backend.paypal.disputes','disputes_client','OpenAI','openai import']
    violations=[]
    for base in roots:
        for path in base.glob('validation*.py') if base.name=='scripts' else base.glob('*.py'):
            text=path.read_text(encoding='utf-8')
            for needle in forbidden:
                if needle in text: violations.append((str(path.relative_to(ROOT)),needle))
    assert not violations


def test_verified_fact_nodes_are_paypal_only_in_scenarios_and_practice():
    rows=load_jsonl(ROOT/'data/validation/scenarios.jsonl')+load_jsonl(ROOT/'data/validation/practice.jsonl')
    bad=[]
    for item in rows:
        for node in item.get('casegraph',{}).get('nodes',[]):
            if node.get('type')=='VERIFIED_FACT' and not str(node.get('source_id','')).startswith('PP'):
                bad.append((item.get('scenario_id'),node.get('id'),node.get('source_id')))
    assert not bad
