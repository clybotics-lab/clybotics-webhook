from __future__ import annotations

import json
from typing import Any, Optional, Tuple

import httpx

from config import DIFY_CHAT_TIMEOUT


def _normalize_base(raw: str) -> str:
    u = raw.strip().rstrip("/")
    if not u:
        return "http://localhost/v1"
    if not u.lower().endswith("/v1"):
        return f"{u}/v1"
    return u


def run_blocking_chat(
    base_url: str,
    api_key: str,
    user: str,
    query: str,
    conversation_id: str = "",
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Returns (answer_text, conversation_id, error_message).
    """
    url = f"{_normalize_base(base_url)}/chat-messages"
    payload: dict[str, Any] = {
        "inputs": {},
        "query": query,
        "response_mode": "blocking",
        "conversation_id": conversation_id or "",
        "user": user,
    }
    try:
        r = httpx.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=DIFY_CHAT_TIMEOUT,
        )
    except Exception as e:  # noqa: BLE001
        return None, None, str(e)

    try:
        body = r.json()
    except json.JSONDecodeError:
        return None, None, r.text[:500]

    if r.status_code >= 400:
        err = body if isinstance(body, dict) else r.text
        return None, None, str(err)[:800]

    if not isinstance(body, dict):
        return None, None, "unexpected response"

    answer = body.get("answer")
    if isinstance(answer, str) and answer.strip():
        conv = body.get("conversation_id")
        conv_s = conv if isinstance(conv, str) else None
        return answer.strip(), conv_s, None

    return None, None, "no answer in Dify response"
