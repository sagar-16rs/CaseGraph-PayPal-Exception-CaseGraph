from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import settings
from backend.db.migrations import create_all, current_database_revision, expected_head_revision
from backend.db.session import engine
from backend.security.config import security_config


REQUIRED_TABLES = {
    "cases",
    "paypal_facts",
    "evidence_revisions",
    "evidence_set_revisions",
    "case_graph_revisions",
    "ai_analyses",
    "ai_safety_assessments",
    "action_approvals",
    "paypal_events",
    "work_items",
    "action_reconciliations",
    "evidence_files",
}


def build_report() -> dict:
    # Development/test may use metadata creation for convenience. Production
    # diagnostics must be read-only: schema changes belong exclusively to Alembic.
    if not security_config.production:
        create_all()

    security_errors = security_config.validate()
    checks: dict[str, bool] = {
        "db_connectivity": False,
        "required_tables": False,
        "alembic_head": False,
        "security_configuration": not security_errors,
        # This repository defaults to PayPal sandbox. Moving to
        # live credentials must be an explicit deployment decision after sandbox proof.
        "paypal_sandbox_url": settings.paypal_base_url == "https://api-m.sandbox.paypal.com",
    }
    db_error: str | None = None
    tables: set[str] = set()
    current_revision: str | None = None
    expected_revision = expected_head_revision()

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            checks["db_connectivity"] = True
        tables = set(inspect(engine).get_table_names())
        checks["required_tables"] = REQUIRED_TABLES <= tables
        current_revision = current_database_revision(engine)
        checks["alembic_head"] = current_revision == expected_revision
    except Exception as exc:  # pragma: no cover - diagnostic path
        db_error = str(exc)

    # Webhook verification may be relaxed only in local/test environments so
    # deterministic tests can inject synthetic events. Production must fail
    # closed and identify the exact PayPal webhook registration.
    if security_config.production:
        checks["production_postgresql"] = settings.database_backend == "postgresql"
        checks["paypal_credentials"] = bool(settings.paypal_client_id and settings.paypal_client_secret)
        checks["paypal_webhook_verification"] = bool(
            settings.paypal_webhook_verify and settings.paypal_webhook_id
        )
        checks["openai_configured"] = bool(settings.openai_api_key)

    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "database_backend": settings.database_backend,
        "environment": security_config.environment,
        "expected_revision": expected_revision,
        "current_revision": current_revision,
        "missing_tables": sorted(REQUIRED_TABLES - tables),
        "security_errors": security_errors,
        "database_error": db_error,
    }


def main() -> int:
    report = build_report()
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
