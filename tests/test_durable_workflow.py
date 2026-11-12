from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from backend.actions.schemas import ActionExecuteRequest
from backend.db.models import WorkItem
from backend.db.session import session_scope
from backend.main import app
from backend.repositories import action_approvals as approval_repo
from backend.repositories import work_items as work_repo
from backend.services.actions import _mark_result, action_engine
from backend.work.dispute_lock import advisory_key
from backend.work.service import utcnow, work_service
from tests.action_fixtures import BASE, prepare, send_message_payload


def test_durable_work_manual_reconciliation_is_not_public_http_api():
    paths = app.openapi()["paths"]
    assert "/api/cases/{case_id}/actions/{action_uid}/reconcile" in paths
    assert "/api/cases/{case_id}/actions/{action_uid}/reconcile/manual" not in paths


def test_durable_work_advisory_lock_key_is_stable_signed_int64():
    first = advisory_key("PP-D-DURABLE_WORK-1")
    assert first == advisory_key("PP-D-DURABLE_WORK-1")
    assert first != advisory_key("PP-D-DURABLE_WORK-2")
    assert -(2**63) <= first < 2**63


def test_durable_work_postgres_guard_uses_nonblocking_session_advisory_lock():
    source = Path("backend/work/dispute_lock.py").read_text(encoding="utf-8")
    assert "pg_try_advisory_lock" in source
    assert "pg_advisory_unlock" in source
    assert "conn.commit()" in source
    assert "session-level advisory lock" in source




def test_durable_work_lock_wait_is_bounded_by_worker_lease_budget():
    source = Path("backend/work/dispute_lock.py").read_text(encoding="utf-8")
    assert "worker_lease_seconds" in source
    assert "paypal_timeout_seconds" in source
    assert "min(30.0, headroom)" in source


def test_durable_work_postgres_unlock_failure_invalidates_pooled_connection():
    source = Path("backend/work/dispute_lock.py").read_text(encoding="utf-8")
    release = source[source.index("def _release_postgres_lock") : source.index("def _lock_wait_seconds")]
    assert "pg_advisory_unlock" in release
    assert "conn.invalidate()" in release

def test_durable_work_worker_serializes_paypal_get_and_case_sync_by_dispute():
    source = Path("backend/work/service.py").read_text(encoding="utf-8")
    guard = source.index("async with dispute_sync_guard(str(dispute_id))")
    get_call = source.index("get_dispute_details(str(dispute_id))", guard)
    sync_call = source.index("sync_dispute_concurrency_safe(fresh)", get_call)
    assert guard < get_call < sync_call


def test_durable_work_doctor_checks_actual_database_revision():
    source = Path("scripts/operations_doctor.py").read_text(encoding="utf-8")
    assert "current_database_revision(db_session.engine)" in source
    assert 'expected_head_revision() == "20261025_0007"' not in source
    assert "postgres_advisory_lock_runtime" in source


def test_durable_work_manual_reconciliation_cli_requires_explicit_dashboard_confirmation():
    source = Path("scripts/reconcile_action.py").read_text(encoding="utf-8")
    assert "--confirm-paypal-dashboard" in source
    assert "confirmed_from_paypal_dashboard=True" in source
    assert "parser.error" in source


def test_durable_work_enqueue_recovers_concurrent_unique_insert(monkeypatch):
    now = utcnow()
    existing = WorkItem(
        work_uid="WORK-RACE-WINNER",
        work_type="PAYPAL_DISPUTE_WEBHOOK",
        source_type="PAYPAL_EVENT",
        source_id="WH-DURABLE_WORK-RACE",
        status="READY",
        attempts=0,
        max_attempts=8,
        available_at=now,
        created_at=now,
        updated_at=now,
    )
    calls = {"get": 0}

    def fake_get_for_source(_session, **_kwargs):
        calls["get"] += 1
        return None if calls["get"] == 1 else existing

    def fake_add(_session, _row):
        raise IntegrityError("INSERT work_items", {}, RuntimeError("duplicate"))

    monkeypatch.setattr(work_repo, "get_for_source", fake_get_for_source)
    monkeypatch.setattr(work_repo, "add", fake_add)

    with session_scope() as session:
        row = work_service.enqueue_paypal_event(session, "WH-DURABLE_WORK-RACE")
    assert row is existing
    assert calls["get"] >= 2


def test_durable_work_executed_result_is_sync_pending_before_refresh():
    import asyncio

    case_id, _, _, approval = asyncio.run(
        prepare(deepcopy(BASE), "SEND_MESSAGE", send_message_payload(), suffix="DURABLE_WORK-PENDING")
    )
    with session_scope() as session:
        row = approval_repo.get_by_uid(session, approval.action_uid, for_update=True)
        assert row is not None
        row.execution_status = "PENDING"
        row.execution_started_at = utcnow()

    _mark_result(
        approval.action_uid,
        status="EXECUTED",
        response_status=200,
        response_body={"ok": True},
        event_type="ACTION_EXECUTED",
    )

    with session_scope() as session:
        row = approval_repo.get_by_uid(session, approval.action_uid)
        assert row is not None
        assert row.execution_status == "EXECUTED"
        assert row.post_action_sync_pending is True
        assert row.post_action_case_revision is None


@pytest.mark.asyncio
async def test_durable_work_local_post_write_sync_failure_never_makes_paypal_write_retryable(monkeypatch):
    case_id, _, _, approval = await prepare(
        deepcopy(BASE), "SEND_MESSAGE", send_message_payload(), suffix="DURABLE_WORK-LOCALFAIL"
    )
    calls = {"send": 0}

    async def get_details(_dispute_id: str):
        return deepcopy(BASE)

    async def send_message(_dispute_id: str, _message: str):
        calls["send"] += 1
        return {"links": []}

    def fail_local_sync(_payload):
        raise RuntimeError("simulated local database/sync failure after PayPal success")

    monkeypatch.setattr(
        "backend.services.actions.disputes_client.get_dispute_details", get_details
    )
    monkeypatch.setattr(
        "backend.services.actions.disputes_client.send_message", send_message
    )
    monkeypatch.setattr(
        "backend.services.actions.case_service.sync_dispute_concurrency_safe", fail_local_sync
    )

    result = await action_engine.execute(
        case_id,
        approval.action_uid,
        ActionExecuteRequest(approval_hash=approval.approval_hash),
    )
    assert result.execution_status == "EXECUTED"
    assert result.result_status == "executed_sync_pending"
    assert result.post_action_sync_pending is True
    assert calls["send"] == 1

    # A browser retry after the confusing local failure must never resend PayPal.
    duplicate = await action_engine.execute(
        case_id,
        approval.action_uid,
        ActionExecuteRequest(approval_hash=approval.approval_hash),
    )
    assert duplicate.execution_status == "EXECUTED"
    assert duplicate.result_status == "already_executed_sync_pending"
    assert duplicate.post_action_sync_pending is True
    assert calls["send"] == 1
