from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_paypal_file_gate_is_explicit_and_sandbox_only():
    text = (ROOT / "scripts/paypal_file_gate.py").read_text(encoding="utf-8")
    assert 'CONFIRM = "EXECUTE_SANDBOX_PAYPAL_FILE_WRITE"' in text
    assert 'paypal_environment") != "sandbox"' in text
    assert '"PROVIDE_EVIDENCE", "APPEAL"' in text
    assert "contains no immutable file references" in text


def test_read_gate_refuses_live_paypal_host():
    text = (ROOT / "scripts/integration_gate.py").read_text(encoding="utf-8")
    assert 'parsed.hostname != "api-m.sandbox.paypal.com"' in text
    assert "/v1/oauth2/token" in text
    assert "/v1/customer/disputes" in text
