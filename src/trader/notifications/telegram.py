"""Telegram Bot API notifier.

Uses the free Bot API — no polling; we only send. Chat IDs must be known
in advance (see docs/install.md for how to obtain them).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import httpx

from trader.notifications.base import Notifier, NotifierMessage, Severity
from trader.observability.logging import get_logger

logger = get_logger("trader.notify.telegram")


@dataclass
class TelegramNotifier(Notifier):
    bot_token: str
    chat_ids: list[str]
    min_severity: Severity = Severity.INFO
    api_base: str = "https://api.telegram.org"
    timeout: float = 5.0
    name: str = "telegram"
    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def send(self, msg: NotifierMessage) -> bool:
        if msg.severity < self.min_severity:
            return False
        if not self.chat_ids or not self.bot_token:
            return False
        text = msg.format_plain()
        # Telegram messages max 4096 chars; truncate defensively.
        if len(text) > 3900:
            text = text[:3900] + "\n...(truncated)"
        url = f"{self.api_base}/bot{self.bot_token}/sendMessage"
        sent_any = False
        for chat_id in self.chat_ids:
            try:
                r = await self._http().post(
                    url,
                    data={"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"},
                )
                if r.status_code == 200:
                    sent_any = True
                else:
                    logger.warning(
                        "telegram_send_failed",
                        status=r.status_code,
                        chat_id=chat_id,
                        body=r.text[:200],
                    )
            except Exception as e:  # noqa: BLE001 - fail closed
                logger.warning("telegram_send_exception", error=str(e), chat_id=chat_id)
        return sent_any
