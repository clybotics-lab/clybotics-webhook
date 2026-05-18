from __future__ import annotations

from typing import Any, Optional

from flask import Blueprint, abort, jsonify, request

from services.inbound_pipeline import is_uuid
from services.supabase_auth import fetch_user_from_jwt
from services.supabase_client import SupabaseRest
from services.whatsapp_meta import fetch_whatsapp_phone_profile

bp = Blueprint("internal_whatsapp", __name__, url_prefix="/internal/v1/whatsapp")
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


@bp.post("/sync-phone")
def sync_phone():
    """Resolve WhatsApp display number via Graph API and store on bot_channels."""
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
    if not ws or not _db.user_can_manage_bot_channels(uid, ws):
        abort(403)

    bot = _db.get_bot(bot_id)
    if not bot:
        abort(404)
    meta = bot.get("metadata") if isinstance(bot.get("metadata"), dict) else {}
    phone_number_id = _read_meta_str(meta, "pageId", "page_id")
    token = _read_meta_str(meta, "accessToken", "access_token")
    if not phone_number_id or not token:
        return jsonify(
            {
                "ok": False,
                "error": "Save WhatsApp Phone Number ID and Cloud API access token first.",
            }
        ), 400

    profile = fetch_whatsapp_phone_profile(phone_number_id, token)
    display = profile.get("display_phone", "")
    verified = profile.get("verified_name", "")
    row = _db.sync_whatsapp_channel_phone(ws, bot_id, phone_number_id, display or None, verified or None)
    if not row:
        return jsonify({"ok": False, "error": "WhatsApp channel row not found. Save webhook token first."}), 404

    im = row.get("integration_metadata") if isinstance(row.get("integration_metadata"), dict) else {}
    return jsonify(
        {
            "ok": True,
            "phone_number_id": row.get("page_id") or phone_number_id,
            "display_phone": im.get("whatsapp_display_phone") or display or None,
            "verified_name": im.get("whatsapp_verified_name") or verified or None,
        }
    ), 200
