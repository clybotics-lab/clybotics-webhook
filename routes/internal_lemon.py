from __future__ import annotations

from typing import Optional

from flask import Blueprint, abort, jsonify, request

from config import LEMONSQUEEZY_API_KEY, LEMONSQUEEZY_STORE_ID
from services.lemon_squeezy import create_lemon_checkout_for_user
from services.supabase_auth import fetch_user_from_jwt
from services.supabase_client import SupabaseRest

bp = Blueprint("internal_lemon", __name__, url_prefix="/internal/v1/lemon")
_db = SupabaseRest()


def _bearer_jwt() -> Optional[str]:
    h = request.headers.get("Authorization", "")
    if h.startswith("Bearer "):
        return h[7:].strip()
    return None


@bp.post("/create-checkout")
def create_checkout():
    if not LEMONSQUEEZY_API_KEY or not LEMONSQUEEZY_STORE_ID:
        return jsonify({"ok": False, "error": "Lemon Squeezy is not configured on this server."}), 503
    jwt = _bearer_jwt()
    if not jwt:
        abort(401)
    user = fetch_user_from_jwt(jwt)
    if not user:
        abort(401)
    uid = str(user.get("id", "")).strip()
    if not uid:
        abort(401)
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        return jsonify({"ok": False, "error": "JSON body required."}), 400
    bot_id = str(body.get("bot_id") or "").strip()
    plan_code = str(body.get("plan_code") or "starter").strip()
    if len(bot_id) < 10:
        return jsonify({"ok": False, "error": "bot_id is required."}), 400
    try:
        url = create_lemon_checkout_for_user(_db, user_id=uid, bot_id=bot_id, plan_code=plan_code)
        return jsonify({"ok": True, "checkout_url": url}), 200
    except PermissionError:
        abort(403)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)[:500]}), 500
