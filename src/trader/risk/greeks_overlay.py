"""Greeks-aware risk overlay.

Sits on top of the base RiskEngine to enforce book-level Greek limits from
the plan:

* |Δ_₹| ≤ max_net_delta_pct * NAV
* |ν|   ≤ 0.5 % NAV per 1 vol pt
* Θ     ∈ [-0.3 %, +0.3 %] NAV/day
* Γ_₹   reject if adding trade moves |Γ_₹| > 10% NAV per 1% underlying move
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GreeksBook:
    delta_rupees: float = 0.0
    vega: float = 0.0            # per 1 vol point
    theta_per_day: float = 0.0
    gamma_rupees: float = 0.0    # per 1% underlying move


@dataclass
class GreekLimits:
    max_delta_pct: float = 0.20
    max_vega_pct: float = 0.005
    max_theta_pos_pct: float = 0.003
    max_theta_neg_pct: float = 0.003
    max_gamma_pct: float = 0.10


@dataclass
class GreeksOverlay:
    nav: float
    limits: GreekLimits = field(default_factory=GreekLimits)
    book: GreeksBook = field(default_factory=GreeksBook)

    def would_breach(
        self,
        *,
        delta_delta: float,
        vega_delta: float,
        theta_delta: float,
        gamma_delta: float,
    ) -> Optional[str]:
        proj_delta = self.book.delta_rupees + delta_delta
        proj_vega = self.book.vega + vega_delta
        proj_theta = self.book.theta_per_day + theta_delta
        proj_gamma = self.book.gamma_rupees + gamma_delta
        if abs(proj_delta) > self.limits.max_delta_pct * self.nav:
            return "delta_cap"
        if abs(proj_vega) > self.limits.max_vega_pct * self.nav:
            return "vega_cap"
        if proj_theta > self.limits.max_theta_pos_pct * self.nav:
            return "theta_pos_cap"
        if proj_theta < -self.limits.max_theta_neg_pct * self.nav:
            return "theta_neg_cap"
        if abs(proj_gamma) > self.limits.max_gamma_pct * self.nav:
            return "gamma_cap"
        return None

    def apply(
        self,
        *,
        delta_delta: float,
        vega_delta: float,
        theta_delta: float,
        gamma_delta: float,
    ) -> None:
        self.book.delta_rupees += delta_delta
        self.book.vega += vega_delta
        self.book.theta_per_day += theta_delta
        self.book.gamma_rupees += gamma_delta
