from __future__ import annotations

from typing import Any, Optional

from flask import Blueprint, abort, jsonify, request

from services.inbound_pipeline import is_uuid
from services.outbound import send_facebook_manual_reply, send_telegram_text, send_whatsapp_text
from services.supabase_auth import fetch_user_from_jwt
from services.subscription_gate import bot_subscription_is_active
from services.supabase_client import SupabaseRest

bp = Blueprint("internal_conversation", __name__, url_prefix="/internal/v1/conversation")
_db = SupabaseRest()


def _bearer_jwt() -> Optional[str]:
    h = request.headers.get("Authorization", "")
    if h.startswith("Bearer "):
        return h[7:].strip()
    return None


def _read_meta_str(meta: dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = meta.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


@bp.post("/reply")
def reply():
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
    session_id = str(body.get("chat_session_id", "")).strip()
    raw_text = body.get("message_text")
    text = str(raw_text).strip() if raw_text is not None else ""
    if not is_uuid(session_id) or not text:
        return jsonify({"ok": False, "error": "chat_session_id and message_text are required."}), 400
    if len(text) > 4000:
        return jsonify({"ok": False, "error": "message_text is too long."}), 400

    sess = _db.get_chat_session_by_id(session_id)
    if not sess:
        return jsonify({"ok": False, "error": "Session not found."}), 404
    ws = str(sess["workspace_id"])
    bot_id = str(sess["bot_id"])
    platform = str(sess.get("platform") or "").strip().lower()
    external = (sess.get("customer_external_id") or "").strip()
    if not external:
        return jsonify({"ok": False, "error": "Session has no customer external id; cannot deliver."}), 400

    if not _db.user_can_manage_bot_channels(uid, ws):
        abort(403)

    if not bot_subscription_is_active(_db, ws, bot_id):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "This bot has no active subscription. Renew or activate the bot to send replies from the dashboard.",
                }
            ),
            403,
        )

    bot = _db.get_bot(bot_id)
    if not bot:
        return jsonify({"ok": False, "error": "Bot not found."}), 404
    meta = bot.get("metadata") if isinstance(bot.get("metadata"), dict) else {}
    meta = dict(meta)

    channel = _db.get_bot_channel(ws, bot_id, platform)
    if not channel:
        return jsonify({"ok": False, "error": "Channel is not configured for this platform."}), 400

    raw_out: dict[str, Any] = {"source": "dashboard_agent_reply", "platform": platform}
    send_err: Optional[str] = None

    if platform == "facebook":
        page_id = _read_meta_str(meta, "pageId", "page_id")
        token = _read_meta_str(meta, "accessToken", "access_token")
        if not page_id or not token:
            return jsonify({"ok": False, "error": "Facebook Page ID or access token missing on bot metadata."}), 400
        send_err = send_facebook_manual_reply(page_id, token, external, text)
    elif platform == "instagram":
        page_id = str(channel.get("page_id") or "").strip() or _read_meta_str(
            meta, "instagramPageId", "instagram_page_id", "pageId", "page_id"
        )
        token = _read_meta_str(meta, "instagramAccessToken", "instagram_access_token", "accessToken", "access_token")
        if not page_id or not token:
            return jsonify({"ok": False, "error": "Instagram Page ID or access token missing on bot metadata."}), 400
        send_err = send_facebook_manual_reply(page_id, token, external, text)
    elif platform == "telegram":
        ttoken = _read_meta_str(meta, "telegramBotToken", "telegram_bot_token")
        if not ttoken:
            return jsonify({"ok": False, "error": "Telegram bot token missing on bot metadata."}), 400
        send_err = send_telegram_text(ttoken, external, text)
    elif platform == "whatsapp":
        phone_number_id = str(channel.get("page_id") or _read_meta_str(meta, "pageId", "page_id"))
        token = _read_meta_str(meta, "accessToken", "access_token")
        if not phone_number_id or not token:
            return jsonify({"ok": False, "error": "WhatsApp phone_number_id or access token missing."}), 400
        send_err = send_whatsapp_text(phone_number_id, token, external, text)
    else:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": f"Outbound reply is not supported for platform '{platform}' from this endpoint (website/widget uses a different channel).",
                }
            ),
            400,
        )

    if send_err:
        raw_out["outbound_error"] = send_err[:500]
        return jsonify({"ok": False, "error": send_err[:500]}), 502

    _db.insert_chat_message(
        ws,
        bot_id,
        session_id,
        "agent",
        text,
        raw_out,
    )
    _db.bump_stats(ws, bot_id, platform, inbound=0, outbound=1)
    return jsonify({"ok": True}), 200
