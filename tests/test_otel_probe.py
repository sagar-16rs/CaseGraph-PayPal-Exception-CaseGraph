from __future__ import annotations

import importlib.util
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("backend.security.config")
pytest.importorskip("opentelemetry.exporter.otlp.proto.http.trace_exporter")

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("integration_live_gate_otel", ROOT / "scripts/integration_gate.py")
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


def test_otel_probe_sends_real_otlp_http(monkeypatch):
    seen = {"posts": 0, "content_type": ""}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("content-length", "0"))
            _ = self.rfile.read(length)
            seen["posts"] += 1
            seen["content_type"] = self.headers.get("content-type", "")
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        import backend.security.config as config_mod
        monkeypatch.setattr(
            config_mod,
            "security_config",
            SimpleNamespace(otel_enabled=True, otel_endpoint=f"http://127.0.0.1:{server.server_port}/v1/traces"),
        )
        detail = mod._otel_check()
        assert "exported successfully" in detail
        assert seen["posts"] == 1
        assert "protobuf" in seen["content_type"]
    finally:
        server.shutdown()
        server.server_close()
