# trader.config

* `settings.py` — `Settings` (env-driven runtime + paths).
* `loader.py` — YAML → strongly-typed `AppConfig` (Pydantic v2).
* `secrets.py` — Argon2id + AES-256-GCM local encrypted secrets file at `~/.trader/secrets.enc`.
