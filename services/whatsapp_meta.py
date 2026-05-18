from __future__ import annotations

from typing import Any, Optional

import requests


def fetch_whatsapp_phone_profile(phone_number_id: str, access_token: str) -> dict[str, str]:
    """Resolve display phone + verified business name from Meta Graph."""
    phone_number_id = str(phone_number_id or "").strip()
    access_token = str(access_token or "").strip()
    if not phone_number_id or not access_token:
        return {}
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}"
    try:
        r = requests.get(
            url,
            params={"fields": "display_phone_number,verified_name", "access_token": access_token},
            timeout=15,
        )
    except requests.RequestException:
        return {}
    if r.status_code >= 400:
        return {}
    data = r.json() if r.content else {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    display = str(data.get("display_phone_number") or "").strip()
    verified = str(data.get("verified_name") or "").strip()
    if display:
        out["display_phone"] = display
    if verified:
        out["verified_name"] = verified
    return out


def whatsapp_metadata_from_webhook_body(body: dict[str, Any]) -> list[dict[str, str]]:
    """Collect phone_number_id + display_phone_number from Meta webhook payloads."""
    found: list[dict[str, str]] = []
    if not isinstance(body, dict):
        return found
    for entry in body.get("entry", []) if isinstance(body.get("entry"), list) else []:
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes", []) or []:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            meta = value.get("metadata")
            if not isinstance(meta, dict):
                continue
            phone_id = str(meta.get("phone_number_id", "")).strip()
            display = str(meta.get("display_phone_number", "")).strip()
            if phone_id:
                found.append({"phone_number_id": phone_id, "display_phone": display})
    return found
