from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, select, text
from sqlalchemy.dialects import postgresql

from backend.config import settings
from backend.db import session as db_session
from backend.db.migrations import current_database_revision, expected_head_revision
from backend.db.models import WorkItem
from backend.work.dispute_lock import advisory_key
from backend.work.service import work_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate durable work-queue and reconciliation infrastructure")
    parser.add_argument("--require-postgres", action="store_true")
    args = parser.parse_args()

    checks: dict[str, bool] = {}
    details: dict[str, object] = {"database_backend": settings.database_backend}

    try:
        with db_session.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database_connectivity"] = True
    except Exception as exc:
        checks["database_connectivity"] = False
        details["database_error"] = f"{type(exc).__name__}: {exc}"
        print(json.dumps({"status": "FAIL", "checks": checks, "details": details}, indent=2))
        return 1

    expected_revision = expected_head_revision()
    current_revision = current_database_revision(db_session.engine)
    details["current_revision"] = current_revision
    details["expected_revision"] = expected_revision
    checks["alembic_head"] = current_revision == expected_revision

    table_names = set(inspect(db_session.engine).get_table_names())
    required_tables = {"work_items", "action_reconciliations"}
    checks["work_tables_present"] = required_tables.issubset(table_names)
    details["missing_work_tables"] = sorted(required_tables - table_names)
    checks["lease_exceeds_paypal_timeout"] = settings.worker_lease_seconds >= settings.paypal_timeout_seconds + 10

    statement = (
        select(WorkItem)
        .where(WorkItem.status.in_(["READY", "RETRY"]))
        .order_by(WorkItem.available_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    checks["postgres_skip_locked_compiles"] = "SKIP LOCKED" in str(
        statement.compile(dialect=postgresql.dialect())
    )

    checks["postgresql_backend"] = settings.database_backend == "postgresql"
    checks["postgres_advisory_lock_runtime"] = False
    if checks["postgresql_backend"]:
        key = advisory_key("CASEGRAPH-OPERATIONS-DOCTOR")
        try:
            with db_session.engine.connect() as connection:
                acquired = bool(connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar())
                connection.commit()
                if acquired:
                    released = bool(connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key}).scalar())
                    connection.commit()
                    checks["postgres_advisory_lock_runtime"] = released
        except Exception as exc:
            details["postgres_lock_error"] = f"{type(exc).__name__}: {exc}"

    if checks["work_tables_present"]:
        try:
            details["queue"] = work_service.status().model_dump()
        except Exception as exc:
            details["queue_error"] = f"{type(exc).__name__}: {exc}"

    required = [
        "database_connectivity",
        "alembic_head",
        "work_tables_present",
        "lease_exceeds_paypal_timeout",
        "postgres_skip_locked_compiles",
    ]
    if args.require_postgres:
        required.extend(["postgresql_backend", "postgres_advisory_lock_runtime"])

    passed = all(checks.get(name, False) for name in required)
    if not passed:
        status = "FAIL"
    elif checks["postgresql_backend"]:
        status = "PASS"
    else:
        status = "LOCAL_PASS_POSTGRES_PENDING"

    print(json.dumps({"status": status, "checks": checks, "details": details}, indent=2, default=str))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
