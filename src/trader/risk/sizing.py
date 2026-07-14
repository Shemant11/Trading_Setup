"""Position sizing utilities.

Two co-equal sizers:

* Fractional Kelly given win_rate + win/loss ratio.
* Volatility-normalized target position size.

Final size = min(Kelly-based size, vol-cap size).
"""

from __future__ import annotations

import math


def kelly_fraction(win_rate: float, win_loss_ratio: float) -> float:
    """Classical Kelly criterion.

    f* = (b*p - (1-p)) / b, where b = win_loss_ratio, p = win_rate.
    Clamped to [0, 1] and returned as a *fraction of capital*.
    """
    if not (0.0 <= win_rate <= 1.0) or win_loss_ratio <= 0:
        return 0.0
    f = (win_loss_ratio * win_rate - (1.0 - win_rate)) / win_loss_ratio
    return max(0.0, min(1.0, f))


def fractional_kelly_size(
    nav: float,
    win_rate: float,
    win_loss_ratio: float,
    fraction: float,
    risk_per_unit: float,
) -> int:
    """Number of units to trade under a fractional-Kelly sizing rule.

    * `fraction` typically 0.25 (quarter-Kelly).
    * `risk_per_unit` = |entry - stop|.
    """
    if nav <= 0 or risk_per_unit <= 0:
        return 0
    kelly_f = kelly_fraction(win_rate, win_loss_ratio)
    dollars_at_risk = nav * kelly_f * fraction
    return max(0, int(dollars_at_risk // risk_per_unit))


def vol_normalized_size(
    nav: float,
    price: float,
    daily_vol_pct: float,
    target_daily_vol_pct: float,
) -> int:
    """Size such that expected daily position volatility = target_daily_vol_pct * NAV.

    daily_vol_pct: daily return std dev of the instrument (e.g. 0.015 for 1.5%).
    """
    if price <= 0 or daily_vol_pct <= 0 or target_daily_vol_pct <= 0:
        return 0
    daily_vol_rupees = daily_vol_pct * price
    target_vol_rupees = target_daily_vol_pct * nav
    return max(0, int(target_vol_rupees // daily_vol_rupees))


def cap_size_by_notional(
    nav: float,
    price: float,
    max_pct: float,
) -> int:
    """Cap by max % of NAV in one position (e.g. 0.10)."""
    if price <= 0:
        return 0
    max_rupees = nav * max_pct
    return max(0, int(max_rupees // price))
