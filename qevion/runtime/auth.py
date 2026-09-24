"""Operator access guard (F-07, OPS 5.5 audit).

Threat fixed: every route was unauthenticated and CORS was `*` — anyone who could reach the URL could replace or
delete the provider key (`/api/admin/test-key`), read the global event log, or open sessions on the operator's
provider account. Verified by the audit with plain curl.

Model (smallest safe change, additive):
* `QEVION_ADMIN_TOKEN` set  → every `/api/*` and `/ws/*` request needs the token, either
  `Authorization: Bearer <token>` / `X-QEVION-Token: <token>` (scripts) or the HttpOnly `qevion_session` cookie
  set by `POST /api/auth/login` (browser; also sent automatically on same-origin WebSockets).
  Open paths: `/api/health`, `/api/auth/*`, and the static UI (so the login prompt can load).
* `QEVION_ADMIN_TOKEN` unset → development mode: requests are allowed, `/api/health` reports
  `auth: "disabled"` and the UI shows a warning banner. Nothing is silently "secure".

Compare with `hmac.compare_digest`; the token is never logged or echoed. The cookie holds an HMAC of the token,
not the token itself, so it is useless if the token is rotated.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Awaitable, Callable, MutableMapping
from http.cookies import SimpleCookie
from typing import Any

COOKIE = "qevion_session"
OPEN_PREFIXES = ("/api/health", "/api/auth/")
GUARDED_PREFIXES = ("/api/", "/ws/")

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def configured_token() -> str | None:
    t = os.environ.get("QEVION_ADMIN_TOKEN", "").strip()
    return t or None


def tenant_tokens() -> dict[str, str]:
    """F-08: optional read-only tenant tokens `QEVION_TENANT_TOKENS="tenant_a:tokA,tenant_b:tokB"` → {token: tenant}.
    A tenant token may only read its own tenant's sessions/events; everything else is 403."""
    out: dict[str, str] = {}
    for part in os.environ.get("QEVION_TENANT_TOKENS", "").split(","):
        tenant, sep, tok = part.strip().partition(":")
        if sep and tenant.strip() and len(tok.strip()) >= 16:
            out[tok.strip()] = tenant.strip()
    return out


TENANT_READ_PREFIXES = ("/api/sessions", "/api/events")


def presented_token(scope: Scope) -> str | None:
    h = _headers(scope)
    auth = h.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    x = h.get("x-qevion-token")
    return x.strip() if x else None


def tenant_for(scope: Scope) -> str | None:
    tok = presented_token(scope)
    if not tok:
        return None
    for known, tenant in tenant_tokens().items():
        if hmac.compare_digest(tok, known):
            return tenant
    return None


def cookie_value(token: str) -> str:
    return hmac.new(token.encode(), b"qevion-session-v1", hashlib.sha256).hexdigest()


def _headers(scope: Scope) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}


def request_is_authorized(scope: Scope, token: str) -> bool:
    h = _headers(scope)
    auth = h.get("authorization", "")
    if auth.lower().startswith("bearer ") and hmac.compare_digest(auth[7:].strip(), token):
        return True
    x = h.get("x-qevion-token")
    if x and hmac.compare_digest(x.strip(), token):
        return True
    raw = h.get("cookie")
    if raw:
        c: SimpleCookie = SimpleCookie()
        try:
            c.load(raw)
        except Exception:  # noqa: BLE001 — malformed cookie header → treat as absent
            return False
        m = c.get(COOKIE)
        if m is not None and hmac.compare_digest(m.value, cookie_value(token)):
            return True
    return False


def needs_guard(path: str) -> bool:
    if any(path.startswith(p) for p in OPEN_PREFIXES):
        return False
    return any(path.startswith(p) for p in GUARDED_PREFIXES)


class OperatorAuthMiddleware:
    """Pure ASGI (covers HTTP *and* WebSocket). Reads the token per request so tests/ops can rotate it."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        kind = scope.get("type")
        if kind not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        token = configured_token()
        path = str(scope.get("path") or "")
        scope.setdefault("state", {})["qevion_tenant"] = None  # None = operator (all tenants)
        if needs_guard(path) and (tenant := tenant_for(scope)) is not None:
            # F-08: tenant tokens are read-only and scoped; the route handlers filter by this tenant
            if kind == "http" and scope.get("method") == "GET" and path.startswith(TENANT_READ_PREFIXES):
                scope["state"]["qevion_tenant"] = tenant
                await self.app(scope, receive, send)
                return
            await self._deny(kind, receive, send, 403, "forbidden: tenant token is read-only (sessions/events)")
            return
        if token is None or not needs_guard(path) or request_is_authorized(scope, token):
            await self.app(scope, receive, send)
            return
        await self._deny(kind, receive, send, 401, "unauthorized: operator token required (QEVION_ADMIN_TOKEN)")

    @staticmethod
    async def _deny(kind: str, receive: Receive, send: Send, status: int, detail: str) -> None:
        if kind == "websocket":
            # must accept the handshake message before closing with an app code
            await receive()
            await send({"type": "websocket.close", "code": 4000 + status, "reason": detail.split(":")[0]})
            return
        body = ('{"detail":"' + detail + '"}').encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")],
            }
        )
        await send({"type": "http.response.body", "body": body})


def cors_origins() -> list[str]:
    """Explicit allow-list only (default: none → same-origin UI works, cross-origin pages are refused)."""
    raw = os.environ.get("QEVION_CORS_ORIGINS", "")
    return [o.strip() for o in raw.split(",") if o.strip() and o.strip() != "*"]


__all__ = [
    "COOKIE",
    "OperatorAuthMiddleware",
    "configured_token",
    "cookie_value",
    "cors_origins",
    "needs_guard",
    "request_is_authorized",
    "tenant_for",
    "tenant_tokens",
]
