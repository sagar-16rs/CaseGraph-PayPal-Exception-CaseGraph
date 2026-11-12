from __future__ import annotations

import hashlib

from backend.db.models import CaseGraphRevision
from backend.db.session import session_scope
from backend.evidence.domain import canonical_json_bytes
from backend.repositories import cases as case_repo
from backend.repositories import evidence as evidence_repo
from backend.repositories import graphs as graph_repo


class GraphStaleInputError(RuntimeError):
    pass


class GraphService:
    def create(
        self,
        case_id: str,
        nodes: list[dict],
        edges: list[dict],
        created_by: str = "system",
        creation_mode: str = "AI",
        *,
        expected_case_revision: int | None = None,
        expected_evidence_set_revision: int | None = None,
    ) -> dict:
        """Commit an immutable graph revision against one exact input snapshot.

        For AI graphs the expected revisions are mandatory at the call site. The
        check and insert happen in the same DB transaction so a model result based
        on stale evidence cannot be committed as current reasoning.
        """
        with session_scope() as session:
            case = case_repo.get_by_id_for_update(session, case_id)
            if case is None:
                raise KeyError(case_id)
            evidence_set = evidence_repo.latest_set(session, case_id)
            evidence_revision = evidence_set.revision if evidence_set else 0

            if expected_case_revision is not None and case.sync_revision != expected_case_revision:
                raise GraphStaleInputError(
                    f"case revision changed from {expected_case_revision} to {case.sync_revision}"
                )
            if (
                expected_evidence_set_revision is not None
                and evidence_revision != expected_evidence_set_revision
            ):
                raise GraphStaleInputError(
                    "evidence-set revision changed from "
                    f"{expected_evidence_set_revision} to {evidence_revision}"
                )

            revision = graph_repo.next_revision(session, case_id)
            graph_id = f"{case_id}-R{revision}"
            content = {
                "case_id": case_id,
                "revision": revision,
                "input_case_revision": case.sync_revision,
                "input_evidence_set_revision": evidence_revision,
                "creation_mode": creation_mode,
                "nodes": nodes,
                "edges": edges,
            }
            content_hash = hashlib.sha256(canonical_json_bytes(content)).hexdigest()
            row = CaseGraphRevision(
                graph_id=graph_id,
                case_id=case_id,
                revision=revision,
                input_case_revision=case.sync_revision,
                input_evidence_set_revision=evidence_revision,
                creation_mode=creation_mode,
                created_by=created_by,
                nodes_json=nodes,
                edges_json=edges,
                content_hash=content_hash,
            )
            session.add(row)
            session.flush()
            return self.serialize(row, case.sync_revision, evidence_revision)

    def serialize(
        self,
        row: CaseGraphRevision,
        current_case: int | None = None,
        current_ev: int | None = None,
    ) -> dict:
        return {
            "graph_id": row.graph_id,
            "case_id": row.case_id,
            "revision": row.revision,
            "input_case_revision": row.input_case_revision,
            "current_case_revision": current_case if current_case is not None else row.input_case_revision,
            "input_evidence_set_revision": row.input_evidence_set_revision,
            "current_evidence_set_revision": current_ev if current_ev is not None else row.input_evidence_set_revision,
            "evidence_staleness_unknown": False,
            "is_stale": (
                current_case is not None and current_case != row.input_case_revision
            ) or (
                current_ev is not None and current_ev != row.input_evidence_set_revision
            ),
            "creation_mode": row.creation_mode,
            "created_by": row.created_by,
            "content_hash": row.content_hash,
            "created_at": row.created_at.isoformat(),
            "nodes": row.nodes_json,
            "edges": row.edges_json,
        }


graph_service = GraphService()
