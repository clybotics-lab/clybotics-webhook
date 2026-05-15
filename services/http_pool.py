from __future__ import annotations

from typing import Optional

import httpx

# Shared clients reuse TCP/TLS to Supabase, Dify, and Meta — cuts seconds of connect overhead per message.
_default_timeout = httpx.Timeout(60.0, connect=10.0)
_limits = httpx.Limits(max_keepalive_connections=24, max_connections=48, keepalive_expiry=45.0)

_rest_client: Optional[httpx.Client] = None
_external_client: Optional[httpx.Client] = None


def get_rest_client() -> httpx.Client:
    global _rest_client
    if _rest_client is None:
        _rest_client = httpx.Client(timeout=_default_timeout, limits=_limits)
    return _rest_client


def get_external_client() -> httpx.Client:
    global _external_client
    if _external_client is None:
        _external_client = httpx.Client(timeout=_default_timeout, limits=_limits)
    return _external_client
