from __future__ import annotations

import logging

from flask import Blueprint, request

from services.lemon_squeezy import process_lemon_webhook
from services.supabase_client import SupabaseRest

log = logging.getLogger(__name__)

bp = Blueprint("lemon_webhook", __name__, url_prefix="/webhooks/v1")
_db = SupabaseRest()


@bp.post("/lemonsqueezy")
def lemonsqueezy_webhook():
    """Lemon Squeezy signed webhooks → insert approved payment + activate subscription."""
    raw = request.get_data(cache=False, as_text=False) or b""
    sig = request.headers.get("X-Signature", "") or ""
    event_name = request.headers.get("X-Event-Name", "") or ""
    try:
        ok, msg = process_lemon_webhook(_db, raw, sig, event_name)
        if not ok and msg == "webhook_secret_not_configured":
            return {"ok": False, "error": "not_configured"}, 503
        if not ok and msg == "invalid_signature":
            return {"ok": False, "error": "invalid_signature"}, 401
        return {"ok": True, "detail": msg}, 200
    except Exception as e:  # noqa: BLE001
        log.exception("lemonsqueezy_webhook_failed")
        return {"ok": False, "error": str(e)[:400]}, 500
