from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from backend.security.config import SecurityConfig


class MalwareScanError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ScanResult:
    clean: bool
    detail: str


class Scanner:
    def scan(self, path: Path) -> ScanResult:
        raise NotImplementedError


class ClamAVScanner(Scanner):
    def __init__(self, timeout_seconds: int = 30):
        binary = shutil.which("clamscan")
        if not binary:
            raise MalwareScanError("clamscan executable not found")
        self.binary = binary
        self.timeout_seconds = timeout_seconds

    def scan(self, path: Path) -> ScanResult:
        proc = subprocess.run(
            [self.binary, "--no-summary", "--stdout", str(path)],
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            shell=False,
        )
        detail = (proc.stdout or proc.stderr or "").strip()[:1000]
        if proc.returncode == 0:
            return ScanResult(True, detail or "clamav clean")
        if proc.returncode == 1:
            return ScanResult(False, detail or "clamav malware detected")
        raise MalwareScanError(detail or f"clamscan failed with code {proc.returncode}")


class DevNoopScanner(Scanner):
    def scan(self, path: Path) -> ScanResult:
        return ScanResult(True, "UNSCANNED_DEV_ONLY")


def build_scanner(config: SecurityConfig) -> Scanner:
    if config.upload_scanner == "clamav":
        return ClamAVScanner()
    if not config.production and config.upload_allow_unscanned_dev:
        return DevNoopScanner()
    raise MalwareScanError("no safe upload scanner is configured")
