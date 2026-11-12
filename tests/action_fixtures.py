from __future__ import annotations
from copy import deepcopy
from backend.actions.schemas import SendMessagePayload, ActionApprovalRequest
from backend.ai.providers.static import StaticReasoningProvider
from backend.ai.schemas import AnalyzeCaseRequest
from backend.ai.service import ai_reasoning_service
from backend.casegraph.schema import SupportIntakeRequest, TranscriptTurnInput
from backend.safety.service import safety_service
from backend.services.actions import action_engine
from backend.services.cases import case_service
from backend.services.evidence import evidence_service
from backend.db.migrations import create_all
create_all()

BASE = {
    "dispute_id": "PP-D-ACT-7001",
    "status": "WAITING_FOR_SELLER_RESPONSE",
    "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
    "dispute_life_cycle_stage": "INQUIRY",
    "dispute_amount": {"value": "129.00", "currency_code": "USD"},
    "refund_details": {"allowed_refund_amount": {"value": "100.00", "currency_code": "USD"}},
    "seller_response_due_date": "2099-01-01T00:00:00Z",
    "disputed_transactions": [{"seller_transaction_id": "TX-ACT-7001", "transaction_status": "COMPLETED"}],
    "allowed_response_options": {"make_offer": {"offer_types": ["REFUND"]}, "accept_claim": {"accept_claim_types": ["REFUND", "PARTIAL_REFUND"]}},
    "links": [
        {"rel": "send-message", "method": "POST"},
        {"rel": "make-offer", "method": "POST"},
        {"rel": "accept-claim", "method": "POST"},
        {"rel": "provide-evidence", "method": "POST"},
        {"rel": "escalate", "method": "POST"},
        {"rel": "provide-supporting-info", "method": "POST"},
    ],
}

def action_output(action: str) -> dict:
    return {
        "summary": "Current PayPal state supports a human-reviewed action.",
        "nodes": [
            {"node_id": "F_STATUS", "node_type": "VERIFIED_FACT", "title": "PayPal dispute status", "statement": "WAITING_FOR_SELLER_RESPONSE", "source_kind": "PAYPAL_FACT", "source_ref": "PF-STATUS", "source_revision": 1, "source_excerpt": "", "confidence": -1},
            {"node_id": "A_ACTION", "node_type": "ACTION", "title": "Human-reviewed action", "statement": "Human may take the action after deterministic validation.", "source_kind": "NONE", "source_ref": "", "source_revision": 0, "source_excerpt": "", "confidence": -1},
        ],
        "edges": [{"edge_id": "E_REF", "source_node_id": "A_ACTION", "target_node_id": "F_STATUS", "relation_type": "REFERENCES", "rationale": "The action is grounded in current PayPal state."}],
        "recommended_action": {"action_type": action, "rationale": "Grounded in current state.", "requires_human_approval": True, "confidence": 0.99, "supporting_node_ids": ["F_STATUS"]},
        "uncertainties": [],
    }

def send_message_payload() -> SendMessagePayload:
    return SendMessagePayload(message="We are reviewing the verified case information and will update you here.")

async def prepare(case_payload: dict, action: str, payload, *, suffix: str = "1"):
    case_payload = deepcopy(case_payload)
    case_id = case_service.sync_dispute_concurrency_safe(case_payload)
    evidence_service.ingest_support_intake(case_id, SupportIntakeRequest(intake_request_id=f"INTAKE-{suffix}", created_by="test", transcript=[TranscriptTurnInput(speaker="customer", message="Package never arrived")]))
    analysis = await ai_reasoning_service.analyze(case_id, AnalyzeCaseRequest(analysis_request_id=f"AIR-ACTION-{suffix}-{action}", requested_by="test"), provider=StaticReasoningProvider(action_output(action)))
    safety = safety_service.get(case_id, analysis.analysis_uid)
    approval = await action_engine.approve(case_id, ActionApprovalRequest(action_request_id=f"ACTREQ-ACTION-{suffix}-{action}", approved_by="human-reviewer", analysis_uid=analysis.analysis_uid, safety_uid=safety.safety_uid, payload=payload))
    return case_id, analysis, safety, approval
