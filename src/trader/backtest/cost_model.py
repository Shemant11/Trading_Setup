"""Transaction cost + slippage models.

Cost model returns the *total* explicit cost (brokerage + STT + exchange + GST
+ SEBI + stamp duty) for a fill. Impact model returns *implicit* cost in bps.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Protocol

from trader.core.enums import AssetClass, OrderSide, ProductType


class CostModel(Protocol):
    def fee_for(
        self, *, notional: float, side: OrderSide, product: ProductType,
        asset_class: AssetClass
    ) -> float: ...


class ImpactModel(Protocol):
    def impact_bps(self, *, size: float, adv_shares: float, spread_bps: float) -> float: ...


@dataclass(frozen=True)
class DhanCostModel:
    """Dhan brokerage schedule (INR).

    Rough approximation of Dhan's current retail schedule + statutory charges.
    These are captured here so they can be updated in one place and appear
    consistently in both backtest and paper reports.
    """

    equity_intraday_brokerage: float = 20.0      # ₹20/order or 0.03%, whichever lower
    equity_intraday_pct: float = 0.0003
    equity_delivery_brokerage: float = 0.0       # zero-brokerage delivery
    futures_brokerage: float = 20.0
    options_brokerage: float = 20.0
    stt_equity_intraday_pct: float = 0.00025     # sell-only
    stt_equity_delivery_pct: float = 0.001       # buy+sell
    stt_futures_pct: float = 0.0002              # sell-only
    stt_options_pct: float = 0.0005              # premium, sell-side; 0.125% on exercised
    exchange_txn_pct: float = 0.0000345          # NSE cash
    exchange_txn_futures_pct: float = 0.00002
    exchange_txn_options_pct: float = 0.0005
    sebi_pct: float = 0.000001                   # ₹10 per crore
    gst_pct: float = 0.18                        # on brokerage + exchange + sebi
    stamp_duty_buy_pct_equity: float = 0.00003
    stamp_duty_buy_pct_futures: float = 0.00002
    stamp_duty_buy_pct_options: float = 0.00003

    def fee_for(
        self,
        *,
        notional: float,
        side: OrderSide,
        product: ProductType,
        asset_class: AssetClass,
    ) -> float:
        notional = abs(notional)
        is_buy = side == OrderSide.BUY
        # ---- Brokerage -----------------------------------------------------
        if asset_class == AssetClass.EQUITY:
            if product == ProductType.MIS:
                brokerage = min(self.equity_intraday_brokerage,
                                notional * self.equity_intraday_pct)
            else:
                brokerage = self.equity_delivery_brokerage
        elif asset_class == AssetClass.FUTURE:
            brokerage = self.futures_brokerage
        elif asset_class == AssetClass.OPTION:
            brokerage = self.options_brokerage
        else:
            brokerage = 0.0
        # ---- STT -----------------------------------------------------------
        stt = 0.0
        if asset_class == AssetClass.EQUITY:
            if product == ProductType.MIS and not is_buy:
                stt = notional * self.stt_equity_intraday_pct
            elif product == ProductType.CNC:
                stt = notional * self.stt_equity_delivery_pct
        elif asset_class == AssetClass.FUTURE and not is_buy:
            stt = notional * self.stt_futures_pct
        elif asset_class == AssetClass.OPTION and not is_buy:
            stt = notional * self.stt_options_pct
        # ---- Exchange -----------------------------------------------------
        if asset_class == AssetClass.EQUITY:
            exch = notional * self.exchange_txn_pct
        elif asset_class == AssetClass.FUTURE:
            exch = notional * self.exchange_txn_futures_pct
        elif asset_class == AssetClass.OPTION:
            exch = notional * self.exchange_txn_options_pct
        else:
            exch = 0.0
        # ---- SEBI ---------------------------------------------------------
        sebi = notional * self.sebi_pct
        # ---- GST ----------------------------------------------------------
        gst = (brokerage + exch + sebi) * self.gst_pct
        # ---- Stamp duty (buy only) ----------------------------------------
        stamp = 0.0
        if is_buy:
            if asset_class == AssetClass.EQUITY:
                stamp = notional * self.stamp_duty_buy_pct_equity
            elif asset_class == AssetClass.FUTURE:
                stamp = notional * self.stamp_duty_buy_pct_futures
            elif asset_class == AssetClass.OPTION:
                stamp = notional * self.stamp_duty_buy_pct_options
        return brokerage + stt + exch + sebi + gst + stamp


@dataclass(frozen=True)
class LinearImpactModel:
    """impact_bps = k * sqrt(size / ADV) + half_spread.

    Simple square-root impact — the standard first-order model.
    """

    k_bps: float = 10.0          # square-root coefficient in bps
    include_half_spread: bool = True

    def impact_bps(self, *, size: float, adv_shares: float, spread_bps: float) -> float:
        if adv_shares <= 0:
            return spread_bps if self.include_half_spread else 0.0
        core = self.k_bps * sqrt(max(size, 0) / adv_shares) * 100.0
        half = (spread_bps / 2.0) if self.include_half_spread else 0.0
        return core + half
