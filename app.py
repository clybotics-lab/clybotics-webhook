from __future__ import annotations

from flask import Flask, jsonify, request
from flask_cors import CORS

from config import CORS_ORIGINS
from routes.facebook_route import bp as facebook_bp
from routes.internal_facebook import bp as internal_facebook_bp
from routes.telegram_route import bp as telegram_bp
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
    app.register_blueprint(whatsapp_bp)
    app.register_blueprint(telegram_bp)
    app.register_blueprint(internal_facebook_bp)

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
