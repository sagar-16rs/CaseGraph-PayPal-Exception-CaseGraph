from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import String, Integer, DateTime, Boolean, Text, ForeignKey, UniqueConstraint, CheckConstraint, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column
from backend.db.base import Base

def utcnow(): return datetime.now(timezone.utc)

class Case(Base):
    __tablename__='cases'
    case_id: Mapped[str]=mapped_column(String(64), primary_key=True)
    paypal_dispute_id: Mapped[str]=mapped_column(String(128), unique=True, nullable=False, index=True)
    paypal_transaction_id: Mapped[str|None]=mapped_column(String(128))
    dispute_status: Mapped[str]=mapped_column(String(128), default='UNKNOWN', nullable=False)
    dispute_reason: Mapped[str|None]=mapped_column(String(128))
    dispute_amount: Mapped[str|None]=mapped_column(String(64))
    currency_code: Mapped[str|None]=mapped_column(String(8))
    allowed_response_options: Mapped[list]=mapped_column(JSON, default=list, nullable=False)
    raw_dispute_payload: Mapped[dict]=mapped_column(JSON, default=dict, nullable=False)
    sync_revision: Mapped[int]=mapped_column(Integer, default=1, nullable=False)
    paypal_snapshot_hash: Mapped[str|None]=mapped_column(String(64))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

class PayPalFact(Base):
    __tablename__='paypal_facts'
    id: Mapped[int]=mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str]=mapped_column(ForeignKey('cases.case_id', ondelete='CASCADE'), index=True)
    fact_id: Mapped[str]=mapped_column(String(128))
    revision: Mapped[int]=mapped_column(Integer)
    fact_type: Mapped[str]=mapped_column(String(128))
    value: Mapped[str]=mapped_column(Text)
    source: Mapped[str]=mapped_column(String(32), default='paypal_api')
    content_hash: Mapped[str]=mapped_column(String(64))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__=(UniqueConstraint('case_id','fact_id','revision',name='uq_paypal_fact_revision'),)

class EvidenceRevision(Base):
    __tablename__='evidence_revisions'
    id: Mapped[int]=mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str]=mapped_column(ForeignKey('cases.case_id', ondelete='CASCADE'), index=True)
    source_ref: Mapped[str]=mapped_column(String(128))
    revision: Mapped[int]=mapped_column(Integer)
    evidence_type: Mapped[str]=mapped_column(String(64))
    speaker: Mapped[str|None]=mapped_column(String(64))
    content: Mapped[str]=mapped_column(Text)
    metadata_json: Mapped[dict]=mapped_column(JSON, default=dict)
    content_hash: Mapped[str]=mapped_column(String(64))
    created_by: Mapped[str]=mapped_column(String(256))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__=(UniqueConstraint('case_id','source_ref','revision',name='uq_evidence_revision'),)

class EvidenceSetRevision(Base):
    __tablename__='evidence_set_revisions'
    id: Mapped[int]=mapped_column(Integer, primary_key=True, autoincrement=True)
    evidence_set_id: Mapped[str]=mapped_column(String(64), unique=True)
    case_id: Mapped[str]=mapped_column(ForeignKey('cases.case_id', ondelete='CASCADE'), index=True)
    revision: Mapped[int]=mapped_column(Integer)
    request_id: Mapped[str]=mapped_column(String(128), unique=True)
    request_hash: Mapped[str]=mapped_column(String(64))
    content_hash: Mapped[str]=mapped_column(String(64))
    created_by: Mapped[str]=mapped_column(String(256))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__=(UniqueConstraint('case_id','revision',name='uq_evidence_set_revision'),)

class EvidenceSetMember(Base):
    __tablename__='evidence_set_members'
    id: Mapped[int]=mapped_column(Integer, primary_key=True, autoincrement=True)
    evidence_set_id: Mapped[str]=mapped_column(ForeignKey('evidence_set_revisions.evidence_set_id', ondelete='CASCADE'), index=True)
    ordinal: Mapped[int]=mapped_column(Integer)
    evidence_revision_id: Mapped[int]=mapped_column(ForeignKey('evidence_revisions.id', ondelete='RESTRICT'))
    __table_args__=(UniqueConstraint('evidence_set_id','ordinal',name='uq_evidence_set_member_ordinal'),)

class CaseGraphRevision(Base):
    __tablename__='case_graph_revisions'
    id: Mapped[int]=mapped_column(Integer, primary_key=True, autoincrement=True)
    graph_id: Mapped[str]=mapped_column(String(96), unique=True)
    case_id: Mapped[str]=mapped_column(ForeignKey('cases.case_id', ondelete='CASCADE'), index=True)
    revision: Mapped[int]=mapped_column(Integer)
    input_case_revision: Mapped[int]=mapped_column(Integer)
    input_evidence_set_revision: Mapped[int]=mapped_column(Integer, default=0)
    creation_mode: Mapped[str]=mapped_column(String(16), default='AI')
    created_by: Mapped[str]=mapped_column(String(256))
    nodes_json: Mapped[list]=mapped_column(JSON, default=list)
    edges_json: Mapped[list]=mapped_column(JSON, default=list)
    content_hash: Mapped[str]=mapped_column(String(64))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__=(UniqueConstraint('case_id','revision',name='uq_graph_case_revision'),)

class AIAnalysis(Base):
    __tablename__='ai_analyses'
    id: Mapped[int]=mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_uid: Mapped[str]=mapped_column(String(64), unique=True, index=True)
    request_id: Mapped[str]=mapped_column(String(128), unique=True)
    case_id: Mapped[str]=mapped_column(ForeignKey('cases.case_id', ondelete='CASCADE'), index=True)
    input_case_revision: Mapped[int]=mapped_column(Integer)
    input_evidence_set_revision: Mapped[int]=mapped_column(Integer)
    graph_id: Mapped[str|None]=mapped_column(String(96))
    model_provider: Mapped[str]=mapped_column(String(64), default='static')
    model_name: Mapped[str]=mapped_column(String(128), default='static')
    prompt_version: Mapped[str]=mapped_column(String(64), default='casegraph_v1')
    prompt_hash: Mapped[str]=mapped_column(String(64), default='')
    schema_version: Mapped[str]=mapped_column(String(64), default='casegraph_schema_v1')
    schema_hash: Mapped[str]=mapped_column(String(64), default='')
    bundle_hash: Mapped[str]=mapped_column(String(64))
    output_hash: Mapped[str|None]=mapped_column(String(64))
    provider_response_id: Mapped[str|None]=mapped_column(String(128))
    status: Mapped[str]=mapped_column(String(32))
    validation_status: Mapped[str]=mapped_column(String(32), default='PENDING')
    output_json: Mapped[dict]=mapped_column(JSON, default=dict)
    error: Mapped[str|None]=mapped_column(Text)
    requested_by: Mapped[str]=mapped_column(String(256), default='system')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)

class AISafetyAssessment(Base):
    __tablename__='ai_safety_assessments'
    id: Mapped[int]=mapped_column(Integer, primary_key=True, autoincrement=True)
    safety_uid: Mapped[str]=mapped_column(String(64), unique=True)
    case_id: Mapped[str]=mapped_column(ForeignKey('cases.case_id', ondelete='CASCADE'), index=True)
    analysis_uid: Mapped[str]=mapped_column(String(64), index=True)
    graph_id: Mapped[str]=mapped_column(String(96))
    policy_version: Mapped[str]=mapped_column(String(64))
    policy_hash: Mapped[str]=mapped_column(String(64))
    safety_status: Mapped[str]=mapped_column(String(16))
    action_risk: Mapped[str]=mapped_column(String(16))
    recommended_action: Mapped[str]=mapped_column(String(64))
    effective_action: Mapped[str]=mapped_column(String(64))
    abstain_required: Mapped[bool]=mapped_column(Boolean, default=False)
    report_json: Mapped[dict]=mapped_column(JSON, default=dict)
    report_hash: Mapped[str]=mapped_column(String(64), default='')
    graph_hash: Mapped[str]=mapped_column(String(64), default='')
    is_stale: Mapped[bool]=mapped_column(Boolean, default=False)
    input_case_revision: Mapped[int]=mapped_column(Integer)
    input_evidence_set_revision: Mapped[int]=mapped_column(Integer)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)

class ActionApproval(Base):
    __tablename__='action_approvals'
    id: Mapped[int]=mapped_column(Integer, primary_key=True, autoincrement=True)
    action_uid: Mapped[str]=mapped_column(String(64), unique=True, index=True)
    action_request_id: Mapped[str]=mapped_column(String(128), unique=True)
    case_id: Mapped[str]=mapped_column(ForeignKey('cases.case_id', ondelete='CASCADE'), index=True)
    analysis_uid: Mapped[str]=mapped_column(String(64))
    safety_uid: Mapped[str]=mapped_column(String(64))
    graph_id: Mapped[str]=mapped_column(String(96))
    safety_policy_hash: Mapped[str]=mapped_column(String(64))
    action_policy_version: Mapped[str]=mapped_column(String(64))
    action_policy_hash: Mapped[str]=mapped_column(String(64))
    action_type: Mapped[str]=mapped_column(String(64))
    action_risk: Mapped[str]=mapped_column(String(16))
    approved_by: Mapped[str]=mapped_column(String(256))
    payload_json: Mapped[dict]=mapped_column(JSON)
    payload_hash: Mapped[str]=mapped_column(String(64))
    approval_context_json: Mapped[dict]=mapped_column(JSON)
    approval_context_hash: Mapped[str]=mapped_column(String(64))
    approval_hash: Mapped[str]=mapped_column(String(64))
    execution_status: Mapped[str]=mapped_column(String(32), default='NOT_STARTED')
    execution_started_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    unknown_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    post_action_sync_pending: Mapped[bool]=mapped_column(Boolean, default=False)
    paypal_response_status: Mapped[int|None]=mapped_column(Integer)
    paypal_response_body: Mapped[dict|None]=mapped_column(JSON)
    post_action_case_revision: Mapped[int|None]=mapped_column(Integer)
    last_error: Mapped[str|None]=mapped_column(Text)
    approved_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class CaseEvent(Base):
    __tablename__='case_events'
    id: Mapped[int]=mapped_column(Integer, primary_key=True, autoincrement=True)
    event_uid: Mapped[str]=mapped_column(String(64), unique=True)
    case_id: Mapped[str]=mapped_column(String(64), index=True)
    event_type: Mapped[str]=mapped_column(String(64))
    graph_revision: Mapped[int|None]=mapped_column(Integer)
    actor_type: Mapped[str]=mapped_column(String(32))
    actor_id: Mapped[str]=mapped_column(String(256))
    source: Mapped[str]=mapped_column(String(128))
    payload_json: Mapped[dict]=mapped_column(JSON, default=dict)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)

class PayPalEvent(Base):
    __tablename__='paypal_events'
    id: Mapped[int]=mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str]=mapped_column(String(128), unique=True, index=True)
    event_type: Mapped[str]=mapped_column(String(128))
    resource_id: Mapped[str|None]=mapped_column(String(128))
    payload: Mapped[dict]=mapped_column('payload_json', JSON)
    processed: Mapped[bool]=mapped_column(Boolean, default=False)
    process_attempts: Mapped[int]=mapped_column(Integer, default=0)
    processing_error: Mapped[str|None]=mapped_column(Text)
    processed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)

class WorkItem(Base):
    __tablename__='work_items'
    id: Mapped[int]=mapped_column(Integer, primary_key=True, autoincrement=True)
    work_uid: Mapped[str]=mapped_column(String(64), unique=True, index=True)
    work_type: Mapped[str]=mapped_column(String(64))
    source_type: Mapped[str]=mapped_column(String(64))
    source_id: Mapped[str]=mapped_column(String(128))
    status: Mapped[str]=mapped_column(String(32), default='READY', index=True)
    attempts: Mapped[int]=mapped_column(Integer, default=0)
    max_attempts: Mapped[int]=mapped_column(Integer, default=8)
    available_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)
    lease_owner: Mapped[str|None]=mapped_column(String(128))
    lease_expires_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    last_error: Mapped[str|None]=mapped_column(Text)
    completed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow,onupdate=utcnow)
    __table_args__=(UniqueConstraint('source_type','source_id','work_type',name='uq_work_source'),)

class ActionReconciliation(Base):
    __tablename__='action_reconciliations'
    id: Mapped[int]=mapped_column(Integer, primary_key=True, autoincrement=True)
    reconciliation_uid: Mapped[str]=mapped_column(String(64), unique=True)
    action_uid: Mapped[str]=mapped_column(String(64), index=True)
    case_id: Mapped[str]=mapped_column(String(64), index=True)
    method: Mapped[str]=mapped_column(String(32))
    outcome: Mapped[str]=mapped_column(String(32))
    # Execution status of the action *after* this reconciliation decision. The
    # reconciliation record is the audit trail of who moved an ambiguous write to
    # a terminal state, so the resulting status must be stored, not inferred later
    # from mutable action state.
    resulting_execution_status: Mapped[str]=mapped_column(String(32))
    observed_snapshot_hash: Mapped[str|None]=mapped_column(String(64))
    details_json: Mapped[dict]=mapped_column(JSON, default=dict)
    details_hash: Mapped[str]=mapped_column(String(64))
    record_hash: Mapped[str]=mapped_column(String(64))
    reconciled_by: Mapped[str|None]=mapped_column(String(256))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)

