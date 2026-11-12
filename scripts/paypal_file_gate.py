from __future__ import annotations

import argparse
import json
import os
from urllib.parse import urlparse

import httpx

CONFIRM = "EXECUTE_SANDBOX_PAYPAL_FILE_WRITE"


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute one already-approved CaseGraph sandbox file-evidence action")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--action-uid", required=True)
    parser.add_argument("--approval-hash", required=True)
    parser.add_argument("--execute-confirm")
    args = parser.parse_args()

    if args.execute_confirm != CONFIRM:
        print(json.dumps({"status": "BLOCKED", "reason": f"pass --execute-confirm {CONFIRM} only after reviewing the immutable approval"}, indent=2))
        return 2

    base = os.getenv("CASEGRAPH_INTEGRATION_API_URL", "http://127.0.0.1:8000").rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SystemExit("Invalid CASEGRAPH_INTEGRATION_API_URL")
    token = os.getenv("CASEGRAPH_INTEGRATION_BEARER_TOKEN", "").strip()
    if not token:
        raise SystemExit("CASEGRAPH_INTEGRATION_BEARER_TOKEN is required; keep it only in your local environment")

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    with httpx.Client(timeout=60, follow_redirects=False, headers=headers) as client:
        health = client.get(base + "/health")
        health.raise_for_status()
        h = health.json()
        if h.get("paypal_environment") != "sandbox":
            raise SystemExit("REFUSED: CaseGraph backend is not reporting PayPal sandbox mode")

        action_url = f"{base}/api/cases/{args.case_id}/actions/{args.action_uid}"
        before = client.get(action_url)
        before.raise_for_status()
        action = before.json()
        if action.get("approval_hash") != args.approval_hash:
            raise SystemExit("REFUSED: supplied approval hash does not match stored immutable approval")
        if action.get("action_type") not in {"PROVIDE_EVIDENCE", "APPEAL"}:
            raise SystemExit("REFUSED: integration file gate only executes PROVIDE_EVIDENCE or APPEAL")
        if action.get("execution_status") != "NOT_STARTED":
            raise SystemExit(f"REFUSED: action execution status is {action.get('execution_status')}")
        evidences = (action.get("payload") or {}).get("evidences") or []
        refs = [ref for item in evidences for ref in (item.get("file_refs") or [])]
        if not refs:
            raise SystemExit("REFUSED: approval contains no immutable file references")

        execute = client.post(action_url + "/execute", json={"approval_hash": args.approval_hash})
        execute.raise_for_status()
        result = execute.json()
        after = client.get(action_url)
        after.raise_for_status()
        final = after.json()

    safe = {
        "status": "PASS" if final.get("execution_status") == "EXECUTED" else "REVIEW",
        "case_id": args.case_id,
        "action_uid": args.action_uid,
        "action_type": final.get("action_type"),
        "execution_status": final.get("execution_status"),
        "post_action_sync_pending": final.get("post_action_sync_pending"),
        "file_ref_count": len(refs),
        "result_status": result.get("result_status"),
        "warning": result.get("warning"),
    }
    print(json.dumps(safe, indent=2, sort_keys=True))
    return 0 if safe["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
