from sqlalchemy import select,func
from backend.db.models import CaseGraphRevision
def get_by_id(s,gid): return s.scalar(select(CaseGraphRevision).where(CaseGraphRevision.graph_id==gid))
def latest(s,cid): return s.scalar(select(CaseGraphRevision).where(CaseGraphRevision.case_id==cid).order_by(CaseGraphRevision.revision.desc()).limit(1))
def list_for_case(s,cid): return list(s.scalars(select(CaseGraphRevision).where(CaseGraphRevision.case_id==cid).order_by(CaseGraphRevision.revision.desc())))
def next_revision(s,cid): return int(s.scalar(select(func.max(CaseGraphRevision.revision)).where(CaseGraphRevision.case_id==cid)) or 0)+1

def get_revision(s,case_id,revision): return s.scalar(select(CaseGraphRevision).where(CaseGraphRevision.case_id==case_id,CaseGraphRevision.revision==revision))
