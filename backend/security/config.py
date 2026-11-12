from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _csv(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class SecurityConfig:
    environment: str
    auth_mode: str
    tenant_id: str
    issuer: str
    audience: str
    jwks_url: str
    jwt_public_key: str
    roles_claim: str
    tenant_claim: str
    allowed_origins: tuple[str, ...]
    max_json_request_bytes: int
    max_upload_request_bytes: int
    rate_backend: str
    redis_url: str
    enforce_role_separation: bool
    jwt_leeway_seconds: int
    jwks_timeout_seconds: int
    upload_dir: Path
    upload_max_file_bytes: int
    upload_scanner: str
    upload_allow_unscanned_dev: bool
    otel_enabled: bool
    otel_endpoint: str = ""

    @classmethod
    def from_env(cls) -> "SecurityConfig":
        environment = os.getenv("CASEGRAPH_ENV", "development").strip().lower()
        return cls(
            environment=environment,
            auth_mode=os.getenv("CASEGRAPH_AUTH_MODE", "disabled").strip().lower(),
            tenant_id=os.getenv("CASEGRAPH_TENANT_ID", "").strip(),
            issuer=os.getenv("CASEGRAPH_AUTH_ISSUER", "").strip().rstrip("/"),
            audience=os.getenv("CASEGRAPH_AUTH_AUDIENCE", "").strip(),
            jwks_url=os.getenv("CASEGRAPH_AUTH_JWKS_URL", "").strip(),
            jwt_public_key=os.getenv("CASEGRAPH_AUTH_PUBLIC_KEY_PEM", "").replace("\\n", "\n").strip(),
            roles_claim=os.getenv("CASEGRAPH_AUTH_ROLES_CLAIM", "roles").strip(),
            tenant_claim=os.getenv("CASEGRAPH_AUTH_TENANT_CLAIM", "tenant_id").strip(),
            allowed_origins=_csv("CASEGRAPH_ALLOWED_ORIGINS"),
            max_json_request_bytes=_int("CASEGRAPH_MAX_JSON_REQUEST_BYTES", 1_000_000),
            max_upload_request_bytes=_int("CASEGRAPH_MAX_UPLOAD_REQUEST_BYTES", 10_500_000),
            rate_backend=os.getenv("CASEGRAPH_RATE_LIMIT_BACKEND", "memory").strip().lower(),
            redis_url=os.getenv("CASEGRAPH_REDIS_URL", "").strip(),
            enforce_role_separation=_bool("CASEGRAPH_ENFORCE_ROLE_SEPARATION", True),
            jwt_leeway_seconds=_int("CASEGRAPH_JWT_LEEWAY_SECONDS", 30),
            jwks_timeout_seconds=_int("CASEGRAPH_JWKS_TIMEOUT_SECONDS", 5),
            upload_dir=Path(os.getenv("CASEGRAPH_UPLOAD_DIR", ".data/evidence_files")).expanduser(),
            upload_max_file_bytes=_int("CASEGRAPH_UPLOAD_MAX_FILE_BYTES", 9_000_000),
            upload_scanner=os.getenv("CASEGRAPH_UPLOAD_SCANNER", "none").strip().lower(),
            upload_allow_unscanned_dev=_bool("CASEGRAPH_UPLOAD_ALLOW_UNSCANNED_DEV", False),
            otel_enabled=_bool("CASEGRAPH_OTEL_ENABLED", False),
            otel_endpoint=os.getenv("CASEGRAPH_OTEL_ENDPOINT", "").strip(),
        )

    @property
    def production(self) -> bool:
        return self.environment == "production"

    @property
    def auth_enforced(self) -> bool:
        return self.auth_mode == "enforce"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.environment not in {"development", "test", "production"}:
            errors.append("CASEGRAPH_ENV must be development, test, or production")
        if self.auth_mode not in {"disabled", "enforce"}:
            errors.append("CASEGRAPH_AUTH_MODE must be disabled or enforce")
        if self.rate_backend not in {"memory", "redis"}:
            errors.append("CASEGRAPH_RATE_LIMIT_BACKEND must be memory or redis")
        if self.upload_scanner not in {"none", "clamav"}:
            errors.append("CASEGRAPH_UPLOAD_SCANNER must be none or clamav")
        if self.upload_max_file_bytes <= 0 or self.upload_max_file_bytes >= 10_000_000:
            errors.append("CASEGRAPH_UPLOAD_MAX_FILE_BYTES must be > 0 and < 10,000,000 for PayPal compatibility")
        if self.max_upload_request_bytes <= self.upload_max_file_bytes:
            errors.append("CASEGRAPH_MAX_UPLOAD_REQUEST_BYTES must exceed CASEGRAPH_UPLOAD_MAX_FILE_BYTES")
        if self.max_json_request_bytes <= 0:
            errors.append("CASEGRAPH_MAX_JSON_REQUEST_BYTES must be positive")

        if self.auth_enforced:
            if not self.tenant_id:
                errors.append("CASEGRAPH_TENANT_ID is required when auth is enforced")
            if not self.issuer:
                errors.append("CASEGRAPH_AUTH_ISSUER is required when auth is enforced")
            else:
                issuer = urlparse(self.issuer)
                if not issuer.hostname:
                    errors.append("CASEGRAPH_AUTH_ISSUER must be an absolute URL")
                if self.production and issuer.scheme != "https":
                    errors.append("production CASEGRAPH_AUTH_ISSUER must use HTTPS")
            if not self.audience:
                errors.append("CASEGRAPH_AUTH_AUDIENCE is required when auth is enforced")
            if bool(self.jwks_url) == bool(self.jwt_public_key):
                errors.append("configure exactly one of CASEGRAPH_AUTH_JWKS_URL or CASEGRAPH_AUTH_PUBLIC_KEY_PEM")
            if self.jwks_url:
                issuer = urlparse(self.issuer)
                jwks = urlparse(self.jwks_url)
                if jwks.scheme != "https":
                    errors.append("CASEGRAPH_AUTH_JWKS_URL must use HTTPS")
                if not jwks.hostname:
                    errors.append("CASEGRAPH_AUTH_JWKS_URL must have a hostname")
                if issuer.hostname and jwks.hostname and issuer.hostname.lower() != jwks.hostname.lower():
                    errors.append("JWKS host must match issuer host to avoid an SSRF/key-confusion boundary")

        if self.production:
            if not self.auth_enforced:
                errors.append("production requires CASEGRAPH_AUTH_MODE=enforce")
            if os.getenv("CASEGRAPH_PAYPAL_TRANSPORT", "live").strip().lower() == "simulated":
                errors.append(
                    "production forbids CASEGRAPH_PAYPAL_TRANSPORT=simulated; the simulated sandbox is never authoritative"
                )
            if self.rate_backend != "redis":
                errors.append("production requires CASEGRAPH_RATE_LIMIT_BACKEND=redis")
            if not self.redis_url:
                errors.append("production Redis rate limiting requires CASEGRAPH_REDIS_URL")
            if not self.allowed_origins:
                errors.append("production requires explicit CASEGRAPH_ALLOWED_ORIGINS")
            if any(origin == "*" for origin in self.allowed_origins):
                errors.append("wildcard browser origins are forbidden in production")
            for origin in self.allowed_origins:
                parsed = urlparse(origin)
                if parsed.scheme != "https" or not parsed.hostname:
                    errors.append(f"production browser origin must be an absolute HTTPS origin: {origin}")
            if self.upload_scanner != "clamav":
                errors.append("production requires CASEGRAPH_UPLOAD_SCANNER=clamav")
            if self.upload_allow_unscanned_dev:
                errors.append("CASEGRAPH_UPLOAD_ALLOW_UNSCANNED_DEV must be false in production")
            if self.otel_enabled and not self.otel_endpoint:
                errors.append("production OTel requires CASEGRAPH_OTEL_ENDPOINT")

        return errors


security_config = SecurityConfig.from_env()
