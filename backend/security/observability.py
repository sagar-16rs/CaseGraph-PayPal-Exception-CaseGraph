from __future__ import annotations

import json
import logging
from typing import Any

_logger = logging.getLogger("casegraph.security")


def log_security_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    _logger.info(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))


def attach_span_attributes(**fields: Any) -> None:
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span is None:
            return
        for key, value in fields.items():
            if value is not None:
                span.set_attribute(f"casegraph.{key}", value)
    except Exception:
        # Observability must not become an availability dependency.
        return
