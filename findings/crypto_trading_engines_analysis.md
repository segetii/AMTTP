# Findings from the Analysis of Crypto Trading Engines (v55 and v58)

Repository: `segetii/AMTTP`  
Primary source: `research/adaptive-friction/pipeline/results/math_reference (1).html` (3 733 lines) — "Mathematical Anatomy of System Collapse", extracted from `energy.py` (GravityEngine), `bsdt.py` (Blind-Spot Detection Theory), and `network.py` (Ledoit-Wolf Correlation Network).  
Simulation script: `research/adaptive-friction/pipeline/results/run_crypto_v58_sim_700.py`

---

## 1. Engine Architecture

The engine has two interlocking layers:

| Layer | Role |
|---|---|
| **GravityEngine** (sections I-V) | Models N crypto instruments as particles in a d-dimensional potential-energy landscape |
| **BSDT** (sections VI-XI) | Four-channel blind-spot detector; measures deviation from normal-period distribution and derives optimal adaptive damping signal gamma_star |

### 1.1 State Space

At each 1-hour bar the system state is a matrix X_t in R^(N x d) with **N = 8** instruments and **d = 8** features per instrument (section XXVIII):

| Agent | Instrument | Feature | Variable |
|---|---|---|---|
| 1 | BTC perp | 1 | Log return over last tau bars |
| 2 | ETH perp | 2 | Normalised volume |
| 3 | BTC quarterly | 3 | Order-book imbalance (bid/ask ratio) |
| 4 | SOL perp | 4 | Funding rate |
| 5 | BNB perp | 5 | Open-interest change |
| 6 | ETH/BTC ratio | 6 | Mark vs index divergence (basis) |
| 7 | Crypto fear index | 7 | Liquidation volume |
| 8 | Stablecoin dominance | 8 | Realised volatility (last 20 bars) |

### 1.2 Calibration (one-time, on normal-period data)

Computed once on 500-2000 bars of stable microstructure regime and then frozen:

- `mu_0 = (1/T0*N) sum x_t^(i)` — global mean, R^8
- `Sigma_0 = Ledoit-Wolf covariance` — R^(8x8)
- `Sigma_0^(-1), Sigma_0^(-1/2)` — computed once via Cholesky/eigen
- `V_k in R^(8xk), k=4` — top-4 eigenvectors of Sigma_0
- `v_0 = Pctl_95( bar-to-bar velocity in normal period )`

---

## 2. GravityEngine Physics (sections III-V)

### 2.1 Potential Energy

```
Phi_rad(X)  = (alpha/2) * ||X - 1*mu^T||_F^2              alpha = 0.10

Phi_pair(X) = (1/2) * [-gamma*sigma * 1^T * erf(D/sigma) * 1
                        + lambda * 1^T * ln(D + eps) * 1]
              closed-form over distance matrix D_ij = ||x_i - x_j||

Phi(X)      = Phi_rad(X) + Phi_pair(X)
```

Parameters: gamma = 1.00, sigma = 1.00, lambda = 0.10, eps = 1e-5.

### 2.2 Force Matrix (Graph Laplacian form)

```
K_ij = [ (2*gamma/sqrt(pi)) * exp(-D_ij^2/sigma^2) - lambda/D_ij ] / D_ij,  i != j
K_ii = 0

L  = diag(K * 1) - K             (weighted graph Laplacian)
F  = -alpha*(X - 1*mu^T) - L*X   in R^(N x d),  ||F_i|| <= F_max = 100
```

### 2.3 Critical Manifold Test (Gershgorin bound, no eigensolver required)

```
lambda_max(Hessian_Phi) <= alpha + max_i sum_{j!=i} [
    (2*gamma / (sqrt(pi)*sigma)) * exp(-D_ij^2/sigma^2) + lambda/D_ij^2 ]

Supercritical  <=>  bound > 1
```

---

## 3. BSDT - Four-Channel Blind-Spot Detection (section VI)

All channels computed per bar from X_t; centred state X_tilde = X_t - 1*mu_0^T is the common input.

### 3.1 Channel Formulas

| Channel | Symbol | Formula | Crypto meaning |
|---|---|---|---|
| Mahalanobis (Camouflage) | delta_C | `norm(X_tilde * Sigma_0^(-1/2))_F^2` | Pre-liquidation-cascade: price + volume + OI + funding all deviating together |
| Feature Gap | delta_G | `norm(X_tilde)_F^2 - norm(X_tilde * V_k)_F^2` | Novel funding behaviour, basis blow-out, new correlations; fires first in regime change |
| Activity Anomaly | delta_A | `norm_1(max(0, row-norms(X_t - X_{t-1}) - v_0))` | In-progress cascade: simultaneous velocity across price, OI, liquidation volume |
| Temporal Novelty | delta_T | `sum_i max(0, -log p_h_hat(x_t^(i)))` | New regime: BTC at new price level, funding at extreme, novel OI structure |

BSDT total energy:

```
e_t = E_BSDT(X_t) = tr( X_tilde * Sigma_0^(-1) * X_tilde^T ) = norm(X_tilde * Sigma_0^(-1/2))_F^2
```

### 3.2 MFLS - Mahalanobis Field Line Score

```
MFLS(X_t) = 2 * norm(X_tilde * Sigma_0^(-1))_F
```

Gradient magnitude of the blind-spot energy — a spike precedes visible chart moves.

### 3.3 Gradient Alignment Angle cos(theta_t)

```
A_t = X_tilde * Sigma_0^(-1)

cos(theta_t) = inner_product(A_t, F_t)_F / ( norm(A_t)_F * norm(F_t)_F )
```

| Value | Interpretation |
|---|---|
| cos(theta) -> +1 | BSDT gradient and GravityEngine force aligned — coherent collapse |
| cos(theta) ~ 0 | Orthogonal — BSDT sees risk invisible to physical potential |
| cos(theta) -> -1 | Anti-aligned — stabilising competition |

### 3.4 Optimal Adaptive Damping gamma_star

```
gamma_star(X_t) = e_t / (e_t + theta),    theta = 1.00
```

gamma_star in [0, 1): approaches 1 as risk diverges, 0 at normal-period baseline.

---

## 4. Per-Channel Collapse Attribution Signals (section XXIX)

### 4.1 Normalised Attribution

These are the **primary trading signals** emitted by the engine every bar:

```
S_tilde_k(t) = S_k(t) / mu_k^(normal)       (mean-normalise each channel)

a_k(t) = S_tilde_k(t)^2 / norm(S_tilde(t))^2,      sum_k a_k = 1
```

| Signal | Name | Meaning when elevated |
|---|---|---|
| `a_C(t)` | Mahalanobis attribution | Within-ellipsoid crowding — all features deviating jointly |
| `a_G(t)` | Gap attribution | PCA out-of-subspace displacement — novel regime forming |
| `a_A(t)` | Activity attribution | Velocity anomaly — cascade in progress |
| `a_T(t)` | Topological attribution | KDE self-surprise — new price/funding territory |

### 4.2 Rolling Memory Operator

Rolling maximum over 8-bar horizon (shift-1 prevents lookahead):

```
G_mem(t) = max_{s in [t-N, t-1]} a_G(s),    N = 8
T_mem(t) = max_{s in [t-N, t-1]} a_T(s),    N = 8
```

### 4.3 A-Channel Firing Gate

```
1_fire(t) = 1[ a_A(t-1) > theta_A ],    theta_A = 0.65
```

All quadrant activity requires this gate to be open.

---

## 5. The 4-Quadrant Phase Modulator (section XXIX, section 29.3)

Attribution pair (G_mem, T_mem) partitions signal space into four quadrants:

### 5.1 Quadrant Indicators (all shift-1 to prevent lookahead)

```
q_GH_TH(t) = 1_fire * 1[G_mem(t) > theta_G] * 1[T_mem(t) > theta_T]
q_GH_TL(t) = 1_fire * 1[G_mem(t) > theta_G] * 1[T_mem(t) <= theta_T]
q_GL_TH(t) = 1_fire * 1[G_mem(t) <= theta_G] * 1[T_mem(t) > theta_T]
q_GL_TL(t) = 1_fire * 1[G_mem(t) <= theta_G] * 1[T_mem(t) <= theta_T]
```

### 5.2 Phase Modulator

```
phi_t = clip( 1 + beta_GH_TH * q_GH_TH + beta_GH_TL * q_GH_TL
                + beta_GL_TH * q_GL_TH + beta_GL_TL * q_GL_TL,
              phi_min, phi_max )
```

| Parameter | Value | Meaning |
|---|---|---|
| beta_GH_TH | +5.0 | Both G and T high: strong boost (reaches phi_max) |
| beta_GH_TL = beta_GL_TH = beta_GL_TL | -1.0 | All other quadrants: full kill (phi -> 0.05) |
| phi_max (CLIP) | 6.0 | Clip ceiling — confirmed optimal at clip in [5.5, 6.5] |
| phi_min | 0.05 | Floor — prevents zero sizing |
| theta_G (static base) | 0.45 | G-memory threshold (dynamically adapted in v55/v58) |
| theta_T | 0.41 | T-memory threshold — cliff-sensitive, kept static |
| theta_A | 0.65 | A-channel firing threshold |

The at-boundary structure (beta_GH_TH = phi_max - 1 = 5.0) places the boost exactly at the clip ceiling. Boosting above phi_max gains nothing (clipped) and degrades MaxDD.

---

## 6. Full Position Sizing Law (section XXIX, section 29.4)

```
PnL_t = base_t
        * clip(1 - gamma_star_{t-1}, 0, 1) * (0.75 + 0.5 * lambda_pct(t-1))   [size_sym]
        * (1 + c_b * 1[a_G(t-1) > theta_GBT])                                  [G-boost]
        * phi_t                                                                   [phase modulator]
```

| Parameter | Value | Role |
|---|---|---|
| gamma_star_{t-1} | from section VIII | Adaptive damping — reduces size when system is anomalous |
| lambda_pct(t-1) | from section XXVIII | Price loading percentile — enlarges size when energy is in price dimension |
| c_b | 0.65 | Champion boost amplitude |
| theta_GBT | 0.45 | G-boost activation threshold (equals theta_G base) |

---

## 7. State-Dependent G-Threshold: v55 and v58 (section XXIX, sections 29.5-29.10)

### 7.1 Core Discovery

Regime analysis of 2023-2026 revealed a persistent asymmetry: high-volatility regimes yield Sharpe +4.30 vs +3.43 in low-volatility regimes under static theta_G = 0.45. This motivated making theta_G a function of state.

### 7.2 Normalised Realised Volatility (shared by v55 and v58)

```
rv_hat_raw(t) = sigma_168(r_t) / E_1000[sigma_168(r_t)]   evaluated at t-1

sigma_168(r_t) = sqrt( (1/168) * sum_{s=t-168}^{t-1} r_s^2 - r_bar^2 )
                 (1-week realised vol on 1h bars)
E_1000         = 1000-bar rolling mean of sigma_168
```

Sign convention: rv_hat > 1 (high vol) lowers theta_G so the system trades more readily; rv_hat < 1 (quiet market) raises theta_G requiring stronger evidence.

### 7.3 v55 — Dynamic G-Threshold (unclamped)

```
theta_G(t) = theta_G_base * (1 + K_G * (1 - rv_hat_t))

K_G          = 0.10
theta_G_base = 0.45
clip range   = [0.20, 0.70]
```

v55 results: Sharpe +4.036, CAGR +20.2%, MaxDD -3.7%.  
v55 passes 3/4 robustness tests. **Fails** the rv x 1.10 stress test (Sharpe drop -0.297 vs threshold -0.15) because the unclamped floor allows adj to become arbitrarily negative under persistent high-vol stress, causing overtrading.

### 7.4 v58 — Stability Patch (asymmetric clamp + EMA smoothing)

Fix: add a floor on adj and smooth rv_hat with an EWM:

```
rv_hat_t   = EWM( rv_hat_raw_t, tau=3 )  evaluated at t-1     [EMA smoothing]
adj_t      = clip( K_G * (1 - rv_hat_t), l0, +0.10 )          [asymmetric clamp]
theta_G(t) = clip( theta_G_base * (1 + adj_t), 0.20, 0.70 )
```

Production values (locked):

| Parameter | Value |
|---|---|
| K_G | 0.10 |
| tau (EMA span) | 3 |
| l0 (clamp floor on adj) | -0.01 |
| theta_G_base | 0.45 |
| Resulting floor on theta_G | 0.45 x 0.99 = 0.4455 |

The floor l0 = -0.01 ensures theta_G never drops below 0.4455 regardless of rv stress, while the upper bound +0.10 is unchanged (the low-vol direction carries structural edge without fragility).

v58 results (champion config `v58_tight`): **Sharpe +3.959**, CAGR +19.7%, MaxDD -3.7%, OOS H2 (2025-26) Sharpe +4.740. All 4 robustness tests PASS.

### 7.5 Version Comparison

| Config | Sharpe | CAGR | MaxDD | rv x 1.10 drop | Verdict |
|---|---|---|---|---|---|
| v34 (base) | +2.616 | +11.2% | -5.1% | — | Baseline |
| v54 (static plateau) | +3.857 | +19.1% | -3.7% | — | Static parameter exhaustion |
| v55_ref (no clamp, no EMA) | +4.036 | +20.2% | -3.7% | -0.297 | FAIL stress |
| v58_tight (lo=-0.01, EMA=3) | +3.959 | +19.7% | -3.7% | -0.074 | **Production lock** |

Frozen parameters for v58 production: `CLIP=6.0, GH_TH=5.0, GH_TL=GL_TH=GL_TL=-1.0, N=8, T_THRESH=0.41, CB=0.65, AFT=0.65, K_G=0.10`

---

## 8. The Price Loading Factor lambda_pct (section XXVIII)

A critical correction over the naive energy-to-price mapping:

```
e_t_price_full = sum_j [Sigma_0^(-1)]_{1j} * sum_i x_tilde^(i,1) * x_tilde^(i,j)
                 (first row of X_tilde * Sigma_0^(-1) * X_tilde^T, summed over agents)

lambda_t_price = sqrt( e_t_price_full / e_t ) in [0, 1]
```

| lambda_t_price | Meaning |
|---|---|
| ~1 | All energy in price — maximum directional move |
| ~0 | Energy in volatility or dispersion — no price move despite high e_t |

The energy rotation signal (bar-over-bar change in lambda_t_price) discriminates real directional moves from volatility-only expansions. In the position sizing law, `lambda_pct(t-1)` is the percentile rank of lambda_t_price over recent history:

```
size_sym = clip(1 - gamma_star, 0, 1) * (0.75 + 0.5 * lambda_pct)
```

---

## 9. Complete Signal Computation Pipeline (per 1h bar)

```
Step 1 : X_t <- update 8 instruments x 8 features
Step 2 : X_tilde = X_t - 1 * mu_0^T
Step 3 : D_ij = norm(x_i - x_j)  (distance matrix, 1 matrix multiply)
Step 4 : e_t = norm(X_tilde * Sigma_0^(-1/2))_F^2               [BSDT energy]
Step 5 : gamma_star_t = e_t / (e_t + 1)                          [adaptive damping]
Step 6 : MFLS_t = 2 * norm(X_tilde * Sigma_0^(-1))_F             [field line score]
Step 7 : F_t = -alpha*(X_t - 1*mu^T) - L_t*X_t                  [restoring force]
Step 8 : cos_theta_t = <A_t, F_t>_F / (norm(A_t)_F * norm(F_t)_F)  [alignment]
Step 9 : delta_G, delta_A, delta_T  <- channel energies
Step 10: a_k = S_tilde_k^2 / norm(S_tilde)^2                     [attributions a_C, a_G, a_A, a_T]
Step 11: G_mem = max_{s in [t-8, t-1]} a_G(s)
         T_mem = max_{s in [t-8, t-1]} a_T(s)
Step 12: 1_fire = 1[a_A(t-1) > 0.65]
         Compute q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL
Step 13: phi_t = clip(1 + 5*q_GH_TH - 1*q_GH_TL - 1*q_GL_TH - 1*q_GL_TL, 0.05, 6.0)
Step 14: rv_hat_t = EWM(sigma_168 / E_1000, tau=3)|_{t-1}
         adj_t = clip(0.10*(1 - rv_hat_t), -0.01, +0.10)
         theta_G(t) = clip(0.45*(1 + adj_t), 0.20, 0.70)          [v58 dynamic threshold]
Step 15: e_t_price_full -> lambda_t_price -> lambda_pct
Step 16: PnL_t = base_t * [clip(1-gamma_star,0,1)*(0.75+0.5*lambda_pct)]
                         * [1 + 0.65*1(a_G > 0.45)]
                         * phi_t
```

---

## 10. Simulation Script Summary

File: `research/adaptive-friction/pipeline/results/run_crypto_v58_sim_700.py`

The script runs the v58 champion configuration (`v58_tight`) on a $700 starting capital simulation:

- **Test window**: 2023-01-01 to present (OOS from v58 stability patch)
- **OOS split**: first half 2023-2024 | second half 2025-2026
- **Fees**: maker 2 bps + slippage 1 bps = 3 bps per side; costs charged on each roundtrip transition
- **Champion config**: EMA span tau=3, clamp lo=-0.01

Key implementation notes:

1. `_build_pnl_with_fired`: implements the position sizing law from section 29.4, using `gamma_star_adj` (gamma_star), `lambda_pct_100` (lambda_pct), and the 4-channel signals `a_G`, `a_A`, `a_T` from `sig_4ch`.
2. `_dynamic_gth`: implements the v58 `theta_G(t)` formula — EWM-smoothed rv_hat, asymmetric clamp lo=-0.01.
3. `_apply_maker_fees`: deducts 3 bps per side on each fired->not-fired or not-fired->fired transition.
4. Output saved to `crypto_bsdt_v58_sim_700.json` with gross/net stats, quarterly and YoY breakdowns.

**Signals in `sig_4ch` DataFrame** (produced by `compute_four_channel_signals_v39b`):
- `a_G` — Gap channel attribution a_G(t)
- `a_A` — Activity channel attribution a_A(t)
- `a_T` — Topological channel attribution a_T(t)

**Signals in `sig_v36` DataFrame** (produced by `compute_intraday_signals`):
- `gamma_star_adj` — adaptive damping gamma_star(t) from section VIII

**Signals in `lam_feat` DataFrame** (produced by `compute_lambda_features`):
- `lambda_pct_100` — percentile rank of price loading factor lambda_t_price

---

## 11. Key Observations

1. **v55 vs v58**: v55 introduced the first state-dependent threshold (+0.179 Sharpe over v54), but failed the rv x 1.10 stress test. v58 fixes this with a one-sided floor (l0=-0.01) and EWM smoothing at the cost of -0.077 Sharpe, gaining stress robustness. The OOS H2 Sharpe improves to +4.740 for v58_tight while eliminating the failure mode.

2. **The GH_TH quadrant is the only profitable regime**: beta=+5.0 means the system fires at full clip (phi=6.0) only when both G-memory and T-memory are elevated. All other quadrants are killed (phi=0.05), making the engine highly selective.

3. **The at-boundary structure is deliberate**: beta_GH_TH = phi_max - 1 = 5.0 places the boost exactly at the clip ceiling. This is a nonlinear gate — boosting higher gains nothing (clipped) and degrades MaxDD.

4. **gamma_star is a damper, not an on/off switch**: the adaptive damping continuously scales position size down as BSDT energy rises. The 4-quadrant phase modulator then decides whether to amplify (GH_TH) or suppress (all others) the remaining size.

5. **The firing signal in `_build_pnl_with_fired`** is `a_A(t-1) > A_FIRE_THRESH (0.65)` — the Activity channel gate. Memory operators G_mem and T_mem then determine the quadrant within that gated universe.