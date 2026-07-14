# Options strategies

**Governing rule:** No naked short options.

Strategy family chosen by **IV rank**:

| IV Rank | Regime                | Strategy                     |
|---------|-----------------------|------------------------------|
| < 30    | Trending              | Debit spread (ATM/ATM+1)     |
| < 30    | Range + event pending | Long straddle                |
| 30–70   | Trending              | Debit spread                 |
| 30–70   | Range                 | Iron condor at ±1.5σ         |
| > 70    | Range                 | Iron fly / narrow condor     |
| > 70    | Trending              | Sit out                      |
| Expiry  | Pin regime            | Butterfly at expected pin    |

## `options_iron_condor`

Enters only when `IVR > 70`. Short strikes at ±1.2× expected move, wings at
±2× expected move. All 4 legs are defined-risk. Size = NAV × 0.5 % / max
loss per lot.

## `options_debit_spread`

Bull-call or bear-put, ATM long + one-strike-OTM short. Runs when
`IVR < 30`. Direction from external bias (regime classifier or discretionary).

## `options_expiry_butterfly`

Weekly expiry days on BANKNIFTY (and any other approved index). Entry 10:30
IST, hard exit 14:30 IST. Center of butterfly at max-pain strike; wings at
`center ± wing_width` (default ±100).

## Book-level greek limits

Enforced by `GreeksOverlay` on top of `RiskEngine`:

* `|Δ_₹| ≤ 20 % NAV`
* `|ν| ≤ 0.5 % NAV per 1 vol pt`
* `Θ ∈ [−0.3 %, +0.3 %] NAV/day`
* `Γ_₹`: reject if trade would move `|Γ_₹|` above 10 % NAV per 1 % underlying move.
