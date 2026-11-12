"""Frontend contract tests.

These assert product invariants, not file layout: the workspace exposes the five
investigation surfaces, the browser never talks to PayPal or OpenAI directly, an
execution is bound to the stored approval hash rather than a browser-supplied
payload, and OIDC stays a session-scoped authorization-code flow.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "frontend/src"


def _read(relative: str) -> str:
    return (SRC / relative).read_text(encoding="utf-8")


APP = _read("App.tsx")
CLIENT = _read("api/client.ts")
AUTH = _read("auth/session.ts")
WORKSPACE = "\n".join(
    path.read_text(encoding="utf-8")
    for path in sorted(SRC.rglob("*.ts*"))
    if path.is_file()
)


def test_workspace_exposes_core_investigation_surfaces():
    for token in ["'overview'", "'graph'", "'evidence'", "'ai'", "'actions'"]:
        assert token in APP
    # Controls may live in focused components; the contract is that the workspace
    # as a whole exposes them.
    assert "Run analysis" in WORKSPACE
    assert "Approve immutable payload" in WORKSPACE
    assert "Execute approved action" in WORKSPACE
    assert "Read-only reconcile" in WORKSPACE


def test_workspace_renders_a_graph_not_only_a_list():
    assert "GraphCanvas" in APP
    assert (SRC / "components/GraphCanvas.tsx").is_file()
    assert "layoutGraph" in _read("lib/graph.ts")


def test_workspace_exposes_the_audit_explanation_export():
    assert "ExplanationPanel" in APP
    assert (SRC / "components/ExplanationPanel.tsx").is_file()
    assert "/explain" in CLIENT
    # A malformed payload must not blank the application.
    assert "ErrorBoundary" in _read("main.tsx")
    assert (SRC / "components/ErrorBoundary.tsx").is_file()


def test_browser_never_calls_paypal_or_openai_directly():
    source = WORKSPACE
    assert "api-m.paypal.com" not in source
    assert "api-m.sandbox.paypal.com" not in source
    assert "api.openai.com" not in source
    assert "/api/cases/" in CLIENT


def test_frontend_execution_uses_approval_hash_not_editable_payload():
    assert "approval_hash" not in APP.lower() or "latestAction.approval_hash" in APP
    assert "executeAction:(id:string,uid:string,hash:string)" in CLIENT
    assert "body:JSON.stringify({approval_hash:hash})" in CLIENT


def test_oidc_tokens_are_session_scoped_and_code_flow():
    assert "response_type: 'code'" in AUTH
    assert "window.sessionStorage" in AUTH
    assert "localStorage" not in AUTH
