from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("integration_live_gate", ROOT / "scripts/integration_gate.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def test_jwks_validation_rejects_symmetric_keys():
    try:
        mod._validate_jwks({"keys": [{"kty": "oct", "kid": "bad", "k": "secret"}]})
    except mod.GateFailure as exc:
        assert "symmetric" in str(exc)
    else:
        raise AssertionError("symmetric JWK was accepted")


def test_jwks_validation_rejects_private_material():
    try:
        mod._validate_jwks({"keys": [{"kty": "RSA", "kid": "k1", "alg": "RS256", "d": "private"}]})
    except mod.GateFailure as exc:
        assert "private" in str(exc)
    else:
        raise AssertionError("private JWK material was accepted")


def test_jwks_validation_accepts_public_signing_keys():
    count, kids = mod._validate_jwks({"keys": [{"kty": "RSA", "kid": "k1", "alg": "RS256", "use": "sig", "n": "x", "e": "AQAB"}]})
    assert count == 1 and kids == ["k1"]


def test_clamav_version_timestamp_parser():
    parsed = mod._parse_clamav_db_time("ClamAV 1.4.3/27885/Tue Oct 20 12:34:56 2026")
    assert parsed is not None
    assert parsed.year == 2026 and parsed.month == 10 and parsed.day == 20


def test_optional_check_failure_is_warn_not_fail():
    check = mod._run("x", False, lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert check.status == "WARN"


def test_required_check_failure_is_fail():
    check = mod._run("x", True, lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert check.status == "FAIL"

def test_cli_refuses_empty_gate_configuration():
    text = (ROOT / "scripts/integration_gate.py").read_text(encoding="utf-8")
    assert 'parser.error("select at least one --require-* gate or use --all")' in text
