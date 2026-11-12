from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = ROOT / "data" / "submission" / "rules_snapshot.json"
CLAIMS_PATH = ROOT / "data" / "submission" / "claim_ledger.json"
SUBMISSION_PATH = ROOT / "data" / "submission" / "submission.json"

PLACEHOLDERS = {"", "CHANGE_ME", "TODO", "TBD", "https://example.com", "YOUR_URL"}
ALLOWED_CLAIM_STATUS = {"LOCAL_VERIFIED", "LIVE_VERIFIED", "PENDING", "NOT_APPLICABLE"}
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bA21AA[A-Za-z0-9._-]{20,}\b"),
    re.compile(r"(?m)^PAYPAL_CLIENT_SECRET=(?!\s*(?:$|CHANGE_ME|your_|<|sandbox-secret|test-secret))\S+"),
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def is_placeholder(value: str | None) -> bool:
    return value is None or value.strip() in PLACEHOLDERS or "CHANGE_ME" in value or "TODO" in value


def lint_claims(claims: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for item in claims.get("claims", []):
        cid = str(item.get("id", ""))
        if not cid or cid in seen:
            errors.append(f"invalid/duplicate claim id: {cid!r}")
        seen.add(cid)
        status = item.get("status")
        if status not in ALLOWED_CLAIM_STATUS:
            errors.append(f"{cid}: unsupported status {status!r}")
        if item.get("include_in_submission") and status == "PENDING":
            errors.append(f"{cid}: pending claim cannot be included in submission")
        wording = str(item.get("submission_wording", "")).strip()
        if item.get("include_in_submission") and not wording:
            errors.append(f"{cid}: included claim needs submission_wording")
    return errors


def scan_text_for_secrets(text: str) -> list[str]:
    hits = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            hits.append(pattern.pattern)
    return hits


def safe_public_file(path: Path, repo_root: Path) -> tuple[bool, str | None]:
    rel = path.relative_to(repo_root).as_posix()
    rel_parts = path.relative_to(repo_root).parts
    parts = set(rel_parts)
    name = path.name
    if parts & {".git", ".data", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", "dist", ".venv", "venv", ".omp"}:
        return False, "generated/private directory"
    if any(part.startswith("pytest-cache-files-") for part in rel_parts):
        return False, "generated/private directory"
    if rel.startswith(("research/.tmp/", "research/.baseline/")):
        return False, "generated/private directory"
    if path.suffix.lower() in {".pyc", ".pyo", ".db", ".sqlite3", ".tsbuildinfo", ".zip"}:
        return False, "generated/private artifact"
    if rel.startswith("study_runs/") and name != ".gitignore":
        return False, "participant study data"
    if rel.startswith("evaluation_runs/"):
        return False, "evaluation runtime data"
    if rel in {"docs/INTEGRATION_GATE_REPORT.json", "docs/VALIDATION_RESULTS.json"}:
        return False, "private live-validation report"
    if rel.startswith("uploads/") or rel.startswith("private_uploads/"):
        return False, "uploaded evidence bytes"
    if name == ".env" or (name.startswith(".env.") and not name.endswith(".example")):
        return False, "environment secret file"
    if name.lower() in {"id_rsa", "credentials.json", "secrets.json"} or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
        if not name.endswith(".example"):
            return False, "credential/private key file"
    return True, None
