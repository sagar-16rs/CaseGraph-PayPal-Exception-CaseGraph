from fastapi import APIRouter

from backend.safety.service import safety_service

router = APIRouter(prefix='/api/cases', tags=['safety'])


@router.get('/{case_id}/ai/analyses/{analysis_uid}/safety')
def get(case_id: str, analysis_uid: str):
    return safety_service.get(case_id, analysis_uid).model_dump()


@router.post('/{case_id}/ai/analyses/{analysis_uid}/safety')
def assess(case_id: str, analysis_uid: str):
    return safety_service.assess(case_id, analysis_uid).model_dump()
