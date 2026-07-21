"""
Crypto BSDT v39 — Four-Channel Operator
=========================================
Implements the full four-channel BSDT operator for the first time.

THEORY (§XII of the paper)
──────────────────────────
The BSDT operator has four channels measuring distinct anomaly types:

  δ_C^{(i)} = x̃ᵢᵀ Σ₀⁻¹ x̃ᵢ            Mahalanobis distance   (familiar stress)
  δ_G^{(i)} = ‖x̃ᵢ‖² − ‖Vkᵀx̃ᵢ‖²      Feature gap            (novel stress, PCA residual)
  δ_A^{(i)} = max(0, ‖xᵢ−xᵢ₋₁‖ − v₀)  Activity anomaly       (cascade velocity)
  δ_T^{(i)} = max(0, −log p̂_h(xᵢ))    Temporal novelty      (regime transition)

Channel-state vector:  S_t = [δ_C, δ_G, δ_A, δ_T] ∈ R⁴  (summed over N agents)
Energy gradient:        g_t = ∇_S E(S_t) = 2A·S_t + ...   (from UnifiedEnergy)
Channel attribution:    a_k = [g_t]_k² / ‖g_t‖²           (dominant driver)

FEATURE-SPACE GRADIENT (for R_t and ψ_t)
──────────────────────────────────────────
Each channel k has a jacobian J_k ∈ R^{N×d} (per-agent feature gradient).
The composite collapse direction in feature space:

  G_t = Σ_k a_k × J_k   ∈ R^{N×d}   (attribution-weighted jacobian sum)

R_t = ‖G_t‖_F²  — controllability proxy
  (with only δ_C: always positive; with 4 channels: can detect opposing gradients)

ψ_t: angle between G_t and J_C (the primary channel gradient)
  cos(ψ_t) = ⟨G_t, J_C⟩_F / (‖G_t‖_F ‖J_C‖_F)

CHANNEL FIRING SEQUENCE
──────────────────────────
Theoretical order in a collapse:
  δ_T fires first  → regime transition
  δ_G fires second → novel structural stress  
  δ_A fires third  → cascade velocity
  δ_C fires fourth → familiar stress fully systemic
  λ_price rises last → stress transmits to returns

We measure the sequence empirically by detecting each channel's threshold crossing
and computing the inter-channel lead times Δτ.

KEY NEW SIGNALS
───────────────
  a_C, a_G, a_A, a_T   : per-channel attribution (sum to 1)
  dom_ch_energy         : dominant channel by energy attribution (0=C,1=G,2=A,3=T)
  psi_4ch               : misalignment angle of composite vs primary gradient (true ψ)
  R_t_4ch               : four-channel controllability (can go negative via cross-terms)
  G_norm_4ch            : ‖G_t‖_F feature-space gradient magnitude
  e_G, e_A, e_T         : per-channel total energies (for firing sequence detection)
  fire_C, fire_G, fire_A, fire_T : threshold-crossing flags (for Δτ measurement)
  dt_CG, dt_CA, dt_CT   : cross-channel lead times (G→C, A→C, T→C delays in bars)
  firing_seq            : detected firing order (string label for logging)

STRATEGY VARIANTS (ALL USE v38_sym_W100 AS BASE)
─────────────────────────────────────────────────
  v38_sym       : (1−γ*) × (0.75 + 0.5·λ_pct_100)   [v38 champion, baseline]
  v39_aG_gate   : v38_sym × 𝟙[a_G < 0.20]           [exit when novel stress dominates]
  v39_aA_gate   : v38_sym × 𝟙[a_A < 0.15]           [exit during cascade velocity]
  v39_aT_entry  : v38_sym × (0.75+0.25·𝟙[a_T > 0.20])  [boost at regime transitions]
  v39_psi_gate  : v38_sym × cos(ψ_t)                [scale by gradient alignment]
  v39_seq_entry : v38_sym + sequence-aware entry     [boost when δ_T just fired → lead time]
  v39_full_4ch  : combined — aG+aA gates + aT boost  [PRIMARY]

Usage:
    py -3 run_crypto_pairs_v39_four_channels.py
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

from collapse_geometry import MasterOperator, Snapshot, LedoitWolfNetwork, InformationGeometry
from run_crypto_pairs_v38_lambda_norm import (
    compute_lambda_features, apply_v38_sizing,
)
from run_crypto_pairs_v37_price_prediction import (
    compute_price_prediction_signals,
)
from run_crypto_pairs_v36_intraday_bsdt import (
    N_AGENTS, N_FEATURES, CALIB_BARS, ALPHA_CONF, PCA_K,
    BPD, ANN_1H,
    build_intraday_state_panel, calibrate_intraday_engine,
    compute_intraday_signals,
    print_yoy_table, _net_ret, _stats,
)
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
    build_1h_df, fetch_and_prepare, fetch_binance_funding,
    add_cross_market_features, add_leverage_features,
    build_daily_positions, upsample_daily_to_1h_pnl,
    compute_1h_strategies, compute_quality, assemble_combined,
)

OUT_DIR_ = Path(OUT_DIR)
N = N_AGENTS    # 8
D = N_FEATURES  # 8
RETURN_FEAT = 0

# ── Channel index mapping ─────────────────────────────────────────────────
CH_C, CH_G, CH_A, CH_T = 0, 1, 2, 3
CH_NAMES = {CH_C: 'C(Mahal)', CH_G: 'G(Gap)', CH_A: 'A(Vel)', CH_T: 'T(Novel)'}

# ── Scoring thresholds (calibrated from data, percentile approach) ─────────
FIRE_PERCENTILE = 90   # use 90th pctile of each channel over normal period as threshold

# ── Anti-noise thresholds for strategy gates ──────────────────────────────
GATE_A_G   = 0.25   # exit when novel-stress attribution > 25%
GATE_A_A   = 0.20   # exit during cascade (activity attribution > 20%)
BOOST_A_T  = 0.15   # boost at regime transition (temporal attribution > 15%)
PSI_FLOOR  = 0.30   # minimum cos(ψ) to size up (avoid opposing gradients)


# ═══════════════════════════════════════════════════════════════════════════
#  FOUR-CHANNEL SIGNAL SWEEP
# ═══════════════════════════════════════════════════════════════════════════

def compute_four_channel_signals(X_panel: np.ndarray,
                                  df_1h:   pd.DataFrame,
                                  M,
                                  sig_v36: pd.DataFrame,
                                  fire_thresholds: np.ndarray) -> pd.DataFrame:
    """
    Full four-channel sweep per bar.

    Parameters
    ----------
    X_panel          : (T, N, d) raw state panels
    df_1h            : hourly DataFrame (for index)
    M                : calibrated MasterOperator
    sig_v36          : v36 signal DataFrame (for e_t, gamma_star_adj)
    fire_thresholds  : (4,) per-channel firing thresholds [C, G, A, T]

    Returns
    -------
    DataFrame with all four-channel signals indexed as df_1h
    """
    T    = len(X_panel)
    bsdt = M.bsdt
    E    = M.energy     # UnifiedEnergy object

    # Pre-allocate buffers
    keys = [
        # raw per-channel sums
        'e_C', 'e_G', 'e_A', 'e_T',
        # channel attribution  a_k = [grad(S)]_k² / ‖grad(S)‖²
        'a_C', 'a_G', 'a_A', 'a_T',
        # dominant channel by attribution
        'dom_energy',
        # feature-space gradient norms
        'G_norm_C', 'G_norm_G', 'G_norm_A', 'G_norm_T',
        'G_norm_4ch',
        # ψ: misalignment angle of composite vs primary
        'cos_psi_4ch',
        # R_t variants
        'R_t_4ch',
        # firing flags (threshold crossings)
        'fire_C', 'fire_G', 'fire_A', 'fire_T',
        # gradient alignment between channels (for R_t cross-term)
        'align_CG', 'align_CA', 'align_CT',
    ]
    buf = {k: np.full(T, np.nan) for k in keys}

    t0 = time.time()
    for t in range(2, T):
        snap = Snapshot(X=X_panel[t], X_prev=X_panel[t-1],
                        history=X_panel[max(0, t-20):t])
        try:
            # ── Channel-state vector ──────────────────────────────────────
            S = bsdt.channel_state(snap)   # (4,): sum of per-agent deltas

            buf['e_C'][t] = S[CH_C]
            buf['e_G'][t] = S[CH_G]
            buf['e_A'][t] = S[CH_A]
            buf['e_T'][t] = S[CH_T]

            # ── Channel attribution via UnifiedEnergy gradient ────────────
            # E.A is currently identity (pure_mahalanobis mode, beta=0, w=0)
            # grad(S) = 2*A*S = 2*I*S = 2*S  → a_k = S_k² / ‖S‖²
            # This is still correct: it weights channels by their squared energy
            a = E.channel_attribution(S)   # (4,)
            buf['a_C'][t] = a[CH_C]
            buf['a_G'][t] = a[CH_G]
            buf['a_A'][t] = a[CH_A]
            buf['a_T'][t] = a[CH_T]
            buf['dom_energy'][t] = float(E.dominant_channel(S))

            # ── Feature-space jacobians ───────────────────────────────────
            # jacobians returns {C,G,A,T} each (N,d)
            jac = bsdt.jacobians(snap)
            jC = jac['C']   # (N, d)
            jG = jac['G']
            jA = jac['A']
            jT = jac['T']

            nC = float(np.linalg.norm(jC, 'fro'))
            nG = float(np.linalg.norm(jG, 'fro'))
            nA = float(np.linalg.norm(jA, 'fro'))
            nT = float(np.linalg.norm(jT, 'fro'))
            buf['G_norm_C'][t] = nC
            buf['G_norm_G'][t] = nG
            buf['G_norm_A'][t] = nA
            buf['G_norm_T'][t] = nT

            # Composite gradient weighted by channel attribution
            G4 = a[CH_C] * jC + a[CH_G] * jG + a[CH_A] * jA + a[CH_T] * jT  # (N,d)
            n4 = float(np.linalg.norm(G4, 'fro'))
            buf['G_norm_4ch'][t] = n4

            # ψ: misalignment  cos(ψ) = ⟨G4, jC⟩_F / (‖G4‖ ‖jC‖)
            if n4 > 1e-12 and nC > 1e-12:
                cos_psi = float(np.sum(G4 * jC)) / (n4 * nC)
            else:
                cos_psi = 1.0
            buf['cos_psi_4ch'][t] = float(np.clip(cos_psi, -1.0, 1.0))

            # R_t: ‖G4‖² — higher-order: also compute cross-term
            # R_t_4ch < R_C when channels are opposing  → divergence measure
            R4 = n4 ** 2
            RC = nC ** 2
            buf['R_t_4ch'][t] = R4 / max(RC, 1e-12)   # ratio: <1 means opposing

            # ── Channel cross-alignment ───────────────────────────────────
            # Positive = channels reinforce, Negative = channels oppose
            def _cos(J1, J2):
                n1 = np.linalg.norm(J1, 'fro')
                n2 = np.linalg.norm(J2, 'fro')
                if n1 < 1e-12 or n2 < 1e-12:
                    return 0.0
                return float(np.sum(J1 * J2)) / (n1 * n2)

            buf['align_CG'][t] = _cos(jC, jG)
            buf['align_CA'][t] = _cos(jC, jA)
            buf['align_CT'][t] = _cos(jC, jT)

            # ── Firing threshold crossings ────────────────────────────────
            buf['fire_C'][t] = float(S[CH_C] > fire_thresholds[CH_C])
            buf['fire_G'][t] = float(S[CH_G] > fire_thresholds[CH_G])
            buf['fire_A'][t] = float(S[CH_A] > fire_thresholds[CH_A])
            buf['fire_T'][t] = float(S[CH_T] > fire_thresholds[CH_T])

        except Exception:
            pass  # leave as nan for this bar

        if t % 5000 == 0:
            print(f"    {t}/{T}  ({time.time()-t0:.1f}s)")

    print(f"  [v39] Four-channel sweep: {T:,} bars  {time.time()-t0:.1f}s")

    # ── Forward-fill and build derived signals ────────────────────────────
    idx = df_1h.index
    def _ff(arr, fill=0.0):
        return pd.Series(arr, index=idx).fillna(method='ffill').fillna(fill)

    df = pd.DataFrame({k: _ff(buf[k]) for k in keys}, index=idx)

    # ── Firing sequence detection ─────────────────────────────────────────
    # For each C-firing event, find the most recent prior G/A/T firing
    # Δτ = t_C_fire - t_last_G_fire  (positive means G fired before C)
    fire_C  = df['fire_C'].values.astype(bool)
    fire_G  = df['fire_G'].values.astype(bool)
    fire_A  = df['fire_A'].values.astype(bool)
    fire_T  = df['fire_T'].values.astype(bool)

    dt_CG = np.full(T, np.nan)
    dt_CA = np.full(T, np.nan)
    dt_CT = np.full(T, np.nan)

    last_G = last_A = last_T = -1
    for t in range(T):
        if fire_G[t]: last_G = t
        if fire_A[t]: last_A = t
        if fire_T[t]: last_T = t
        if fire_C[t]:
            if last_G >= 0: dt_CG[t] = t - last_G
            if last_A >= 0: dt_CA[t] = t - last_A
            if last_T >= 0: dt_CT[t] = t - last_T

    df['dt_CG'] = dt_CG
    df['dt_CA'] = dt_CA
    df['dt_CT'] = dt_CT

    return df


# ═══════════════════════════════════════════════════════════════════════════
#  CALIBRATE FIRING THRESHOLDS
# ═══════════════════════════════════════════════════════════════════════════

def calibrate_firing_thresholds(X_panel: np.ndarray,
                                  calib_mask: np.ndarray,
                                  M,
                                  pct: float = FIRE_PERCENTILE) -> np.ndarray:
    """
    Compute per-channel firing thresholds as pct-th percentile of channel
    energy in the normal (calibration) period.

    Returns
    -------
    thresholds : (4,)  [threshold_C, threshold_G, threshold_A, threshold_T]
    """
    bsdt = M.bsdt
    X_c  = X_panel[calib_mask]
    T0   = len(X_c)

    S_buf = np.full((T0, 4), np.nan)
    for t in range(1, T0):
        snap = Snapshot(X=X_c[t], X_prev=X_c[t-1],
                        history=X_c[max(0, t-20):t])
        try:
            S_buf[t] = bsdt.channel_state(snap)
        except Exception:
            pass

    thresholds = np.nanpercentile(S_buf, pct, axis=0)
    print(f"  [v39] Firing thresholds ({pct}th pctile over normal window):")
    for k, name in CH_NAMES.items():
        print(f"    {name}: {thresholds[k]:.4f}")
    return thresholds


# ═══════════════════════════════════════════════════════════════════════════
#  POSITION SIZING — V39 STRATEGY VARIANTS
# ═══════════════════════════════════════════════════════════════════════════

def apply_v39_sizing(base_pnl:  pd.Series,
                     sig_v36:   pd.DataFrame,
                     lam_feat:  pd.DataFrame,
                     sig_4ch:   pd.DataFrame) -> dict[str, pd.Series]:
    """
    V39 variants, all built on top of v38_sym_W100 base sizing.

    Lag all signals by 1 bar (no lookahead).

    v39_aG_gate   : multiply by 𝟙[a_G < GATE_A_G]
                    Exit when novel-stress is dominant — edge invalidated
    v39_aA_gate   : multiply by 𝟙[a_A < GATE_A_A]
                    Exit during velocity cascade — don't chase
    v39_aT_boost  : multiply by (0.75 + 0.25·𝟙[a_T > BOOST_A_T])
                    Full size at regime transitions (δ_T high = new move starting)
    v39_psi_gate  : multiply by max(cos_ψ, 0)
                    Zero size when gradient channels oppose
    v39_comb_CG   : aG_gate + aA_gate  (remove novel + velocity risk)
    v39_full_4ch  : aG_gate + aA_gate + aT_boost  [PRIMARY]
    v39_seq18     : boost when δ_T fired within 1-8 bars before current bar
                    (exploiting Δτ lead time of regime transition channel)
    """
    idx  = base_pnl.index
    sv36 = sig_v36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lam_feat.reindex(idx, method='ffill').fillna(0.5)
    s4   = sig_4ch.reindex(idx, method='ffill').fillna(0.0)
    base = base_pnl.fillna(0.0)

    # Core v38_sym_W100 sizing (lag-1)
    gam_adj  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lam_pct  = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size_sym = np.clip(1.0 - gam_adj, 0.0, 1.0) * (0.75 + 0.5 * lam_pct)

    # Channel signals (lag-1)
    a_G    = s4['a_G'].shift(1).fillna(0.0)
    a_A    = s4['a_A'].shift(1).fillna(0.0)
    a_T    = s4['a_T'].shift(1).fillna(0.0)
    cos_p  = s4['cos_psi_4ch'].shift(1).fillna(1.0)
    fire_T = s4['fire_T'].shift(1).fillna(0.0)

    # v39 gates and boosts
    gate_G  = (a_G < GATE_A_G).astype(float)
    gate_A  = (a_A < GATE_A_A).astype(float)
    boost_T = 0.75 + 0.25 * (a_T > BOOST_A_T).astype(float)
    psi_scl = np.clip(cos_p, 0.0, 1.0)     # zero out when opposing

    # Sequence signal: was δ_T fired 1-8 bars ago (and not now = transition started)?
    # Look forward from a T-fire event: boost sizing for the next 8 bars
    fire_T_raw = s4['fire_T'].values.astype(bool)
    seq_boost  = np.zeros(len(base))
    for t in range(len(base)):
        # If fire_T was active in any of the last 1-8 bars, boost
        lo = max(0, t - 9)
        hi = max(0, t - 1)
        if fire_T_raw[lo:hi+1].any():
            seq_boost[t] = 1.0
    seq_boost_s = pd.Series(seq_boost, index=idx)
    boost_seq = 0.75 + 0.25 * seq_boost_s

    pnl = {}
    pnl['v38_sym_W100']   = base * size_sym                                  # v38 champion
    pnl['v39_aG_gate']    = base * size_sym * gate_G
    pnl['v39_aA_gate']    = base * size_sym * gate_A
    pnl['v39_aT_boost']   = base * size_sym * boost_T
    pnl['v39_psi_gate']   = base * size_sym * psi_scl
    pnl['v39_comb_CG']    = base * size_sym * gate_G * gate_A
    pnl['v39_full_4ch']   = base * size_sym * gate_G * gate_A * boost_T
    pnl['v39_seq18']      = base * size_sym * boost_seq

    return pnl


# ═══════════════════════════════════════════════════════════════════════════
#  TRANSMISSION LAG ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def print_transmission_lag_analysis(sig_4ch: pd.DataFrame, test_mask):
    """
    Measure Δτ: how many bars before C-firing did each other channel fire.
    Reports the empirical firing sequence and lead times.
    """
    s = sig_4ch[test_mask]
    T = len(s)

    print(f"\n  Transmission Lag Analysis  ({T:,} test bars)")
    print(f"  {'Channel':12}  {'Fire Rate':10}  {'Avg e_norm':12}")
    total_e = (s['e_C'] + s['e_G'].clip(0) + s['e_A'].clip(0) + s['e_T']).clip(lower=1e-9)
    for ch, col_e, col_f in [('C(Mahal)', 'e_C', 'fire_C'),
                               ('G(Gap)',   'e_G', 'fire_G'),
                               ('A(Vel)',   'e_A', 'fire_A'),
                               ('T(Novel)', 'e_T', 'fire_T')]:
        fr  = s[col_f].mean() * 100
        en  = (s[col_e] / total_e).mean() * 100
        print(f"  {ch:12}  {fr:8.1f}%   {en:10.1f}%")

    print(f"\n  Cross-channel lead times (bars before C firing):")
    for col, lbl in [('dt_CG', 'Δτ(G→C)'), ('dt_CA', 'Δτ(A→C)'), ('dt_CT', 'Δτ(T→C)')]:
        v = s[col].dropna()
        if len(v) < 10:
            print(f"  {lbl}: insufficient data ({len(v)} events)")
            continue
        # Restrict to recent predecessor (within 48 bars = 2 days)
        v48 = v[v <= 48]
        if len(v48) < 10:
            print(f"  {lbl}: median={v.median():.0f} bars  mean={v.mean():.0f}  "
                  f"n_events={len(v)}")
            continue
        pct = [10, 25, 50, 75, 90]
        ps  = [float(v48.quantile(p/100)) for p in pct]
        print(f"  {lbl}: n={len(v48):4d}  "
              f"p10={ps[0]:.0f}  p25={ps[1]:.0f}  median={ps[2]:.0f}  "
              f"p75={ps[3]:.0f}  p90={ps[4]:.0f}  bars")

    # Channel attribution breakdown
    print(f"\n  Channel attribution (a_k) — test period 2023-2026:")
    for col, lbl in [('a_C','a_C'),('a_G','a_G'),('a_A','a_A'),('a_T','a_T')]:
        v = s[col]
        print(f"    {lbl}: mean={v.mean():.3f}  std={v.std():.3f}  "
              f"p5={v.quantile(0.05):.3f}  p95={v.quantile(0.95):.3f}")

    # Dominant channel breakdown
    dc = s['dom_energy'].round().astype(int).value_counts(normalize=True) * 100
    print(f"\n  Dominant channel distribution:")
    for ki, pct in dc.sort_index().items():
        print(f"    {CH_NAMES.get(ki, ki)}: {pct:.1f}%")

    # Gradient alignment breakdown
    print(f"\n  Gradient alignment (cos angle between channel jacobians):")
    for col, lbl in [('align_CG','C↔G'), ('align_CA','C↔A'), ('align_CT','C↔T')]:
        v = s[col]
        frac_opp = (v < 0).mean() * 100
        print(f"    {lbl}: mean={v.mean():+.3f}  opposing={frac_opp:.1f}%")

    # cos(ψ) distribution — critical for false-alarm analysis
    cp = s['cos_psi_4ch']
    low_psi_pct = (cp < PSI_FLOOR).mean() * 100
    print(f"\n  cos(ψ_4ch) distribution:")
    print(f"    mean={cp.mean():+.3f}  std={cp.std():.3f}  "
          f"p5={cp.quantile(0.05):+.3f}  p95={cp.quantile(0.95):+.3f}")
    print(f"    cos(ψ) < {PSI_FLOOR} (opposing/weak):  {low_psi_pct:.1f}% of bars")


# ═══════════════════════════════════════════════════════════════════════════
#  SUMMARY TABLE
# ═══════════════════════════════════════════════════════════════════════════

def print_summary_table(pnl_dict: dict[str, pd.Series], K: int = 5):
    test = lambda s: s[s.index >= TEST_START]
    print(f"\n  {'Strategy':<22}  {'Sharpe':>7}  {'MaxDD':>7}  {'CAGR':>8}  "
          f"{'Active%':>8}  {'ActDays':>8}  {'$100→':>8}")
    print("  " + "-" * 88)
    for name, pnl in pnl_dict.items():
        ts = test(pnl)
        lev = (ts * K).clip(-0.5, 0.5)
        sh  = float(lev.mean() / lev.std() * np.sqrt(ANN_1H)) if lev.std() > 0 else 0.0
        ec  = (1 + lev).cumprod()
        dd  = float((ec / ec.cummax() - 1).min())
        final = float(ec.iloc[-1]) * 100
        n_yrs = len(ts) / (365 * 24)
        cagr  = float(ec.iloc[-1] ** (1 / max(n_yrs, 0.1)) - 1) * 100
        active = float((ts != 0).mean()) * 100
        act_d  = int(active / 100 * len(ts) / 24)
        print(f"  {name:<22}  {sh:>+7.3f}  {dd*100:>6.1f}%  {cagr:>7.1f}%  "
              f"  {active:>6.1f}%  {act_d:>5d}d  ${final:>6.2f}")


def _yoy_table(name: str, pnl: pd.Series, K_list=(1, 2, 5)):
    test_mask = pnl.index >= TEST_START
    years = sorted(pnl[test_mask].index.year.unique())
    print(f"\n  {name}")
    print(f"    {'K':<5}  " + "  ".join(f"{y:>7}" for y in years) +
          f"  {'$100→':>8}  {'MaxDD':>7}  {'CAGR':>9}")
    print("  " + "-" * (5 + 9 * len(years) + 28))
    for K in K_list:
        r   = _net_ret(pnl, K)
        eq  = 100.0
        yr_r = {}
        for yr in years:
            m = (pnl.index.year == yr) & test_mask
            ret = float((1.0 + r[m]).prod() - 1.0)
            yr_r[yr] = ret
            eq *= (1.0 + ret)
        ec  = 100.0 * (1.0 + r).cumprod()
        mdd = float((ec / ec.cummax() - 1.0).min())
        n_yrs = len(r[test_mask]) / (365 * 24)
        cagr  = float((eq / 100.0) ** (1.0 / max(n_yrs, 0.01)) - 1.0) * 100
        yr_str = "  ".join(f"{yr_r.get(y,0)*100:>+6.0f}%" for y in years)
        print(f"    {K:<5d}  {yr_str}  ${eq:>7.2f}  {mdd*100:>+6.1f}%  {cagr:>+7.1f}%/yr")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    t_start = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)

    print("=" * 100)
    print("  CRYPTO BSDT v39 — FOUR-CHANNEL OPERATOR")
    print("  δ_C (Mahal) | δ_G (Gap) | δ_A (Velocity) | δ_T (Temporal)")
    print("=" * 100)

    # ─────────────────────────────────────── 1h DATA ──
    print("\n[1] Fetching Binance 1h data ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"  {len(df_1h):,} bars  |  Train: {train_1h.sum():,}  |  Test: {test_1h.sum():,}")

    # ──────────────────────────────────────── FUNDING ──
    print("\n[2] Fetching funding data ...")
    try:
        funding  = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
        fund_eth = funding.get('ETHUSDT') if isinstance(funding, dict) else None
        fund_btc = funding.get('BTCUSDT') if isinstance(funding, dict) else None
    except Exception:
        fund_eth = fund_btc = None

    # ──────────────────────────────── 8×8 STATE PANEL ──
    print("\n[3] Building 8×8 intraday state panel ...")
    X_panel = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X_panel = np.nan_to_num(X_panel)
    print(f"  Shape: {X_panel.shape}")

    # ──────────────────────────────────── CALIBRATE ──
    train_idx  = np.where(train_1h)[0]
    calib_idx  = train_idx[-CALIB_BARS:]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[calib_idx] = True

    print(f"\n[4] Calibrating physics engine ...")
    M, net, geom, lyap, ews, stoch, e_star, theta = \
        calibrate_intraday_engine(X_panel, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)

    # ───────────────────────────── V36 SIGNALS ──
    print(f"\n[5] Computing v36 signals ({len(df_1h):,} bars) ...")
    sig_v36 = compute_intraday_signals(X_panel, df_1h, M, net, ews, stoch,
                                       e_star, theta, history_len=48)
    print(f"  v36 signals: {len(sig_v36.columns)} columns")

    # ─────────────────────── V37 PRICE PREDICTION LAYER ──
    print(f"\n[6] Computing v37 price prediction layer (λ_price) ...")
    sig_v37, M_reversal, sigma00_sqrt = compute_price_prediction_signals(
        X_panel, df_1h, M, sig_v36, e_star, sigma_n)

    # ─────────────────────── V38 NORMALISED-λ FEATURES ──
    print(f"\n[7] Computing v38 normalised-λ features ...")
    lam_feat = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    # ──────────────── CALIBRATE FIRING THRESHOLDS ──
    print(f"\n[8] Calibrating four-channel firing thresholds ...")
    fire_thresholds = calibrate_firing_thresholds(X_panel, calib_mask, M,
                                                   pct=FIRE_PERCENTILE)

    # ──────────────── FOUR-CHANNEL SWEEP ──
    print(f"\n[9] Computing four-channel signals ({len(df_1h):,} bars) ...")
    sig_4ch = compute_four_channel_signals(X_panel, df_1h, M, sig_v36, fire_thresholds)
    print(f"  Four-channel signals: {len(sig_4ch.columns)} columns")

    # ──────────────── TRANSMISSION LAG ANALYSIS ──
    print("\n" + "=" * 100)
    print("  TRANSMISSION LAG ANALYSIS  (theoretical firing sequence measurement)")
    print("=" * 100)
    print_transmission_lag_analysis(sig_4ch, test_1h)

    # ─────────────────────────── BUILD V34 BASE PORTFOLIO ──
    print("\n[10] Building v34 base portfolio ...")
    h_strats = compute_1h_strategies(df_1h, has_sol)
    df_d    = fetch_and_prepare()
    df_d    = add_cross_market_features(df_d)
    fund_d  = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
    df_d    = add_leverage_features(df_d, fund_d)
    train_mask_d   = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
    train_mask_arr = np.asarray(train_mask_d, dtype=bool)

    pos_dict, _, F_daily, gate_daily = build_daily_positions(
        df_d, train_mask_d, train_mask_arr)
    instr_map = {
        'D1_trend_eth': df_1h['ret_eth'],
        'D2_pairs_eb':  df_1h['spread_ret_eb'],
        'D3_pairs_es':  df_1h['ret_eth'] - df_1h.get('ret_sol', df_1h['ret_eth']),
        'D4_macro_btc': df_1h['ret_btc'],
        'D5_macro_alt': df_1h['ret_eth'],
    }
    d_strats_1h = {
        name: upsample_daily_to_1h_pnl(pos, instr_map.get(name, df_1h['ret_eth']),
                                        gate_daily)
        for name, pos in pos_dict.items()
    }
    all_pnls = {**d_strats_1h, **h_strats}
    Q_v34    = compute_quality(all_pnls, bpd=BPD)
    pnl_combined_v34 = assemble_combined(all_pnls, Q_v34)
    st_v34 = _stats(pnl_combined_v34[pnl_combined_v34.index >= TEST_START])
    print(f"  v34 gross  Sharpe: {st_v34['sharpe']:+.3f}  "
          f"MaxDD: {st_v34['max_dd']:+.1%}  CAGR: {st_v34['cagr']:+.1%}")

    # ──────────────────────────── APPLY V39 SIZING ──
    print("\n[11] Applying v39 four-channel sizing ...")
    pnl_dict = apply_v39_sizing(pnl_combined_v34, sig_v36, lam_feat, sig_4ch)
    # Add v34 baseline for comparison
    pnl_dict = {'v34_baseline': pnl_combined_v34, **pnl_dict}

    # ──────────────── GROSS SNAPSHOT TABLE ──
    print("\n" + "=" * 100)
    print("  GROSS SNAPSHOT  (K=5, 2023 → 2026)")
    print("=" * 100)
    print_summary_table(pnl_dict, K=5)

    # ──────────────── YEAR-ON-YEAR TABLES ──
    print("\n" + "=" * 100)
    print("  YEAR-ON-YEAR  ($100 start, compounding, gross)")
    print("=" * 100)
    for name, pnl in pnl_dict.items():
        _yoy_table(name, pnl)

    # ─────────────────────────────────────── SAVE ──
    res_path = OUT_DIR_ / 'crypto_bsdt_v39_four_channels.json'
    results = {}
    for name, pnl in pnl_dict.items():
        ts  = pnl[pnl.index >= TEST_START]
        lev = (ts * 5).clip(-0.5, 0.5)
        ec  = (1 + lev).cumprod()
        n_yrs = len(ts) / (365 * 24)
        cagr  = float(ec.iloc[-1] ** (1 / max(n_yrs, 0.1)) - 1) * 100
        dd    = float((ec / ec.cummax() - 1).min())
        sh    = float(lev.mean() / lev.std() * np.sqrt(ANN_1H)) if lev.std() > 0 else 0.0
        results[name] = {
            'sharpe_K5': round(sh, 4),
            'max_dd_K5': round(dd * 100, 2),
            'cagr_K5':   round(cagr, 2),
            'final_K5':  round(float(ec.iloc[-1]) * 100, 2)
        }

    # Also save 4ch signal summary stats
    sig_summary = {}
    for col in ['a_C','a_G','a_A','a_T','cos_psi_4ch','R_t_4ch',
                'align_CG','align_CA','align_CT','e_G','e_A']:
        v = sig_4ch[test_1h][col].dropna()
        sig_summary[col] = {
            'mean': round(float(v.mean()), 5),
            'std':  round(float(v.std()),  5),
            'p5':   round(float(v.quantile(0.05)), 5),
            'p95':  round(float(v.quantile(0.95)), 5),
        }

    with open(res_path, 'w') as f:
        json.dump({'strategies': results, 'signals': sig_summary}, f, indent=2)
    print(f"\n  Saved → {res_path}")

    print(f"\n  Total runtime: {time.time()-t_start:.0f}s")
    print("=" * 100)


if __name__ == '__main__':
    main()
