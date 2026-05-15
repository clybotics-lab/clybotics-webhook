import os

from dotenv import load_dotenv

load_dotenv()


def _req(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v


SUPABASE_URL = _req("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = _req("SUPABASE_SERVICE_ROLE_KEY")
# Used to validate end-user JWT from the dashboard on /internal/* routes.
SUPABASE_ANON_KEY = _req("SUPABASE_ANON_KEY")

# Optional: verify X-Hub-Signature-256 for Meta webhooks (single app secret).
META_APP_SECRET = os.environ.get("META_APP_SECRET", "").strip()

# Optional: require this header on all POST webhooks (extra gate in addition to per-bot tokens).
WEBHOOK_GATE_SECRET = os.environ.get("WEBHOOK_GATE_SECRET", "").strip()

# Optional: require X-Clybotics-Website-Secret on POST /webhooks/v1/website/message (recommended in production).
WEBSITE_WIDGET_GATE_SECRET = os.environ.get("WEBSITE_WIDGET_GATE_SECRET", "").strip()

# When bots.metadata has no difyBaseUrl: use this env first, then runtime_settings.dify_server_base_url (see inbound_pipeline).
DIFY_DEFAULT_BASE_URL = os.environ.get("DIFY_DEFAULT_BASE_URL", "").strip()

# Cache duration (seconds) for the DB global Dify base URL per worker process.
DIFY_RUNTIME_BASE_CACHE_SECONDS = float(os.environ.get("DIFY_RUNTIME_BASE_CACHE_SECONDS", "300"))

# Dify chat uses the same API key pattern as the assigned pool (provider_api_key in bots.metadata).
DIFY_CHAT_TIMEOUT = float(os.environ.get("DIFY_CHAT_TIMEOUT", "90"))

# 1 = acknowledge Meta/Telegram/WhatsApp webhooks immediately; process in a background thread (not for Vercel serverless).
WEBHOOK_ASYNC_PROCESSING = os.environ.get("WEBHOOK_ASYNC_PROCESSING", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Comma-separated origins for flask-cors (e.g. https://app.clybotics.com,http://localhost:8080). Use * for dev only.
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]

# Lemon Squeezy (optional — leave unset to disable checkout + webhook routes).
LEMONSQUEEZY_API_KEY = os.environ.get("LEMONSQUEEZY_API_KEY", "").strip()
LEMONSQUEEZY_WEBHOOK_SECRET = os.environ.get("LEMONSQUEEZY_WEBHOOK_SECRET", "").strip()
LEMONSQUEEZY_STORE_ID = os.environ.get("LEMONSQUEEZY_STORE_ID", "").strip()
LEMONSQUEEZY_VARIANT_STARTER = os.environ.get("LEMONSQUEEZY_VARIANT_STARTER", "1654766").strip()
LEMONSQUEEZY_VARIANT_PRO = os.environ.get("LEMONSQUEEZY_VARIANT_PRO", "1654789").strip()
LEMONSQUEEZY_CHECKOUT_SUCCESS_URL = os.environ.get("LEMONSQUEEZY_CHECKOUT_SUCCESS_URL", "https://app.clybotics.com").strip()
