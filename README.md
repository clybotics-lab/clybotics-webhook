# clybotics-webhook

Clybotics **channel webhooks** service (Flask): Facebook Messenger, WhatsApp Cloud, Telegram, plus authenticated internal routes for dashboard provisioning.

Synced from the `flask-webhooks` app in the main Clybotics monorepo.

## Deploy on Vercel

1. Import this repository in [Vercel](https://vercel.com).
2. **Root directory**: repository root (default).
3. Under **Settings → Environment Variables**, add every variable from [`.env.example`](./.env.example) (use real values for production). Required: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`.
4. Deploy. Your base URL will look like `https://<project>.vercel.app`.

### Dashboard / frontend

Set **`VITE_CHANNEL_WEBHOOK_BASE_URL`** (or equivalent) to that base URL **with no trailing slash**, e.g. `https://<project>.vercel.app`.

### Health check

`GET /health` → `{"status":"ok","service":"clybotics-channel-webhooks"}`

### Routes (reference)

- `GET|POST /v1/facebook/<bot_id>` — Meta webhook
- `GET|POST /v1/whatsapp/<bot_id>` — WhatsApp Cloud webhook
- `POST /v1/telegram/<bot_id>/<secret>` — Telegram webhook
- `POST /internal/v1/facebook/*` — Dashboard (JWT) provisioning

## Local run

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
copy .env.example .env   # then edit .env
python app.py
```

Default port: `5055` (or `PORT` env).

## Repository

<https://github.com/clybotics-lab/clybotics-webhook>
