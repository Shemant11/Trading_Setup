"""Email notifier via SMTP (Gmail-friendly).

Runs the blocking `smtplib` call in a thread to avoid blocking the loop.
"""

from __future__ import annotations

import asyncio
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from trader.notifications.base import Notifier, NotifierMessage, Severity
from trader.observability.logging import get_logger

logger = get_logger("trader.notify.email")


@dataclass
class EmailNotifier(Notifier):
    smtp_host: str
    smtp_port: int
    from_addr: str
    to_addrs: list[str]
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    min_severity: Severity = Severity.WARNING
    name: str = "email"

    def _send_sync(self, msg: NotifierMessage) -> bool:
        email_msg = EmailMessage()
        email_msg["Subject"] = f"[trader/{msg.severity.name}] {msg.title}"
        email_msg["From"] = self.from_addr
        email_msg["To"] = ", ".join(self.to_addrs)
        email_msg.set_content(msg.format_plain())

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as smtp:
                if self.use_tls:
                    smtp.starttls()
                if self.username and self.password:
                    smtp.login(self.username, self.password)
                smtp.send_message(email_msg)
            return True
        except Exception as e:  # noqa: BLE001 - fail closed
            logger.warning("email_send_failed", error=str(e))
            return False

    async def send(self, msg: NotifierMessage) -> bool:
        if msg.severity < self.min_severity:
            return False
        if not self.to_addrs:
            return False
        return await asyncio.to_thread(self._send_sync, msg)
