from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

pytest.importorskip("backend.security.config")
from backend.security.config import SecurityConfig
from backend.security.jwt_auth import JWTVerifier


def _jwk(private_key, kid: str) -> dict:
    data = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    data.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return data


def _config(jwks_url: str) -> SecurityConfig:
    return SecurityConfig(
        environment="test", auth_mode="enforce", tenant_id="merchant-demo",
        issuer="https://issuer.example", audience="casegraph-api", jwks_url=jwks_url,
        jwt_public_key="", roles_claim="roles", tenant_claim="tenant_id",
        allowed_origins=(), max_json_request_bytes=1_000_000,
        max_upload_request_bytes=10_500_000, rate_backend="memory", redis_url="",
        enforce_role_separation=True, jwt_leeway_seconds=0, jwks_timeout_seconds=2,
        upload_dir=Path(".data/test"), upload_max_file_bytes=9_000_000,
        upload_scanner="none", upload_allow_unscanned_dev=True, otel_enabled=False,
        otel_endpoint="",
    )


def _token(key, kid: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {"iss": "https://issuer.example", "aud": "casegraph-api", "sub": "user-1",
         "tenant_id": "merchant-demo", "roles": ["VIEWER"], "iat": now, "exp": now + 300},
        key, algorithm="RS256", headers={"kid": kid},
    )


def test_jwks_client_refreshes_when_new_kid_appears():
    key1 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key2 = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    state = {"keys": [_jwk(key1, "kid-1")]}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            payload = json.dumps(state).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        verifier = JWTVerifier(_config(f"http://127.0.0.1:{server.server_port}/jwks"))
        assert verifier.verify(_token(key1, "kid-1")).subject == "user-1"
        state["keys"] = [_jwk(key2, "kid-2")]
        # PyJWKClient refreshes the set when the requested kid is absent.
        assert verifier.verify(_token(key2, "kid-2")).subject == "user-1"
    finally:
        server.shutdown()
        server.server_close()
