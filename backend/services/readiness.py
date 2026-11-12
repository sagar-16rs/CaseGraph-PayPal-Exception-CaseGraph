"""Dispute readiness: what this case still needs before an action is defensible.

Provenance of the mapping, stated precisely because it matters:

* The **dispute reason codes** follow PayPal's published dispute-reason taxonomy
  (item not received, not as described, unauthorised, credit not processed,
  duplicate, incorrect amount, paid by other means, cancelled subscription).
* The **per-reason requirement list is CaseGraph's own judgement**, derived from
  the evidence types PayPal accepts (`PROOF_OF_FULFILLMENT`, `PROOF_OF_REFUND`,
  `OTHER`) and ordinary merchant practice. PayPal does not publish a normative
  per-reason evidence checklist. This is advisory, not a PayPal rule.

Honesty boundary: this is deterministic coverage over the text the merchant
attached. It is not a win-probability estimate, and it never substitutes for the
safety policy. `basis` says exactly what was examined.
"""

from __future__ import annotations

import re
from typing import Any

#: Negation before a signal means the evidence argues *against* the requirement —
#: "no delivery proof was provided" must not count as delivery evidence.
_NEGATION = re.compile(
    r"\b(?:no|not|never|without|missing|absent|none|lacks?|lacking|denied|refused|"
    r"did not|does not|was not|were not|has not|have not|cannot|can't)\b[^.;]{0,48}$",
    re.IGNORECASE,
)

REASON_REQUIREMENTS: dict[str, list[dict[str, str]]] = {
    "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": [
        {
            "code": "proof_of_fulfilment",
            "label": "Proof of fulfilment",
            "detail": "Carrier scan, tracking number, or signed delivery showing the item reached the buyer's address.",
            "signals": r"track|deliver|dispatch|ship|parcel|carrier|signed|receipt",
            "critical": "yes",
        },
        {
            "code": "order_record",
            "label": "Order record",
            "detail": "Order identifier matching the disputed transaction, with the delivery address used.",
            "signals": r"order|invoice|#\d|reference",
            "critical": "no",
        },
    ],
    "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": [
        {
            "code": "item_condition",
            "label": "Item condition evidence",
            "detail": "Photographs or inspection record of the item as shipped.",
            "signals": r"photo|image|inspect|condition|packaging|scratch|damage",
            "critical": "yes",
        },
        {
            "code": "listing_description",
            "label": "Listing as advertised",
            "detail": "The product description or specification the buyer purchased against.",
            "signals": r"listing|description|specification|advert|as described",
            "critical": "no",
        },
    ],
    "UNAUTHORIZED": [
        {
            "code": "customer_recognition",
            "label": "Customer recognition evidence",
            "detail": "Device fingerprint, IP geolocation, or prior order history linking the buyer to this purchase.",
            "signals": r"device|fingerprint|ip address|ip |login|prior order|history|account",
            "critical": "yes",
        },
        {
            "code": "delivery_to_buyer",
            "label": "Delivery to the buyer",
            "detail": "Fulfilment evidence delivered to an address the buyer has used before.",
            # Deliberately not the bare word "address": "IP address" satisfied a
            # delivery requirement before this was tightened, which is exactly the
            # kind of false positive a checklist must not produce.
            "signals": r"deliver|shipment|shipped|courier|tracking number|address on file|proof of delivery",
            "critical": "yes",
        },
    ],
    "CREDIT_NOT_PROCESSED": [
        {
            "code": "refund_proof",
            "label": "Refund transaction proof",
            "detail": "The PayPal refund transaction identifier and date.",
            "signals": r"refund|credit|transaction id|reversal",
            "critical": "yes",
        }
    ],
    "DUPLICATE_TRANSACTION": [
        {
            "code": "transaction_comparison",
            "label": "Transaction comparison",
            "detail": "Both transaction identifiers and evidence that only one charge corresponds to the order.",
            "signals": r"transaction|duplicate|charge|authori[sz]ation",
            "critical": "yes",
        }
    ],
    "INCORRECT_AMOUNT": [
        {
            "code": "price_breakdown",
            "label": "Price breakdown",
            "detail": "The order total, tax, shipping, and any agreed adjustment.",
            "signals": r"price|total|tax|shipping|invoice|amount",
            "critical": "yes",
        }
    ],
    "PAYMENT_BY_OTHER_MEANS": [
        {
            "code": "alternate_payment",
            "label": "Alternate payment proof",
            "detail": "Evidence of the other payment method the buyer says they used.",
            "signals": r"bank transfer|wire|invoice|paid by|cash|other method",
            "critical": "yes",
        }
    ],
    "CANCELED_RECURRING_BILLING": [
        {
            "code": "cancellation_record",
            "label": "Cancellation record",
            "detail": "The subscription state at charge time and any cancellation or renewal notice.",
            "signals": r"cancel|subscription|renew|billing|notice",
            "critical": "yes",
        }
    ],
}

#: Phrasing for what to do about an unmet requirement.
ACTION_HINT = "Attach a document or note that establishes this, then re-run the analysis so the graph reflects it."


def _corpus(evidence: list[dict[str, Any]]) -> str:
    return "\n".join(str(item.get("content") or "") for item in evidence)


def _missing_texts(nodes: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{node.get('title') or ''} {node.get('statement') or ''}"
        for node in nodes
        if node.get("node_type") == "MISSING_EVIDENCE"
    )


def _mentions(corpus: str, pattern: re.Pattern[str]) -> tuple[bool, bool]:
    """Return (affirmed, negated) for a signal pattern.

    An occurrence preceded by a negator within the same clause counts as evidence
    against the requirement, not for it. Without this, "no delivery proof was
    received" reads as delivery evidence — the single easiest way a keyword
    checklist lies to an operator.
    """
    affirmed = False
    negated = False
    for match in pattern.finditer(corpus):
        window = corpus[max(0, match.start() - 70):match.start()]
        if _NEGATION.search(window):
            negated = True
        else:
            affirmed = True
        if affirmed and negated:
            break
    return affirmed, negated


def assess_readiness(
    *,
    reason: str | None,
    evidence: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
    available_actions: list[str],
    contradictions: int = 0,
) -> dict[str, Any]:
    requirements = REASON_REQUIREMENTS.get(str(reason or ""), [])
    corpus = _corpus(evidence)
    missing_text = _missing_texts(nodes)

    items: list[dict[str, Any]] = []
    for requirement in requirements:
        pattern = re.compile(requirement["signals"], re.IGNORECASE)
        affirmed, negated = _mentions(corpus, pattern)
        flagged = bool(pattern.search(missing_text))
        if flagged or negated:
            status = "missing"
        elif affirmed and contradictions:
            # The file contains supporting text, but the graph records a conflict.
            # Calling this "covered" would overstate what the evidence supports.
            status = "contradicted"
        elif affirmed:
            status = "present"
        elif not evidence:
            status = "missing"
        else:
            status = "unknown"
        items.append(
            {
                "code": requirement["code"],
                "label": requirement["label"],
                "detail": requirement["detail"],
                "critical": requirement["critical"] == "yes",
                "status": status,
                "how_to_satisfy": ACTION_HINT,
            }
        )

    critical = [item for item in items if item["critical"]]
    satisfied = [item for item in critical if item["status"] == "present"]
    contradicted_critical = [item for item in critical if item["status"] == "contradicted"]
    missing_critical = [item for item in critical if item["status"] == "missing"]
    unknown_critical = [item for item in critical if item["status"] == "unknown"]

    can_submit_evidence = "PROVIDE_EVIDENCE" in available_actions
    can_supplement = "PROVIDE_SUPPORTING_INFO" in available_actions

    if not requirements:
        summary = "PayPal does not publish a fixed evidence checklist for this dispute reason; rely on the attached evidence."
        coverage = None
    elif not missing_critical and not unknown_critical and not contradicted_critical:
        coverage = 1.0
        summary = "Every critical evidence requirement for this dispute reason is covered by attached evidence."
    else:
        coverage = round(len(satisfied) / len(critical), 2) if critical else None
        parts = []
        if missing_critical:
            parts.append(f"{len(missing_critical)} critical requirement{'s' if len(missing_critical) != 1 else ''} unmet")
        if contradicted_critical:
            count = len(contradicted_critical)
            parts.append(f"{count} requirement{'s' if count != 1 else ''} evidenced but contradicted")
        if unknown_critical:
            count = len(unknown_critical)
            parts.append(f"{count} requirement{'s' if count != 1 else ''} not evidenced in the attached text")
        summary = "; ".join(parts) + "."

    return {
        "reason": reason,
        "basis": "deterministic keyword coverage over the attached evidence text and the graph's missing-evidence nodes",
        "coverage": coverage,
        "summary": summary,
        "requirements": items,
        "missing_critical": [item["code"] for item in missing_critical],
        "contradicted_critical": [item["code"] for item in contradicted_critical],
        "unknown_critical": [item["code"] for item in unknown_critical],
        "can_attach_evidence": can_submit_evidence,
        "can_supplement": can_supplement,
        "next_action": (
            "Gather the unmet evidence, attach it to the case, then re-run the analysis so the graph reflects it."
            if missing_critical or unknown_critical or contradicted_critical
            else "The evidence set is complete enough to support a response; a human must still approve the exact payload."
        ),
    }
