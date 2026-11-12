from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.security.config import security_config


async def _redis_ping() -> tuple[bool, str | None]:
    try:
        from backend.security.rate_limit import RedisRateLimiter

        limiter = RedisRateLimiter(security_config.redis_url)
        return bool(await limiter.ping()), None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _clamav_check() -> tuple[bool, dict[str, str]]:
    details: dict[str, str] = {}
    binary = shutil.which("clamscan")
    if not binary:
        return False, {"error": "clamscan executable not found"}

    eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        handle.write(eicar)
        path = Path(handle.name)
    try:
        scan = subprocess.run(
            [binary, "--no-summary", "--stdout", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
            shell=False,
        )
        version = subprocess.run(
            [binary, "--version"], capture_output=True, text=True, timeout=10, shell=False
        )
        details["version"] = version.stdout.strip()[:500]
        if scan.returncode == 1 and "FOUND" in (scan.stdout + scan.stderr):
            return True, details
        details["error"] = (scan.stdout or scan.stderr or f"exit {scan.returncode}").strip()[:1000]
        return False, details
    except Exception as exc:
        return False, {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        path.unlink(missing_ok=True)


def build_report(args: argparse.Namespace) -> dict:
    checks: dict[str, bool] = {}
    details: dict[str, object] = {
        "environment": security_config.environment,
        "auth_mode": security_config.auth_mode,
        "rate_backend": security_config.rate_backend,
        "upload_scanner": security_config.upload_scanner,
        "allowed_origins": list(security_config.allowed_origins),
        "otel_enabled": security_config.otel_enabled,
    }

    config_errors = security_config.validate()
    details["config_errors"] = config_errors
    checks["security_config"] = not config_errors
    checks["jwt_crypto_dependencies"] = (
        importlib.util.find_spec("jwt") is not None and importlib.util.find_spec("cryptography") is not None
    )
    checks["multipart_dependency"] = importlib.util.find_spec("multipart") is not None
    checks["security_migration_present"] = (
        ROOT / "migrations/versions/20261025_0008_security_uploads.py"
    ).is_file()
    checks["manual_reconcile_not_public"] = not any(
        "reconcile/manual" in path.read_text(encoding="utf-8", errors="ignore")
        for path in (ROOT / "backend").rglob("*.py")
    )

    try:
        upload_dir = security_config.upload_dir.resolve()
        upload_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=upload_dir, delete=True) as handle:
            handle.write(b"doctor")
            handle.flush()
        checks["upload_storage_writable"] = True
        details["upload_dir"] = str(upload_dir)
    except Exception as exc:
        checks["upload_storage_writable"] = False
        details["upload_error"] = f"{type(exc).__name__}: {exc}"

    if args.require_clamav or security_config.production:
        ok, clamav_details = _clamav_check()
        checks["clamav"] = ok
        details["clamav"] = clamav_details
    else:
        checks["clamav"] = True
        details["clamav_available"] = shutil.which("clamscan") is not None

    if args.require_redis or security_config.production:
        ok, error = asyncio.run(_redis_ping())
        checks["redis_rate_limiter"] = ok
        if error:
            details["redis_error"] = error
    else:
        checks["redis_rate_limiter"] = True

    lockfile = ROOT / "frontend/package-lock.json"
    checks["frontend_lockfile"] = lockfile.is_file() if args.require_frontend_lock else True
    details["frontend_lockfile_present"] = lockfile.is_file()

    if args.require_casegraph:
        try:
            from sqlalchemy import inspect
            from backend.config import settings
            from backend.db.migrations import current_database_revision, expected_head_revision
            from backend.db.session import engine

            current = current_database_revision(engine)
            expected = expected_head_revision()
            tables = set(inspect(engine).get_table_names())
            checks["alembic_head"] = current == expected
            checks["evidence_files_table"] = "evidence_files" in tables
            checks["paypal_webhook_verification"] = (
                bool(settings.paypal_webhook_verify and settings.paypal_webhook_id)
                if security_config.production
                else True
            )
            checks["cors_no_wildcard"] = "*" not in security_config.allowed_origins
            details["database_revision"] = current
            details["expected_revision"] = expected
            checks["casegraph_runtime"] = True
        except Exception as exc:
            checks["casegraph_runtime"] = False
            details["casegraph_error"] = f"{type(exc).__name__}: {exc}"
    else:
        checks["casegraph_runtime"] = True

    if args.require_production:
        checks["production_mode"] = security_config.production
        checks["auth_enforced"] = security_config.auth_enforced
        checks["role_separation"] = security_config.enforce_role_separation
        checks["redis_required"] = security_config.rate_backend == "redis" and bool(security_config.redis_url)
        checks["scanner_required"] = security_config.upload_scanner == "clamav"
        checks["explicit_https_origins"] = bool(security_config.allowed_origins) and all(
            origin.startswith("https://") and origin != "*" for origin in security_config.allowed_origins
        )

    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CaseGraph security configuration and dependencies")
    parser.add_argument("--require-production", action="store_true")
    parser.add_argument("--require-casegraph", action="store_true")
    parser.add_argument("--require-redis", action="store_true")
    parser.add_argument("--require-clamav", action="store_true")
    parser.add_argument("--require-frontend-lock", action="store_true")
    args = parser.parse_args()
    report = build_report(args)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
