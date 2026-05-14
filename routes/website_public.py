from __future__ import annotations

from typing import Any, Optional

from flask import Blueprint, abort, jsonify, request

from config import WEBSITE_WIDGET_GATE_SECRET
from services.inbound_pipeline import process_text_message
from services.supabase_client import SupabaseRest

bp = Blueprint("website_public", __name__, url_prefix="/webhooks/v1/website")
_db = SupabaseRest()


def _gate_ok() -> bool:
    if not WEBSITE_WIDGET_GATE_SECRET:
        return True
    return request.headers.get("X-Clybotics-Website-Secret") == WEBSITE_WIDGET_GATE_SECRET


def _str_field(body: dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = body.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


@bp.post("/message")
def website_message():
    """Public ingest for embedded website widget: persists customer (+ optional bot) to chat_sessions / chat_messages."""
    if not _gate_ok():
        abort(401)

    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON body required."}), 400

    bot_id = _str_field(body, "bot_id")
    visitor_id = _str_field(body, "visitor_id", "visitor_key", "external_user_id")
    message = _str_field(body, "message", "text", "query")
    bot_reply_raw = body.get("bot_reply")
    bot_reply = str(bot_reply_raw).strip() if bot_reply_raw is not None else ""
    visitor_name = _str_field(body, "visitor_name", "customer_name") or None

    if not bot_id or not visitor_id or not message:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "bot_id, visitor_id (or visitor_key), and message are required.",
                }
            ),
            400,
        )

    visitor_id = visitor_id[:240]
    message = message[:8000]
    bot_reply_opt: Optional[str] = bot_reply if bot_reply else None

    raw: dict[str, Any] = {"source": "website_widget_http", "path": request.path}
    if request.remote_addr:
        raw["remote_addr"] = request.remote_addr[:80]

    try:
        process_text_message(
            _db,
            bot_id=bot_id,
            platform="website",
            external_user_id=visitor_id,
            message_text=message,
            raw_for_storage=raw,
            customer_name=visitor_name,
            prefilled_bot_reply=bot_reply_opt,
        )
    except ValueError as e:
        code = str(e)
        if code == "unknown_bot":
            return jsonify({"ok": False, "error": "Unknown bot_id."}), 404
        return jsonify({"ok": False, "error": code}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)[:500]}), 500

    return jsonify({"ok": True}), 200
