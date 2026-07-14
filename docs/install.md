# Install Guide

## Requirements

- **Python 3.12+**
- **Git**
- (Optional) **Docker Desktop** — only if you want to run Redis / Postgres in containers.

## Steps

```bash
git clone <this-repo>
cd trader
python install.py
```

`install.py` will:

1. Verify Python version.
2. Create `.venv/` and install dependencies (uses `uv` if present; falls back to `pip`).
3. Ensure `~/.trader/` exists with a `config.yaml` copied from `config/config.example.yaml`.
4. Prompt for broker + notification secrets and store them encrypted in `~/.trader/secrets.enc`.
5. Run `alembic upgrade head` to create the schema in `~/.trader/trader.db`.
6. Optionally bring up Redis via Docker (`docker compose up -d redis`).
7. Print next steps.

## Getting broker credentials

**Dhan** — login to <https://dhan.co>, generate an access token from `Profile → API Access → Generate Token`. Note your Client ID from the same page.

**Groww** (optional failover) — API keys are only available on the Pro plan. Generate under `Profile → Account → API`. Copy the `API Key` and `API Secret`.

**Telegram** (optional notifications) —

1. Talk to `@BotFather` on Telegram, `/newbot`, follow the prompts, save the token.
2. Message your new bot once from your personal account.
3. Fetch your chat id from `https://api.telegram.org/bot<TOKEN>/getUpdates` — copy the `chat.id` field.

**SMTP** (optional email) — For Gmail, enable 2FA and create an "App password". Use that as the SMTP password.

## Running

```bash
# Windows
.venv\Scripts\activate
python run.py

# macOS / Linux
source .venv/bin/activate
python run.py
```

Dashboard: <http://127.0.0.1:8000>

## Docker (optional)

Bring up Redis:

```bash
docker compose up -d redis
```

All services (Redis, Postgres, Grafana, Prometheus):

```bash
docker compose --profile postgres --profile observability up -d
```

## Uninstall

```bash
rm -rf .venv ~/.trader logs
```
