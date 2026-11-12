import os,uuid,copy,pytest
os.environ.setdefault('CASEGRAPH_AUTH_MODE','disabled');os.environ.setdefault('PAYPAL_WEBHOOK_VERIFY','false')
from fastapi.testclient import TestClient
from backend.db.base import Base
from backend.db.session import engine
from backend.main import app
from backend.services.cases import case_service
from backend.services.evidence import evidence_service
from backend.casegraph.schema import SupportIntakeRequest,TranscriptTurnInput
from backend.ai.service import ai_reasoning_service
from backend.ai.providers.static import StaticReasoningProvider
from backend.ai.schemas import AnalyzeCaseRequest
from backend.safety.service import safety_service
from backend.actions.schemas import ActionApprovalRequest,SendMessagePayload
from backend.services.actions import action_engine
BASE={'dispute_id':'PP-D-FINAL-1','status':'WAITING_FOR_SELLER_RESPONSE','reason':'MERCHANDISE_OR_SERVICE_NOT_RECEIVED','dispute_amount':{'value':'100.00','currency_code':'USD'},'links':[{'rel':'send-message','method':'POST'},{'rel':'provide-evidence','method':'POST'}],'allowed_response_options':{},'disputed_transactions':[{'seller_transaction_id':'TX1'}]}
@pytest.fixture(autouse=True)
def clean(): Base.metadata.drop_all(engine);Base.metadata.create_all(engine);yield

def output(case_id):
    return {'summary':'Clarify without inventing facts','nodes':[{'node_id':'F1','node_type':'VERIFIED_FACT','title':'PayPal status','statement':'WAITING_FOR_SELLER_RESPONSE','source_kind':'PAYPAL_FACT','source_ref':'PF-STATUS','source_revision':1,'source_excerpt':'','confidence':-1},{'node_id':'C1','node_type':'CUSTOMER_CLAIM','title':'Claim','statement':'Package never arrived','source_kind':'EXTERNAL_EVIDENCE','source_ref':'CHAT-1','source_revision':1,'source_excerpt':'Package never arrived','confidence':-1}], 'edges':[{'edge_id':'E1','source_node_id':'C1','target_node_id':'F1','relation_type':'REFERENCES','rationale':'current case context'}], 'recommended_action':{'action_type':'SEND_MESSAGE','rationale':'ask for clarification','requires_human_approval':True,'confidence':0.99,'supporting_node_ids':['F1']},'uncertainties':[]}
@pytest.mark.asyncio
async def test_end_to_end_reasoning_safety_approval(monkeypatch):
    cid=case_service.sync_dispute_concurrency_safe(copy.deepcopy(BASE)); evidence_service.ingest_support_intake(cid,SupportIntakeRequest(intake_request_id='INTAKE-INTEGRATION-1',created_by='tester',transcript=[TranscriptTurnInput(speaker='customer',message='Package never arrived')]))
    a=await ai_reasoning_service.analyze(cid,AnalyzeCaseRequest(analysis_request_id='AIR-INTEGRATION-1',requested_by='tester'),provider=StaticReasoningProvider(output(cid))); assert a.status=='COMPLETED'
    s=safety_service.get(cid,a.analysis_uid); assert s.effective_action=='SEND_MESSAGE'
    ap=await action_engine.approve(cid,ActionApprovalRequest(action_request_id='ACTREQ-INTEGRATION-1',approved_by='tester',analysis_uid=a.analysis_uid,safety_uid=s.safety_uid,payload=SendMessagePayload(message='We are reviewing the verified case information.'))); assert ap.execution_status=='NOT_STARTED'

def test_webhook_duplicate_is_idempotent():
    body={'id':'WH-INTEGRATION-1','event_type':'CUSTOMER.DISPUTE.UPDATED','resource':{'id':'PP-D-FINAL-1'}}
    with TestClient(app) as c:
        r=c.post('/api/webhooks/paypal',json=body); assert r.status_code==200
        r2=c.post('/api/webhooks/paypal',json=body); assert r2.status_code==200 and r2.json()['status']=='ignored_duplicate'

def test_claim_cannot_forge_excerpt():
    cid=case_service.sync_dispute_concurrency_safe(copy.deepcopy(BASE)); evidence_service.ingest_support_intake(cid,SupportIntakeRequest(intake_request_id='INTAKE-INTEGRATION-2',created_by='tester',transcript=[TranscriptTurnInput(speaker='customer',message='Package never arrived')]))
    bad=output(cid); bad['nodes'][1]['source_excerpt']='I demand a refund'
    import asyncio
    a=asyncio.run(ai_reasoning_service.analyze(cid,AnalyzeCaseRequest(analysis_request_id='AIR-INTEGRATION-BAD',requested_by='tester'),provider=StaticReasoningProvider(bad))); assert a.status=='FAILED_OUTPUT'
