from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.paypal.disputes import disputes_client
from backend.paypal.errors import PayPalAPIError, PayPalTransportError
from backend.services.cases import case_service
from backend.work.dispute_lock import DisputeSyncLockTimeout, dispute_sync_guard

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.get("")
def list_cases():
    # One batched projection instead of a per-case detail read; the board shows
    # every case, so an N+1 here is felt immediately.
    return case_service.list_details()


@router.get("/{case_id}")
def get_case(case_id: str):
    detail = case_service.detail(case_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="case not found")
    return detail


@router.post("/sync/{paypal_dispute_id}")
async def sync(paypal_dispute_id: str):
    # Manual/API sync participates in the same per-dispute serialization as the
    # durable webhook worker. This prevents a user-triggered refresh from racing a
    # worker and committing an older PayPal observation last.
    try:
        async with dispute_sync_guard(paypal_dispute_id):
            payload = await disputes_client.get_dispute_details(paypal_dispute_id)
            case_id = case_service.sync_dispute_concurrency_safe(payload)
    except DisputeSyncLockTimeout as exc:
        raise HTTPException(status_code=409, detail="dispute synchronization is already in progress") from exc
    except PayPalAPIError as exc:
        # A mistyped or unknown dispute id is a client error, not a server fault.
        # Before this mapping FastAPI turned it into an opaque 500 and the operator
        # had no way to tell a bad id from a broken deployment.
        if exc.status_code in {400, 404, 422}:
            raise HTTPException(
                status_code=404,
                detail="PayPal has no dispute with that identifier. Check the id and try again.",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"PayPal rejected the dispute lookup ({exc.status_code}). Case state was not changed.",
        ) from exc
    except PayPalTransportError as exc:
        raise HTTPException(
            status_code=502,
            detail="PayPal could not be reached. Case state was not changed; retry the sync later.",
        ) from exc
    return case_service.detail(case_id)
