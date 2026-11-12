from __future__ import annotations

import threading
import time
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError

from backend.security.config import SecurityConfig
from backend.security.domain import Actor, AuthenticationError, Role

_ALLOWED_ALGORITHMS = ("RS256", "ES256")
_MAX_TOKEN_LENGTH = 16_384

# PyJWT refuses to refetch the JWK set for an unknown `kid` while it is inside
# its own cooldown window (30s by default). An identity provider that rotates to
# a new signing key would therefore produce up to 30 seconds of valid tokens
# being rejected. CaseGraph forces exactly one extra refresh per window, and
# rate-limits that refresh so a client rotating random `kid` values cannot turn
# the JWKS endpoint into a request amplifier.
_MIN_FORCED_REFRESH_SECONDS = 5.0


def _normalize_roles(value: Any) -> frozenset[Role]:
    if isinstance(value, str):
        raw = value.replace(",", " ").split()
    elif isinstance(value, list):
        raw = [str(item) for item in value]
    else:
        raw = []
    roles: set[Role] = set()
    for item in raw:
        normalized = item.strip().upper()
        try:
            roles.add(Role(normalized))
        except ValueError:
            continue
    return frozenset(roles)


class JWTVerifier:
    def __init__(self, config: SecurityConfig):
        self.config = config
        self._jwks: PyJWKClient | None = None
        self._refresh_lock = threading.Lock()
        self._last_forced_refresh = 0.0
        if config.jwks_url:
            self._jwks = PyJWKClient(
                config.jwks_url,
                cache_jwk_set=True,
                lifespan=300,
                timeout=config.jwks_timeout_seconds,
            )

    def _refresh_for_unknown_kid(self, token: str) -> Any:
        """Force at most one JWKS refresh per window when a `kid` is unknown.

        Returns the matching key, or raises AuthenticationError when the key is
        still absent or the refresh budget for this window is exhausted.
        """
        kid = str(jwt.get_unverified_header(token).get("kid") or "")
        with self._refresh_lock:
            now = time.monotonic()
            if kid and now - self._last_forced_refresh < _MIN_FORCED_REFRESH_SECONDS:
                raise AuthenticationError("invalid or expired bearer token")
            self._last_forced_refresh = now
            try:
                signing_keys = self._jwks.get_signing_keys(refresh=True)  # type: ignore[union-attr]
                match = self._jwks.match_kid(signing_keys, kid)  # type: ignore[union-attr]
            except Exception as exc:
                raise AuthenticationError("invalid or expired bearer token") from exc
            if match is None:
                raise AuthenticationError("invalid or expired bearer token")
            return match.key

    def _signing_key(self, token: str) -> Any:
        if self._jwks is None:
            return self.config.jwt_public_key
        try:
            return self._jwks.get_signing_key_from_jwt(token).key
        except PyJWKClientError:
            return self._refresh_for_unknown_kid(token)

    def verify(self, token: str) -> Actor:
        if not token or len(token) > _MAX_TOKEN_LENGTH:
            raise AuthenticationError("invalid bearer token")
        try:
            header = jwt.get_unverified_header(token)
        except PyJWTError as exc:
            raise AuthenticationError("invalid bearer token") from exc
        alg = str(header.get("alg", ""))
        if alg not in _ALLOWED_ALGORITHMS:
            raise AuthenticationError("unsupported token signing algorithm")

        try:
            key = self._signing_key(token)
            claims = jwt.decode(
                token,
                key=key,
                algorithms=list(_ALLOWED_ALGORITHMS),
                audience=self.config.audience,
                issuer=self.config.issuer,
                leeway=self.config.jwt_leeway_seconds,
                options={"require": ["exp", "iat", "sub"]},
            )
        except Exception as exc:
            # Never reflect provider/JWK/token internals to clients.
            raise AuthenticationError("invalid or expired bearer token") from exc

        subject = str(claims.get("sub", "")).strip()
        tenant = str(claims.get(self.config.tenant_claim, "")).strip()
        if not subject or len(subject) > 256:
            raise AuthenticationError("token subject is missing or invalid")
        if tenant != self.config.tenant_id:
            raise AuthenticationError("token tenant is not authorized for this deployment")

        roles = _normalize_roles(claims.get(self.config.roles_claim))
        if not roles:
            raise AuthenticationError("token has no recognized CaseGraph roles")
        if self.config.enforce_role_separation and Role.ANALYST in roles and Role.APPROVER in roles:
            raise AuthenticationError("ANALYST and APPROVER must be held by separate principals")

        return Actor(subject=subject, tenant_id=tenant, roles=roles, issuer=self.config.issuer)
