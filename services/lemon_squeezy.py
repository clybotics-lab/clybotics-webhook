"""Lemon Squeezy: signed webhooks + server-side checkout creation (API key never exposed to browser)."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from config import (
    LEMONSQUEEZY_API_KEY,
    LEMONSQUEEZY_CHECKOUT_SUCCESS_URL,
    LEMONSQUEEZY_STORE_ID,
    LEMONSQUEEZY_VARIANT_PRO,
    LEMONSQUEEZY_VARIANT_STARTER,
    LEMONSQUEEZY_WEBHOOK_SECRET,
)
from services.supabase_client import SupabaseRest


def verify_lemon_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    if not secret or not signature_header:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    try:
        return hmac.compare_digest(expected, signature_header.strip())
    except Exception:  # noqa: BLE001
        return False


def _variant_for_plan(plan_code: str, starter_id: str, pro_id: str) -> Optional[str]:
    p = (plan_code or "").strip().lower()
    if p == "starter":
        return starter_id
    if p == "pro":
        return pro_id
    return None


def create_checkout_url(
    *,
    store_id: str,
    variant_id: str,
    custom: dict[str, str],
    redirect_url: str,
    api_key: str,
) -> str:
    """POST /v1/checkouts and return hosted checkout URL."""
    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "custom": {k: str(v) for k, v in custom.items()},
                },
                "product_options": {
                    "redirect_url": redirect_url,
                },
                "preview": False,
            },
            "relationships": {
                "store": {"data": {"type": "stores", "id": str(store_id)}},
                "variant": {"data": {"type": "variants", "id": str(variant_id)}},
            },
        }
    }
    r = httpx.post(
        "https://api.lemonsqueezy.com/v1/checkouts",
        headers={
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
            "Authorization": f"Bearer {api_key}",
        },
        content=json.dumps(payload),
        timeout=45.0,
    )
    r.raise_for_status()
    body = r.json()
    data = body.get("data") or {}
    attrs = data.get("attributes") or {}
    url = attrs.get("url")
    if not url or not isinstance(url, str):
        raise RuntimeError("Lemon Squeezy checkout response missing url")
    return url


def _norm_plan(code: str) -> str:
    c = (code or "").strip().lower()
    if c in ("starter", "pro", "business"):
        return c
    return "starter"


def _extract_custom(meta: dict[str, Any]) -> dict[str, str]:
    raw = meta.get("custom_data")
    if not isinstance(raw, dict):
        raw = meta.get("custom") if isinstance(meta.get("custom"), dict) else {}
    out: dict[str, str] = {}
    for k in ("workspace_id", "bot_id", "plan_code"):
        v = raw.get(k)
        if v is not None and str(v).strip():
            out[k] = str(v).strip()
    return out


def _order_variant_id(attrs: dict[str, Any]) -> Optional[str]:
    item = attrs.get("first_order_item")
    if isinstance(item, dict):
        vid = item.get("variant_id")
        if vid is not None:
            return str(vid).strip()
    return None


def _amount_minor_usd(attrs: dict[str, Any]) -> int:
    for key in ("total_usd", "total"):
        v = attrs.get(key)
        if v is None:
            continue
        try:
            return int(round(float(v)))
        except (TypeError, ValueError):
            continue
    return 0


def _renewal_dates() -> tuple[str, str]:
    start = date.today()
    end = start + timedelta(days=30)
    return start.isoformat(), f"{end.isoformat()}T23:59:59Z"


def apply_paid_lemon_order(db: SupabaseRest, *, transaction_id: str, amount_minor: int, plan_code: str, workspace_id: str, bot_id: str, raw_meta: dict[str, Any]) -> None:
    if db.find_payment_by_provider_tx("lemonsqueezy", transaction_id):
        return
    ws = db.get_bot_workspace_id(bot_id)
    if not ws or ws != workspace_id:
        raise ValueError("bot_id does not belong to workspace_id")
    sub = db.get_bot_subscription_row(workspace_id, bot_id)
    if not sub:
        raise ValueError("No bot_subscriptions row for bot")
    sub_id = str(sub.get("id") or "")
    paid_plan = _norm_plan(plan_code)
    renewal_date, expires_at = _renewal_dates()
    db.insert_payment_row(
        {
            "workspace_id": workspace_id,
            "bot_id": bot_id,
            "subscription_id": sub_id or None,
            "plan_code": paid_plan,
            "amount": amount_minor,
            "currency": "USD",
            "payment_provider": "lemonsqueezy",
            "transaction_id": transaction_id,
            "sender_phone": None,
            "status": "approved",
            "paid_at": datetime.now(timezone.utc).isoformat(),
            "created_by": None,
            "raw_response": {"source": "lemonsqueezy", "meta": raw_meta},
        }
    )
    db.patch_bot_subscription_by_bot(
        workspace_id,
        bot_id,
        {
            "status": "active",
            "plan_code": paid_plan,
            "renewal_date": renewal_date,
            "expires_at": expires_at,
        },
    )
    db.patch_bot_row(workspace_id, bot_id, {"status": "active"})


def process_lemon_webhook(db: SupabaseRest, raw_body: bytes, signature_header: str, event_name: str) -> tuple[bool, str]:
    """Returns (ok, message). ok False + invalid_signature means 401."""
    secret = LEMONSQUEEZY_WEBHOOK_SECRET
    if not secret:
        return False, "webhook_secret_not_configured"
    if not verify_lemon_signature(raw_body, signature_header, secret):
        return False, "invalid_signature"
    try:
        body = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return True, "ignored_invalid_json"

    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    en = (event_name or meta.get("event_name") or "").strip()
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    dtype = str(data.get("type") or "")
    attrs = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
    data_id = str(data.get("id") or "").strip()
    if not data_id:
        return True, "ignored_no_id"

    custom = _extract_custom(meta)
    workspace_id = custom.get("workspace_id", "")
    bot_id = custom.get("bot_id", "")
    plan_code = custom.get("plan_code", "starter")
    if not workspace_id or not bot_id:
        return True, "ignored_missing_custom"

    amount_minor = _amount_minor_usd(attrs)
    status = str(attrs.get("status") or "").lower()
    if status != "paid":
        return True, f"ignored_status_{status or 'empty'}"

    tx_id = ""
    if dtype == "subscription-invoices" and en in ("subscription_payment_success",):
        tx_id = f"ls_subinv_{data_id}"
    else:
        return True, f"ignored_type_{dtype}_event_{en}"

    if amount_minor <= 0:
        return True, "ignored_zero_amount"

    vid_order = _order_variant_id(attrs)
    starter = LEMONSQUEEZY_VARIANT_STARTER
    pro = LEMONSQUEEZY_VARIANT_PRO
    expected_vid = _variant_for_plan(plan_code, starter, pro)
    if vid_order and expected_vid and vid_order != expected_vid:
        return True, "ignored_variant_mismatch"

    apply_paid_lemon_order(
        db,
        transaction_id=tx_id,
        amount_minor=amount_minor,
        plan_code=plan_code,
        workspace_id=workspace_id,
        bot_id=bot_id,
        raw_meta={"event_name": en, "data_type": dtype, "data_id": data_id},
    )
    return True, f"applied_{tx_id}"


def create_lemon_checkout_for_user(
    db: SupabaseRest,
    *,
    user_id: str,
    bot_id: str,
    plan_code: str,
) -> str:
    """Validate membership + build Lemon checkout (returns checkout URL)."""
    if not LEMONSQUEEZY_API_KEY or not LEMONSQUEEZY_STORE_ID:
        raise RuntimeError("Lemon Squeezy is not configured on this server.")
    ws = db.get_bot_workspace_id(bot_id)
    if not ws:
        raise ValueError("Bot not found")
    if not db.user_is_active_workspace_member(user_id, ws):
        raise PermissionError("Forbidden")
    pc = _norm_plan(plan_code)
    if pc == "business":
        raise ValueError("Card checkout is only available for Starter and Pro.")
    vid = _variant_for_plan(pc, LEMONSQUEEZY_VARIANT_STARTER, LEMONSQUEEZY_VARIANT_PRO)
    if not vid:
        raise ValueError("Unsupported plan for Lemon checkout")
    custom = {"workspace_id": ws, "bot_id": bot_id, "plan_code": pc}
    return create_checkout_url(
        store_id=LEMONSQUEEZY_STORE_ID,
        variant_id=vid,
        custom=custom,
        redirect_url=LEMONSQUEEZY_CHECKOUT_SUCCESS_URL or "https://app.clybotics.com",
        api_key=LEMONSQUEEZY_API_KEY,
    )
