from pathlib import Path
from submission.submission import safe_public_file, scan_text_for_secrets


def test_public_file_filters_sensitive_artifacts(tmp_path):
    for rel in [
        '.env',
        'study_runs/participant.json',
        'uploads/a.pdf',
        '.git/config',
        'research/.tmp/qa/profile4/voices.json',
        'research/.baseline/pre-20261108/README.md',
        'pytest-cache-files-abc/temp.txt',
        '.omp/state.json',
    ]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('x')
        ok, _ = safe_public_file(p, tmp_path)
        assert ok is False, f"{rel} should be excluded"
    p = tmp_path / '.env.example'
    p.write_text('OPENAI_API_KEY=your_key\nPAYPAL_CLIENT_SECRET=\n')
    ok, _ = safe_public_file(p, tmp_path)
    assert ok is True


def test_secret_scanner_detects_private_key_api_key_and_paypal_secret():
    fake_key = '-----BEGIN ' + 'PRIVATE KEY-----'
    assert scan_text_for_secrets(fake_key)
    fake = 'OPENAI_API_KEY=' + 'sk-' + ('a' * 32)
    assert scan_text_for_secrets(fake)
    fake_paypal = 'PAYPAL_CLIENT_SECRET=' + 'E' + ('x' * 70)
    assert scan_text_for_secrets(fake_paypal)
    assert not scan_text_for_secrets('OPENAI_API_KEY=your_openai_api_key')
    assert not scan_text_for_secrets('PAYPAL_CLIENT_SECRET=CHANGE_ME')
    assert not scan_text_for_secrets('PAYPAL_CLIENT_SECRET=')
