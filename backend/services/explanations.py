"""Deterministic explanation artifact for one AI analysis.

Why this exists
---------------
The workspace already shows the reasoning in three places: the graph canvas, the
safety findings, and the approved payload. None of them is exportable, and all of
them require the browser to reconstruct "why". For an auditable dispute decision
the artifact itself has to be a first-class, reproducible output of the backend so
that it can be archived, diffed between revisions, and attached to a dispute file.

Everything here is derived from persisted rows — the analysis output, the graph
revision, and the safety assessment — with no model call and no new state. Given
the same rows it produces the same document.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.db.session import session_scope
from backend.repositories import analyses as analysis_repo
from backend.repositories import cases as case_repo
from backend.repositories import evidence as evidence_repo
from backend.repositories import graphs as graph_repo
from backend.safety.domain import POLICY, SAFETY_POLICY_VERSION
from backend.safety.service import safety_service
from backend.services.readiness import assess_readiness

#: Edge types that carry provenance. `CONTRADICTS` is deliberately excluded: it is
#: a conflict marker, not a grounding path.
SOURCE_RELATIONS = {"DERIVED_FROM", "SUPPORTS", "REFERENCES", "CLAIMS"}

#: Bounded traversal — an explanation must never be the reason a request hangs.
_MAX_PATHS_PER_NODE = 3
_MAX_DEPTH = 6

FINDING_EXPLANATIONS: dict[str, str] = {
    "UNGROUNDED_AI_INFERENCE": (
        "The model asserted something that does not trace back to a PayPal fact or an exact evidence "
        "revision. An unverifiable inference cannot support a dispute decision, so the graph is blocked."
    ),
    "HIGH_CONFIDENCE_INFERENCE_WITHOUT_PAYPAL_ROOT": (
        "A confident inference rests only on non-authoritative evidence. PayPal state is not in the "
        "grounding chain, so the assessment is downgraded for review."
    ),
    "ACTION_WITHOUT_SUPPORT": (
        "The recommended action cites no supporting node, so nothing in the graph justifies contacting "
        "PayPal on the buyer's behalf."
    ),
    "MISSING_EVIDENCE_CANNOT_JUSTIFY_ACTION": (
        "A consequential action is being justified by evidence that is absent. Absence can motivate a "
        "request for information, never a payment decision."
    ),
    "ACTION_SUPPORT_IS_CONTRADICTED": (
        "At least one node supporting the recommendation is explicitly contradicted by another node. "
        "High-risk actions are blocked; low-risk actions are downgraded to review."
    ),
    "ACTION_CONFIDENCE_BELOW_POLICY_THRESHOLD": (
        "Model confidence is below the threshold the policy requires for this risk class."
    ),
    "CRITICAL_ACTION_REQUIRES_EXACT_HUMAN_PAYLOAD_VALIDATION": (
        "This action can move money, so the exact typed payload must be validated and approved by a "
        "human before PayPal is contacted."
    ),
}


def _paths_to_grounding(
    node_id: str,
    nodes: dict[str, dict[str, Any]],
    outgoing: dict[str, list[str]],
) -> list[list[str]]:
    """Return bounded simple paths from `node_id` to source-backed roots."""
    results: list[list[str]] = []

    def walk(current: str, trail: list[str]) -> None:
        if len(results) >= _MAX_PATHS_PER_NODE:
            return
        node = nodes.get(current)
        if node is None or len(trail) > _MAX_DEPTH:
            return
        if node.get("source_kind") in {"PAYPAL_FACT", "EXTERNAL_EVIDENCE"}:
            results.append(trail)
            return
        for child in outgoing.get(current, []):
            if child in trail:
                continue
            walk(child, trail + [child])

    walk(node_id, [node_id])
    return results


def _source_of(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": node.get("source_kind") or "NONE",
        "ref": node.get("source_ref") or None,
        "revision": node.get("source_revision") if node.get("source_ref") else None,
        "excerpt": node.get("source_excerpt") or None,
    }


def build_explanation(case_id: str, analysis_uid: str) -> dict[str, Any]:
    with session_scope() as session:
        analysis = analysis_repo.get_by_uid(session, case_id, analysis_uid)
        if analysis is None:
            raise HTTPException(status_code=404, detail=f"AI analysis '{analysis_uid}' not found")
        if analysis.status != "COMPLETED" or not analysis.graph_id:
            raise HTTPException(
                status_code=409,
                detail="Only a completed analysis with a compiled CaseGraph can be explained.",
            )
        graph = graph_repo.get_by_id(session, analysis.graph_id)
        if graph is None:
            raise HTTPException(status_code=409, detail="The analysis references a missing CaseGraph revision")
        case = case_repo.get_by_id(session, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

        nodes = {node["node_id"]: node for node in (graph.nodes_json or [])}
        edges = list(graph.edges_json or [])
        output = analysis.output_json or {}
        recommendation = output.get("recommended_action") or {}
        summary = str(output.get("summary") or "")
        uncertainties = [str(item) for item in (output.get("uncertainties") or [])]
        case_revision = case.sync_revision
        evidence_revision = analysis.input_evidence_set_revision
        graph_id = graph.graph_id
        graph_revision = graph.revision
        input_case_revision = graph.input_case_revision
        input_evidence_revision = graph.input_evidence_set_revision
        provider = analysis.model_provider
        model = analysis.model_name
        dispute_reason = case.dispute_reason
        available_actions = list(case.allowed_response_options or [])
        evidence_set = evidence_repo.latest_set(session, case_id)
        evidence_items = (
            [
                {"source_ref": item.source_ref, "content": item.content}
                for _ordinal, item in evidence_repo.members(session, evidence_set.evidence_set_id)
            ]
            if evidence_set is not None
            else []
        )

    # Resolved after the analysis is known to exist, so a missing analysis is a
    # 404 rather than a generic safety-service ValueError.
    safety = safety_service.get(case_id, analysis_uid)

    outgoing: dict[str, list[str]] = {}
    incoming: dict[str, list[str]] = {}
    for edge in edges:
        if edge.get("relation_type") in SOURCE_RELATIONS:
            outgoing.setdefault(edge["source_node_id"], []).append(edge["target_node_id"])
            incoming.setdefault(edge["target_node_id"], []).append(edge["source_node_id"])

    supporting_ids = list(recommendation.get("supporting_node_ids") or [])
    grounding: list[dict[str, Any]] = []
    for node_id in supporting_ids:
        node = nodes.get(node_id)
        if node is None:
            grounding.append({"node_id": node_id, "resolved": False})
            continue
        paths = _paths_to_grounding(node_id, nodes, outgoing)
        grounding.append(
            {
                "node_id": node_id,
                "resolved": True,
                "title": node.get("title"),
                "node_type": node.get("node_type"),
                "statement": node.get("statement"),
                "source": _source_of(node),
                "grounded_in": [
                    [
                        {
                            "node_id": step,
                            "kind": (nodes.get(step) or {}).get("source_kind"),
                            "ref": (nodes.get(step) or {}).get("source_ref") or None,
                            "revision": (nodes.get(step) or {}).get("source_revision"),
                        }
                        for step in path
                    ]
                    for path in paths
                ],
                "grounded": bool(paths),
            }
        )

    ungrounded_inferences = [
        node_id
        for node_id, node in nodes.items()
        if node.get("node_type") == "AI_INFERENCE" and not _paths_to_grounding(node_id, nodes, outgoing)
    ]

    contradictions = [
        {
            "left": edge["source_node_id"],
            "right": edge["target_node_id"],
            "left_title": (nodes.get(edge["source_node_id"]) or {}).get("title"),
            "right_title": (nodes.get(edge["target_node_id"]) or {}).get("title"),
            "rationale": edge.get("rationale"),
            "affects_recommendation": bool(
                {edge["source_node_id"], edge["target_node_id"]} & set(supporting_ids)
            ),
        }
        for edge in edges
        if edge.get("relation_type") == "CONTRADICTS"
    ]

    evidence_gaps = [
        {
            "node_id": node_id,
            "title": node.get("title"),
            "statement": node.get("statement"),
            "required_for": incoming.get(node_id, []),
        }
        for node_id, node in nodes.items()
        if node.get("node_type") == "MISSING_EVIDENCE"
    ]

    risk = safety.action_risk.value
    confidence = float(recommendation.get("confidence") or 0.0)
    findings = [
        {
            "code": finding["code"],
            "severity": finding["severity"],
            "explanation": FINDING_EXPLANATIONS.get(finding["code"], finding.get("message", "")),
            "node_ids": [
                *([finding["node_id"]] if finding.get("node_id") else []),
                *(finding.get("supporting_node_ids") or []),
            ],
        }
        for finding in (safety.report.get("findings") or [])
    ]

    if safety.is_stale:
        next_step = (
            "The assessment is stale because the case or evidence changed. Re-run the analysis before "
            "approving any action."
        )
    elif safety.safety_status == "BLOCKED":
        next_step = (
            "No PayPal action may be approved from this graph. Resolve the blocking findings or add "
            "missing evidence, then re-analyze."
        )
    elif safety.effective_action == "NONE":
        next_step = "CaseGraph abstains. Obtain more evidence before proposing a PayPal action."
    else:
        # Deliberately free of action enums: this string is rendered as prose, and
        # an ALL_CAPS identifier mid-sentence reads as a bug in the interface.
        next_step = (
            "The recommended response is ready for human approval. CaseGraph re-reads PayPal immediately "
            "before the single allowed write and refuses if the live state differs from what was approved."
        )

    readiness = assess_readiness(
        reason=dispute_reason,
        evidence=evidence_items,
        nodes=list(nodes.values()),
        available_actions=available_actions,
        contradictions=len(contradictions),
    )

    return {
        "case_id": case_id,
        "analysis_uid": analysis_uid,
        "graph_id": graph_id,
        "graph_revision": graph_revision,
        "safety_uid": safety.safety_uid,
        "policy_version": SAFETY_POLICY_VERSION,
        "policy_hash": safety.policy_hash,
        "reasoning": {"provider": provider, "model": model, "summary": summary, "uncertainties": uncertainties},
        "revisions": {
            "graph_input_case_revision": input_case_revision,
            "graph_input_evidence_set_revision": input_evidence_revision,
            "current_case_revision": case_revision,
            "current_evidence_set_revision": evidence_revision,
        },
        "verdict": {
            "status": safety.safety_status.value,
            "risk": risk,
            "recommended_action": safety.recommended_action,
            "effective_action": safety.effective_action,
            "abstain_required": bool(safety.abstain_required),
            "is_stale": bool(safety.is_stale),
            "stale_reason": safety.stale_reason,
        },
        "confidence": {
            "recommendation": confidence,
            "required_minimum": POLICY["minimum_action_confidence"].get(risk, 0.0),
        },
        "grounding": grounding,
        "ungrounded_inferences": ungrounded_inferences,
        "contradictions": contradictions,
        "evidence_gaps": evidence_gaps,
        "readiness": readiness,
        "findings": findings,
        "next_step": next_step,
    }
