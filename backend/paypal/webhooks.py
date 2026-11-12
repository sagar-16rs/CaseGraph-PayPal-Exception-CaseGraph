from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from backend.config import settings
from backend.db.models import PayPalEvent
from backend.db.session import session_scope
from backend.paypal.http import paypal_http
from backend.repositories import events as event_repo
from backend.work.service import work_service

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


async def _verify(request: Request, body: dict) -> bool:
    # Synthetic webhook injection is permitted only when verification is
    # explicitly disabled in local/test mode. Production startup refuses that
    # configuration in backend.main and scripts/doctor.py.
    if not settings.paypal_webhook_verify:
        return True

    headers = {key.lower(): value for key, value in request.headers.items()}
    required = [
        "paypal-auth-algo",
        "paypal-cert-url",
        "paypal-transmission-id",
        "paypal-transmission-sig",
        "paypal-transmission-time",
    ]
    if any(key not in headers for key in required) or not settings.paypal_webhook_id:
        return False

    payload = {
        "auth_algo": headers["paypal-auth-algo"],
        "cert_url": headers["paypal-cert-url"],
        "transmission_id": headers["paypal-transmission-id"],
        "transmission_sig": headers["paypal-transmission-sig"],
        "transmission_time": headers["paypal-transmission-time"],
        "webhook_id": settings.paypal_webhook_id,
        "webhook_event": body,
    }
    try:
        result = await paypal_http.request(
            "POST",
            "/v1/notifications/verify-webhook-signature",
            json_body=payload,
            operation="verify_webhook",
        )
        return result.get("verification_status") == "SUCCESS"
    except Exception:
        # Authenticity uncertainty is fail-closed. PayPal will redeliver a
        # non-2xx webhook later rather than CaseGraph accepting an unverified event.
        return False


@router.post("/paypal")
async def paypal_webhook(request: Request):
    body = await request.json()
    event_id = body.get("id")
    if not event_id:
        raise HTTPException(status_code=400, detail="missing event id")
    if not await _verify(request, body):
        raise HTTPException(status_code=400, detail="invalid PayPal webhook signature")

    # Event receipt and its durable work row commit in ONE transaction before the
    # 2xx response. A duplicate delivery also repairs a missing work row before it
    # is acknowledged, closing the historical event-commit/enqueue-crash gap.
    duplicate = False
    with session_scope() as session:
        event = event_repo.get_by_event_id(session, event_id)
        if event is None:
            resource = body.get("resource") or {}
            resource_id = resource.get("dispute_id") or resource.get("id")
            event = PayPalEvent(
                event_id=event_id,
                event_type=body.get("event_type", "UNKNOWN"),
                resource_id=resource_id,
                payload=body,
            )
            event_repo.add(session, event)
            session.flush()
        else:
            duplicate = True
        work_service.enqueue_paypal_event(session, event_id)

    return {
        "status": "ignored_duplicate" if duplicate else "accepted",
        "event_id": event_id,
    }
