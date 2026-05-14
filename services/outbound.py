from __future__ import annotations

from typing import Any, Optional

import httpx


def send_facebook_agent_tagged_text(page_id: str, page_access_token: str, recipient_psid: str, text: str) -> Optional[str]:
    """Human/agent reply from dashboard (MESSAGE_TAG + HUMAN_AGENT)."""
    url = f"https://graph.facebook.com/v19.0/{page_id}/messages"
    try:
        r = httpx.post(
            url,
            params={"access_token": page_access_token},
            json={
                "recipient": {"id": recipient_psid},
                "message": {"text": text[:2000]},
                "messaging_type": "MESSAGE_TAG",
                "tag": "HUMAN_AGENT",
            },
            timeout=30.0,
        )
    except Exception as e:  # noqa: BLE001
        return str(e)
    if r.status_code >= 400:
        return r.text[:500]
    return None


def send_facebook_text(page_id: str, page_access_token: str, recipient_psid: str, text: str) -> Optional[str]:
    url = f"https://graph.facebook.com/v19.0/{page_id}/messages"
    try:
        r = httpx.post(
            url,
            params={"access_token": page_access_token},
            json={"recipient": {"id": recipient_psid}, "message": {"text": text[:2000]}, "messaging_type": "RESPONSE"},
            timeout=30.0,
        )
    except Exception as e:  # noqa: BLE001
        return str(e)
    if r.status_code >= 400:
        return r.text[:500]
    return None


def send_telegram_text(bot_token: str, chat_id: str, text: str) -> Optional[str]:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        r = httpx.post(url, json={"chat_id": chat_id, "text": text[:4096]}, timeout=30.0)
    except Exception as e:  # noqa: BLE001
        return str(e)
    if r.status_code >= 400:
        return r.text[:500]
    data = r.json()
    if isinstance(data, dict) and not data.get("ok"):
        return str(data)[:500]
    return None


def send_whatsapp_text(phone_number_id: str, wa_access_token: str, to_wa_id: str, text: str) -> Optional[str]:
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "text",
        "text": {"body": text[:4096]},
    }
    try:
        r = httpx.post(
            url,
            headers={"Authorization": f"Bearer {wa_access_token}"},
            json=payload,
            timeout=30.0,
        )
    except Exception as e:  # noqa: BLE001
        return str(e)
    if r.status_code >= 400:
        return r.text[:500]
    return None
