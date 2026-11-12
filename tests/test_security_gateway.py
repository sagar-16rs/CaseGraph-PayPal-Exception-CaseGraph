from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.security.config import SecurityConfig
from backend.security.middleware import SecurityGatewayMiddleware


def keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    pub = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return priv, pub


def config(pub: str, *, production: bool = False, max_json: int = 1_000_000) -> SecurityConfig:
    return SecurityConfig(
        environment="production" if production else "test",
        auth_mode="enforce",
        tenant_id="tenant-a",
        issuer="https://issuer.example",
        audience="casegraph-api",
        jwks_url="",
        jwt_public_key=pub,
        roles_claim="roles",
        tenant_claim="tenant_id",
        allowed_origins=("https://app.example",),
        max_json_request_bytes=max_json,
        max_upload_request_bytes=10_500_000,
        rate_backend="memory",
        redis_url="",
        enforce_role_separation=True,
        jwt_leeway_seconds=0,
        jwks_timeout_seconds=2,
        upload_dir=Path(".data/evidence_files"),
        upload_max_file_bytes=9_000_000,
        upload_scanner="none",
        upload_allow_unscanned_dev=False,
        otel_enabled=False,
    )


def token(priv: bytes, roles: list[str], *, tenant: str = "tenant-a") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "iss": "https://issuer.example",
            "aud": "casegraph-api",
            "sub": "alice",
            "tenant_id": tenant,
            "roles": roles,
            "iat": now,
            "exp": now + timedelta(minutes=10),
        },
        priv,
        algorithm="RS256",
    )


def client(cfg: SecurityConfig) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://app.example"],
        allow_methods=["*"],
        allow_headers=["authorization", "content-type"],
    )

    @app.get("/api/cases/{case_id}")
    def read_case(case_id: str, request: Request):
        return {"case_id": case_id, "sub": request.state.actor.subject}

    @app.post("/api/cases/{case_id}/actions/approve")
    async def approve(case_id: str, request: Request):
        return {"case_id": case_id, "body": await request.json()}

    app.add_middleware(SecurityGatewayMiddleware, config=cfg)
    return TestClient(app)


def test_missing_token_is_401_and_early_error_has_hardening_headers():
    _, pub = keys()
    response = client(config(pub, production=True)).get("/api/cases/CASE-1")
    assert response.status_code == 401
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "max-age=" in response.headers["strict-transport-security"]


def test_valid_viewer_can_read_but_wrong_tenant_cannot():
    priv, pub = keys()
    c = client(config(pub))
    ok = c.get("/api/cases/CASE-1", headers={"Authorization": f"Bearer {token(priv, ['VIEWER'])}"})
    assert ok.status_code == 200 and ok.json()["sub"] == "alice"
    bad = c.get(
        "/api/cases/CASE-1",
        headers={"Authorization": f"Bearer {token(priv, ['VIEWER'], tenant='tenant-b')}"},
    )
    assert bad.status_code == 401


def test_audit_identity_spoof_is_rejected_before_route():
    priv, pub = keys()
    c = client(config(pub))
    response = c.post(
        "/api/cases/CASE-1/actions/approve",
        headers={"Authorization": f"Bearer {token(priv, ['APPROVER'])}"},
        json={"approved_by": "mallory"},
    )
    assert response.status_code == 422


def test_unknown_api_and_legacy_write_fail_closed():
    _, pub = keys()
    c = client(config(pub))
    assert c.get("/api/not-in-inventory").status_code == 404
    assert c.post("/api/cases/C/actions/send-message").status_code == 410


def test_allowed_cors_preflight_reaches_cors_layer_without_bearer_token():
    _, pub = keys()
    c = client(config(pub))
    response = c.options(
        "/api/cases/CASE-1",
        headers={
            "Origin": "https://app.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://app.example"


def test_disallowed_origin_and_oversize_body_fail_before_application():
    priv, pub = keys()
    c = client(config(pub, max_json=20))
    origin = c.get(
        "/api/cases/C",
        headers={"Origin": "https://evil.example", "Authorization": f"Bearer {token(priv, ['VIEWER'])}"},
    )
    assert origin.status_code == 403
    too_big = c.post(
        "/api/cases/C/actions/approve",
        headers={"Authorization": f"Bearer {token(priv, ['APPROVER'])}"},
        content=b"x" * 21,
    )
    assert too_big.status_code == 413
