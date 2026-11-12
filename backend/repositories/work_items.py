from datetime import datetime
from sqlalchemy import select,or_
from backend.db.models import WorkItem
def get_for_source(s,*,source_type,source_id,work_type): return s.scalar(select(WorkItem).where(WorkItem.source_type==source_type,WorkItem.source_id==source_id,WorkItem.work_type==work_type))
def add(s,row): s.add(row); s.flush(); return row
def get(s,uid,for_update=False):
    q=select(WorkItem).where(WorkItem.work_uid==uid)
    if for_update:q=q.with_for_update()
    return s.scalar(q)
def claim_next(s,*,now,lease_owner,lease_expires_at,max_attempts_default,use_skip_locked):
    q=select(WorkItem).where(WorkItem.available_at<=now,or_(WorkItem.status.in_(['READY','RETRY']),((WorkItem.status=='LEASED')&(WorkItem.lease_expires_at<now))),WorkItem.attempts<WorkItem.max_attempts).order_by(WorkItem.available_at,WorkItem.id).limit(1)
    if use_skip_locked:q=q.with_for_update(skip_locked=True)
    else:q=q.with_for_update()
    row=s.scalar(q)
    if row:
        row.status='LEASED';row.attempts+=1;row.max_attempts=row.max_attempts or max_attempts_default;row.lease_owner=lease_owner;row.lease_expires_at=lease_expires_at;row.updated_at=now;s.flush()
    return row
def list_recent(s,limit=100): return list(s.scalars(select(WorkItem).order_by(WorkItem.created_at.desc()).limit(limit)))
