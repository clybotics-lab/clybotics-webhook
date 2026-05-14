from __future__ import annotations

from typing import Any, Optional, Tuple

import httpx

from config import SUPABASE_ANON_KEY, SUPABASE_URL


def _user_from_auth_user_json(body: Any) -> Optional[dict[str, Any]]:
    """
    GET /auth/v1/user may return either:
    - { "user": { "id": ..., ... } }  (nested)
    - { "id": ..., "aud": ..., ... } (flat user object)
    """
    if not isinstance(body, dict):
        return None
    nested = body.get("user")
    if isinstance(nested, dict) and nested.get("id") is not None:
        return nested
    if body.get("id") is None:
        return None
    if any(
        k in body
        for k in ("aud", "role", "email", "phone", "app_metadata", "user_metadata", "created_at")
    ):
        return body
    return None


def fetch_user_from_jwt(jwt: str) -> Optional[dict[str, Any]]:
    """Backward-compatible: returns user or None. Prefer verify_supabase_session_jwt for debugging."""
    user, _reason = verify_supabase_session_jwt(jwt)
    return user


def verify_supabase_session_jwt(jwt: str) -> Tuple[Optional[dict[str, Any]], str]:
    """
    Validates a Supabase access token via GET /auth/v1/user.
    Returns (user_dict_or_None, reason_code). reason_code is always set (use for JSON error responses).
    """
    jwt = (jwt or "").strip()
    if not jwt:
        return None, "empty_jwt"
    base = SUPABASE_URL.rstrip("/")
    url = f"{base}/auth/v1/user"
    try:
        r = httpx.get(
            url,
            headers={"Authorization": f"Bearer {jwt}", "apikey": SUPABASE_ANON_KEY},
            timeout=20.0,
        )
    except httpx.RequestError:
        return None, "supabase_auth_unreachable"
    if r.status_code in (401, 403):
        return None, "supabase_rejected_session"
    if r.status_code != 200:
        return None, f"supabase_auth_http_{r.status_code}"
    try:
        body = r.json()
    except ValueError:
        return None, "supabase_auth_invalid_json"
    user = _user_from_auth_user_json(body)
    if user is None:
        return None, "supabase_user_missing"
    uid = user.get("id")
    if uid is None or str(uid).strip() == "":
        return None, "supabase_user_id_missing"
    return user, "ok"
