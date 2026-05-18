from __future__ import annotations

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from config import CORS_ORIGINS
from routes.facebook_route import bp as facebook_bp
from routes.instagram_route import bp as instagram_bp
from routes.internal_conversation import bp as internal_conversation_bp
from routes.internal_facebook import bp as internal_facebook_bp
from routes.internal_instagram import bp as internal_instagram_bp
from routes.internal_whatsapp import bp as internal_whatsapp_bp
from routes.internal_lemon import bp as internal_lemon_bp
from routes.internal_website import bp as internal_website_bp
from routes.lemon_webhook import bp as lemon_webhook_bp
from routes.telegram_route import bp as telegram_bp
from routes.website_public import bp as website_public_bp
from routes.whatsapp_route import bp as whatsapp_bp


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(
        app,
        resources={r"/*": {"origins": CORS_ORIGINS or ["*"]}},
        allow_headers=["Authorization", "Content-Type"],
        methods=["GET", "POST", "OPTIONS"],
    )
    app.register_blueprint(facebook_bp)
    app.register_blueprint(instagram_bp)
    app.register_blueprint(whatsapp_bp)
    app.register_blueprint(telegram_bp)
    app.register_blueprint(internal_facebook_bp)
    app.register_blueprint(internal_instagram_bp)
    app.register_blueprint(internal_whatsapp_bp)
    app.register_blueprint(internal_conversation_bp)
    app.register_blueprint(internal_website_bp)
    app.register_blueprint(internal_lemon_bp)
    app.register_blueprint(lemon_webhook_bp)
    app.register_blueprint(website_public_bp)

    @app.get("/")
    def home():
        html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Clybotics Channel Webhooks</title>
  <style>
    :root { color-scheme: dark; --bg: #0b1220; --card: #111a2e; --border: #1e2d4a; --text: #e8eef7; --muted: #8fa3bf; --accent: #22d3ee; --accent-dim: #0891b2; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      min-height: 100vh; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      background: radial-gradient(ellipse 80% 60% at 50% -10%, rgba(34,211,238,.12), transparent), var(--bg);
      color: var(--text); display: flex; align-items: center; justify-content: center; padding: 1.5rem;
    }
    .wrap { width: 100%; max-width: 32rem; }
    .badge {
      display: inline-flex; align-items: center; gap: .5rem; font-size: .75rem; font-weight: 600;
      letter-spacing: .04em; text-transform: uppercase; color: var(--accent); margin-bottom: 1rem;
    }
    .dot { width: .5rem; height: .5rem; border-radius: 999px; background: #34d399; box-shadow: 0 0 12px #34d399; }
    h1 { font-size: 1.75rem; font-weight: 700; line-height: 1.2; margin-bottom: .75rem; }
    p { color: var(--muted); line-height: 1.6; font-size: .95rem; margin-bottom: 1rem; }
    .card {
      background: var(--card); border: 1px solid var(--border); border-radius: 12px;
      padding: 1.25rem 1.35rem; margin-top: 1.25rem;
    }
    .card h2 { font-size: .8rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-bottom: .75rem; }
    ul { list-style: none; font-size: .875rem; }
    li { padding: .35rem 0; border-bottom: 1px solid var(--border); color: var(--muted); }
    li:last-child { border-bottom: none; }
    li code { color: var(--accent); font-size: .8rem; }
    .actions { display: flex; flex-wrap: wrap; gap: .75rem; margin-top: 1.25rem; }
    a.btn {
      display: inline-flex; align-items: center; justify-content: center; padding: .55rem 1rem;
      border-radius: 8px; font-size: .875rem; font-weight: 600; text-decoration: none; transition: opacity .15s;
    }
    a.btn-primary { background: linear-gradient(135deg, var(--accent), var(--accent-dim)); color: #042f2e; }
    a.btn-ghost { border: 1px solid var(--border); color: var(--text); }
    a.btn:hover { opacity: .9; }
    footer { margin-top: 1.5rem; font-size: .75rem; color: var(--muted); text-align: center; }
  </style>
</head>
<body>
  <main class="wrap">
    <div class="badge"><span class="dot"></span> Service online</div>
    <h1>Clybotics Channel Webhooks</h1>
    <p>This host receives Messenger, Instagram, WhatsApp, and Telegram events for your bots. Configure callback URLs in the Clybotics dashboard — not on this page.</p>
    <div class="card">
      <h2>Quick links</h2>
      <ul>
        <li>Health check → <code>GET /health</code></li>
        <li>Messenger → <code>/v1/facebook/&lt;bot_id&gt;</code></li>
        <li>Instagram → <code>/v1/instagram/&lt;bot_id&gt;</code></li>
        <li>WhatsApp → <code>/v1/whatsapp/&lt;bot_id&gt;</code></li>
      </ul>
    </div>
    <div class="actions">
      <a class="btn btn-primary" href="/health">View health JSON</a>
      <a class="btn btn-ghost" href="https://app.clybotics.com" rel="noopener noreferrer">Open dashboard</a>
    </div>
    <footer>© Clybotics · API service only</footer>
  </main>
</body>
</html>"""
        return Response(html, mimetype="text/html; charset=utf-8")

    @app.get("/health")
    def health():
        payload: dict = {"status": "ok", "service": "clybotics-channel-webhooks"}
        if request.args.get("dify", "").lower() in ("1", "true", "yes"):
            from services.inbound_pipeline import dify_fallback_health_info
            from services.supabase_client import SupabaseRest

            try:
                payload["dify_fallback"] = dify_fallback_health_info(SupabaseRest())
            except Exception as e:  # noqa: BLE001
                payload["dify_fallback"] = {"error": str(e)[:200]}
        return jsonify(payload), 200

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(__import__("os").environ.get("PORT", "5055")), debug=False)
