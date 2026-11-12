from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.ai.schemas import AnalyzeCaseRequest
from backend.ai.service import AIRequestConflict, ai_reasoning_service
from backend.db.session import session_scope
from backend.repositories import analyses as analysis_repo
from backend.security.context import get_current_actor
from backend.services.explanations import build_explanation

router = APIRouter(prefix="/api/cases", tags=["ai"])


@router.post("/{case_id}/ai/analyze")
async def analyze(case_id: str, req: AnalyzeCaseRequest):
    actor = get_current_actor()
    if actor is not None:
        req = req.model_copy(update={"requested_by": actor.subject})
    try:
        return await ai_reasoning_service.analyze(case_id, req)
    except AIRequestConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc


@router.get("/{case_id}/ai/analyses")
def analyses(case_id: str):
    with session_scope() as session:
        return [
            ai_reasoning_service._resp(item).model_dump(mode="json")
            for item in analysis_repo.list_for_case(session, case_id)
        ]


@router.get("/{case_id}/ai/analyses/{analysis_uid}/explain")
def explain(case_id: str, analysis_uid: str):
    """Exportable, deterministic explanation of one analysis.

    Restated rather than recomputed: it is assembled from the persisted analysis,
    graph revision, and safety assessment, so it can be archived or attached to a
    dispute file without the browser.
    """
    return build_explanation(case_id, analysis_uid)
