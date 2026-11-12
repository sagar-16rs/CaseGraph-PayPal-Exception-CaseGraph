from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.api.actions import router as actions_router
from backend.api.ai import router as ai_router
from backend.api.cases import router as cases_router
from backend.api.evidence import router as evidence_router
from backend.api.graphs import router as graphs_router
from backend.api.reconciliation import router as reconciliation_router
from backend.api.safety import router as safety_router
from backend.api.work import router as work_router
from backend.config import settings
from backend.db.migrations import create_all, current_database_revision, expected_head_revision
from backend.db.session import engine
from backend.paypal.webhooks import router as webhook_router
from backend.security.config import security_config
from backend.security.install import install_security
from backend.version import VERSION

logger = logging.getLogger("casegraph.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Local/test mode is intentionally self-contained. Production must use the
    # audited Alembic migration chain and refuses to start on a stale/unmigrated DB.
    if security_config.production:
        if settings.database_backend != "postgresql":
            raise RuntimeError("Production CaseGraph requires PostgreSQL")
        if settings.simulated_paypal:
            # The simulated transport stands in for PayPal. Letting a production
            # process believe it has executed a financial action would be the most
            # dangerous failure this system can have.
            raise RuntimeError("Production CaseGraph forbids the simulated PayPal transport")
        if not settings.paypal_webhook_verify or not settings.paypal_webhook_id:
            raise RuntimeError("Production CaseGraph requires verified PayPal webhooks and PAYPAL_WEBHOOK_ID")
        current = current_database_revision(engine)
        expected = expected_head_revision()
        if current != expected:
            raise RuntimeError(
                f"Production database migration mismatch: current={current!r}, expected={expected!r}. "
                "Run 'alembic upgrade head' before starting CaseGraph."
            )
    else:
        create_all()

    try:
        from backend.work.service import work_service

        work_service.backfill_unprocessed_events()
    except Exception:
        if security_config.production:
            # Losing the durable webhook backfill silently would violate the event
            # processing guarantee, so production startup fails closed.
            raise
        logger.exception("Local startup could not backfill durable PayPal events")

    yield


app = FastAPI(
    title="CaseGraph — PayPal Exception CaseGraph",
    version=VERSION,
    docs_url=None if security_config.production else "/docs",
    redoc_url=None if security_config.production else "/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        list(security_config.allowed_origins)
        if security_config.allowed_origins
        else ["http://127.0.0.1:5173", "http://localhost:5173"]
    ),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

app.include_router(cases_router)
app.include_router(evidence_router)
app.include_router(graphs_router)
app.include_router(ai_router)
app.include_router(safety_router)
app.include_router(actions_router)
app.include_router(work_router)
app.include_router(reconciliation_router)
app.include_router(webhook_router)
install_security(app)


@app.get("/health", tags=["system"])
def health():
    return {
        "status": "ok",
        "service": "casegraph-backend",
        "version": VERSION,
    }


@app.get("/ready", tags=["system"])
def readiness():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        revision_ok = (
            not security_config.production
            or current_database_revision(engine) == expected_head_revision()
        )
    except Exception:
        return {"status": "not_ready", "database": False, "migration_head": False}
    return {
        "status": "ready" if revision_ok else "not_ready",
        "database": True,
        "migration_head": revision_ok,
    }
