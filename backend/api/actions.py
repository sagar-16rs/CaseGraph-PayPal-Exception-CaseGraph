from fastapi import APIRouter

from backend.actions.schemas import (
    ActionApprovalRequest,
    ActionApprovalResponse,
    ActionExecuteRequest,
    ActionExecutionResponse,
)
from backend.services.actions import action_engine

router = APIRouter(prefix='/api/cases', tags=['actions'])


# Every handler annotates its parameters. Without annotations FastAPI treats the
# request body as a required *query* parameter, which silently made the entire
# human-approval -> execution path unusable over HTTP while service-level tests
# still passed.
@router.post('/{case_id}/actions/approve', response_model=ActionApprovalResponse)
async def approve(case_id: str, req: ActionApprovalRequest) -> ActionApprovalResponse:
    return await action_engine.approve(case_id, req)


@router.get('/{case_id}/actions', response_model=list[ActionApprovalResponse])
async def list_actions(case_id: str) -> list[ActionApprovalResponse]:
    return await action_engine.list(case_id)


@router.get('/{case_id}/actions/{action_uid}', response_model=ActionApprovalResponse)
async def get_action(case_id: str, action_uid: str) -> ActionApprovalResponse:
    return await action_engine.get(case_id, action_uid)


@router.post('/{case_id}/actions/{action_uid}/execute', response_model=ActionExecutionResponse)
async def execute(
    case_id: str, action_uid: str, req: ActionExecuteRequest
) -> ActionExecutionResponse:
    return await action_engine.execute(case_id, action_uid, req)


@router.post('/{case_id}/actions/send-message', deprecated=True)
async def legacy(case_id: str):
    return {'detail': 'legacy route disabled by security gateway'}
