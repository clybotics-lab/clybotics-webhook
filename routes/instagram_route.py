from __future__ import annotations

from typing import Any, Iterator

from flask import Blueprint, abort, jsonify, request

from config import META_APP_SECRET, WEBHOOK_GATE_SECRET
from services.inbound_pipeline import is_uuid, process_text_message, verify_meta_signature
from services.supabase_client import SupabaseRest
from services.channel_inbound import dispatch_inbound_text
from services.webhook_dispatch import dispatch_channel_message

bp = Blueprint("instagram", __name__, url_prefix="/v1/instagram")
_db = SupabaseRest()


def _gate_ok() -> bool:
    if not WEBHOOK_GATE_SECRET:
        return True
    return request.headers.get("X-Clybotics-Webhook-Secret", "") == WEBHOOK_GATE_SECRET


def _read_meta_str(meta: dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = meta.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _iter_instagram_messaging(body: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    entries = body.get("entry", []) if isinstance(body.get("entry"), list) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("id", ""))
        for key in ("messaging", "messaging_events"):
            for ev in entry.get(key, []) or []:
                if isinstance(ev, dict):
                    yield entry_id, ev


@bp.route("/<bot_id>", methods=["GET", "POST"])
def instagram_webhook(bot_id: str):
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
            ch = _db.get_bot_channel(ws, bot_id, "instagram")
            if not ch:
                abort(403)
            expected = (ch.get("webhook_verify_token") or "").strip()
            if expected and token == expected:
                _db.mark_webhook_connected(ws, bot_id, "instagram")
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
    ch = _db.get_bot_channel(ws, bot_id, "instagram")
    if not ch:
        return jsonify({"ok": True, "ignored": True}), 200

    meta = bot.get("metadata") if isinstance(bot.get("metadata"), dict) else {}
    expected_page = (ch.get("page_id") or "").strip() or _read_meta_str(
        meta, "instagramPageId", "instagram_page_id", "pageId", "page_id"
    )
    im = ch.get("integration_metadata") if isinstance(ch.get("integration_metadata"), dict) else {}
    expected_ig_account = str(im.get("instagram_account_id") or "").strip()

    for entry_id, ev in _iter_instagram_messaging(body_typed):
        if ev.get("delivery") or ev.get("read"):
            continue
        if expected_ig_account and entry_id and entry_id != expected_ig_account:
            continue
        recipient = ev.get("recipient", {})
        recipient_id = str(recipient.get("id", "")) if isinstance(recipient, dict) else ""
        if expected_page and recipient_id and recipient_id != expected_page:
            continue
        if entry_id and not expected_ig_account:
            _db.sync_instagram_account_id(ws, bot_id, entry_id)
        sender = ev.get("sender", {})
        igsid = str(sender.get("id", "")) if isinstance(sender, dict) else ""
        msg = ev.get("message", {})
        text = msg.get("text") if isinstance(msg, dict) else None
        if igsid and isinstance(text, str) and text.strip():
            raw_store = {"instagram": ev}
            try:
                dispatch_inbound_text(
                    db=_db,
                    workspace_id=ws,
                    bot_id=bot_id,
                    bot=bot,
                    channel=ch,
                    platform="instagram",
                    external_user_id=igsid,
                    message_text=text.strip(),
                    raw_for_storage=raw_store,
                    customer_name=None,
                    work=process_text_message,
                    dispatch=dispatch_channel_message,
                )
            except ValueError:
                pass
            except Exception:  # noqa: BLE001
                return jsonify({"ok": False}), 500

    return jsonify({"ok": True}), 200
