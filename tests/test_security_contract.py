from __future__ import annotations

from pathlib import Path


def test_action_engine_binds_authenticated_actor_and_exact_file_hashes():
    root = Path(__file__).resolve().parents[1]
    service = (root / "backend/services/actions.py").read_text(encoding="utf-8")
    schemas = (root / "backend/actions/schemas.py").read_text(encoding="utf-8")
    assert 'req = req.model_copy(update={"approved_by": actor.subject})' in service
    assert "resolve_action_files(case_id, extract_file_refs(req.payload))" in service
    assert "build_paypal_evidence_payload" in service
    assert "class EvidenceFileRef" in schemas
    assert "sha256" in schemas


def test_no_security_http_manual_ambiguity_override_added():
    root = Path(__file__).resolve().parents[1]
    for path in (root / "backend").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "reconcile/manual" not in text


def test_rate_limit_bucket_does_not_use_raw_resource_path():
    root = Path(__file__).resolve().parents[1]
    middleware = (root / "backend/security/middleware.py").read_text(encoding="utf-8")
    assert "rule.pattern.pattern" in middleware
    assert 'rate_key = f"{method}:{path}:{identity}"' not in middleware


def test_browser_auth_uses_code_flow_and_no_localstorage():
    root = Path(__file__).resolve().parents[1]
    session = (root / "frontend/src/auth/session.ts").read_text(encoding="utf-8")
    assert "response_type: 'code'" in session
    assert "window.sessionStorage" in session
    assert "localStorage" not in session
    assert "signinRedirect" in session
    gate = (root / "frontend/src/auth/AuthGate.tsx").read_text(encoding="utf-8")
    assert "addAccessTokenExpired" in gate
    assert "removeAccessTokenExpired" in gate


def test_cors_preflight_is_in_hardened_route_inventory():
    root = Path(__file__).resolve().parents[1]
    policy = (root / "backend/security/policy.py").read_text(encoding="utf-8")
    assert '_r("OPTIONS", r"/api/.*", public=True' in policy
