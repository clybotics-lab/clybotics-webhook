from __future__ import annotations

from typing import Optional

from flask import Blueprint, jsonify, request

from config import LEMONSQUEEZY_API_KEY, LEMONSQUEEZY_STORE_ID
from services.lemon_squeezy import create_lemon_checkout_for_user
from services.supabase_auth import verify_supabase_session_jwt
from services.supabase_client import SupabaseRest

bp = Blueprint("internal_lemon", __name__, url_prefix="/internal/v1/lemon")
_db = SupabaseRest()


def _bearer_jwt() -> Optional[str]:
    h = request.headers.get("Authorization", "")
    if h.startswith("Bearer "):
        return h[7:].strip()
    return None


def _auth_error_payload(reason: str, *, hint: str) -> tuple[dict, int]:
    return (
        jsonify(
            {
                "ok": False,
                "error": "Unauthorized",
                "reason": reason,
                "hint": hint,
            }
        ),
        401,
    )


@bp.post("/create-checkout")
def create_checkout():
    if not LEMONSQUEEZY_API_KEY or not LEMONSQUEEZY_STORE_ID:
        return jsonify({"ok": False, "error": "Lemon Squeezy is not configured on this server."}), 503
    jwt = _bearer_jwt()
    if not jwt:
        return _auth_error_payload(
            "missing_authorization",
            hint="Send header Authorization: Bearer <Supabase access_token> from the signed-in dashboard.",
        )
    user, auth_reason = verify_supabase_session_jwt(jwt)
    if not user:
        hints = {
            "empty_jwt": "Bearer token was empty after parsing.",
            "supabase_auth_unreachable": "Server could not reach Supabase (check SUPABASE_URL and outbound network).",
            "supabase_rejected_session": "Supabase rejected the token (expired, wrong signing key, or anon key does not match the project that minted the JWT). Re-login.",
            "supabase_auth_invalid_json": "Supabase /auth/v1/user returned non-JSON.",
            "supabase_user_missing": "Supabase /auth/v1/user JSON was not a recognized user shape (nested user or flat user with id).",
            "supabase_user_id_missing": "Supabase user payload had no id.",
        }
        suffix = ""
        if auth_reason.startswith("supabase_auth_http_"):
            suffix = " Supabase /auth/v1/user returned an unexpected status."
        return _auth_error_payload(
            auth_reason,
            hint=hints.get(auth_reason, f"Auth step failed ({auth_reason}).{suffix}"),
        )
    uid = str(user.get("id", "")).strip()
    if not uid:
        return _auth_error_payload(
            "user_id_empty",
            hint="JWT was accepted but user id is empty — unexpected; try re-login.",
        )
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
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Forbidden",
                    "reason": "not_allowed_for_bot_or_workspace",
                    "hint": "Signed-in user is not an active member of the bot's workspace.",
                }
            ),
            403,
        )
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)[:500]}), 500
