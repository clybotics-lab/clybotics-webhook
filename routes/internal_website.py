from __future__ import annotations

from typing import Any, Optional

from flask import Blueprint, abort, jsonify, request

from services.inbound_pipeline import is_uuid, process_text_message
from services.supabase_auth import fetch_user_from_jwt
from services.supabase_client import SupabaseRest

bp = Blueprint("internal_website", __name__, url_prefix="/internal/v1/website")
_db = SupabaseRest()


def _bearer_jwt() -> Optional[str]:
    h = request.headers.get("Authorization", "")
    if h.startswith("Bearer "):
        return h[7:].strip()
    return None


@bp.post("/log-turn")
def log_dashboard_website_preview_turn():
    """Authenticated: log dashboard Website Widget preview as platform=website (conversation logs)."""
    jwt = _bearer_jwt()
    if not jwt:
        abort(401)
    user = fetch_user_from_jwt(jwt)
    if not user:
        abort(401)
    uid = str(user.get("id", ""))
    if not uid:
        abort(401)

    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        abort(400)

    bot_id = str(body.get("bot_id") or "").strip()
    raw_user = body.get("message")
    raw_bot = body.get("bot_reply")
    user_msg = str(raw_user).strip() if raw_user is not None else ""
    bot_msg = str(raw_bot).strip() if raw_bot is not None else ""
    if not is_uuid(bot_id) or not user_msg:
        return jsonify({"ok": False, "error": "bot_id (uuid) and message are required."}), 400
    if len(user_msg) > 4000:
        return jsonify({"ok": False, "error": "message is too long."}), 400
    if len(bot_msg) > 8000:
        return jsonify({"ok": False, "error": "bot_reply is too long."}), 400

    bot = _db.get_bot(bot_id)
    if not bot:
        return jsonify({"ok": False, "error": "Bot not found."}), 404
    ws = str(bot["workspace_id"])
    if not _db.user_can_manage_bot_channels(uid, ws):
        abort(403)

    visitor_key = f"dashboard_preview:{uid}"
    raw: dict[str, Any] = {"source": "dashboard_website_widget_preview"}

    try:
        process_text_message(
            _db,
            bot_id=bot_id,
            platform="website",
            external_user_id=visitor_key,
            message_text=user_msg,
            raw_for_storage=raw,
            customer_name=None,
            prefilled_bot_reply=bot_msg if bot_msg else None,
        )
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)[:500]}), 500

    return jsonify({"ok": True}), 200
