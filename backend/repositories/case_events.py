import uuid
from backend.db.models import CaseEvent
def append_event(s,*,case_id,event_type,graph_revision=None,actor_type='system',actor_id='system',source='casegraph',payload=None):
    row=CaseEvent(event_uid='EVT-'+uuid.uuid4().hex.upper(),case_id=case_id,event_type=str(event_type),graph_revision=graph_revision,actor_type=actor_type,actor_id=actor_id,source=source,payload_json=payload or {}); s.add(row); s.flush(); return row
