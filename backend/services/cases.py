from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from backend.db.models import Case, EvidenceRevision, EvidenceSetMember, EvidenceSetRevision, PayPalFact
from backend.db.session import session_scope
from backend.evidence.domain import canonical_json_bytes, content_hash
from backend.repositories import cases as case_repo
from backend.repositories import evidence as evidence_repo


SUPPORTED_ACTION_RELS = {
    "SEND_MESSAGE",
    "MAKE_OFFER",
    "ACCEPT_CLAIM",
    "PROVIDE_EVIDENCE",
    "ESCALATE",
    "PROVIDE_SUPPORTING_INFO",
    "ACKNOWLEDGE_RETURN_ITEM",
    "APPEAL",
}


def paypal_snapshot_hash(payload: dict[str, Any]) -> str:
    """Exact canonical response-content hash used only for no-op deduplication."""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def case_id_for_dispute(dispute_id: str) -> str:
    return "CASE-" + hashlib.sha256(dispute_id.encode("utf-8")).hexdigest()[:20].upper()


def _supported_actions(payload: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    for link in payload.get("links") or []:
        rel = str(link.get("rel") or "").upper().replace("-", "_")
        if rel in SUPPORTED_ACTION_RELS and rel not in actions:
            actions.append(rel)
    return actions


def _money(value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, dict):
        return None, None
    amount = value.get("value")
    currency = value.get("currency_code")
    return (str(amount) if amount is not None else None, str(currency) if currency else None)


def _transaction_id(payload: dict[str, Any]) -> str | None:
    transactions = payload.get("disputed_transactions") or []
    if not transactions or not isinstance(transactions[0], dict):
        return None
    return transactions[0].get("seller_transaction_id") or transactions[0].get("buyer_transaction_id")


def _fact_values(payload: dict[str, Any], actions: list[str]) -> list[tuple[str, str, str]]:
    amount, currency = _money(payload.get("dispute_amount"))
    refund_amount, refund_currency = _money((payload.get("refund_details") or {}).get("allowed_refund_amount"))
    values: list[tuple[str, str, str | None]] = [
        ("PF-DISPUTE-ID", "PAYPAL_DISPUTE_ID", str(payload.get("dispute_id") or payload.get("id") or "") or None),
        ("PF-STATUS", "PAYPAL_DISPUTE_STATUS", str(payload.get("status") or "") or None),
        ("PF-REASON", "PAYPAL_DISPUTE_REASON", str(payload.get("reason") or "") or None),
        ("PF-LIFECYCLE", "PAYPAL_DISPUTE_LIFECYCLE_STAGE", str(payload.get("dispute_life_cycle_stage") or "") or None),
        ("PF-AMOUNT", "PAYPAL_DISPUTE_AMOUNT", f"{amount} {currency}" if amount and currency else amount),
        ("PF-DUE", "PAYPAL_SELLER_RESPONSE_DUE_DATE", str(payload.get("seller_response_due_date") or "") or None),
        ("PF-TRANSACTION", "PAYPAL_TRANSACTION_ID", _transaction_id(payload)),
        ("PF-ALLOWED-ACTIONS", "PAYPAL_AVAILABLE_ACTIONS", json.dumps(sorted(actions), separators=(",", ":"))),
        (
            "PF-REFUND-CEILING",
            "PAYPAL_ALLOWED_REFUND_AMOUNT",
            f"{refund_amount} {refund_currency}" if refund_amount and refund_currency else refund_amount,
        ),
    ]
    return [(fact_id, fact_type, value) for fact_id, fact_type, value in values if value is not None]


def _detail_payload(
    case: Case,
    facts: list[PayPalFact],
    external_evidence: list[dict[str, Any]],
    evidence_set_revision: int,
) -> dict[str, Any]:
    """Assemble the case detail contract shared by the single and list paths."""
    amount = case.dispute_amount
    if amount and case.currency_code:
        amount = f"{amount} {case.currency_code}"
    raw = case.raw_dispute_payload or {}
    return {
        "case_id": case.case_id,
        "paypal_dispute_id": case.paypal_dispute_id,
        "paypal_transaction_id": case.paypal_transaction_id,
        "dispute_status": case.dispute_status,
        "dispute_reason": case.dispute_reason,
        "dispute_amount": amount,
        "allowed_response_options": list(case.allowed_response_options or []),
        # Surfaces the non-authoritative demo transport in the UI. This is
        # a boolean derived from the stored PayPal payload, never new state.
        "simulated": bool(raw.get("simulated")),
        "sync_revision": case.sync_revision,
        "evidence_set_revision": evidence_set_revision,
        "verified_facts": [
            {
                "fact_id": fact.fact_id,
                "type": fact.fact_type,
                "value": fact.value,
                "source": fact.source,
                "verified": True,
            }
            for fact in facts
        ],
        "external_evidence": external_evidence,
    }


class CaseService:

    def sync_dispute_concurrency_safe(self, payload: dict[str, Any]) -> str:
        dispute_id = str(payload.get("dispute_id") or payload.get("id") or "")
        if not dispute_id:
            raise ValueError("PayPal dispute payload missing dispute_id/id")

        case_id = case_id_for_dispute(dispute_id)
        snapshot_hash = paypal_snapshot_hash(payload)
        amount, currency = _money(payload.get("dispute_amount"))
        actions = _supported_actions(payload)
        transaction_id = _transaction_id(payload)

        with session_scope() as session:
            row = case_repo.get_by_dispute_id(session, dispute_id, for_update=True)
            changed = row is None or row.paypal_snapshot_hash != snapshot_hash
            if row is None:
                row = Case(
                    case_id=case_id,
                    paypal_dispute_id=dispute_id,
                    paypal_transaction_id=transaction_id,
                    dispute_status=str(payload.get("status") or "UNKNOWN"),
                    dispute_reason=payload.get("reason"),
                    dispute_amount=amount,
                    currency_code=currency,
                    allowed_response_options=actions,
                    raw_dispute_payload=payload,
                    sync_revision=1,
                    paypal_snapshot_hash=snapshot_hash,
                )
                session.add(row)
                session.flush()
            elif changed:
                row.sync_revision += 1
                row.paypal_transaction_id = transaction_id
                row.dispute_status = str(payload.get("status") or row.dispute_status)
                row.dispute_reason = payload.get("reason")
                row.dispute_amount = amount
                row.currency_code = currency
                row.allowed_response_options = actions
                row.raw_dispute_payload = payload
                row.paypal_snapshot_hash = snapshot_hash
                row.updated_at = datetime.now(timezone.utc)

            if changed:
                for fact_id, fact_type, value in _fact_values(payload, actions):
                    session.add(
                        PayPalFact(
                            case_id=case_id,
                            fact_id=fact_id,
                            revision=row.sync_revision,
                            fact_type=fact_type,
                            value=value,
                            content_hash=content_hash({"fact_type": fact_type, "value": value}),
                        )
                    )

        return case_id

    def get(self, case_id: str) -> Case | None:
        with session_scope() as session:
            return case_repo.get_by_id(session, case_id)

    def list(self) -> list[Case]:
        with session_scope() as session:
            return case_repo.list_all(session)

    def detail(self, case_id: str) -> dict[str, Any] | None:
        with session_scope() as session:
            case = case_repo.get_by_id(session, case_id)
            if case is None:
                return None
            facts = list(
                session.scalars(
                    select(PayPalFact)
                    .where(PayPalFact.case_id == case_id, PayPalFact.revision == case.sync_revision)
                    .order_by(PayPalFact.fact_id.asc())
                )
            )
            evidence_set = evidence_repo.latest_set(session, case_id)
            external_evidence = []
            if evidence_set is not None:
                for _ordinal, item in evidence_repo.members(session, evidence_set.evidence_set_id):
                    external_evidence.append(
                        {
                            "source_ref": item.source_ref,
                            "revision": item.revision,
                            "evidence_type": item.evidence_type,
                            "speaker": item.speaker,
                            "content": item.content,
                            "metadata": item.metadata_json,
                            "content_hash": item.content_hash,
                            "created_by": item.created_by,
                        }
                    )
            return _detail_payload(
                case,
                facts,
                external_evidence,
                evidence_set.revision if evidence_set else 0,
            )

    def list_details(self) -> list[dict[str, Any]]:
        """Every case detail in a constant number of queries.

        The previous implementation called `detail()` once per case, which issued
        four queries per row (facts, latest evidence set, members, plus the case
        itself). On a dispute board that is the difference between four queries and
        four hundred, so the list endpoint gets its own batched projection rather
        than reusing the single-case read.
        """
        with session_scope() as session:
            cases = case_repo.list_all(session)
            if not cases:
                return []
            case_ids = [case.case_id for case in cases]

            facts_by_case: dict[str, list[PayPalFact]] = defaultdict(list)
            for fact in session.scalars(
                select(PayPalFact).where(PayPalFact.case_id.in_(case_ids)).order_by(PayPalFact.fact_id.asc())
            ):
                facts_by_case[fact.case_id].append(fact)

            latest_set: dict[str, EvidenceSetRevision] = {}
            for evidence_set in session.scalars(
                select(EvidenceSetRevision)
                .where(EvidenceSetRevision.case_id.in_(case_ids))
                .order_by(EvidenceSetRevision.revision.asc())
            ):
                latest_set[evidence_set.case_id] = evidence_set

            members_by_set: dict[str, list[tuple[int, EvidenceRevision]]] = defaultdict(list)
            set_ids = [item.evidence_set_id for item in latest_set.values()]
            if set_ids:
                for member, revision in session.execute(
                    select(EvidenceSetMember, EvidenceRevision)
                    .join(EvidenceRevision, EvidenceRevision.id == EvidenceSetMember.evidence_revision_id)
                    .where(EvidenceSetMember.evidence_set_id.in_(set_ids))
                    .order_by(EvidenceSetMember.ordinal)
                ):
                    members_by_set[member.evidence_set_id].append((member.ordinal, revision))

            result: list[dict[str, Any]] = []
            for case in cases:
                evidence_set = latest_set.get(case.case_id)
                members = members_by_set.get(evidence_set.evidence_set_id, []) if evidence_set else []
                external_evidence = [
                    {
                        "source_ref": item.source_ref,
                        "revision": item.revision,
                        "evidence_type": item.evidence_type,
                        "speaker": item.speaker,
                        "content": item.content,
                        "metadata": item.metadata_json,
                        "content_hash": item.content_hash,
                        "created_by": item.created_by,
                    }
                    for _ordinal, item in members
                ]
                facts = [
                    fact
                    for fact in facts_by_case.get(case.case_id, [])
                    if fact.revision == case.sync_revision
                ]
                result.append(
                    _detail_payload(
                        case,
                        facts,
                        external_evidence,
                        evidence_set.revision if evidence_set else 0,
                    )
                )
            return result


case_service = CaseService()
