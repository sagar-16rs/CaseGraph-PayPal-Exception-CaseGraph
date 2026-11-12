from __future__ import annotations

import argparse
import asyncio
import socket
import uuid
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.work.service import work_service


def default_worker_id() -> str:
    return f"{socket.gethostname()}-{uuid.uuid4().hex[:10]}"


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Run the CaseGraph durable background worker")
    parser.add_argument("--once", action="store_true", help="Process at most one available work item and exit")
    parser.add_argument("--worker-id", default=None, help="Stable worker identifier for logs and leases")
    args = parser.parse_args()

    worker_id = args.worker_id or default_worker_id()
    work_service.backfill_unprocessed_events()
    if args.once:
        processed = await work_service.run_once(lease_owner=worker_id)
        return 0 if processed else 0

    await work_service.run_forever(lease_owner=worker_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
