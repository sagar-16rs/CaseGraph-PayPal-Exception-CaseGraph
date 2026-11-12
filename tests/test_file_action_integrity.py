from __future__ import annotations

from types import SimpleNamespace

from backend.uploads.action_files import ActionFile, build_paypal_evidence_payload, extract_file_refs


def _payload(refs):
    item = SimpleNamespace(file_refs=refs)
    return SimpleNamespace(evidences=[item])


def test_extract_file_refs_rejects_conflicting_duplicate_uid():
    a = SimpleNamespace(file_uid="FILE-AAAABBBB11", sha256="a" * 64)
    b = SimpleNamespace(file_uid="FILE-AAAABBBB11", sha256="b" * 64)
    try:
        extract_file_refs(_payload([a, b]))
    except RuntimeError as exc:
        assert "conflicting hashes" in str(exc)
    else:
        raise AssertionError("conflicting duplicate file UID was accepted")


def test_extract_file_refs_rejects_same_duplicate_uid():
    a = SimpleNamespace(file_uid="FILE-AAAABBBB11", sha256="a" * 64)
    try:
        extract_file_refs(_payload([a, a]))
    except RuntimeError as exc:
        assert "more than once" in str(exc)
    else:
        raise AssertionError("duplicate file UID was accepted")


class FakeEvidence:
    def __init__(self, refs):
        self.file_refs = refs
    def model_dump(self, **_kwargs):
        return {"evidence_type": "OTHER", "notes": "proof", "file_refs": [vars(r) for r in self.file_refs]}


def test_build_payload_rechecks_approved_hash():
    ref = SimpleNamespace(file_uid="FILE-AAAABBBB11", sha256="a" * 64)
    payload = SimpleNamespace(evidences=[FakeEvidence([ref])])
    file = ActionFile("FILE-AAAABBBB11", "proof.pdf", "application/pdf", b"pdf", "b" * 64)
    try:
        build_paypal_evidence_payload(payload, [file])
    except RuntimeError as exc:
        assert "hash does not match" in str(exc)
    else:
        raise AssertionError("changed evidence bytes/hash were accepted")
