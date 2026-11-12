from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

from backend.security.domain import Actor
from backend.uploads.service import get_for_case, list_for_case, store

router = APIRouter(prefix="/api/cases", tags=["evidence-files"])


def _actor(request: Request) -> Actor | None:
    # The security gateway only populates `state.actor` when authentication is
    # enforced. Reading it unguarded made every upload fail with AttributeError in
    # the local/demo profile — which is the profile the demo runs in.
    return getattr(request.state, "actor", None)


@router.post("/{case_id}/files")
async def upload_evidence_file(case_id: str, request: Request, file: UploadFile = File(...)) -> dict:
    actor = _actor(request)
    chunks: list[bytes] = []
    total = 0
    # The ASGI gateway already caps the multipart request. This second cap is
    # intentional defense in depth at the decoded file level.
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > 9_999_999:
            raise HTTPException(status_code=413, detail="file too large")
        chunks.append(chunk)
    result = store(
        case_id,
        file.filename or "upload.bin",
        b"".join(chunks),
        file.content_type,
        actor.subject if actor is not None else "local-operator",
    )
    return asdict(result)



@router.get("/{case_id}/files")
def list_evidence_files(case_id: str) -> list[dict]:
    return [asdict(item) for item in list_for_case(case_id)]


@router.get("/{case_id}/files/{file_uid}")
def download_evidence_file(case_id: str, file_uid: str) -> Response:
    meta, data = get_for_case(case_id, file_uid)
    safe_name = f"evidence_{meta.file_uid[-12:]}{meta.extension}"
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_name}"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
        "X-CaseGraph-SHA256": meta.sha256,
    }
    return Response(content=data, media_type=meta.detected_mime, headers=headers)
