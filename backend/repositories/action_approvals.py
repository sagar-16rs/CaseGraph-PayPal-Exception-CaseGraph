from sqlalchemy import select
from backend.db.models import ActionApproval
def add(s,row): s.add(row); s.flush(); return row
def get_by_uid(s,uid,for_update=False):
    stmt=select(ActionApproval).where(ActionApproval.action_uid==uid)
    if for_update: stmt=stmt.with_for_update()
    return s.scalar(stmt)
def get_by_request_id(s,rid): return s.scalar(select(ActionApproval).where(ActionApproval.action_request_id==rid))
def list_for_case(s,cid): return list(s.scalars(select(ActionApproval).where(ActionApproval.case_id==cid).order_by(ActionApproval.approved_at.desc())))
def unresolved_for_case(s,cid,exclude_uid=None):
    stmt=select(ActionApproval).where(ActionApproval.case_id==cid,ActionApproval.execution_status.in_(['PENDING','UNKNOWN_OUTCOME']))
    if exclude_uid: stmt=stmt.where(ActionApproval.action_uid!=exclude_uid)
    return s.scalar(stmt.limit(1))
