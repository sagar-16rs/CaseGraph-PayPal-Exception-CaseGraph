from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from typing import Any, Awaitable, Callable

from backend.security.config import SecurityConfig
from backend.security.context import bind_actor, reset_actor
from backend.security.domain import Actor, AuthenticationError
from backend.security.jwt_auth import JWTVerifier
from backend.security.observability import attach_span_attributes, log_security_event
from backend.security.policy import match_rule
from backend.security.rate_limit import MemoryRateLimiter, RateLimiter, RedisRateLimiter

ASGIApp = Callable[[dict, Callable[[], Awaitable[dict]], Callable[[dict], Awaitable[None]]], Awaitable[None]]
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")
_AUDIT_FIELDS = {"approved_by", "requested_by", "created_by"}


def _headers(scope: dict) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}


async def _json_response(send, status: int, body: dict, request_id: str, *, production: bool = False) -> None:
    data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(data)).encode("ascii")),
        (b"x-request-id", request_id.encode("ascii")),
        (b"cache-control", b"no-store"),
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    ]
    if production:
        headers.extend([
            (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
            (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
        ])
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": data})


def _extract_bearer(value: str) -> str:
    parts = value.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise AuthenticationError("missing bearer token")
    return parts[1].strip()


def _audit_values(value: Any) -> list[tuple[str, str]]:
    if not isinstance(value, dict):
        return []
    return [(key, child) for key, child in value.items() if key in _AUDIT_FIELDS and isinstance(child, str)]



class SecurityGatewayMiddleware:
    def __init__(self, app: ASGIApp, config: SecurityConfig):
        self.app = app
        self.config = config
        self.verifier = JWTVerifier(config) if config.auth_enforced else None
        self.rate_limiter: RateLimiter = (
            RedisRateLimiter(config.redis_url) if config.rate_backend == "redis" else MemoryRateLimiter()
        )

    async def __call__(self, scope: dict, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        headers = _headers(scope)
        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", "/"))
        incoming_id = headers.get("x-request-id", "")
        request_id = incoming_id if _REQUEST_ID_RE.fullmatch(incoming_id) else uuid.uuid4().hex

        if self.config.production and path in {"/docs", "/redoc", "/openapi.json"}:
            await _json_response(send, 404, {"detail": "not found"}, request_id, production=self.config.production)
            return

        origin = headers.get("origin")
        if origin and self.config.allowed_origins and origin not in self.config.allowed_origins:
            await _json_response(send, 403, {"detail": "browser origin not allowed"}, request_id, production=self.config.production)
            return

        rule = match_rule(method, path)
        if rule is None:
            if path.startswith("/api/"):
                await _json_response(send, 404, {"detail": "route is not present in the hardened API inventory"}, request_id, production=self.config.production)
                return
        elif rule.deny:
            await _json_response(send, 410, {"detail": "legacy write route is disabled; use approve -> execute"}, request_id, production=self.config.production)
            return

        max_body = self.config.max_json_request_bytes
        if path.endswith("/files") and method == "POST":
            max_body = self.config.max_upload_request_bytes
        body_parts: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > max_body:
                await _json_response(send, 413, {"detail": "request body too large"}, request_id, production=self.config.production)
                return
            body_parts.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(body_parts)

        actor: Actor | None = None
        if self.config.auth_enforced and rule is not None and not rule.public:
            try:
                actor = self.verifier.verify(_extract_bearer(headers.get("authorization", "")))  # type: ignore[union-attr]
            except AuthenticationError:
                await _json_response(send, 401, {"detail": "authentication required"}, request_id, production=self.config.production)
                return
            if rule.role is not None and not actor.has_role(rule.role):
                await _json_response(send, 403, {"detail": "insufficient role"}, request_id, production=self.config.production)
                return

            content_type = headers.get("content-type", "")
            if body and content_type.startswith("application/json"):
                try:
                    parsed = json.loads(body)
                except json.JSONDecodeError:
                    parsed = None
                if parsed is not None:
                    found = _audit_values(parsed)
                    if any(value.strip() != actor.subject for _name, value in found):
                        await _json_response(
                            send,
                            422,
                            {"detail": "audit identity fields must match the authenticated subject"},
                            request_id,
                            production=self.config.production,
                        )
                        return

        if rule is not None:
            identity = actor.subject if actor else (scope.get("client") or ("unknown", 0))[0]
            # Use the route class, not the raw resource path. Otherwise an attacker
            # can evade a limit by rotating case/action/file IDs.
            rate_key = f"{method}:{rule.pattern.pattern}:{identity}"
            try:
                allowed = await self.rate_limiter.allow(rate_key, rule.requests_per_minute)
            except Exception:
                if self.config.production:
                    await _json_response(send, 503, {"detail": "security rate limiter unavailable"}, request_id, production=self.config.production)
                    return
                allowed = True
            if not allowed:
                await _json_response(send, 429, {"detail": "rate limit exceeded"}, request_id, production=self.config.production)
                return

        state = scope.setdefault("state", {})
        state["actor"] = actor
        state["request_id"] = request_id
        actor_hash = hashlib.sha256(actor.subject.encode()).hexdigest()[:16] if actor else None
        attach_span_attributes(request_id=request_id, actor=actor_hash, tenant=actor.tenant_id if actor else None)

        replayed = False

        async def replay_receive() -> dict:
            nonlocal replayed
            if replayed:
                return {"type": "http.request", "body": b"", "more_body": False}
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        status_holder = {"status": 500}

        async def wrapped_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = int(message["status"])
                response_headers = list(message.get("headers", []))
                lower_names = {k.lower() for k, _ in response_headers}
                def add(name: bytes, value: bytes) -> None:
                    if name not in lower_names:
                        response_headers.append((name, value))
                add(b"x-request-id", request_id.encode("ascii"))
                add(b"x-content-type-options", b"nosniff")
                add(b"x-frame-options", b"DENY")
                add(b"referrer-policy", b"no-referrer")
                add(b"permissions-policy", b"camera=(), microphone=(), geolocation=()")
                add(b"cache-control", b"no-store")
                if self.config.production:
                    add(b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    add(b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")
                message["headers"] = response_headers
            await send(message)

        token = bind_actor(actor)
        try:
            await self.app(scope, replay_receive, wrapped_send)
        finally:
            reset_actor(token)
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            log_security_event(
                "http_request",
                request_id=request_id,
                method=method,
                path=path,
                status=status_holder["status"],
                latency_ms=elapsed_ms,
                actor_hash=actor_hash,
                tenant=actor.tenant_id if actor else None,
            )
