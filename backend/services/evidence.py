from __future__ import annotations

import hashlib
import uuid

from backend.db.models import EvidenceRevision, EvidenceSetMember, EvidenceSetRevision
from backend.db.session import session_scope
from backend.evidence.domain import content_hash
from backend.repositories import cases as case_repo
from backend.repositories import evidence as evidence_repo


def _namespace_for_set(revision: int) -> str:
    # Preserve legacy evidence refs for the first intake so historical graphs and
    # tests remain valid. Later append-only intakes receive new source identities
    # instead of silently turning a new chat line into CHAT-1 revision 2.
    return "" if revision == 1 else f"{revision}-"


class EvidenceService:
    def ingest_support_intake(self, case_id, req):
        request_id = req.intake_request_id or "INTAKE-" + uuid.uuid4().hex.upper()
        request_body = req.model_dump(mode="json")
        request_hash = content_hash(request_body)

        with session_scope() as session:
            if case_repo.get_by_id_for_update(session, case_id) is None:
                raise KeyError(case_id)

            old = evidence_repo.by_request_id(session, request_id)
            if old:
                if old.case_id != case_id or old.request_hash != request_hash:
                    raise ValueError("intake_request_id reused with different case or payload")
                return self._serialize(session, old)

            previous_set = evidence_repo.latest_set(session, case_id)
            next_set_revision = evidence_repo.next_set_revision(session, case_id)
            namespace = _namespace_for_set(next_set_revision)

            entries = []
            for index, turn in enumerate(req.transcript, 1):
                entries.append(
                    (
                        f"CHAT-{namespace}{index}",
                        "transcript",
                        turn.speaker,
                        turn.message,
                        {},
                    )
                )
            if req.merchant_notes:
                entries.append(
                    (
                        f"NOTE-{namespace}1",
                        "merchant_note",
                        "merchant_agent",
                        req.merchant_notes,
                        {},
                    )
                )
            if req.attachment_metadata:
                entries.append(
                    (
                        f"DOC-{namespace}1",
                        "document_metadata",
                        "merchant_agent",
                        str(req.attachment_metadata.get("filename", "attachment")),
                        req.attachment_metadata,
                    )
                )

            # Start from the exact previous active snapshot. New intake is append-
            # only and does not make earlier evidence disappear.
            active_revisions: list[EvidenceRevision] = []
            if previous_set is not None:
                active_revisions.extend(
                    item for _ordinal, item in evidence_repo.members(session, previous_set.evidence_set_id)
                )

            new_revisions: list[EvidenceRevision] = []
            for source_ref, evidence_type, speaker, content, metadata in entries:
                revision = evidence_repo.next_source_revision(session, case_id, source_ref)
                item_hash = content_hash(
                    {
                        "source_ref": source_ref,
                        "revision": revision,
                        "content": content,
                        "metadata": metadata,
                        "speaker": speaker,
                    }
                )
                item = EvidenceRevision(
                    case_id=case_id,
                    source_ref=source_ref,
                    revision=revision,
                    evidence_type=evidence_type,
                    speaker=speaker,
                    content=content,
                    metadata_json=metadata,
                    content_hash=item_hash,
                    created_by=req.created_by,
                )
                session.add(item)
                session.flush()
                new_revisions.append(item)

            active_revisions.extend(new_revisions)
            evidence_set_id = "ESET-" + uuid.uuid4().hex.upper()
            set_hash = content_hash(
                [
                    {
                        "source_ref": item.source_ref,
                        "revision": item.revision,
                        "content_hash": item.content_hash,
                    }
                    for item in active_revisions
                ]
            )
            evidence_set = EvidenceSetRevision(
                evidence_set_id=evidence_set_id,
                case_id=case_id,
                revision=next_set_revision,
                request_id=request_id,
                request_hash=request_hash,
                content_hash=set_hash,
                created_by=req.created_by,
            )
            session.add(evidence_set)
            session.flush()

            for ordinal, item in enumerate(active_revisions):
                session.add(
                    EvidenceSetMember(
                        evidence_set_id=evidence_set_id,
                        ordinal=ordinal,
                        evidence_revision_id=item.id,
                    )
                )
            session.flush()
            return self._serialize(session, evidence_set)

    def _serialize(self, session, evidence_set):
        return {
            "evidence_set_id": evidence_set.evidence_set_id,
            "case_id": evidence_set.case_id,
            "revision": evidence_set.revision,
            "request_id": evidence_set.request_id,
            "request_hash": evidence_set.request_hash,
            "content_hash": evidence_set.content_hash,
            "created_by": evidence_set.created_by,
            "created_at": evidence_set.created_at.isoformat(),
            "members": [
                {
                    "ordinal": member.ordinal,
                    "evidence": {
                        "source_ref": item.source_ref,
                        "revision": item.revision,
                        "evidence_type": item.evidence_type,
                        "speaker": item.speaker,
                        "content": item.content,
                        "metadata": item.metadata_json,
                        "content_hash": item.content_hash,
                        "created_by": item.created_by,
                        "created_at": item.created_at.isoformat(),
                    },
                }
                for member, item in evidence_repo.members(session, evidence_set.evidence_set_id)
            ],
        }

    def current(self, case_id):
        with session_scope() as session:
            evidence_set = evidence_repo.latest_set(session, case_id)
            return None if evidence_set is None else self._serialize(session, evidence_set)


evidence_service = EvidenceService()
