# trader.core

Pure domain models. No I/O, no dependencies on other trader modules.

Structure:

- `enums.py` — string enums for order/exchange/segment/timeframe.
- `domain.py` — Pydantic models (`Instrument`, `Tick`, `Quote`, `Bar`, `Signal`, `OrderRequest`, `Order`, `Fill`, `Position`, `Trade`, option chain).
- `events.py` — Discriminated union of in-process bus events.

Invariants enforced at construction:

- `Bar.high >= Bar.low`, close/open inside range, non-negative volume.
- Option `Instrument` requires strike/expiry/type.

Everything is immutable (`frozen=True`) except `Order` and `Position`, which have a state machine.
