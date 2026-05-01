"""
Crypto BSDT v36 — Full Intraday Physics Engine
================================================
Implements the practitioner's guide in full:

  STATE MATRIX  X_t ∈ R^{8×8}  (N=8 instruments × d=8 features, 1h bars)

  INSTRUMENTS (N=8):
    0  BTC perp          1  ETH perp
    2  SOL perp          3  BNB proxy  (ETH × 0.70 decay)
    4  ETH/BTC ratio     5  USDT-dominance (synthetic from BTC-dom)
    6  BTC dominance     7  ETH/SOL ratio

  FEATURES (d=8):
    0  log-return (1h)           1  log-return 4h momentum
    2  volume z-score (24h)      3  realised vol (20 bars)
    4  trend sign (72h)          5  funding rate (daily broadcast)
    6  OI change proxy           7  ATR-norm range

  SIGNALS produced per bar (all from M.pipeline + BSDT):
    e_t         total blind-spot energy  (Mahalanobis²)
    gamma_star  position damping  e_t/(e_t+θ)
    cos_θ       directional filter  (MR supported when <0)
    ψ_t         false-alarm angle   (valid entry when <π/4)
    R_t         controllability margin   (block entry when ≤0)
    RSS_t       regime state score [0,1]
    τ_lin       bars to critical manifold  (exit when <5)
    dom_ch      dominant BSDT channel     (C/G/A/T)
    δ_C/G/A/T   per-bar channel scores (scalar = mean over 8 agents)

  DECISION TREE → per-bar size_mult, entry_ok, exit_now

Usage:
    py -3 run_crypto_pairs_v36_intraday_bsdt.py
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

from collapse_geometry import (
    MasterOperator, Snapshot, LedoitWolfNetwork,
    CollapseGeometry, LyapunovCertificate,
    EarlyWarning, PrecursorScale, InformationGeometry,
    StochasticExtension,
)
from run_crypto_pairs_v34_full_combined import (
    # constants
    OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
    G_LO, K_LO,
    # data builders
    build_1h_df, fetch_and_prepare, fetch_binance_funding,
    add_cross_market_features, add_leverage_features,
    # strategy builders
    build_daily_positions, upsample_daily_to_1h_pnl,
    compute_1h_strategies, compute_quality, assemble_combined,
    # helpers
    yearly_breakdown, simulate_from_pnl,
)

OUT_DIR_ = Path(OUT_DIR)
BPD      = 24    # bars per day at 1h resolution
ANN_1H   = 252.0 * BPD

# ── Engine hyper-parameters ──────────────────────────────────────────────────
N_AGENTS    = 8    # instruments in the state matrix
N_FEATURES  = 8    # features per instrument
PCA_K       = 4    # leading eigenvectors for normal manifold
CALIB_BARS  = 500  # normal-window length (≈21 trading days at 1h)
ALPHA_CONF  = 0.01 # 99th percentile for chi² threshold  (must match v21)
SIGMA_N_FALLBACK = 1e-3

# RSS operating thresholds — z-score space (σ above AGC reference).
# The reference is an asymmetric EMA (slow attack / fast decay) initialized
# from the calibration mean — equivalent to AGC in electronics:
#   slow attack: crisis builds → reference barely moves → z spikes → alarm fires
#   fast decay:  crisis ends  → reference drops quickly → z normalises
# Normal < 0.5σ → pass-through; Elevated 0.5–1.5σ → damp;
# Pre-collapse 1.5–2.5σ → halve; Critical ≥2.5σ → flat.
Z_RSS_NORMAL      = 0.5
Z_RSS_ELEVATED    = 1.5
Z_RSS_PRECOLLAPSE = 2.5

# AGC asymmetric time constants (in 1h bars)
AGC_SPAN_ATTACK = 2160   # 90 days — reference rises very slowly during crises
AGC_SPAN_DECAY  =  168   #  7 days — reference falls quickly after crisis passes

# Minimum calibration σ for a ξ signal to participate in the per-ξ stretch.
# Signals constant in the calibration window (σ < MIN_XI_SIG) are skipped;
# they would always contribute sigmoid(0)=0.5, diluting the product with no info.
MIN_XI_SIG      = 0.01

# Per-ξ tanh-stretch gain — applied to each signal's z-score before geometric mean.
# sigmoid(STRETCH_GAMMA · z) maps z=0 (normal) → 0.50, z=+2σ → 0.998, z=−2σ → 0.002.
# This breaks 5th-root variance compression: dynamic range expands from ~0.055 to ~0.5.
STRETCH_GAMMA   = 3.0

# Legacy absolute thresholds (kept for signal-report readability)
RSS_NORMAL      = 0.20
RSS_ELEVATED    = 0.50
RSS_PRECOLLAPSE = 0.70
RSS_CRITICAL    = 0.90

# τ_lin exit thresholds (bars)
TAU_NORMAL  = 20
TAU_TIGHT   = 5

# Kramers escape reference horizon
KRAMERS_TAU_1H = 24    # 1 day in hourly bars


# ═══════════════════════════════════════════════════════════════════════════
#  1.  BUILD 8×8 STATE MATRIX
# ═══════════════════════════════════════════════════════════════════════════

def build_intraday_state_panel(df_1h: pd.DataFrame,
                                fund_btc: pd.Series | None,
                                fund_eth: pd.Series | None) -> np.ndarray:
    """
    Returns X_panel of shape (T, N_AGENTS, N_FEATURES).

    All features are standardised to zero-mean unit-variance on each
    training window by the physics engine; here we produce raw signals
    in natural units so the engine's internal whitening is correct.
    """
    T = len(df_1h)
    X = np.zeros((T, N_AGENTS, N_FEATURES), dtype=float)

    # ── return series ─────────────────────────────────────────────────────
    r_btc = df_1h['ret_btc'].fillna(0.0).values
    r_eth = df_1h['ret_eth'].fillna(0.0).values
    r_sol = df_1h['ret_sol'].fillna(0.0).values if 'ret_sol' in df_1h.columns \
            else r_eth * 0.95
    r_bnb = r_eth * 0.70     # BNB tracked via ETH decay factor

    # Cumulative index for ratio instruments
    p_btc = np.cumprod(1.0 + r_btc)
    p_eth = np.cumprod(1.0 + r_eth)
    p_sol = np.cumprod(1.0 + r_sol)

    r_eb  = np.concatenate([[0.0], np.diff(np.log(p_eth / p_btc))])
    r_es  = np.concatenate([[0.0], np.diff(np.log(p_eth / p_sol))])

    # Dominance series (BTC-dom from df; USDT proxy)
    btc_dom  = df_1h.get('btc_dom', pd.Series(0.45, index=df_1h.index)).fillna(0.45).values
    usdt_dom = np.clip(1.0 - btc_dom - 0.18, 0.04, 0.50)
    r_btcdom = np.concatenate([[0.0], np.diff(btc_dom)])
    r_usd_d  = np.concatenate([[0.0], np.diff(usdt_dom)])

    instr_rets = [r_btc, r_eth, r_sol, r_bnb,
                  r_eb, r_usd_d, r_btcdom, r_es]

    # ── broadcast daily funding to 1h ────────────────────────────────────
    dt_idx = pd.to_datetime(df_1h.index).normalize()
    if dt_idx.tz is not None:
        dt_idx = dt_idx.tz_localize(None)

    def _broadcast_funding(fs: pd.Series | None) -> np.ndarray:
        if fs is not None and len(fs) > 0:
            fi = pd.to_datetime(fs.index).normalize()
            if fi.tz is not None:
                fi = fi.tz_localize(None)
            fm = pd.Series(fs.values, index=fi)
            return np.array([float(fm.get(d, 0.0)) for d in dt_idx])
        return np.zeros(T)

    fund_b = _broadcast_funding(fund_btc)
    fund_e = _broadcast_funding(fund_eth)

    # Per-instrument funding (indices 0-7)
    funding_arr = [
        fund_b,                        # BTC perp
        fund_e,                        # ETH perp
        fund_e * 1.10,                 # SOL proxy (higher funding typical)
        fund_e * 0.85,                 # BNB proxy
        fund_e - fund_b,               # ETH/BTC spread funding
        np.zeros(T),                   # USDT dom (no perp)
        np.zeros(T),                   # BTC dom  (no perp)
        fund_e * 1.05,                 # ETH/SOL proxy
    ]

    # ── fill feature matrix ───────────────────────────────────────────────
    W_vol  = 24    # volume normalisation window (1 day)
    W_rv   = 20    # realised vol window
    W_mom  = 72    # trend-sign window (3 days)
    W_4bar =  4    # short-horizon momentum

    for i in range(N_AGENTS):
        ret  = instr_rets[i]
        fund = funding_arr[i]

        # F0: 1-bar log return
        X[:, i, 0] = ret

        # F1: 4-bar rolling log return (4h momentum)
        r4 = pd.Series(ret).rolling(W_4bar, min_periods=1).sum().shift(1).fillna(0.0).values
        X[:, i, 1] = r4

        # F2: volume z-score proxy (|ret| as activity proxy)
        vol_p  = np.abs(ret)
        v_mu   = pd.Series(vol_p).rolling(W_vol, min_periods=4).mean().fillna(0.0).values
        v_std  = pd.Series(vol_p).rolling(W_vol, min_periods=4).std().fillna(1e-9).values + 1e-9
        X[:, i, 2] = np.clip((vol_p - v_mu) / v_std, -5.0, 5.0)

        # F3: realised vol (20-bar rolling std)
        rvol = pd.Series(ret).rolling(W_rv, min_periods=4).std().fillna(0.0).values
        X[:, i, 3] = rvol

        # F4: trend sign (sign of 3d momentum, lag-1 to avoid leakage)
        mom3d = pd.Series(ret).rolling(W_mom, min_periods=BPD).sum().shift(1).fillna(0.0).values
        X[:, i, 4] = np.sign(mom3d)

        # F5: funding rate (daily, broadcast)
        X[:, i, 5] = fund

        # F6: OI-change proxy (|ret| first-difference)
        oi_chg = np.concatenate([[0.0], np.diff(np.abs(ret))])
        X[:, i, 6] = oi_chg

        # F7: ATR-normalised range (|ret| / realised_vol)
        atr = np.maximum(rvol, 1e-9)
        X[:, i, 7] = np.clip(np.abs(ret) / atr, 0.0, 10.0)

    X = np.nan_to_num(X, nan=0.0, posinf=5.0, neginf=-5.0)
    return X


# ═══════════════════════════════════════════════════════════════════════════
#  2.  CALIBRATE INTRADAY PHYSICS ENGINE
# ═══════════════════════════════════════════════════════════════════════════

def calibrate_intraday_engine(X_panel: np.ndarray,
                               calib_mask: np.ndarray) -> tuple:
    """
    Calibrate MasterOperator on the normal-period slice selected by calib_mask.
    Frozen at training time — never re-calibrated on test data.

    Returns:
        M, net, geom, lyap, ews, stoch, e_star, theta
    """
    X_normal = X_panel[calib_mask]
    T0, N, d = X_normal.shape
    print(f"  [v36] Normal window: {T0} bars × {N} agents × {d} features")

    k = min(PCA_K, d)
    M    = MasterOperator.calibrate(X_normal, k=k, theta=1.0)
    net  = LedoitWolfNetwork.from_panel(X_normal[..., 0])
    info = InformationGeometry(op=M)
    e_star = float(info.chi2_threshold(N, d, alpha_conf=ALPHA_CONF))

    geom = CollapseGeometry(op=M)
    lyap = LyapunovCertificate(op=M)
    ews  = EarlyWarning(op=M, geom=geom)
    ews.precursor_scale = PrecursorScale.from_panel(M, X_normal)

    print(f"  [v36] e* (χ², df={N*d}) = {e_star:.3f}")

    # σ_n: std of ||dX - F(X)|| over the calibration window
    residuals = []
    for t in range(1, min(T0, 200)):
        snap = Snapshot(X=X_normal[t], X_prev=X_normal[t-1],
                        history=X_normal[max(0, t-12):t])
        try:
            F_t = M.force(snap)
            dX  = X_normal[t] - X_normal[t-1]
            residuals.append(float(np.linalg.norm(dX - F_t)))
        except Exception:
            pass
    sigma_n = max(float(np.std(residuals)) if residuals else SIGMA_N_FALLBACK, 1e-3)
    print(f"  [v36] σ_n = {sigma_n:.6f}")

    stoch = StochasticExtension(op=M, lyap=lyap, sigma_n=sigma_n)

    # Single pass: compute e_t (for θ) and cos_theta_channel (for ξ₄ z-score) together.
    e_vals    = []
    cos_calib = []
    for t in range(1, T0):
        snap_c = Snapshot(X=X_normal[t], X_prev=X_normal[t-1],
                          history=X_normal[max(0, t-12):t])
        try:
            p = M.pipeline(snap_c, net)
            e_vals.append(float(p['e_t']))
            cos_calib.append(float(geom.cos_theta_channel(snap_c)))
        except Exception:
            pass
    theta = float(np.percentile(e_vals, 90)) if e_vals else 1.0
    theta = max(theta, 1.0)
    print(f"  [v36] θ (90-pctile normal e_t) = {theta:.3f}")

    cos_mu  = float(np.mean(cos_calib)) if cos_calib else 0.0
    cos_sig = max(float(np.std(cos_calib)) if cos_calib else 1.0, 0.01)
    print(f"  [v36] cos_theta_channel calib: μ={cos_mu:.3f}, σ={cos_sig:.3f}")

    # Combined pass 2+3: collect the 5 raw ξ values over the calibration window,
    # compute per-ξ (μ, σ) — xi_calib — then derive RSS_stretch distribution.
    # ξ signals: [γ*, λ_f, W̄_off, z_θ (already z-scored), mfls_f]
    # Only z_θ is already centred; γ*, λ_f, W̄_off, mfls_f each need their own μ/σ.
    raw_xi   = [[], [], [], [], []]  # gamma, lam, wbar, z_theta, mfls
    psi_vals = []
    for t in range(1, T0):
        snap_r = Snapshot(X=X_normal[t], X_prev=X_normal[t-1],
                          history=X_normal[max(0, t-12):t])
        try:
            p      = M.pipeline(snap_r, net)
            gamma  = float(p['gamma_star'])
            lam_f  = max(0.0, min(float(p.get('lambda_bound', 0.5)), 1.0))
            W_bar  = float(p.get('W_bar_off', 0.5))
            cos_ch = float(geom.cos_theta_channel(snap_r))
            z_th   = (cos_ch - cos_mu) / cos_sig
            mfls_v = float(p.get('MFLS_state', 1.0))
            mfls_f = mfls_v / (1.0 + mfls_v)
            raw_xi[0].append(gamma)
            raw_xi[1].append(lam_f)
            raw_xi[2].append(W_bar)
            raw_xi[3].append(z_th)
            raw_xi[4].append(mfls_f)
            psi_vals.append(float(p.get('psi', 0.0)))
        except Exception:
            pass

    # Per-ξ calibration: (μ, raw_σ).  σ is NOT floored here so that the
    # MIN_XI_SIG check below can correctly identify constant signals.
    xi_calib = []
    for vals in raw_xi:
        arr = np.array(vals) if vals else np.array([0.0])
        xi_calib.append((float(np.mean(arr)), float(np.std(arr))))
    print("  [v36] ξ calib: " + "  ".join(
        f"ξ{i+1}(μ={mu:.3f},σ={sig:.3f})" for i, (mu, sig) in enumerate(xi_calib)))

    # Compute RSS_stretch distribution — skip constant-in-calibration signals.
    def _sig(x: float) -> float:
        return 1.0 / (1.0 + np.exp(-x))

    def _rss_stretch(xis_raw, psi):
        """Geometric mean of sigmoid-stretched z-scores for active ξ signals."""
        stretched = []
        for xi_v, (xi_mu, xi_sig) in zip(xis_raw, xi_calib):
            if xi_sig < MIN_XI_SIG:
                continue   # constant in calibration → skip (no discriminative info)
            z_i = (xi_v - xi_mu) / xi_sig
            stretched.append(_sig(STRETCH_GAMMA * z_i))
        if not stretched:
            return 0.5
        inner = 1.0
        for s in stretched:
            inner *= s
        return inner ** (1.0 / len(stretched))  # K-th root (K = active signal count)

    rss_calib = []
    for i in range(len(psi_vals)):
        try:
            xis_raw = [raw_xi[k][i] for k in range(5)]
            rss_raw = _rss_stretch(xis_raw, psi_vals[i])
            cos2psi = np.cos(psi_vals[i]) ** 2
            rss_calib.append(float(np.clip(rss_raw * cos2psi, 0.0, 1.0)))
        except Exception:
            pass
    rss_mu  = float(np.mean(rss_calib)) if rss_calib else 0.5
    rss_sig = max(float(np.std(rss_calib)) if rss_calib else 0.1, 1e-4)
    print(f"  [v36] RSS_stretch calib: μ={rss_mu:.3f}, σ={rss_sig:.3f}")

    return M, net, geom, lyap, ews, stoch, e_star, theta, cos_mu, cos_sig, rss_mu, rss_sig, xi_calib


# ═══════════════════════════════════════════════════════════════════════════
#  3.  INTRADAY SIGNAL SWEEP
# ═══════════════════════════════════════════════════════════════════════════

def compute_intraday_signals(X_panel: np.ndarray,
                              df_1h:   pd.DataFrame,
                              M,  net,  ews,  stoch,
                              e_star:  float,
                              theta:   float,
                              history_len: int = 48,
                              cos_mu: float = 0.0,
                              cos_sig: float = 1.0,
                              rss_mu: float = 0.0,
                              rss_sig: float = 1.0,
                              xi_calib: list | None = None) -> pd.DataFrame:
    """
    Sweep every 1h bar and compute all 7 BSDT signals via M.pipeline().

    The pipeline dict keys used:
        e_t, gamma_star, psi, cos_theta_state,
        W_bar_off, MFLS_state, lambda_bound, F_t

    Additional per-channel scores from M.bsdt.delta_X(snap).
    Controllability R_t via jacobians + channel_state.
    """
    T    = len(X_panel)
    bsdt = M.bsdt

    # output buffers
    buf = {k: np.full(T, np.nan) for k in [
        'e_t', 'gamma_star', 'cos_theta', 'z_theta', 'psi_t', 'R_t',
        'P_t', 'G_norm', 'RSS_t', 'tau_lin', 'dom_ch',
        'delta_C', 'delta_G', 'delta_A', 'delta_T',
        'kramers_p',
    ]}

    # Lyapunov certificate for exact ė_t = P_t − γ* Q_t/||g||\u00b2 (§XVI)
    _lyap = LyapunovCertificate(op=M)

    t0 = time.time()
    for t in range(2, T):
        snap = Snapshot(
            X       = X_panel[t],
            X_prev  = X_panel[t-1],
            history = X_panel[max(0, t - history_len):t],
        )
        try:
            # ── pipeline output (bulk of signals) ─────────────────────────
            p = M.pipeline(snap, net)

            e_t       = float(p['e_t'])
            gamma_star= float(p['gamma_star'])
            psi_t     = float(p['psi'])         # false-alarm angle (rad)
            cos_theta = float(ews.geom.cos_theta_channel(snap))  # 4D channel space, not 64D state
            W_bar_off = float(p.get('W_bar_off', 0.5))
            mfls_val  = float(p.get('MFLS_state', 1.0))
            lam_bound = float(p.get('lambda_bound', 0.5))

            buf['e_t'][t]        = e_t
            buf['gamma_star'][t] = gamma_star
            buf['psi_t'][t]      = psi_t
            buf['cos_theta'][t]  = cos_theta
            buf['z_theta'][t]    = (cos_theta - cos_mu) / cos_sig

            # ── BSDT channel scores δ_C, δ_G, δ_A, δ_T ───────────────────
            dc = float(np.mean(bsdt.delta_C(snap)))
            dg = float(np.mean(bsdt.delta_G(snap)))
            da = float(np.mean(bsdt.delta_A(snap)))
            dt = float(np.mean(bsdt.delta_T(snap)))
            buf['delta_C'][t] = dc
            buf['delta_G'][t] = dg
            buf['delta_A'][t] = da
            buf['delta_T'][t] = dt
            buf['dom_ch'][t]  = float(np.argmax([dc, dg, da, dt]))

            # ── G̃_t — physical collapse direction ──────────────────────
            try:
                G_tilde = M.collapse_direction_state(snap)    # (N, d)
                G_norm  = float(np.linalg.norm(G_tilde, 'fro'))
            except Exception:
                G_norm = float(np.sqrt(max(dg, 0.0)))
            buf['G_norm'][t] = G_norm

            # ── P_t = pullback power G̃_t · F_t ──────────────────────────
            try:
                F_mat = np.array(p.get('F_t', M.force(snap)))
                G_mat = G_tilde
                P_t   = float(np.sum(G_mat * F_mat))
                F_norm= float(np.linalg.norm(F_mat, 'fro'))
            except Exception:
                P_t   = 0.0
                F_norm= 1.0
            buf['P_t'][t] = P_t

            # ── R_t — controllability margin ──────────────────────────────
            # R_t = g_t · (J g_t)  where g_t = channel_state (4-dim),
            # J = jacobians_stacked (4×N×d) and · means scalar triple product
            try:
                ch_state = bsdt.channel_state(snap)         # (4,)
                jacs     = bsdt.jacobians(snap)             # dict {C,G,A,T} each (N,d)
                R_t = 0.0
                for ki, key in enumerate(['C', 'G', 'A', 'T']):
                    if ki >= len(ch_state):
                        break
                    J_k = jacs.get(key)
                    if J_k is None:
                        continue
                    # ⟨J_k, g_t ⊗ 1_{Nxd}⟩_F — broadcast g_k along feature axis
                    g_k = float(ch_state[ki])
                    R_t += g_k * float(np.sum(J_k * g_k))
                buf['R_t'][t] = R_t
            except Exception:
                buf['R_t'][t] = float(P_t)   # conservative fallback

            # ── RSS_t — regime state score (per-ξ tanh-stretch) ─────────
            # ξ signals: [γ*, λ_f, W̄_off, z_θ, mfls_f].  ξ₂ clamped to [0,1]
            # because λ_bound can be negative (Gershgorin bound only upper).
            mfls_f = mfls_val / (1.0 + mfls_val)
            lam_f  = max(0.0, min(lam_bound, 1.0))                    # ξ₂ fix
            z_th   = buf['z_theta'][t]                                 # already stored

            # ── RSS_t — per-ξ tanh-stretch (UDL SubspaceScanScorer pattern) ──
            # sigmoid(STRETCH_GAMMA · z_i) ∈ [0,1] with z=0→0.50, z=+2→0.998.
            # Only signals with calibration σ ≥ MIN_XI_SIG participate; constant
            # calibration signals (σ≈0) are skipped — no discriminative power.
            if xi_calib is not None:
                xis_raw  = [gamma_star, lam_f, W_bar_off, z_th, mfls_f]
                stretched = []
                for xi_v, (xi_mu, xi_sig) in zip(xis_raw, xi_calib):
                    if xi_sig < MIN_XI_SIG:
                        continue
                    z_i = (xi_v - xi_mu) / xi_sig
                    stretched.append(1.0 / (1.0 + np.exp(-STRETCH_GAMMA * z_i)))
                if stretched:
                    inner = 1.0
                    for s in stretched:
                        inner *= s
                    rss_raw = inner ** (1.0 / len(stretched))
                else:
                    rss_raw = 0.5
            else:
                # Legacy path: simple sigmoid on z_theta only
                xi4     = float(1.0 / (1.0 + np.exp(-z_th)))
                inner   = gamma_star * lam_f * W_bar_off * xi4 * mfls_f
                rss_raw = inner ** (1.0 / 5.0) if inner > 0.0 else 0.0
            cos2psi = np.cos(psi_t) ** 2
            buf['RSS_t'][t] = float(np.clip(rss_raw * cos2psi, 0.0, 1.0))

            # ── τ_lin — bars to critical manifold ─────────────────────────
            # τ = (e* - e_t) / ė_t   where ė_t = dV/dt = P_t − γ* Q_t/||g||²  (§XVI)
            # Use the exact Lyapunov formula instead of the simplified P_t(1−γ*) approximation.
            e_dot = _lyap.dV_dt(snap)
            if e_dot > 1e-8:
                buf['tau_lin'][t] = float(np.clip((e_star - e_t) / e_dot, 0.0, 9999.9))
            else:
                buf['tau_lin'][t] = 9999.0

            # ── Kramers escape probability ─────────────────────────────────
            try:
                buf['kramers_p'][t] = float(
                    stoch.cross_probability(snap, e_star=e_star,
                                            tau=KRAMERS_TAU_1H, dt=1e-2))
            except Exception:
                pass

        except Exception:
            pass   # NaN remains — forward-filled below

        if t > 2 and (t % 5000) == 0:
            print(f"    {t:>6}/{T}  ({time.time()-t0:>5.1f}s)")

    print(f"  [v36] Signal sweep complete: {T:,} bars  {time.time()-t0:.1f}s")

    # ── forward-fill holes + derive decision signals ──────────────────────
    def _ff(arr, fill=0.0):
        return pd.Series(arr).fillna(method='ffill').fillna(fill).values

    e_t_s   = _ff(buf['e_t'],        0.0)
    gam_s   = _ff(buf['gamma_star'], 0.0)   # pipeline theta=1 (diagnostic only)
    cos_s   = _ff(buf['cos_theta'],  0.0)
    z_th_s  = _ff(buf['z_theta'],    0.0)
    psi_s   = _ff(buf['psi_t'],      0.0)
    R_s     = _ff(buf['R_t'],        1.0)   # fallback = controllable
    RSS_s   = _ff(buf['RSS_t'],      0.0)
    tau_s   = _ff(buf['tau_lin'],  9999.0)
    dom_s   = _ff(buf['dom_ch'],     0.0)

    # ── γ*_adj using calibrated θ (90th-pctile of normal e_t) ────────────
    # The pipeline uses theta=1.0 internally (always saturated at 0.97+).
    # Re-compute using the θ we calibrated from the normal-period energy dist.
    gam_adj = e_t_s / (e_t_s + theta)   # θ≈121 gives sensible [0,1] range

    # Size multiplier = 1 − γ*_adj (gives 0–50% reduction depending on energy)
    size_mult = np.clip(1.0 - gam_adj, 0.0, 1.0)

    # ── Method A: fixed z-score — (RSS_t − μ_cal) / σ_cal ───────────────────
    # Reference is frozen at calibration baseline (AC-coupling analogue).
    z_rss_fixed = (RSS_s - rss_mu) / max(rss_sig, 1e-8)

    # ── Method B: AGC adaptive reference — asymmetric EMA ────────────────
    # Initialized from calibration mean; slow attack / fast decay:
    #   Attack (90d half-life): RSS rises → reference barely follows → z spikes
    #   Decay  ( 7d half-life): RSS falls → reference drops quickly → z normalises
    alpha_att = 2.0 / (AGC_SPAN_ATTACK + 1)   # ≈ 0.00093
    alpha_dec = 2.0 / (AGC_SPAN_DECAY  + 1)   # ≈ 0.01183
    agc_ref = np.empty(len(RSS_s))
    agc_ref[0] = rss_mu
    for i in range(1, len(RSS_s)):
        if RSS_s[i] > agc_ref[i - 1]:         # rising → slow attack
            agc_ref[i] = (1.0 - alpha_att) * agc_ref[i - 1] + alpha_att * RSS_s[i]
        else:                                  # falling → fast decay
            agc_ref[i] = (1.0 - alpha_dec) * agc_ref[i - 1] + alpha_dec * RSS_s[i]
    z_rss_agc = (RSS_s - agc_ref) / max(rss_sig, 1e-8)

    # Use fixed as the primary z_rss (backward-compatible); AGC exposed separately
    z_rss_s = z_rss_fixed

    # RSS-based regime sizing — both methods
    def _rss_zones(z):
        return np.where(z >= Z_RSS_PRECOLLAPSE, 0.0,
               np.where(z >= Z_RSS_ELEVATED,    size_mult * 0.5,
               np.where(z >= Z_RSS_NORMAL,       size_mult,
                                                  1.0)))

    rss_size     = _rss_zones(z_rss_fixed)   # Method A: fixed baseline
    rss_size_agc = _rss_zones(z_rss_agc)     # Method B: AGC adaptive

    # Entry gate (relaxed): R_t>0, ψ<π/4, dominant channel ≠ G
    # NOTE: cos_θ<0 filter removed — in 64-dim state cos is ≈0 always;
    #       RSS regime is the primary directional filter instead.
    entry_ok = ((R_s > 0.0) &
                (psi_s < np.pi / 4.0) &
                (dom_s.astype(int) != 1)).astype(float)

    # Exit trigger: z_RSS ≥ 2.5σ above reference OR R<0 OR τ<5
    exit_now     = ((z_rss_fixed >= Z_RSS_PRECOLLAPSE) |
                    (R_s < 0.0) |
                    (tau_s < TAU_TIGHT)).astype(float)
    exit_now_agc = ((z_rss_agc   >= Z_RSS_PRECOLLAPSE) |
                    (R_s < 0.0) |
                    (tau_s < TAU_TIGHT)).astype(float)

    idx = df_1h.index
    return pd.DataFrame({
        'e_t':           e_t_s,
        'gamma_star':    gam_s,       # pipeline raw (theta=1 internal)
        'gamma_star_adj':gam_adj,     # calibrated theta (θ=90th pctile)
        'cos_theta':     cos_s,
        'z_theta':       z_th_s,
        'psi_t':         psi_s,
        'R_t':           R_s,
        'P_t':           _ff(buf['P_t'],       0.0),
        'G_norm':        _ff(buf['G_norm'],    0.0),
        'RSS_t':         RSS_s,
        'z_rss':         z_rss_fixed,
        'z_rss_agc':     z_rss_agc,
        'tau_lin':       tau_s,
        'dom_ch':        dom_s,
        'delta_C':       _ff(buf['delta_C'],   0.0),
        'delta_G':       _ff(buf['delta_G'],   0.0),
        'delta_A':       _ff(buf['delta_A'],   0.0),
        'delta_T':       _ff(buf['delta_T'],   0.0),
        'kramers_p':     _ff(buf['kramers_p'], 0.5),
        'size_mult':     size_mult,       # 1 − γ*_adj
        'rss_size':      rss_size,         # fixed z-score sizing
        'rss_size_agc':  rss_size_agc,     # AGC adaptive sizing
        'entry_ok':      entry_ok,
        'exit_now':      exit_now,
        'exit_now_agc':  exit_now_agc,
    }, index=idx)


# ═══════════════════════════════════════════════════════════════════════════
#  4.  BSDT DECISION TREE → POSITION SIZING
# ═══════════════════════════════════════════════════════════════════════════

def apply_bsdt_decision_tree(base_pnl: pd.Series,
                              sig:      pd.DataFrame,
                              ret_eth:  pd.Series) -> dict[str, pd.Series]:
    """
    Variants applying the BSDT engine to the v34 base portfolio.
    Two RSS methods compared side-by-side:
      _fixed : z-score vs frozen calibration mean (AC-coupling)
      _agc   : z-score vs asymmetric-EMA adaptive reference (AGC/compressor)

    v34_baseline    : unchanged v34 combined PnL
    BSDT_scaled     : base × (1−γ*_adj)  — energy damping only
    BSDT_rss_fixed  : base × rss_size_fixed   — fixed z-score thresholds
    BSDT_rss_agc    : base × rss_size_agc     — AGC adaptive thresholds
    BSDT_filtered   : base × entry/exit gate (stateful, R_t/ψ_t/dom_ch)
    BSDT_combined   : BSDT_rss_fixed × entry/exit gate
    BSDT_comb_agc   : BSDT_rss_agc   × entry/exit gate
    BSDT_tau_guard  : BSDT_rss_fixed + τ_lin early-exit
    """
    base = base_pnl.fillna(0.0)
    s    = sig.reindex(base.index, method='ffill').fillna(0.0)
    r    = ret_eth.reindex(base.index, fill_value=0.0)

    # Lag signals by 1 bar (no lookahead)
    sm    = s['size_mult'].shift(1).fillna(1.0)
    rs    = s['rss_size'].shift(1).fillna(1.0)
    rs_agc= s['rss_size_agc'].shift(1).fillna(1.0)
    eo    = s['entry_ok'].shift(1).fillna(0.0)
    en    = s['exit_now'].shift(1).fillna(0.0)
    en_agc= s['exit_now_agc'].shift(1).fillna(0.0)
    Rt    = s['R_t'].shift(1).fillna(1.0)
    tau   = s['tau_lin'].shift(1).fillna(9999.0)
    RSS   = s['RSS_t'].shift(1).fillna(0.0)

    # ── 1. Baseline ────────────────────────────────────────────────────────
    pnl_base = base

    # ── 2. Scaled  ─────────────────────────────────────────────────────────
    # Use calibrated γ*_adj: full exposure in Normal regime, reduces when
    # e_t exceeds θ. size_mult = 121/(e_t+121) ≈ 0.64 at mean energy.
    pnl_scaled = base * sm

    # ── 3. RSS fixed z-score ───────────────────────────────────────────────
    # Zones vs frozen calibration mean (AC-coupling):
    # z<0.5 → pass-through, z 0.5-1.5 → damp, z 1.5-2.5 → halve, z≥2.5 → flat
    pnl_rss = base * rs

    # ── 4. RSS AGC adaptive ────────────────────────────────────────────────
    # Same zones but reference is asymmetric EMA (slow attack / fast decay)
    pnl_rss_agc = base * rs_agc

    # ── 5. Filtered  ───────────────────────────────────────────────────────
    # Stateful: enter when entry_ok=1, exit when exit_now=1 (fixed z-score gate)
    active = pd.Series(0.0, index=base.index)
    in_pos = False
    for t in range(len(base)):
        if not in_pos and eo.iloc[t] > 0:
            in_pos = True
        if in_pos and en.iloc[t] > 0:
            in_pos = False
        active.iloc[t] = 1.0 if in_pos else 0.0

    # AGC-gated stateful filter
    active_agc = pd.Series(0.0, index=base.index)
    in_pos_agc = False
    for t in range(len(base)):
        if not in_pos_agc and eo.iloc[t] > 0:
            in_pos_agc = True
        if in_pos_agc and en_agc.iloc[t] > 0:
            in_pos_agc = False
        active_agc.iloc[t] = 1.0 if in_pos_agc else 0.0

    pnl_filtered = base * active

    # ── 6. Combined ────────────────────────────────────────────────────────
    pnl_combined     = base * rs     * active
    pnl_combined_agc = base * rs_agc * active_agc

    # ── 7. τ_lin guard (fixed z-score base) ───────────────────────────────
    tau_factor = np.clip(tau / (tau + TAU_NORMAL), 0.0, 1.0)
    pnl_tau = pnl_rss * tau_factor

    return {
        'v34_baseline':   pnl_base,
        'BSDT_scaled':    pnl_scaled,
        'BSDT_rss_fixed': pnl_rss,
        'BSDT_rss_agc':   pnl_rss_agc,
        'BSDT_filtered':  pnl_filtered,
        'BSDT_combined':  pnl_combined,
        'BSDT_comb_agc':  pnl_combined_agc,
        'BSDT_tau_guard': pnl_tau,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  5.  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _net_ret(pnl: pd.Series, K: float,
             bpd: int = BPD, tc_bps: float = 5.0) -> pd.Series:
    """Apply K× leverage and deduct transaction costs."""
    p  = pnl.fillna(0.0)
    fee= tc_bps / 1e4 / bpd * (p.abs() > 1e-12).astype(float)
    return p * K - fee


def _stats(pnl: pd.Series) -> dict:
    p = pnl.fillna(0.0)
    if p.std() < 1e-12:
        return {'sharpe': 0.0, 'cagr': 0.0, 'max_dd': 0.0, 'final': 100.0}
    sh   = float(p.mean() / p.std() * np.sqrt(ANN_1H))
    eq   = 100.0 * (1.0 + p).cumprod()
    mdd  = float((eq / eq.cummax() - 1.0).min())
    yrs  = max((p.index[-1] - p.index[0]).days / 365.25, 0.01)
    cagr = float((eq.iloc[-1] / 100.0) ** (1.0 / yrs) - 1.0)
    return {'sharpe': sh, 'cagr': cagr, 'max_dd': mdd, 'final': float(eq.iloc[-1])}


def print_yoy_table(title: str, pnl: pd.Series, K_list: list):
    print(f"\n  {title}")
    hdr = f"  {'K':>3}  {'2023':>7}  {'2024':>7}  {'2025':>7}  {'2026YTD':>8}  "
    hdr += f"{'$100→':>9}  {'MaxDD':>7}  {'CAGR':>10}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for K in K_list:
        r   = _net_ret(pnl, K)
        eq  = 100.0
        yr  = {}
        for y in [2023, 2024, 2025, 2026]:
            mk = pnl.index.year == y
            if not mk.any():
                continue
            ret = float((1.0 + r[mk]).prod() - 1.0)
            yr[y] = ret
            eq  *= (1.0 + ret)
        ec   = 100.0 * (1.0 + r).cumprod()
        mdd  = float((ec / ec.cummax() - 1.0).min())
        yrs  = max((r[r.index.year >= 2023].index[-1]
                    - r[r.index.year >= 2023].index[0]).days / 365.25, 0.01)
        cagr = (eq / 100.0) ** (1.0 / yrs) - 1.0
        f = lambda y: f"{100*yr[y]:>+5.0f}%" if y in yr else "  ─  "
        print(f"  {K:>3}  {f(2023):>7}  {f(2024):>7}  {f(2025):>7}  {f(2026):>8}  "
              f"${eq:>8.2f}  {100*mdd:>+6.1f}%  {100*cagr:>+6.1f}%/yr")


def print_signal_report(sig: pd.DataFrame, mask: pd.Series):
    s = sig[mask]
    print(f"\n  [Signal report]  test bars={len(s):,}",
          f"  ({s.index[0].date()} → {s.index[-1].date()})")
    print(f"  {'Signal':<16}  {'mean':>9}  {'std':>9}  {'p5':>9}  {'p95':>9}")
    for col in ['e_t', 'gamma_star', 'gamma_star_adj', 'cos_theta', 'z_theta', 'psi_t', 'R_t',
                'RSS_t', 'z_rss', 'z_rss_agc', 'tau_lin', 'size_mult', 'rss_size', 'rss_size_agc']:
        if col not in s.columns:
            continue
        v = s[col].dropna()
        print(f"  {col:<16}  {v.mean():>+9.3f}  {v.std():>9.3f}  "
              f"{v.quantile(0.05):>+9.3f}  {v.quantile(0.95):>+9.3f}")
    rss = s['RSS_t'].fillna(0.0)
    zr_f = s['z_rss'].fillna(0.0)     if 'z_rss'     in s.columns else pd.Series(0.0, index=s.index)
    zr_a = s['z_rss_agc'].fillna(0.0) if 'z_rss_agc' in s.columns else zr_f
    print(f"\n  RSS regime breakdown (fixed z-score vs AGC):")
    print(f"  {'Zone':<26}  {'Fixed':>8}  {'AGC':>8}")
    for label, lo, hi in [
        (f'Normal (z<{Z_RSS_NORMAL})',          -np.inf, Z_RSS_NORMAL),
        (f'Elevated ({Z_RSS_NORMAL}–{Z_RSS_ELEVATED})', Z_RSS_NORMAL, Z_RSS_ELEVATED),
        (f'Pre-coll ({Z_RSS_ELEVATED}–{Z_RSS_PRECOLLAPSE})', Z_RSS_ELEVATED, Z_RSS_PRECOLLAPSE),
        (f'Critical (z≥{Z_RSS_PRECOLLAPSE})',   Z_RSS_PRECOLLAPSE, np.inf),
    ]:
        pf = 100 * ((zr_f >= lo) & (zr_f < hi)).mean()
        pa = 100 * ((zr_a >= lo) & (zr_a < hi)).mean()
        print(f"  {label:<26}  {pf:>7.1f}%  {pa:>7.1f}%")
    print(f"    Entry OK:  {100*s['entry_ok'].mean():.1f}% of bars")
    print(f"    Exit now:  {100*s['exit_now'].mean():.1f}% of bars")
    dom = s['dom_ch'].round().astype(int).value_counts(normalize=True) * 100
    names = {0:'C(Mahalano)', 1:'G(PCA-gap)', 2:'A(velocity)', 3:'T(temporal)'}
    print(f"    Dominant channel:")
    for ki, pct in dom.sort_index().items():
        print(f"      {names.get(ki, ki)}: {pct:.1f}%")


# ═══════════════════════════════════════════════════════════════════════════
#  6.  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print("=" * 100)
    print("  CRYPTO BSDT v36 — FULL INTRADAY PHYSICS ENGINE")
    print("  8 instruments × 8 features  |  7 BSDT signals  |  Decision tree")
    print("=" * 100)

    # ─────────────────────────────────────────────────── 1h DATA ──
    print("\n[1] Fetching Binance 1h data (ETH, BTC, SOL) ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"  Total: {len(df_1h):,} bars  |  Train: {train_1h.sum():,}  |  Test: {test_1h.sum():,}")

    # ──────────────────────────────────────────── FUNDING DATA ──
    print("\n[2] Fetching daily funding rates ...")
    try:
        funding = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
        if isinstance(funding, dict):
            fund_eth = funding.get('ETHUSDT')
            fund_btc = funding.get('BTCUSDT')
        else:
            fund_eth = fund_btc = None
    except Exception:
        fund_eth = fund_btc = None
        print("  WARNING: funding data unavailable — using zero funding")

    # ──────────────────────────────────────── 8×8 STATE MATRIX ──
    print("\n[3] Building 8×8 intraday state matrix (T, 8, 8) ...")
    X_panel = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    print(f"  Shape: {X_panel.shape}")
    bad = int(np.sum(~np.isfinite(X_panel)))
    if bad:
        print(f"  WARNING: {bad} non-finite values — replaced with 0")
        X_panel = np.nan_to_num(X_panel)

    # ─────────────────────────────────── CALIBRATE ENGINE ──
    # Use the last CALIB_BARS of training data as the "normal period"
    train_idx  = np.where(train_1h)[0]
    calib_idx  = train_idx[-CALIB_BARS:]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[calib_idx] = True
    print(f"\n[4] Calibrating intraday physics engine on {CALIB_BARS} normal-period bars ...")
    print(f"  Window: {df_1h.index[calib_idx[0]].date()} → "
          f"{df_1h.index[calib_idx[-1]].date()}")

    M, net, geom, lyap, ews, stoch, e_star, theta, cos_mu, cos_sig, rss_mu, rss_sig, xi_calib = \
        calibrate_intraday_engine(X_panel, calib_mask)

    # ────────────────────────────────────────── SIGNAL SWEEP ──
    print(f"\n[5] Computing 7 BSDT signals over {len(df_1h):,} bars ...")
    sig = compute_intraday_signals(X_panel, df_1h, M, net, ews, stoch,
                                   e_star, theta, history_len=48,
                                   cos_mu=cos_mu, cos_sig=cos_sig,
                                   rss_mu=rss_mu, rss_sig=rss_sig,
                                   xi_calib=xi_calib)

    print_signal_report(sig, test_1h)

    # ────────────────────────────────────── V34 BASE PORTFOLIO ──
    print("\n[6] Building v34 base portfolio (daily D-series + 1h H-series) ...")

    h_strats = compute_1h_strategies(df_1h, has_sol)

    df_d = fetch_and_prepare()
    df_d = add_cross_market_features(df_d)
    fund_d = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
    df_d = add_leverage_features(df_d, fund_d)

    train_mask_d   = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
    train_mask_arr = np.asarray(train_mask_d, dtype=bool)

    pos_dict, spread_ret, F_daily, gate_daily = build_daily_positions(
        df_d, train_mask_d, train_mask_arr)

    instr_map = {
        'D1_trend_eth': df_1h['ret_eth'],
        'D2_pairs_eb':  df_1h['spread_ret_eb'],
        'D3_pairs_es':  df_1h['ret_eth'] - df_1h.get('ret_sol', df_1h['ret_eth']),
        'D4_macro_btc': df_1h['ret_btc'],
        'D5_macro_alt': df_1h['ret_eth'],
    }
    d_strats_1h = {
        name: upsample_daily_to_1h_pnl(pos, instr_map.get(name, df_1h['ret_eth']), gate_daily)
        for name, pos in pos_dict.items()
    }
    all_pnls  = {**d_strats_1h, **h_strats}
    Q_v34     = compute_quality(all_pnls, bpd=BPD)
    pnl_v34_full = assemble_combined(all_pnls, Q_v34)

    s_v34 = _stats(pnl_v34_full[test_1h])
    print(f"  v34 gross Sharpe: {s_v34['sharpe']:+.3f}  "
          f"MaxDD: {100*s_v34['max_dd']:+.1f}%  CAGR: {100*s_v34['cagr']:+.1f}%")

    # ─────────────────────────────────── APPLY DECISION TREE ──
    print("\n[7] Applying BSDT decision tree ...")
    strategies = apply_bsdt_decision_tree(
        pnl_v34_full, sig, df_1h['ret_eth'])

    # Restrict to test window
    for k in list(strategies.keys()):
        strategies[k] = strategies[k][test_1h]

    # Print gross comparison
    print(f"\n  Gross snapshot (test 2023→2026):")
    print(f"  {'Strategy':<22}  {'Sharpe':>8}  {'MaxDD':>8}  {'CAGR':>9}  "
          f"{'Entry%':>7}  {'Active d':>8}")
    for name, pnl in strategies.items():
        st  = _stats(pnl)
        er  = float((pnl.abs() > 1e-12).mean()) * 100
        act = float((pnl.abs() > 1e-12).sum()) / BPD
        print(f"  {name:<22}  {st['sharpe']:>+8.3f}  {100*st['max_dd']:>+7.1f}%  "
              f"{100*st['cagr']:>+8.1f}%  {er:>6.1f}%  {act:>7.0f}d")

    # ──────────────────────────────────────── YEAR-ON-YEAR ──
    print(f"\n\n{'═'*100}")
    print("  YEAR-ON-YEAR  ($100 start, compounding, gross)")
    print(f"{'═'*100}")
    K_LIST = [1, 2, 5, 10, 14]
    for name, pnl in strategies.items():
        print_yoy_table(name, pnl, K_LIST)

    # ────────────────────────────────────────────── SAVE ──
    out = {
        'meta': {
            'version':    'v36',
            'state_dim':  f'{N_AGENTS}x{N_FEATURES}',
            'e_star':     float(e_star),
            'theta':      float(theta),
            'calib_bars': CALIB_BARS,
        },
        'v34_gross': s_v34,
        'strategies': {},
    }
    for name, pnl in strategies.items():
        r2 = _net_ret(pnl, 2)
        eq = 100.0; yr = {}
        for y in [2023, 2024, 2025, 2026]:
            msk = pnl.index.year == y
            if not msk.any(): continue
            ret = float((1.0 + r2[msk]).prod() - 1.0)
            yr[str(y)] = ret; eq *= (1.0 + ret)
        st = _stats(pnl)
        out['strategies'][name] = {
            'yr_returns_K2': yr,
            'final_K2':      float(eq),
            'sharpe_gross':  st['sharpe'],
            'max_dd':        st['max_dd'],
        }
    sig_test = sig[test_1h]
    out['signal_summary'] = {
        'RSS_mean':       float(sig_test['RSS_t'].mean()),
        'gamma_star_mean':float(sig_test['gamma_star'].mean()),
        'cos_theta_mean': float(sig_test['cos_theta'].mean()),
        'psi_mean':       float(sig_test['psi_t'].mean()),
        'R_t_pos_pct':    float((sig_test['R_t'] > 0).mean()),
        'entry_ok_pct':   float(sig_test['entry_ok'].mean()),
        'exit_now_pct':   float(sig_test['exit_now'].mean()),
    }

    out_path = OUT_DIR_ / 'crypto_bsdt_v36_intraday_bsdt.json'
    with open(out_path, 'w') as fh:
        json.dump(out, fh, indent=2, default=float)
    print(f"\n  Saved → {out_path}")
    print("=" * 100)


if __name__ == '__main__':
    main()
