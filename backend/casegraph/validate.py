from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.ai.schemas import AIOutput


class GraphValidationError(ValueError):
    """The model output violates a deterministic CaseGraph invariant."""


def _require_none_source(node: dict[str, Any]) -> None:
    if (
        node["source_kind"] != "NONE"
        or node["source_ref"] != ""
        or node["source_revision"] != 0
        or node["source_excerpt"] != ""
    ):
        raise GraphValidationError(f"{node['node_type']} node {node['node_id']} must not claim a direct source")


def _assert_acyclic(nodes: set[str], edges: list[dict[str, Any]]) -> None:
    # CONTRADICTS is a symmetric relationship, not causal provenance. Every
    # other relation participates in the provenance/reasoning DAG.
    graph: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge["relation_type"] != "CONTRADICTS":
            graph[edge["source_node_id"]].append(edge["target_node_id"])

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise GraphValidationError("CaseGraph reasoning/provenance edges contain a cycle")
        if node in visited:
            return
        visiting.add(node)
        for target in graph.get(node, []):
            visit(target)
        visiting.remove(node)
        visited.add(node)

    for node in nodes:
        visit(node)


def validate_ai_output(bundle: dict[str, Any], raw_output: dict[str, Any]) -> dict[str, Any]:
    """Validate provider output against the exact frozen bundle.

    This function is deliberately deterministic. A provider's JSON-schema
    compliance is not trusted as authorization or provenance validation.
    """
    output = AIOutput.model_validate(raw_output).model_dump(mode="json")

    facts = {(item["ref"], item["revision"]): item for item in bundle["paypal_facts"]}
    evidence = {(item["source_ref"], item["revision"]): item for item in bundle["evidence"]}

    node_ids: set[str] = set()
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for node in output["nodes"]:
        node_id = node["node_id"]
        if node_id in node_ids:
            raise GraphValidationError(f"duplicate node_id: {node_id}")
        node_ids.add(node_id)
        nodes_by_id[node_id] = node

        kind = node["node_type"]
        source_kind = node["source_kind"]
        source_key = (node["source_ref"], node["source_revision"])

        if kind == "VERIFIED_FACT":
            if source_kind != "PAYPAL_FACT" or source_key not in facts:
                raise GraphValidationError(f"VERIFIED_FACT {node_id} must cite an exact PayPal fact revision")
            fact = facts[source_key]
            if node["statement"] != fact["value"]:
                raise GraphValidationError(
                    f"VERIFIED_FACT {node_id} statement must exactly equal the authoritative PayPal fact value"
                )
            if node["source_excerpt"]:
                raise GraphValidationError(f"VERIFIED_FACT {node_id} must not invent a source excerpt")
            if node["confidence"] != -1:
                raise GraphValidationError(f"VERIFIED_FACT {node_id} must use confidence=-1")

        elif kind in {"CUSTOMER_CLAIM", "MERCHANT_CLAIM"}:
            if source_kind != "EXTERNAL_EVIDENCE" or source_key not in evidence:
                raise GraphValidationError(f"{kind} {node_id} must cite an exact evidence revision")
            source = evidence[source_key]
            expected_speaker = "customer" if kind == "CUSTOMER_CLAIM" else "merchant_agent"
            if source.get("speaker") != expected_speaker:
                raise GraphValidationError(f"{kind} {node_id} speaker does not match its source evidence")
            excerpt = node["source_excerpt"]
            if not excerpt.strip() or excerpt not in source["content"]:
                raise GraphValidationError(f"{kind} {node_id} must contain a verbatim non-empty source excerpt")
            if node["confidence"] != -1:
                raise GraphValidationError(f"{kind} {node_id} must use confidence=-1")

        elif kind == "AI_INFERENCE":
            _require_none_source(node)
            if node["confidence"] < 0:
                raise GraphValidationError(f"AI_INFERENCE {node_id} must have confidence in [0,1]")

        elif kind in {"MISSING_EVIDENCE", "ACTION"}:
            _require_none_source(node)
            if node["confidence"] != -1:
                raise GraphValidationError(f"{kind} {node_id} must use confidence=-1")

        elif kind == "EVENT":
            if source_kind == "PAYPAL_FACT":
                if source_key not in facts:
                    raise GraphValidationError(f"EVENT {node_id} cites an unknown PayPal fact revision")
                if node["statement"] != facts[source_key]["value"]:
                    raise GraphValidationError(f"PayPal-backed EVENT {node_id} must copy the authoritative value exactly")
                if node["source_excerpt"]:
                    raise GraphValidationError(f"PayPal-backed EVENT {node_id} must not invent a source excerpt")
            elif source_kind == "EXTERNAL_EVIDENCE":
                if source_key not in evidence:
                    raise GraphValidationError(f"EVENT {node_id} cites an unknown evidence revision")
                excerpt = node["source_excerpt"]
                if not excerpt.strip() or excerpt not in evidence[source_key]["content"]:
                    raise GraphValidationError(f"Evidence-backed EVENT {node_id} requires a verbatim source excerpt")
            else:
                _require_none_source(node)
            if node["confidence"] != -1:
                raise GraphValidationError(f"EVENT {node_id} must use confidence=-1")

    edge_ids: set[str] = set()
    contradiction_pairs: set[tuple[str, str]] = set()
    for edge in output["edges"]:
        edge_id = edge["edge_id"]
        if edge_id in edge_ids:
            raise GraphValidationError(f"duplicate edge_id: {edge_id}")
        edge_ids.add(edge_id)
        source = edge["source_node_id"]
        target = edge["target_node_id"]
        if source not in node_ids or target not in node_ids:
            raise GraphValidationError(f"edge {edge_id} references a node not present in this output")
        if source == target:
            raise GraphValidationError(f"edge {edge_id} cannot point a node to itself")
        if edge["relation_type"] == "CONTRADICTS":
            pair = tuple(sorted((source, target)))
            if pair in contradiction_pairs:
                raise GraphValidationError(f"duplicate contradiction relation between {pair[0]} and {pair[1]}")
            contradiction_pairs.add(pair)

    _assert_acyclic(node_ids, output["edges"])

    recommendation = output["recommended_action"]
    action = recommendation["action_type"]
    available = set(bundle["available_actions"])
    if action != "NONE" and action not in available:
        raise GraphValidationError(f"unsupported PayPal action recommendation: {action}")

    supporting = recommendation["supporting_node_ids"]
    if len(set(supporting)) != len(supporting):
        raise GraphValidationError("recommended_action.supporting_node_ids must be unique")
    if any(node_id not in node_ids for node_id in supporting):
        raise GraphValidationError("recommended action cites a supporting node that does not exist")
    if action != "NONE" and not supporting:
        raise GraphValidationError("non-NONE recommendations require at least one supporting node")
    if action == "NONE" and supporting:
        raise GraphValidationError("NONE recommendation must not claim supporting nodes")

    return output
