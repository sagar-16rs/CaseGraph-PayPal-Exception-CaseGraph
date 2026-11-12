from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.config import settings
from backend.db import session as db_session


# The production path uses a PostgreSQL session-level advisory lock. The lock is
# intentionally not transaction-scoped: CaseGraph must not keep a DB transaction
# open while waiting on PayPal network I/O. If the process/connection dies,
# PostgreSQL releases the session lock automatically.
_LOCK_POLL_SECONDS = 0.05
_LOCAL_LOCKS: dict[tuple[asyncio.AbstractEventLoop, str], asyncio.Lock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()


class DisputeSyncLockTimeout(RuntimeError):
    pass


def advisory_key(dispute_id: str) -> int:
    """Return a deterministic signed int64 advisory-lock key for a dispute id."""
    digest = hashlib.sha256(f"casegraph:paypal-dispute:{dispute_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _try_postgres_lock(key: int) -> Connection | None:
    conn = db_session.engine.connect()
    try:
        acquired = bool(
            conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar()
        )
        # SQLAlchemy autobegins around SELECT. End that transaction immediately;
        # the session-level advisory lock remains owned by this connection.
        conn.commit()
        if acquired:
            return conn
    except Exception:
        conn.close()
        raise
    conn.close()
    return None


def _release_postgres_lock(conn: Connection, key: int) -> None:
    try:
        released = bool(
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key}).scalar()
        )
        conn.commit()
        if not released:
            # A pooled physical connection must never be returned while CaseGraph
            # is unsure whether it still owns a session-level lock. Invalidate it
            # so the pool discards the DBAPI connection and PostgreSQL ends that
            # session rather than risking a leaked lock.
            conn.invalidate()
            raise RuntimeError("PostgreSQL advisory lock was unexpectedly not held at release")
    except Exception:
        # If unlock itself fails, force the physical pooled connection out of use.
        # Server/session teardown is the final lock-release mechanism.
        conn.invalidate()
        raise
    finally:
        conn.close()


def _lock_wait_seconds() -> float:
    # Keep dispute-lock contention inside the existing queue lease budget. durable-work layer
    # already requires lease >= PayPal timeout + 10s. Any extra lease headroom may
    # be spent waiting for the per-dispute lock, capped at 30s. This avoids adding
    # a heartbeat while preventing normal lock contention from consuming the lease.
    headroom = float(settings.worker_lease_seconds) - float(settings.paypal_timeout_seconds) - 10.0
    return max(0.0, min(30.0, headroom))


def _local_lock(dispute_id: str) -> asyncio.Lock:
    # SQLite is explicitly a single-process development fallback. This lock only
    # prevents overlap within that process; production multi-process safety is the
    # PostgreSQL advisory-lock path above.
    loop = asyncio.get_running_loop()
    key = (loop, dispute_id)
    with _LOCAL_LOCKS_GUARD:
        lock = _LOCAL_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _LOCAL_LOCKS[key] = lock
        return lock


@asynccontextmanager
async def dispute_sync_guard(dispute_id: str) -> AsyncIterator[None]:
    if not dispute_id:
        raise ValueError("dispute_id is required for synchronization locking")

    if settings.database_backend != "postgresql":
        lock = _local_lock(dispute_id)
        wait_seconds = _lock_wait_seconds()
        try:
            if wait_seconds <= 0:
                if lock.locked():
                    raise DisputeSyncLockTimeout(
                        f"Local dispute synchronization lock is busy: {dispute_id}"
                    )
                await lock.acquire()
            else:
                await asyncio.wait_for(lock.acquire(), timeout=wait_seconds)
        except TimeoutError as exc:
            raise DisputeSyncLockTimeout(
                f"Timed out waiting for local dispute synchronization lock: {dispute_id}"
            ) from exc
        try:
            yield
        finally:
            lock.release()
        return

    key = advisory_key(dispute_id)
    deadline = time.monotonic() + _lock_wait_seconds()
    conn: Connection | None = None
    while conn is None:
        # pg_try_advisory_lock does not block the event loop waiting on another
        # session. The query itself is short; contention waits happen via the
        # async sleep below.
        conn = _try_postgres_lock(key)
        if conn is not None:
            break
        if time.monotonic() >= deadline:
            raise DisputeSyncLockTimeout(
                f"Timed out waiting for PayPal dispute synchronization lock: {dispute_id}"
            )
        await asyncio.sleep(_LOCK_POLL_SECONDS)

    try:
        yield
    finally:
        _release_postgres_lock(conn, key)
