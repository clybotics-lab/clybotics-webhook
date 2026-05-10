from __future__ import annotations

import json
import re
from typing import Any, Optional

from config import DEFAULT_BOT_REPLY
from services.dify_chat import run_blocking_chat
from services.outbound import send_facebook_text, send_telegram_text, send_whatsapp_text
from services.supabase_client import SupabaseRest


def _read_meta_str(meta: dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = meta.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _dify_credentials(meta: dict[str, Any]) -> tuple[str, str]:
    """Returns (base_url, api_key) if configured on the bot."""
    base = _read_meta_str(meta, "difyBaseUrl", "dify_base_url")
    key = _read_meta_str(meta, "providerApiKey", "provider_api_key", "dify_api_key")
    return base, key


def process_text_message(
    db: SupabaseRest,
    *,
    bot_id: str,
    platform: str,
    external_user_id: str,
    message_text: str,
    raw_for_storage: dict[str, Any],
    customer_name: Optional[str] = None,
) -> None:
    bot = db.get_bot(bot_id)
    if not bot:
        raise ValueError("unknown_bot")

    workspace_id = str(bot["workspace_id"])
    meta = bot.get("metadata") if isinstance(bot.get("metadata"), dict) else {}
    meta = dict(meta)

    channel = db.get_bot_channel(workspace_id, bot_id, platform)
    if not channel:
        raise ValueError("channel_not_configured")

    if str(channel.get("status") or "") != "connected":
        raise ValueError("channel_not_connected")

    session = db.find_chat_session(workspace_id, bot_id, platform, external_user_id)
    session_meta: dict[str, Any] = {}
    if session:
        sid = str(session["id"])
        sm = session.get("session_metadata")
        if isinstance(sm, dict):
            session_meta = dict(sm)
    else:
        tracking = {
            "source": platform,
            "bot_id": bot_id,
            "external_user_id": external_user_id,
            "tracking_conversation_key": f"{bot_id}:{platform}:{external_user_id}",
        }
        created = db.create_chat_session(
            workspace_id,
            bot_id,
            platform,
            external_user_id,
            customer_name,
            tracking,
        )
        sid = str(created["id"])

    db.insert_chat_message(
        workspace_id,
        bot_id,
        sid,
        "customer",
        message_text,
        raw_for_storage,
    )
    db.bump_stats(workspace_id, bot_id, platform, inbound=1, outbound=0)

    base, api_key = _dify_credentials(meta)
    dify_user = f"{platform}:{external_user_id}"
    conv_id = _read_meta_str(session_meta, "dify_conversation_id", "difyConversationId")

    reply_text: Optional[str] = None
    if base and api_key:
        ans, new_conv, err = run_blocking_chat(base, api_key, dify_user, message_text, conv_id)
        if ans:
            reply_text = ans
            if new_conv:
                session_meta["dify_conversation_id"] = new_conv
                db.patch_chat_session_metadata(sid, session_meta)
        elif err:
            raw_for_storage["dify_error"] = err[:500]

    if not reply_text:
        sp = bot.get("system_prompt")
        if isinstance(sp, str) and sp.strip():
            reply_text = f"{DEFAULT_BOT_REPLY}\n\n— {sp.strip()[:280]}"
        else:
            reply_text = DEFAULT_BOT_REPLY

    db.insert_chat_message(
        workspace_id,
        bot_id,
        sid,
        "bot",
        reply_text,
        {"source": "clybotics_webhook_service", "platform": platform},
    )

    send_err: Optional[str] = None
    if platform == "facebook":
        page_id = _read_meta_str(meta, "pageId", "page_id")
        token = _read_meta_str(meta, "accessToken", "access_token")
        if page_id and token:
            send_err = send_facebook_text(page_id, token, external_user_id, reply_text)
    elif platform == "telegram":
        token = _read_meta_str(meta, "telegramBotToken", "telegram_bot_token")
        if token:
            send_err = send_telegram_text(token, external_user_id, reply_text)
    elif platform == "whatsapp":
        phone_number_id = str(channel.get("page_id") or _read_meta_str(meta, "pageId", "page_id"))
        token = _read_meta_str(meta, "accessToken", "access_token")
        if phone_number_id and token:
            send_err = send_whatsapp_text(phone_number_id, token, external_user_id, reply_text)

    if send_err:
        raw_for_storage["outbound_error"] = send_err[:500]
    else:
        db.bump_stats(workspace_id, bot_id, platform, inbound=0, outbound=1)


def verify_meta_signature(body_raw: bytes, signature_header: Optional[str], app_secret: str) -> bool:
    if not app_secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    import hashlib
    import hmac

    expected = "sha256=" + hmac.new(app_secret.encode("utf-8"), body_raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode("utf-8"), signature_header.encode("utf-8"))


def parse_telegram_text(update: dict[str, Any]) -> tuple[Optional[str], Optional[str], dict[str, Any]]:
    msg = update.get("message") or update.get("edited_message")
    if not isinstance(msg, dict):
        return None, None, update
    chat = msg.get("chat")
    cid = str(chat["id"]) if isinstance(chat, dict) and chat.get("id") is not None else None
    text = msg.get("text") or msg.get("caption")
    if cid and isinstance(text, str) and text.strip():
        return cid, text.strip(), update
    return cid, None, update


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)


def is_uuid(s: str) -> bool:
    return bool(_UUID_RE.match((s or "").strip()))
