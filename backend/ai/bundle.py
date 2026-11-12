from __future__ import annotations

from sqlalchemy import select

from backend.db.models import PayPalFact
from backend.db.session import session_scope
from backend.repositories import cases as case_repo
from backend.repositories import evidence as evidence_repo


def build_analysis_bundle(case_id: str) -> dict:
    """Build the exact, normalized, frozen input exposed to the reasoning model.

    Raw PayPal JSON and unrelated database state are deliberately excluded. The
    model sees only authoritative normalized facts, the exact active evidence-set
    revisions, and the currently available action identifiers.
    """
    with session_scope() as session:
        case = case_repo.get_by_id(session, case_id)
        if case is None:
            raise KeyError(case_id)

        evidence_set = evidence_repo.latest_set(session, case_id)
        evidence = []
        if evidence_set is not None:
            for member, item in evidence_repo.members(session, evidence_set.evidence_set_id):
                evidence.append(
                    {
                        "ordinal": member.ordinal,
                        "source_ref": item.source_ref,
                        "revision": item.revision,
                        "evidence_type": item.evidence_type,
                        "speaker": item.speaker,
                        "content": item.content,
                        "metadata": item.metadata_json,
                        "content_hash": item.content_hash,
                    }
                )

        facts = [
            {
                "ref": fact.fact_id,
                "revision": fact.revision,
                "fact_type": fact.fact_type,
                "value": fact.value,
                "content_hash": fact.content_hash,
            }
            for fact in session.scalars(
                select(PayPalFact)
                .where(PayPalFact.case_id == case_id, PayPalFact.revision == case.sync_revision)
                .order_by(PayPalFact.fact_id.asc())
            )
        ]

        return {
            "case_id": case_id,
            "case_revision": case.sync_revision,
            "evidence_set_revision": evidence_set.revision if evidence_set else 0,
            "paypal_facts": facts,
            "evidence": evidence,
            "available_actions": sorted(set(case.allowed_response_options or [])),
        }
