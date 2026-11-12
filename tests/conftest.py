"""Test-session bootstrap.

Two guarantees, both learned the hard way from the previous test layout:

1. Running `pytest` must never touch the developer's development database.
   Several suites call ``Base.metadata.drop_all(engine)`` in an autouse fixture,
   and they previously bound to ``.data/casegraph.db`` — the same file the
   running application uses. A test run could therefore delete real local cases.
   The URL below is only a default: an explicit ``DATABASE_URL`` always wins, so
   CI and production-like verification can point tests at any isolated database.
   When `pytest` creates its own per-process SQLite file, an `atexit` handler
   disposes the engine and unlinks the temporary file so `.data/` does not
   accumulate stale `pytest-<pid>.db` files.

2. Local/test runs must not depend on operator-configured secrets. Authentication
   stays disabled and PayPal webhook verification stays off unless a test opts in.
"""

from __future__ import annotations

import atexit
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

if not os.environ.get("DATABASE_URL"):
    _db_dir = _ROOT / ".data"
    _db_dir.mkdir(parents=True, exist_ok=True)
    _db_path = _db_dir / f"pytest-{os.getpid()}.db"
    # A fresh process must start from an empty schema; suites create and drop
    # tables, so reusing a file from an earlier PID would leak state.
    _db_path.unlink(missing_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{_db_path.as_posix()}"

    def _cleanup_test_db() -> None:
        try:
            from backend.db.session import engine

            engine.dispose()
        except Exception:
            pass
        try:
            _db_path.unlink(missing_ok=True)
        except OSError:
            pass

    atexit.register(_cleanup_test_db)

os.environ.setdefault("CASEGRAPH_ENV", "test")
os.environ.setdefault("CASEGRAPH_AUTH_MODE", "disabled")
os.environ.setdefault("PAYPAL_WEBHOOK_VERIFY", "false")
# The test profile mirrors .env.example: uploads are accepted without a scanner.
os.environ.setdefault("CASEGRAPH_UPLOAD_ALLOW_UNSCANNED_DEV", "true")
