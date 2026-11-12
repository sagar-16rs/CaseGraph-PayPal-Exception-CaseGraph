from sqlalchemy import select,func
from backend.db.models import EvidenceRevision,EvidenceSetRevision,EvidenceSetMember
def latest_set(s,cid): return s.scalar(select(EvidenceSetRevision).where(EvidenceSetRevision.case_id==cid).order_by(EvidenceSetRevision.revision.desc()).limit(1))
def by_request_id(s,rid): return s.scalar(select(EvidenceSetRevision).where(EvidenceSetRevision.request_id==rid))
def next_set_revision(s,cid): return int(s.scalar(select(func.max(EvidenceSetRevision.revision)).where(EvidenceSetRevision.case_id==cid)) or 0)+1
def next_source_revision(s,cid,ref): return int(s.scalar(select(func.max(EvidenceRevision.revision)).where(EvidenceRevision.case_id==cid,EvidenceRevision.source_ref==ref)) or 0)+1
def members(s,set_id):
    return list(s.execute(select(EvidenceSetMember,EvidenceRevision).join(EvidenceRevision,EvidenceRevision.id==EvidenceSetMember.evidence_revision_id).where(EvidenceSetMember.evidence_set_id==set_id).order_by(EvidenceSetMember.ordinal)).all())
