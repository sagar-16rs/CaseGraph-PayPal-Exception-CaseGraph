from fastapi import APIRouter
from backend.work.reconciliation import reconciliation_service
router=APIRouter(prefix="/api/cases",tags=["reconciliation"])
@router.post("/{case_id}/actions/{action_uid}/reconcile")
async def reconcile(case_id:str,action_uid:str): return await reconciliation_service.auto(case_id,action_uid)
@router.get("/{case_id}/actions/{action_uid}/reconciliations")
async def list_reconciliations(case_id:str,action_uid:str): return reconciliation_service.list(case_id,action_uid)
