from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from pydantic import TypeAdapter
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from backend.actions.domain import ACTION_POLICY_VERSION, action_policy_hash
from backend.actions.schemas import (
    AcceptClaimPayload,
    ActionApprovalRequest,
    ActionApprovalResponse,
    ActionExecuteRequest,
    ActionExecutionResponse,
    ActionPayload,
    AcknowledgeReturnItemPayload,
    AppealPayload,
    EscalatePayload,
    MakeOfferPayload,
    ProvideEvidencePayload,
    ProvideSupportingInfoPayload,
    SendMessagePayload,
)
from backend.actions.validation import live_action_context, validate_action_payload_against_dispute
from backend.casegraph.domain import CaseEventType
from backend.db.models import ActionApproval
from backend.db.session import session_scope
from backend.evidence.domain import canonical_json_bytes
from backend.paypal.disputes import disputes_client
from backend.paypal.errors import PayPalAPIError, PayPalTransportError
from backend.repositories import action_approvals as approval_repo
from backend.repositories import analyses as analysis_repo
from backend.repositories import case_events as event_repo
from backend.repositories import cases as case_repo
from backend.repositories import evidence as evidence_repo
from backend.repositories import graphs as graph_repo
from backend.repositories import safety as safety_repo
from backend.safety.domain import policy_hash as safety_policy_hash
from backend.safety.service import SafetyIntegrityError, safety_service
from backend.services.cases import case_service
from backend.work.dispute_lock import DisputeSyncLockTimeout, dispute_sync_guard
from backend.security.context import get_current_actor
from backend.uploads.action_files import build_paypal_evidence_payload, extract_file_refs
from backend.uploads.service import resolve_action_files


_PAYLOAD_ADAPTER = TypeAdapter(ActionPayload)


class ActionApprovalIntegrityError(RuntimeError):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _uid() -> str:
    return f"ACT-{uuid.uuid4().hex.upper()}"


def _canonical_utc_iso(value: datetime) -> str:
    # SQLite commonly reloads timezone-aware DateTime columns as naive values.
    # Treat stored naive timestamps as UTC so the approval hash is stable across
    # SQLite development and PostgreSQL production.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _approval_payload(row: ActionApproval) -> dict[str, Any]:
    return {
        "action_uid": row.action_uid,
        "action_request_id": row.action_request_id,
        "case_id": row.case_id,
        "analysis_uid": row.analysis_uid,
        "safety_uid": row.safety_uid,
        "graph_id": row.graph_id,
        "safety_policy_hash": row.safety_policy_hash,
        "action_policy_version": row.action_policy_version,
        "action_policy_hash": row.action_policy_hash,
        "action_type": row.action_type,
        "action_risk": row.action_risk,
        "approved_by": row.approved_by,
        "payload_hash": row.payload_hash,
        "approval_context_hash": row.approval_context_hash,
        "approved_at": _canonical_utc_iso(row.approved_at),
    }


def _verify_row(row: ActionApproval) -> None:
    if _hash(row.payload_json) != row.payload_hash:
        raise ActionApprovalIntegrityError(f"Action approval {row.action_uid} payload integrity failure")
    if _hash(row.approval_context_json) != row.approval_context_hash:
        raise ActionApprovalIntegrityError(f"Action approval {row.action_uid} context integrity failure")
    if _hash(_approval_payload(row)) != row.approval_hash:
        raise ActionApprovalIntegrityError(f"Action approval {row.action_uid} approval integrity failure")


def _response(row: ActionApproval) -> ActionApprovalResponse:
    _verify_row(row)
    return ActionApprovalResponse(
        action_uid=row.action_uid,
        action_request_id=row.action_request_id,
        case_id=row.case_id,
        analysis_uid=row.analysis_uid,
        safety_uid=row.safety_uid,
        graph_id=row.graph_id,
        action_type=row.action_type,
        action_risk=row.action_risk,
        approved_by=row.approved_by,
        payload=row.payload_json,
        payload_hash=row.payload_hash,
        approval_hash=row.approval_hash,
        execution_status=row.execution_status,
        post_action_sync_pending=bool(row.post_action_sync_pending),
        approved_at=row.approved_at.isoformat(),
    )


def _execution_response(row: ActionApproval, *, result_status: str, warning: str | None = None) -> ActionExecutionResponse:
    _verify_row(row)
    return ActionExecutionResponse(
        action_uid=row.action_uid,
        action_request_id=row.action_request_id,
        case_id=row.case_id,
        action_type=row.action_type,
        execution_status=row.execution_status,
        result_status=result_status,
        post_action_sync_pending=bool(row.post_action_sync_pending),
        paypal_response=row.paypal_response_body or {},
        updated_dispute_status=None,
        warning=warning,
        last_error=row.last_error,
    )


def _load_duplicate(action_request_id: str) -> ActionApproval | None:
    with session_scope() as session:
        row = approval_repo.get_by_request_id(session, action_request_id)
        if row:
            _verify_row(row)
        return row


def _duplicate_matches_request(row: ActionApproval, case_id: str, req: ActionApprovalRequest) -> bool:
    candidate_payload = req.payload.model_dump(mode="json", exclude_none=True)
    return (
        row.case_id == case_id
        and row.analysis_uid == req.analysis_uid
        and row.safety_uid == req.safety_uid
        and row.approved_by == req.approved_by
        and row.payload_hash == _hash(candidate_payload)
        and row.action_policy_version == ACTION_POLICY_VERSION
        and row.action_policy_hash == action_policy_hash()
    )


def _assert_local_chain_current(
    session,
    *,
    case_id: str,
    analysis_uid: str,
    safety_uid: str,
    graph_id: str,
    action_type: str,
    expected_safety_policy_hash: str,
) -> tuple[Any, Any, Any]:
    """Atomically verify local semantic state at an approval/execution boundary.

    Case sync and evidence ingestion already serialize on the case row.
    Taking the same lock creates a local linearization point without holding a
    database transaction open during the external PayPal write.
    """
    case = case_repo.get_by_id_for_update(session, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    analysis = analysis_repo.get_by_uid(session, case_id, analysis_uid)
    if analysis is None or analysis.status != "COMPLETED" or analysis.graph_id != graph_id:
        raise HTTPException(status_code=409, detail="AI analysis/graph chain is no longer current for this approval.")
    safety = safety_repo.get_by_uid(session, safety_uid)
    latest_safety = safety_repo.latest(session, analysis_uid)
    if safety is None or latest_safety is None or latest_safety.safety_uid != safety_uid:
        raise HTTPException(status_code=409, detail="Safety assessment is no longer the latest assessment for this analysis.")
    if _hash(safety.report_json) != safety.report_hash:
        raise ActionApprovalIntegrityError("Stored safety report failed integrity verification at action boundary")
    if (
        safety.analysis_uid != analysis_uid
        or safety.case_id != case_id
        or safety.graph_id != graph_id
        or safety.policy_hash != expected_safety_policy_hash
        or safety.policy_hash != safety_policy_hash()
        or safety.safety_status == "BLOCKED"
        or safety.abstain_required
        or safety.effective_action != action_type
    ):
        raise HTTPException(status_code=409, detail="Current safety state does not permit this exact action.")
    graph_revision = int(graph_id.rsplit("R", 1)[-1])
    graph = graph_repo.get_revision(session, case_id, graph_revision)
    if graph is None or graph.graph_id != graph_id or graph.content_hash != safety.graph_hash:
        raise HTTPException(status_code=409, detail="Safety assessment no longer matches the persisted CaseGraph revision.")
    evidence_set = evidence_repo.latest_set(session, case_id)
    evidence_revision = evidence_set.revision if evidence_set else 0
    if (
        graph.input_case_revision != case.sync_revision
        or (graph.input_evidence_set_revision or 0) != evidence_revision
    ):
        raise HTTPException(
            status_code=409,
            detail="Case/evidence changed after analysis. Re-analyze and obtain a new human approval.",
        )
    return case, safety, graph


def _approval_inputs(case_id: str, req: ActionApprovalRequest) -> tuple[dict[str, Any], str, str, str, str]:
    """Validate the AI/safety chain and return current PayPal snapshot metadata.

    Returns raw_dispute_payload, graph_id, action_risk, safety_hash, expected_action.
    """
    with session_scope() as session:
        analysis = analysis_repo.get_by_uid(session, case_id, req.analysis_uid)
        if analysis is None:
            raise HTTPException(status_code=404, detail=f"AI analysis '{req.analysis_uid}' not found")
        if analysis.status != "COMPLETED" or not analysis.graph_id:
            raise HTTPException(status_code=409, detail="Only completed AI analyses can authorize actions.")
        case = case_repo.get_by_id(session, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
        raw = dict(case.raw_dispute_payload or {})

    try:
        safety = safety_service.get(case_id, req.analysis_uid)
    except SafetyIntegrityError as exc:
        raise HTTPException(status_code=409, detail="Safety assessment integrity check failed.") from exc

    if safety.safety_uid != req.safety_uid:
        raise HTTPException(
            status_code=409,
            detail="The supplied safety assessment is not the latest assessment for this analysis.",
        )
    if safety.is_stale or safety.safety_status == "BLOCKED" or safety.abstain_required:
        raise HTTPException(status_code=409, detail="The current safety assessment does not permit this action.")
    if safety.policy_hash != safety_policy_hash():
        raise HTTPException(status_code=409, detail="Safety policy changed; re-run safety assessment.")
    if safety.effective_action != req.payload.action_type:
        raise HTTPException(
            status_code=422,
            detail=f"Approved payload action {req.payload.action_type} does not match safety recommendation {safety.effective_action}.",
        )
    if safety.graph_id != analysis.graph_id:
        raise HTTPException(status_code=409, detail="Safety assessment graph does not match the AI analysis graph.")

    validate_action_payload_against_dispute(req.payload, raw)
    # File UIDs are part of the immutable payload hash. Resolve them before approval
    # so a human cannot approve references to missing/cross-case/unscanned files.
    resolve_action_files(case_id, extract_file_refs(req.payload))
    return raw, safety.graph_id, safety.action_risk.value, safety.policy_hash, safety.effective_action


def _persist_approval(case_id: str, req: ActionApprovalRequest) -> ActionApprovalResponse:
    duplicate = _load_duplicate(req.action_request_id)
    if duplicate:
        if not _duplicate_matches_request(duplicate, case_id, req):
            raise HTTPException(status_code=409, detail="action_request_id was already used for a different approval.")
        return _response(duplicate)

    # First run the full safety integrity path. The insertion transaction below
    # then re-checks the same chain while holding the case row lock.
    _, graph_id, risk, safety_hash, _ = _approval_inputs(case_id, req)
    payload = req.payload.model_dump(mode="json", exclude_none=True)
    payload_hash = _hash(payload)
    now = utcnow()

    try:
        with session_scope() as session:
            case, _safety_row, _graph = _assert_local_chain_current(
                session,
                case_id=case_id,
                analysis_uid=req.analysis_uid,
                safety_uid=req.safety_uid,
                graph_id=graph_id,
                action_type=req.payload.action_type,
                expected_safety_policy_hash=safety_hash,
            )
            unresolved = approval_repo.unresolved_for_case(session, case_id)
            if unresolved is not None:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Case has unresolved action {unresolved.action_uid} in {unresolved.execution_status} state. "
                        "Reconcile that outcome before creating another approval."
                    ),
                )
            raw = dict(case.raw_dispute_payload or {})
            validate_action_payload_against_dispute(req.payload, raw)
            resolve_action_files(case_id, extract_file_refs(req.payload))
            context = live_action_context(raw, req.payload.action_type)
            row = ActionApproval(
                action_uid=_uid(),
                action_request_id=req.action_request_id,
                case_id=case_id,
                analysis_uid=req.analysis_uid,
                safety_uid=req.safety_uid,
                graph_id=graph_id,
                safety_policy_hash=safety_hash,
                action_policy_version=ACTION_POLICY_VERSION,
                action_policy_hash=action_policy_hash(),
                action_type=req.payload.action_type,
                action_risk=risk,
                approved_by=req.approved_by,
                payload_json=payload,
                payload_hash=payload_hash,
                approval_context_json=context,
                approval_context_hash=_hash(context),
                approval_hash="0" * 64,
                execution_status="NOT_STARTED",
                approved_at=now,
                updated_at=now,
                post_action_sync_pending=False,
            )
            row.approval_hash = _hash(_approval_payload(row))
            approval_repo.add(session, row)
            event_repo.append_event(
                session,
                case_id=case_id,
                event_type=CaseEventType.ACTION_APPROVED.value,
                graph_revision=int(graph_id.rsplit("R", 1)[-1]),
                actor_type="human",
                actor_id=req.approved_by,
                source="action_engine",
                payload={
                    "action_uid": row.action_uid,
                    "analysis_uid": req.analysis_uid,
                    "safety_uid": req.safety_uid,
                    "action_type": row.action_type,
                    "action_risk": row.action_risk,
                    "payload_hash": row.payload_hash,
                    "approval_hash": row.approval_hash,
                },
            )
    except IntegrityError:
        # A concurrent request may have won the unique action_request_id race.
        # Re-run the exact idempotency comparison; never return a differently
        # approved payload merely because it shares the same request ID.
        duplicate = _load_duplicate(req.action_request_id)
        if duplicate:
            if not _duplicate_matches_request(duplicate, case_id, req):
                raise HTTPException(
                    status_code=409,
                    detail="action_request_id was concurrently used for a different approval.",
                )
            return _response(duplicate)
        raise
    return _response(row)


def _begin_execution(action_uid: str, approval_hash: str) -> ActionApproval:
    with session_scope() as session:
        row = approval_repo.get_by_uid(session, action_uid, for_update=True)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Action approval '{action_uid}' not found")
        _verify_row(row)
        if row.approval_hash != approval_hash:
            raise HTTPException(status_code=409, detail="approval_hash does not match the human-approved payload/context.")
        if row.execution_status == "EXECUTED":
            return row
        if row.execution_status in {"PENDING", "UNKNOWN_OUTCOME"}:
            raise HTTPException(
                status_code=409,
                detail="Action has an unresolved external-write outcome; CaseGraph will not retry it automatically.",
            )
        if row.execution_status == "FAILED":
            raise HTTPException(
                status_code=409,
                detail="A definitively failed execution requires a new human approval and action_request_id.",
            )
        _assert_local_chain_current(
            session,
            case_id=row.case_id,
            analysis_uid=row.analysis_uid,
            safety_uid=row.safety_uid,
            graph_id=row.graph_id,
            action_type=row.action_type,
            expected_safety_policy_hash=row.safety_policy_hash,
        )
        unresolved = approval_repo.unresolved_for_case(
            session, row.case_id, exclude_uid=row.action_uid
        )
        if unresolved is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Case already has unresolved action {unresolved.action_uid} in "
                    f"{unresolved.execution_status} state. No concurrent/ambiguous write is allowed."
                ),
            )
        row.execution_status = "PENDING"
        row.execution_started_at = utcnow()
        row.updated_at = utcnow()
        event_repo.append_event(
            session,
            case_id=row.case_id,
            event_type=CaseEventType.ACTION_EXECUTION_STARTED.value,
            graph_revision=int(row.graph_id.rsplit("R", 1)[-1]),
            actor_type="system",
            actor_id=row.action_uid,
            source="action_engine",
            payload={"action_uid": row.action_uid, "action_type": row.action_type},
        )
        session.flush()
        return row


def _mark_result(
    action_uid: str,
    *,
    status: str,
    response_status: int | None = None,
    response_body: dict[str, Any] | None = None,
    error: str | None = None,
    event_type: str,
) -> ActionApproval:
    with session_scope() as session:
        row = approval_repo.get_by_uid(session, action_uid, for_update=True)
        if row is None:
            raise RuntimeError("Action approval disappeared while recording execution result")
        if row.execution_status != "PENDING":
            raise RuntimeError(
                f"Invalid action transition: expected PENDING before result, found {row.execution_status}"
            )
        row.execution_status = status
        row.paypal_response_status = response_status
        row.paypal_response_body = response_body
        row.last_error = error[:1000] if error else None
        row.updated_at = utcnow()
        if status == "EXECUTED":
            row.executed_at = utcnow()
            # PayPal has acknowledged the non-idempotent write, but local state
            # has not yet been authoritatively refreshed. Persist this before any
            # subsequent network/DB work so crashes cannot lose the sync-needed flag.
            row.post_action_sync_pending = True
            row.post_action_case_revision = None
        event_repo.append_event(
            session,
            case_id=row.case_id,
            event_type=event_type,
            graph_revision=int(row.graph_id.rsplit("R", 1)[-1]),
            actor_type="system",
            actor_id=row.action_uid,
            source="action_engine",
            payload={
                "action_uid": row.action_uid,
                "action_type": row.action_type,
                "execution_status": status,
                "paypal_response_status": response_status,
            },
        )
        session.flush()
        return row


def _mark_post_sync(action_uid: str, *, case_revision: int | None, pending: bool, error: str | None = None) -> ActionApproval:
    with session_scope() as session:
        row = approval_repo.get_by_uid(session, action_uid, for_update=True)
        if row is None:
            raise RuntimeError("Action approval disappeared during post-action sync")
        if row.execution_status != "EXECUTED":
            raise RuntimeError(
                f"Post-action synchronization requires EXECUTED state, found {row.execution_status}"
            )
        row.post_action_case_revision = case_revision
        row.post_action_sync_pending = pending
        if error:
            row.last_error = error[:1000]
        row.updated_at = utcnow()
        session.flush()
        return row


def _payload_model(row: ActionApproval) -> ActionPayload:
    try:
        return _PAYLOAD_ADAPTER.validate_python(row.payload_json)
    except Exception as exc:  # persisted row corruption must fail closed
        raise ActionApprovalIntegrityError(f"Stored action payload {row.action_uid} is invalid") from exc


def _paypal_body(payload: ActionPayload) -> dict[str, Any]:
    body = payload.model_dump(mode="json", exclude_none=True)
    body.pop("action_type", None)
    if isinstance(payload, (ProvideEvidencePayload, AppealPayload)):
        evidences = []
        for item in body["evidences"]:
            clean = dict(item)
            clean.pop("file_refs", None)
            evidences.append(clean)
        return {"evidences": evidences}
    return body


async def _call_paypal(dispute_id: str, case_id: str, payload: ActionPayload) -> dict[str, Any]:
    if isinstance(payload, SendMessagePayload):
        return await disputes_client.send_message(dispute_id, payload.message)
    if isinstance(payload, MakeOfferPayload):
        return await disputes_client.make_offer(dispute_id, _paypal_body(payload))
    if isinstance(payload, AcceptClaimPayload):
        return await disputes_client.accept_claim(dispute_id, _paypal_body(payload))
    if isinstance(payload, ProvideEvidencePayload):
        files = resolve_action_files(case_id, extract_file_refs(payload))
        input_body, parts = build_paypal_evidence_payload(payload, files)
        return await disputes_client.provide_evidence(dispute_id, input_body, file_parts=parts)
    if isinstance(payload, AppealPayload):
        files = resolve_action_files(case_id, extract_file_refs(payload))
        input_body, parts = build_paypal_evidence_payload(payload, files)
        return await disputes_client.appeal(dispute_id, input_body, file_parts=parts)
    if isinstance(payload, EscalatePayload):
        return await disputes_client.escalate(dispute_id, payload.note)
    if isinstance(payload, ProvideSupportingInfoPayload):
        return await disputes_client.provide_supporting_info(dispute_id, payload.notes)
    if isinstance(payload, AcknowledgeReturnItemPayload):
        return await disputes_client.acknowledge_return_item(dispute_id, _paypal_body(payload))
    raise RuntimeError(f"Unsupported persisted action payload {payload.action_type}")


class ActionEngine:
    async def approve(self, case_id: str, req: ActionApprovalRequest) -> ActionApprovalResponse:
        actor = get_current_actor()
        if actor is not None:
            # Audit identity is derived from the verified bearer token, never from
            # a caller-controlled body field. This preserves CLI/static demos when
            # auth is deliberately disabled outside production.
            req = req.model_copy(update={"approved_by": actor.subject})
        return await run_in_threadpool(_persist_approval, case_id, req)

    async def get(self, case_id: str, action_uid: str) -> ActionApprovalResponse:
        def load() -> ActionApprovalResponse:
            with session_scope() as session:
                row = approval_repo.get_by_uid(session, action_uid)
                if row is None or row.case_id != case_id:
                    raise HTTPException(status_code=404, detail=f"Action approval '{action_uid}' not found")
                return _response(row)
        return await run_in_threadpool(load)

    async def list(self, case_id: str) -> list[ActionApprovalResponse]:
        def load() -> list[ActionApprovalResponse]:
            with session_scope() as session:
                case = case_repo.get_by_id(session, case_id)
                if case is None:
                    raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
                return [_response(row) for row in approval_repo.list_for_case(session, case_id)]
        return await run_in_threadpool(load)

    async def execute(self, case_id: str, action_uid: str, req: ActionExecuteRequest) -> ActionExecutionResponse:
        def load_for_preflight() -> ActionApproval:
            with session_scope() as session:
                row = approval_repo.get_by_uid(session, action_uid)
                if row is None or row.case_id != case_id:
                    raise HTTPException(status_code=404, detail=f"Action approval '{action_uid}' not found")
                _verify_row(row)
                if row.execution_status == "NOT_STARTED":
                    unresolved = approval_repo.unresolved_for_case(
                        session, row.case_id, exclude_uid=row.action_uid
                    )
                    if unresolved is not None:
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                f"Case already has unresolved action {unresolved.action_uid} in "
                                f"{unresolved.execution_status} state. CaseGraph will not contact "
                                "PayPal for another write until that outcome is reconciled."
                            ),
                        )
                return row

        row = await run_in_threadpool(load_for_preflight)
        if row.approval_hash != req.approval_hash:
            raise HTTPException(status_code=409, detail="approval_hash does not match this action approval.")
        if row.execution_status == "EXECUTED":
            return _execution_response(
                row,
                result_status=(
                    "already_executed_sync_pending"
                    if row.post_action_sync_pending
                    else "already_executed"
                ),
                warning=(
                    "PayPal already accepted this action, but local synchronization is still pending. "
                    "Do not retry the PayPal write; reconcile the case instead."
                    if row.post_action_sync_pending
                    else None
                ),
            )
        if row.execution_status in {"PENDING", "UNKNOWN_OUTCOME"}:
            raise HTTPException(
                status_code=409,
                detail="Action has an unresolved external-write outcome; CaseGraph will not contact PayPal or retry it automatically.",
            )
        if row.execution_status == "FAILED":
            raise HTTPException(
                status_code=409,
                detail="A definitively failed execution requires a new human approval and action_request_id.",
            )

        safety = await run_in_threadpool(safety_service.get, case_id, row.analysis_uid)
        if (
            safety.safety_uid != row.safety_uid
            or safety.is_stale
            or safety.safety_status == "BLOCKED"
            or safety.abstain_required
            or safety.effective_action != row.action_type
            or safety.policy_hash != row.safety_policy_hash
            or row.action_policy_hash != action_policy_hash()
        ):
            raise HTTPException(status_code=409, detail="Approval is no longer backed by the current safety/action policy state.")

        payload = _payload_model(row)
        dispute_id = row.approval_context_json["dispute_id"]

        # Keep the per-dispute session advisory lock from the authoritative GET
        # through the one non-idempotent PayPal POST and post-write refresh. This
        # serializes local webhook workers/manual syncs with the financial write
        # without holding a SQL transaction across network I/O.
        try:
            async with dispute_sync_guard(dispute_id):
                live = await disputes_client.get_dispute_details(dispute_id)
                try:
                    validate_action_payload_against_dispute(payload, live)
                except HTTPException:
                    await run_in_threadpool(case_service.sync_dispute_concurrency_safe, live)
                    raise
                live_context = live_action_context(live, row.action_type)
                if _hash(live_context) != row.approval_context_hash:
                    await run_in_threadpool(case_service.sync_dispute_concurrency_safe, live)
                    raise HTTPException(
                        status_code=409,
                        detail="Live PayPal action context changed after human approval. Case was refreshed; re-analyze and approve again.",
                    )

                row = await run_in_threadpool(_begin_execution, action_uid, req.approval_hash)
                if row.execution_status == "EXECUTED":
                    return _execution_response(
                        row,
                        result_status=(
                            "already_executed_sync_pending"
                            if row.post_action_sync_pending
                            else "already_executed"
                        ),
                        warning=(
                            "PayPal already accepted this action, but local synchronization is still pending. "
                            "Do not retry the PayPal write; reconcile the case instead."
                            if row.post_action_sync_pending
                            else None
                        ),
                    )

                try:
                    response = await _call_paypal(dispute_id, case_id, payload)
                except PayPalTransportError as exc:
                    await run_in_threadpool(
                        _mark_result,
                        action_uid,
                        status="UNKNOWN_OUTCOME",
                        error=str(exc),
                        event_type=CaseEventType.ACTION_OUTCOME_UNKNOWN.value,
                    )
                    raise
                except PayPalAPIError as exc:
                    status = "UNKNOWN_OUTCOME" if exc.status_code >= 500 else "FAILED"
                    event = (
                        CaseEventType.ACTION_OUTCOME_UNKNOWN.value
                        if status == "UNKNOWN_OUTCOME"
                        else CaseEventType.ACTION_FAILED.value
                    )
                    await run_in_threadpool(
                        _mark_result,
                        action_uid,
                        status=status,
                        response_status=exc.status_code,
                        error=str(exc),
                        event_type=event,
                    )
                    raise

                row = await run_in_threadpool(
                    _mark_result,
                    action_uid,
                    status="EXECUTED",
                    response_status=200,
                    response_body=response,
                    event_type=CaseEventType.ACTION_EXECUTED.value,
                )

                try:
                    updated = await disputes_client.get_dispute_details(dispute_id)
                    await run_in_threadpool(case_service.sync_dispute_concurrency_safe, updated)
                    updated_case = await run_in_threadpool(case_service.get, case_id)
                    if updated_case is None:
                        raise RuntimeError("case disappeared during post-action synchronization")
                    row = await run_in_threadpool(
                        _mark_post_sync,
                        action_uid,
                        case_revision=updated_case.sync_revision,
                        pending=False,
                    )
                    result = _execution_response(row, result_status="executed")
                    result.updated_dispute_status = updated_case.dispute_status
                    return result
                except Exception as exc:
                    # The external write is already confirmed EXECUTED. Any later
                    # failure must never make the caller think it is safe to resend.
                    try:
                        row = await run_in_threadpool(
                            _mark_post_sync,
                            action_uid,
                            case_revision=None,
                            pending=True,
                            error=f"{type(exc).__name__}: {exc}",
                        )
                    except Exception:
                        # `_mark_result` already committed EXECUTED + sync_pending.
                        raise exc
                    return _execution_response(
                        row,
                        result_status="executed_sync_pending",
                        warning=(
                            "PayPal accepted the action, but CaseGraph could not complete the local authoritative refresh. "
                            "Do not retry the action; reconcile/sync the case instead."
                        ),
                    )
        except DisputeSyncLockTimeout as exc:
            raise HTTPException(
                status_code=409,
                detail="PayPal dispute synchronization is busy; retry the approval execution request later.",
            ) from exc


action_engine = ActionEngine()
