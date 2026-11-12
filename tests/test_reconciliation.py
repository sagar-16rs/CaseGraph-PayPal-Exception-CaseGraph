"""Reconciliation must be executable, not merely documented.

Before this suite existed, `backend/work/reconciliation.py` referenced ORM
columns and enum members that did not exist (`resulting_execution_status`,
`details_json`, `record_hash`, `ReconciliationMethod.AUTO_PAYPAL_STATE`,
`ReconciliationOutcome.INCONCLUSIVE`). Every call raised `AttributeError` or
`TypeError`, so an action left in `UNKNOWN_OUTCOME` could never be resolved and
its case stayed permanently blocked from further PayPal writes.

These tests drive the real service against the real database.
"""

from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi import HTTPException

from backend.actions.schemas import ActionExecuteRequest
from backend.db.base import Base
from backend.db.session import engine, session_scope
from backend.repositories import action_approvals as approval_repo
from backend.services.actions import _mark_result, action_engine
from backend.work.domain import ReconciliationMethod, ReconciliationOutcome
from backend.work.reconciliation import reconciliation_service
from backend.work.schemas import ManualReconciliationRequest
from tests.action_fixtures import BASE, prepare, send_message_payload


@pytest.fixture(autouse=True)
def _clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


async def _approval_in_status(status: str, *, suffix: str):
    case_id, _analysis, _safety, approval = await prepare(
        deepcopy(BASE), "SEND_MESSAGE", send_message_payload(), suffix=suffix
    )
    with session_scope() as session:
        row = approval_repo.get_by_uid(session, approval.action_uid, for_update=True)
        assert row is not None
        row.execution_status = status
    return case_id, approval


@pytest.mark.asyncio
async def test_auto_reconciliation_records_an_inconclusive_probe_without_clearing_the_block(monkeypatch):
    case_id, approval = await _approval_in_status("UNKNOWN_OUTCOME", suffix="RECON-AUTO")

    async def get_details(_dispute_id: str):
        return deepcopy(BASE)

    monkeypatch.setattr(
        "backend.work.reconciliation.disputes_client.get_dispute_details", get_details
    )

    record = await reconciliation_service.auto(case_id, approval.action_uid)

    assert record.outcome == ReconciliationOutcome.INCONCLUSIVE.value
    assert record.method == ReconciliationMethod.AUTO_PAYPAL_STATE.value
    # A GET that shows no effect is not proof the POST failed.
    assert record.execution_status == "UNKNOWN_OUTCOME"
    assert record.observed_snapshot_hash

    with session_scope() as session:
        row = approval_repo.get_by_uid(session, approval.action_uid)
        assert row is not None
        assert row.execution_status == "UNKNOWN_OUTCOME"


@pytest.mark.asyncio
async def test_auto_reconciliation_clears_sync_pending_on_an_executed_action(monkeypatch):
    case_id, approval = await _approval_in_status("PENDING", suffix="RECON-SYNC")
    _mark_result(
        approval.action_uid,
        status="EXECUTED",
        response_status=204,
        response_body={},
        event_type="ACTION_EXECUTED",
    )

    async def get_details(_dispute_id: str):
        return deepcopy(BASE)

    monkeypatch.setattr(
        "backend.work.reconciliation.disputes_client.get_dispute_details", get_details
    )

    record = await reconciliation_service.auto(case_id, approval.action_uid)
    assert record.outcome == ReconciliationOutcome.CONFIRMED_EXECUTED.value
    assert record.execution_status == "EXECUTED"

    with session_scope() as session:
        row = approval_repo.get_by_uid(session, approval.action_uid)
        assert row is not None
        assert row.post_action_sync_pending is False


@pytest.mark.asyncio
async def test_manual_reconciliation_requires_explicit_dashboard_confirmation():
    case_id, approval = await _approval_in_status("UNKNOWN_OUTCOME", suffix="RECON-MANUAL-GATE")
    request = ManualReconciliationRequest(
        decision="CONFIRMED_NOT_EXECUTED",
        confirmed_from_paypal_dashboard=False,
        confirmed_by="analyst@example.com",
        note="Checked PayPal dashboard",
    )
    with pytest.raises(HTTPException) as excinfo:
        await reconciliation_service.manual(case_id, approval.action_uid, request)
    assert excinfo.value.status_code == 422

    with session_scope() as session:
        row = approval_repo.get_by_uid(session, approval.action_uid)
        assert row is not None
        assert row.execution_status == "UNKNOWN_OUTCOME"


@pytest.mark.asyncio
async def test_manual_reconciliation_can_release_an_ambiguous_write_as_not_executed():
    case_id, approval = await _approval_in_status("UNKNOWN_OUTCOME", suffix="RECON-MANUAL-RELEASE")
    request = ManualReconciliationRequest(
        decision="CONFIRMED_NOT_EXECUTED",
        confirmed_from_paypal_dashboard=True,
        confirmed_by="analyst@example.com",
        note="PayPal dashboard shows no message was sent",
    )
    record = await reconciliation_service.manual(case_id, approval.action_uid, request)

    assert record.outcome == ReconciliationOutcome.CONFIRMED_NOT_EXECUTED.value
    assert record.method == ReconciliationMethod.MANUAL_PAYPAL_DASHBOARD.value
    assert record.execution_status == "FAILED"
    assert record.reconciled_by == "analyst@example.com"

    with session_scope() as session:
        row = approval_repo.get_by_uid(session, approval.action_uid)
        assert row is not None
        assert row.execution_status == "FAILED"
        assert row.post_action_sync_pending is False

    # The case is no longer blocked: a fresh approval may be created.
    case_id2, _analysis, _safety, fresh = await prepare(
        deepcopy(BASE), "SEND_MESSAGE", send_message_payload(), suffix="RECON-MANUAL-NEXT"
    )
    assert fresh.execution_status == "NOT_STARTED"


@pytest.mark.asyncio
async def test_reconciliation_history_is_listed_and_integrity_checked():
    case_id, approval = await _approval_in_status("UNKNOWN_OUTCOME", suffix="RECON-HISTORY")
    await reconciliation_service.manual(
        case_id,
        approval.action_uid,
        ManualReconciliationRequest(
            decision="CONFIRMED_NOT_EXECUTED",
            confirmed_from_paypal_dashboard=True,
            confirmed_by="analyst@example.com",
            note="Verified in PayPal dashboard",
        ),
    )
    records = reconciliation_service.list(case_id, approval.action_uid)
    assert len(records) == 1
    assert records[0].details["confirmed_from_paypal_dashboard"] is True
    assert records[0].details["previous_status"] == "UNKNOWN_OUTCOME"


@pytest.mark.asyncio
async def test_execute_refuses_an_unresolved_write_before_any_network_call(monkeypatch):
    """The block is enforced at the execution boundary too, not only in the UI."""
    case_id, approval = await _approval_in_status("UNKNOWN_OUTCOME", suffix="RECON-EXEC-GATE")

    called = {"get": 0}

    async def get_details(_dispute_id: str):
        called["get"] += 1
        return deepcopy(BASE)

    monkeypatch.setattr(
        "backend.services.actions.disputes_client.get_dispute_details", get_details
    )

    with pytest.raises(HTTPException) as excinfo:
        await action_engine.execute(
            case_id,
            approval.action_uid,
            ActionExecuteRequest(approval_hash=approval.approval_hash),
        )
    assert excinfo.value.status_code == 409
    assert called["get"] == 0
