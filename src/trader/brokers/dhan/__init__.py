"""Dhan broker adapter.

Split across files to stay < 300 lines each:

* `client.py`  — the `Broker` implementation glueing REST + WS + mapping.
* `rest.py`    — thin async HTTP client for Dhan REST API v2.
* `websocket.py` — market feed + order update WS clients.
* `mapping.py` — enum/string translation between our domain and Dhan wire format.
"""

from trader.brokers.dhan.client import DhanClient

__all__ = ["DhanClient"]
