# Godmode Trading Script — Branch Reference

> **Framework**: Canonical Dynamical Geometry System v4 (`canonical_system_v4.pdf`)
> Applied to crypto stat-arb (ETH/BTC/SOL, 1-hour bars, 2021–2026).
> Each script is a self-contained backtest that imports the shared canonical ODE kernel
> and varies only the triple **(S, G, F_base)** — the locked ODE, gradient formula
> `g_X = 2JᵀGS`, and Euclidean projection are **never** modified.

---

## Canonical ODE (locked kernel)

```
Ẋ = F − γ · ⟨F, g_X⟩ / (‖g_X‖² + ε) · g_X

where
  S(X) ∈ Rᵏ               — representation / feature map          (§4.1)
  G ∈ Rᵏˣᵏ, G ≻ 0          — feature-space metric                  (§4.2)
  E(X) = S(X)ᵀ G S(X)      — energy                                (§4.2)
  g_X  = 2 J(X)ᵀ G S(X)   — gradient (single, unique definition)  (§4.3)
  F    = F_base − g_X      — modified force                        (§4.4)
  γ(X) = E / (E + θ)       — adaptive gain ∈ [0, 1)               (§4.5)
```

Four inviolable rules (§5):
1. Geometry enters **only** through `g_X`.
2. All projections use the **Euclidean** inner product.
3. `G_pull = JᵀGJ` is for curvature analysis **only** — never in dynamics.
4. Each object has **exactly one** definition; no duplication.

---

## Branch 1 — Canonical ODE (Deterministic Core)

The base engine, frozen at §3–§5. No stochastic term. Validates the locked
ODE drift with real crypto data and introduces the first geometry diagnostics.

| File | Version | Key contribution |
|------|---------|-----------------|
| `run_crypto_godmode_v28_canonical_stability.py` | **v28** | First integration of canonical diagnostics into live backtesting: `ρ_eff` (effective decay rate) as a soft position throttle; G7 covariance regularisation (`κ(Σ) ≤ κ_max`) to improve admissibility; soft microstructure friction replacing hard vetoes. Base strategy: v27 `funding_hot_guard`. |
| `run_crypto_godmode_v29_regularized_validation.py` | **v29** | Full OOS validation of the v28 canonical engine over 2022–2026. K-sweep at the regularised geometry, fee/slippage stress at K=6 and best-K, extended bear-market (2022) check. Locks in the regularised canonical ODE as the production baseline. |

**Canonical geometry (§8.1 `TradingDomain`):**
```
X = w  (portfolio weights in factor space)
S(w) = A w − b_t           (factor spread)
G    = Σ_f⁻¹               (inverse factor covariance)
F_base(w) = −κ (w − w⋆)   (alpha-tracking mean-reversion)
E(w) = (Aw−b)ᵀ Σ_f⁻¹ (Aw−b)  (squared Mahalanobis spread)
```

---

## Branch 2 — Fractional / Fractal (Appendix D)

Extends S(X) and G with fractional memory operators, implementing the
multi-scale mollified distance framework of Appendix D. Two levels:

| File | Version | Key contribution |
|------|---------|-----------------|
| `run_crypto_godmode_v30_fractional_ricci.py` | **v30** | Power-law weighted covariance (exponential approximation of fractional memory) + log-Euclidean Ricci-style SPD shrinkage on the covariance cone. First fractional branch; "soft" fractional. |
| `run_crypto_godmode_v32_true_fractional.py` | **v32** | **Genuine** fractional calculus. (A) Grünwald-Letnikov fractional differencing `(1−L)^d` on log-prices, `d ∈ (0,1)`, preserving long memory at order `H = d + ½`. (B) Fractional Laplacian Ricci flow on the SPD cone: `log λ_i → sign · |log λ_i|^{1−s}`, pulling the spectrum toward isotropy at sub-linear rate. |

**Fractional geometry:**
```
G_t   = Σ_FL⁻¹
Σ_FL  = fractional-differenced factor covariance
        → condition-capped (κ ≤ κ_max)
        → fractional Laplacian smoothed (parameter s ∈ (0,1))
θ     = v31 disturbance budget accounting for fractional smoothing residual
```

---

## Branch 3 — Itô-BSDT / SDE (§S.1, §16)

Adds a Wiener noise term to the canonical ODE drift, implementing the
stochastic canonical SDE of §S.1:

```
dX = H(X) dt + σ_W Σ(X) dW

Σ_F(X) = I_X(X)^{†/2}   (Fisher-optimal diffusion, §S.2)
I_X     = JᵀI_S J        (pullback Fisher metric)
```

The noise enters **only** through the diffusion term; `H(X)` is the
unchanged canonical-ODE drift; `g_X` and the Euclidean projection are frozen.

| File | Version | Key contribution |
|------|---------|-----------------|
| `run_crypto_godmode_v36_ito_bsdt.py` | **v36** | First real stochastic extension. Fisher-optimal diffusion `Σ = √η · I_X^{−1/2}`. G2.4 stochastic ultimate-boundedness CB override: release CB halt early when the Itô noise budget covers the residual drawdown (`cb_dd ≤ cb_resume + c_σ · lock_bars`). Tests CB-only and ODE+noise variants. |
| `run_crypto_godmode_v38_ito_tightcb.py` | **v38** | Itô-BSDT + G7 covariance regularisation (`κ(Σ₀) ≤ κ_max`) applied to the tight CB (`halt=8%, resume=4%, window=90d`). The production SDE branch. Achieved **$730K final / Calmar 17 / MaxDD −35%**. Basis for v54–v58 champion stack. |

**Itô energy formula (§Thm 16.3):**
```
d/dt E[E(X_t)] = ⟨g_X, H⟩ + ½ σ_W² tr(Σᵀ ∇²E Σ)
```
Mean-square noise floor (§Thm 16.5): `lim_{t→∞} E[E] ≤ σ_W² τ_Σ / (2ρ)`

---

## Branch 4 — Ω-gate (Gain × ODE-Residual Norm)

Discriminant derived from the canonical ODE state at circuit-breaker events:

```
Ω_t = γ_t × ‖f(z_t)‖

where  γ   = E / (E + θ)  — adaptive gain
       f(z) = rhs(X)       — ODE residual (right-hand side norm)
```

High Ω indicates the ODE is far from convergence — the gain is large while
residual forces are unresolved. Entering positions in this state leads to
Mode 1 reversals (empirical 6.4× separation between winner/loser Ω).

| File | Version | Key contribution |
|------|---------|-----------------|
| `run_crypto_godmode_v39_omega_rho.py` | **v39** | Introduces the Ω gate at CB **re-entry**: block release when `Ω ≥ 0.02`. Also adds `ρ_eff` throttle (scale K by effective decay rate) and disturbance-budget gate. Derived from v38 cluster analysis showing zero winning segments blocked at threshold 0.020. |
| `run_crypto_godmode_v48_omega_active.py` | **v48** | Continuous Ω monitor on **every active bar** (not only at CB release). Emergency halt when `Ω_t ≥ ω_thresh` during live trading; lockout for `ω_lockout_bars` or until `Ω_t < ω_resume`. Runs in parallel with equity-based CB; both must clear to resume. Catches Mode 1 reversals before drawdown is booked. |

---

## Branch 5 — Champion Robustness Stack (v54–v58)

Builds on the v35 **$730K champion cell**: `d=0.50, q=0.65, CB halt=8%, resume=4%, window=90d`.
Each version layers additional canonical mechanisms multiplicatively without breaking the champion's productive bars.

| File | Version | Key contribution |
|------|---------|-----------------|
| `v54_730k_fractal_geoflow.py` | **v54** | Adds fractal memory covariance (v30) + Ricci SPD shrinkage + soft position sizing `K_eff = K / (1 + a·γ·‖f(z)‖)` to the champion cell. **Achieved $953K / MaxDD −28.97% / Calmar 23.02** — best result in the series. |
| `v58_dd_gated_brake.py` | **v58** | DD-gated soft brake: `k_dd = max(K_min, 1 − β·dd_excess / (dd_stop − dd_thr))`. Activates **only when live drawdown exceeds `dd_thr`**; floors at `K_min` so the engine participates in recovery. Preserves productive bars (shallow regime untouched). Stacks all v55 canonical mechanisms (G7, G2.4, admissibility brake, curvature sizing, soft-ω, rhs-release filter). |

**Stacked K multipliers (v55+):**
```
K_eff = K_normal
      × y              (dynamic equity throttle)
      × k_admiss       = min(1, c · Ψ⋆ / (‖rhs‖ + ε))   [admissibility brake]
      × k_curv         = 1 / (1 + b · ‖rhs‖)             [curvature sizing]
      × k_omega        = 1 / (1 + a · γ · ‖rhs‖)         [soft-ω sizing]
      × k_dd           = max(K_min, 1 − β·dd_excess/…)    [v58 DD brake]

where  Ψ⋆ = σ θ μ_G / √M_G   (§Thm 7.4 ultimate-bound threshold)
```

---

## Version Lineage Summary

```
v1–v2   Core canonical ODE + stat-arb trading domain (§8.1)
v3–v7   Signal filters, alarm logic, angular discriminant, exec shell
v8–v9   Multi-asset extension (ETH/BTC/SOL)
v10–v14 Clustering, k-sweep, parameter optimisation
v15–v17 Cost/fee backtesting, period reporting
v18–v24 Circuit-breaker (CB) design: reset, window, decay, directional
v25–v27 Microstructure features: TBR, funding rate, dollar-volume
v28–v29 ── BRANCH 1: Canonical ODE + G7 regularisation ──
v30, v32 ─ BRANCH 2: Fractional / Fractal geometry ──────
v31     Disturbance budget (Ψ⋆ calibration)
v33–v35 CB refinement → v35 $730K champion cell locked
v36–v38 ── BRANCH 3: Itô-BSDT / SDE ────────────────────
v39–v48 ── BRANCH 4: Ω-gate (continuous + at-release) ──
v49–v53 Mode 1 feature search, segment clustering, champion filters
v54–v58 ── BRANCH 5: Champion robustness stack ──────────
```

---

## Canonical Module Reference

| Module | Section | Contents |
|--------|---------|---------|
| `collapse_geometry/canonical/core.py` | §3–§5, §7 | Locked ODE kernel, integrator, Hessian, stability metrics |
| `collapse_geometry/canonical/stochastic.py` | §S.1, §16 | SDE, Euler–Maruyama, Fisher noise, Itô formula, MC |
| `collapse_geometry/canonical/extensions.py` | App. D–H | Fractal, Contact, Geometric-Flow, Fisher/NG extensions |
| `collapse_geometry/canonical/domains.py` | §8.1–§8.4 | TradingDomain, Galerkin, Optimisation, Robotics |
| `collapse_geometry/canonical/verification.py` | §10, §H.1.2 | 10-item checklist, FD gradient correctness check |
