from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, jsonify, request

from config import WEBHOOK_GATE_SECRET
from services.inbound_pipeline import is_uuid, parse_telegram_text, process_text_message
from services.supabase_client import SupabaseRest

bp = Blueprint("telegram", __name__, url_prefix="/v1/telegram")
_db = SupabaseRest()


def _gate_ok() -> bool:
    if not WEBHOOK_GATE_SECRET:
        return True
    return request.headers.get("X-Clybotics-Webhook-Secret", "") == WEBHOOK_GATE_SECRET


@bp.route("/<bot_id>/<path_secret>", methods=["POST"])
def telegram_webhook(bot_id: str, path_secret: str):
    if not is_uuid(bot_id):
        abort(404)
    if not _gate_ok():
        abort(401)

    bot = _db.get_bot(bot_id)
    if not bot:
        abort(404)
    ws = str(bot["workspace_id"])
    ch = _db.get_bot_channel(ws, bot_id, "telegram")
    # Missing row (e.g. admin deleted channel): reject; URL path secret alone must not accept traffic.
    if not ch:
        abort(403)

    expected = (ch.get("telegram_webhook_path_secret") or "").strip()
    if not expected or path_secret != expected:
        abort(403)

    if str(ch.get("status") or "") != "connected":
        return jsonify({"ok": True, "ignored": True}), 200

    update = request.get_json(force=True, silent=True)
    if not isinstance(update, dict):
        abort(400, "invalid json")
    chat_id, text, raw = parse_telegram_text(update)
    if chat_id and text:
        try:
            process_text_message(
                _db,
                bot_id=bot_id,
                platform="telegram",
                external_user_id=chat_id,
                message_text=text,
                raw_for_storage={"telegram": raw},
            )
        except ValueError:
            pass
        except Exception:  # noqa: BLE001
            return jsonify({"ok": False}), 500

    return jsonify({"ok": True}), 200
