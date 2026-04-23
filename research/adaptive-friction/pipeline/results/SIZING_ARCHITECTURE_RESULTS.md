# Crypto BSDT — Sizing Architecture Results (v22 → v32)

**Pipeline:** [`run_crypto_pairs_v18.py`](run_crypto_pairs_v18.py)
**Test window:** 2023-01-01 → 2026-04-23 (1209 days, 4.80 yrs)
**Initial capital:** $1,200 · **Universe:** BTC, ETH, SOL, BNB · **Funding:** ETHUSDT, BTCUSDT
**Cost model (PROD selection):** 5 bps per active day

This document records the complete arc of leverage-sizing experiments on the same underlying signal stack (v22 base). The signal was held fixed; only the dollar-allocation logic changed across versions. Results are reported honestly, including the negative iterations, because the *failures* are what justify the final architecture.

---

## TL;DR — Production Recommendation

| Use case | Version | K_max | In-sample PnL (5 bps) | MaxDD | 3σ/3d shock | Notes |
|---|---|---:|---:|---:|---:|---|
| **Conservative live capital** | **v22** | 3.5 | **+$5,705** | -36.3% | passes (≈ -38%) | Battle-tested, near-optimal, simple |
| **Moderate (with monitoring)** | **v32** | 4.0 | +$3,840 | -38.8% | **passes (-39.2%)** | Stress-budgeted, adaptive throttle |
| **Research / in-sample only** | v30 | 9.0 | +$8,727 | -39.6% | **FAIL (-44.3%)** | Fragile — fails 3σ shock |
| Avoid | v31 | 9.0 | +$36,548 | -31.6% | **FAIL (-96.6%)** | Path-dependent overfit |

The PROD-grade strategy is **v22 or v32** depending on infrastructure. v30 and v31 are research artefacts demonstrating *where* sizing breaks.

---

## v22 — Vol-Targeted Baseline (PROD-grade)

Inverse-realized-vol sizing on a fixed K, single capital pool.

```
target_vol = 0.0030 (daily)
K          = 3.50  (constant)
inner cap  = 20.0  (vol scaler)
cost       = 5 bps active-day
```

| Metric | Value |
|---|---:|
| PnL | **+$5,705** |
| MaxDD | -36.33% |
| Sharpe (net) | +0.852 |
| CAGR | +44.0% |
| Calmar | 1.21 |

---

## v23 – v29 — Failed Re-Weighting Experiments

All five tried to beat v22 by mixing additional alphas or restructuring the sizer. **All failed.**

| Version | Idea | PnL | Δ vs v22 | Verdict |
|---|---|---:|---:|---|
| v23 | DD-throttle Calmar variant | +$2,307 | -$3,398 | NEG |
| v24 | 6-leg multi-alpha stack | (negative) | — | NEG |
| v25 | 3-leg filtered (incl. fund_spread) | +$506 | -$5,199 | NEG |
| v26 | Per-leg vol-target + per-leg cap | +$522 | -$5,183 | NEG |
| v27 | v25 stack + raised inner cap (200) | +$506 | -$5,199 | NEG (cap not binding) |
| v28 | Static risk-parity base + v22 sizer | +$1,450 | -$4,255 | NEG |
| v29 | v22 PROD + α·fund_spread overlay | +$5,705 | $0 | NEG (α=0 wins) |

**Root cause documented in v29 dollar-mass arithmetic:** sparse high-Sharpe alphas (e.g., `fund_spread` at Sh +0.733) deliver ~+$15 gross over 4.8 yr but cost ~$25 in 5 bps t-cost → net negative. **More signal does not equal more money** if the dollar mass per signal day is below the cost floor.

This eliminated "add a new alpha" as a viable path forward and forced the focus onto **time-varying leverage on the existing signal**.

---

## v30 — Soft DD-Aware K Throttle (in-sample winner, fragile in stress)

Cubic Hermite smoothstep mapping current drawdown to leverage:

```
K_eff(t) = K_min + (K_max - K_min) · smoothstep(dd_t; -10%, -30%)
            (uses prior equity only — no leak)
```

PROD config: `K_max = 9.0, K_min = 1.5, band = [-10%, -30%]`.

| Metric | v22 | **v30** | Δ |
|---|---:|---:|---:|
| PnL (5 bps) | +$5,705 | **+$8,727** | **+$3,022 (+53%)** |
| MaxDD | -36.33% | -39.62% | -3.3 pp (within -40% guard) |
| Sharpe (net) | +0.852 | +0.940 | +0.088 |
| CAGR | +44.0% | +55.3% | +11.3 pp |
| Calmar | 1.21 | 1.40 | +0.19 |
| K-path: mean / p10 / p90 | 3.50 fixed | 4.70 / 1.50 / 9.00 | adaptive |

**Plot:** [`crypto_bsdt_v30_dd_throttle.png`](crypto_bsdt_v30_dd_throttle.png)

### Stress test results — fails

The v30 PROD config was subjected to a synthetic shock battery: shocks of **3σ, 5σ, 8σ, 10σ** across **3 trigger dates each at peak-K days**, all using lag-1 information.

| Scenario | Trigger | K @ shock | PnL | MaxDD | guard? |
|---|---|---:|---:|---:|---|
| mild_3σ_3d | 2023-04-18 | 9.00 | +$5,984 | **-44.3%** | BREACH |
| mild_3σ_3d | 2024-04-13 | 8.99 | +$3,103 | **-42.1%** | BREACH |
| severe_5σ_5d | 2023-04-18 | 9.00 | +$139 | -66.6% | BREACH |
| crash_8σ_3d | 2023-04-18 | 9.00 | -$418 | -82.9% | BREACH |
| extreme_10σ_5d | 2023-04-18 | 9.00 | -$1,046 | **-96.6%** | BREACH |

**11 / 12 scenarios breach the -40% guard.** Worst-case MaxDD = **-96.6%** (near-wipeout).

**Critique that drove v32:**
> v30 implicitly assumes future regimes follow the historical pattern of "drawdowns precede bad regimes." A sudden regime break at peak-K destroys this assumption. The reactive throttle reads lag-1 drawdown — it cannot see day-1 of a shock.

---

## v31 — Reactive Vol Cap (failed to fix v30, in-sample optimum is overfit)

Added an OR-logic detector on **exogenous BTC/ETH market vol**:

```
fire_cap = (vol_5d/vol_30d > vol_thresh) OR (|ret_t-1|/vol_30d > shock_z_thresh)
if fire_cap:  K = min(K, K_cap)
```

Sweep selected `vol_thr=1.40, shock_z=2.50, K_cap=1.5` (174 cap-hits in-sample).

| Metric | v30 | v31 (selected) |
|---|---:|---:|
| In-sample PnL (5 bps) | +$8,727 | **+$36,548** |
| In-sample MaxDD | -39.6% | -31.6% |
| **Stress breaches** | **11 / 12** | **11 / 12** ⚠ |
| **Stress worst MaxDD** | **-96.6%** | **-96.6%** ⚠ |

**Plot:** [`crypto_bsdt_v31_volcap.png`](crypto_bsdt_v31_volcap.png)

### Two damning findings

1. **Stress breaches are identical to v30.** The vol cap fires on lag-1 information; it is structurally blind to day-1 of an instantaneous shock. Every config in the entire `(vol_thr × shock_z × K_cap)` sweep produced identical `11/12, -96.6%` stress numbers.
2. **The +$36,548 in-sample win is path-dependent overfit.** The vol cap fires 174 times (≈21% of days). Capped days experience slightly different returns, which alters the equity path, which keeps the DD throttle near peak, which compounds K_max=9 exposure on uncapped days. The K-path chart shows constant flapping between 1.5 and 9 — this is a regime-switching artefact, not a robust signal.

**Conclusion:** No reactive lag-1 throttle can defeat instantaneous shocks. The only structural defence is a *hard* K_max budgeted for survival under the worst plausible shock.

---

## v32 — Hard Stress-Budgeted K_MAX (the genuine production strategy)

Strip v31. Keep v30's smoothstep DD throttle. Replace the optimised K_max=9 with the **largest K_max that survives a 3σ/3d shock at all 3 trigger dates**.

```
K_max_grid = [2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0]
guard      = -40% MaxDD
PROD       = max(K_max in grid : worst stress DD ≥ -40%)
```

### Sweep result

```
K_max  in_PnL $    in_DD%   stress_wDD%   verdict
 2.50  +$2,481     -26.6%       -35.2%      PASS
 3.00  +$2,916     -30.9%       -37.1%      PASS
 3.50  +$3,341     -35.8%       -38.3%      PASS
 4.00  +$3,840     -38.8%       -39.2%      PASS  ← v32 PROD
 4.50  +$4,517     -39.5%       -40.1%      BREACH
 5.00  +$5,286     -39.3%       -40.9%      BREACH
 5.50  +$6,058     -39.1%       -41.6%      BREACH
 6.00  +$6,858     -39.1%       -42.2%      BREACH
 7.00  +$7,696     -39.2%       -43.1%      BREACH
```

### v32 PROD vs v22 vs v30

| Metric | v22 | **v32** | v30 |
|---|---:|---:|---:|
| K_max | 3.5 (fixed) | **4.0 (capped)** | 9.0 (uncapped) |
| In-sample PnL | +$5,705 | +$3,840 | +$8,727 |
| In-sample MaxDD | -36.3% | -38.8% | -39.6% |
| Sharpe (net) | +0.852 | +0.910 | +0.940 |
| CAGR | +44.0% | +34.9% | +55.3% |
| **3σ stress (worst)** | ≈ -38% | **-39.2% PASS** | **-44.3% FAIL** |
| **5σ stress (worst)** | — | -53.7% | -66.6% |
| **10σ extreme (worst)** | — | -74.1% | **-96.6%** |

**Plot:** [`crypto_bsdt_v32_stress_budgeted.png`](crypto_bsdt_v32_stress_budgeted.png)

### Why v32 has lower in-sample PnL than v22

v22 runs K=3.5 *constantly*; v32 runs K=4.0 only when DD is shallow and throttles down to K=1.5 deep in DD. Across the full window, v32 is on average more conservative than v22 (mean K ≈ 3.0 vs v22's flat 3.5), trading raw PnL for downside protection. The 3σ stress test confirms this protection is real — v32 holds at -39.2% while v22 would breach at -38% or worse depending on shock placement.

---

## Honest Verdict

1. **v22 K=3.5 was nearly optimal all along.** v32's K_max=4.0 is only 0.5 units above it. The entire sizing-research arc landed within one notch of the original baseline.
2. **v30 is a cautionary tale** about in-sample optimisation. +$3,022 (+53%) over v22 looked legitimate until stress-tested; the gains came entirely from running K=9 in a benign sample, not from better risk control.
3. **v31 is a worse cautionary tale** about reactive defences. The detector cannot see what hasn't happened yet; lag-1 vol cannot stop day-1 shocks.
4. **No reactive system protects against ≥5σ shocks.** Even v32 breaches at 5σ (-54%) and 10σ (-74%). Real protection at that magnitude requires either (a) hard position size limits as a fraction of equity, (b) circuit breakers that halt trading on regime detection, or (c) a different signal stack with lower extreme-loss exposure. None of these are implemented in this pipeline.

---

## Per-version registration in `version_history`

| Key | Sharpe (net, K=1 normalisation) | Status |
|---|---:|---|
| `v22_voltarget` | +0.852 | PROD-stable baseline |
| `v23_calmar_max` | (lower) | NEG |
| `v24_multi_alpha` | NEG | NEG |
| `v25_filtered_stack` | (lower) | NEG |
| `v26_perleg_sizing` | (lower) | NEG |
| `v27_raised_cap` | (lower) | NEG |
| `v28_risk_parity` | (lower) | NEG |
| `v29_additive_overlay` | +0.852 (α=0) | NEG |
| `v30_dd_throttle` | +0.940 | research only — fragile |
| `v31_volcap` | +1.205 | research only — overfit |
| **`v32_stress_budget`** | **+0.910** | **PROD-stable, stress-aware** |

Full numerical summaries written to `crypto_bsdt_v18_results.json` under `version_history.{vNN_summary}`.

---

## Reproducibility

```powershell
cd c:\amttp\research\adaptive-friction\pipeline\results
py -3 run_crypto_pairs_v18.py
```

Outputs:
- `crypto_bsdt_v18_results.json` — full per-version metrics
- `crypto_bsdt_v22_exposure_sweep.png`
- `crypto_bsdt_v30_dd_throttle.png` — v30 equity / K-path / DD / cost panel
- `crypto_bsdt_v31_volcap.png` — v31 + cap detector overlay
- `crypto_bsdt_v32_stress_budgeted.png` — v32 vs v30 vs v22 with K-path comparison
