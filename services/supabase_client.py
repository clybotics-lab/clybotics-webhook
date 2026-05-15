from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL
from services.http_pool import get_rest_client


class SupabaseRest:
    def __init__(self) -> None:
        base = SUPABASE_URL.rstrip("/")
        self._rest = f"{base}/rest/v1"
        self._rpc_base = f"{base}/rest/v1/rpc"
        self._headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
        }
        self._http = get_rest_client()

    def _get(self, path: str, params: Optional[dict[str, str]] = None) -> httpx.Response:
        return self._http.get(f"{self._rest}{path}", headers=self._headers, params=params or {})

    def _patch(self, path: str, payload: dict[str, Any], params: Optional[dict[str, str]] = None) -> httpx.Response:
        return self._http.patch(
            f"{self._rest}{path}",
            headers={**self._headers, "Prefer": "return=minimal"},
            params=params or {},
            content=json.dumps(payload),
        )

    def _post(self, path: str, payload: Any, params: Optional[dict[str, str]] = None) -> httpx.Response:
        return self._http.post(
            f"{self._rest}{path}",
            headers={**self._headers, "Prefer": "return=representation"},
            params=params or {},
            content=json.dumps(payload),
        )

    def rpc(self, fn: str, payload: dict[str, Any]) -> httpx.Response:
        return self._http.post(
            f"{self._rpc_base}/{fn}",
            headers=self._headers,
            content=json.dumps(payload),
        )

    def get_runtime_setting_text(self, setting_key: str) -> Optional[str]:
        r = self._get(
            "/runtime_settings",
            {
                "setting_key": f"eq.{setting_key}",
                "select": "setting_value_text",
                "limit": "1",
            },
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return None
        v = rows[0].get("setting_value_text")
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    def get_bot(self, bot_id: str) -> Optional[dict[str, Any]]:
        r = self._get(
            "/bots",
            {"id": f"eq.{bot_id}", "select": "id,workspace_id,metadata,system_prompt"},
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None

    def get_bot_channel(
        self,
        workspace_id: str,
        bot_id: str,
        platform: str,
    ) -> Optional[dict[str, Any]]:
        r = self._get(
            "/bot_channels",
            {
                "workspace_id": f"eq.{workspace_id}",
                "bot_id": f"eq.{bot_id}",
                "platform": f"eq.{platform}",
                "select": ",".join(
                    [
                        "id",
                        "workspace_id",
                        "bot_id",
                        "platform",
                        "status",
                        "page_id",
                        "external_account_id",
                        "webhook_verify_token",
                        "telegram_webhook_path_secret",
                        "webhook_connection_state",
                        "config",
                    ]
                ),
            },
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None

    def get_chat_session_by_id(self, session_id: str) -> Optional[dict[str, Any]]:
        r = self._get(
            "/chat_sessions",
            {
                "id": f"eq.{session_id}",
                "select": "id,workspace_id,bot_id,platform,customer_external_id,customer_name,session_metadata",
                "limit": "1",
            },
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None

    def find_chat_session(
        self,
        workspace_id: str,
        bot_id: str,
        platform: str,
        customer_external_id: str,
    ) -> Optional[dict[str, Any]]:
        r = self._get(
            "/chat_sessions",
            {
                "workspace_id": f"eq.{workspace_id}",
                "bot_id": f"eq.{bot_id}",
                "platform": f"eq.{platform}",
                "customer_external_id": f"eq.{customer_external_id}",
                "select": "id,session_metadata",
                "limit": "1",
            },
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None

    def create_chat_session(
        self,
        workspace_id: str,
        bot_id: str,
        platform: str,
        customer_external_id: str,
        customer_name: Optional[str],
        session_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        body = {
            "workspace_id": workspace_id,
            "bot_id": bot_id,
            "platform": platform,
            "customer_external_id": customer_external_id,
            "customer_name": customer_name,
            "session_metadata": session_metadata,
        }
        r = self._post("/chat_sessions", body)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            raise RuntimeError("chat_sessions insert returned no row")
        return rows[0]

    def patch_chat_session_metadata(self, session_id: str, metadata: dict[str, Any]) -> None:
        r = self._patch("/chat_sessions", {"session_metadata": metadata}, {"id": f"eq.{session_id}"})
        r.raise_for_status()

    def insert_chat_message(
        self,
        workspace_id: str,
        bot_id: str,
        chat_session_id: str,
        sender_type: str,
        message_text: str,
        raw_payload: dict[str, Any],
    ) -> None:
        r = self._post(
            "/chat_messages",
            {
                "workspace_id": workspace_id,
                "bot_id": bot_id,
                "chat_session_id": chat_session_id,
                "sender_type": sender_type,
                "message_text": message_text,
                "raw_payload": raw_payload,
            },
        )
        r.raise_for_status()

    def mark_webhook_connected(self, workspace_id: str, bot_id: str, platform: str) -> None:
        from datetime import datetime, timezone

        r = self._patch(
            "/bot_channels",
            {
                "webhook_connected_at": datetime.now(timezone.utc).isoformat(),
                "webhook_connection_state": "connected",
                "status": "connected",
            },
            {
                "workspace_id": f"eq.{workspace_id}",
                "bot_id": f"eq.{bot_id}",
                "platform": f"eq.{platform}",
            },
        )
        r.raise_for_status()

    def bump_stats(
        self,
        workspace_id: str,
        bot_id: str,
        platform: str,
        inbound: int = 0,
        outbound: int = 0,
    ) -> None:
        r = self.rpc(
            "webhook_increment_message_stats",
            {
                "p_workspace_id": workspace_id,
                "p_bot_id": bot_id,
                "p_platform": platform,
                "p_inbound_delta": inbound,
                "p_outbound_delta": outbound,
            },
        )
        r.raise_for_status()

    def workspace_for_bot(self, bot_id: str) -> Optional[str]:
        bot = self.get_bot(bot_id)
        return str(bot["workspace_id"]) if bot else None

    def user_can_manage_bot_channels(self, user_id: str, workspace_id: str) -> bool:
        r = self._get(
            "/workspace_members",
            {
                "workspace_id": f"eq.{workspace_id}",
                "user_id": f"eq.{user_id}",
                "select": "role,is_active",
                "limit": "1",
            },
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return False
        row = rows[0]
        if row.get("is_active") is False:
            return False
        role = str(row.get("role") or "")
        return role in ("owner", "admin", "manager", "operator")

    def user_is_active_workspace_member(self, user_id: str, workspace_id: str) -> bool:
        r = self._get(
            "/workspace_members",
            {
                "workspace_id": f"eq.{workspace_id}",
                "user_id": f"eq.{user_id}",
                "select": "is_active",
                "limit": "1",
            },
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return False
        return rows[0].get("is_active") is not False

    def upsert_facebook_provision(
        self,
        workspace_id: str,
        bot_id: str,
        page_id: str,
        verify_token: str,
    ) -> None:
        existing = self.get_bot_channel(workspace_id, bot_id, "facebook")
        patch: dict[str, Any] = {
            "webhook_verify_token": verify_token,
            "webhook_connection_state": "provisioned",
            "status": "disconnected",
        }
        if page_id:
            patch["page_id"] = page_id
        elif not existing:
            patch["page_id"] = None
        if existing:
            r = self._patch("/bot_channels", patch, {"id": f"eq.{existing['id']}"})
        else:
            body = {
                "workspace_id": workspace_id,
                "bot_id": bot_id,
                "platform": "facebook",
                "config": {},
                **patch,
            }
            r = self._post("/bot_channels", body)
        r.raise_for_status()

    def patch_facebook_channel(
        self,
        workspace_id: str,
        bot_id: str,
        fields: dict[str, Any],
    ) -> None:
        r = self._patch(
            "/bot_channels",
            fields,
            {
                "workspace_id": f"eq.{workspace_id}",
                "bot_id": f"eq.{bot_id}",
                "platform": "eq.facebook",
            },
        )
        r.raise_for_status()

    def disconnect_facebook_channel(self, workspace_id: str, bot_id: str) -> None:
        self.patch_facebook_channel(
            workspace_id,
            bot_id,
            {
                "webhook_verify_token": None,
                "webhook_connected_at": None,
                "webhook_connection_state": "none",
                "status": "disconnected",
            },
        )

    def get_bot_workspace_id(self, bot_id: str) -> Optional[str]:
        bot = self.get_bot(bot_id)
        if not bot:
            return None
        return str(bot.get("workspace_id") or "").strip() or None

    def find_payment_by_provider_tx(self, payment_provider: str, transaction_id: str) -> Optional[dict[str, Any]]:
        r = self._get(
            "/payments",
            {
                "payment_provider": f"eq.{payment_provider}",
                "transaction_id": f"eq.{transaction_id}",
                "select": "id,status",
                "limit": "1",
            },
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None

    def get_bot_subscription_row(self, workspace_id: str, bot_id: str) -> Optional[dict[str, Any]]:
        r = self._get(
            "/bot_subscriptions",
            {
                "workspace_id": f"eq.{workspace_id}",
                "bot_id": f"eq.{bot_id}",
                "select": "id,plan_code,workspace_id,bot_id",
                "limit": "1",
            },
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None

    def insert_payment_row(self, row: dict[str, Any]) -> None:
        r = self._post("/payments", [row])
        r.raise_for_status()

    def patch_bot_subscription_by_bot(self, workspace_id: str, bot_id: str, fields: dict[str, Any]) -> None:
        r = self._patch(
            "/bot_subscriptions",
            fields,
            {"workspace_id": f"eq.{workspace_id}", "bot_id": f"eq.{bot_id}"},
        )
        r.raise_for_status()

    def patch_bot_row(self, workspace_id: str, bot_id: str, fields: dict[str, Any]) -> None:
        r = self._patch(
            "/bots",
            fields,
            {"id": f"eq.{bot_id}", "workspace_id": f"eq.{workspace_id}"},
        )
        r.raise_for_status()
