from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, jsonify, request

from config import META_APP_SECRET, WEBHOOK_GATE_SECRET
from services.inbound_pipeline import is_uuid, process_text_message, verify_meta_signature
from services.supabase_client import SupabaseRest

bp = Blueprint("facebook", __name__, url_prefix="/v1/facebook")
_db = SupabaseRest()


def _gate_ok() -> bool:
    if not WEBHOOK_GATE_SECRET:
        return True
    return request.headers.get("X-Clybotics-Webhook-Secret", "") == WEBHOOK_GATE_SECRET


@bp.route("/<bot_id>", methods=["GET", "POST"])
def facebook_webhook(bot_id: str):
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
            ch = _db.get_bot_channel(ws, bot_id, "facebook")
            if not ch:
                abort(403)
            expected = (ch.get("webhook_verify_token") or "").strip()
            if expected and token == expected:
                _db.mark_webhook_connected(ws, bot_id, "facebook")
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
    body_typed: dict[str, Any] = body

    bot = _db.get_bot(bot_id)
    if not bot:
        abort(404)
    ws = str(bot["workspace_id"])
    ch = _db.get_bot_channel(ws, bot_id, "facebook")
    if not ch or str(ch.get("status") or "") != "connected":
        return jsonify({"ok": True, "ignored": True}), 200

    meta = bot.get("metadata") if isinstance(bot.get("metadata"), dict) else {}
    meta_page = str(meta.get("pageId") or meta.get("page_id") or "").strip()
    expected_page = (ch.get("page_id") or "").strip() or meta_page

    for entry in body_typed.get("entry", []) if isinstance(body_typed, dict) else []:
        page_id = str(entry.get("id", ""))
        if expected_page and page_id and page_id != expected_page:
            continue
        for ev in entry.get("messaging", []) or []:
            if ev.get("delivery") or ev.get("read"):
                continue
            sender = ev.get("sender", {})
            psid = str(sender.get("id", "")) if isinstance(sender, dict) else ""
            msg = ev.get("message", {})
            text = msg.get("text") if isinstance(msg, dict) else None
            if psid and isinstance(text, str) and text.strip():
                try:
                    process_text_message(
                        _db,
                        bot_id=bot_id,
                        platform="facebook",
                        external_user_id=psid,
                        message_text=text.strip(),
                        raw_for_storage={"facebook": ev},
                    )
                except ValueError:
                    pass
                except Exception:  # noqa: BLE001
                    # Log in production via your platform; never fail Meta retry storms permanently.
                    return jsonify({"ok": False}), 500

    return jsonify({"ok": True}), 200
