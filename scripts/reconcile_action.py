from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import session as db_session
from backend.db.migrations import assert_database_ready
from backend.work.reconciliation import reconciliation_service
from backend.work.schemas import ManualReconciliationRequest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Operator-only durable-work layer manual reconciliation. Use only after directly "
            "verifying the action outcome in the PayPal dashboard."
        )
    )
    parser.add_argument("case_id")
    parser.add_argument("action_uid")
    parser.add_argument(
        "decision",
        choices=["CONFIRMED_EXECUTED", "CONFIRMED_NOT_EXECUTED"],
    )
    parser.add_argument("--confirmed-by", required=True)
    parser.add_argument("--note", required=True)
    parser.add_argument(
        "--confirm-paypal-dashboard",
        action="store_true",
        help="Required acknowledgement that the outcome was checked directly in PayPal.",
    )
    args = parser.parse_args()
    if not args.confirm_paypal_dashboard:
        parser.error("--confirm-paypal-dashboard is required; ambiguous writes must fail closed")
    return args


async def main() -> None:
    args = parse_args()
    assert_database_ready(db_session.engine)
    req = ManualReconciliationRequest(
        decision=args.decision,
        confirmed_by=args.confirmed_by,
        note=args.note,
        confirmed_from_paypal_dashboard=True,
    )
    result = await reconciliation_service.manual(args.case_id, args.action_uid, req)
    print(json.dumps(result.model_dump(), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
