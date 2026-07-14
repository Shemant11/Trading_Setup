"""Daily / EOD reporting.

Generates a human-readable Markdown summary + delivers via the notification
dispatcher. Also feeds a JSON payload for the dashboard.
"""

from trader.reporting.eod import EodReport, generate_eod_report

__all__ = ["EodReport", "generate_eod_report"]
