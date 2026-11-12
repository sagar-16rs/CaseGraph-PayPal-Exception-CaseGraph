from __future__ import annotations

from fastapi import APIRouter, Request

from backend.security.domain import Actor

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
def current_actor(request: Request) -> dict:
    actor: Actor = request.state.actor
    return {
        "subject": actor.subject,
        "tenant_id": actor.tenant_id,
        "roles": sorted(role.value for role in actor.roles),
    }
