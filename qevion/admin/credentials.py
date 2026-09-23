"""CredentialResolver (§39.6 QV-CRED, ADR-0002 D9): env → admin store → ephemeral UI key.

Rules enforced here:
- Values are never logged, never written to disk by the ephemeral path, never included in events (only `CredentialScope`).
- Ephemeral keys expire; reading past expiry returns None.
- `fingerprint()` is the only representation allowed to leave this module (last 4 chars, prefixed).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from qevion.contracts.control import CredentialScope, CredentialSource

_ENV_KEYS: dict[str, str] = {
    "openai_realtime": "OPENAI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini_live": "GEMINI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "typesafe": "TYPESAFE_API_KEY",
}


def fingerprint(value: str) -> str:
    return f"…{value[-4:]}" if len(value) >= 8 else "…"


@dataclass
class _Ephemeral:
    value: str
    expires_at: float


@dataclass
class EnvAdminEphemeralResolver:
    """Default resolver. `admin_store` is an in-memory dict in the POC (A7)."""

    admin_store: dict[tuple[str | None, str], str] = field(default_factory=dict)  # (tenant_id|None, provider) -> key
    _ephemeral: dict[tuple[str | None, str], _Ephemeral] = field(default_factory=dict)
    ephemeral_ttl_seconds: int = 3600
    env: dict[str, str] | None = None  # injectable for tests; defaults to os.environ
    scopes_opened: list[CredentialScope] = field(default_factory=list)

    def _env(self) -> dict[str, str]:
        return self.env if self.env is not None else dict(os.environ)

    # --- admin operations (never log values) ---------------------------------------------
    def set_admin(self, provider: str, value: str, tenant_id: str | None = None) -> CredentialScope:
        self.admin_store[(tenant_id, provider)] = value
        return self._scope(provider, CredentialSource.ADMIN_STORE, tenant_id, value)

    def set_ephemeral(
        self, provider: str, value: str, tenant_id: str | None = None, ttl_seconds: int | None = None
    ) -> CredentialScope:
        ttl = ttl_seconds or self.ephemeral_ttl_seconds
        self._ephemeral[(tenant_id, provider)] = _Ephemeral(value=value, expires_at=time.time() + ttl)
        return self._scope(provider, CredentialSource.EPHEMERAL_UI, tenant_id, value)

    def clear_ephemeral(self, provider: str | None = None, tenant_id: str | None = None) -> int:
        keys = [
            k
            for k in self._ephemeral
            if (provider is None or k[1] == provider) and (tenant_id is None or k[0] == tenant_id)
        ]
        for k in keys:
            del self._ephemeral[k]
        return len(keys)

    # --- resolution -----------------------------------------------------------------
    def resolve(self, provider: str, tenant_id: str | None) -> tuple[str | None, CredentialSource]:
        env_key = _ENV_KEYS.get(provider, f"{provider.upper()}_API_KEY")
        v = self._env().get(env_key, "").strip()
        if v:
            return v, CredentialSource.ENV
        for tid in (tenant_id, None):
            v2 = self.admin_store.get((tid, provider))
            if v2:
                return v2, CredentialSource.ADMIN_STORE
        for tid in (tenant_id, None):
            e = self._ephemeral.get((tid, provider))
            if e:
                if e.expires_at < time.time():
                    del self._ephemeral[(tid, provider)]
                    continue
                return e.value, CredentialSource.EPHEMERAL_UI
        return None, CredentialSource.NONE

    def status(self, provider: str, tenant_id: str | None) -> CredentialScope:
        value, source = self.resolve(provider, tenant_id)
        return CredentialScope(
            provider=provider, source=source, tenant_id=tenant_id, fingerprint=fingerprint(value) if value else None
        )

    def _scope(self, provider: str, source: CredentialSource, tenant_id: str | None, value: str) -> CredentialScope:
        s = CredentialScope(provider=provider, source=source, tenant_id=tenant_id, fingerprint=fingerprint(value))
        self.scopes_opened.append(s)
        return s
