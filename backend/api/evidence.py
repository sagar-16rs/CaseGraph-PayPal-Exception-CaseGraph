from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.casegraph.schema import SupportIntakeRequest
from backend.security.context import get_current_actor
from backend.services.evidence import evidence_service

router = APIRouter(prefix="/api/cases", tags=["evidence"])


@router.post("/{case_id}/intake")
def intake(case_id: str, req: SupportIntakeRequest):
    actor = get_current_actor()
    if actor is not None:
        req = req.model_copy(update={"created_by": actor.subject})
    try:
        return evidence_service.ingest_support_intake(case_id, req)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{case_id}/evidence/sets/current")
def current(case_id: str):
    return evidence_service.current(case_id)
