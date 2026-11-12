from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from backend.config import settings
from backend.db.models import PayPalEvent, WorkItem
from backend.db.session import session_scope
from backend.paypal.disputes import disputes_client
from backend.repositories import events as event_repo
from backend.repositories import work_items as work_repo
from backend.services.cases import case_service
from backend.work.dispute_lock import dispute_sync_guard
from backend.work.domain import WorkStatus, WorkType
from backend.work.schemas import QueueStatusResponse, WorkItemResponse

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _work_uid(source_type: str, source_id: str, work_type: str) -> str:
    digest = hashlib.sha256(f"{source_type}:{source_id}:{work_type}".encode()).hexdigest()[:24].upper()
    return f"WORK-{digest}"


def _dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _response(row: WorkItem) -> WorkItemResponse:
    return WorkItemResponse(
        work_uid=row.work_uid,
        work_type=row.work_type,
        source_type=row.source_type,
        source_id=row.source_id,
        status=row.status,
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        available_at=_dt(row.available_at) or "",
        lease_owner=row.lease_owner,
        lease_expires_at=_dt(row.lease_expires_at),
        last_error=row.last_error,
        created_at=_dt(row.created_at) or "",
        updated_at=_dt(row.updated_at) or "",
        completed_at=_dt(row.completed_at),
    )


class DurableWorkService:
    def enqueue_paypal_event(self, session, event_id: str) -> WorkItem:
        existing = work_repo.get_for_source(
            session,
            source_type="PAYPAL_EVENT",
            source_id=event_id,
            work_type=WorkType.PAYPAL_DISPUTE_WEBHOOK.value,
        )
        if existing is not None:
            return existing
        now = utcnow()
        row = WorkItem(
            work_uid=_work_uid("PAYPAL_EVENT", event_id, WorkType.PAYPAL_DISPUTE_WEBHOOK.value),
            work_type=WorkType.PAYPAL_DISPUTE_WEBHOOK.value,
            source_type="PAYPAL_EVENT",
            source_id=event_id,
            status=WorkStatus.READY.value,
            attempts=0,
            max_attempts=settings.worker_max_attempts,
            available_at=now,
            created_at=now,
            updated_at=now,
        )
        # API and worker startup can backfill concurrently. The unique source
        # constraint is the authority; a savepoint keeps the outer transaction
        # usable when another process wins the insert race.
        try:
            with session.begin_nested():
                return work_repo.add(session, row)
        except IntegrityError:
            existing = work_repo.get_for_source(
                session,
                source_type="PAYPAL_EVENT",
                source_id=event_id,
                work_type=WorkType.PAYPAL_DISPUTE_WEBHOOK.value,
            )
            if existing is None:
                raise
            return existing

    def backfill_unprocessed_events(self) -> int:
        """Ensure pre-durable-work layer/unprocessed events have durable work rows."""
        created = 0
        with session_scope() as session:
            for event in event_repo.list_unprocessed(session):
                existing = work_repo.get_for_source(
                    session,
                    source_type="PAYPAL_EVENT",
                    source_id=event.event_id,
                    work_type=WorkType.PAYPAL_DISPUTE_WEBHOOK.value,
                )
                if existing is None:
                    self.enqueue_paypal_event(session, event.event_id)
                    created += 1
        return created

    def claim_next(self, *, lease_owner: str) -> WorkItemResponse | None:
        now = utcnow()
        lease_expires = now + timedelta(seconds=settings.worker_lease_seconds)
        with session_scope() as session:
            row = work_repo.claim_next(
                session,
                now=now,
                lease_owner=lease_owner,
                lease_expires_at=lease_expires,
                max_attempts_default=settings.worker_max_attempts,
                use_skip_locked=settings.database_backend == "postgresql",
            )
            return _response(row) if row else None

    def _complete(self, work_uid: str, *, lease_owner: str) -> None:
        with session_scope() as session:
            row = work_repo.get(session, work_uid, for_update=True)
            if row is None:
                raise RuntimeError(f"Work item {work_uid} disappeared")
            if row.status != WorkStatus.LEASED.value or row.lease_owner != lease_owner:
                raise RuntimeError("Worker no longer owns work lease")
            now = utcnow()
            row.status = WorkStatus.COMPLETED.value
            row.lease_owner = None
            row.lease_expires_at = None
            row.last_error = None
            row.completed_at = now
            row.updated_at = now

    def _dead_letter_now(self, work_uid: str, *, lease_owner: str, error: str) -> None:
        with session_scope() as session:
            row = work_repo.get(session, work_uid, for_update=True)
            if row is None:
                raise RuntimeError(f"Work item {work_uid} disappeared")
            if row.status != WorkStatus.LEASED.value or row.lease_owner != lease_owner:
                raise RuntimeError("Worker no longer owns work lease")
            now = utcnow()
            row.status = WorkStatus.DEAD_LETTER.value
            row.lease_owner = None
            row.lease_expires_at = None
            row.last_error = error[:2000]
            row.available_at = now
            row.updated_at = now

    def _retry_or_dead_letter(self, work_uid: str, *, lease_owner: str, error: str) -> str:
        with session_scope() as session:
            row = work_repo.get(session, work_uid, for_update=True)
            if row is None:
                raise RuntimeError(f"Work item {work_uid} disappeared")
            if row.status != WorkStatus.LEASED.value or row.lease_owner != lease_owner:
                raise RuntimeError("Worker no longer owns work lease")
            now = utcnow()
            row.last_error = error[:2000]
            row.lease_owner = None
            row.lease_expires_at = None
            row.updated_at = now
            if row.attempts >= row.max_attempts:
                row.status = WorkStatus.DEAD_LETTER.value
                row.available_at = now
                return row.status
            delay = min(
                settings.worker_backoff_cap_seconds,
                settings.worker_backoff_base_seconds * (2 ** max(0, row.attempts - 1)),
            )
            row.status = WorkStatus.RETRY.value
            row.available_at = now + timedelta(seconds=delay)
            return row.status

    async def process_claimed(self, work: WorkItemResponse, *, lease_owner: str) -> bool:
        if work.work_type != WorkType.PAYPAL_DISPUTE_WEBHOOK.value or work.source_type != "PAYPAL_EVENT":
            self._dead_letter_now(
                work.work_uid, lease_owner=lease_owner, error="Unsupported work type/source"
            )
            return False

        with session_scope() as session:
            event = event_repo.get(session, work.source_id)
            event_missing = event is None
            event_processed = bool(event.processed) if event is not None else False
            payload = dict(event.payload or {}) if event is not None else {}

        if event_missing:
            self._dead_letter_now(
                work.work_uid, lease_owner=lease_owner, error="Source PayPal event not found"
            )
            return False
        if event_processed:
            self._complete(work.work_uid, lease_owner=lease_owner)
            return True

        resource = payload.get("resource") or {}
        dispute_id = resource.get("dispute_id") or resource.get("id")
        if not dispute_id or not str(dispute_id).startswith("PP-"):
            error = "Webhook resource did not expose a recognizable dispute id."
            with session_scope() as session:
                event = event_repo.get(session, work.source_id)
                if event:
                    event.processing_error = error
                    event.process_attempts = max(event.process_attempts, work.attempts)
            self._dead_letter_now(work.work_uid, lease_owner=lease_owner, error=error)
            return False

        try:
            # Different webhook rows can refer to the same PayPal dispute. Queue
            # row SKIP LOCKED alone does not serialize those rows, so guard the
            # authoritative GET + local sync by dispute id.
            async with dispute_sync_guard(str(dispute_id)):
                fresh = await disputes_client.get_dispute_details(str(dispute_id))
                case_service.sync_dispute_concurrency_safe(fresh)
        except Exception as exc:  # worker boundary intentionally catches provider/network/lock failures
            error = f"{type(exc).__name__}: {exc}"
            with session_scope() as session:
                event = event_repo.get(session, work.source_id)
                if event:
                    event.processing_error = error[:1000]
                    event.process_attempts = max(event.process_attempts, work.attempts)
            status = self._retry_or_dead_letter(
                work.work_uid, lease_owner=lease_owner, error=error
            )
            logger.warning("Work %s failed -> %s: %s", work.work_uid, status, error)
            return False

        with session_scope() as session:
            event = event_repo.get(session, work.source_id)
            if event:
                event.processed = True
                event.processing_error = None
                event.process_attempts = max(event.process_attempts, work.attempts)
                event.processed_at = utcnow()
        self._complete(work.work_uid, lease_owner=lease_owner)
        return True

    async def run_once(self, *, lease_owner: str | None = None) -> bool:
        owner = lease_owner or f"worker-{uuid.uuid4().hex[:12]}"
        work = self.claim_next(lease_owner=owner)
        if work is None:
            return False
        await self.process_claimed(work, lease_owner=owner)
        return True

    async def run_forever(self, *, lease_owner: str | None = None) -> None:
        owner = lease_owner or f"worker-{uuid.uuid4().hex[:12]}"
        while True:
            claimed = self.claim_next(lease_owner=owner)
            if claimed is None:
                await asyncio.sleep(settings.worker_poll_seconds)
                continue
            await self.process_claimed(claimed, lease_owner=owner)

    def requeue_dead_letter(self, work_uid: str) -> WorkItemResponse:
        with session_scope() as session:
            row = work_repo.get(session, work_uid, for_update=True)
            if row is None:
                raise ValueError(f"Unknown work item {work_uid}")
            if row.status != WorkStatus.DEAD_LETTER.value:
                raise ValueError("Only DEAD_LETTER work can be explicitly requeued")
            now = utcnow()
            row.status = WorkStatus.READY.value
            row.attempts = 0
            row.available_at = now
            row.lease_owner = None
            row.lease_expires_at = None
            row.last_error = None
            row.completed_at = None
            row.updated_at = now
            session.flush()
            return _response(row)

    def status(self) -> QueueStatusResponse:
        with session_scope() as session:
            counts = {
                status: int(
                    session.scalar(select(func.count()).select_from(WorkItem).where(WorkItem.status == status))
                    or 0
                )
                for status in ["READY", "LEASED", "RETRY", "COMPLETED", "DEAD_LETTER"]
            }
            oldest = session.scalar(
                select(func.min(WorkItem.available_at)).where(WorkItem.status.in_(["READY", "RETRY"]))
            )
            return QueueStatusResponse(
                ready=counts["READY"],
                leased=counts["LEASED"],
                retry=counts["RETRY"],
                completed=counts["COMPLETED"],
                dead_letter=counts["DEAD_LETTER"],
                oldest_available_at=_dt(oldest),
            )

    def list_recent(self, *, limit: int = 100) -> list[WorkItemResponse]:
        with session_scope() as session:
            return [_response(row) for row in work_repo.list_recent(session, limit=limit)]


work_service = DurableWorkService()
