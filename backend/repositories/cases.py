from sqlalchemy import select
from backend.db.models import Case

def get_by_id(s,case_id,for_update=False):
    stmt=select(Case).where(Case.case_id==case_id)
    if for_update: stmt=stmt.with_for_update()
    return s.scalar(stmt)
def get_by_dispute_id(s,did,for_update=False):
    stmt=select(Case).where(Case.paypal_dispute_id==did)
    if for_update: stmt=stmt.with_for_update()
    return s.scalar(stmt)
def list_all(s): return list(s.scalars(select(Case).order_by(Case.updated_at.desc())))

def get_by_id_for_update(s,case_id): return get_by_id(s,case_id,for_update=True)
