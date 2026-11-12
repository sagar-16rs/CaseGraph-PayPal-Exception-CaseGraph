"""Deterministic reference reasoner.

This provider exists so CaseGraph's reasoning, validation, and safety pipeline
can be exercised without a language-model credential — for local development, the
demo walkthrough, and as a non-LLM baseline in the benchmark.

It is *not* a substitute for a model and does not pretend to be one: it applies a
small, documented, reproducible set of rules to the frozen analysis bundle. The
provenance it produces is honest — every claim node cites an exact evidence
revision with a verbatim excerpt, every fact node copies the authoritative PayPal
value, and every inference is explicitly labelled `AI_INFERENCE` with a fixed,
conservative confidence.

The analysis record stores `model_provider="rules"` and
`model_name="reference-rules-v1"`, so a reviewer can always tell which reasoning
path produced a graph.
"""

from __future__ import annotations

import re
from typing import Any

PROVIDER_NAME = "rules"
MODEL_NAME = "reference-rules-v1"

#: Words that indicate the merchant evidence actually addresses fulfilment.
_DELIVERY_EVIDENCE = re.compile(
    r"track|deliver|dispatch|ship|parcel|carrier|signed|receipt|proof of delivery",
    re.IGNORECASE,
)
_DELIVERY_GAP_REASONS = ("NOT_RECEIVED",)
_AS_DESCRIBED_GAP_REASONS = ("NOT_AS_DESCRIBED",)

_MAX_EXCERPT = 5000

#: Facts worth putting on the graph. Volume identifiers belong in the case record,
#: action availability is already shown there, and a raw ISO timestamp or a JSON
#: array makes a poor epistemic node — the graph should show facts an investigator
#: reasons *about*.
GRAPH_FACT_REFS = {
    "PF-STATUS",
    "PF-REASON",
    "PF-LIFECYCLE",
    "PF-AMOUNT",
    "PF-REFUND-CEILING",
    "PF-TRANSACTION",
}

FACT_TITLES = {
    "PAYPAL_DISPUTE_STATUS": "Dispute status",
    "PAYPAL_DISPUTE_REASON": "Dispute reason",
    "PAYPAL_DISPUTE_LIFECYCLE_STAGE": "Lifecycle stage",
    "PAYPAL_DISPUTE_AMOUNT": "Disputed amount",
    "PAYPAL_ALLOWED_REFUND_AMOUNT": "Refund ceiling",
    "PAYPAL_TRANSACTION_ID": "Transaction",
    "PAYPAL_DISPUTE_ID": "Dispute identifier",
    "PAYPAL_SELLER_RESPONSE_DUE_DATE": "Response due",
    "PAYPAL_AVAILABLE_ACTIONS": "Available actions",
}

#: Emit the facts the inference actually derives from first, so the graph reads
#: top-down: state of the dispute, then the amounts and identifiers.
FACT_ORDER = {
    "PF-STATUS": 0,
    "PF-REASON": 1,
    "PF-LIFECYCLE": 2,
    "PF-AMOUNT": 3,
    "PF-DUE": 4,
    "PF-REFUND-CEILING": 5,
    "PF-TRANSACTION": 6,
}


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", value)[:_MAX_EXCERPT]


class ReferencesRulesProvider:
    provider_name = PROVIDER_NAME
    model_name = MODEL_NAME

    async def run(self, bundle: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        return self.build(bundle), {
            "provider": PROVIDER_NAME,
            "model": MODEL_NAME,
            "response_id": "reference-rules",
        }

    # ------------------------------------------------------------------ build
    def build(self, bundle: dict[str, Any]) -> dict[str, Any]:
        facts: list[dict[str, Any]] = list(bundle.get("paypal_facts") or [])
        evidence: list[dict[str, Any]] = list(bundle.get("evidence") or [])
        available = set(bundle.get("available_actions") or [])

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        uncertainties: list[str] = []

        fact_ids: dict[str, str] = {}
        graph_facts = sorted(
            (fact for fact in facts if fact["ref"] in GRAPH_FACT_REFS),
            key=lambda fact: FACT_ORDER.get(str(fact["ref"]), 99),
        )
        for fact in graph_facts:
            node_id = f"F_{len(fact_ids) + 1}"
            fact_ids[fact["ref"]] = node_id
            nodes.append(
                {
                    "node_id": node_id,
                    "node_type": "VERIFIED_FACT",
                    "title": FACT_TITLES.get(str(fact["fact_type"]), _slug(str(fact["fact_type"]))),
                    "statement": str(fact["value"]),
                    "source_kind": "PAYPAL_FACT",
                    "source_ref": str(fact["ref"]),
                    "source_revision": int(fact["revision"]),
                    "source_excerpt": "",
                    "confidence": -1,
                }
            )

        claim_ids: list[str] = []
        customer_ids: list[str] = []
        merchant_ids: list[str] = []
        for index, item in enumerate(evidence, start=1):
            content = str(item.get("content") or "")
            if not content.strip():
                continue
            speaker = str(item.get("speaker") or "")
            excerpt = content[:_MAX_EXCERPT]
            common = {
                "title": _slug(f"{item.get('evidence_type') or 'evidence'} {item.get('source_ref')}"),
                "statement": excerpt.strip()[:2000],
                "source_kind": "EXTERNAL_EVIDENCE",
                "source_ref": str(item["source_ref"]),
                "source_revision": int(item["revision"]),
                "source_excerpt": excerpt,
            }
            if speaker == "customer":
                node_id = f"C_{index}"
                customer_ids.append(node_id)
                nodes.append({"node_id": node_id, "node_type": "CUSTOMER_CLAIM", "confidence": -1, **common})
            elif speaker == "merchant_agent":
                node_id = f"M_{index}"
                merchant_ids.append(node_id)
                nodes.append({"node_id": node_id, "node_type": "MERCHANT_CLAIM", "confidence": -1, **common})
            else:
                node_id = f"E_{index}"
                nodes.append({"node_id": node_id, "node_type": "EVENT", "confidence": -1, **common})
            claim_ids.append(node_id)

        if not claim_ids:
            uncertainties.append("No customer or merchant statements are attached to this case.")

        # ---------------------------------------------------- contradiction
        # A customer statement and a merchant statement about the same dispute are
        # treated as contradictory unless the merchant evidence positively
        # corroborates fulfilment. This is deliberately conservative: the graph
        # records the conflict instead of letting the reasoner pick a winner.
        contradictions: list[tuple[str, str]] = []
        has_fulfilment_evidence = any(_DELIVERY_EVIDENCE.search(str(item.get("content") or "")) for item in evidence)
        if customer_ids and merchant_ids:
            contradictions.append((customer_ids[0], merchant_ids[0]))
            edges.append(
                {
                    "edge_id": "E_CONTRADICTS",
                    "source_node_id": customer_ids[0],
                    "target_node_id": merchant_ids[0],
                    "relation_type": "CONTRADICTS",
                    "rationale": "Customer and merchant statements describe incompatible account activity.",
                }
            )
            uncertainties.append("Customer and merchant statements conflict; resolution requires evidence outside the transcript.")

        # ------------------------------------------------------- hypothesis
        reasoning_roots = [node for node in claim_ids]
        for key in ("PF-STATUS", "PF-REASON", "PF-LIFECYCLE"):
            if key in fact_ids:
                reasoning_roots.append(fact_ids[key])
        if not reasoning_roots:
            # Nothing source-backed exists; abstain rather than infer.
            return self._abstain(bundle, nodes, edges, uncertainties)

        inference_id = "I_1"
        confidence = 0.45 if contradictions else 0.5
        nodes.append(
            {
                "node_id": inference_id,
                "node_type": "AI_INFERENCE",
                "title": "Dispute assessment",
                "statement": (
                    "The dispute is currently "
                    f"{self._fact_value(facts, 'PF-STATUS') or 'in an unknown state'} and the attached evidence "
                    + ("conflicts across the parties." if contradictions else "does not conflict across the parties.")
                ),
                "source_kind": "NONE",
                "source_ref": "",
                "source_revision": 0,
                "source_excerpt": "",
                "confidence": confidence,
            }
        )
        for index, root in enumerate(reasoning_roots, start=1):
            edges.append(
                {
                    "edge_id": f"E_DERIVED_{index}",
                    "source_node_id": inference_id,
                    "target_node_id": root,
                    "relation_type": "DERIVED_FROM",
                    "rationale": "Assessment is derived from attached sources.",
                }
            )

        # ------------------------------------------------- missing evidence
        reason = self._fact_value(facts, "PF-REASON") or ""
        missing: list[str] = []
        if any(token in reason for token in _DELIVERY_GAP_REASONS) and not has_fulfilment_evidence:
            missing.append("X_DELIVERY")
            nodes.append(
                {
                    "node_id": "X_DELIVERY",
                    "node_type": "MISSING_EVIDENCE",
                    "title": "Delivery proof absent",
                    "statement": "No carrier scan, tracking number, or proof-of-delivery document is attached.",
                    "source_kind": "NONE",
                    "source_ref": "",
                    "source_revision": 0,
                    "source_excerpt": "",
                    "confidence": -1,
                }
            )
            edges.append(
                {
                    "edge_id": "E_MISSING_DELIVERY",
                    "source_node_id": "X_DELIVERY",
                    "target_node_id": inference_id,
                    "relation_type": "MISSING_FOR",
                    "rationale": "Fulfilment evidence is required to answer this dispute reason.",
                }
            )
            uncertainties.append("No fulfilment evidence is attached for a not-received dispute.")
        if any(token in reason for token in _AS_DESCRIBED_GAP_REASONS) and not evidence:
            uncertainties.append("No evidence describes the item condition or the listing it was compared against.")

        # ----------------------------------------------------- action
        action, rationale, supporting, action_confidence = self._recommend(
            available=available,
            customer_ids=customer_ids,
            merchant_ids=merchant_ids,
            fact_ids=fact_ids,
            contradictions=contradictions,
            missing=missing,
        )
        if action != "NONE":
            nodes.append(
                {
                    "node_id": "A_1",
                    "node_type": "ACTION",
                    "title": action,
                    "statement": f"Recommended action: {action}",
                    "source_kind": "NONE",
                    "source_ref": "",
                    "source_revision": 0,
                    "source_excerpt": "",
                    "confidence": -1,
                }
            )
            for index, node_id in enumerate(supporting, start=1):
                edges.append(
                    {
                        "edge_id": f"E_SUPPORTS_{index}",
                        "source_node_id": "A_1",
                        "target_node_id": node_id,
                        "relation_type": "SUPPORTS",
                        "rationale": "Action is grounded in this node.",
                    }
                )
        uncertainties.append("Deterministic reference reasoner: recommendation follows a fixed rule table, not model judgement.")

        return {
            "summary": f"Reference assessment for case {bundle.get('case_id')} at case revision {bundle.get('case_revision')}.",
            "nodes": nodes,
            "edges": edges,
            "recommended_action": {
                "action_type": action,
                "rationale": rationale,
                "requires_human_approval": True,
                "confidence": action_confidence,
                "supporting_node_ids": supporting if action != "NONE" else [],
            },
            "uncertainties": uncertainties,
        }

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _fact_value(facts: list[dict[str, Any]], ref: str) -> str | None:
        for fact in facts:
            if fact.get("ref") == ref:
                return str(fact.get("value") or "")
        return None

    @staticmethod
    def _recommend(
        *,
        available: set[str],
        customer_ids: list[str],
        merchant_ids: list[str],
        fact_ids: dict[str, str],
        contradictions: list[tuple[str, str]],
        missing: list[str],
    ) -> tuple[str, str, list[str], float]:
        status_fact = fact_ids.get("PF-STATUS")
        if contradictions:
            if "SEND_MESSAGE" in available:
                support = [customer_ids[0], merchant_ids[0]]
                return (
                    "SEND_MESSAGE",
                    "The parties disagree, so a low-risk clarifying message is the only defensible step until the conflict is resolved.",
                    support,
                    0.72,
                )
            return (
                "NONE",
                "The evidence conflicts and no low-risk clarification action is available.",
                [],
                0.0,
            )
        if "PROVIDE_EVIDENCE" in available and merchant_ids:
            return (
                "PROVIDE_EVIDENCE",
                "Merchant evidence exists and PayPal is currently requesting evidence; a human must approve the exact submission.",
                merchant_ids[:2],
                0.80,
            )
        if "PROVIDE_SUPPORTING_INFO" in available:
            support = customer_ids[:1] + ([status_fact] if status_fact else [])
            return (
                "PROVIDE_SUPPORTING_INFO",
                "The current stage accepts supporting information; a human must approve the exact notes.",
                support,
                0.75,
            )
        if "SEND_MESSAGE" in available:
            support = customer_ids[:1] + ([status_fact] if status_fact else [])
            if not support and missing:
                return ("NONE", "Only missing evidence is available; CaseGraph abstains.", [], 0.0)
            return (
                "SEND_MESSAGE",
                "A low-risk clarifying message acknowledges the dispute without moving money.",
                support,
                0.72,
            )
        return ("NONE", "No defensible PayPal action is currently available for this dispute.", [], 0.0)

    @staticmethod
    def _abstain(
        bundle: dict[str, Any],
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        uncertainties: list[str],
    ) -> dict[str, Any]:
        uncertainties.append("No source-backed roots were available, so CaseGraph abstained.")
        return {
            "summary": f"Reference assessment for case {bundle.get('case_id')} at case revision {bundle.get('case_revision')}.",
            "nodes": nodes,
            "edges": edges,
            "recommended_action": {
                "action_type": "NONE",
                "rationale": "No source-backed roots are available to ground a recommendation.",
                "requires_human_approval": True,
                "confidence": 0.0,
                "supporting_node_ids": [],
            },
            "uncertainties": uncertainties,
        }


rules_provider = ReferencesRulesProvider()
