from sqlalchemy import select
from backend.db.models import PayPalEvent
def get(s,eid): return s.scalar(select(PayPalEvent).where(PayPalEvent.event_id==eid))
def get_by_event_id(s,eid): return get(s,eid)
def add(s,row): s.add(row); s.flush(); return row
def list_unprocessed(s): return list(s.scalars(select(PayPalEvent).where(PayPalEvent.processed==False).order_by(PayPalEvent.received_at)))
