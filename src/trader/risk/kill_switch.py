"""Kill switch — three redundant channels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from trader.observability.metrics import KILL_SWITCH_ACTIVE
from trader.storage.redis_client import RedisClient


@dataclass
class KillSwitch:
    """Any of file / Redis / manual override triggers a halt.

    The engine polls `active()` on every risk check; the API and Telegram
    handlers set/unset the file and Redis flag.
    """

    halt_file: Path
    redis: Optional[RedisClient] = None
    _manual: bool = False

    def activate(self, reason: str = "manual") -> None:
        self._manual = True
        try:
            self.halt_file.parent.mkdir(parents=True, exist_ok=True)
            self.halt_file.write_text(reason)
        except OSError:  # pragma: no cover
            pass
        KILL_SWITCH_ACTIVE.set(1)

    def deactivate(self) -> None:
        self._manual = False
        if self.halt_file.exists():
            try:
                self.halt_file.unlink()
            except OSError:  # pragma: no cover
                pass
        KILL_SWITCH_ACTIVE.set(0)

    async def active(self) -> bool:
        if self._manual or self.halt_file.exists():
            KILL_SWITCH_ACTIVE.set(1)
            return True
        if self.redis is not None:
            if await self.redis.get_flag("trader:halt"):
                KILL_SWITCH_ACTIVE.set(1)
                return True
        KILL_SWITCH_ACTIVE.set(0)
        return False
