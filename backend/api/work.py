from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.work.service import work_service

router = APIRouter(prefix="/api/ops/work", tags=["ops"])


@router.get("/queue")
def queue():
    return work_service.status()


@router.get("/recent")
def recent(limit: int = 100):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
    return work_service.list_recent(limit=limit)
