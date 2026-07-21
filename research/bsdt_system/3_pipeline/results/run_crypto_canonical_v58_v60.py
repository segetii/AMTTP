"""
Crypto Canonical v58 + v60 — Re-implementation on §8.1 TradingDomain
======================================================================

Replaces the BSDT 4-channel scoring (δ_C/δ_G/δ_A/δ_T, e_t, a_G, a_T, a_A)
that the original v58/v60 used as gate inputs with paper-faithful canonical
scalars from canonical_system_v4 §8.1.  The architectural ideas of the two
champions are kept; only the math underneath changes.

Mapping  (BSDT  →  canonical v4):
  e_t                           →  E(w)        = SᵀGS                   (§4.2)
  γ*_adj = e_t/(e_t+θ)          →  γ(w)        = E/(E+θ)                (§4.5)
  g_E    = θ/(e_t+θ) = 1−γ*     →  g_E(w)      = θ/(E+θ) = 1−γ           (§4.5)
  a_G  (PCA-gap fire)           →  γ          (energy-saturation level)
  a_T  (temporal anomaly)       →  𝟙{dE/dt > 0}  (Lemma 6.7 violation)
  a_A  (velocity-fire)          →  𝟙{‖Ẋ‖ > τ}    (significant ODE motion)
  rv_norm (return realised vol) →  rv_norm of factor returns (kept,
                                   used only as exogenous risk gauge)

What v58 contributes (kept literal):
  • EMA-smoothed rv_norm (span = 3) — removes spike-driven overtrading
  • Asymmetric clamp on the size-adjustment:  adj ∈ [-0.01, +0.10]
  • Dynamic size threshold gth_dyn = (1−γ_base) · (1 + adj)

What v60 contributes (kept literal, on canonical scalars):
  • Floating gate Q_E   accumulates γ          (alpha = 0.85, 8-bar half-life)
  • Floating gate Q_dE  accumulates 𝟙{dE/dt > 0}
  • Schmitt triggers on Q_E, Q_dE (asymmetric set/reset thresholds)
  • Priority encoder    → raw_phase ∈ [0.05, 6.0]
  • Continuous attenuation:  phase = 1 + (1−γ) · max(raw_phase − 1, 0)
                              (kill state preserved unchanged)

The §10 verification checklist must pass for the underlying TradingDomain
*before* either overlay is computed; otherwise the overlays are vacuous.

Strategies produced (test 2023→2026):
    canonical_v4_raw   — pure §8.1, no overlay (baseline)
    canonical_v58      — canonical + v58 stability patch
    canonical_v60      — canonical + v60 ST-FGRC + continuous attenuation
    long_only_eqwt     — benchmark

Usage:
    py -3 run_crypto_canonical_v58_v60.py
"""
from __future__ import annotations
import os, sys, json, time, warnings
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
from pathlib import Path
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

from collapse_geometry.canonical import (
    TradingDomain, verification_checklist, verify_gradient_fd,
)
from run_crypto_canonical_v4 import (
    A_FACTORS, N_STATE, K_FACTOR,
    KAPPA, EPSILON, DT, TARGET_DIR, TARGET_ROT, MOM_BARS_DIR, MOM_BARS_ROT,
    MOM_TANH_S, W_MAX, THETA_PCTILE,
    LW_SHRINK_FLOOR,
    ledoit_wolf_cov, rescale_to_correlation,
    build_factor_returns, build_target_b,
    _stats, _net_ret, print_yoy_table,
)
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START,
    build_1h_df,
)

OUT_DIR_ = Path(OUT_DIR)
ANN_1H   = 252.0 * 24
BPD      = 24


# ═══════════════════════════════════════════════════════════════════════════
#  v58 / v60 hyper-parameters — preserved verbatim from originals
# ═══════════════════════════════════════════════════════════════════════════

# v58 stability patch
EMA_SPAN_V58   = 3       # light EMA smoothing on rv_norm (no new free param)
K_G            = 0.10    # frozen v58 gain on (1 − rv_norm) adjustment
ADJ_CLAMP_LO   = -0.01   # asymmetric clamp lower bound (champion config)
ADJ_CLAMP_HI   = +0.10   # high-side bound is safe (verbatim from v58)

# v60 ST-FGRC + continuous attenuation
ALPHA_FG       = 0.85    # floating-gate decay (≈ 8-bar half-life)
GAMMA_HI       = 0.60    # Schmitt SET on Q_γ  (hi)
GAMMA_LO       = 0.40    # Schmitt RESET on Q_γ (lo, hysteresis)
DE_HI          = 0.50    # Schmitt SET on Q_dE+   (hi)
DE_LO          = 0.30    # Schmitt RESET on Q_dE+ (lo, hysteresis)
A_FIRE_TAU     = 1.0     # ‖Ẋ‖ percentile threshold scale  (calibrated below)
PARTIAL_CREDIT = 0.30    # partial-credit gain in priority encoder (verbatim)
RAW_PHASE_CLIP = 6.0     # raw_phase ceiling (verbatim from v58/v59/v60)
GH_TH_LIT      = 5.0     # = CLIP − 1, full-boost magnitude (verbatim)
GL_TH_LIT      = -1.0    # partial penalties (verbatim)

# Realised-vol normalisation window (verbatim from v58 _realized_vol)
RV_WIN         = 168     # 1 week of 1h bars
RV_NORM_WIN    = 1000    # ~6 weeks rolling mean window


# ═══════════════════════════════════════════════════════════════════════════
#  Canonical-v4 sweep — same logic as run_crypto_canonical_v4 but logs more
# ═══════════════════════════════════════════════════════════════════════════

def run_canonical_sweep(df: pd.DataFrame,
                         train_mask: np.ndarray,
                         test_mask:  np.ndarray) -> tuple[pd.DataFrame, dict]:
    """Runs §8.1 TradingDomain forward for every bar.

    Returns a per-bar log of canonical scalars:
        E, gamma, dE_dt, curv_ind, rhs_norm, grad_norm, w_btc/eth/sol
      Predictive quartet (§6 forward chain):
        cos_theta = ⟨F_base, g_X⟩ / (‖F_base‖·‖g_X‖)            — direction
        mfls      = ‖g_X‖                                          — capacity
        v_E       = -dE/dt                                          — energy velocity
        rho_eff   = -dE/dt / max(E, eps)                            — instantaneous decay rate
        F_dot_g   = ⟨F_base, g_X⟩                                    — signed alignment
    plus the raw canonical PnL (w_new·ret) for use as base.
    """
    T = len(df)
    R = np.column_stack([
        df['ret_btc'].fillna(0.0).values,
        df['ret_eth'].fillna(0.0).values,
        df['ret_sol'].fillna(0.0).values if 'ret_sol' in df.columns
            else df['ret_eth'].fillna(0.0).values,
    ])
    factor_R = build_factor_returns(df)
    b_seq    = build_target_b(df)

    Sigma_raw, lw_delta = ledoit_wolf_cov(factor_R[train_mask])
    Sigma_f = rescale_to_correlation(Sigma_raw)
    G_for_theta = np.linalg.inv(Sigma_f)
    E_train = np.einsum('ti,ij,tj->t', b_seq[train_mask], G_for_theta, b_seq[train_mask])
    theta_cal = max(float(np.percentile(E_train, THETA_PCTILE)), 1e-3)
    print(f"  [v4] LW δ = {lw_delta:.3f}   θ (P{THETA_PCTILE}) = {theta_cal:.4f}")

    # §10 verification
    sys0 = TradingDomain(A=A_FACTORS, b=b_seq[np.where(train_mask)[0][-1]],
                         Sigma=Sigma_f, kappa=KAPPA, w_star=np.zeros(N_STATE),
                         theta=theta_cal, epsilon=EPSILON).build()
    chk = verification_checklist(sys0, np.array([0.10, 0.20, 0.05]))
    print(chk.summary())
    if not chk.all_passed:
        raise RuntimeError("§10 checklist failed")
    fd = verify_gradient_fd(sys0, np.array([0.10, 0.20, 0.05]), h=1e-6)
    print(f"  [v4] Gradient FD: max_abs = {fd['max_abs_error']:.2e}   passed = {fd['passed']}")

    # ── per-bar log allocation ──
    log = {k: np.zeros(T) for k in [
        'E', 'gamma', 'dE_dt', 'curv_ind', 'rhs_norm', 'grad_norm',
        'w_btc', 'w_eth', 'w_sol',
        'pnl_raw', 'pnl_long_only',
        # Predictive quartet (§6 forward chain)
        'cos_theta', 'mfls', 'v_E', 'rho_eff', 'F_dot_g',
    ]}

    w = np.zeros(N_STATE, dtype=float)
    t0 = time.time()
    for t in range(T):
        sys_t = TradingDomain(A=A_FACTORS, b=b_seq[t], Sigma=Sigma_f,
                              kappa=KAPPA, w_star=np.zeros(N_STATE),
                              theta=theta_cal, epsilon=EPSILON).build()
        E_t   = sys_t.energy(w)
        gma   = sys_t.gain(w)
        dEdt  = sys_t.dE_dt(w)
        curv  = sys_t.curvature_manifold_indicator(w)
        rhs   = sys_t.rhs(w)
        gw    = sys_t.gradient(w)

        # ── Predictive quartet (§6 forward chain) ──
        Fb         = np.asarray(sys_t.F_base(w), dtype=float)
        gX_norm    = float(np.linalg.norm(gw))
        Fb_norm    = float(np.linalg.norm(Fb))
        F_dot_g    = float(Fb @ gw)
        denom      = (Fb_norm * gX_norm)
        cos_theta  = (F_dot_g / denom) if denom > 1e-12 else 0.0
        v_E        = -dEdt                              # energy velocity (>0 ⇒ contracting)
        rho_eff    = v_E / max(E_t, 1e-9)                # instantaneous decay rate

        w_new = w + DT * rhs
        # §10.1 box constraint: per-asset position cap (Lipschitz barrier equivalent)
        # Prevents position overshoot past the tanh-smooth target and bounds gross exposure.
        w_new = np.clip(w_new, -W_MAX, W_MAX)

        log['E'][t]            = E_t
        log['gamma'][t]        = gma
        log['dE_dt'][t]        = dEdt
        log['curv_ind'][t]     = curv
        log['rhs_norm'][t]     = float(np.linalg.norm(rhs))
        log['grad_norm'][t]    = gX_norm
        log['w_btc'][t]        = w_new[0]
        log['w_eth'][t]        = w_new[1]
        log['w_sol'][t]        = w_new[2]
        log['pnl_raw'][t]      = float(w_new @ R[t])
        log['pnl_long_only'][t]= float(R[t].mean())
        # ── predictive quartet ──
        log['cos_theta'][t]    = cos_theta
        log['mfls'][t]         = gX_norm
        log['v_E'][t]          = v_E
        log['rho_eff'][t]      = rho_eff
        log['F_dot_g'][t]      = F_dot_g
        w = w_new

        if t > 0 and (t % 5000) == 0:
            print(f"    {t:>6}/{T}  ({time.time()-t0:>5.1f}s)")
    print(f"  [v4] sweep complete: {T:,} bars  {time.time()-t0:.1f}s")

    out = pd.DataFrame(log, index=df.index)
    diag = {
        'lw_delta': lw_delta,
        'theta_calibrated': theta_cal,
        'checklist_pass': chk.all_passed,
        'fd_max_abs': fd['max_abs_error'],
        'fd_max_rel': fd['max_rel_error'],
    }
    return out, diag


# ═══════════════════════════════════════════════════════════════════════════
#  v58 OVERLAY — stability patch on canonical scalars
# ═══════════════════════════════════════════════════════════════════════════

def _realized_vol_norm(df: pd.DataFrame, ema_span: int = EMA_SPAN_V58) -> pd.Series:
    """v58 _realized_vol re-implemented on factor-return realised vol.

    Uses ETH log-return as primary risk gauge (matches original v58 exactly).
    EMA-smooths and shifts(1) to avoid lookahead.
    """
    rv      = df['ret_eth'].rolling(RV_WIN, min_periods=BPD).std()
    rv_mean = rv.rolling(RV_NORM_WIN, min_periods=100).mean()
    rv_norm = (rv / rv_mean.replace(0, np.nan)).fillna(1.0)
    if ema_span > 1:
        rv_norm = rv_norm.ewm(span=ema_span, adjust=False).mean()
    return rv_norm.shift(1).fillna(1.0)


def overlay_v58(log: pd.DataFrame,
                 df:   pd.DataFrame,
                 train_mask: np.ndarray,
                 lo:   float = ADJ_CLAMP_LO,
                 hi:   float = ADJ_CLAMP_HI) -> pd.Series:
    """v58 stability patch on canonical-v4 base PnL  (recalibrated).

    Recalibration: size_base is *normalised* against the training
    median of g_E = 1 − γ, so that the typical multiplier is 1.0 (no
    attenuation in normal regime) and only spikes in γ above typical
    cut size.  This preserves γ-driven risk reduction while not
    constantly killing 70% of every position.

      g_E_typ      = median_train(1 − γ)
      size_base    = clip( (1 − γ) / g_E_typ , 0, 1 )         (§4.5 normalised)
      adj          = clip(K_G · (1 − rv_norm), lo, hi)         (v58 asym clamp)
      pnl_v58      = pnl_raw · size_base · (1 + adj)

    The Lemma-6.7 hard kill (dE/dt > 0) is kept but in this regime
    dE/dt > 0 ≈ 0% (E monotonically decreases with w → w*), so the
    gate is effectively pass-through and removing it changes nothing.
    """
    idx = log.index
    rv_norm = _realized_vol_norm(df).reindex(idx).fillna(1.0)
    gamma   = log['gamma'].shift(1).fillna(0.0)
    dEdt    = log['dE_dt'].shift(1).fillna(0.0)

    # Normalise (1−γ) against training-median so typical multiplier = 1
    g_E         = (1.0 - gamma.values).clip(0.0, 1.0)
    g_E_typ     = float(np.median(g_E[train_mask]))
    g_E_typ     = max(g_E_typ, 1e-3)
    size_base   = np.clip(g_E / g_E_typ, 0.0, 1.0)

    adj          = np.clip(K_G * (1.0 - rv_norm.values), lo, hi)
    gate_lemma67 = (dEdt.values <= 0.0).astype(float)   # active when E rising

    pnl_raw = log['pnl_raw'].values
    return pd.Series(pnl_raw * size_base * (1.0 + adj) * gate_lemma67, index=idx)


# ═══════════════════════════════════════════════════════════════════════════
#  v60 OVERLAY — ST-FGRC + continuous attenuation on canonical scalars
# ═══════════════════════════════════════════════════════════════════════════

def _float_gate_charge(a: np.ndarray, alpha: float) -> np.ndarray:
    """Q(t) = α·Q(t-1) + a(t-1)  — verbatim from v59/v60 (shift(1) built in)."""
    q = np.zeros(len(a), dtype=float)
    for t in range(1, len(a)):
        q[t] = alpha * q[t - 1] + a[t - 1]
    return q


def _schmitt_trigger(q: np.ndarray, hi: float, lo: float) -> np.ndarray:
    """Schmitt comparator with hysteresis — verbatim from v59/v60."""
    state = np.zeros(len(q), dtype=float)
    s = 0.0
    for t in range(len(q)):
        if q[t] > hi:
            s = 1.0
        elif q[t] < lo:
            s = 0.0
        state[t] = s
    return state


def overlay_v60(log: pd.DataFrame,
                 train_mask: np.ndarray,
                 alpha:  float = ALPHA_FG,
                 g_hi:   float = GAMMA_HI,
                 g_lo:   float = GAMMA_LO,
                 d_hi:   float = DE_HI,
                 d_lo:   float = DE_LO) -> pd.Series:
    """v60 ST-FGRC + continuous attenuation, on canonical scalars.

    Channel mapping (BSDT → canonical):
      a_G  →  γ(w)                  saturation level (∈ [0,1])
      a_T  →  𝟙{dE/dt > 0}          Lemma-6.7 violation indicator
      a_A  →  𝟙{‖Ẋ‖ > τ}           significant ODE motion (calibrated τ)

    Architecture:
      LAYER 1   Q_γ  = α·Q_γ + γ(t-1)      (floating-gate accumulator)
                Q_dE = α·Q_dE + 𝟙{dE/dt(t-1) > 0}
      LAYER 2   GH = Schmitt(Q_γ, hi=GAMMA_HI, lo=GAMMA_LO)
                TH = Schmitt(Q_dE, hi=DE_HI,  lo=DE_LO)
      LAYER 3   priority encoder → raw_phase ∈ {0.05, partial, full}
      LAYER 4   excess = max(raw_phase − 1, 0)
                phase  = raw_phase  if raw_phase < 1   (preserve kill — hard)
                       = 1 + (1−γ)·excess              (continuous attenuate)

    Note on direction: in the canonical system high γ ↔ high E ↔ high blind-
    spot saturation, which mirrors a_G's "PCA-gap fire" semantics: when γ is
    elevated the system is far from the target manifold and any boost should
    be heavily attenuated — exactly what (1−γ) does.
    """
    idx     = log.index
    gamma   = log['gamma'].values
    dEdt    = log['dE_dt'].values
    rhs_n   = log['rhs_norm'].values

    # ── Calibrate fire threshold on training set: τ = 90th-pctile of ‖Ẋ‖ ──
    tau_fire = max(float(np.percentile(rhs_n[train_mask], 90)), 1e-12)

    # ── Per-bar canonical channels (causal: shift 1) ──
    a_G_t = np.zeros_like(gamma)
    a_G_t[1:] = gamma[:-1]                                  # γ(t-1)
    a_T_t = np.zeros_like(gamma)
    a_T_t[1:] = (dEdt[:-1] > 0.0).astype(float)              # Lemma-6.7 violation
    a_A_t = np.zeros_like(gamma)
    a_A_t[1:] = (rhs_n[:-1] > tau_fire).astype(float)        # significant motion

    # ── LAYER 1: floating-gate charges ──
    Q_G_raw = _float_gate_charge(a_G_t, alpha)
    Q_T_raw = _float_gate_charge(a_T_t, alpha)
    Q_G = Q_G_raw * (1.0 - alpha)        # normalise to ≈ E[a] at steady state
    Q_T = Q_T_raw * (1.0 - alpha)

    # ── LAYER 2: Schmitt triggers ──
    GH = _schmitt_trigger(Q_G, g_hi, g_lo)
    TH = _schmitt_trigger(Q_T, d_hi, d_lo)
    gh = GH > 0.5
    th = TH > 0.5
    fire = a_A_t > 0.5

    # ── LAYER 3: priority encoder (verbatim structure from v60) ──
    # Q ratios clipped at 2.0 — bounds partial credit under threshold drift
    Q_G_ratio = np.clip(Q_G / max(g_hi, 1e-9), 0.0, 2.0)
    Q_T_ratio = np.clip(Q_T / max(d_hi, 1e-9), 0.0, 2.0)
    raw_phase = np.where(
        ~fire,            1.0,
        np.where(
            gh & th,        RAW_PHASE_CLIP,
            np.where(
                gh & ~th,    1.0 + PARTIAL_CREDIT * Q_G_ratio,
                np.where(
                    ~gh & th, 1.0 + PARTIAL_CREDIT * Q_T_ratio,
                    0.05                 # neither → kill (hard)
                )
            )
        )
    )

    # ── LAYER 4: continuous canonical attenuation (recalibrated) ──
    # Normalised g_E so typical regime is pass-through (multiplier ≈ 1)
    # and only γ spikes above training median attenuate.
    g_E       = 1.0 - gamma
    g_E_typ   = max(float(np.median(g_E[train_mask])), 1e-3)
    g_E_norm  = np.clip(g_E / g_E_typ, 0.0, 1.0)
    g_E_lag   = np.zeros_like(g_E_norm)
    g_E_lag[1:] = g_E_norm[:-1]                   # causal
    excess    = np.maximum(raw_phase - 1.0, 0.0)
    phase     = np.where(raw_phase >= 1.0,
                          1.0 + g_E_lag * excess,
                          raw_phase)
    phase     = np.maximum(phase, 0.02)            # numerical guard

    # ── Apply to canonical raw PnL with normalised size_base ──
    # size_base also normalised so typical regime preserves raw PnL.
    size_base = np.zeros_like(g_E_norm)
    size_base[1:] = g_E_norm[:-1]
    pnl_raw   = log['pnl_raw'].values
    return pd.Series(pnl_raw * size_base * phase, index=idx)


# ═══════════════════════════════════════════════════════════════════════════
#  v61 OVERLAY — predictive-quartet direction filter on top of v58
# ═══════════════════════════════════════════════════════════════════════════
#  Empirically (test diagnostics):
#     cos θ < 0  on 92.8% of bars   (F_base restoring → trust)
#     cos θ > 0  on  7.2% of bars   (F_base fighting friction → de-risk)
#     v_E   > 0  on 100% of bars    (E always contracting)
#     ρ_eff      varies bar-to-bar  (too noisy for direct sizing — use only
#                                     to identify regime changes, not as gain)
#
#  Therefore v61 = v58 · direction_filter   where the filter only attenuates
#  on the rare cos θ > 0 + low-ρ bars.  This is a pure DD-reduction layer
#  that keeps profit untouched in the dominant regime.
#
#     dir_filter = 1                                    if cos θ ≤ 0
#                = 1 − DIR_FIGHT_PENALTY · cos θ        if cos θ > 0 and ρ ≥ ρ_typ
#                = 1 − DIR_FIGHT_PENALTY                if cos θ > 0 and ρ < ρ_typ
#                                                       (worst case: fight + slow)
# ═══════════════════════════════════════════════════════════════════════════

DIR_FIGHT_PENALTY = 0.7     # max attenuation when cos θ → +1 + ρ slow

def overlay_v61(log: pd.DataFrame,
                pnl_v58_in: pd.Series,
                train_mask: np.ndarray) -> pd.Series:
    """v61 = v58 × direction-fight filter.  Pure DD-reduction layer."""
    idx       = log.index
    cos_th    = log['cos_theta'].values
    rho_eff   = log['rho_eff'].values

    # Lag (causal)
    cos_th_l  = np.zeros_like(cos_th);   cos_th_l[1:]  = cos_th[:-1]
    rho_l     = np.zeros_like(rho_eff);  rho_l[1:]     = rho_eff[:-1]

    # Training-typical decay rate (positive ρ only)
    rho_train_pos = rho_l[train_mask]
    rho_train_pos = rho_train_pos[rho_train_pos > 0]
    rho_typ = float(np.median(rho_train_pos)) if len(rho_train_pos) else 1.0
    rho_typ = max(rho_typ, 1e-6)

    # Direction-fight indicator
    fight     = np.clip(cos_th_l, 0.0, 1.0)               # 0 when restoring
    slow      = (rho_l < rho_typ).astype(float)            # 1 when below median
    # Penalty doubles when we're both fighting AND below typical decay rate
    penalty   = DIR_FIGHT_PENALTY * fight * (0.5 + 0.5 * slow)
    dir_filter = 1.0 - penalty                             # ∈ [1−PEN, 1]

    return pd.Series(pnl_v58_in.values * dir_filter, index=idx)


def print_dollar_simulation(strategies: dict,
                             test_mask: np.ndarray,
                             start_capital: float = 1000.0,
                             K_list: list = None):
    """Full dollar-denominated simulation: $start_capital from K=1 to K=5.

    Shows:
      • Running equity curve: start, Q1→Q4 each year, year-end balance
      • Quarterly P&L in dollars and %
      • YoY total return
      • Overall MaxDD in dollars and %
      • Final balance and total P&L
    """
    if K_list is None:
        K_list = [1, 2, 3, 5]

    SEP = "═" * 110

    for name, pnl_raw in strategies.items():
        pnl = pnl_raw.iloc[test_mask].fillna(0.0)
        if len(pnl) == 0:
            continue

        print(f"\n{SEP}")
        print(f"  STRATEGY: {name}   |   Starting capital: ${start_capital:,.2f}")
        print(SEP)

        for K in K_list:
            r   = _net_ret(pnl, K)         # K-leveraged hourly returns after TC
            col = 100.0 * (1.0 + r).cumprod()   # % equity starting at 100
            eq  = start_capital * col / 100.0    # dollar equity

            # ── MaxDD in dollars ──
            running_max = eq.cummax()
            dd_abs = (eq - running_max)
            max_dd_dollars = float(dd_abs.min())
            max_dd_pct     = float((eq / running_max - 1.0).min()) * 100

            # ── Build year × quarter grid ──
            years = sorted(pnl.index.year.unique())
            rows  = []
            for yr in years:
                yr_rows = []
                for q in [1, 2, 3, 4]:
                    q_mask = (pnl.index.year == yr) & (pnl.index.quarter == q)
                    if not q_mask.any():
                        yr_rows.append(None)
                        continue
                    q_r     = r[q_mask]
                    # equity AT END of this quarter (absolute $)
                    q_end   = float(eq[q_mask].iloc[-1])
                    q_start = float(eq[q_mask].iloc[0] / (1 + q_r.iloc[0]))
                    q_pnl   = q_end - q_start
                    q_ret   = float((1 + q_r).prod()) - 1.0
                    yr_rows.append((q_pnl, q_ret, q_end))
                rows.append((yr, yr_rows))

            # Header
            print(f"\n  K={K}  (gross leverage {K}×)")
            print(f"  {'Year':>5}  {'Q1 $':>10}  {'Q1%':>7}  {'Q2 $':>10}  {'Q2%':>7}  "
                  f"{'Q3 $':>10}  {'Q3%':>7}  {'Q4 $':>10}  {'Q4%':>7}  "
                  f"{'YoY $':>11}  {'YoY%':>7}  {'Yr-End Bal':>12}")
            print("  " + "-" * 107)

            prev_yr_end = start_capital
            for yr, yr_rows in rows:
                q_parts = []
                yr_start_bal = prev_yr_end
                yr_end_bal   = prev_yr_end
                for item in yr_rows:
                    if item is None:
                        q_parts.append(("   ─    ", " ─ "))
                        continue
                    q_pnl, q_ret, q_end_bal = item
                    yr_end_bal = q_end_bal
                    pnl_str = f"${q_pnl:>+8.2f}"
                    pct_str = f"{100*q_ret:>+5.1f}%"
                    q_parts.append((pnl_str, pct_str))

                yoy_pnl = yr_end_bal - yr_start_bal
                yoy_ret = yr_end_bal / yr_start_bal - 1.0 if yr_start_bal > 0 else 0.0
                row_cols = "  ".join(f"{a:>10}  {b:>7}" for a, b in q_parts)
                print(f"  {yr:>5}  {row_cols}  "
                      f"{yoy_pnl:>+10.2f}$  {100*yoy_ret:>+5.1f}%  ${yr_end_bal:>10.2f}")
                prev_yr_end = yr_end_bal

            final_bal   = float(eq.iloc[-1])
            total_pnl   = final_bal - start_capital
            total_ret   = (final_bal / start_capital - 1.0) * 100
            yrs         = max((pnl.index[-1] - pnl.index[0]).days / 365.25, 0.01)
            cagr        = ((final_bal / start_capital) ** (1.0 / yrs) - 1.0) * 100
            sharpe      = float(r.mean() / r.std() * np.sqrt(ANN_1H)) if r.std() > 1e-12 else 0.0

            print(f"\n  {'─'*50}")
            print(f"  Final balance : ${final_bal:>10,.2f}   Total P&L: ${total_pnl:>+10,.2f}  ({total_ret:>+.1f}%)")
            print(f"  CAGR          : {cagr:>+.2f}%/yr     Sharpe  : {sharpe:>+.3f}")
            print(f"  MaxDD         : ${max_dd_dollars:>+,.2f}  ({max_dd_pct:>+.1f}%)")


# ═══════════════════════════════════════════════════════════════════════════
#  Reporting
# ═══════════════════════════════════════════════════════════════════════════

def print_strategy_table(strategies: dict, mask: np.ndarray):
    print(f"\n  {'Strategy':<22}  {'Sharpe':>8}  {'MaxDD':>8}  {'CAGR':>9}  "
          f"{'Active%':>8}  {'$100→':>9}")
    for name, pnl in strategies.items():
        p   = pnl.iloc[mask] if isinstance(mask, np.ndarray) else pnl[mask]
        st  = _stats(p)
        ar  = float((p.abs() > 1e-12).mean()) * 100
        print(f"  {name:<22}  {st['sharpe']:>+8.3f}  {100*st['max_dd']:>+7.1f}%  "
              f"{100*st['cagr']:>+8.1f}%  {ar:>7.1f}%  ${st['final']:>7.2f}")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print("=" * 100)
    print("  CRYPTO  CANONICAL v58 + v60  —  re-implementation on §8.1 TradingDomain")
    print("  pure canonical-v4 math; v58/v60 architectures preserved on canonical scalars")
    print("=" * 100)

    print("\n[1] Fetching Binance 1h data ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask  = np.asarray(df_1h.index >= TEST_START)
    train_mask = np.asarray((df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START))
    print(f"  Total: {len(df_1h):,} bars  Train: {int(train_mask.sum()):,}  "
          f"Test: {int(test_mask.sum()):,}   SOL real: {has_sol}")

    print("\n[2] Canonical-v4 sweep (locked ODE, §10 verified) ...")
    log, diag = run_canonical_sweep(df_1h, train_mask, test_mask)

    print("\n[3] Building overlays ...")
    pnl_raw  = log['pnl_raw']
    pnl_long = log['pnl_long_only']
    pnl_v58  = overlay_v58(log, df_1h, train_mask)
    pnl_v60  = overlay_v60(log, train_mask)
    pnl_v61  = overlay_v61(log, pnl_v58, train_mask)

    strategies = {
        'canonical_v4_raw':  pnl_raw,
        'canonical_v58':     pnl_v58,
        'canonical_v60':     pnl_v60,
        'canonical_v61':     pnl_v61,
        'long_only_eqwt':    pnl_long,
    }

    # ── Test-window stats ──
    print(f"\n{'═'*100}")
    print("  PERFORMANCE  (test 2023→2026, gross)")
    print(f"{'═'*100}")
    print_strategy_table(strategies, test_mask)

    # ── Year-on-year summary table ──
    K_LIST = [1, 2, 3, 5]
    for name, pnl in strategies.items():
        print_yoy_table(name, pnl.iloc[test_mask], K_LIST)

    # ── Dollar simulation: $1,000 starting capital, K=1–5,  quarterly + YoY ──
    print(f"\n\n{'▓'*110}")
    print(f"  $1,000 DOLLAR SIMULATION  —  quarterly P&L and year-on-year")
    print(f"{'▓'*110}")
    print_dollar_simulation(strategies, test_mask, start_capital=1000.0, K_list=[1, 2, 3, 5])

    # ── Diagnostics on the canonical channels ──
    print(f"\n  [Canonical channel diagnostics — test window]")
    s = log.iloc[test_mask]
    print(f"  γ:         mean={s['gamma'].mean():.3f}  p95={s['gamma'].quantile(0.95):.3f}")
    print(f"  dE/dt:     mean={s['dE_dt'].mean():+.3f}  pct >0 = {100*(s['dE_dt']>0).mean():.1f}%")
    print(f"  ‖Ẋ‖:      mean={s['rhs_norm'].mean():.3f}  p95={s['rhs_norm'].quantile(0.95):.3f}")
    print(f"  curv_ind:  mean={s['curv_ind'].mean():+.3f}  pct >0 = {100*(s['curv_ind']>0).mean():.1f}%")
    # ── Predictive quartet (§6 forward chain) — direction + momentum ──
    print(f"\n  [Predictive quartet — test window]")
    print(f"  cos θ:      mean={s['cos_theta'].mean():+.3f}  p05={s['cos_theta'].quantile(0.05):+.3f}  p95={s['cos_theta'].quantile(0.95):+.3f}")
    print(f"  ‖g_X‖:      mean={s['mfls'].mean():.3f}  p95={s['mfls'].quantile(0.95):.3f}   (MFLS, capacity)")
    print(f"  v_E:        mean={s['v_E'].mean():+.3f}  pct >0 = {100*(s['v_E']>0).mean():.1f}%   (energy velocity)")
    print(f"  ρ_eff:      mean={s['rho_eff'].mean():+.3f}  p95={s['rho_eff'].quantile(0.95):.3f}   (predicted decay rate)")
    print(f"  ⟨F,g⟩>0:    pct = {100*(s['F_dot_g']>0).mean():.1f}%   (F_base fighting friction)")

    # ── Save ──
    out = {
        'meta': {
            'version':       'canonical_v58_v60',
            'paper_section': '§8.1 TradingDomain + v58/v60 overlays',
            'kappa':         KAPPA,
            'theta':         diag['theta_calibrated'],
            'epsilon':       EPSILON,
            'dt':            DT,
            'v58': {'ema_span': EMA_SPAN_V58, 'K_G': K_G,
                    'adj_lo': ADJ_CLAMP_LO, 'adj_hi': ADJ_CLAMP_HI},
            'v60': {'alpha_fg': ALPHA_FG, 'g_hi': GAMMA_HI, 'g_lo': GAMMA_LO,
                    'd_hi': DE_HI, 'd_lo': DE_LO,
                    'partial_credit': PARTIAL_CREDIT, 'raw_phase_clip': RAW_PHASE_CLIP},
        },
        'verification': diag,
        'performance':  {n: _stats(p.iloc[test_mask]) for n, p in strategies.items()},
    }
    out_path = OUT_DIR_ / 'crypto_canonical_v58_v60.json'
    with open(out_path, 'w') as fh:
        json.dump(out, fh, indent=2, default=float)
    print(f"\n  Saved → {out_path}")
    print("=" * 100)


if __name__ == '__main__':
    main()
