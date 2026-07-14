"""Tests for core domain models."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from trader.core.domain import (
    Bar,
    Instrument,
    OptionChainSnapshot,
    OptionQuote,
    Quote,
    Tick,
)
from trader.core.enums import (
    AssetClass,
    Exchange,
    OrderStatus,
    Segment,
)


def test_instrument_option_requires_fields():
    with pytest.raises(ValueError):
        Instrument(
            security_id="1",
            symbol="NIFTY25JAN23000CE",
            exchange=Exchange.NFO,
            segment=Segment.OPTIONS,
            asset_class=AssetClass.OPTION,
        )


def test_instrument_option_ok():
    inst = Instrument(
        security_id="1",
        symbol="NIFTY25JAN23000CE",
        exchange=Exchange.NFO,
        segment=Segment.OPTIONS,
        asset_class=AssetClass.OPTION,
        underlying_symbol="NIFTY",
        strike=23000,
        expiry=date(2025, 1, 30),
        option_type="CE",
    )
    assert inst.is_option


def test_bar_validation_rejects_bad_ohlc():
    with pytest.raises(ValueError):
        Bar(
            instrument_id="1",
            ts_open=datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc),
            ts_close=datetime(2025, 1, 1, 9, 16, tzinfo=timezone.utc),
            timeframe="1m",
            open=100,
            high=99,       # high < low
            low=101,
            close=100,
        )


def test_tick_spread_bps_and_microprice():
    t = Tick(
        instrument_id="1",
        ts_exchange=datetime.now(timezone.utc),
        ts_ingest=datetime.now(timezone.utc),
        ltp=100.0,
        bid=99.95,
        ask=100.05,
        bid_qty=100,
        ask_qty=300,
    )
    assert t.spread_bps == pytest.approx(10.0, rel=0.05)
    # Weighted microprice pulled toward the deeper side (asks).
    mp = t.microprice
    assert mp is not None
    assert 99.95 < mp < 100.05


def test_quote_imbalance():
    q = Quote(
        instrument_id="1",
        ts=datetime.now(timezone.utc),
        ltp=100.0,
        bids=[(99.95, 200), (99.90, 100)],
        asks=[(100.05, 100)],
    )
    assert q.imbalance == pytest.approx(0.75, rel=1e-6)


def test_order_status_terminality():
    assert OrderStatus.FILLED.is_terminal
    assert OrderStatus.REJECTED.is_terminal
    assert not OrderStatus.OPEN.is_terminal
    assert OrderStatus.OPEN.is_active


def test_option_chain_pcr():
    ts = datetime.now(timezone.utc)
    snap = OptionChainSnapshot(
        underlying="NIFTY",
        spot=23000,
        expiry=date(2025, 1, 30),
        ts=ts,
        quotes=[
            OptionQuote(strike=23000, option_type="CE", ltp=100, oi=1000, volume=100),
            OptionQuote(strike=23000, option_type="PE", ltp=100, oi=1500, volume=200),
        ],
    )
    assert snap.pcr_oi == pytest.approx(1.5)
    assert snap.pcr_volume == pytest.approx(2.0)
