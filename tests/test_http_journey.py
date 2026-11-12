"""HTTP-level journey.

This suite exists because a defect survived the service-level tests: the action
approval and execution routes were declared without type annotations, so FastAPI
parsed their request bodies as required query parameters. Service-level tests
called `action_engine` directly and passed; the shipped browser flow returned
422 for every approval. Anything user-visible must be asserted through the ASGI
application, not only through the service layer.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.db.base import Base
from backend.db.session import engine
from backend.main import app
from backend.paypal.http import set_simulator_for_testing
from backend.paypal.simulator import build_simulator


def _state_dir() -> Path:
    return Path(settings.database_url.removeprefix("sqlite:///")).resolve().parent


@pytest.fixture(autouse=True)
def _clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    (_state_dir() / "simulated-paypal-http.json").unlink(missing_ok=True)
    yield


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr("backend.paypal.http.simulated_transport_enabled", lambda: True)
    simulator = build_simulator(_state_dir() / "simulated-paypal-http.json")
    set_simulator_for_testing(simulator)
    with TestClient(app) as test_client:
        yield test_client
    set_simulator_for_testing(None)


def _prepare_case(client: TestClient) -> tuple[str, str, str]:
    synced = client.post("/api/cases/sync/PP-D-DEMO-1001")
    assert synced.status_code == 200, synced.text
    case_id = synced.json()["case_id"]
    assert synced.json()["simulated"] is True

    intake = client.post(
        f"/api/cases/{case_id}/intake",
        json={
            "intake_request_id": "INTAKE-HTTP-1",
            "created_by": "operator",
            "transcript": [
                {
                    "speaker": "customer",
                    "message": "The parcel never arrived and tracking still says pre-transit.",
                },
                {
                    "speaker": "merchant_agent",
                    "message": "Carrier scan shows delivery to the address on file.",
                },
            ],
        },
    )
    assert intake.status_code == 200, intake.text

    analysis = client.post(
        f"/api/cases/{case_id}/ai/analyze",
        json={"analysis_request_id": "AIR-HTTP-1", "requested_by": "operator"},
    )
    assert analysis.status_code == 200, analysis.text
    body = analysis.json()
    assert body["status"] == "COMPLETED", body

    safety = client.get(f"/api/cases/{case_id}/ai/analyses/{body['analysis_uid']}/safety")
    assert safety.status_code == 200, safety.text
    return case_id, body["analysis_uid"], safety.json()["safety_uid"]


def test_approval_and_execution_accept_json_request_bodies(client: TestClient):
    case_id, analysis_uid, safety_uid = _prepare_case(client)

    approval = client.post(
        f"/api/cases/{case_id}/actions/approve",
        json={
            "action_request_id": "ACTREQ-HTTP-1",
            "approved_by": "human-reviewer",
            "analysis_uid": analysis_uid,
            "safety_uid": safety_uid,
            "payload": {"action_type": "SEND_MESSAGE", "message": "Checking the carrier scan now."},
        },
    )
    assert approval.status_code == 200, approval.text
    approved = approval.json()
    assert approved["execution_status"] == "NOT_STARTED"
    assert approved["payload"]["message"] == "Checking the carrier scan now."

    execution = client.post(
        f"/api/cases/{case_id}/actions/{approved['action_uid']}/execute",
        json={"approval_hash": approved["approval_hash"]},
    )
    assert execution.status_code == 200, execution.text
    result = execution.json()
    assert result["execution_status"] == "EXECUTED"
    assert result["result_status"] in {"executed", "executed_sync_pending"}

    history = client.get(f"/api/cases/{case_id}/actions")
    assert history.status_code == 200
    assert history.json()[0]["execution_status"] == "EXECUTED"

    trail = client.get(f"/api/cases/{case_id}/actions/{approved['action_uid']}/reconciliations")
    assert trail.status_code == 200
    assert trail.json() == []


def test_execution_rejects_a_mismatched_approval_hash(client: TestClient):
    case_id, analysis_uid, safety_uid = _prepare_case(client)
    approval = client.post(
        f"/api/cases/{case_id}/actions/approve",
        json={
            "action_request_id": "ACTREQ-HTTP-WRONG-HASH",
            "approved_by": "human-reviewer",
            "analysis_uid": analysis_uid,
            "safety_uid": safety_uid,
            "payload": {"action_type": "SEND_MESSAGE", "message": "Status update."},
        },
    ).json()

    response = client.post(
        f"/api/cases/{case_id}/actions/{approval['action_uid']}/execute",
        json={"approval_hash": "0" * 64},
    )
    assert response.status_code == 409


def test_explanation_is_exportable_over_http(client: TestClient):
    case_id, analysis_uid, _safety_uid = _prepare_case(client)
    response = client.get(f"/api/cases/{case_id}/ai/analyses/{analysis_uid}/explain")
    assert response.status_code == 200, response.text
    document = response.json()
    assert document["analysis_uid"] == analysis_uid
    assert document["verdict"]["effective_action"]
    assert document["next_step"]
    # The export must stand alone: grounding paths, findings and the policy
    # threshold all have to be present without further API calls.
    assert document["grounding"]
    assert document["confidence"]["required_minimum"] > 0
    course = client.get(f"/api/cases/{case_id}/ai/analyses/AIR-NOT-REAL/explain")
    assert course.status_code == 404


def test_evidence_file_upload_works_with_authentication_disabled(client: TestClient):
    """The demo profile runs with auth disabled; upload must still work there."""
    case_id, _analysis_uid, _safety_uid = _prepare_case(client)
    payload = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
    response = client.post(
        f"/api/cases/{case_id}/files",
        files={"file": ("delivery-note.pdf", payload, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["original_name"] == "delivery-note.pdf"
    assert body["sha256"] == __import__("hashlib").sha256(payload).hexdigest()
    assert body["created_by"], "an upload must always record an actor"

    listed = client.get(f"/api/cases/{case_id}/files")
    assert listed.status_code == 200
    assert [item["file_uid"] for item in listed.json()] == [body["file_uid"]]


def test_unknown_dispute_id_is_a_client_error_not_a_server_error(client: TestClient):
    response = client.post("/api/cases/sync/PP-D-DOES-NOT-EXIST")
    assert response.status_code == 404, response.text
    assert "no dispute" in response.json()["detail"].lower()


def test_unreachable_paypal_is_a_gateway_error_and_changes_nothing(client: TestClient, monkeypatch):
    from backend.paypal.errors import PayPalTransportError

    async def fail(_dispute_id: str):
        raise PayPalTransportError("simulated network failure")

    monkeypatch.setattr("backend.api.cases.disputes_client.get_dispute_details", fail)
    response = client.post("/api/cases/sync/PP-D-DEMO-1001")
    assert response.status_code == 502, response.text
    assert "not changed" in response.json()["detail"].lower()
    # No case may be created from a failed read.
    assert client.get("/api/cases").json() == []


def test_case_board_lists_every_case_with_its_facts(client: TestClient):
    case_id, _analysis_uid, _safety_uid = _prepare_case(client)
    board = client.get("/api/cases")
    assert board.status_code == 200
    rows = board.json()
    assert [row["case_id"] for row in rows] == [case_id]
    assert rows[0]["simulated"] is True
    assert rows[0]["verified_facts"], "the board must expose current PayPal facts"
    assert rows[0]["evidence_set_revision"] >= 1

    case_id, analysis_uid, safety_uid = _prepare_case(client)
    # The reference reasoner recommends SEND_MESSAGE for a contradicted case; a
    # money-moving payload must be refused before it is ever persisted.
    response = client.post(
        f"/api/cases/{case_id}/actions/approve",
        json={
            "action_request_id": "ACTREQ-HTTP-MISMATCH",
            "approved_by": "human-reviewer",
            "analysis_uid": analysis_uid,
            "safety_uid": safety_uid,
            "payload": {
                "action_type": "MAKE_OFFER",
                "offer_type": "REFUND",
                "offer_amount": {"currency_code": "USD", "value": "1.00"},
            },
        },
    )
    assert response.status_code == 422
