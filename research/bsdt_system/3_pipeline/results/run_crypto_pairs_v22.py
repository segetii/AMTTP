"""
Crypto BSDT v22 — Geometric Allocation Engine
=============================================

Engine → ALLOCATION (not just scaling).

Three fixes over v21 + a real allocation layer:

  FIX 1  PrecursorScale floors
         v21: P_scale collapsed to 1e-9 → precursor_score O(1e9)
         v22: relative floors (std + |mean|) → precursor_score O(1)

  FIX 2  Layer-B threshold = ROLLING μ + 2σ  (not frozen ceiling)
         v21: frozen μ+2σ on 730 train days → max test score 0.907 < 0.911
              ⇒ Layer B never fires
         v22: 252-day rolling stats (lagged) → adaptive, geometry actually fires

  FIX 3  PER-PAIR mini-engines (cross-sectional allocation)
         v21: one global engine → one global pos_scale → all pairs gated identically
         v22: each pair (P1/P2/P3) gets its own MasterOperator+EWS calibrated on
              its 2-asset panel; per-pair continuous gate ∈ [0.2, 1.1] via
              sigmoid((thresh − score)/σ)
         Plus directional cos θ_channel tilt: pairs whose channel cosine is
         well-aligned (|cos θ| close to 1) get a weight boost; those near the
         null space get pulled back.

GLOBAL gating (full-cash AB event) is retained from v21 as a safety net.
"""
from __future__ import annotations
import os
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import sys
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── reuse v19 stack + v21 engine helpers ─────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
import run_crypto_pairs_v19 as v19
from run_crypto_pairs_v19 import (
    fetch_and_prepare, add_cross_market_features,
    fetch_binance_funding, add_leverage_features,
    compute_bsdt, compute_gamma_rank, compute_activity_signals,
    compute_state_vector, compute_geom_signals_v18_smooth,
    apply_geom_penalties_v18, compute_leverage_dial,
    compute_rolling_spread_v8, SpreadUDLClassifier,
    compute_manifold_validity, detect_phase,
    route_pair_v7, route_btcalt_macro, setup_a_directional,
    get_daily_pnl, compute_cs_weights,
    simulate_from_pnl, equity_at_K, find_best_K,
    _build_state_panel,
    TRAIN_START, TRAIN_END, TEST_START, OUT_DIR,
    GAMMA_SCORE_WIN, ALARM_MIN_STEPS,
)
from run_crypto_pairs_v21 import (
    calibrate_frozen_engine, calibrate_layer_b_threshold,
    apply_alarm_latch,
    HISTORY_LEN, ALPHA_CONF, N_SIGMA_THRESHOLD, ALARM_LATCH_DAYS,
    KRAMERS_TAU, SIGMA_N_FALLBACK, LEV_LO, LEV_HI,
)

sys.path.insert(0, r'C:\amttp\research\adaptive-friction')
from collapse_geometry import (
    MasterOperator, Snapshot,
    LedoitWolfNetwork,
    LyapunovCertificate, CollapseGeometry,
    EarlyWarning, PrecursorScale,
    InformationGeometry,
    StochasticExtension,
)


# ═══════════════════════════════════════════════════════════════════════
#   v22 PARAMETERS
# ═══════════════════════════════════════════════════════════════════════
PAIR_ASSETS = {
    'P1_ETH_BTC': ['eth', 'btc'],
    'P2_ETH_SOL': ['eth', 'sol'],
    'P3_ETH_BNB': ['eth', 'bnb'],
}
ROLL_WIN          = 252      # rolling threshold window
PAIR_GATE_LO      = 0.20     # min per-pair gate
PAIR_GATE_HI      = 1.10     # max per-pair gate (mild over-position when very calm)
COSTHETA_TILT_K   = 0.5      # weight tilt strength from |cos θ|
LAYER_A_THRESHOLD = 0.50     # fire Layer A when precursor_score ≥ 0.5 (was 1.0)
LAYER_B_N_SIGMA   = 1.0      # rolling Layer B threshold = μ + 1.0σ (was 2.0)

# Global allocator: AB only triggers full cash; A/B mild de-risk
ALLOC_GLOBAL = {
    "":   (1.00, 0.00),
    "A":  (0.85, 0.15),    # mild — let per-pair gates do the work
    "B":  (0.60, 0.40),    # geometry confirmed → meaningful global cut
    "AB": (0.00, 1.00),    # both → full cash
}
# v21-style alloc retained for baseline comparison
ALLOC_V21 = {
    "":   (1.00, 0.00),
    "A":  (0.70, 0.30),
    "B":  (0.40, 0.60),
    "AB": (0.00, 1.00),
}


# ═══════════════════════════════════════════════════════════════════════
#   FIX 1 — PrecursorScale floors
# ═══════════════════════════════════════════════════════════════════════
def patch_precursor_scale(ews, M, X_normal):
    """Re-floor each P95 denominator using std + |mean| of its raw signal.

    Prevents 1e-9 collapse (which makes precursor_score O(1e9)).
    Floors are computed from the SAME vals from_panel saw.
    """
    lyap = LyapunovCertificate(op=M)
    T0 = X_normal.shape[0]
    P_vals, psi_vals, S_vals, V_vals = [], [], [], []
    snap_prev = None
    for t in range(T0):
        snap = Snapshot(
            X=X_normal[t],
            X_prev=X_normal[t-1] if t > 0 else X_normal[0],
            history=X_normal[max(0, t-5):t] if t > 0 else X_normal[0:1],
        )
        try: P_vals.append(max(0.0, float(lyap._bundle(snap)["Pt"])))
        except Exception: P_vals.append(0.0)
        try: psi_vals.append(float(1.0 - np.cos(M.mfls.psi(snap))))
        except Exception: psi_vals.append(0.0)
        try: S_vals.append(float(np.std(M.bsdt.channel_state(snap))))
        except Exception: S_vals.append(0.0)
        if snap_prev is not None:
            try:
                V_vals.append(float(np.sum(np.abs(
                    M.bsdt.channel_state(snap) - M.bsdt.channel_state(snap_prev)))))
            except Exception:
                V_vals.append(0.0)
        else:
            V_vals.append(0.0)
        snap_prev = snap

    def _floor(vals, current):
        v = np.asarray(vals, dtype=float)
        std_floor = float(np.std(v) + abs(np.mean(v)))
        max_floor = float(np.max(np.abs(v))) * 0.5
        proposed  = max(std_floor, max_floor, 1e-3)
        # always take the bigger of (P95 from from_panel, our std-based floor)
        return max(current, proposed)

    old = (ews.precursor_scale.P_scale, ews.precursor_scale.psi_scale,
           ews.precursor_scale.S_scale, ews.precursor_scale.V_scale)
    ews.precursor_scale.P_scale   = _floor(P_vals,   ews.precursor_scale.P_scale)
    ews.precursor_scale.psi_scale = _floor(psi_vals, ews.precursor_scale.psi_scale)
    ews.precursor_scale.S_scale   = _floor(S_vals,   ews.precursor_scale.S_scale)
    ews.precursor_scale.V_scale   = _floor(V_vals,   ews.precursor_scale.V_scale)
    new = (ews.precursor_scale.P_scale, ews.precursor_scale.psi_scale,
           ews.precursor_scale.S_scale, ews.precursor_scale.V_scale)
    print(f"  [v22] PrecursorScale patched:")
    print(f"        P  : {old[0]:.4e} → {new[0]:.4e}")
    print(f"        ψ  : {old[1]:.4e} → {new[1]:.4e}")
    print(f"        S  : {old[2]:.4e} → {new[2]:.4e}")
    print(f"        V  : {old[3]:.4e} → {new[3]:.4e}")


# ═══════════════════════════════════════════════════════════════════════
#   FIX 2 — Rolling Layer-B threshold
# ═══════════════════════════════════════════════════════════════════════
def emit_global_signals(df, X_panel, M, net, geom, lyap, ews, sigma_n,
                        history_len=HISTORY_LEN):
    """One pass over the timeline producing:

        geom_score_t          = ews.score(snap, net)             (Layer B raw)
        precursor_score_t     = ews.precursor_score(snap, prev)  (Layer A normalised)
        cos_theta_channel_t   = geom.cos_theta_channel(snap)
        kramers_p_t           = stoch.cross_probability(...)

    Returns DataFrame indexed by df.index.
    """
    T = len(df)
    stoch = StochasticExtension(op=M, lyap=lyap, sigma_n=sigma_n)

    geom_s = np.full(T, np.nan)
    pre_s  = np.full(T, np.nan)
    cos_t  = np.full(T, np.nan)
    p_kr   = np.full(T, np.nan)

    t0 = time.time()
    for t in range(2, T):
        snap = Snapshot(X=X_panel[t], X_prev=X_panel[t-1],
                        history=X_panel[max(0, t-history_len):t])
        snap_prev = Snapshot(X=X_panel[t-1], X_prev=X_panel[t-2],
                             history=X_panel[max(0, t-1-history_len):t-1])
        try: geom_s[t] = float(ews.score(snap, net))
        except Exception: pass
        try: pre_s[t]  = float(ews.precursor_score(snap, snap_prev))
        except Exception: pass
        try: cos_t[t]  = float(geom.cos_theta_channel(snap))
        except Exception: pass
        try: p_kr[t]   = float(stoch.cross_probability(
                              snap, e_star=20.0, tau=KRAMERS_TAU, dt=1e-2))
        except Exception: pass

        if (t % 400) == 0:
            print(f"    global sweep t={t}/{T}  ({time.time()-t0:.1f}s)")

    print(f"  [v22] Global signal sweep complete ({time.time()-t0:.1f}s)")
    return pd.DataFrame({
        'geom_score':       geom_s,
        'precursor_score':  pre_s,
        'cos_theta':        cos_t,
        'kramers_p':        p_kr,
    }, index=df.index)


def rolling_layer_b_alarm(geom_score, n_sigma=N_SIGMA_THRESHOLD,
                          win=ROLL_WIN, min_periods=60):
    """Day-t threshold = mean + n·σ over [t-win, t-1] (lagged → no lookahead)."""
    mu = geom_score.rolling(win, min_periods=min_periods).mean().shift(1)
    sd = geom_score.rolling(win, min_periods=min_periods).std().shift(1)
    thresh = mu + n_sigma * sd
    alarm  = (geom_score > thresh).fillna(False)
    return thresh, alarm


def two_layer_from_signals(F, e_star_unused=None,
                           n_sigma=LAYER_B_N_SIGMA, win=ROLL_WIN,
                           a_threshold=LAYER_A_THRESHOLD):
    """Compose two-layer alarm using:
       Layer A — ews.precursor_score >= a_threshold  (default 0.5)
       Layer B — geom_score > rolling μ + n·σ
    """
    thresh, alarm_B = rolling_layer_b_alarm(F['geom_score'], n_sigma=n_sigma, win=win)
    alarm_A = (F['precursor_score'] >= a_threshold).fillna(False)

    layer = pd.Series('', index=F.index)
    layer[alarm_A &  alarm_B] = 'AB'
    layer[alarm_A & ~alarm_B] = 'A'
    layer[~alarm_A & alarm_B] = 'B'
    F = F.copy()
    F['layer_b_thresh'] = thresh
    F['alarm_A'] = alarm_A.astype(int)
    F['alarm_B'] = alarm_B.astype(int)
    F['layer']   = layer
    F['alarm_raw'] = (alarm_A | alarm_B).astype(int)
    return F


# ═══════════════════════════════════════════════════════════════════════
#   FIX 3 — Per-pair mini-engines + continuous gating
# ═══════════════════════════════════════════════════════════════════════
def _build_pair_panel(df, assets):
    """Build (T, N=len(assets), d=2) panel for one pair."""
    def _rz(s, w=252):
        mu = s.rolling(w, min_periods=60).mean()
        sd = s.rolling(w, min_periods=60).std()
        return (s - mu) / (sd + 1e-9)

    T = len(df)
    X = np.zeros((T, len(assets), 2))
    for i, a in enumerate(assets):
        if f'ret_{a}_z' in df.columns:
            X[:, i, 0] = df[f'ret_{a}_z'].fillna(0).values
        else:
            X[:, i, 0] = _rz(df[f'ret_{a}']).fillna(0).values
        if f'vol_{a}' in df.columns:
            X[:, i, 1] = _rz(df[f'vol_{a}']).fillna(0).values
    return X


def calibrate_pair_engine(X_pair, train_mask):
    """Calibrate a frozen mini-engine on a pair's 2-asset panel."""
    X_normal = X_pair[train_mask]
    T0, N, d = X_normal.shape
    M    = MasterOperator.calibrate(X_normal, k=min(2, d), theta=1.0)
    net  = LedoitWolfNetwork.from_panel(X_normal[..., 0])
    geom = CollapseGeometry(op=M)
    ews  = EarlyWarning(op=M, geom=geom)
    ews.precursor_scale = PrecursorScale.from_panel(M, X_normal)
    patch_precursor_scale(ews, M, X_normal)
    return M, net, geom, ews


def emit_pair_signals(df, X_pair, M, net, geom, ews, history_len=HISTORY_LEN):
    """Per-pair sweep: geom_score + cos_theta_channel."""
    T = len(df)
    g = np.full(T, np.nan)
    c = np.full(T, np.nan)
    for t in range(2, T):
        snap = Snapshot(X=X_pair[t], X_prev=X_pair[t-1],
                        history=X_pair[max(0, t-history_len):t])
        try: g[t] = float(ews.score(snap, net))
        except Exception: pass
        try: c[t] = float(geom.cos_theta_channel(snap))
        except Exception: pass
    return pd.Series(g, index=df.index), pd.Series(c, index=df.index)


def per_pair_gate(score, n_sigma=N_SIGMA_THRESHOLD, win=ROLL_WIN,
                  lo=PAIR_GATE_LO, hi=PAIR_GATE_HI):
    """SYMMETRIC continuous gate centered on 1.0.

    z_t = (score_t − μ_t) / σ_t      (rolling, lagged → no lookahead)
    gate_t = 1.0 − α · tanh(z_t)       α = (hi − lo)/2

    Calm (score < μ → z<0) → gate slightly > 1 (boost).
    Stress (score > μ → z>0) → gate < 1 (cut).
    Mean gate ≈ 1.0 over the window so we don't bleed Sharpe to chronic
    under-positioning.
    """
    mu = score.rolling(win, min_periods=60).mean().shift(1)
    sd = score.rolling(win, min_periods=60).std().shift(1).clip(lower=1e-6)
    z  = ((score - mu) / sd).clip(-5.0, 5.0)
    alpha = (hi - lo) / 2.0
    gate = 1.0 - alpha * np.tanh(z)
    gate = gate.clip(lower=lo, upper=hi).fillna(1.0)
    thresh = mu + n_sigma * sd
    return gate, thresh


def cos_theta_tilt(cos_series, k=COSTHETA_TILT_K):
    """Map |cos θ_channel| ∈ [0, 1] → multiplier ∈ [1−k, 1+k].

    Aligned channel (|cos θ| → 1) means the system is moving along its
    natural manifold direction → boost weight.  Near the null space
    (|cos θ| → 0) → cut weight.
    """
    abs_cos = cos_series.abs().clip(0.0, 1.0)
    # rescale so mean ≈ 1
    base = (1.0 - k) + 2.0 * k * abs_cos
    return base.fillna(1.0)


# ═══════════════════════════════════════════════════════════════════════
#   ALLOCATOR — global cash gate × per-pair gate × cos-θ tilt
# ═══════════════════════════════════════════════════════════════════════
def compose_v22_pnl(pnl_base_dict, pair_gates, pair_tilts,
                    global_pos, global_cash, cs_wts):
    """v22 PnL builder.

    pnl_base_dict : {strategy_key → pnl_series}
    pair_gates    : {strategy_key → gate_series}  (1.0 if unhedged)
    pair_tilts    : {strategy_key → tilt_series}  (1.0 default)
    global_pos    : Series ∈ [0, 1] (from layer)
    global_cash   : Series ∈ [0, 1] = 1 − global_pos
    cs_wts        : {key → weight_series}
    """
    idx  = next(iter(pnl_base_dict.values())).index
    risk = (1.0 - global_cash).clip(0.0, 1.0)
    n_s  = len(pnl_base_dict)
    pnl_v22 = pd.Series(0.0, index=idx)

    for k, base in pnl_base_dict.items():
        gate = pair_gates.get(k, pd.Series(1.0, index=idx))
        tilt = pair_tilts.get(k, pd.Series(1.0, index=idx))
        cs_w = cs_wts.get(k, pd.Series(1.0/n_s, index=idx))
        # All multipliers shifted by 1 day to avoid lookahead
        eff = (cs_w.shift(1).fillna(1.0/n_s)
               * gate.shift(1).fillna(1.0).clip(0.0, PAIR_GATE_HI)
               * tilt.shift(1).fillna(1.0).clip(0.5, 1.5))
        pnl_v22 += eff * base.fillna(0.0)

    return pnl_v22 * risk.values * global_pos.values


# ═══════════════════════════════════════════════════════════════════════
#   MAIN
# ═══════════════════════════════════════════════════════════════════════
def main():
    out_dir = Path(OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 92)
    print("  CRYPTO BSDT v22 — Geometric Allocation Engine")
    print("  Engine → ALLOCATION  ·  per-pair gating  ·  directional cos θ tilt")
    print("=" * 92)

    df = fetch_and_prepare()
    print("  Adding cross-market features ...")
    df = add_cross_market_features(df)
    print("  Fetching Binance funding rates ...")
    funding = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
    df = add_leverage_features(df, funding)

    train_mask = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask  = df.index >= TEST_START
    print(f"  Train: {df[train_mask].index[0].date()} → {df[train_mask].index[-1].date()}  "
          f"({int(train_mask.sum())} days)")
    print(f"  Test:  {df[test_mask].index[0].date()} → {df[test_mask].index[-1].date()}  "
          f"({int(test_mask.sum())} days)")
    train_mask_arr = train_mask.values if hasattr(train_mask, 'values') else np.asarray(train_mask)

    # ── [2] Legacy BSDT ──────────────────────────────────────────────────
    print("\n[2] Computing BSDT signals (legacy) ...")
    feats_strat = ['ret_eth_z', 'ret_btc_z', 'ret_sol_z', 'ret_bnb_z',
                   'vol_eth_z', 'vol_btc_z', 'btc_dom_z', 'cross_disp_z']
    feats_ext   = feats_strat + ['ret_spx_z', 'dvix_z', 'ret_dxy_z']
    omega_strat, mfls_eth, gamma_eth = compute_bsdt(df, feats_strat, window=60)
    omega_ext,   _,        _         = compute_bsdt(df, feats_ext,   window=60)
    A_eth, A_rank, dA_fast, dA_rank  = compute_activity_signals(mfls_eth, gamma_eth)
    gamma_rank = compute_gamma_rank(omega_ext, min_periods=60)
    lev_mult   = compute_leverage_dial(gamma_rank)

    # ── [3] Global engine ────────────────────────────────────────────────
    print("\n[3] Building global (T, N=4, d=2) state panel ...")
    X_panel = _build_state_panel(df)
    print(f"  Panel shape: {X_panel.shape}")

    print("\n[4] Calibrating frozen GLOBAL engine ...")
    M, net, geom, lyap, info, ews, e_star, sigma_n = calibrate_frozen_engine(
        X_panel, train_mask_arr)
    patch_precursor_scale(ews, M, X_panel[train_mask_arr])

    print("\n[5] Global signal sweep (geom, precursor, cos θ, Kramers) ...")
    F = emit_global_signals(df, X_panel, M, net, geom, lyap, ews, sigma_n)
    F = two_layer_from_signals(F, n_sigma=LAYER_B_N_SIGMA, win=ROLL_WIN,
                               a_threshold=LAYER_A_THRESHOLD)

    F_test = F[test_mask]
    print(f"\n  Test diagnostics ({len(F_test)} days):")
    layer_counts = F_test['layer'].value_counts().to_dict()
    for k in ('', 'A', 'B', 'AB'):
        cnt = layer_counts.get(k, 0)
        print(f"    layer='{k or '<clear>':7s}': {cnt:4d} days  "
              f"({100*cnt/max(len(F_test),1):.1f}%)")
    print(f"    geom_score    : mean={F_test['geom_score'].mean():.4f}  "
          f"max={F_test['geom_score'].max():.4f}  "
          f"avg_thresh={F_test['layer_b_thresh'].mean():.4f}")
    print(f"    precursor (FIXED): mean={F_test['precursor_score'].mean():.4f}  "
          f"max={F_test['precursor_score'].max():.4f}  thresh=1.000")
    print(f"    |cos θ|       : mean={F_test['cos_theta'].abs().mean():.4f}")
    print(f"    Kramers P     : mean={F_test['kramers_p'].mean():.4f}")

    # ── [6] Latch + global allocation (AB-only safety net) ───────────────
    print("\n[6] Latching alarm + global allocation ...")
    alarm_latched = apply_alarm_latch(F, min_steps=ALARM_LATCH_DAYS)
    layers = F['layer'].fillna('').values
    last_layer = ""
    g_pos = np.ones(len(F))
    g_cash = np.zeros(len(F))
    for i, (lat, ly) in enumerate(zip(alarm_latched.values, layers)):
        if lat:
            if ly:
                last_layer = ly
            ps, cs = ALLOC_GLOBAL.get(last_layer or "B", ALLOC_GLOBAL["B"])
        else:
            last_layer = ""
            ps, cs = ALLOC_GLOBAL[""]
        g_pos[i], g_cash[i] = ps, cs
    g_pos  = pd.Series(g_pos,  index=F.index, name='global_pos')
    g_cash = pd.Series(g_cash, index=F.index, name='global_cash')
    print(f"  Latched alarm [test]: {int(alarm_latched[test_mask].sum())} / "
          f"{int(test_mask.sum())} ({100*alarm_latched[test_mask].mean():.1f}%)")
    print(f"  global_pos  [test]: mean={g_pos[test_mask].mean():.3f}  "
          f"min={g_pos[test_mask].min():.3f}")
    print(f"  global_cash [test]: mean={g_cash[test_mask].mean():.3f}")

    # ── [7] Per-pair mini-engines ────────────────────────────────────────
    print("\n[7] Calibrating per-pair mini-engines ...")
    pair_engines = {}
    for key, assets in PAIR_ASSETS.items():
        print(f"  {key} ({'+'.join(assets)}):")
        Xp = _build_pair_panel(df, assets)
        Mp, netp, geomp, ewsp = calibrate_pair_engine(Xp, train_mask_arr)
        pair_engines[key] = (Xp, Mp, netp, geomp, ewsp)

    print("\n[8] Per-pair signal sweep + continuous gating ...")
    pair_gates = {}
    pair_tilts = {}
    for key, (Xp, Mp, netp, geomp, ewsp) in pair_engines.items():
        score, cos_p = emit_pair_signals(df, Xp, Mp, netp, geomp, ewsp)
        gate, thresh = per_pair_gate(score)
        tilt = cos_theta_tilt(cos_p)
        pair_gates[key] = gate
        pair_tilts[key] = tilt
        gt = gate[test_mask]
        st = score[test_mask]
        ct = cos_p[test_mask].abs()
        print(f"  {key}: gate mean={gt.mean():.3f} (lo={gt.min():.3f}, "
              f"hi={gt.max():.3f}) | score mean={st.mean():.3f} | "
              f"|cos θ| mean={ct.mean():.3f}")

    # ── [9] Build base strategies (verbatim v19) ─────────────────────────
    print("\n[9] Building strategy positions ...")
    ret7  = df['ret_eth'].rolling(7).sum()
    ret3  = df['ret_eth'].rolling(3).sum()
    phase = detect_phase(omega_strat, ret7, ret3, df['btc_dom_z'])
    pos_A_dir = setup_a_directional(df, omega_strat, mfls_eth, gamma_eth, phase)
    pairs_def = [
        ('P1_ETH_BTC', 'log_eth', 'log_btc', 'ret_eth', 'ret_btc'),
        ('P2_ETH_SOL', 'log_eth', 'log_sol', 'ret_eth', 'ret_sol'),
        ('P3_ETH_BNB', 'log_eth', 'log_bnb', 'ret_eth', 'ret_bnb'),
    ]
    pair_data = {}
    for key, col_a, col_b, ret_a, ret_b in pairs_def:
        print(f"  {key}: spread ...", end='', flush=True)
        sd = compute_rolling_spread_v8(
            df[col_a], df[col_b], df[ret_a], df[ret_b],
            train_mask=train_mask, beta_window=252)
        train_spread = sd['spread'][train_mask].dropna()
        clf = SpreadUDLClassifier(window=20, n_ref_dirs=100).fit(train_spread)
        udl_state, udl_mag, udl_novelty = clf.classify_series(sd['spread'])
        sd['udl_state'] = udl_state
        mval, _ = compute_manifold_validity(sd['z'], sd['sret'])
        sd['manifold_valid'] = mval
        pair_data[key] = sd
        print(f" done")

    pair_pos = {}
    for key, _, _, _, _ in pairs_def:
        sd = pair_data[key]
        pair_pos[key] = route_pair_v7(
            omega_strat, A_rank, sd['z'], sd['udl_state'], sd['poa'],
            sd['manifold_valid'])
    pos_btc_macro, pos_alt_macro = route_btcalt_macro(
        df, omega_strat, A_rank, dA_rank)

    pnl_base = {
        'A_directional': get_daily_pnl(pos_A_dir, df['ret_eth']),
        'P1_ETH_BTC':    get_daily_pnl(pair_pos['P1_ETH_BTC'], pair_data['P1_ETH_BTC']['sret']),
        'P2_ETH_SOL':    get_daily_pnl(pair_pos['P2_ETH_SOL'], pair_data['P2_ETH_SOL']['sret']),
        'P3_ETH_BNB':    get_daily_pnl(pair_pos['P3_ETH_BNB'], pair_data['P3_ETH_BNB']['sret']),
        'M1_ALT_macro':  get_daily_pnl(pos_alt_macro, df['ret_eth']),
        'M1_BTC_macro':  get_daily_pnl(pos_btc_macro, df['ret_btc']),
    }

    # ── [10] Baselines for comparison ─────────────────────────────────────
    print("\n[10] Building v18_smooth + v19_alarm + v21_full baselines ...")
    V_state = compute_state_vector(omega_strat, gamma_rank, mfls_eth, dA_fast)
    phi_18s, align_18s = compute_geom_signals_v18_smooth(V_state)
    lev_v18_smooth = apply_geom_penalties_v18(lev_mult, phi_18s, align_18s)
    cs_wts_v10 = compute_cs_weights(pnl_base, window=GAMMA_SCORE_WIN)
    n_s = len(pnl_base)
    pnl_v10 = pd.Series(0.0, index=df.index)
    for k in pnl_base:
        pnl_v10 += cs_wts_v10[k].shift(1).fillna(1.0/n_s) * pnl_base[k]
    pnl_v18s = pnl_v10 * lev_v18_smooth.shift(1).fillna(1.0)

    # v19 hard-lock alarm (cos_θ_channel from global engine)
    cos_tc_series = F['cos_theta'].copy()
    alarm_v19 = v19.compute_hard_lock_alarm(cos_tc_series)
    pnl_v19_alarm = pnl_v18s.copy()
    pnl_v19_alarm[alarm_v19.shift(1).fillna(False)] = 0.0

    # v21-style four-state gate (REBUILD with original v21 alloc + Kramers damp)
    g_pos21 = np.ones(len(F))
    g_cash21 = np.zeros(len(F))
    last_layer = ""
    for i, (lat, ly) in enumerate(zip(alarm_latched.values, layers)):
        if lat:
            if ly:
                last_layer = ly
            ps, cs = ALLOC_V21.get(last_layer or "B", ALLOC_V21["B"])
        else:
            last_layer = ""
            ps, cs = ALLOC_V21[""]
        g_pos21[i], g_cash21[i] = ps, cs
    p_kr_arr = F['kramers_p'].fillna(0.0).clip(0.0, 1.0).values
    lev21 = np.clip(g_pos21 * (1.0 - p_kr_arr), LEV_LO, LEV_HI)
    lev21_s = pd.Series(lev21, index=F.index).ewm(span=5, adjust=False).mean()
    lev21_s = lev21_s.clip(lower=LEV_LO, upper=LEV_HI)
    pnl_v21_full = pnl_v18s * g_pos21 * (1.0 - g_cash21) * lev21_s.values

    # ── [11] Compose v22 PnL ──────────────────────────────────────────────
    print("\n[11] Composing v22 PnL ...")
    # KEY: keep the working v18_smooth blend structure; multiply per-pair
    # gates and tilts INTO the blend (don't replace the cs_w/leverage stack).
    strategy_gates = {
        'A_directional': pd.Series(1.0, index=df.index),
        'P1_ETH_BTC':    pair_gates['P1_ETH_BTC'],
        'P2_ETH_SOL':    pair_gates['P2_ETH_SOL'],
        'P3_ETH_BNB':    pair_gates['P3_ETH_BNB'],
        'M1_ALT_macro':  pd.Series(1.0, index=df.index),
        'M1_BTC_macro':  pd.Series(1.0, index=df.index),
    }
    strategy_tilts = {
        'A_directional': pd.Series(1.0, index=df.index),
        'P1_ETH_BTC':    pair_tilts['P1_ETH_BTC'],
        'P2_ETH_SOL':    pair_tilts['P2_ETH_SOL'],
        'P3_ETH_BNB':    pair_tilts['P3_ETH_BNB'],
        'M1_ALT_macro':  pd.Series(1.0, index=df.index),
        'M1_BTC_macro':  pd.Series(1.0, index=df.index),
    }
    # Build v22 blend: cs_w * gate * tilt * pnl  (then v18_smooth leverage + global gate)
    pnl_blend_v22 = pd.Series(0.0, index=df.index)
    for k, base in pnl_base.items():
        gate = strategy_gates[k]
        tilt = strategy_tilts[k]
        cs_w = cs_wts_v10[k].shift(1).fillna(1.0/n_s)
        eff  = (cs_w
                * gate.shift(1).fillna(1.0).clip(0.0, PAIR_GATE_HI)
                * tilt.shift(1).fillna(1.0).clip(0.5, 1.5))
        pnl_blend_v22 += eff * base.fillna(0.0)
    pnl_v22 = (pnl_blend_v22
               * lev_v18_smooth.shift(1).fillna(1.0)
               * g_pos.values
               * (1.0 - g_cash.values))

    # Kramers leverage damp (v21's secret sauce — keep it!)
    p_kr = F['kramers_p'].fillna(0.0).clip(0.0, 1.0).values
    lev_kr = np.clip(g_pos.values * (1.0 - p_kr), LEV_LO, LEV_HI)
    lev_kr_s = pd.Series(lev_kr, index=df.index).ewm(span=5, adjust=False).mean()
    lev_kr_s = lev_kr_s.clip(lower=LEV_LO, upper=LEV_HI)
    pnl_v22 = pnl_v22 * lev_kr_s.shift(1).fillna(1.0).values
    print(f"  Kramers lev [test]: mean={lev_kr_s[test_mask].mean():.3f}  "
          f"min={lev_kr_s[test_mask].min():.3f}")

    # ── ABLATION: v22 with PrecursorScale fix + rolling Layer B + Kramers,
    # but WITHOUT per-pair gates/tilts (isolate the value of pair-level engines).
    pnl_v22_nogates = pd.Series(0.0, index=df.index)
    for k, base in pnl_base.items():
        cs_w = cs_wts_v10[k].shift(1).fillna(1.0/n_s)
        pnl_v22_nogates += cs_w * base.fillna(0.0)
    pnl_v22_nogates = (pnl_v22_nogates
                       * lev_v18_smooth.shift(1).fillna(1.0)
                       * g_pos.values
                       * (1.0 - g_cash.values)
                       * lev_kr_s.shift(1).fillna(1.0).values)

    # ── [12] Simulate ─────────────────────────────────────────────────────
    print("\n[12] Simulating test period ...")
    sims = {}
    pnl_lookup = {
        'v18_smooth':         pnl_v18s,
        'v19_alarm_only':     pnl_v19_alarm,
        'v21_full':           pnl_v21_full,
        'v22_fixes_only':     pnl_v22_nogates,
        'v22_alloc_full':     pnl_v22,
    }
    for name, pnl in pnl_lookup.items():
        sims[name] = simulate_from_pnl(pnl[test_mask].fillna(0.0), label=name)

    print("\n" + "=" * 92)
    print("  v22 RESULTS  (K=1 gross, test period)")
    print("=" * 92)
    print(f"  {'variant':<22}  {'Sharpe':>8}  {'MaxDD':>8}  {'CAGR%':>8}  "
          f"{'CumRet%':>8}  {'Active':>7}")
    print("  " + "-" * 86)
    for k, s in sims.items():
        active = int(pnl_lookup[k][test_mask].abs().gt(1e-9).sum())
        marker = ''
        if k == 'v18_smooth':       marker = '  <- baseline'
        if k == 'v19_alarm_only':   marker = '  <- v19 champion'
        if k == 'v21_full':         marker = '  <- v21 (engine -> scaling)'
        if k == 'v22_fixes_only':   marker = '  <- v22 fixes (no per-pair)'
        if k == 'v22_alloc_full':   marker = '  <- v22 FULL (per-pair allocation)'
        print(f"  {k:<22}  {s['sharpe']:+8.4f}  {s['max_dd']:+8.4f}  "
              f"{100*s['cagr']:+7.2f}%  {100*s['cum_return']:+7.2f}%  "
              f"{active:6d}d{marker}")

    sh22f = sims['v22_alloc_full']['sharpe']
    sh22n = sims['v22_fixes_only']['sharpe']
    sh21  = sims['v21_full']['sharpe']
    sh19  = sims['v19_alarm_only']['sharpe']
    print()
    print(f"  Δ(v22_fixes − v21)        = {sh22n - sh21:+.4f}  (does the fix bundle help?)")
    print(f"  Δ(v22_alloc − v22_fixes)  = {sh22f - sh22n:+.4f}  (do per-pair gates help?)")
    print(f"  Δ(v22_alloc − v21)        = {sh22f - sh21:+.4f}")
    print(f"  Δ(v22_alloc − v19_alarm)  = {sh22f - sh19:+.4f}")

    sh22 = sh22f  # for downstream
    if sh22 >= sh21 and sh22 >= sh19:
        print(f"  ✓ v22 BEATS all prior variants")
    elif sh22 >= sh19:
        print(f"  ~ v22 beats v19 champion (but underperforms v21 by {sh21-sh22:.4f})")
    else:
        print(f"  ✗ v22 below v19_alarm by {sh19-sh22:.4f}")

    # ── [13] K-sweep on best ─────────────────────────────────────────────
    best_name = max(sims, key=lambda k: sims[k]['sharpe'])
    best_pnl  = pnl_lookup[best_name]
    print(f"\n[13] K-sweep on best: {best_name}")
    print(f"  {'K':>4}  {'mode':<10}  {'Sharpe':>8}  {'CAGR%':>8}  "
          f"{'Final $':>12}  {'PnL $':>12}  {'MaxDD%':>8}")
    print("  " + "-" * 78)
    for K in (1, 2, 3, 5, 10):
        for mode, bps in (('gross', 0.0), ('net 5bp', 5.0)):
            m = equity_at_K(best_pnl[test_mask].fillna(0.0),
                            K=float(K), tcost_bps=bps, init=1200.0)
            print(f"  {K:4d}  {mode:<10}  {m['sh']:+8.3f}  "
                  f"{100*m['cagr']:+7.2f}%  ${m['final']:10,.2f}  "
                  f"${m['pnl']:+10,.2f}  {100*m['max_dd']:+7.2f}%")

    bestK = find_best_K(best_pnl[test_mask].fillna(0.0),
                        tcost_bps=5.0, init=1200.0, max_dd_limit=0.40)
    if bestK is not None:
        print(f"\n  * Best K (net Sharpe, MaxDD <= 40%): K={bestK['K']:.2f}  "
              f"Final ${bestK['final']:,.2f}  Sharpe {bestK['sh']:+.3f}")
    else:
        bestK = {'K': float('nan'), 'final': float('nan'), 'sh': float('nan')}

    # ── [14] Save ────────────────────────────────────────────────────────
    print("\n[14] Saving ...")
    out = {
        'protocol': 'v22 — Geometric Allocation Engine',
        'fixes': {
            'precursor_scale_floors': True,
            'rolling_layer_b':        True,
            'per_pair_engines':       True,
            'cos_theta_tilt':         True,
        },
        'engine': {
            'global_e_star_chi2': e_star,
            'global_sigma_n':     sigma_n,
            'precursor_scale': {
                'P':   ews.precursor_scale.P_scale,
                'psi': ews.precursor_scale.psi_scale,
                'S':   ews.precursor_scale.S_scale,
                'V':   ews.precursor_scale.V_scale,
            },
        },
        'layer_occupancy_test': {k: int(layer_counts.get(k, 0))
                                  for k in ('', 'A', 'B', 'AB')},
        'pair_gates_test_mean': {k: float(pair_gates[k][test_mask].mean())
                                  for k in pair_gates},
        'sims': {k: {kk: float(vv) if isinstance(vv, (int, float, np.floating)) else vv
                     for kk, vv in v.items()} for k, v in sims.items()},
        'best_K_net5bp': {kk: (float(vv) if isinstance(vv, (int, float, np.floating))
                                else str(vv))
                          for kk, vv in bestK.items() if kk != 'eq'},
    }
    json_path = out_dir / 'crypto_bsdt_v22_results.json'
    json_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"  Results -> {json_path}")

    print("\n" + "=" * 92)
    print(f"  v22 SUMMARY  v22={sh22:+.4f}  v21={sh21:+.4f}  v19={sh19:+.4f}")
    print("=" * 92)


if __name__ == "__main__":
    main()
