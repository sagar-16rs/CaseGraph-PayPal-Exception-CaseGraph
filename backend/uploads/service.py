from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from backend.db.session import session_scope
from backend.security.config import security_config
from backend.services.cases import case_service
from backend.uploads import repository as upload_repo
from backend.uploads.action_files import ActionFile
from backend.uploads.models import EvidenceFile
from backend.uploads.scanner import MalwareScanError, build_scanner
from backend.uploads.validation import UploadValidationError, validate_upload


class UploadIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StoredFile:
    file_uid: str
    case_id: str
    original_name: str
    detected_mime: str
    extension: str
    size_bytes: int
    sha256: str
    scan_status: str
    created_by: str
    created_at: str


def _response(row: EvidenceFile) -> StoredFile:
    return StoredFile(
        file_uid=row.file_uid,
        case_id=row.case_id,
        original_name=row.original_name,
        detected_mime=row.detected_mime,
        extension=row.extension,
        size_bytes=int(row.size_bytes),
        sha256=row.sha256,
        scan_status=row.scan_status,
        created_by=row.created_by,
        created_at=row.created_at.isoformat(),
    )


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _storage_path(storage_key: str) -> Path:
    base = security_config.upload_dir.resolve()
    path = (base / storage_key).resolve()
    if base != path and base not in path.parents:
        raise UploadIntegrityError("invalid evidence storage key")
    return path


def _read_verified(row: EvidenceFile) -> bytes:
    path = _storage_path(row.storage_key)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise UploadIntegrityError(f"evidence file {row.file_uid} is missing from private storage") from exc
    if len(data) != row.size_bytes or _sha256_bytes(data) != row.sha256:
        raise UploadIntegrityError(f"evidence file {row.file_uid} failed content-hash verification")
    return data


def store(case_id: str, filename: str, data: bytes, content_type: str | None, created_by: str) -> StoredFile:
    if case_service.get(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    try:
        detected = validate_upload(filename, data, content_type, security_config.upload_max_file_bytes)
        scanner = build_scanner(security_config)
    except (UploadValidationError, MalwareScanError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    root = security_config.upload_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    case_bucket = hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:16]
    file_uid = f"FILE-{uuid.uuid4().hex.upper()}"
    storage_key = f"{case_bucket}/{uuid.uuid4().hex}{detected.extension}"
    final_path = _storage_path(storage_key)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(final_path.parent, 0o700)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="casegraph-upload-", dir=root, delete=False) as tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_path = Path(tmp.name)
        os.chmod(temp_path, 0o600)
        scan = scanner.scan(temp_path)
        if not scan.clean:
            raise HTTPException(status_code=422, detail="uploaded file failed malware scanning")
        os.replace(temp_path, final_path)
        temp_path = None
        os.chmod(final_path, 0o600)

        row = EvidenceFile(
            file_uid=file_uid,
            case_id=case_id,
            original_name=Path(filename).name,
            storage_key=storage_key,
            detected_mime=detected.mime,
            extension=detected.extension,
            size_bytes=len(data),
            sha256=_sha256_bytes(data),
            scan_status="CLEAN" if scan.detail != "UNSCANNED_DEV_ONLY" else "UNSCANNED_DEV_ONLY",
            created_by=created_by,
            scanner_detail=scan.detail[:1000],
        )
        try:
            with session_scope() as session:
                upload_repo.add(session, row)
        except Exception:
            final_path.unlink(missing_ok=True)
            raise
        return _response(row)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def list_for_case(case_id: str) -> list[StoredFile]:
    if case_service.get(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    with session_scope() as session:
        return [_response(row) for row in upload_repo.list_for_case(session, case_id)]


def get_for_case(case_id: str, file_uid: str) -> tuple[StoredFile, bytes]:
    with session_scope() as session:
        row = upload_repo.get(session, file_uid)
        if row is None or row.case_id != case_id:
            raise HTTPException(status_code=404, detail="Evidence file not found")
        response = _response(row)
        data = _read_verified(row)
    return response, data


def resolve_action_files(case_id: str, file_refs: list[tuple[str, str]]) -> list[ActionFile]:
    if not file_refs:
        return []
    if len(file_refs) > 20:
        raise HTTPException(status_code=422, detail="too many evidence files in one action")
    result: list[ActionFile] = []
    total = 0
    with session_scope() as session:
        for uid, expected_sha256 in file_refs:
            row = upload_repo.get(session, uid)
            if row is None or row.case_id != case_id:
                raise HTTPException(status_code=422, detail=f"evidence file {uid} does not belong to this case")
            if row.sha256 != expected_sha256:
                raise HTTPException(status_code=409, detail=f"evidence file {uid} hash no longer matches the approved reference")
            if row.scan_status != "CLEAN" and security_config.production:
                raise HTTPException(status_code=422, detail=f"evidence file {uid} is not malware-scan clean")
            data = _read_verified(row)
            total += len(data)
            result.append(
                ActionFile(
                    file_uid=uid,
                    filename=f"evidence{row.extension}",
                    mime=row.detected_mime,
                    content=data,
                    sha256=row.sha256,
                )
            )
    if total > 50_000_000:
        raise HTTPException(status_code=422, detail="PayPal evidence files exceed 50 MB per action")
    return result
