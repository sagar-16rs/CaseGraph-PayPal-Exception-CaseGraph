from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    VIEWER = "VIEWER"
    ANALYST = "ANALYST"
    APPROVER = "APPROVER"
    ADMIN = "ADMIN"


@dataclass(frozen=True, slots=True)
class Actor:
    subject: str
    tenant_id: str
    roles: frozenset[Role]
    issuer: str

    def has_role(self, required: Role) -> bool:
        # Every authenticated operational role may read. Higher-risk capabilities
        # are NOT implied by ADMIN: ANALYST and APPROVER must be explicit.
        if required == Role.VIEWER:
            return bool(self.roles)
        return required in self.roles


class AuthenticationError(RuntimeError):
    pass


class AuthorizationError(RuntimeError):
    pass
