from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_DIRS = {".git", ".data", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", "dist", ".venv", "venv", ".omp"}
#: Scratch trees that are never published: local baselines, throwaway databases and
#: browser profiles. Scanning them produced false positives (a Chrome TTS cache
#: matched the API-key pattern), which trains people to ignore the scan.
FORBIDDEN_PREFIXES = ("research/.tmp/", "research/.baseline/", "pytest-cache-files-")
SECRET_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "paypal_client_secret": re.compile(r"(?m)^PAYPAL_CLIENT_SECRET=(?!\s*(?:$|CHANGE_ME|your_|<|sandbox-secret|test-secret))\S+"),
}


def main() -> int:
    findings: list[dict[str, str]] = []
    forbidden_files: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if set(rel.parts) & FORBIDDEN_DIRS:
            continue
        if rel.as_posix().startswith(FORBIDDEN_PREFIXES):
            continue
        if path.name == ".env" or path.suffix.lower() in {".pyc", ".pyo"}:
            forbidden_files.append(rel.as_posix())
            continue
        if path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text("utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for kind, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append({"path": rel.as_posix(), "kind": kind})
    status = "PASS" if not findings and not forbidden_files else "FAIL"
    report = {
        "status": status,
        "secret_like_findings": findings,
        "forbidden_source_files": forbidden_files,
    }
    print(json.dumps(report, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
