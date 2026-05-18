from __future__ import annotations

import json
import re
from typing import Any, Optional

from services.http_pool import get_external_client

_TEMPLATE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,512}$")


def normalize_template_name(name: str) -> str:
    s = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s[:512]


def fetch_waba_id(phone_number_id: str, access_token: str) -> Optional[str]:
    phone_number_id = str(phone_number_id or "").strip()
    access_token = str(access_token or "").strip()
    if not phone_number_id or not access_token:
        return None
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}"
    try:
        r = get_external_client().get(
            url,
            params={"fields": "whatsapp_business_account", "access_token": access_token},
            timeout=20.0,
        )
    except Exception:  # noqa: BLE001
        return None
    if r.status_code >= 400:
        return None
    data = r.json() if r.content else {}
    if not isinstance(data, dict):
        return None
    waba = data.get("whatsapp_business_account")
    if isinstance(waba, dict):
        wid = str(waba.get("id") or "").strip()
        return wid or None
    if isinstance(waba, str) and waba.strip():
        return waba.strip()
    return None


def _friendly_graph_error(raw: str) -> str:
    try:
        data = json.loads(raw)
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])[:500]
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return raw[:500]


def list_message_templates(waba_id: str, access_token: str) -> tuple[list[dict[str, Any]], Optional[str]]:
    url = f"https://graph.facebook.com/v19.0/{waba_id}/message_templates"
    try:
        r = get_external_client().get(
            url,
            params={
                "access_token": access_token,
                "limit": "100",
                "fields": "id,name,status,language,category,components,rejected_reason",
            },
            timeout=30.0,
        )
    except Exception as e:  # noqa: BLE001
        return [], str(e)
    if r.status_code >= 400:
        return [], _friendly_graph_error(r.text[:2000])
    data = r.json() if r.content else {}
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return [], None
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        body = ""
        for comp in row.get("components") or []:
            if isinstance(comp, dict) and comp.get("type") == "BODY":
                body = str(comp.get("text") or "")
                break
        out.append(
            {
                "id": str(row.get("id") or ""),
                "name": str(row.get("name") or ""),
                "status": str(row.get("status") or "UNKNOWN").upper(),
                "language": str(row.get("language") or ""),
                "category": str(row.get("category") or ""),
                "body_preview": body[:500],
                "rejected_reason": str(row.get("rejected_reason") or "") or None,
            }
        )
    return out, None


def create_message_template(
    waba_id: str,
    access_token: str,
    *,
    name: str,
    language: str,
    category: str,
    body_text: str,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    tname = normalize_template_name(name)
    if not tname or not _TEMPLATE_NAME_RE.match(tname):
        return None, "Template name must be lowercase letters, numbers, and underscores (e.g. order_update)."
    lang = (language or "en_US").strip() or "en_US"
    cat = (category or "UTILITY").strip().upper()
    if cat not in ("UTILITY", "MARKETING", "AUTHENTICATION"):
        return None, "Category must be UTILITY, MARKETING, or AUTHENTICATION."
    body = (body_text or "").strip()
    if len(body) < 1 or len(body) > 1024:
        return None, "Template body must be between 1 and 1024 characters."

    url = f"https://graph.facebook.com/v19.0/{waba_id}/message_templates"
    payload = {
        "name": tname,
        "language": lang,
        "category": cat,
        "components": [{"type": "BODY", "text": body}],
    }
    try:
        r = get_external_client().post(
            url,
            params={"access_token": access_token},
            json=payload,
            timeout=30.0,
        )
    except Exception as e:  # noqa: BLE001
        return None, str(e)
    if r.status_code >= 400:
        return None, _friendly_graph_error(r.text[:2000])
    data = r.json() if r.content else {}
    if not isinstance(data, dict):
        return {"name": tname, "language": lang, "status": "PENDING"}, None
    return {
        "id": str(data.get("id") or ""),
        "name": tname,
        "language": lang,
        "status": str(data.get("status") or "PENDING").upper(),
        "category": cat,
        "body_preview": body[:500],
    }, None


def send_whatsapp_template(
    phone_number_id: str,
    access_token: str,
    to_wa_id: str,
    *,
    template_name: str,
    language_code: str,
    body_variables: Optional[list[str]] = None,
) -> Optional[str]:
    to_wa_id = str(to_wa_id or "").strip().lstrip("+")
    tname = normalize_template_name(template_name)
    lang = (language_code or "en_US").strip() or "en_US"
    if not phone_number_id or not access_token or not to_wa_id or not tname:
        return "Missing phone_number_id, token, recipient, or template name."

    template_block: dict[str, Any] = {
        "name": tname,
        "language": {"code": lang},
    }
    vars_clean = [str(v).strip() for v in (body_variables or []) if str(v).strip()]
    if vars_clean:
        template_block["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": v[:1000]} for v in vars_clean],
            }
        ]

    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "template",
        "template": template_block,
    }
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    try:
        r = get_external_client().post(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
            timeout=30.0,
        )
    except Exception as e:  # noqa: BLE001
        return str(e)
    if r.status_code >= 400:
        return _friendly_graph_error(r.text[:2000])
    return None
