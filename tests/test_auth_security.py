from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.security.config import SecurityConfig
from backend.security.domain import Role
from backend.security.jwt_auth import JWTVerifier
from backend.security.policy import match_rule


def make_config(public_key: str, *, production: bool = False, separate: bool = True) -> SecurityConfig:
    return SecurityConfig(
        environment="production" if production else "test",
        auth_mode="enforce",
        tenant_id="tenant-a",
        issuer="https://issuer.example",
        audience="casegraph-api",
        jwks_url="",
        jwt_public_key=public_key,
        roles_claim="roles",
        tenant_claim="tenant_id",
        allowed_origins=("https://app.example",) if production else (),
        max_json_request_bytes=1_000_000,
        max_upload_request_bytes=10_500_000,
        rate_backend="redis" if production else "memory",
        redis_url="redis://redis:6379/0" if production else "",
        enforce_role_separation=separate,
        jwt_leeway_seconds=0,
        jwks_timeout_seconds=2,
        upload_dir=Path(".data/evidence_files"),
        upload_max_file_bytes=9_000_000,
        upload_scanner="clamav" if production else "none",
        upload_allow_unscanned_dev=False,
        otel_enabled=False,
    )


@pytest.fixture(scope="module")
def keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv, pub.decode()


def token(priv: bytes, *, roles, tenant="tenant-a", exp_offset=300):
    now = int(time.time())
    return jwt.encode(
        {
            "sub": "user-123",
            "tenant_id": tenant,
            "roles": roles,
            "iss": "https://issuer.example",
            "aud": "casegraph-api",
            "iat": now,
            "exp": now + exp_offset,
        },
        priv,
        algorithm="RS256",
    )


def test_rs256_token_tenant_and_roles(keys):
    priv, pub = keys
    actor = JWTVerifier(make_config(pub)).verify(token(priv, roles=["ANALYST"]))
    assert actor.subject == "user-123"
    assert actor.tenant_id == "tenant-a"
    assert actor.has_role(Role.ANALYST)
    assert actor.has_role(Role.VIEWER)
    assert not actor.has_role(Role.APPROVER)


def test_wrong_tenant_rejected(keys):
    priv, pub = keys
    with pytest.raises(Exception):
        JWTVerifier(make_config(pub)).verify(token(priv, roles=["VIEWER"], tenant="tenant-b"))


def test_expired_token_rejected(keys):
    priv, pub = keys
    with pytest.raises(Exception):
        JWTVerifier(make_config(pub)).verify(token(priv, roles=["VIEWER"], exp_offset=-1))


def test_analyst_approver_separation_rejected(keys):
    priv, pub = keys
    with pytest.raises(Exception):
        JWTVerifier(make_config(pub, separate=True)).verify(token(priv, roles=["ANALYST", "APPROVER"]))


def test_admin_does_not_implicitly_gain_approver(keys):
    priv, pub = keys
    actor = JWTVerifier(make_config(pub)).verify(token(priv, roles=["ADMIN"]))
    assert actor.has_role(Role.VIEWER)
    assert not actor.has_role(Role.APPROVER)


def test_production_config_rejects_insecure_defaults(keys):
    _, pub = keys
    cfg = make_config(pub, production=True)
    assert cfg.validate() == []
    bad = replace(cfg, auth_mode="disabled", rate_backend="memory", allowed_origins=("*",), upload_scanner="none")
    errors = bad.validate()
    assert any("auth" in item.lower() for item in errors)
    assert any("redis" in item.lower() for item in errors)
    assert any("wildcard" in item.lower() for item in errors)
    assert any("clamav" in item.lower() for item in errors)




def test_production_config_requires_https_issuer(keys):
    _, pub = keys
    cfg = replace(make_config(pub, production=True), issuer="http://issuer.example")
    errors = cfg.validate()
    assert any("issuer" in item.lower() and "https" in item.lower() for item in errors)

def test_route_policy_fail_closed_and_legacy_disabled():
    legacy = match_rule("POST", "/api/cases/CASE-1/actions/send-message")
    assert legacy is not None and legacy.deny
    execute = match_rule("POST", "/api/cases/CASE-1/actions/ACT-1/execute")
    assert execute is not None and execute.role == Role.APPROVER
    upload = match_rule("POST", "/api/cases/CASE-1/files")
    assert upload is not None and upload.role == Role.ANALYST
    assert match_rule("DELETE", "/api/cases/CASE-1/files/FILE-1") is None
