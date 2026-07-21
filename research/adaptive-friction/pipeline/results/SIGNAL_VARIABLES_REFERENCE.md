# Crypto BSDT Signal-Generation Reference — Every Variable, Formula, Usage

Full reference for the signal-generation stack across `run_crypto_pairs_v19/22/26/27/28.py`,
`run_crypto_canonical_v4.py`, `collapse_geometry/canonical/{core,domains}.py`, and
`crypto_eigen_direction_patch.py`. Organized bottom-up: raw geometry → engine scalars →
direction sources → strategies → allocators → leverage. Every entry gives the **formula**,
**where it's computed**, and **how/why it's used downstream**.

---

## 1. Core BSDT geometry (the "engine state")

Computed once per pipeline run in `compute_bsdt(df, features, window=60)` —
[run_crypto_pairs_v19.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_pairs_v19.py#L243).

| Variable | Formula | Interpretation | Used for |
|---|---|---|---|
| `omega` (Ω) | `0.9 × λ_max(W)`, where `W = ‖corr‖ / rowsum(‖corr‖)` is the row-normalized absolute-correlation matrix of `features` over a rolling 60-bar window | Network coherence: how tightly the feature block co-moves right now. High Ω = features are moving as one unit (structural stress/regime). | Phase detection, activation gates (`w1_g`, `omega_gate`), θ calibration reference |
| `mfls` (S0, Mahalanobis Field Line Score) | `‖X_t − window_mean‖ × λ_max` | Distance-from-normal (raw deviation magnitude) scaled by the coherence factor — "how far, and how structurally organized is that distance." | Numerator of `A` (Activity) |
| `gamma` (γ, BSDT-local, distinct from canonical `gain()`) | `1 / (1 + mean(Ω over trailing 21 bars))` | Inverse trailing coherence — a "calm" dial; near 1 when the market has been quiet, small when persistently coherent/stressed. | Denominator of `A` |
| `A` (Activity) | `A = mfls / (γ + 1e-9)` | Composite "how much is happening and how sharply" — the master intensity/urgency scalar. | `A_rank`, gates in `route_pair_v7`, `route_btcalt_macro`, `setup_a_directional` |
| `A_rank` | `A.expanding(60).rank(pct=True)` | Percentile-normalized Activity ∈ [0,1], comparable across time. | Activation gates (`A_rank >= 0.33`) |
| `dA_fast` | `A.diff(1).rolling(2).mean()` | Velocity of Activity (2-bar smoothed first difference). | `dA_rank`, `compute_state_vector` (`c4`) |
| `dA_rank` | `dA_fast.expanding(60).rank(pct=True)` | Percentile of Activity velocity. | `route_btcalt_macro` |

`compute_activity_signals(mfls, gamma)` — [run_crypto_pairs_v19.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_pairs_v19.py#L288) — returns `(A, A_rank, dA_fast, dA_rank)`.

`compute_gamma_rank(omega_series, min_periods=60)` — [run_crypto_pairs_v19.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_pairs_v19.py#L272) — an O(n log n) expanding percentile rank of Ω via `bisect.insort`, used to build `gamma_rank` (feeds the leverage dial, distinct from `gamma`/γ above — naming collision in the codebase, be careful).

### Phase classification

`detect_phase(omega, ret7, ret3, btc_dom_z)` — [run_crypto_pairs_v19.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_pairs_v19.py#L620):

```
q50, q75 = Ω.expanding(60).quantile(0.50 / 0.75)
elev  = Ω >= q50
high  = Ω >= q75
crash = elev & ((ret7 < -0.10) | (btc_dom_z > 1.5)) & (ret3 < 0)
recov = high & (ret3 > 0.03) & ~crash
phase = 0 (quiet, Ω<q50) / 1 (elevated, default) / 2 (crash) / 3 (recovery/boom)
```
Used directly in `setup_a_directional` to select which direction rule applies (momentum in phase 2, force `+1` in phase 3).

---

## 2. Engine-v22 scalars (used strictly as non-negative gates)

Built in `emit_global_signals` — [run_crypto_pairs_v22.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_pairs_v22.py#L172):

| Variable | Source call | Interpretation | Locked usage rule |
|---|---|---|---|
| `geom_score` | `ews.score(snap, net)` (Layer B raw early-warning score) | Raw structural/geometric stress score. | Gate only — `rolling_layer_b_alarm`: alarm when `geom_score > rolling_mean + n_sigma·rolling_std` |
| `precursor_score` | `ews.precursor_score(snap, prev)` (Layer A, normalized in v22 to fix v21's 1e-9-collapse bug) | Early-warning precursor magnitude, O(1) scale after v22's relative-floor fix (`std + |mean|` floor instead of raw scale). | Gate only — `alarm_A = precursor_score >= 0.5` (`LAYER_A_THRESHOLD`) |
| `cos_theta` | `geom.cos_theta_channel(snap)` — `cos θ_C = (g·h)/(‖g‖‖h‖)`, `g=∇_S E_BS(S_t)` (channel-space energy gradient), `h_k=⟨∂δ_k/∂X,F⟩` (per-channel Jacobian projected onto restoring force) | Alignment/coherence between the energy gradient and the physical restoring force, ∈[-1,1]. Bilinear ⇒ **even function, carries no return-axis sign** (proven in §4 below). Test-panel mean was **-0.71**. | **`align = |cos_theta|`** — absolute value only, used as a confidence/coherence gate. NEVER use `sign(cos_theta)` as direction (v26 catastrophic failure, Sharpe -0.30 — see §5). |
| `kramers_p` | `stoch.cross_probability(...)` — Kramers escape-rate probability (stochastic barrier-crossing formalism, calibrated by `KRAMERS_TAU`) | Probability the system "escapes" its current regime/basin. ∈[0,1]. | Gate: `w2_g = A_rank.where(A_rank>=0.33,0)`-style gating in v27/v28; leverage dampener: `lev = clip(g_pos*(1-kramers_p), LEV_LO, LEV_HI)` (higher escape prob ⇒ de-lever) |

---

## 3. Canonical energy/ODE framework (`collapse_geometry/canonical`)

`CanonicalSystem` — [core.py](../../../../research/adaptive-friction/collapse_geometry/canonical/core.py#L42) — generic (S, J, G, F_base, θ, ε) engine used by every "domain" (trading, Galerkin, optimisation, robotics). Formulas:

| Method | Formula | Interpretation |
|---|---|---|
| `energy(X)` | `E(X) = S(X)ᵀ G S(X)` | Squared Mahalanobis-style spread energy. **Even** in S (Theorem 1, proven in [crypto_eigen_direction_patch.py](../../../../crypto_eigen_direction_patch.py)) |
| `gradient(X)` | `g_X = 2 J(X)ᵀ G S(X)` | Energy gradient in state space |
| `gain(X)` | `γ(X) = E/(E+θ) ∈ [0,1)` | Confidence/saturation dial — large E ⇒ γ→1 |
| `modified_force(X)` | `F = F_base(X) − g_X(X)` | Alpha-tracking force net of the energy-restoring pull |
| `rhs(X)` | `Ẋ = F − γ·(⟨F,g_X⟩/(‖g_X‖²+ε))·g_X` | The locked canonical ODE (§3) — projects out the component of F along the gradient, scaled by confidence γ |
| `dE_dt(X)` | `Ė = (1−γ)·(⟨g_X,F_base⟩ − ‖g_X‖²)` | Closed-form energy derivative (Lemma 6.7) — used as a gate: `gate_lemma67 = 1 if Ė≤0 else 0` |
| `curvature_manifold_indicator(X)` | `λ_max(∇²E(X)) − 1` | Sign tells curvature- vs convex-dominated regime; `gate_curv = 1 if ≤0 else 0.5` |

### TradingDomain (§8.1) — the crypto-specific instantiation

[domains.py](../../../../research/adaptive-friction/collapse_geometry/canonical/domains.py#L23):

```
X = w                      (portfolio weight vector, n=3: btc/eth/sol)
S(w) = A·w − b             (factor-space spread vs. target)
G = Σ⁻¹                    (inverse factor covariance)
F_base(w) = −κ(w − w⋆)     (alpha-tracking + mean reversion pull toward target)
```
`K ≡ 0` because `S` is affine (constant Jacobian `J=A`), which zeroes the curvature-tensor term in the Hessian and simplifies `dE_dt`/`rhs`.

`A_FACTORS` (k=5 × n=3 loading matrix) — [run_crypto_canonical_v4.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_canonical_v4.py#L142):

```
f1 = w_btc            → directional alpha (BTC)
f2 = w_eth            → directional alpha (ETH)
f3 = w_sol            → directional alpha (SOL)
f4 = w_eth − w_btc     → rotation alpha (ETH/BTC)
f5 = w_eth − w_sol     → rotation alpha (ETH/SOL)
```
`build_factor_returns(df) = R @ A_FACTORS.T` — per-bar factor returns for Σ_f calibration (Ledoit-Wolf shrinkage, rescaled to correlation, **frozen on train only**, [run_crypto_canonical_v4.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_canonical_v4.py#L219)).

`θ` (theta_cal) calibration: `θ = P50( b_trainᵀ · Σ_f⁻¹ · b_train )` — median energy-at-w=0 on the training window ([run_crypto_canonical_v4.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_canonical_v4.py#L240)). Sets the natural scale so `γ=E/(E+θ)` is non-degenerate.

### Target `b_t` construction — `build_target_b(df)`

[run_crypto_canonical_v4.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_canonical_v4.py#L164):

```
_mom_tanh(r, win) = tanh(MOM_TANH_S · rolling_sum(r,win).shift(1) / rolling_std(that_sum))
b[:,0..2] = _mom_tanh(r_btc/eth/sol, MOM_BARS_DIR) × TARGET_DIR      # directional rows
b[:,3]    = _mom_tanh(r_eth − r_btc, MOM_BARS_ROT) × TARGET_ROT      # rotation row
b[:,4]    = _mom_tanh(r_eth − r_sol, MOM_BARS_ROT) × TARGET_ROT      # rotation row
```
Using `tanh` instead of raw `sign()` gives a **smooth** target that eases through 0 near trend crossovers instead of an instantaneous ±2τ flip — this was the deliberate v4 fix for the "primary MaxDD driver" identified in earlier versions.

### Constants (canonical / v4)

| Constant | Value | Meaning |
|---|---|---|
| `KAPPA` | 0.05 | Alpha-tracking strength κ in `F_base` |
| `EPSILON` | 1e-12 | ODE singular-set regularisation (denominator floor in `rhs`) |
| `DT` | 0.10 | Euler integration step |
| `TARGET_DIR` (τ_dir) | 0.18 | Directional-alpha target amplitude |
| `TARGET_ROT` (τ_rot) | 0.20 | Rotation-alpha target amplitude |
| `MOM_BARS_DIR` | 7×24=168h | Directional momentum window — longer ⇒ fewer flips ⇒ lower drawdown |
| `MOM_BARS_ROT` | 3×24=72h | Rotation momentum window — kept short/faster |
| `MOM_TANH_S` | 2.0 | tanh steepness; `sign(x)=tanh(S·x)` in the limit S→∞ |
| `W_MAX` | 0.10 | Hard per-asset position box constraint |
| `THETA_PCTILE` | 50 | Percentile of training E used to set θ |
| `LW_SHRINK_FLOOR` | 1e-8 | Ledoit-Wolf shrinkage floor on Σ_f |

---

## 4. Direction sources — what actually decides long vs. short

This is the most important section given the locked production rule. Three generations exist:

### 4a. Legacy naive momentum (v19, phase-gated)
`setup_a_directional(df, omega, mfls, gamma, phase)` — [run_crypto_pairs_v19.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_pairs_v19.py#L671):
```
A     = mfls/(gamma+1e-9)
w1_g  = Ω_rank.where(Ω_rank>=0.50, 0)          # coherence gate
w2_g  = A_rank.where(A_rank>=0.33, 0)          # activity gate
mom5  = sign(ret5_eth)                          # raw 5-bar return sign
d     = mom5   if phase==2 (crash/transition)
      = +1.0   if phase==3 (boom, forced long)
      = 0                otherwise (mom5 unused/unset)
position = clip(d × w1_g × w2_g, -1, 1)
```
Direction (`mom5`, or the forced `+1`) is odd/signed; `w1_g`/`w2_g` are non-negative magnitude gates only — **this pattern (signed direction × non-negative gates) is the template every later version follows.**

### 4b. Smoothed tanh momentum (v4/canonical, current production)
`_mom_tanh` inside `build_target_b` (§3 above) — replaces the discontinuous `sign()` with `tanh(S·mom/std(mom))`, feeding `b_t` directly rather than a separate direction variable. This is what backs the v3 steady-incremental strategy work.

### 4c. Eigen-direction (researched, formally CLOSED — do not deploy)
[crypto_eigen_direction_patch.py](../../../../crypto_eigen_direction_patch.py) (open file):

| Function | Formula | Status |
|---|---|---|
| `compute_crypto_eigen_direction` (v1, original) | Rolling `eigh()` of row-normalized abs-correlation `W`; `evec_r[t] = v_max[ret_idx]` | **Buggy** — eigenvector sign ambiguity (`Wv=λv ⟺ W(-v)=λ(-v)`) causes arbitrary sign flips every window (`flip_rate=0.125` measured) |
| `compute_crypto_eigen_direction_v2` | Same, + sign-continuity correction (`flip v_max if v_max·v_prev<0`) + shrinkage `W_reg=(1-ρ)W+ρI` | **Fixed and stable** (`flip_rate=0.000`), but Sharpe 0.186 — still worse than naive momentum |
| `compute_energy_gate` | `E(S)=S^TΣ0⁻¹S` (Mahalanobis energy, rolling shrinkage-regularized Σ0), `gate=E.expanding(60).rank(pct=True)` | Confidence gate only (Theorem 1: even, no direction) |
| `setup_energy_direction_separated` (EDS) | `signal = sign(D_v2) × gate(E)` | Theorem 3: provably odd overall (`signal(-S)=-signal(S)`), but Sharpe -1.064 in ablation — worse, not better |

**Verdict (ablation, [ablation_energy_direction.py](../../../../research/adaptive-friction/pipeline/results/ablation_energy_direction.py), 2021–2026 ETH 1h)**:

| variant | Sharpe | flip_rate |
|---|---:|---:|
| naive_momentum (production) | **0.613** | 0.034 |
| eigen v1 (buggy) | -1.119 | 0.125 |
| eigen v2 (fixed) | 0.186 | 0.000 |
| EDS full | -1.064 | 0.000 |

Fixing the instability does not recover edge — naive momentum remains the production direction source. Do not re-wire eigen/EDS variants into `build_w_star`.

### 4d. Locked rule (v26 failure → v27 fix)
- **v26 (Sharpe -0.30, catastrophic)**: used `sign(cos_theta)` as direction. `cos_theta` is bilinear/even, engine-internal, mean -0.71 in test panel ⇒ force-shorted a 3-year bull market.
- **v27 fix**: direction must come from each strategy's own signed PnL (or `mom5`/momentum); `Ω, A, cos_theta, kramers_p` used **only as non-negative gates**.

---

## 5. Pairs / relative-value signals

`compute_rolling_spread_v8(log_a, log_b, ret_a, ret_b, train_mask, beta_window=252)` — [run_crypto_pairs_v19.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_pairs_v19.py#L449):

| Variable | Formula | Interpretation |
|---|---|---|
| `beta` (β) | rolling OLS: `log_a = alpha + beta·log_b` over 252-bar window | Hedge ratio between the two legs |
| `spread` | `log_a − alpha − beta·log_b` | Residual (cointegration-style spread) |
| `z` | `(spread − train_mean) / train_std` | Standardized spread vs. its **training-period** distribution (frozen, no lookahead into test) |
| `var_ratio` | `std(spread,30) / std(spread,252)` | Short-vs-long vol ratio — regime/volatility-of-spread indicator |
| `beta_velocity` | `|beta.diff(21)| / rolling_mean(|beta|,252)` | How fast the hedge ratio itself is changing (structural instability of the pair) |
| `poa` | `rolling_corr(ret_a, ret_b, 60).abs()` | "Persistence of alignment" — how correlated the two legs' returns currently are |
| `sret` | `(ret_a − beta·ret_b)/(1+|beta|+1e-9)` | Spread return actually traded (dollar/beta-neutral combination) |

`SpreadUDLClassifier` — [run_crypto_pairs_v19.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_pairs_v19.py#L492): extracts 14 statistical features per rolling window of the spread (variance, entropy, Wasserstein-vs-Gaussian distance, skew/kurtosis, autocorrelation, spectral entropy/peak/centroid, trend slope, residual variance, 2nd-difference roughness) and classifies each window into:
- `udl_state`: **0** = normal/tradeable, **1** = degenerate (too low variance/magnitude), **2** = novel/structural-break (high novelty vs. reference directions from an SVD basis of training deviations)
- `udl_mag`: deviation magnitude from the training centroid
- `udl_novelty`: `1 − max(cosine-similarity to reference directions)`

`compute_manifold_validity(z_spread, sret, drift_thresh=1.0, drift_win=60)` — [run_crypto_pairs_v19.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_pairs_v19.py#L614): `drift_ok = rolling_mean(|z|,60) < 1.0` — gates out spreads that have drifted too far from their calibrated mean (cointegration breakdown check).

`route_pair_v7(omega, A_rank, z_spread, udl_state, poa, manifold_valid, z_threshold=1.0)` — [run_crypto_pairs_v19.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_pairs_v19.py#L634):
```
gate = (Ω>=Ω_median) & (A_rank>=0.33) & (|z|>1.0) & manifold_valid
direction = -sign(z)                         # fade the spread (mean-reversion)
base_size = min(|z|,2.0)/2.0
if udl_state==0: size = base_size × clip((poa-0.30)/(0.80-0.30), 0, 1)   # normal regime, scale by alignment persistence
if udl_state==2: size = base_size × 0.50 (STRUCT_SIZE_SCALE)             # structural-break regime, halved
if udl_state==1: no trade (degenerate)
```

`route_btcalt_macro(df, omega, A_rank, dA_rank)` — [run_crypto_pairs_v19.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_pairs_v19.py#L668):
```
gate = (Ω>=Ω_median) & (A_rank>=0.33)
btc_flight (pos_btc) when btc_dom_z > 1.0    → size = min(dom_z,2)/2
alt_season (pos_alt) when btc_dom_z < -1.0 AND cross_disp_z > 1.0 → size = 1.0
```
Captures BTC-dominance flight-to-safety vs. alt-season rotation regimes.

---

## 6. Strategy book (signed PnL sources feeding the allocator)

| Strategy key | Function | Formula / rule | Status |
|---|---|---|---|
| `trend` (v18_smooth) | `pos_A_dir` via `setup_a_directional` + `compute_state_vector`/`compute_geom_signals_v18_smooth`/`apply_geom_penalties_v18` for leverage overlay | Momentum-direction × coherence/activity gates, leverage-dialed | Kept — contribution Sharpe +1.6 to +2.6 |
| `pairs` | mean of P1(ETH/BTC), P2(ETH/SOL), P3(ETH/BNB) via `route_pair_v7` | Dollar/beta-neutral spread-fade | Kept — contribution Sharpe +0.93 to +1.64 |
| `macro` | mean of `M1_BTC_macro` + `M1_ALT_macro` via `route_btcalt_macro` | BTC-dominance/alt-season rotation | Kept — contribution Sharpe +2.45 to +2.62 (best contributor) |
| `breakout` (Donchian) | `compute_donchian_breakout(df, win_in=20, win_out=10)` — [run_crypto_pairs_v26.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_pairs_v26.py#L79): `+1` if price > 20d high, `-1` if < 10d low, hold until channel exit | **Dropped in v28** — zero edge, 7× the vol of trend, polluted PnL 140% even after quality-gating |
| `mr` (mean-reversion) | `compute_mean_reversion(df, win=10, z_in=2.0, z_out=0.5)` — [run_crypto_pairs_v26.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_pairs_v26.py#L117): z-score of rolling-5d return fade, enter at `|z|>2`, exit at `|z|<0.5` | **Dropped in v27** — contribution Sharpe -2.27, "structurally wrong for crypto" (locked rule) |

`get_daily_pnl(pos, ret) = pos.shift(1).fillna(0) × ret` — the universal causal PnL formula (1-bar lag prevents lookahead) used by every strategy above.

---

## 7. Allocators — turning multiple signed-PnL strategies into one book

### v27: Unsigned engine-state weights (direction stays with each strategy)
`compute_unsigned_weights(F, win=252, smooth_span=3, g_lo=0.50, k_lo=0.30)` — [run_crypto_pairs_v27.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_pairs_v27.py#L75):
```
geom_n = sigmoid(rolling_z(geom_score, win=252, lag=1))
prec_n = sigmoid(rolling_z(precursor_score, win=252, lag=1))
align  = |cos_theta|                                    # coherence, never signed

mag_trend    = align × (1−geom_n) × (1−prec_n)          # calm + coherent
mag_breakout = align × kramers_p × (1−geom_n)           # escape-probable + coherent
mag_macro    = align × geom_n × (1−kramers_p)           # stressed + coherent + trapped
mag_mr       = (1−align) × prec_n                        # incoherent + warning
mag_pairs    = (1−align) × (1−kramers_p)                 # incoherent + trapped (mkt-neutral)

W = L1-normalize(stack(mag)) → EWM(span=3) smoothed → renormalized
activation = (geom_n > 0.50) & (kramers_p > 0.30)
W = W × activation
pnl_t = lev[t-1] × Σ_s W[t-1,s]·pnl_s[t]
```
Every `mag_*` term is a **product of non-negative gates only** — no sign anywhere, by design (this is the direct structural fix for the v26 failure).

### v28: Quality + risk-normalized weights (on top of v27's state weights)
`compute_quality_risk_weights(pnl_dict, vol_win=60, sharpe_win=120, sharpe_k=2.0, target_vol=0.01, scale_cap=5.0)` — [run_crypto_pairs_v28.py](../../../../research/adaptive-friction/pipeline/results/run_crypto_pairs_v28.py#L64):
```
scale[s,t]   = clip(target_vol / rolling_std(pnl_s, 60), upper=5.0)      # per-strategy size normalization (Layer 1)
rsharpe[s,t] = rolling_mean(pnl_s,120)/rolling_std(pnl_s,120) × √252
quality[s,t] = sigmoid(rsharpe × sharpe_k)                                # Layer 2 — suppress weak/negative-Sharpe strategies
weight[s,t]  = (quality × scale).shift(1)
```
Then combined: `eff[t,s] = W_state[t-1,s] × Q[t,s]`, renormalized to sum 1, `pnl = lev[t-1] × Σ eff·pnl_s`. This is the fix for v27's finding that L1-normalization let a zero-edge, 7×-vol strategy (breakout) dominate PnL by raw magnitude.

---

## 8. Leverage dial

| Function | Formula | Interpretation |
|---|---|---|
| `compute_leverage_dial(gamma_rank, base=1.5, lo=0.5, hi=1.2)` | `clip(base − gamma_rank, lo, hi)` | High coherence percentile (`gamma_rank`) ⇒ de-lever; calm markets ⇒ lever up toward `hi` |
| `compute_state_vector(omega, gamma_rank, mfls, dA_fast)` | 4 components, each expanding-z-scored: `c1=z(Ω)`, `c2=(gamma_rank-0.5)×2`, `c3=z(mfls)`, `c4=z(dA_fast)` | Composite 4-D engine state vector for the geometric overlay |
| `compute_geom_signals_v18_smooth(V)` | `V_smooth = EMA(V, span)`, `U=V_smooth/‖V_smooth‖`, `dir_phi = ⟨ΔV,U⟩` clipped ≥0, `alignment = ⟨U, EMA(V_smooth,20)/‖·‖⟩` | `phi` = magnitude of state movement *in the direction of current state* (≥0 only — expansion, not contraction); `alignment` = how consistent recent state direction is with medium-term trend |
| `apply_geom_penalties_v18(lev_base, phi, alignment, phi_pen=0.5, align_pen=0.5, ...)` | `lev = lev_base/(1+phi_pen·phi)`; `gate=clip((phi-0.5)/2,0,1)`; `lev *= (1-align_pen·gate·align_pos)`; EMA-smoothed, clipped to `[0.3,1.2]` | De-levers when the engine state is both expanding fast (`phi` high) and persistently aligned (`alignment` high) — i.e. a strong, sustained regime shift in progress |

### Leverage constants

| Constant | Value | Meaning |
|---|---|---|
| `LEV_BASE` | 1.5 | Base leverage before any penalty |
| `LEV_LO` / `LEV_HI` | 0.5 / 1.2 | Global leverage clip |
| `GEOM_PHI_PEN` / `GEOM_ALIGN_PEN` | 0.5 / 0.5 | Penalty strengths in `apply_geom_penalties_v18` |
| `GEOM_EMA_SPAN` | 5 | Smoothing span on final leverage |
| `GEOM_LEV_LO` / `GEOM_LEV_HI` | 0.3 / 1.2 | Clip after geometric penalty |
| `GAMMA_SCORE_WIN` | 126 | Window for `compute_cs_weights` cross-sectional Sharpe weighting |

`compute_cs_weights(pnl_dict, window=126)` — cross-sectional weighting by rolling Sharpe, clipped ≥0, renormalized (equal-weight fallback `1/n` if all Sharpes ≤0). Used in the `v18s`/`v10` trend-strategy blend (distinct from, and older than, the v28 quality-gate).

---

## 9. Summary — the one rule that governs everything above

**Every even/bilinear/magnitude quantity (Ω, A, `cos_theta`, `kramers_p`, `geom_score`, `precursor_score`, energy `E(S)=SᵀΣ⁻¹S`) is used exclusively as a non-negative gate or scaling factor.**
**Every signed/direction decision (`mom5`, `_mom_tanh`, each strategy's own `pos.shift(1)×ret` PnL sign) comes from an odd statistic.**
This is proven mathematically (Theorems 1–3, [crypto_eigen_direction_patch.py](../../../../crypto_eigen_direction_patch.py)) and empirically validated twice: the v26→v27 production fix, and the July-2026 eigen-direction ablation.
