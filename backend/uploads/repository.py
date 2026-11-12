from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.uploads.models import EvidenceFile


def add(session: Session, row: EvidenceFile) -> EvidenceFile:
    session.add(row)
    session.flush()
    return row


def get(session: Session, file_uid: str) -> EvidenceFile | None:
    return session.scalar(select(EvidenceFile).where(EvidenceFile.file_uid == file_uid))


def list_for_case(session: Session, case_id: str) -> list[EvidenceFile]:
    return list(
        session.scalars(
            select(EvidenceFile)
            .where(EvidenceFile.case_id == case_id)
            .order_by(EvidenceFile.created_at.asc(), EvidenceFile.id.asc())
        )
    )
