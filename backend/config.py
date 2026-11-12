from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_environment(path: Path | None = None) -> None:
    """Load `.env` from the repository root, without overriding real variables.

    The documented setup is "copy `.env.example` to `.env`, then run uvicorn". Until
    this call existed the file was silently ignored: every value had to be exported
    by hand, and a correctly filled `.env` produced a process with no credentials.
    `override=False` keeps an explicit shell/CI environment authoritative.
    """
    target = path or _ENV_FILE
    if target.is_file():
        load_dotenv(target, override=False)


load_environment()


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None else int(value)


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./.data/casegraph.db")
    paypal_base_url: str = os.getenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com").rstrip("/")
    paypal_client_id: str = os.getenv("PAYPAL_CLIENT_ID", "")
    paypal_client_secret: str = os.getenv("PAYPAL_CLIENT_SECRET", "")
    paypal_webhook_id: str = os.getenv("PAYPAL_WEBHOOK_ID", "")
    paypal_webhook_verify: bool = _bool("PAYPAL_WEBHOOK_VERIFY", False)
    paypal_timeout_seconds: int = _int("PAYPAL_TIMEOUT_SECONDS", 30)
    # Evidence uploads legitimately need a longer budget than a JSON call; it is a
    # setting rather than a literal inside the transport.
    paypal_multipart_timeout_seconds: int = _int("PAYPAL_MULTIPART_TIMEOUT_SECONDS", 60)
    # `live` talks to PAYPAL_BASE_URL. `simulated` uses the in-process
    # deterministic sandbox so the product can be demonstrated without
    # credentials; it is refused when CASEGRAPH_ENV=production.
    paypal_transport: str = os.getenv("CASEGRAPH_PAYPAL_TRANSPORT", "live").strip().lower()
    simulation_state_path: str = os.getenv(
        "CASEGRAPH_SIMULATION_STATE", ".data/simulated-paypal.json"
    )
    simulated_fault: str = os.getenv("CASEGRAPH_SIMULATED_FAULT", "none").strip().lower()

    openai_api_key: str = os.getenv("OPENAI_API_KEY", "") or os.getenv("DEEPSEEK_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "") or (
        os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        if os.getenv("DEEPSEEK_API_KEY") and not os.getenv("OPENAI_API_KEY")
        else ""
    )
    openai_model: str = os.getenv("OPENAI_MODEL", "") or os.getenv("DEEPSEEK_MODEL", "") or "gpt-5.6"
    ai_timeout_seconds: int = _int("AI_TIMEOUT_SECONDS", 60)
    ai_max_output_tokens: int = _int("AI_MAX_OUTPUT_TOKENS", 6000)
    ai_max_bundle_chars: int = _int("AI_MAX_BUNDLE_CHARS", 200000)
    # `auto` uses OpenAI/DeepSeek when a key is configured and otherwise falls back
    # to the deterministic reference reasoner outside production.
    ai_provider: str = os.getenv("CASEGRAPH_AI_PROVIDER", "auto").strip().lower()
    # `auto` | `responses` | `chat_completions`. `auto` uses `/v1/responses` on
    # OpenAI and switches to `/v1/chat/completions` for DeepSeek or gateways that
    # do not implement the Responses API.
    ai_api_mode: str = os.getenv("CASEGRAPH_AI_API_MODE", "auto").strip().lower()

    worker_lease_seconds: int = _int("CASEGRAPH_WORKER_LEASE_SECONDS", 60)
    worker_max_attempts: int = _int("CASEGRAPH_WORKER_MAX_ATTEMPTS", 8)
    worker_poll_seconds: int = _int("CASEGRAPH_WORKER_POLL_SECONDS", 2)
    worker_backoff_base_seconds: int = _int("CASEGRAPH_WORKER_BACKOFF_BASE_SECONDS", 5)
    worker_backoff_cap_seconds: int = _int("CASEGRAPH_WORKER_BACKOFF_CAP_SECONDS", 300)
    dispute_lock_timeout_seconds: int = _int("CASEGRAPH_DISPUTE_LOCK_TIMEOUT_SECONDS", 30)

    @property
    def database_backend(self) -> str:
        return "postgresql" if self.database_url.startswith(("postgresql://", "postgresql+")) else "sqlite"

    @property
    def is_paypal_sandbox(self) -> bool:
        return self.paypal_base_url == "https://api-m.sandbox.paypal.com"

    @property
    def simulated_paypal(self) -> bool:
        return self.paypal_transport == "simulated"

    def validate_paypal_sandbox(self, *, require_webhook: bool = True) -> None:
        if self.simulated_paypal:
            return
        if not self.is_paypal_sandbox:
            raise RuntimeError("This verification path is sandbox-only; configure the PayPal sandbox endpoint.")
        if not self.paypal_client_id or not self.paypal_client_secret:
            raise RuntimeError("PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET are required")
        if require_webhook and not self.paypal_webhook_id:
            raise RuntimeError("PAYPAL_WEBHOOK_ID is required")


settings = Settings()
