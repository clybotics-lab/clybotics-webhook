from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, jsonify, request

from config import META_APP_SECRET, WEBHOOK_GATE_SECRET
from services.inbound_pipeline import is_uuid, process_text_message, verify_meta_signature
from services.supabase_client import SupabaseRest
from services.channel_inbound import dispatch_inbound_text
from services.webhook_dispatch import dispatch_channel_message
from services.whatsapp_meta import whatsapp_metadata_from_webhook_body

bp = Blueprint("whatsapp", __name__, url_prefix="/v1/whatsapp")
_db = SupabaseRest()


def _gate_ok() -> bool:
    if not WEBHOOK_GATE_SECRET:
        return True
    return request.headers.get("X-Clybotics-Webhook-Secret", "") == WEBHOOK_GATE_SECRET


@bp.route("/<bot_id>", methods=["GET", "POST"])
def whatsapp_webhook(bot_id: str):
    if not is_uuid(bot_id):
        abort(404)

    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token and challenge:
            bot = _db.get_bot(bot_id)
            if not bot:
                abort(403)
            ws = str(bot["workspace_id"])
            ch = _db.get_bot_channel(ws, bot_id, "whatsapp")
            if not ch:
                abort(403)
            expected = (ch.get("webhook_verify_token") or "").strip()
            if expected and token == expected:
                _db.mark_webhook_connected(ws, bot_id, "whatsapp")
                return challenge, 200, {"Content-Type": "text/plain"}
            abort(403)
        abort(400)

    if not _gate_ok():
        abort(401)

    raw = request.get_data()
    if META_APP_SECRET:
        sig = request.headers.get("X-Hub-Signature-256", "")
        if not verify_meta_signature(raw, sig, META_APP_SECRET):
            abort(403)

    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        abort(400, "invalid json")

    bot = _db.get_bot(bot_id)
    if not bot:
        abort(404)
    ws = str(bot["workspace_id"])
    ch = _db.get_bot_channel(ws, bot_id, "whatsapp")
    if not ch:
        return jsonify({"ok": True, "ignored": True}), 200

    meta = bot.get("metadata") if isinstance(bot.get("metadata"), dict) else {}
    meta_phone = str(meta.get("pageId") or meta.get("page_id") or "").strip()
    expected_phone_id = (ch.get("page_id") or "").strip() or meta_phone

    for item in whatsapp_metadata_from_webhook_body(body):
        phone_id = item.get("phone_number_id", "")
        display = item.get("display_phone", "")
        if phone_id and (not expected_phone_id or phone_id == expected_phone_id):
            _db.sync_whatsapp_channel_phone(ws, bot_id, phone_id, display or None)

    for entry in body.get("entry", []) if isinstance(body, dict) else []:
        for change in entry.get("changes", []) or []:
            value = change.get("value") if isinstance(change, dict) else None
            if not isinstance(value, dict):
                continue
            meta = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
            phone_number_id = str(meta.get("phone_number_id", ""))
            if expected_phone_id and phone_number_id and phone_number_id != expected_phone_id:
                continue
            for msg in value.get("messages", []) or []:
                if not isinstance(msg, dict):
                    continue
                from_id = str(msg.get("from", ""))
                text_body = msg.get("text", {})
                text = text_body.get("body") if isinstance(text_body, dict) else None
                if from_id and isinstance(text, str) and text.strip():
                    try:
                        dispatch_inbound_text(
                            db=_db,
                            workspace_id=ws,
                            bot_id=bot_id,
                            bot=bot,
                            channel=ch,
                            platform="whatsapp",
                            external_user_id=from_id,
                            message_text=text.strip(),
                            raw_for_storage={"whatsapp": msg, "value": value},
                            customer_name=None,
                            work=process_text_message,
                            dispatch=dispatch_channel_message,
                        )
                    except ValueError:
                        pass
                    except Exception:  # noqa: BLE001
                        return jsonify({"ok": False}), 500

    return jsonify({"ok": True}), 200
