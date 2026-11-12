from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.security.config import SecurityConfig
from backend.security.jwt_auth import JWTVerifier
from backend.uploads.validation import validate_upload


def main() -> int:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    cfg = SecurityConfig(
        environment="test",
        auth_mode="enforce",
        tenant_id="selftest",
        issuer="https://selftest.example",
        audience="casegraph-api",
        jwks_url="",
        jwt_public_key=public_pem,
        roles_claim="roles",
        tenant_claim="tenant_id",
        allowed_origins=(),
        max_json_request_bytes=1_000_000,
        max_upload_request_bytes=10_500_000,
        rate_backend="memory",
        redis_url="",
        enforce_role_separation=True,
        jwt_leeway_seconds=0,
        jwks_timeout_seconds=2,
        upload_dir=Path(".data/selftest"),
        upload_max_file_bytes=9_000_000,
        upload_scanner="none",
        upload_allow_unscanned_dev=True,
        otel_enabled=False,
    )
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "selftest-user",
            "tenant_id": "selftest",
            "roles": ["ANALYST"],
            "iss": cfg.issuer,
            "aud": cfg.audience,
            "iat": now,
            "exp": now + 60,
        },
        private_pem,
        algorithm="RS256",
    )
    actor = JWTVerifier(cfg).verify(token)
    detected = validate_upload("proof.pdf", b"%PDF-1.7\nselftest", "application/pdf", cfg.upload_max_file_bytes)
    result = {
        "status": "PASS",
        "jwt_subject": actor.subject,
        "jwt_roles": sorted(role.value for role in actor.roles),
        "upload_mime": detected.mime,
        "checks": ["asymmetric_jwt", "tenant_claim", "roles", "file_signature"],
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
