from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from services.http_pool import get_external_client


def _meta_error_needs_human_agent_tag(raw: str) -> bool:
    lower = raw.lower()
    if any(
        token in lower
        for token in (
            "outside",
            "24 hour",
            "24-hour",
            "messaging window",
            "window has expired",
            "(#10)",
            "error_subcode\":2018278",
            "subcode\":2018278",
            "551",
        )
    ):
        return True
    return False


def _friendly_meta_send_error(raw: str) -> str:
    try:
        data = json.loads(raw)
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            msg = str(err.get("message") or "").strip()
            if msg:
                low = msg.lower()
                if "cannot tag" in low or "approval" in low:
                    return (
                        "Meta rejected the Human Agent message tag (your app may not have approval). "
                        "If the customer messaged within the last 24 hours, try again — we now send normal replies first. "
                        "Otherwise ask them to message your Page again, or request Human Agent permission in Meta App Review."
                    )
                return msg
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return raw[:500]


def send_facebook_agent_tagged_text(page_id: str, page_access_token: str, recipient_psid: str, text: str) -> Optional[str]:
    """Human/agent reply from dashboard (MESSAGE_TAG + HUMAN_AGENT)."""
    url = f"https://graph.facebook.com/v19.0/{page_id}/messages"
    try:
        r = get_external_client().post(
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
        return _friendly_meta_send_error(r.text[:2000])
    return None


def send_facebook_text(page_id: str, page_access_token: str, recipient_psid: str, text: str) -> Optional[str]:
    url = f"https://graph.facebook.com/v19.0/{page_id}/messages"
    try:
        r = get_external_client().post(
            url,
            params={"access_token": page_access_token},
            json={"recipient": {"id": recipient_psid}, "message": {"text": text[:2000]}, "messaging_type": "RESPONSE"},
            timeout=30.0,
        )
    except Exception as e:  # noqa: BLE001
        return str(e)
    if r.status_code >= 400:
        return _friendly_meta_send_error(r.text[:2000])
    return None


def send_facebook_manual_reply(
    page_id: str, page_access_token: str, recipient_psid: str, text: str
) -> Optional[str]:
    """
    Dashboard / agent manual reply inside Meta's standard messaging window (RESPONSE).
    We do not use MESSAGE_TAG + HUMAN_AGENT here — most apps lack that approval and Meta
  returns (#100) Cannot tag messages with approval.
    """
    err = send_facebook_text(page_id, page_access_token, recipient_psid, text)
    if err is None:
        return None
    if _meta_error_needs_human_agent_tag(err):
        return (
            "This conversation is outside Meta's 24-hour reply window. "
            "Ask the customer to send a new message to your Page, then reply again from Logs."
        )
    return err


def send_telegram_text(bot_token: str, chat_id: str, text: str) -> Optional[str]:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        r = get_external_client().post(url, json={"chat_id": chat_id, "text": text[:4096]}, timeout=30.0)
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
        r = get_external_client().post(
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
