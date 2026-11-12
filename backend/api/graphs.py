from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.ai.bundle import build_analysis_bundle
from backend.casegraph.schema import GraphCreateRequest
from backend.casegraph.validate import GraphValidationError, validate_ai_output
from backend.db.session import session_scope
from backend.repositories import cases as case_repo
from backend.repositories import evidence as evidence_repo
from backend.repositories import graphs as graph_repo
from backend.security.context import get_current_actor
from backend.services.graphs import GraphStaleInputError, graph_service

router = APIRouter(prefix="/api/cases", tags=["graphs"])


@router.post("/{case_id}/graphs")
def create(case_id: str, req: GraphCreateRequest):
    actor = get_current_actor()
    created_by = actor.subject if actor is not None else req.created_by
    try:
        bundle = build_analysis_bundle(case_id)
        validated = validate_ai_output(
            bundle,
            {
                "summary": "Manual CaseGraph revision",
                "nodes": req.nodes,
                "edges": req.edges,
                "recommended_action": {
                    "action_type": "NONE",
                    "rationale": "Manual graph creation does not authorize an action.",
                    "requires_human_approval": True,
                    "confidence": 0.0,
                    "supporting_node_ids": [],
                },
                "uncertainties": [],
            },
        )
        return graph_service.create(
            case_id,
            validated["nodes"],
            validated["edges"],
            created_by,
            "MANUAL",
            expected_case_revision=bundle["case_revision"],
            expected_evidence_set_revision=bundle["evidence_set_revision"],
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    except (GraphValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GraphStaleInputError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{case_id}/graphs/latest")
def latest(case_id: str):
    with session_scope() as session:
        row = graph_repo.latest(session, case_id)
        if not row:
            raise HTTPException(status_code=404, detail="no graph")
        case = case_repo.get_by_id(session, case_id)
        evidence_set = evidence_repo.latest_set(session, case_id)
        return graph_service.serialize(
            row,
            case.sync_revision,
            evidence_set.revision if evidence_set else 0,
        )
