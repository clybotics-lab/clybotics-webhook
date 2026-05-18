from __future__ import annotations

from typing import Any, Callable, Optional

from services.subscription_gate import should_run_bot_auto_reply
from services.supabase_client import SupabaseRest


def dispatch_inbound_text(
    *,
    db: SupabaseRest,
    workspace_id: str,
    bot_id: str,
    bot: dict[str, Any],
    channel: Optional[dict[str, Any]],
    platform: str,
    external_user_id: str,
    message_text: str,
    raw_for_storage: dict[str, Any],
    customer_name: Optional[str],
    work: Callable[..., None],
    dispatch: Callable[..., None],
) -> None:
    """Log inbound always when channel row exists; auto-reply only if connected + active subscription."""
    auto_reply = should_run_bot_auto_reply(db, workspace_id, bot_id, channel)
    dispatch(
        work,
        db=db,
        bot_id=bot_id,
        platform=platform,
        external_user_id=external_user_id,
        message_text=message_text,
        raw_for_storage=raw_for_storage,
        customer_name=customer_name,
        bot=bot,
        channel=channel,
        auto_reply=auto_reply,
        allow_disconnected_channel=True,
    )
