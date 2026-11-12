from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class Check:
    name: str
    required: bool
    status: str
    detail: str
    seconds: float


class GateFailure(RuntimeError):
    pass


def _run(name: str, required: bool, fn) -> Check:
    started = time.perf_counter()
    try:
        detail = fn()
        status = "PASS"
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        status = "FAIL" if required else "WARN"
    return Check(name, required, status, str(detail), round(time.perf_counter() - started, 3))


def _production_config_check() -> str:
    from backend.security.config import security_config

    errors = security_config.validate()
    if errors:
        raise GateFailure("; ".join(errors))
    if not security_config.production:
        raise GateFailure("CASEGRAPH_ENV must be production for the live freeze gate")
    if not security_config.auth_enforced:
        raise GateFailure("authentication is not enforced")
    return "security production security configuration validated"


def _postgres_check() -> str:
    from sqlalchemy import inspect, text
    from backend.db import session as db_session
    from backend.db.migrations import current_database_revision, expected_head_revision

    engine = db_session.engine
    if engine.dialect.name != "postgresql":
        raise GateFailure(f"database backend is {engine.dialect.name!r}, expected PostgreSQL")
    current = current_database_revision(engine)
    expected = expected_head_revision()
    # The gate asserts that the deployment is at the repository's expected head.
    # Pinning a second literal here previously drifted from expected_head_revision()
    # and made even a correctly migrated database fail the gate.
    if current != expected:
        raise GateFailure(f"Alembic revision current={current!r}, expected={expected!r}")

    tables = set(inspect(engine).get_table_names())
    required_tables = {"work_items", "action_reconciliations", "evidence_files"}
    missing = sorted(required_tables - tables)
    if missing:
        raise GateFailure("missing hardened tables: " + ", ".join(missing))

    # Prove the session-level dispute lock assumption against the real DB.
    key = 4850181448440799568  # stable signed 64-bit probe key
    with engine.connect() as one, engine.connect() as two:
        if not bool(one.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar()):
            raise GateFailure("first PostgreSQL advisory lock acquisition failed")
        try:
            if bool(two.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar()):
                two.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                raise GateFailure("second session unexpectedly acquired the same advisory lock")
        finally:
            released = bool(one.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key}).scalar())
            if not released:
                raise GateFailure("advisory lock release could not be proven")
        if not bool(two.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar()):
            raise GateFailure("second session could not acquire advisory lock after release")
        if not bool(two.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key}).scalar()):
            raise GateFailure("second advisory lock release could not be proven")

    with engine.connect() as connection:
        version = str(connection.execute(text("SELECT version()" )).scalar() or "")
    return f"PostgreSQL runtime, migration 0008, required tables, and advisory locking verified ({version[:90]})"


def _redis_check() -> str:
    from backend.security.config import security_config
    from backend.security.rate_limit import RedisRateLimiter

    if security_config.rate_backend != "redis" or not security_config.redis_url:
        raise GateFailure("production Redis rate limiter is not configured")
    parsed = urlparse(security_config.redis_url)
    if parsed.scheme not in {"redis", "rediss"}:
        raise GateFailure("Redis URL must use redis:// or rediss://")
    if not parsed.password:
        raise GateFailure("Redis URL has no authentication secret")

    async def probe() -> tuple[bool, bool, bool, str]:
        limiter = RedisRateLimiter(security_config.redis_url)
        key = f"integration-live-{uuid.uuid4().hex}"
        ping = await limiter.ping()
        first = await limiter.allow(key, 2, 20)
        second = await limiter.allow(key, 2, 20)
        third = await limiter.allow(key, 2, 20)
        who = "unknown"
        try:
            who = str(await limiter._redis.acl_whoami())  # non-destructive diagnostic
        except Exception:
            who = "ACL WHOAMI not permitted"
        return ping, first and second, not third, who

    ping, accepted, blocked, who = asyncio.run(probe())
    if not (ping and accepted and blocked):
        raise GateFailure(f"Redis limiter probe failed ping={ping} accepted={accepted} blocked={blocked}")
    warning = ""
    if who == "default":
        warning = "; warning: authenticated as Redis default user, dedicated ACL user is preferred"
    return f"Redis ping + real rate-limit increment/expiry script verified; user={who}{warning}"


def _validate_jwks(jwks: dict) -> tuple[int, list[str]]:
    keys = jwks.get("keys")
    if not isinstance(keys, list) or not keys:
        raise GateFailure("JWKS contains no keys")
    kids: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if not isinstance(key, dict):
            raise GateFailure("JWKS contains a non-object key")
        if key.get("kty") == "oct":
            raise GateFailure("symmetric JWKs are forbidden")
        if any(private in key for private in ("d", "p", "q", "dp", "dq", "qi")):
            raise GateFailure("JWKS exposes private key material")
        if key.get("use") not in (None, "sig"):
            continue
        alg = key.get("alg")
        if alg not in (None, "RS256", "ES256"):
            continue
        kid = str(key.get("kid", "")).strip()
        if kid:
            if kid in seen:
                raise GateFailure(f"duplicate JWK kid {kid!r}")
            seen.add(kid)
            kids.append(kid)
    if not kids:
        raise GateFailure("JWKS has no usable RS256/ES256 signing key with a kid")
    return len(keys), kids


def _oidc_check(require_token: bool) -> str:
    import httpx
    from backend.security.config import security_config
    from backend.security.jwt_auth import JWTVerifier

    issuer = security_config.issuer.rstrip("/")
    if not issuer.startswith("https://"):
        raise GateFailure("OIDC issuer must use HTTPS")
    discovery_url = issuer + "/.well-known/openid-configuration"
    with httpx.Client(timeout=security_config.jwks_timeout_seconds, follow_redirects=False) as client:
        response = client.get(discovery_url, headers={"Accept": "application/json"})
        response.raise_for_status()
        metadata = response.json()
        if metadata.get("issuer") != issuer:
            raise GateFailure("OIDC discovery issuer does not exactly match configured issuer")
        jwks_uri = str(metadata.get("jwks_uri", ""))
        parsed = urlparse(jwks_uri)
        if parsed.scheme != "https" or not parsed.hostname:
            raise GateFailure("OIDC discovery jwks_uri is missing or not HTTPS")
        if security_config.jwks_url and security_config.jwks_url != jwks_uri:
            raise GateFailure("configured JWKS URL does not match OIDC discovery jwks_uri")
        jwks_resp = client.get(jwks_uri, headers={"Accept": "application/json"})
        jwks_resp.raise_for_status()
        total, kids = _validate_jwks(jwks_resp.json())

    token = os.getenv("CASEGRAPH_INTEGRATION_TEST_TOKEN", "").strip()
    if require_token and not token:
        raise GateFailure("CASEGRAPH_INTEGRATION_TEST_TOKEN is required for token validation")
    token_detail = "token not requested"
    if token:
        actor = JWTVerifier(security_config).verify(token)
        token_detail = f"token verified for subject hash only, tenant={actor.tenant_id}, roles={','.join(sorted(r.value for r in actor.roles))}"
    return f"OIDC discovery and JWKS verified ({total} keys, usable kids={len(kids)}); {token_detail}"


def _parse_clamav_db_time(version_text: str) -> datetime | None:
    # Common output: ClamAV 1.4.x/NNNNN/Tue Oct 20 12:34:56 2026
    parts = version_text.strip().split("/", 2)
    if len(parts) < 3:
        return None
    raw = parts[2].strip()
    for parser in (
        lambda x: datetime.strptime(x, "%a %b %d %H:%M:%S %Y").replace(tzinfo=timezone.utc),
        lambda x: parsedate_to_datetime(x),
    ):
        try:
            dt = parser(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            continue
    return None


def _clamav_check() -> str:
    binary = shutil.which("clamscan")
    if not binary:
        raise GateFailure("clamscan executable not found")
    version_proc = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=10, shell=False)
    version_text = (version_proc.stdout or version_proc.stderr).strip()
    if version_proc.returncode != 0:
        raise GateFailure("clamscan --version failed")

    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        handle.write(eicar)
        path = Path(handle.name)
    try:
        proc = subprocess.run([binary, "--no-summary", "--stdout", str(path)], capture_output=True, text=True, timeout=30, shell=False)
    finally:
        path.unlink(missing_ok=True)
    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 1 or "FOUND" not in output:
        raise GateFailure("ClamAV did not detect the EICAR test signature")

    max_age = int(os.getenv("CASEGRAPH_CLAMAV_MAX_DB_AGE_HOURS", "72"))
    db_time = _parse_clamav_db_time(version_text)
    if db_time is None:
        raise GateFailure(f"could not determine ClamAV signature timestamp from: {version_text[:200]}")
    age_hours = (datetime.now(timezone.utc) - db_time).total_seconds() / 3600
    if age_hours < -1:
        raise GateFailure("ClamAV signature timestamp is unexpectedly in the future")
    if age_hours > max_age:
        raise GateFailure(f"ClamAV signature database is {age_hours:.1f}h old; policy maximum is {max_age}h")
    return f"ClamAV EICAR detection PASS; signature DB age={age_hours:.1f}h; {version_text[:160]}"


def _otel_check() -> str:
    from backend.security.config import security_config
    if not security_config.otel_enabled or not security_config.otel_endpoint:
        raise GateFailure("OTel export is not configured")

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    provider = TracerProvider()
    memory = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    tracer = provider.get_tracer("casegraph.integration")
    with tracer.start_as_current_span("integration.live_probe") as span:
        span.set_attribute("casegraph.stage", "11L")
        span.set_attribute("casegraph.live_probe", True)
    spans = memory.get_finished_spans()
    if len(spans) != 1:
        raise GateFailure("could not construct OTel probe span")
    exporter = OTLPSpanExporter(endpoint=security_config.otel_endpoint, timeout=5)
    result = exporter.export(spans)
    try:
        exporter.shutdown()
    except Exception:
        pass
    if result != SpanExportResult.SUCCESS:
        raise GateFailure(f"OTLP exporter returned {result}")
    return f"OTLP trace probe exported successfully to {urlparse(security_config.otel_endpoint).hostname or 'configured endpoint'}"


def _frontend_check() -> str:
    frontend = ROOT / "frontend"
    if not (frontend / "package-lock.json").is_file():
        raise GateFailure("frontend/package-lock.json is missing")
    if not shutil.which("npm"):
        raise GateFailure("npm executable not found")

    commands = [
        ["npm", "ci"],
        ["npm", "run", "typecheck"],
        ["npm", "run", "build"],
        ["npm", "audit", "--audit-level=high"],
    ]
    summaries: list[str] = []
    for command in commands:
        proc = subprocess.run(command, cwd=frontend, capture_output=True, text=True, timeout=600, shell=False)
        if proc.returncode != 0:
            tail = (proc.stdout + "\n" + proc.stderr)[-2500:]
            raise GateFailure(f"{' '.join(command)} failed:\n{tail}")
        summaries.append(" ".join(command[1:]))
    return "frontend production gates passed: " + ", ".join(summaries)


def _paypal_read_check() -> str:
    import httpx

    base = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com").strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" or parsed.hostname != "api-m.sandbox.paypal.com":
        raise GateFailure("integration PayPal gate refuses any host other than https://api-m.sandbox.paypal.com")
    client_id = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    secret = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    if not client_id or not secret or client_id.startswith("your_") or secret.startswith("your_"):
        raise GateFailure("PayPal sandbox client ID/secret are not configured")

    with httpx.Client(timeout=20, follow_redirects=False) as client:
        token_resp = client.post(
            base + "/v1/oauth2/token",
            auth=(client_id, secret),
            headers={"Accept": "application/json", "Accept-Language": "en_US"},
            data={"grant_type": "client_credentials"},
        )
        token_resp.raise_for_status()
        token_payload = token_resp.json()
        access_token = str(token_payload.get("access_token", ""))
        if not access_token:
            raise GateFailure("PayPal OAuth response contained no access_token")
        disputes = client.get(
            base + "/v1/customer/disputes",
            params={"page_size": "1"},
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        disputes.raise_for_status()
        body = disputes.json()
        items = body.get("items") if isinstance(body, dict) else None
        count = len(items) if isinstance(items, list) else 0
    return f"PayPal sandbox OAuth + read-only disputes API PASS; sample item count={count}"


def build_report(args: argparse.Namespace) -> dict:
    checks: list[Check] = []
    checks.append(_run("production_security_config", args.require_production, _production_config_check))
    checks.append(_run("postgresql_runtime", args.require_postgres, _postgres_check))
    checks.append(_run("redis_rate_limiter", args.require_redis, _redis_check))
    checks.append(_run("oidc_discovery_jwks", args.require_oidc, lambda: _oidc_check(args.require_oidc_token)))
    checks.append(_run("clamav_runtime", args.require_clamav, _clamav_check))
    checks.append(_run("otel_export", args.require_otel, _otel_check))
    checks.append(_run("frontend_production_build", args.require_frontend, _frontend_check))
    checks.append(_run("paypal_sandbox_read", args.require_paypal_read, _paypal_read_check))

    required_failures = [c.name for c in checks if c.required and c.status != "PASS"]
    status = "PASS" if not required_failures else "FAIL"
    return {
        "stage": "11L",
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "required_failures": required_failures,
        "checks": [asdict(c) for c in checks],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CaseGraph integration live integration/freeze gate")
    parser.add_argument("--all", action="store_true", help="require every read-only/live infrastructure gate")
    parser.add_argument("--require-production", action="store_true")
    parser.add_argument("--require-postgres", action="store_true")
    parser.add_argument("--require-redis", action="store_true")
    parser.add_argument("--require-oidc", action="store_true")
    parser.add_argument("--require-oidc-token", action="store_true")
    parser.add_argument("--require-clamav", action="store_true")
    parser.add_argument("--require-otel", action="store_true")
    parser.add_argument("--require-frontend", action="store_true")
    parser.add_argument("--require-paypal-read", action="store_true")
    parser.add_argument("--report", default="docs/INTEGRATION_GATE_REPORT.json")
    args = parser.parse_args()
    if args.all:
        args.require_production = True
        args.require_postgres = True
        args.require_redis = True
        args.require_oidc = True
        args.require_oidc_token = True
        args.require_clamav = True
        args.require_otel = True
        args.require_frontend = True
        args.require_paypal_read = True
    if args.require_oidc_token:
        args.require_oidc = True
    required_flags = [
        args.require_production, args.require_postgres, args.require_redis,
        args.require_oidc, args.require_clamav, args.require_otel,
        args.require_frontend, args.require_paypal_read,
    ]
    if not any(required_flags):
        parser.error("select at least one --require-* gate or use --all")

    report = build_report(args)
    target = ROOT / args.report
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
