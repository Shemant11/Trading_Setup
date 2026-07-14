"""Notification channels (Telegram, email) + dispatcher.

All senders implement `Notifier` and fail *closed*: exceptions are logged but
never propagate — a broken Telegram must never crash the trader.
"""

from trader.notifications.base import Notifier, NotifierMessage, Severity
from trader.notifications.telegram import TelegramNotifier
from trader.notifications.email import EmailNotifier
from trader.notifications.dispatcher import NotificationDispatcher, LoggingNotifier

__all__ = [
    "Notifier",
    "NotifierMessage",
    "Severity",
    "TelegramNotifier",
    "EmailNotifier",
    "NotificationDispatcher",
    "LoggingNotifier",
]
