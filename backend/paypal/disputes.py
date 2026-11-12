from __future__ import annotations

import re

from backend.paypal.http import paypal_http

_DISPUTE_ID = re.compile(r"^PP-[A-Za-z0-9_-]{3,120}$")


def _id(value: str) -> str:
    if not _DISPUTE_ID.fullmatch(str(value)):
        raise ValueError("invalid PayPal dispute id")
    return str(value)


class DisputesClient:
    async def list_disputes(self):
        return await paypal_http.request("GET", "/v1/customer/disputes", operation="list_disputes")

    async def get_dispute_details(self, dispute_id):
        dispute_id = _id(dispute_id)
        return await paypal_http.request("GET", f"/v1/customer/disputes/{dispute_id}", operation="get_dispute")

    async def send_message(self, dispute_id, message):
        dispute_id = _id(dispute_id)
        return await paypal_http.request(
            "POST",
            f"/v1/customer/disputes/{dispute_id}/send-message",
            json_body={"message": message},
            idempotent=False,
            operation="send_message",
        )

    async def make_offer(self, dispute_id, payload):
        dispute_id = _id(dispute_id)
        return await paypal_http.request(
            "POST",
            f"/v1/customer/disputes/{dispute_id}/make-offer",
            json_body=payload,
            idempotent=False,
            operation="make_offer",
        )

    async def accept_claim(self, dispute_id, payload):
        dispute_id = _id(dispute_id)
        return await paypal_http.request(
            "POST",
            f"/v1/customer/disputes/{dispute_id}/accept-claim",
            json_body=payload,
            idempotent=False,
            operation="accept_claim",
        )

    async def provide_evidence(self, dispute_id, payload, *, file_parts=None):
        dispute_id = _id(dispute_id)
        return await paypal_http.multipart_input(
            "POST",
            f"/v1/customer/disputes/{dispute_id}/provide-evidence",
            input_body=payload,
            file_parts=file_parts,
            idempotent=False,
            operation="provide_dispute_evidence",
        )

    async def appeal(self, dispute_id, payload, *, file_parts=None):
        dispute_id = _id(dispute_id)
        return await paypal_http.multipart_input(
            "POST",
            f"/v1/customer/disputes/{dispute_id}/appeal",
            input_body=payload,
            file_parts=file_parts,
            idempotent=False,
            operation="appeal_dispute",
        )

    async def escalate(self, dispute_id, note):
        dispute_id = _id(dispute_id)
        return await paypal_http.request(
            "POST",
            f"/v1/customer/disputes/{dispute_id}/escalate",
            json_body={"note": note},
            idempotent=False,
            operation="escalate",
        )

    async def provide_supporting_info(self, dispute_id, notes):
        dispute_id = _id(dispute_id)
        return await paypal_http.request(
            "POST",
            f"/v1/customer/disputes/{dispute_id}/provide-supporting-info",
            json_body={"notes": notes},
            idempotent=False,
            operation="supporting_info",
        )

    async def acknowledge_return_item(self, dispute_id, payload):
        dispute_id = _id(dispute_id)
        return await paypal_http.request(
            "POST",
            f"/v1/customer/disputes/{dispute_id}/acknowledge-return-item",
            json_body=payload,
            idempotent=False,
            operation="acknowledge_return",
        )


disputes_client = DisputesClient()
