from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from config import WEBHOOK_ASYNC_PROCESSING

_log = logging.getLogger(__name__)


def dispatch_channel_message(work: Callable[..., None], **kwargs: Any) -> None:
    """
    When WEBHOOK_ASYNC_PROCESSING=1 (gunicorn/VPS/Railway), return HTTP 200 immediately and process in a thread.
    On Vercel serverless, keep async off — the runtime may freeze after the response.
    """
    if not WEBHOOK_ASYNC_PROCESSING:
        work(**kwargs)
        return

    def _runner() -> None:
        try:
            work(**kwargs)
        except Exception:  # noqa: BLE001
            _log.exception("async webhook processing failed")

    threading.Thread(target=_runner, daemon=True).start()
