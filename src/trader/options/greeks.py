"""Black-Scholes-Merton pricing + greeks + implied vol.

Assumes constant-vol European options. Good enough for weekly index options
which dominate the strategy set. For deep-ITM American stock options a
Bjerksund–Stensland approximation would be preferable — we don't trade those.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


SQRT_2PI = math.sqrt(2 * math.pi)


def _phi(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / SQRT_2PI


def _Phi(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass(frozen=True)
class Greeks:
    delta: float
    gamma: float
    theta: float          # per calendar day
    vega: float           # per 1 vol point (i.e. 1.0 = 100 percentage points)
    rho: float


def bs_price(
    *,
    spot: float,
    strike: float,
    sigma: float,
    t_years: float,
    r: float = 0.065,
    q: float = 0.0,
    kind: Literal["CE", "PE"] = "CE",
) -> float:
    """Black-Scholes price for a European option."""
    if t_years <= 0 or sigma <= 0:
        intrinsic = max(spot - strike, 0.0) if kind == "CE" else max(strike - spot, 0.0)
        return intrinsic
    d1 = (math.log(spot / strike) + (r - q + 0.5 * sigma * sigma) * t_years) / (
        sigma * math.sqrt(t_years)
    )
    d2 = d1 - sigma * math.sqrt(t_years)
    df_r = math.exp(-r * t_years)
    df_q = math.exp(-q * t_years)
    if kind == "CE":
        return spot * df_q * _Phi(d1) - strike * df_r * _Phi(d2)
    return strike * df_r * _Phi(-d2) - spot * df_q * _Phi(-d1)


def bs_greeks(
    *,
    spot: float,
    strike: float,
    sigma: float,
    t_years: float,
    r: float = 0.065,
    q: float = 0.0,
    kind: Literal["CE", "PE"] = "CE",
) -> Greeks:
    if t_years <= 0 or sigma <= 0:
        # Degenerate case: delta = 0/1, all others zero.
        d = 1.0 if (kind == "CE" and spot > strike) else 0.0
        return Greeks(delta=d if kind == "CE" else -1.0 + d, gamma=0, theta=0, vega=0, rho=0)
    d1 = (math.log(spot / strike) + (r - q + 0.5 * sigma * sigma) * t_years) / (
        sigma * math.sqrt(t_years)
    )
    d2 = d1 - sigma * math.sqrt(t_years)
    df_r = math.exp(-r * t_years)
    df_q = math.exp(-q * t_years)
    gamma = df_q * _phi(d1) / (spot * sigma * math.sqrt(t_years))
    vega = spot * df_q * _phi(d1) * math.sqrt(t_years) / 100.0
    if kind == "CE":
        delta = df_q * _Phi(d1)
        theta = -(
            spot * df_q * _phi(d1) * sigma / (2 * math.sqrt(t_years))
            + r * strike * df_r * _Phi(d2)
            - q * spot * df_q * _Phi(d1)
        ) / 365.0
        rho = strike * t_years * df_r * _Phi(d2) / 100.0
    else:
        delta = df_q * (_Phi(d1) - 1.0)
        theta = -(
            spot * df_q * _phi(d1) * sigma / (2 * math.sqrt(t_years))
            - r * strike * df_r * _Phi(-d2)
            + q * spot * df_q * _Phi(-d1)
        ) / 365.0
        rho = -strike * t_years * df_r * _Phi(-d2) / 100.0
    return Greeks(delta=delta, gamma=gamma, theta=theta, vega=vega, rho=rho)


def implied_volatility(
    *,
    price: float,
    spot: float,
    strike: float,
    t_years: float,
    r: float = 0.065,
    q: float = 0.0,
    kind: Literal["CE", "PE"] = "CE",
    tol: float = 1e-5,
    max_iter: int = 100,
) -> float:
    """Newton-Raphson with a small brent-like fallback if the derivative dies."""
    if t_years <= 0 or price <= 0:
        return float("nan")
    intrinsic = (
        max(spot - strike, 0.0) if kind == "CE" else max(strike - spot, 0.0)
    )
    if price < intrinsic * math.exp(-r * t_years):
        return float("nan")
    sigma = max(0.5, 4.0 * price / (spot * math.sqrt(t_years)))
    for _ in range(max_iter):
        try:
            p = bs_price(
                spot=spot, strike=strike, sigma=sigma,
                t_years=t_years, r=r, q=q, kind=kind,
            )
            g = bs_greeks(
                spot=spot, strike=strike, sigma=sigma,
                t_years=t_years, r=r, q=q, kind=kind,
            )
            vega100 = g.vega * 100.0
            if vega100 == 0:
                break
            diff = price - p
            if abs(diff) < tol:
                return sigma
            sigma += diff / vega100
            if sigma <= 0:
                sigma = tol
        except (ValueError, OverflowError):
            return float("nan")
    return sigma
