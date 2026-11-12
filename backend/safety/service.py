from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from backend.db.models import AISafetyAssessment
from backend.db.session import session_scope
from backend.evidence.domain import content_hash
from backend.repositories import analyses as analysis_repo
from backend.repositories import cases as case_repo
from backend.repositories import evidence as evidence_repo
from backend.repositories import graphs as graph_repo
from backend.repositories import safety as safety_repo
from backend.safety.domain import (
    POLICY,
    SAFETY_POLICY_VERSION,
    ActionRisk,
    SafetyStatus,
    policy_hash,
)


class SafetyIntegrityError(RuntimeError):
    pass


@dataclass
class SafetyView:
    safety_uid: str
    case_id: str
    analysis_uid: str
    graph_id: str
    policy_version: str
    policy_hash: str
    safety_status: SafetyStatus
    action_risk: ActionRisk
    recommended_action: str
    effective_action: str
    abstain_required: bool
    report: dict
    input_case_revision: int
    input_evidence_set_revision: int
    is_stale: bool = False
    stale_reason: str | None = None

    def model_dump(self, mode: str = "json") -> dict:
        data = self.__dict__.copy()
        data["safety_status"] = self.safety_status.value
        data["action_risk"] = self.action_risk.value
        return data


def _risk(action: str) -> ActionRisk:
    risk = POLICY["risk"]
    if action in risk["critical"]:
        return ActionRisk.CRITICAL
    if action in risk["high"]:
        return ActionRisk.HIGH
    if action in risk["medium"]:
        return ActionRisk.MEDIUM
    if action in risk["low"]:
        return ActionRisk.LOW
    return ActionRisk.NONE


def _max_status(*statuses: SafetyStatus) -> SafetyStatus:
    order = {SafetyStatus.PASS: 0, SafetyStatus.REVIEW: 1, SafetyStatus.BLOCKED: 2}
    return max(statuses, key=lambda item: order[item])


def _finding(code: str, severity: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, **details}


def _grounding(nodes: dict[str, dict], edges: list[dict]) -> dict[str, dict[str, bool]]:
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for edge in edges:
        if edge.get("relation_type") in {"DERIVED_FROM", "SUPPORTS", "REFERENCES", "CLAIMS"}:
            outgoing.setdefault(edge["source_node_id"], []).append(edge["target_node_id"])

    cache: dict[str, dict[str, bool]] = {}

    def roots(node_id: str, stack: set[str]) -> dict[str, bool]:
        if node_id in cache:
            return cache[node_id]
        if node_id in stack:
            return {"source_backed": False, "paypal": False}
        node = nodes[node_id]
        if node.get("source_kind") == "PAYPAL_FACT":
            result = {"source_backed": True, "paypal": True}
        elif node.get("source_kind") == "EXTERNAL_EVIDENCE":
            result = {"source_backed": True, "paypal": False}
        else:
            children = outgoing.get(node_id, [])
            child_results = [roots(child, stack | {node_id}) for child in children]
            result = {
                "source_backed": any(item["source_backed"] for item in child_results),
                "paypal": any(item["paypal"] for item in child_results),
            }
        cache[node_id] = result
        return result

    for node_id in nodes:
        roots(node_id, set())
    return cache


class SafetyService:
    def assess(self, case_id: str, analysis_uid: str) -> SafetyView:
        with session_scope() as session:
            analysis = analysis_repo.get_by_uid(session, case_id, analysis_uid)
            if not analysis or analysis.status != "COMPLETED" or not analysis.graph_id:
                raise ValueError("completed analysis required")
            old = safety_repo.latest_for_analysis(session, case_id, analysis_uid)
            if old:
                return self._view(session, old)

            graph = graph_repo.get_by_id(session, analysis.graph_id)
            if graph is None:
                raise SafetyIntegrityError("AI analysis references a missing CaseGraph revision")

            output = analysis.output_json or {}
            recommendation = output.get("recommended_action") or {}
            action = str(recommendation.get("action_type") or "NONE")
            confidence = float(recommendation.get("confidence", 0) or 0)
            supporting_ids = list(recommendation.get("supporting_node_ids") or [])
            risk = _risk(action)

            nodes = {node["node_id"]: node for node in (graph.nodes_json or [])}
            edges = list(graph.edges_json or [])
            grounding = _grounding(nodes, edges)
            findings: list[dict[str, Any]] = []
            status = SafetyStatus.PASS
            abstain = action == "NONE"

            # Every AI inference must ultimately be grounded in a PayPal fact or
            # exact external-evidence revision. This is independent of confidence.
            for node_id, node in nodes.items():
                if node.get("node_type") != "AI_INFERENCE":
                    continue
                root = grounding.get(node_id, {"source_backed": False, "paypal": False})
                if not root["source_backed"]:
                    findings.append(
                        _finding(
                            "UNGROUNDED_AI_INFERENCE",
                            "BLOCK",
                            "AI inference has no transitive source-backed root.",
                            node_id=node_id,
                        )
                    )
                    status = SafetyStatus.BLOCKED
                elif float(node.get("confidence", 0) or 0) >= float(POLICY["high_inference_confidence"]) and not root["paypal"]:
                    findings.append(
                        _finding(
                            "HIGH_CONFIDENCE_INFERENCE_WITHOUT_PAYPAL_ROOT",
                            "REVIEW",
                            "High-confidence inference is grounded only in non-authoritative evidence.",
                            node_id=node_id,
                        )
                    )
                    status = _max_status(status, SafetyStatus.REVIEW)

            if action != "NONE" and not supporting_ids:
                findings.append(_finding("ACTION_WITHOUT_SUPPORT", "BLOCK", "Recommendation has no supporting nodes."))
                status = SafetyStatus.BLOCKED
                abstain = True

            missing_support = [
                node_id
                for node_id in supporting_ids
                if nodes.get(node_id, {}).get("node_type") == "MISSING_EVIDENCE"
            ]
            if missing_support and risk in {ActionRisk.MEDIUM, ActionRisk.HIGH, ActionRisk.CRITICAL}:
                findings.append(
                    _finding(
                        "MISSING_EVIDENCE_CANNOT_JUSTIFY_ACTION",
                        "BLOCK",
                        "Missing evidence is being used to justify a consequential action.",
                        supporting_node_ids=missing_support,
                    )
                )
                status = SafetyStatus.BLOCKED
                abstain = True

            contradicted: set[str] = set()
            support_set = set(supporting_ids)
            for edge in edges:
                if edge.get("relation_type") != "CONTRADICTS":
                    continue
                if edge["source_node_id"] in support_set:
                    contradicted.add(edge["source_node_id"])
                if edge["target_node_id"] in support_set:
                    contradicted.add(edge["target_node_id"])
            if contradicted:
                severity = "BLOCK" if risk in {ActionRisk.HIGH, ActionRisk.CRITICAL} else "REVIEW"
                findings.append(
                    _finding(
                        "ACTION_SUPPORT_IS_CONTRADICTED",
                        severity,
                        "One or more recommendation support nodes are explicitly contradicted.",
                        supporting_node_ids=sorted(contradicted),
                    )
                )
                status = _max_status(status, SafetyStatus.BLOCKED if severity == "BLOCK" else SafetyStatus.REVIEW)
                if severity == "BLOCK":
                    abstain = True

            threshold = POLICY["minimum_action_confidence"].get(risk.value, 0.0)
            if action != "NONE" and confidence < threshold:
                severity = "BLOCK" if risk in {ActionRisk.HIGH, ActionRisk.CRITICAL} else "REVIEW"
                findings.append(
                    _finding(
                        "ACTION_CONFIDENCE_BELOW_POLICY_THRESHOLD",
                        severity,
                        f"Action confidence {confidence:.3f} is below the {risk.value} threshold {threshold:.3f}.",
                    )
                )
                status = _max_status(status, SafetyStatus.BLOCKED if severity == "BLOCK" else SafetyStatus.REVIEW)
                if severity == "BLOCK":
                    abstain = True

            if risk == ActionRisk.CRITICAL and status != SafetyStatus.BLOCKED:
                findings.append(
                    _finding(
                        "CRITICAL_ACTION_REQUIRES_EXACT_HUMAN_PAYLOAD_VALIDATION",
                        "REVIEW",
                        "Money-moving action requires typed payload validation and explicit human approval.",
                    )
                )
                status = _max_status(status, SafetyStatus.REVIEW)

            effective = "NONE" if status == SafetyStatus.BLOCKED or abstain else action
            report = {
                "policy_version": SAFETY_POLICY_VERSION,
                "analysis_uid": analysis_uid,
                "graph_id": graph.graph_id,
                "findings": findings,
                "action_result": {
                    "recommended_action": action,
                    "effective_action": effective,
                    "risk": risk.value,
                    "confidence": confidence,
                    "supporting_node_ids": supporting_ids,
                    "finding_codes": [item["code"] for item in findings],
                },
            }
            row = AISafetyAssessment(
                safety_uid="SAFE-" + uuid.uuid4().hex.upper(),
                case_id=case_id,
                analysis_uid=analysis_uid,
                graph_id=analysis.graph_id,
                policy_version=SAFETY_POLICY_VERSION,
                policy_hash=policy_hash(),
                safety_status=status.value,
                action_risk=risk.value,
                recommended_action=action,
                effective_action=effective,
                abstain_required=abstain,
                report_json=report,
                report_hash=content_hash(report),
                graph_hash=graph.content_hash,
                is_stale=False,
                input_case_revision=analysis.input_case_revision,
                input_evidence_set_revision=analysis.input_evidence_set_revision,
            )
            session.add(row)
            session.flush()
            return self._view(session, row)

    def get(self, case_id: str, analysis_uid: str) -> SafetyView:
        with session_scope() as session:
            row = safety_repo.latest_for_analysis(session, case_id, analysis_uid)
            if not row:
                return self.assess(case_id, analysis_uid)
            return self._view(session, row)

    def _view(self, session, row: AISafetyAssessment) -> SafetyView:
        if content_hash(row.report_json) != row.report_hash:
            raise SafetyIntegrityError("stored safety report hash does not match its content")
        graph = graph_repo.get_by_id(session, row.graph_id)
        if graph is None or graph.content_hash != row.graph_hash:
            raise SafetyIntegrityError("stored safety assessment no longer matches its CaseGraph content hash")

        case = case_repo.get_by_id(session, row.case_id)
        evidence_set = evidence_repo.latest_set(session, row.case_id)
        evidence_revision = evidence_set.revision if evidence_set else 0
        stale_reasons: list[str] = []
        if case is None or case.sync_revision != row.input_case_revision:
            stale_reasons.append("PayPal case revision changed")
        if evidence_revision != row.input_evidence_set_revision:
            stale_reasons.append("evidence-set revision changed")
        if row.policy_hash != policy_hash() or row.policy_version != SAFETY_POLICY_VERSION:
            stale_reasons.append("safety policy changed")

        stale = bool(stale_reasons)
        status = SafetyStatus.BLOCKED if stale else SafetyStatus(row.safety_status)
        effective = "NONE" if stale else row.effective_action
        return SafetyView(
            row.safety_uid,
            row.case_id,
            row.analysis_uid,
            row.graph_id,
            row.policy_version,
            row.policy_hash,
            status,
            ActionRisk(row.action_risk),
            row.recommended_action,
            effective,
            row.abstain_required or stale,
            row.report_json,
            row.input_case_revision,
            row.input_evidence_set_revision,
            stale,
            "; ".join(stale_reasons) if stale else None,
        )


safety_service = SafetyService()
