from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ActionFile:
    file_uid: str
    filename: str
    mime: str
    content: bytes
    sha256: str


def extract_file_refs(payload: Any) -> list[tuple[str, str]]:
    """Extract immutable file references from an already-validated action payload.

    security Pydantic schemas already reject a file UID reused across evidence items.
    integration repeats the invariant here so future callers that bypass those schemas do
    not silently collapse conflicting UID/hash pairs.
    """
    refs: list[tuple[str, str]] = []
    seen: dict[str, str] = {}
    for item in getattr(payload, "evidences", []) or []:
        for ref in getattr(item, "file_refs", []) or []:
            uid = str(ref.file_uid)
            digest = str(ref.sha256)
            prior = seen.get(uid)
            if prior is not None:
                if prior != digest:
                    raise RuntimeError(f"evidence file {uid} is referenced with conflicting hashes")
                raise RuntimeError(f"evidence file {uid} is referenced more than once")
            seen[uid] = digest
            refs.append((uid, digest))
    return refs


def build_paypal_evidence_payload(
    payload: Any,
    files: list[ActionFile],
) -> tuple[dict[str, Any], list[tuple[str, str, bytes, str]]]:
    by_uid = {item.file_uid: item for item in files}
    if len(by_uid) != len(files):
        raise RuntimeError("resolved evidence files contain duplicate file UIDs")

    multipart: list[tuple[str, str, bytes, str]] = []
    evidences: list[dict[str, Any]] = []
    counter = 1
    used_uids: set[str] = set()

    for evidence in payload.evidences:
        raw = evidence.model_dump(mode="json", exclude_none=True)
        file_refs = raw.pop("file_refs", [])
        documents: list[dict[str, str]] = []
        for ref in file_refs:
            uid = ref["file_uid"]
            expected_sha = ref["sha256"]
            if uid in used_uids:
                raise RuntimeError(f"evidence file {uid} is referenced more than once")
            used_uids.add(uid)

            file = by_uid.get(uid)
            if file is None:
                raise RuntimeError(f"approved evidence file {uid} is unavailable")
            if file.sha256 != expected_sha:
                raise RuntimeError(f"approved evidence file {uid} hash does not match the approved payload")
            if len(file.content) >= 10_000_000:
                raise RuntimeError(f"approved evidence file {uid} is not below PayPal's 10 MB per-file limit")

            suffix_index = file.filename.rfind(".")
            suffix = file.filename[suffix_index:] if suffix_index >= 0 else ""
            field = f"file{counter}"
            filename = f"{field}{suffix}"
            documents.append({"name": filename})
            multipart.append((field, filename, file.content, file.mime))
            counter += 1
        if documents:
            raw["documents"] = documents
        evidences.append(raw)

    total = sum(len(item[2]) for item in multipart)
    if total > 50_000_000:
        raise RuntimeError("PayPal evidence files exceed the 50 MB per-call limit")
    return {"evidences": evidences}, multipart
