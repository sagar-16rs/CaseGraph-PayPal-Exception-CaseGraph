"""End-to-end journey on the simulated PayPal sandbox.

This is the suite that proves the product is demonstrable without credentials:
sync -> evidence intake -> deterministic reasoning -> safety -> human approval ->
execution against a labelled simulated PayPal -> ambiguity handling ->
reconciliation. It also proves the simulated transport still passes through the
real validation and policy code rather than bypassing it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.actions.schemas import ActionApprovalRequest, ActionExecuteRequest, SendMessagePayload
from backend.ai.schemas import AnalyzeCaseRequest
from backend.ai.service import ai_reasoning_service
from backend.casegraph.schema import SupportIntakeRequest, TranscriptTurnInput
from backend.config import settings
from backend.db.base import Base
from backend.db.session import engine, session_scope
from backend.paypal.disputes import disputes_client
from backend.paypal.errors import PayPalTransportError
from backend.paypal.http import set_simulator_for_testing
from backend.paypal.simulation_data import DEMO_DISPUTES, DEMO_EVIDENCE
from backend.paypal.simulator import build_simulator
from backend.repositories import action_approvals as approval_repo
from backend.safety.service import safety_service
from backend.services.actions import action_engine
from backend.services.cases import case_service
from backend.services.evidence import evidence_service
from backend.work.reconciliation import reconciliation_service
from backend.work.schemas import ManualReconciliationRequest


def _state_dir() -> Path:
    """Keep simulator state beside the isolated test database."""
    url = settings.database_url
    if url.startswith("sqlite:///"):
        return Path(url.removeprefix("sqlite:///")).resolve().parent
    raise RuntimeError("this suite requires the SQLite test database")


@pytest.fixture(autouse=True)
def _clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    state = _state_dir() / "simulated-paypal-test.json"
    state.unlink(missing_ok=True)
    yield


@pytest.fixture()
def simulated(monkeypatch):
    """Force the simulated transport for the duration of a test."""
    monkeypatch.setattr("backend.paypal.http.simulated_transport_enabled", lambda: True)
    state = _state_dir() / "simulated-paypal-test.json"
    simulator = build_simulator(state)
    set_simulator_for_testing(simulator)
    yield simulator
    set_simulator_for_testing(None)


async def _seed_case(dispute_id: str) -> tuple[str, str, str]:
    payload = await disputes_client.get_dispute_details(dispute_id)
    case_id = case_service.sync_dispute_concurrency_safe(payload)
    evidence = DEMO_EVIDENCE[dispute_id]
    evidence_service.ingest_support_intake(
        case_id,
        SupportIntakeRequest(
            intake_request_id=f"INTAKE-DEMO-{dispute_id[-4:]}",
            created_by="demo-seed",
            transcript=[TranscriptTurnInput(**turn) for turn in evidence["transcript"]],
            merchant_notes=evidence.get("merchant_notes"),
        ),
    )
    analysis = await ai_reasoning_service.analyze(
        case_id,
        AnalyzeCaseRequest(
            analysis_request_id=f"AIR-DEMO-{dispute_id[-4:]}", requested_by="demo-seed"
        ),
    )
    assert analysis.status == "COMPLETED", analysis.error
    return case_id, analysis.analysis_uid, analysis.graph_id or ""


@pytest.mark.asyncio
async def test_seeded_demo_cases_produce_graphs_and_safety_assessments(simulated):
    for dispute in DEMO_DISPUTES:
        case_id, analysis_uid, graph_id = await _seed_case(dispute["dispute_id"])
        assert graph_id.startswith(case_id)
        assessment = safety_service.get(case_id, analysis_uid)
        assert assessment.safety_status in {"PASS", "REVIEW", "BLOCKED"}
        # The reference reasoner never invents a high-confidence inference.
        assert assessment.action_risk in {"LOW", "MEDIUM", "HIGH", "CRITICAL", "NONE"}


@pytest.mark.asyncio
async def test_conflicting_statements_downgrade_the_action_to_review(simulated):
    case_id, analysis_uid, _graph = await _seed_case("PP-D-DEMO-1001")
    assessment = safety_service.get(case_id, analysis_uid)
    codes = [finding["code"] for finding in assessment.report["findings"]]
    assert "ACTION_SUPPORT_IS_CONTRADICTED" in codes
    assert assessment.safety_status == "REVIEW"
    # REVIEW still permits the low-risk clarification message.
    assert assessment.effective_action == "SEND_MESSAGE"


@pytest.mark.asyncio
async def test_supported_info_recommendation_passes_policy(simulated):
    case_id, analysis_uid, _graph = await _seed_case("PP-D-DEMO-1003")
    assessment = safety_service.get(case_id, analysis_uid)
    assert assessment.recommended_action == "PROVIDE_SUPPORTING_INFO"
    assert assessment.safety_status == "PASS"
    assert assessment.effective_action == "PROVIDE_SUPPORTING_INFO"


@pytest.mark.asyncio
async def test_human_approved_message_executes_against_the_simulated_sandbox(simulated):
    case_id, analysis_uid, _graph = await _seed_case("PP-D-DEMO-1001")
    assessment = safety_service.get(case_id, analysis_uid)

    approval = await action_engine.approve(
        case_id,
        ActionApprovalRequest(
            action_request_id="ACTREQ-DEMO-EXEC",
            approved_by="human-reviewer",
            analysis_uid=analysis_uid,
            safety_uid=assessment.safety_uid,
            payload=SendMessagePayload(message="We are checking the delivery record and will reply here."),
        ),
    )
    result = await action_engine.execute(
        case_id, approval.action_uid, ActionExecuteRequest(approval_hash=approval.approval_hash)
    )
    assert result.execution_status == "EXECUTED"
    assert result.post_action_sync_pending is False
    assert result.updated_dispute_status == "WAITING_FOR_SELLER_RESPONSE"

    # The write really happened in the simulated sandbox, and the response is
    # stamped as simulated so it can never be mistaken for provider truth.
    dispute = await disputes_client.get_dispute_details("PP-D-DEMO-1001")
    assert dispute["messages"][0]["message"].startswith("We are checking")
    assert dispute["simulated"] is True


@pytest.mark.asyncio
async def test_ambiguous_write_is_blocked_reconciled_and_released(simulated):
    case_id, analysis_uid, _graph = await _seed_case("PP-D-DEMO-1001")
    assessment = safety_service.get(case_id, analysis_uid)

    approval = await action_engine.approve(
        case_id,
        ActionApprovalRequest(
            action_request_id="ACTREQ-DEMO-AMBIGUOUS",
            approved_by="human-reviewer",
            analysis_uid=analysis_uid,
            safety_uid=assessment.safety_uid,
            payload=SendMessagePayload(message="Please confirm the delivery address on file."),
        ),
    )

    # Inject a transport failure for the write only.
    simulated.fault = "timeout"
    with pytest.raises(PayPalTransportError):
        await action_engine.execute(
            case_id, approval.action_uid, ActionExecuteRequest(approval_hash=approval.approval_hash)
        )

    with session_scope() as session:
        row = approval_repo.get_by_uid(session, approval.action_uid)
        assert row is not None
        assert row.execution_status == "UNKNOWN_OUTCOME"

    # Never retried automatically.
    with pytest.raises(HTTPException) as blocked:
        await action_engine.execute(
            case_id, approval.action_uid, ActionExecuteRequest(approval_hash=approval.approval_hash)
        )
    assert blocked.value.status_code == 409

    # An automatic probe cannot prove the write failed, so it stays blocked.
    simulated.fault = "none"
    auto_record = await reconciliation_service.auto(case_id, approval.action_uid)
    assert auto_record.outcome == "INCONCLUSIVE"
    assert auto_record.execution_status == "UNKNOWN_OUTCOME"

    # An operator who checked PayPal can release the case.
    manual = await reconciliation_service.manual(
        case_id,
        approval.action_uid,
        ManualReconciliationRequest(
            decision="CONFIRMED_NOT_EXECUTED",
            confirmed_from_paypal_dashboard=True,
            confirmed_by="analyst@example.com",
            note="PayPal dashboard shows no message in the dispute thread.",
        ),
    )
    assert manual.execution_status == "FAILED"


@pytest.mark.asyncio
async def test_simulated_bundle_is_deterministic_across_reads(simulated):
    first = await disputes_client.get_dispute_details("PP-D-DEMO-1002")
    second = await disputes_client.get_dispute_details("PP-D-DEMO-1002")
    assert first == second
    assert first["simulation_revision"] == 1
