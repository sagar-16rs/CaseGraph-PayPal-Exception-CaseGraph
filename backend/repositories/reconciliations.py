from sqlalchemy import select
from backend.db.models import ActionReconciliation
def add(s,row): s.add(row); s.flush(); return row
def list_for_action(s,uid): return list(s.scalars(select(ActionReconciliation).where(ActionReconciliation.action_uid==uid).order_by(ActionReconciliation.created_at)))
