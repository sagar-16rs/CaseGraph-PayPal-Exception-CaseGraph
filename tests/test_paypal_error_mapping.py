"""PayPal HTTP error mapping at the money boundary.

The classification that matters is not the HTTP status itself — it is whether
CaseGraph is allowed to try again. A 401/403/404/429 means PayPal did not process
the write, so the approval fails definitively and needs a new human approval. A 5xx
or a transport failure is *ambiguous*: the write may have landed, so the action must
stay in UNKNOWN_OUTCOME and never be retried automatically.
"""

from __future__ import annotations

from copy import deepcopy

import pytest
from fastapi import HTTPException

from backend.actions.schemas import ActionExecuteRequest
from backend.db.base import Base
from backend.db.session import engine, session_scope
from backend.paypal.errors import PayPalAPIError, PayPalTransportError
from backend.repositories import action_approvals as approval_repo
from backend.services.actions import action_engine
from tests.action_fixtures import BASE, prepare, send_message_payload


@pytest.fixture(autouse=True)
def _clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


async def _approved_action(suffix: str):
    return await prepare(deepcopy(BASE), "SEND_MESSAGE", send_message_payload(), suffix=suffix)


def _failing(status: int):
    async def fail(_dispute_id, _message):
        raise PayPalAPIError("provider rejected the write", status, {"name": f"ERR_{status}"})

    return fail


async def _timing_out(_dispute_id, _message):
    raise PayPalTransportError("read timeout after request was sent")


CLIENT_REJECTIONS = [401, 403, 404, 422, 429]
SERVER_AMBIGUITIES = [500, 502, 503, 504]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", CLIENT_REJECTIONS)
async def test_client_rejections_fail_definitively_and_are_not_retried(status, monkeypatch):
    case_id, _analysis, _safety, approval = await _approved_action(f"ERR-{status}")
    calls = {"n": 0}

    async def get_details(_dispute_id):
        return deepcopy(BASE)

    async def send(_dispute_id, _message):
        calls["n"] += 1
        raise PayPalAPIError("provider rejected the write", status, {"name": f"ERR_{status}"})

    monkeypatch.setattr("backend.services.actions.disputes_client.get_dispute_details", get_details)
    monkeypatch.setattr("backend.services.actions.disputes_client.send_message", send)

    with pytest.raises(PayPalAPIError):
        await action_engine.execute(
            case_id, approval.action_uid, ActionExecuteRequest(approval_hash=approval.approval_hash)
        )

    with session_scope() as session:
        row = approval_repo.get_by_uid(session, approval.action_uid)
        assert row is not None
        assert row.execution_status == "FAILED"
        assert row.paypal_response_status == status

    # A terminal failure requires a fresh human approval; the engine must not resend.
    with pytest.raises(HTTPException) as excinfo:
        await action_engine.execute(
            case_id, approval.action_uid, ActionExecuteRequest(approval_hash=approval.approval_hash)
        )
    assert excinfo.value.status_code == 409
    assert calls["n"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", SERVER_AMBIGUITIES)
async def test_server_errors_are_ambiguous_and_block_further_writes(status, monkeypatch):
    case_id, _analysis, _safety, approval = await _approved_action(f"AMB-{status}")
    calls = {"n": 0}

    async def get_details(_dispute_id):
        return deepcopy(BASE)

    async def send(_dispute_id, _message):
        calls["n"] += 1
        raise PayPalAPIError("provider failed mid-write", status, {"name": "SERVICE_UNAVAILABLE"})

    monkeypatch.setattr("backend.services.actions.disputes_client.get_dispute_details", get_details)
    monkeypatch.setattr("backend.services.actions.disputes_client.send_message", send)

    with pytest.raises(PayPalAPIError):
        await action_engine.execute(
            case_id, approval.action_uid, ActionExecuteRequest(approval_hash=approval.approval_hash)
        )

    with session_scope() as session:
        row = approval_repo.get_by_uid(session, approval.action_uid)
        assert row is not None
        assert row.execution_status == "UNKNOWN_OUTCOME"

    # Never retried: the second attempt is refused *before* any PayPal contact.
    with pytest.raises(HTTPException) as excinfo:
        await action_engine.execute(
            case_id, approval.action_uid, ActionExecuteRequest(approval_hash=approval.approval_hash)
        )
    assert excinfo.value.status_code == 409
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_transport_timeout_is_ambiguous(monkeypatch):
    case_id, _analysis, _safety, approval = await _approved_action("ERR-TIMEOUT")

    async def get_details(_dispute_id):
        return deepcopy(BASE)

    monkeypatch.setattr("backend.services.actions.disputes_client.get_dispute_details", get_details)
    monkeypatch.setattr("backend.services.actions.disputes_client.send_message", _timing_out)

    with pytest.raises(PayPalTransportError):
        await action_engine.execute(
            case_id, approval.action_uid, ActionExecuteRequest(approval_hash=approval.approval_hash)
        )

    with session_scope() as session:
        row = approval_repo.get_by_uid(session, approval.action_uid)
        assert row is not None
        assert row.execution_status == "UNKNOWN_OUTCOME"


@pytest.mark.asyncio
async def test_ambiguous_outcome_blocks_a_second_approval_on_the_same_case(monkeypatch):
    case_id, analysis, safety, approval = await _approved_action("ERR-BLOCK")

    async def get_details(_dispute_id):
        return deepcopy(BASE)

    async def send(_dispute_id, _message):
        raise PayPalTransportError("connection reset")

    monkeypatch.setattr("backend.services.actions.disputes_client.get_dispute_details", get_details)
    monkeypatch.setattr("backend.services.actions.disputes_client.send_message", send)

    with pytest.raises(PayPalTransportError):
        await action_engine.execute(
            case_id, approval.action_uid, ActionExecuteRequest(approval_hash=approval.approval_hash)
        )

    from backend.actions.schemas import ActionApprovalRequest

    with pytest.raises(HTTPException) as excinfo:
        await action_engine.approve(
            case_id,
            ActionApprovalRequest(
                action_request_id="ACTREQ-ERR-BLOCK-SECOND",
                approved_by="human-reviewer",
                analysis_uid=analysis.analysis_uid,
                safety_uid=safety.safety_uid,
                payload=send_message_payload(),
            ),
        )
    assert excinfo.value.status_code == 409


def test_transport_preserves_provider_status_and_body(monkeypatch):
    """The transport layer must not flatten provider errors into a generic failure."""

    class _Response:
        def __init__(self, status, payload):
            self.status_code = status
            self.content = b"{}"
            self._payload = payload

        def json(self):
            return self._payload

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def request(self, *args, **kwargs):
            return _Response(429, {"name": "RATE_LIMIT_REACHED", "debug_id": "abc"})

    import backend.paypal.http as http_module

    monkeypatch.setattr(http_module.httpx, "AsyncClient", _Client)

    async def token():
        return "test-token"

    monkeypatch.setattr(http_module.paypal_auth, "access_token", token)
    monkeypatch.setattr(http_module, "simulated_transport_enabled", lambda: False)

    import asyncio

    with pytest.raises(PayPalAPIError) as excinfo:
        asyncio.run(http_module.paypal_http.request("POST", "/v1/customer/disputes/PP-D-X/send-message"))
    assert excinfo.value.status_code == 429
    assert excinfo.value.body.get("name") == "RATE_LIMIT_REACHED"
