from __future__ import annotations

from typing import Any, Optional

import httpx

from config import SUPABASE_ANON_KEY, SUPABASE_URL


def fetch_user_from_jwt(jwt: str) -> Optional[dict[str, Any]]:
    jwt = (jwt or "").strip()
    if not jwt:
        return None
    base = SUPABASE_URL.rstrip("/")
    r = httpx.get(
        f"{base}/auth/v1/user",
        headers={"Authorization": f"Bearer {jwt}", "apikey": SUPABASE_ANON_KEY},
        timeout=20.0,
    )
    if r.status_code != 200:
        return None
    body = r.json()
    user = body.get("user") if isinstance(body, dict) else None
    return user if isinstance(user, dict) else None
