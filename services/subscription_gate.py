from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from services.supabase_client import SupabaseRest


def _parse_expires_at(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def bot_subscription_is_active(db: SupabaseRest, workspace_id: str, bot_id: str) -> bool:
    row = db.get_bot_subscription_row(workspace_id, bot_id)
    if not row:
        return False
    status = str(row.get("status") or "").strip().lower()
    if status not in ("active", "trial"):
        return False
    exp = _parse_expires_at(row.get("expires_at"))
    if exp is None:
        return True
    return exp > datetime.now(timezone.utc)


def channel_is_connected(channel: Optional[dict[str, Any]]) -> bool:
    if not channel:
        return False
    return str(channel.get("status") or "").strip().lower() == "connected"


def should_run_bot_auto_reply(
    db: SupabaseRest,
    workspace_id: str,
    bot_id: str,
    channel: Optional[dict[str, Any]],
) -> bool:
    return channel_is_connected(channel) and bot_subscription_is_active(db, workspace_id, bot_id)
