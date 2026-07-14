"""Broker error taxonomy.

We classify errors so the execution engine can decide auto-retry vs alert.
"""


class BrokerError(RuntimeError):
    """Base class for all broker errors."""


class AuthError(BrokerError):
    """Authentication / authorization failed. Not retryable without user action."""


class RateLimitError(BrokerError):
    """Rate limit hit. Retryable with backoff."""


class TransientBrokerError(BrokerError):
    """Network / 5xx / timeouts. Retryable with backoff."""


class OrderRejectedError(BrokerError):
    """Structural rejection (margin, price band, contract). Not auto-retryable."""

    def __init__(self, reason: str, code: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.code = code
