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

# Fallback reply when Dify or outbound send fails.
DEFAULT_BOT_REPLY = os.environ.get(
    "DEFAULT_BOT_REPLY",
    "Thanks — we received your message and will get back to you shortly.",
).strip()

# Dify chat uses the same API key pattern as the assigned pool (provider_api_key in bots.metadata).
DIFY_CHAT_TIMEOUT = float(os.environ.get("DIFY_CHAT_TIMEOUT", "90"))

# Comma-separated origins for flask-cors (e.g. https://app.clybotics.com,http://localhost:8080). Use * for dev only.
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
