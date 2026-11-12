from __future__ import annotations

import copy
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.ai.providers.static import StaticReasoningProvider
from backend.ai.schemas import AnalyzeCaseRequest
from backend.ai.service import AIRequestConflict, ai_reasoning_service
from backend.casegraph.schema import SupportIntakeRequest, TranscriptTurnInput
from backend.db.base import Base
from backend.db.models import AISafetyAssessment, PayPalEvent
from backend.db.session import engine, session_scope
from backend.main import app
from backend.repositories import events as event_repo
from backend.repositories import work_items as work_repo
from backend.safety.service import SafetyIntegrityError, safety_service
from backend.services.cases import case_service
from backend.services.evidence import evidence_service


BASE = {
    "dispute_id": "PP-D-FINAL-ADV-1",
    "status": "WAITING_FOR_SELLER_RESPONSE",
    "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
    "dispute_life_cycle_stage": "INQUIRY",
    "dispute_amount": {"value": "100.00", "currency_code": "USD"},
    "allowed_response_options": {
        "make_offer": {"offer_types": ["REFUND"]},
        "accept_claim": {"accept_claim_types": ["REFUND"]},
    },
    "disputed_transactions": [{"seller_transaction_id": "TX-FINAL-ADV-1"}],
    "links": [
        {"rel": "self", "method": "GET"},
        {"rel": "send-message", "method": "POST"},
    ],
}


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


def intake(case_id: str, request_id: str = "INTAKE-ADV-0001", message: str = "Package never arrived"):
    return evidence_service.ingest_support_intake(
        case_id,
        SupportIntakeRequest(
            intake_request_id=request_id,
            created_by="tester",
            transcript=[TranscriptTurnInput(speaker="customer", message=message)],
        ),
    )


def good_output(*, action: str = "SEND_MESSAGE", support: list[str] | None = None) -> dict:
    return {
        "summary": "Use only the authoritative PayPal state and exact customer statement.",
        "nodes": [
            {
                "node_id": "F_STATUS",
                "node_type": "VERIFIED_FACT",
                "title": "PayPal dispute status",
                "statement": "WAITING_FOR_SELLER_RESPONSE",
                "source_kind": "PAYPAL_FACT",
                "source_ref": "PF-STATUS",
                "source_revision": 1,
                "source_excerpt": "",
                "confidence": -1,
            },
            {
                "node_id": "C_CUSTOMER",
                "node_type": "CUSTOMER_CLAIM",
                "title": "Customer says package is missing",
                "statement": "Customer reports non-delivery.",
                "source_kind": "EXTERNAL_EVIDENCE",
                "source_ref": "CHAT-1",
                "source_revision": 1,
                "source_excerpt": "Package never arrived",
                "confidence": -1,
            },
        ],
        "edges": [
            {
                "edge_id": "E_REF",
                "source_node_id": "C_CUSTOMER",
                "target_node_id": "F_STATUS",
                "relation_type": "REFERENCES",
                "rationale": "The claim is evaluated in the current dispute context.",
            }
        ],
        "recommended_action": {
            "action_type": action,
            "rationale": "Ask for clarification without moving money.",
            "requires_human_approval": True,
            "confidence": 0.99,
            "supporting_node_ids": support if support is not None else (["F_STATUS"] if action != "NONE" else []),
        },
        "uncertainties": [],
    }


@pytest.mark.asyncio
async def test_verified_fact_laundering_is_rejected():
    case_id = case_service.sync_dispute_concurrency_safe(copy.deepcopy(BASE))
    intake(case_id)
    output = good_output()
    output["nodes"][0]["statement"] = "PayPal already refunded the customer"
    analysis = await ai_reasoning_service.analyze(
        case_id,
        AnalyzeCaseRequest(analysis_request_id="AIR-ADV-FACT-1", requested_by="tester"),
        provider=StaticReasoningProvider(output),
    )
    assert analysis.status == "FAILED_OUTPUT"
    assert analysis.graph_id is None


@pytest.mark.asyncio
async def test_claim_speaker_laundering_is_rejected():
    case_id = case_service.sync_dispute_concurrency_safe(copy.deepcopy(BASE))
    intake(case_id)
    output = good_output()
    output["nodes"][1]["node_type"] = "MERCHANT_CLAIM"
    analysis = await ai_reasoning_service.analyze(
        case_id,
        AnalyzeCaseRequest(analysis_request_id="AIR-ADV-SPEAKER-1", requested_by="tester"),
        provider=StaticReasoningProvider(output),
    )
    assert analysis.status == "FAILED_OUTPUT"


@pytest.mark.asyncio
async def test_model_result_becomes_stale_if_evidence_changes_during_provider_call():
    case_id = case_service.sync_dispute_concurrency_safe(copy.deepcopy(BASE))
    intake(case_id)

    class MutatingProvider(StaticReasoningProvider):
        async def run(self, bundle):
            evidence_service.ingest_support_intake(
                case_id,
                SupportIntakeRequest(
                    intake_request_id="INTAKE-ADV-STALE-2",
                    created_by="concurrent-user",
                    transcript=[TranscriptTurnInput(speaker="customer", message="New evidence arrived")],
                ),
            )
            return await super().run(bundle)

    analysis = await ai_reasoning_service.analyze(
        case_id,
        AnalyzeCaseRequest(analysis_request_id="AIR-ADV-STALE-1", requested_by="tester"),
        provider=MutatingProvider(good_output()),
    )
    assert analysis.status == "STALE_INPUT"
    assert analysis.graph_id is None


@pytest.mark.asyncio
async def test_request_id_reuse_after_input_change_is_conflict():
    case_id = case_service.sync_dispute_concurrency_safe(copy.deepcopy(BASE))
    intake(case_id)
    request = AnalyzeCaseRequest(analysis_request_id="AIR-ADV-IDEMP-1", requested_by="tester")
    first = await ai_reasoning_service.analyze(case_id, request, provider=StaticReasoningProvider(good_output()))
    assert first.status == "COMPLETED"
    evidence_service.ingest_support_intake(
        case_id,
        SupportIntakeRequest(
            intake_request_id="INTAKE-ADV-IDEMP-2",
            created_by="tester",
            transcript=[TranscriptTurnInput(speaker="customer", message="I found the parcel later")],
        ),
    )
    with pytest.raises(AIRequestConflict):
        await ai_reasoning_service.analyze(case_id, request, provider=StaticReasoningProvider(good_output()))


@pytest.mark.asyncio
async def test_ungrounded_inference_blocks_action():
    case_id = case_service.sync_dispute_concurrency_safe(copy.deepcopy(BASE))
    intake(case_id)
    output = good_output(support=["I_UNGROUNDED"])
    output["nodes"].append(
        {
            "node_id": "I_UNGROUNDED",
            "node_type": "AI_INFERENCE",
            "title": "Unsupported inference",
            "statement": "The merchant probably already refunded the buyer.",
            "source_kind": "NONE",
            "source_ref": "",
            "source_revision": 0,
            "source_excerpt": "",
            "confidence": 0.95,
        }
    )
    analysis = await ai_reasoning_service.analyze(
        case_id,
        AnalyzeCaseRequest(analysis_request_id="AIR-ADV-GROUND-1", requested_by="tester"),
        provider=StaticReasoningProvider(output),
    )
    assert analysis.status == "COMPLETED"
    safety = safety_service.get(case_id, analysis.analysis_uid)
    assert safety.safety_status.value == "BLOCKED"
    assert safety.effective_action == "NONE"
    assert "UNGROUNDED_AI_INFERENCE" in safety.report["action_result"]["finding_codes"]


@pytest.mark.asyncio
async def test_safety_record_tampering_is_detected():
    case_id = case_service.sync_dispute_concurrency_safe(copy.deepcopy(BASE))
    intake(case_id)
    analysis = await ai_reasoning_service.analyze(
        case_id,
        AnalyzeCaseRequest(analysis_request_id="AIR-ADV-SAFE-1", requested_by="tester"),
        provider=StaticReasoningProvider(good_output()),
    )
    safety = safety_service.get(case_id, analysis.analysis_uid)
    with session_scope() as session:
        row = session.query(AISafetyAssessment).filter_by(safety_uid=safety.safety_uid).one()
        row.report_json = {"tampered": True}
    with pytest.raises(SafetyIntegrityError):
        safety_service.get(case_id, analysis.analysis_uid)


def test_evidence_sets_are_cumulative_not_destructive():
    case_id = case_service.sync_dispute_concurrency_safe(copy.deepcopy(BASE))
    first = intake(case_id, "INTAKE-ADV-CUMUL-1", "First customer statement")
    second = intake(case_id, "INTAKE-ADV-CUMUL-2", "Second customer statement")
    assert first["revision"] == 1
    assert second["revision"] == 2
    assert [item["evidence"]["content"] for item in second["members"]] == [
        "First customer statement",
        "Second customer statement",
    ]
    assert len({item["evidence"]["source_ref"] for item in second["members"]}) == 2


def test_only_hateoas_links_create_available_actions():
    payload = copy.deepcopy(BASE)
    payload["links"] = [{"rel": "self", "method": "GET"}, {"rel": "send-message", "method": "POST"}]
    payload["allowed_response_options"] = {"make_offer": {"offer_types": ["REFUND"]}}
    case_id = case_service.sync_dispute_concurrency_safe(payload)
    detail = case_service.detail(case_id)
    assert detail is not None
    assert detail["allowed_response_options"] == ["SEND_MESSAGE"]
    assert "SELF" not in detail["allowed_response_options"]
    assert "MAKE_OFFER" not in detail["allowed_response_options"]


def test_duplicate_webhook_repairs_missing_work_row_before_ack():
    body = {
        "id": "WH-ADV-REPAIR-1",
        "event_type": "CUSTOMER.DISPUTE.UPDATED",
        "resource": {"id": "PP-D-FINAL-ADV-1"},
    }
    with session_scope() as session:
        event_repo.add(
            session,
            PayPalEvent(
                event_id=body["id"],
                event_type=body["event_type"],
                resource_id=body["resource"]["id"],
                payload=body,
            ),
        )
    client = TestClient(app)
    response = client.post("/api/webhooks/paypal", json=body)
    assert response.status_code == 200
    assert response.json()["status"] == "ignored_duplicate"
    with session_scope() as session:
        work = work_repo.get_for_source(
            session,
            source_type="PAYPAL_EVENT",
            source_id=body["id"],
            work_type="PAYPAL_DISPUTE_WEBHOOK",
        )
        assert work is not None


def test_doctor_is_read_only_in_production(tmp_path):
    db_path = tmp_path / "production_doctor.db"
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
        "CASEGRAPH_ENV": "production",
        "CASEGRAPH_AUTH_MODE": "enforce",
        "CASEGRAPH_TENANT_ID": "tenant-test",
        "CASEGRAPH_AUTH_ISSUER": "https://issuer.example",
        "CASEGRAPH_AUTH_AUDIENCE": "casegraph",
        "CASEGRAPH_AUTH_PUBLIC_KEY_PEM": "test-public-key-placeholder",
        "CASEGRAPH_RATE_LIMIT_BACKEND": "redis",
        "CASEGRAPH_REDIS_URL": "redis://:test-password@127.0.0.1:6379/0",
        "CASEGRAPH_ALLOWED_ORIGINS": "https://casegraph.example",
        "CASEGRAPH_UPLOAD_SCANNER": "clamav",
        "CASEGRAPH_UPLOAD_ALLOW_UNSCANNED_DEV": "false",
        "PAYPAL_BASE_URL": "https://api-m.sandbox.paypal.com",
        "PAYPAL_CLIENT_ID": "sandbox-client",
        "PAYPAL_CLIENT_SECRET": "sandbox-secret",
        "PAYPAL_WEBHOOK_VERIFY": "true",
        "PAYPAL_WEBHOOK_ID": "WH-TEST",
        "OPENAI_API_KEY": "test-key",
    })
    result = subprocess.run(
        [sys.executable, "scripts/doctor.py"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    # SQLite is intentionally invalid for production, so the doctor must fail.
    assert result.returncode == 1
    # The diagnostic may open/create the SQLite file, but production doctor must
    # never create application tables or otherwise migrate the schema.
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not tables

@pytest.mark.asyncio
async def test_exact_analysis_request_replay_does_not_call_provider_twice():
    case_id = case_service.sync_dispute_concurrency_safe(copy.deepcopy(BASE))
    intake(case_id, "INTAKE-ADV-IDEMP-1")

    class CountingProvider(StaticReasoningProvider):
        def __init__(self, output):
            super().__init__(output)
            self.calls = 0

        async def run(self, bundle):
            self.calls += 1
            return await super().run(bundle)

    provider = CountingProvider(good_output())
    req = AnalyzeCaseRequest(analysis_request_id="AIR-ADV-IDEMP-1", requested_by="tester")
    first = await ai_reasoning_service.analyze(case_id, req, provider=provider)
    second = await ai_reasoning_service.analyze(case_id, req, provider=provider)
    assert first.analysis_uid == second.analysis_uid
    assert first.status == second.status == "COMPLETED"
    assert provider.calls == 1
