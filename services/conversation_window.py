from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

META_MESSAGING_WINDOW = timedelta(hours=24)


def meta_conversation_window_payload(last_customer_at: Optional[str]) -> dict[str, Any]:
    """24-hour customer care window (WhatsApp, Messenger, Instagram DM)."""
    now = datetime.now(timezone.utc)
    if not last_customer_at:
        return {
            "has_customer_message": False,
            "window_open": False,
            "is_new_contact": True,
            "last_customer_message_at": None,
            "window_expires_at": None,
            "seconds_remaining": 0,
        }
    try:
        s = last_customer_at.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        started = datetime.fromisoformat(s)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
    except ValueError:
        return {
            "has_customer_message": True,
            "window_open": False,
            "is_new_contact": False,
            "last_customer_message_at": last_customer_at,
            "window_expires_at": None,
            "seconds_remaining": 0,
        }
    expires = started + META_MESSAGING_WINDOW
    remaining = max(0, int((expires - now).total_seconds()))
    return {
        "has_customer_message": True,
        "window_open": remaining > 0,
        "is_new_contact": False,
        "last_customer_message_at": started.isoformat(),
        "window_expires_at": expires.isoformat(),
        "seconds_remaining": remaining,
    }
