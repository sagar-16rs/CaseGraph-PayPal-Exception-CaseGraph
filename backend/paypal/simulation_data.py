"""Deterministic PayPal dispute fixtures for the simulated sandbox.

These payloads follow the shape of `GET /v1/customer/disputes/{id}` closely
enough for the real normalization, validation, and safety code paths to run
unmodified. They exist so CaseGraph can be demonstrated end to end without a
PayPal developer account, and they are never used when the live transport is
selected.
"""

from __future__ import annotations

from typing import Any

_SANDBOX_STAMP = "2026-11-08T09:00:00Z"


def _links(*rels: str) -> list[dict[str, str]]:
    return [{"rel": rel, "method": "POST", "href": f"https://simulated.invalid/{rel}"} for rel in rels]


SELLER_RESPONSE_LINKS = (
    "send-message",
    "provide-evidence",
    "make-offer",
    "accept-claim",
    "escalate",
    "provide-supporting-info",
)


def _dispute(
    *,
    dispute_id: str,
    status: str,
    reason: str,
    amount: str,
    currency: str,
    transition: str,
    allowed_refund: str | None = None,
    links: tuple[str, ...] = SELLER_RESPONSE_LINKS,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dispute_id": dispute_id,
        "dispute_state": "REQUIRED_ACTION",
        "dispute_life_cycle_stage": transition,
        "status": status,
        "reason": reason,
        "dispute_amount": {"currency_code": currency, "value": amount},
        "seller_response_due_date": "2026-11-22T00:00:00Z",
        "create_time": _SANDBOX_STAMP,
        "update_time": _SANDBOX_STAMP,
        "disputed_transactions": [
            {
                "seller_transaction_id": f"TX-{dispute_id[-4:]}",
                "buyer_transaction_id": f"BUY-{dispute_id[-4:]}",
                "transaction_status": "COMPLETED",
            }
        ],
        "allowed_response_options": {
            "make_offer": {
                "offer_types": ["REFUND", "REFUND_WITH_RETURN", "REPLACEMENT_WITHOUT_REFUND"]
            },
            "accept_claim": {"accept_claim_types": ["REFUND", "PARTIAL_REFUND"]},
            "acknowledge_return_item": {
                "acknowledgement_types": [
                    "ITEM_RECEIVED",
                    "ITEM_NOT_RECEIVED",
                    "DAMAGED",
                    "EMPTY_PACKAGE_OR_DIFFERENT",
                    "MISSING_ITEMS",
                ]
            },
        },
        "links": _links(*links),
    }
    if allowed_refund is not None:
        payload["refund_details"] = {
            "allowed_refund_amount": {"currency_code": currency, "value": allowed_refund}
        }
    return payload


#: Three disputes that exercise distinct safety outcomes: a contradictory case,
#: an evidence gap, and a case where the only defensible recommendation is to
#: abstain.
DEMO_DISPUTES: list[dict[str, Any]] = [
    _dispute(
        dispute_id="PP-D-DEMO-1001",
        status="WAITING_FOR_SELLER_RESPONSE",
        reason="MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        amount="129.00",
        currency="USD",
        transition="INQUIRY",
        allowed_refund="129.00",
    ),
    _dispute(
        dispute_id="PP-D-DEMO-1002",
        status="WAITING_FOR_SELLER_RESPONSE",
        reason="MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED",
        amount="64.50",
        currency="USD",
        transition="INQUIRY",
        allowed_refund="40.00",
    ),
    _dispute(
        dispute_id="PP-D-DEMO-1003",
        status="UNDER_REVIEW",
        reason="UNAUTHORIZED",
        amount="310.00",
        currency="EUR",
        transition="CHARGEBACK",
        links=("send-message", "provide-supporting-info"),
    ),
]


#: Reference support evidence used by `scripts/demo_seed.py`. Every entry is a
#: customer/merchant statement that the reasoning layer must treat as a claim.
DEMO_EVIDENCE: dict[str, dict[str, Any]] = {
    "PP-D-DEMO-1001": {
        "transcript": [
            {
                "speaker": "customer",
                "message": "The parcel never arrived. I have been waiting three weeks and the tracking page still says pre-transit.",
            },
            {
                "speaker": "merchant_agent",
                "message": "We shipped order 88-4211 on 2 November. Carrier scan shows delivery to the address on file on 5 November at 14:12.",
            },
        ],
        "merchant_notes": "Fulfilment record notes tracking number 9400111899223857260001 and signed delivery receipt.",
    },
    "PP-D-DEMO-1002": {
        "transcript": [
            {
                "speaker": "customer",
                "message": "The item arrived scratched and the finish does not match the product photos at all.",
            },
            {
                "speaker": "merchant_agent",
                "message": "We have no record of a damage report for this order and no photographs were attached to the support thread.",
            },
        ],
        "merchant_notes": "No delivery proof or damage claim received from the buyer.",
    },
    "PP-D-DEMO-1003": {
        "transcript": [
            {
                "speaker": "customer",
                "message": "I did not authorise this charge and I do not recognise the merchant.",
            }
        ],
        "merchant_notes": None,
    },
}


def demo_state() -> dict[str, Any]:
    return {
        "disputes": {item["dispute_id"]: dict(item) for item in DEMO_DISPUTES},
        "messages": {item["dispute_id"]: [] for item in DEMO_DISPUTES},
        "revision": {item["dispute_id"]: 1 for item in DEMO_DISPUTES},
    }
