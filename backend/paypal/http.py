from __future__ import annotations

import json
import re
from typing import Any

import httpx

from backend.config import settings
from backend.paypal.auth import paypal_auth
from backend.paypal.errors import PayPalAPIError, PayPalTransportError
from backend.paypal.simulator import SimulatedPayPal, build_simulator

_DISPUTE_PATH = re.compile(r"^/v1/customer/disputes/(?P<id>[A-Za-z0-9_-]+)")

#: Operations the simulated transport treats as dispute writes.
_SIMULATED_WRITES = {
    "send_message",
    "make_offer",
    "accept_claim",
    "provide_dispute_evidence",
    "appeal_dispute",
    "escalate",
    "supporting_info",
    "acknowledge_return",
}

_simulator_override: SimulatedPayPal | None = None


def simulated_transport_enabled() -> bool:
    return settings.paypal_transport == "simulated"


def get_simulator() -> SimulatedPayPal:
    """Return the process-wide simulated PayPal sandbox.

    The instance is injectable so tests can use a temporary state file without
    mutating global settings.
    """
    global _simulator_override
    if _simulator_override is not None:
        return _simulator_override
    return build_simulator(settings.simulation_state_path, fault=settings.simulated_fault)


def set_simulator_for_testing(simulator: SimulatedPayPal | None) -> None:
    global _simulator_override
    _simulator_override = simulator


def _dispute_id(path: str) -> str:
    match = _DISPUTE_PATH.match(path)
    if not match:
        raise PayPalAPIError(f"simulated transport cannot resolve a dispute id from {path!r}", 400, {})
    return match.group("id")


class PayPalHTTP:
    async def request(self, method, path, *, json_body=None, idempotent=True, operation="paypal"):
        if simulated_transport_enabled():
            return self._simulated(operation, path, json_body)

        token=await paypal_auth.access_token()
        try:
            async with httpx.AsyncClient(timeout=settings.paypal_timeout_seconds) as c: r=await c.request(method,settings.paypal_base_url+path,headers={'Authorization':f'Bearer {token}','Accept':'application/json','Content-Type':'application/json'},json=json_body)
        except httpx.HTTPError as e: raise PayPalTransportError(f'{operation}: {e}') from e
        body={}
        if r.content:
            try: body=r.json()
            except Exception: body={'text':r.text}
        if r.status_code>=400: raise PayPalAPIError(f'{operation} failed',r.status_code,body)
        return body

    async def multipart_input(self, method, path, *, input_body:dict[str,Any], file_parts:list[tuple[str,str,bytes,str]]|None=None,idempotent=False,operation='paypal'):
        if simulated_transport_enabled():
            return self._simulated(operation, path, input_body)

        token=await paypal_auth.access_token(); payload=json.dumps(input_body,separators=(',',':')); files={'input':(None,payload,'application/json')}
        for field,filename,content,mime in file_parts or []: files[field]=(filename,content,mime)
        try:
            async with httpx.AsyncClient(timeout=settings.paypal_multipart_timeout_seconds) as c: r=await c.request(method,settings.paypal_base_url+path,headers={'Authorization':f'Bearer {token}','Accept':'application/json'},files=files)
        except httpx.HTTPError as e: raise PayPalTransportError(f'{operation}: {e}') from e
        try: body=r.json() if r.content else {}
        except Exception: body={'text':r.text}
        if r.status_code>=400: raise PayPalAPIError(f'{operation} failed',r.status_code,body)
        return body

    # ----------------------------------------------------------- simulation
    @staticmethod
    def _simulated(operation: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        simulator = get_simulator()
        if operation == "verify_webhook":
            return simulator.verify_webhook_signature()
        if operation == "list_disputes":
            return simulator.list_disputes()
        if operation == "get_dispute":
            return simulator.get_dispute(_dispute_id(path))
        if operation in _SIMULATED_WRITES:
            # Reuse the real operation name so fault injection and the audit
            # trail describe the same action the live path would perform.
            return simulator.write(operation, _dispute_id(path), body)
        raise PayPalAPIError(f"simulated transport does not implement {operation!r}", 501, {})


paypal_http=PayPalHTTP()
