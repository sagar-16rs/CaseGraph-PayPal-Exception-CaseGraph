from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from backend.db.models import ActionApproval, ActionReconciliation
from backend.db.session import session_scope
from backend.evidence.domain import canonical_json_bytes
from backend.paypal.disputes import disputes_client
from backend.paypal.errors import PayPalError
from backend.repositories import action_approvals as approval_repo
from backend.repositories import case_events as case_event_repo
from backend.repositories import cases as case_repo
from backend.repositories import reconciliations as reconciliation_repo
from backend.services.cases import case_service, paypal_snapshot_hash
from backend.work.dispute_lock import DisputeSyncLockTimeout, dispute_sync_guard
from backend.work.domain import ReconciliationMethod, ReconciliationOutcome
from backend.work.schemas import ManualReconciliationRequest, ReconciliationResponse


class ActionReconciliationIntegrityError(RuntimeError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _uid() -> str:
    return f"REC-{uuid.uuid4().hex.upper()}"


def _canonical_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _record_payload(row: ActionReconciliation) -> dict[str, Any]:
    return {
        "reconciliation_uid": row.reconciliation_uid,
        "action_uid": row.action_uid,
        "case_id": row.case_id,
        "method": row.method,
        "outcome": row.outcome,
        "resulting_execution_status": row.resulting_execution_status,
        "observed_snapshot_hash": row.observed_snapshot_hash,
        "details_hash": row.details_hash,
        "reconciled_by": row.reconciled_by,
        "created_at": _canonical_utc_iso(row.created_at),
    }


def _response(row: ActionReconciliation) -> ReconciliationResponse:
    if _hash(row.details_json or {}) != row.details_hash or _hash(_record_payload(row)) != row.record_hash:
        raise ActionReconciliationIntegrityError(f"Reconciliation {row.reconciliation_uid} integrity failure")
    return ReconciliationResponse(
        reconciliation_uid=row.reconciliation_uid,
        action_uid=row.action_uid,
        case_id=row.case_id,
        method=row.method,
        outcome=row.outcome,
        observed_snapshot_hash=row.observed_snapshot_hash,
        details=dict(row.details_json or {}),
        reconciled_by=row.reconciled_by,
        created_at=(row.created_at.replace(tzinfo=timezone.utc) if row.created_at.tzinfo is None else row.created_at).isoformat(),
        execution_status=row.resulting_execution_status,
    )


def _record(
    *,
    action: ActionApproval,
    method: str,
    outcome: str,
    observed_hash: str | None,
    details: dict[str, Any],
    reconciled_by: str | None,
    resulting_execution_status: str,
) -> ActionReconciliation:
    row = ActionReconciliation(
        reconciliation_uid=_uid(),
        action_uid=action.action_uid,
        case_id=action.case_id,
        method=method,
        outcome=outcome,
        resulting_execution_status=resulting_execution_status,
        observed_snapshot_hash=observed_hash,
        details_json=details,
        details_hash=_hash(details),
        record_hash="0" * 64,
        reconciled_by=reconciled_by,
        created_at=utcnow(),
    )
    row.record_hash = _hash(_record_payload(row))
    return row


class ActionReconciliationService:
    async def auto(self, case_id: str, action_uid: str) -> ReconciliationResponse:
        def load() -> ActionApproval:
            with session_scope() as session:
                row = approval_repo.get_by_uid(session, action_uid)
                if row is None or row.case_id != case_id:
                    raise HTTPException(status_code=404, detail=f"Action approval '{action_uid}' not found")
                if row.execution_status not in {"PENDING", "UNKNOWN_OUTCOME", "EXECUTED"}:
                    raise HTTPException(status_code=409, detail="Only unresolved or sync-pending actions can be reconciled.")
                if row.execution_status == "EXECUTED" and not row.post_action_sync_pending:
                    raise HTTPException(status_code=409, detail="Action is already executed and synchronized.")
                return row

        action = await run_in_threadpool(load)
        dispute_id = action.approval_context_json["dispute_id"]
        try:
            async with dispute_sync_guard(dispute_id):
                fresh = await disputes_client.get_dispute_details(dispute_id)
                observed_hash = paypal_snapshot_hash(fresh)
                await run_in_threadpool(case_service.sync_dispute_concurrency_safe, fresh)
        except DisputeSyncLockTimeout as exc:
            raise HTTPException(
                status_code=409,
                detail="PayPal dispute synchronization is busy; retry reconciliation without repeating the original write.",
            ) from exc
        except PayPalError as exc:
            raise HTTPException(status_code=502, detail="Could not fetch authoritative PayPal state for reconciliation.") from exc

        def persist() -> ReconciliationResponse:
            with session_scope() as session:
                row = approval_repo.get_by_uid(session, action_uid, for_update=True)
                if row is None or row.case_id != case_id:
                    raise HTTPException(status_code=404, detail=f"Action approval '{action_uid}' not found")
                if row.execution_status == "EXECUTED" and row.post_action_sync_pending:
                    row.post_action_sync_pending = False
                    current_case = case_repo.get_by_id(session, case_id)
                    if current_case is None:
                        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
                    row.post_action_case_revision = current_case.sync_revision
                    row.updated_at = utcnow()
                    outcome = ReconciliationOutcome.CONFIRMED_EXECUTED.value
                    details = {
                        "reason": "PayPal previously acknowledged execution; durable-work layer refreshed authoritative dispute state.",
                        "case_revision": current_case.sync_revision,
                    }
                elif row.execution_status in {"PENDING", "UNKNOWN_OUTCOME"}:
                    # A GET that does not reveal an effect is not proof that a
                    # non-idempotent POST failed. Preserve the block.
                    outcome = ReconciliationOutcome.INCONCLUSIVE.value
                    details = {
                        "reason": "Fresh PayPal state was synchronized, but CaseGraph cannot prove whether the ambiguous non-idempotent write executed.",
                        "execution_status_preserved": row.execution_status,
                    }
                else:
                    raise HTTPException(status_code=409, detail="Action state changed during reconciliation.")
                rec = _record(
                    action=row,
                    method=ReconciliationMethod.AUTO_PAYPAL_STATE.value,
                    outcome=outcome,
                    observed_hash=observed_hash,
                    details=details,
                    reconciled_by=None,
                    resulting_execution_status=row.execution_status,
                )
                reconciliation_repo.add(session, rec)
                case_event_repo.append_event(
                    session,
                    case_id=case_id,
                    event_type="ACTION_RECONCILED",
                    actor_type="system",
                    actor_id=action_uid,
                    source="durable_reconciliation",
                    payload={
                        "action_uid": action_uid,
                        "reconciliation_uid": rec.reconciliation_uid,
                        "method": rec.method,
                        "outcome": rec.outcome,
                    },
                )
                return _response(rec)

        return await run_in_threadpool(persist)

    async def manual(
        self, case_id: str, action_uid: str, req: ManualReconciliationRequest
    ) -> ReconciliationResponse:
        # Manual decisions are intentionally explicit. They are the only durable-work layer
        # path that can clear UNKNOWN_OUTCOME as "not executed" and thereby
        # permit a newly approved write.
        if not req.confirmed_from_paypal_dashboard:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Manual reconciliation requires explicit confirmation that the outcome was "
                    "verified in the PayPal dashboard; ambiguous writes fail closed."
                ),
            )
        if req.decision not in {
            ReconciliationOutcome.CONFIRMED_EXECUTED.value,
            ReconciliationOutcome.CONFIRMED_NOT_EXECUTED.value,
        }:
            raise HTTPException(status_code=422, detail="Unsupported manual reconciliation decision.")

        def persist() -> ReconciliationResponse:
            with session_scope() as session:
                row = approval_repo.get_by_uid(session, action_uid, for_update=True)
                if row is None or row.case_id != case_id:
                    raise HTTPException(status_code=404, detail=f"Action approval '{action_uid}' not found")
                if row.execution_status not in {"PENDING", "UNKNOWN_OUTCOME"}:
                    raise HTTPException(status_code=409, detail="Manual reconciliation is only allowed for unresolved external-write outcomes.")
                now = utcnow()
                previous_status = row.execution_status
                if req.decision == ReconciliationOutcome.CONFIRMED_EXECUTED.value:
                    row.execution_status = "EXECUTED"
                    row.executed_at = now
                    row.post_action_sync_pending = True
                    row.last_error = None
                else:
                    row.execution_status = "FAILED"
                    row.executed_at = None
                    row.post_action_sync_pending = False
                    row.last_error = f"Manual PayPal-dashboard reconciliation by {req.confirmed_by}: confirmed not executed."
                row.updated_at = now
                details = {
                    "note": req.note,
                    "confirmed_from_paypal_dashboard": True,
                    "previous_status": previous_status,
                }
                rec = _record(
                    action=row,
                    method=ReconciliationMethod.MANUAL_PAYPAL_DASHBOARD.value,
                    outcome=req.decision,
                    observed_hash=None,
                    details=details,
                    reconciled_by=req.confirmed_by,
                    resulting_execution_status=row.execution_status,
                )
                reconciliation_repo.add(session, rec)
                case_event_repo.append_event(
                    session,
                    case_id=case_id,
                    event_type="ACTION_RECONCILED",
                    actor_type="human",
                    actor_id=req.confirmed_by,
                    source="durable_reconciliation",
                    payload={
                        "action_uid": action_uid,
                        "reconciliation_uid": rec.reconciliation_uid,
                        "method": rec.method,
                        "outcome": rec.outcome,
                    },
                )
                return _response(rec)

        result = await run_in_threadpool(persist)
        if req.decision == ReconciliationOutcome.CONFIRMED_EXECUTED.value:
            # Best-effort state refresh happens after the durable manual record.
            # Failure does not reverse the operator-confirmed execution status.
            try:
                action = await run_in_threadpool(self._load_action, case_id, action_uid)
                dispute_id = action.approval_context_json["dispute_id"]
                async with dispute_sync_guard(dispute_id):
                    fresh = await disputes_client.get_dispute_details(dispute_id)
                    await run_in_threadpool(case_service.sync_dispute_concurrency_safe, fresh)
                await run_in_threadpool(self._clear_sync_pending, case_id, action_uid)
                result.execution_status = "EXECUTED"
            except Exception:
                pass
        return result

    @staticmethod
    def _load_action(case_id: str, action_uid: str) -> ActionApproval:
        with session_scope() as session:
            row = approval_repo.get_by_uid(session, action_uid)
            if row is None or row.case_id != case_id:
                raise HTTPException(status_code=404, detail=f"Action approval '{action_uid}' not found")
            return row

    @staticmethod
    def _clear_sync_pending(case_id: str, action_uid: str) -> None:
        current = case_service.get(case_id)
        with session_scope() as session:
            row = approval_repo.get_by_uid(session, action_uid, for_update=True)
            if row and row.execution_status == "EXECUTED":
                row.post_action_sync_pending = False
                row.post_action_case_revision = current.sync_revision
                row.updated_at = utcnow()

    def list(self, case_id: str, action_uid: str) -> list[ReconciliationResponse]:
        with session_scope() as session:
            action = approval_repo.get_by_uid(session, action_uid)
            if action is None or action.case_id != case_id:
                raise HTTPException(status_code=404, detail=f"Action approval '{action_uid}' not found")
            return [
                _response(row)
                for row in reconciliation_repo.list_for_action(session, action_uid)
            ]


reconciliation_service = ActionReconciliationService()
