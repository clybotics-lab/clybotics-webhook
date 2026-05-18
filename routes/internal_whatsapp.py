from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from flask import Blueprint, abort, jsonify, request

from services.inbound_pipeline import is_uuid
from services.supabase_auth import fetch_user_from_jwt
from services.supabase_client import SupabaseRest
from services.whatsapp_meta import fetch_whatsapp_phone_profile
from services.whatsapp_templates import (
    create_message_template,
    fetch_waba_id,
    list_message_templates,
    normalize_template_name,
    send_whatsapp_template,
)

bp = Blueprint("internal_whatsapp", __name__, url_prefix="/internal/v1/whatsapp")
_db = SupabaseRest()

WA_WINDOW = timedelta(hours=24)


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


def _auth_bot(bot_id: str) -> tuple[str, str, dict[str, Any], dict[str, Any], dict[str, Any]]:
    jwt = _bearer_jwt()
    if not jwt:
        abort(401)
    user = fetch_user_from_jwt(jwt)
    if not user:
        abort(401)
    uid = str(user.get("id", ""))
    if not uid:
        abort(401)
    if not is_uuid(bot_id):
        abort(400)

    ws = _db.workspace_for_bot(bot_id)
    if not ws or not _db.user_can_manage_bot_channels(uid, ws):
        abort(403)

    bot = _db.get_bot(bot_id)
    if not bot:
        abort(404)
    meta = bot.get("metadata") if isinstance(bot.get("metadata"), dict) else {}
    meta = dict(meta)

    channel = _db.get_bot_channel(ws, bot_id, "whatsapp")
    if not channel:
        abort(400)

    return ws, bot_id, bot, meta, channel


def _whatsapp_send_creds(meta: dict[str, Any], channel: dict[str, Any]) -> tuple[str, str]:
    phone_number_id = str(channel.get("page_id") or "").strip() or _read_meta_str(meta, "pageId", "page_id")
    token = _read_meta_str(meta, "accessToken", "access_token")
    return phone_number_id, token


def _resolve_waba(phone_number_id: str, token: str, channel: dict[str, Any], ws: str, bot_id: str) -> Optional[str]:
    im = channel.get("integration_metadata") if isinstance(channel.get("integration_metadata"), dict) else {}
    cached = str(im.get("whatsapp_waba_id") or "").strip()
    if cached:
        return cached
    waba = fetch_waba_id(phone_number_id, token)
    if waba:
        new_im = dict(im)
        new_im["whatsapp_waba_id"] = waba
        _db._patch(
            "/bot_channels",
            {"integration_metadata": new_im},
            {
                "workspace_id": f"eq.{ws}",
                "bot_id": f"eq.{bot_id}",
                "platform": "eq.whatsapp",
            },
        )
    return waba


def _window_payload(last_customer_at: Optional[str]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    if not last_customer_at:
        return {
            "has_customer_message": False,
            "window_open": False,
            "is_new_contact": True,
            "last_customer_message_at": None,
            "window_expires_at": None,
            "seconds_remaining": 0,
        }
    try:
        s = last_customer_at.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        started = datetime.fromisoformat(s)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
    except ValueError:
        return {
            "has_customer_message": True,
            "window_open": False,
            "is_new_contact": False,
            "last_customer_message_at": last_customer_at,
            "window_expires_at": None,
            "seconds_remaining": 0,
        }
    expires = started + WA_WINDOW
    remaining = max(0, int((expires - now).total_seconds()))
    return {
        "has_customer_message": True,
        "window_open": remaining > 0,
        "is_new_contact": False,
        "last_customer_message_at": started.isoformat(),
        "window_expires_at": expires.isoformat(),
        "seconds_remaining": remaining,
    }


@bp.post("/sync-phone")
def sync_phone():
    """Resolve WhatsApp display number via Graph API and store on bot_channels."""
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        abort(400)
    bot_id = str(body.get("bot_id", "")).strip()
    ws, _, bot, meta, channel = _auth_bot(bot_id)

    phone_number_id, token = _whatsapp_send_creds(meta, channel)
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


@bp.get("/templates")
def get_templates():
    bot_id = str(request.args.get("bot_id", "")).strip()
    ws, _, _, meta, channel = _auth_bot(bot_id)
    phone_number_id, token = _whatsapp_send_creds(meta, channel)
    if not phone_number_id or not token:
        return jsonify({"ok": False, "error": "Save WhatsApp Phone Number ID and access token first."}), 400
    waba = _resolve_waba(phone_number_id, token, channel, ws, bot_id)
    if not waba:
        return jsonify({"ok": False, "error": "Could not resolve WhatsApp Business Account from Meta."}), 400
    templates, err = list_message_templates(waba, token)
    if err:
        return jsonify({"ok": False, "error": err}), 502
    approved = [t for t in templates if t.get("status") == "APPROVED"]
    return jsonify({"ok": True, "waba_id": waba, "templates": templates, "approved_count": len(approved)}), 200


@bp.post("/templates")
def post_template():
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        abort(400)
    bot_id = str(body.get("bot_id", "")).strip()
    ws, _, _, meta, channel = _auth_bot(bot_id)
    phone_number_id, token = _whatsapp_send_creds(meta, channel)
    if not phone_number_id or not token:
        return jsonify({"ok": False, "error": "Save WhatsApp credentials first."}), 400
    waba = _resolve_waba(phone_number_id, token, channel, ws, bot_id)
    if not waba:
        return jsonify({"ok": False, "error": "Could not resolve WhatsApp Business Account."}), 400

    created, err = create_message_template(
        waba,
        token,
        name=str(body.get("name", "")),
        language=str(body.get("language", "en_US")),
        category=str(body.get("category", "UTILITY")),
        body_text=str(body.get("body_text", "")),
    )
    if err:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, "template": created}), 200


@bp.get("/conversation-window")
def conversation_window():
    session_id = str(request.args.get("chat_session_id", "")).strip()
    if not is_uuid(session_id):
        abort(400)
    jwt = _bearer_jwt()
    if not jwt:
        abort(401)
    user = fetch_user_from_jwt(jwt)
    if not user:
        abort(401)
    uid = str(user.get("id", ""))
    if not uid:
        abort(401)
    sess = _db.get_chat_session_by_id(session_id)
    if not sess:
        return jsonify({"ok": False, "error": "Session not found."}), 404
    if str(sess.get("platform") or "").lower() != "whatsapp":
        return jsonify({"ok": False, "error": "Not a WhatsApp session."}), 400
    ws = str(sess["workspace_id"])
    if not _db.user_can_manage_bot_channels(uid, ws):
        abort(403)
    last_at = _db.get_last_customer_message_at(session_id)
    return jsonify({"ok": True, "window": _window_payload(last_at)}), 200


@bp.post("/send-template")
def send_template_message():
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        abort(400)
    session_id = str(body.get("chat_session_id", "")).strip()
    if not is_uuid(session_id):
        abort(400)

    jwt = _bearer_jwt()
    if not jwt:
        abort(401)
    user = fetch_user_from_jwt(jwt)
    if not user:
        abort(401)
    uid = str(user.get("id", ""))
    if not uid:
        abort(401)

    sess = _db.get_chat_session_by_id(session_id)
    if not sess:
        return jsonify({"ok": False, "error": "Session not found."}), 404
    ws = str(sess["workspace_id"])
    bot_id = str(sess["bot_id"])
    platform = str(sess.get("platform") or "").strip().lower()
    if platform != "whatsapp":
        return jsonify({"ok": False, "error": "Template send is only for WhatsApp."}), 400
    external = (sess.get("customer_external_id") or "").strip()
    if not external:
        return jsonify({"ok": False, "error": "Session has no customer id."}), 400
    if not _db.user_can_manage_bot_channels(uid, ws):
        abort(403)

    from services.subscription_gate import bot_subscription_is_active

    if not bot_subscription_is_active(_db, ws, bot_id):
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "This bot has no active subscription. Renew to send messages.",
                }
            ),
            403,
        )

    bot = _db.get_bot(bot_id)
    if not bot:
        return jsonify({"ok": False, "error": "Bot not found."}), 404
    meta = bot.get("metadata") if isinstance(bot.get("metadata"), dict) else {}
    channel = _db.get_bot_channel(ws, bot_id, "whatsapp")
    if not channel:
        return jsonify({"ok": False, "error": "WhatsApp channel not configured."}), 400

    phone_number_id, token = _whatsapp_send_creds(dict(meta), channel)
    if not phone_number_id or not token:
        return jsonify({"ok": False, "error": "WhatsApp credentials missing."}), 400

    tname = normalize_template_name(str(body.get("template_name", "")))
    lang = str(body.get("language_code", "en_US")).strip() or "en_US"
    raw_vars = body.get("body_variables")
    body_variables: list[str] = []
    if isinstance(raw_vars, list):
        body_variables = [str(v) for v in raw_vars]

    waba = _resolve_waba(phone_number_id, token, channel, ws, bot_id)
    if waba:
        templates, _ = list_message_templates(waba, token)
        match = next(
            (t for t in templates if t.get("name") == tname and str(t.get("language", "")).startswith(lang.split("_")[0])),
            None,
        )
        if match and match.get("status") != "APPROVED":
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": f"Template '{tname}' is {match.get('status')}. Only APPROVED templates can be sent.",
                    }
                ),
                400,
            )

    send_err = send_whatsapp_template(
        phone_number_id,
        token,
        external,
        template_name=tname,
        language_code=lang,
        body_variables=body_variables,
    )
    if send_err:
        return jsonify({"ok": False, "error": send_err}), 502

    display = f"[Template: {tname}]"
    if body_variables:
        display = f"[Template: {tname}] " + " · ".join(body_variables[:5])
    raw_out: dict[str, Any] = {
        "source": "dashboard_agent_template",
        "platform": "whatsapp",
        "template_name": tname,
        "language_code": lang,
        "body_variables": body_variables,
    }
    _db.insert_chat_message(ws, bot_id, session_id, "agent", display, raw_out)
    _db.bump_stats(ws, bot_id, platform, inbound=0, outbound=1)
    return jsonify({"ok": True}), 200
