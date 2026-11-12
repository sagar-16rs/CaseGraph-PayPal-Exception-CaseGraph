from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    checks: dict[str, bool] = {}
    details: dict[str, object] = {}
    try:
        from backend.security.config import security_config
        errors = security_config.validate()
        details["security_config_errors"] = errors
        checks["security_security_config"] = not errors
        details["environment"] = security_config.environment
        details["rate_backend"] = security_config.rate_backend
        details["upload_scanner"] = security_config.upload_scanner
        details["otel_enabled"] = security_config.otel_enabled
    except Exception as exc:
        checks["security_security_config"] = False
        details["security_config_error"] = f"{type(exc).__name__}: {exc}"

    expected = {
        "backend/uploads/action_files.py",
        "scripts/integration_gate.py",
        "scripts/paypal_file_gate.py",
        "docs/OPERATIONS.md",
    }
    missing = sorted(rel for rel in expected if not (ROOT / rel).is_file())
    details["missing_integration_files"] = missing
    checks["integration_files"] = not missing

    action_files = (ROOT / "backend/uploads/action_files.py").read_text(encoding="utf-8", errors="ignore") if (ROOT / "backend/uploads/action_files.py").is_file() else ""
    checks["file_ref_defense_in_depth"] = (
        "conflicting hashes" in action_files
        and "hash does not match the approved payload" in action_files
        and "50 MB per-call limit" in action_files
    )
    checks["pyjwt"] = importlib.util.find_spec("jwt") is not None
    checks["httpx"] = importlib.util.find_spec("httpx") is not None
    checks["sqlalchemy"] = importlib.util.find_spec("sqlalchemy") is not None

    report = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "details": details}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
