from __future__ import annotations

import secrets
from typing import Any, Optional

from flask import Blueprint, abort, jsonify, request

from services.inbound_pipeline import is_uuid
from services.supabase_auth import fetch_user_from_jwt
from services.supabase_client import SupabaseRest

bp = Blueprint("internal_facebook", __name__, url_prefix="/internal/v1/facebook")
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


@bp.post("/provision")
def provision():
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
    bot_id = str(body.get("bot_id", "")).strip()
    if not is_uuid(bot_id):
        abort(400)

    ws = _db.workspace_for_bot(bot_id)
    if not ws:
        abort(404)
    if not _db.user_can_manage_bot_channels(uid, ws):
        abort(403)

    bot = _db.get_bot(bot_id)
    if not bot:
        abort(404)
    meta = bot.get("metadata") if isinstance(bot.get("metadata"), dict) else {}
    # Page ID + access token can be saved after Meta webhook verify; provision only needs the channel row + verify token.
    page_id = _read_meta_str(meta, "pageId", "page_id")

    raw_verify = body.get("verify_token")
    verify: str
    if raw_verify is not None and str(raw_verify).strip():
        verify = str(raw_verify).strip()
        if len(verify) > 256:
            return jsonify({"ok": False, "error": "verify_token must be at most 256 characters."}), 400
    else:
        verify = secrets.token_hex(20)
    _db.upsert_facebook_provision(ws, bot_id, page_id, verify)

    public_base = str(body.get("webhook_public_base", "")).strip().rstrip("/")
    if not public_base:
        return jsonify({"ok": False, "error": "Missing webhook_public_base in body."}), 400

    callback = f"{public_base}/v1/facebook/{bot_id}"
    return jsonify(
        {
            "ok": True,
            "webhook_url": callback,
            "verify_token": verify,
            "webhook_connection_state": "provisioned",
        }
    ), 200


@bp.post("/awaiting")
def awaiting():
    jwt = _bearer_jwt()
    if not jwt:
        abort(401)
    user = fetch_user_from_jwt(jwt)
    if not user:
        abort(401)
    uid = str(user.get("id", ""))
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        abort(400)
    bot_id = str(body.get("bot_id", "")).strip()
    if not is_uuid(bot_id):
        abort(400)

    ws = _db.workspace_for_bot(bot_id)
    if not ws or not _db.user_can_manage_bot_channels(uid, ws):
        abort(403)

    _db.patch_facebook_channel(
        ws,
        bot_id,
        {"webhook_connection_state": "awaiting_handshake"},
    )
    return jsonify({"ok": True, "webhook_connection_state": "awaiting_handshake"}), 200


@bp.post("/disconnect")
def disconnect():
    jwt = _bearer_jwt()
    if not jwt:
        abort(401)
    user = fetch_user_from_jwt(jwt)
    if not user:
        abort(401)
    uid = str(user.get("id", ""))
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        abort(400)
    bot_id = str(body.get("bot_id", "")).strip()
    if not is_uuid(bot_id):
        abort(400)

    ws = _db.workspace_for_bot(bot_id)
    if not ws or not _db.user_can_manage_bot_channels(uid, ws):
        abort(403)

    _db.disconnect_facebook_channel(ws, bot_id)
    return jsonify({"ok": True, "webhook_connection_state": "none"}), 200
