# trader.notifications

Fail-closed dispatch:

* `base.py` — `Notifier` protocol + `Severity` + `NotifierMessage`.
* `telegram.py` — Telegram Bot API sender.
* `email.py` — SMTP sender (async wraps `smtplib`).
* `dispatcher.py` — Multi-channel fan-out + rate-limited dedup + safety-net `LoggingNotifier`.
