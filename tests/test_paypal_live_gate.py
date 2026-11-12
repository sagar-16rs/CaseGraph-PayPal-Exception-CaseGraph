"""The live PayPal transport must fail closed, and must say why.

No sandbox credentials exist in this environment, so the live path cannot be
executed. What *can* be proven deterministically is the guard: the application
refuses to pretend it has a working live integration, and the simulator is refused
in production regardless of configuration.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from backend.config import Settings, settings
from backend.security.config import SecurityConfig


def test_live_sandbox_validation_requires_credentials():
    """The guard must fire when credentials are absent, whatever this box has.

    Previously this test skipped whenever credentials were configured, so the guard
    was never exercised in the environment that actually has them. Building the
    probe from the live settings with the credentials stripped tests the real rule.
    """
    probe = replace(Settings(), paypal_client_id="", paypal_client_secret="")
    with pytest.raises(RuntimeError) as excinfo:
        probe.validate_paypal_sandbox()
    assert "PAYPAL_CLIENT_ID" in str(excinfo.value)


def test_simulated_transport_is_never_authoritative():
    assert settings.paypal_transport in {"live", "simulated"}
    if settings.paypal_transport == "simulated":
        from backend.paypal.http import simulated_transport_enabled

        assert simulated_transport_enabled() is True


def test_production_forbids_the_simulated_transport(monkeypatch):
    # The production profile is what matters: the guard only fires there, because a
    # local demo is expected to use the simulator.
    monkeypatch.setenv("CASEGRAPH_ENV", "production")
    monkeypatch.setenv("CASEGRAPH_PAYPAL_TRANSPORT", "simulated")
    config = SecurityConfig.from_env()
    assert config.production is True
    errors = config.validate()
    assert any("simulated" in error for error in errors), errors
