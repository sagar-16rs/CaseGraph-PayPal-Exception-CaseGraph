from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from backend.actions.schemas import EvidenceFileRef, EvidenceInfo, EvidenceItem, ProvideEvidencePayload
from backend.uploads.action_files import ActionFile, build_paypal_evidence_payload, extract_file_refs
from backend.uploads.validation import UploadValidationError, validate_upload


PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 32
PDF = b"%PDF-1.7\n" + b"x" * 32
GIF = b"GIF89a" + b"x" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"x" * 32


@pytest.mark.parametrize(
    "name,data,mime",
    [
        ("a.pdf", PDF, "application/pdf"),
        ("a.png", PNG, "image/png"),
        ("a.gif", GIF, "image/gif"),
        ("a.jpg", JPEG, "image/jpeg"),
        ("a.jpeg", JPEG, "image/jpeg"),
    ],
)
def test_paypal_supported_signatures(name, data, mime):
    detected = validate_upload(name, data, mime, 9_000_000)
    assert detected.mime == mime


def test_extension_spoofing_rejected():
    with pytest.raises(UploadValidationError):
        validate_upload("invoice.pdf", PNG, "application/pdf", 9_000_000)


def test_double_extension_and_executable_rejected():
    with pytest.raises(UploadValidationError):
        validate_upload("invoice.pdf.exe", PDF, "application/pdf", 9_000_000)


def test_colon_and_null_rejected():
    with pytest.raises(UploadValidationError):
        validate_upload("x.pdf:evil", PDF, "application/pdf", 9_000_000)
    with pytest.raises(UploadValidationError):
        validate_upload("x\x00.pdf", PDF, "application/pdf", 9_000_000)


def test_file_hash_is_bound_into_action_payload():
    ref = EvidenceFileRef(file_uid="FILE-ABCDEF1234", sha256="a" * 64)
    payload = ProvideEvidencePayload(
        evidences=[EvidenceItem(evidence_type="OTHER", file_refs=[ref])]
    )
    dumped = payload.model_dump(mode="json", exclude_none=True)
    assert dumped["evidences"][0]["file_refs"][0]["sha256"] == "a" * 64
    assert extract_file_refs(payload) == [("FILE-ABCDEF1234", "a" * 64)]


def test_paypal_multipart_documents_match_generated_fields():
    ref = EvidenceFileRef(file_uid="FILE-ABCDEF1234", sha256="b" * 64)
    payload = ProvideEvidencePayload(
        evidences=[EvidenceItem(evidence_type="OTHER", file_refs=[ref])]
    )
    file = ActionFile(
        file_uid=ref.file_uid,
        filename="evidence.pdf",
        mime="application/pdf",
        content=PDF,
        sha256=ref.sha256,
    )
    input_body, parts = build_paypal_evidence_payload(payload, [file])
    assert input_body["evidences"][0]["documents"] == [{"name": "file1.pdf"}]
    assert "file_refs" not in input_body["evidences"][0]
    assert parts[0][0] == "file1"
    assert parts[0][1] == "file1.pdf"
    assert parts[0][3] == "application/pdf"


def test_duplicate_file_uid_across_evidence_items_is_rejected():
    first = EvidenceFileRef(file_uid="FILE-ABCDEF1234", sha256="a" * 64)
    conflicting = EvidenceFileRef(file_uid="FILE-ABCDEF1234", sha256="b" * 64)
    with pytest.raises(Exception):
        ProvideEvidencePayload(
            evidences=[
                EvidenceItem(evidence_type="OTHER", file_refs=[first]),
                EvidenceItem(evidence_type="OTHER", file_refs=[conflicting]),
            ]
        )
