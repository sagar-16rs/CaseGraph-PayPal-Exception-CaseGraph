from __future__ import annotations

from contextvars import ContextVar, Token

from backend.security.domain import Actor

_current_actor: ContextVar[Actor | None] = ContextVar("casegraph_current_actor", default=None)


def get_current_actor() -> Actor | None:
    return _current_actor.get()


def require_current_actor() -> Actor:
    actor = _current_actor.get()
    if actor is None:
        raise RuntimeError("No authenticated actor is bound to this request context")
    return actor


def bind_actor(actor: Actor | None) -> Token:
    return _current_actor.set(actor)


def reset_actor(token: Token) -> None:
    _current_actor.reset(token)
