from typing import Literal

from pydantic import BaseModel, Field


class WorkItemResponse(BaseModel):
    work_uid:str; work_type:str; source_type:str; source_id:str; status:str; attempts:int; max_attempts:int; available_at:str; lease_owner:str|None=None; lease_expires_at:str|None=None; last_error:str|None=None; created_at:str; updated_at:str; completed_at:str|None=None


class QueueStatusResponse(BaseModel):
    ready:int=0; leased:int=0; retry:int=0; completed:int=0; dead_letter:int=0; oldest_available_at:str|None=None


class ManualReconciliationRequest(BaseModel):
    """Operator-only resolution of an ambiguous PayPal write.

    `confirmed_from_paypal_dashboard` is not decorative: ambiguous writes fail
    closed, so the operator must assert that the outcome was checked directly in
    PayPal. The service rejects the request when the assertion is missing.
    """

    decision: Literal["CONFIRMED_EXECUTED", "CONFIRMED_NOT_EXECUTED"]
    confirmed_from_paypal_dashboard: bool = False
    confirmed_by: str = Field(min_length=1, max_length=256)
    note: str = Field(min_length=1, max_length=2000)


class ReconciliationResponse(BaseModel):
    reconciliation_uid: str
    action_uid: str
    case_id: str
    method: str
    outcome: str
    observed_snapshot_hash: str | None = None
    details: dict = Field(default_factory=dict)
    reconciled_by: str | None = None
    created_at: str
    execution_status: str
