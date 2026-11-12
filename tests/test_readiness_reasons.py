"""Per-reason readiness coverage and ambiguous-signal behaviour.

Two properties are asserted here:

1. Every PayPal dispute reason has a requirement set that a genuinely complete
   evidence pack can satisfy — otherwise the checklist would be unusable.
2. Ambiguity resolves conservatively. When a document both affirms and negates the
   same signal ("delivery confirmed, but no tracking number"), CaseGraph must not
   claim the requirement is met.
"""

from __future__ import annotations

import pytest

from backend.services.readiness import REASON_REQUIREMENTS, assess_readiness

#: A realistic, complete evidence pack per reason. Written to satisfy every signal
#: without negation, which is exactly what the "present" path must detect.
COMPLETE_EVIDENCE = {
    "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": (
        "Carrier scan confirms delivery to the address on file. Tracking number 9400111899223857260001. "
        "Order 88-4211 invoice attached."
    ),
    "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": (
        "Photographs record the item condition as packed. The listing description and specification the "
        "buyer purchased against are attached."
    ),
    "UNAUTHORIZED": (
        "Device fingerprint and IP address match the buyer account, and prior order history shows three "
        "purchases. The parcel was delivered to the address on file."
    ),
    "CREDIT_NOT_PROCESSED": (
        "Refund transaction ID 5O190127TN364715T was processed on 3 November; the reversal reference is attached."
    ),
    "DUPLICATE_TRANSACTION": (
        "Both transaction identifiers are listed, and only one charge corresponds to the order."
    ),
    "INCORRECT_AMOUNT": (
        "The invoice shows the order total, tax and shipping; the stated amount matches the price breakdown."
    ),
    "PAYMENT_BY_OTHER_MEANS": (
        "The buyer confirmed in writing that they paid by bank transfer on 2 November, and the invoice is marked paid."
    ),
    "CANCELED_RECURRING_BILLING": (
        "The subscription state at charge time was active. The renewal notice was sent on 28 October and billing "
        "occurred on 1 November."
    ),
}


def _assess(reason: str, texts: list[str], *, contradictions: int = 0, nodes=None):
    return assess_readiness(
        reason=reason,
        evidence=[{"source_ref": f"E-{i}", "content": t} for i, t in enumerate(texts)],
        nodes=nodes or [],
        available_actions=["PROVIDE_EVIDENCE", "PROVIDE_SUPPORTING_INFO", "SEND_MESSAGE"],
        contradictions=contradictions,
    )


def test_every_reason_in_the_table_has_a_complete_pack_fixture():
    assert set(COMPLETE_EVIDENCE) == set(REASON_REQUIREMENTS), "fixtures drifted from the requirement table"


@pytest.mark.parametrize("reason", sorted(COMPLETE_EVIDENCE))
def test_a_complete_evidence_pack_satisfies_every_critical_requirement(reason):
    result = _assess(reason, [COMPLETE_EVIDENCE[reason]])
    critical = [item for item in result["requirements"] if item["critical"]]
    assert critical, f"{reason} has no critical requirement"
    unmet = [item for item in critical if item["status"] != "present"]
    assert not unmet, f"{reason}: {[(i['code'], i['status']) for i in unmet]}"
    assert result["coverage"] == 1.0
    assert result["missing_critical"] == []
    assert result["contradicted_critical"] == []


@pytest.mark.parametrize("reason", sorted(COMPLETE_EVIDENCE))
def test_a_complete_pack_becomes_contested_when_the_graph_reports_a_conflict(reason):
    result = _assess(reason, [COMPLETE_EVIDENCE[reason]], contradictions=1)
    contested = [item for item in result["requirements"] if item["status"] == "contradicted"]
    assert contested, f"{reason}: contradiction did not downgrade any evidenced requirement"
    assert result["contradicted_critical"]
    assert result["coverage"] < 1.0, "contested requirements must not count as covered"


@pytest.mark.parametrize("reason", sorted(COMPLETE_EVIDENCE))
def test_an_unrelated_pack_never_claims_coverage(reason):
    result = _assess(reason, ["The buyer emailed on Tuesday asking for an update."])
    assert all(item["status"] != "present" for item in result["requirements"])
    assert result["coverage"] == 0.0


def test_ambiguous_document_resolves_conservatively():
    text = (
        "The carrier reports delivery was confirmed, but no tracking number is available for this parcel."
    )
    result = _assess("MERCHANDISE_OR_SERVICE_NOT_RECEIVED", [text])
    status = next(i["status"] for i in result["requirements"] if i["code"] == "proof_of_fulfilment")
    # "deliver" is affirmed and "tracking number" is negated in the same document.
    # The negative mention wins: an operator must not be told a gap is closed.
    assert status == "missing"


def test_contradiction_does_not_invent_coverage_for_absent_evidence():
    result = _assess("UNAUTHORIZED", ["Unrelated note."], contradictions=2)
    assert all(item["status"] != "contradicted" for item in result["requirements"])
    assert result["coverage"] == 0.0


def test_missing_evidence_node_outranks_a_positive_mention():
    result = _assess(
        "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        ["Carrier scan confirms delivery on the tracking page."],
        nodes=[
            {
                "node_type": "MISSING_EVIDENCE",
                "title": "Tracking number absent",
                "statement": "No tracking number is attached to the file.",
            }
        ],
    )
    assert next(i["status"] for i in result["requirements"] if i["code"] == "proof_of_fulfilment") == "missing"
