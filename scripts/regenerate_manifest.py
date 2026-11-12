"""Regenerate MANIFEST.sha256 for the distributable source tree.

The manifest is a human-readable integrity snapshot: it lets a reviewer confirm
that the files they received match the release. It is *not* consumed by any
runtime path, so it is refreshed on demand rather than at import time.

Scope deliberately excludes secrets, dependency directories, generated output,
runtime state, and research artifacts. Paths are written with POSIX separators
and sorted by POSIX path string so the manifest verifies identically on Windows,
macOS, and Linux.

Usage:
    python scripts/regenerate_manifest.py [--check]

`--check` reports drift without rewriting the file, which is what a release gate
would use.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST.sha256"

EXCLUDED_DIRS = {
    ".git", ".data", ".venv", "venv", "node_modules", "dist", "__pycache__",
    ".pytest_cache", ".ruff_cache", "study_runs", "evaluation_runs", "research",
    "uploads", "private_uploads", ".omp",
}
EXCLUDED_NAMES = {".env", "MANIFEST.sha256"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".zip", ".db", ".sqlite3", ".tsbuildinfo"}


def is_distributable(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if set(relative.parts) & EXCLUDED_DIRS:
        return False
    if any(part.startswith("pytest-cache-files-") for part in relative.parts):
        return False
    if path.name in EXCLUDED_NAMES:
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    if path.name.startswith(".env.") and not path.name.endswith(".example"):
        return False
    return True


def build_lines() -> list[str]:
    lines: list[str] = []
    # Sort by POSIX string key rather than OS-specific Path comparison so Windows
    # (case-insensitive WindowsPath) and Linux/macOS (case-sensitive PosixPath)
    # produce identical ordering.
    paths = [p for p in ROOT.rglob("*") if p.is_file() and is_distributable(p)]
    for path in sorted(paths, key=lambda p: p.relative_to(ROOT).as_posix()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(ROOT).as_posix()}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate or verify MANIFEST.sha256")
    parser.add_argument("--check", action="store_true", help="Report drift without rewriting the manifest")
    args = parser.parse_args()

    lines = build_lines()
    payload = "\n".join(lines) + "\n"
    current = MANIFEST.read_text(encoding="utf-8") if MANIFEST.is_file() else ""

    if args.check:
        if current == payload:
            print(f"PASS: manifest matches {len(lines)} files")
            return 0
        print(f"FAIL: manifest drift ({len(lines)} files currently in tree)")
        return 1

    MANIFEST.write_text(payload, encoding="utf-8")
    print(f"wrote {len(lines)} entries to {MANIFEST.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
