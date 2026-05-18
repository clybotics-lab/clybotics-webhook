from __future__ import annotations

import re
from typing import Any, Optional

import requests

_NAME_FROM_TEXT = re.compile(
    r"(?:"
    r"আপনার\s*নাম|তোমার\s*নাম|নাম"
    r"|your\s*name|name|customer\s*name|full\s*name"
    r")\s*[:：\-]\s*([^\n\r,;|]{2,80})",
    re.IGNORECASE,
)


def extract_name_from_message_text(text: str) -> Optional[str]:
    t = (text or "").strip()
    if not t:
        return None
    m = _NAME_FROM_TEXT.search(t)
    if not m:
        return None
    name = m.group(1).strip()
    if len(name) < 2 or len(name) > 80:
        return None
    if "@" in name and " " not in name:
        return None
    return name


def telegram_display_name(update: dict[str, Any]) -> Optional[str]:
    msg = update.get("message") or update.get("edited_message")
    if not isinstance(msg, dict):
        return None
    user = msg.get("from")
    if not isinstance(user, dict):
        return None
    first = str(user.get("first_name") or "").strip()
    last = str(user.get("last_name") or "").strip()
    username = str(user.get("username") or "").strip()
    full = f"{first} {last}".strip()
    if full:
        return full[:80]
    if username:
        return f"@{username}"[:80]
    return None


def whatsapp_display_name(value: dict[str, Any]) -> Optional[str]:
    if not isinstance(value, dict):
        return None
    contacts = value.get("contacts")
    if isinstance(contacts, list):
        for c in contacts:
            if not isinstance(c, dict):
                continue
            profile = c.get("profile")
            if isinstance(profile, dict):
                name = str(profile.get("name") or "").strip()
                if name:
                    return name[:80]
    meta = value.get("metadata")
    if isinstance(meta, dict):
        name = str(meta.get("display_phone_number") or "").strip()
        if name and not name.isdigit():
            return name[:80]
    return None


def meta_messaging_sender_name(ev: dict[str, Any]) -> Optional[str]:
    if not isinstance(ev, dict):
        return None
    sender = ev.get("sender")
    if isinstance(sender, dict):
        for key in ("name", "username"):
            v = str(sender.get(key) or "").strip()
            if v:
                return v[:80]
    return None


def fetch_graph_user_name(user_id: str, access_token: str) -> Optional[str]:
    user_id = str(user_id or "").strip()
    access_token = str(access_token or "").strip()
    if not user_id or not access_token:
        return None
    try:
        r = requests.get(
            f"https://graph.facebook.com/v19.0/{user_id}",
            params={"fields": "name,first_name,last_name,username", "access_token": access_token},
            timeout=12,
        )
    except requests.RequestException:
        return None
    if r.status_code >= 400:
        return None
    data = r.json() if r.content else {}
    if not isinstance(data, dict):
        return None
    name = str(data.get("name") or "").strip()
    if name:
        return name[:80]
    first = str(data.get("first_name") or "").strip()
    last = str(data.get("last_name") or "").strip()
    full = f"{first} {last}".strip()
    if full:
        return full[:80]
    username = str(data.get("username") or "").strip()
    if username:
        return f"@{username}"[:80]
    return None


def pick_customer_name(
    *,
    platform: str,
    external_user_id: str,
    message_text: str,
    provided: Optional[str] = None,
    raw_for_storage: Optional[dict[str, Any]] = None,
    bot_meta: Optional[dict[str, Any]] = None,
    channel: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    if provided and str(provided).strip():
        return str(provided).strip()[:80]

    raw = raw_for_storage or {}
    plat = (platform or "").lower()

    if plat == "telegram":
        tg = raw.get("telegram")
        if isinstance(tg, dict):
            n = telegram_display_name(tg)
            if n:
                return n

    if plat == "whatsapp":
        value = raw.get("value")
        if isinstance(value, dict):
            n = whatsapp_display_name(value)
            if n:
                return n

    for key in ("facebook", "instagram"):
        block = raw.get(key)
        if isinstance(block, dict):
            n = meta_messaging_sender_name(block)
            if n:
                return n

    n = extract_name_from_message_text(message_text)
    if n:
        return n

    meta = bot_meta if isinstance(bot_meta, dict) else {}
    ch = channel if isinstance(channel, dict) else {}
    token = ""
    if plat in ("facebook", "instagram", "whatsapp"):
        token = str(
            meta.get("accessToken")
            or meta.get("access_token")
            or meta.get("instagramAccessToken")
            or meta.get("instagram_access_token")
            or ""
        ).strip()
    if plat in ("facebook", "instagram") and token and external_user_id:
        n = fetch_graph_user_name(external_user_id, token)
        if n:
            return n

    return None


def is_placeholder_name(name: Optional[str]) -> bool:
    n = (name or "").strip().lower()
    return not n or n in ("unknown visitor", "unknown", "visitor")
