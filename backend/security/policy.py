from __future__ import annotations

import re
from dataclasses import dataclass

from backend.security.domain import Role


@dataclass(frozen=True, slots=True)
class RouteRule:
    method: str
    pattern: re.Pattern[str]
    role: Role | None = None
    public: bool = False
    deny: bool = False
    max_body_bytes: int | None = None
    requests_per_minute: int = 120

    def matches(self, method: str, path: str) -> bool:
        return self.method == method.upper() and bool(self.pattern.fullmatch(path))


def _r(method: str, pattern: str, **kwargs) -> RouteRule:
    return RouteRule(method=method, pattern=re.compile(pattern), **kwargs)


# First match wins. High-risk/specific routes must precede broad read rules.
RULES: tuple[RouteRule, ...] = (
    _r("GET", r"/health", public=True, requests_per_minute=60),
    _r("GET", r"/ready", public=True, requests_per_minute=60),
    _r("POST", r"/api/webhooks/paypal", public=True, requests_per_minute=240),
    _r("GET", r"/api/auth/me", role=Role.VIEWER, requests_per_minute=120),
    # CORS preflights contain no bearer token. The existing CORS middleware still
    # validates the requested origin/method/headers; the gateway only inventories
    # and rate-limits them so cross-origin deployments can function.
    _r("OPTIONS", r"/api/.*", public=True, requests_per_minute=120),

    # Explicitly retire the legacy one-shot write path in hardened mode.
    _r("POST", r"/api/cases/[^/]+/actions/send-message", deny=True),

    _r("GET", r"/api/ops(?:/.*)?", role=Role.ADMIN, requests_per_minute=60),
    _r("POST", r"/api/ops(?:/.*)?", role=Role.ADMIN, requests_per_minute=30),

    _r("POST", r"/api/cases/sync/[^/]+", role=Role.ANALYST, requests_per_minute=30),
    _r("POST", r"/api/cases/[^/]+/intake", role=Role.ANALYST, requests_per_minute=30),
    _r("POST", r"/api/cases/[^/]+/files", role=Role.ANALYST, requests_per_minute=20),
    _r("GET", r"/api/cases/[^/]+/files", role=Role.VIEWER, requests_per_minute=120),
    _r("GET", r"/api/cases/[^/]+/files/[^/]+", role=Role.VIEWER, requests_per_minute=120),

    _r("POST", r"/api/cases/[^/]+/ai/analyze", role=Role.ANALYST, requests_per_minute=10),
    _r("POST", r"/api/cases/[^/]+/ai/analyses/[^/]+/safety", role=Role.ANALYST, requests_per_minute=30),
    # Read-only explanation export. Listed before the generic case-read rule so it
    # keeps its own bucket rather than sharing the board-wide read limit.
    _r("GET", r"/api/cases/[^/]+/ai/analyses/[^/]+/explain", role=Role.VIEWER, requests_per_minute=120),
    _r("POST", r"/api/cases/[^/]+/graphs", role=Role.ANALYST, requests_per_minute=30),

    _r("POST", r"/api/cases/[^/]+/actions/approve", role=Role.APPROVER, requests_per_minute=20),
    _r("POST", r"/api/cases/[^/]+/actions/[^/]+/execute", role=Role.APPROVER, requests_per_minute=20),
    _r("POST", r"/api/cases/[^/]+/actions/[^/]+/reconcile", role=Role.APPROVER, requests_per_minute=20),

    # All case-scoped reads are read-only roles after the write rules above.
    _r("GET", r"/api/cases(?:/.*)?", role=Role.VIEWER, requests_per_minute=180),
)


def match_rule(method: str, path: str) -> RouteRule | None:
    for rule in RULES:
        if rule.matches(method, path):
            return rule
    return None
