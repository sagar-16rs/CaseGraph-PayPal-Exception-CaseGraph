from sqlalchemy import select
from backend.db.models import AISafetyAssessment
def get_by_uid(s,uid): return s.scalar(select(AISafetyAssessment).where(AISafetyAssessment.safety_uid==uid))
def latest_for_analysis(s,cid,aid): return s.scalar(select(AISafetyAssessment).where(AISafetyAssessment.case_id==cid,AISafetyAssessment.analysis_uid==aid).order_by(AISafetyAssessment.created_at.desc()).limit(1))

def latest(s,analysis_uid): return s.scalar(select(AISafetyAssessment).where(AISafetyAssessment.analysis_uid==analysis_uid).order_by(AISafetyAssessment.created_at.desc()).limit(1))
