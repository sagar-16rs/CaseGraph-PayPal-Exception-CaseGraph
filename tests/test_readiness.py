"""Evidence-readiness validation.

Covers the five evidence situations an operator actually meets — present, missing,
unknown, contradicted, misleading — and guards the honesty boundary: coverage is
labelled as coverage, never as a probability of winning the dispute.

The requirement table is CaseGraph's own judgement (PayPal publishes no normative
per-reason checklist), so the tests assert *internal* consistency and the documented
behaviour rather than pretending to verify PayPal policy.
"""

from __future__ import annotations

import json

import pytest

from backend.services.readiness import REASON_REQUIREMENTS, assess_readiness

PAYPAL_REASONS = [
    "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
    "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED",
    "UNAUTHORIZED",
    "CREDIT_NOT_PROCESSED",
    "DUPLICATE_TRANSACTION",
    "INCORRECT_AMOUNT",
    "PAYMENT_BY_OTHER_MEANS",
    "CANCELED_RECURRING_BILLING",
]


def _assess(reason: str, evidence_texts: list[str], *, nodes=None, contradictions: int = 0):
    return assess_readiness(
        reason=reason,
        evidence=[{"source_ref": f"E-{i}", "content": text} for i, text in enumerate(evidence_texts)],
        nodes=nodes or [],
        available_actions=["PROVIDE_EVIDENCE", "SEND_MESSAGE"],
        contradictions=contradictions,
    )


def _status(result, code: str) -> str:
    return next(item["status"] for item in result["requirements"] if item["code"] == code)


def test_every_paypal_reason_code_has_a_requirement_set():
    for reason in PAYPAL_REASONS:
        assert reason in REASON_REQUIREMENTS, f"{reason} has no requirement mapping"
        requirements = REASON_REQUIREMENTS[reason]
        assert requirements, f"{reason} maps to an empty list"
        assert any(item["critical"] == "yes" for item in requirements), f"{reason} has no critical requirement"
        for item in requirements:
            assert item["signals"] and item["label"] and item["detail"]


def test_unknown_reason_degrades_to_no_requirements_rather_than_guessing():
    result = _assess("SOMETHING_PAYPAL_ADDED_LATER", ["some evidence"])
    assert result["requirements"] == []
    assert result["coverage"] is None
    assert "does not publish" in result["summary"]


def test_present_evidence_satisfies_the_requirement():
    result = _assess(
        "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        ["Carrier scan shows delivery to the address on file; tracking number 9400."],
    )
    assert _status(result, "proof_of_fulfilment") == "present"
    assert result["coverage"] is not None and result["coverage"] > 0


def test_missing_evidence_node_marks_the_requirement_missing_even_if_text_mentions_it():
    result = _assess(
        "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        ["Carrier scan shows delivery on the tracking page."],
        nodes=[
            {
                "node_type": "MISSING_EVIDENCE",
                "title": "Delivery proof absent",
                "statement": "No carrier scan or tracking number is attached.",
            }
        ],
    )
    assert _status(result, "proof_of_fulfilment") == "missing"


def test_negated_evidence_is_not_counted_as_present():
    """The easiest way a keyword checklist lies: 'no delivery proof was provided'."""
    result = _assess(
        "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        ["No delivery proof was provided and no tracking number exists for this order."],
    )
    assert _status(result, "proof_of_fulfilment") == "missing"


def test_unrelated_evidence_left_the_requirement_unknown():
    result = _assess(
        "UNAUTHORIZED",
        ["The buyer opened the case on a Tuesday and asked for a call back."],
    )
    assert _status(result, "customer_recognition") == "unknown"


def test_contradicted_when_the_file_supports_it_but_the_graph_records_a_conflict():
    result = _assess(
        "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        ["Carrier scan shows delivery to the address on file."],
        contradictions=1,
    )
    assert _status(result, "proof_of_fulfilment") == "contradicted"
    assert "contradicted" in result["summary"]


def test_no_evidence_at_all_reports_every_requirement_missing():
    result = _assess("MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED", [])
    assert all(item["status"] == "missing" for item in result["requirements"])
    assert result["coverage"] == 0.0


def test_readiness_is_never_presented_as_a_win_probability():
    result = _assess(
        "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        ["Carrier scan shows delivery to the address on file."],
    )
    rendered = json.dumps(result).lower()
    for forbidden in ("probability", "win rate", "win-rate", "likelihood", "chance of winning", "predict"):
        assert forbidden not in rendered, f"readiness output contains {forbidden!r}"
    assert result["basis"].startswith("deterministic")


def test_coverage_counts_only_present_critical_requirements():
    result = _assess(
        "UNAUTHORIZED",
        ["Device fingerprint and IP address match the buyer's previous three orders."],
    )
    critical = [item for item in result["requirements"] if item["critical"]]
    present = [item for item in critical if item["status"] == "present"]
    assert result["coverage"] == round(len(present) / len(critical), 2)
    # Delivery evidence is still missing from that text.
    assert _status(result, "delivery_to_buyer") in {"unknown", "missing"}
