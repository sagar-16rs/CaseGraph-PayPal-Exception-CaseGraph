from sqlalchemy import select
from backend.db.models import AIAnalysis
def get_by_uid(s,case_id,uid): return s.scalar(select(AIAnalysis).where(AIAnalysis.case_id==case_id,AIAnalysis.analysis_uid==uid))
def get_by_request_id(s,rid): return s.scalar(select(AIAnalysis).where(AIAnalysis.request_id==rid))
def list_for_case(s,cid): return list(s.scalars(select(AIAnalysis).where(AIAnalysis.case_id==cid).order_by(AIAnalysis.created_at.desc())))
