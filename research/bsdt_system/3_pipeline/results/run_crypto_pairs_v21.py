"""
Crypto BSDT v21 — Frozen-Normal-Window Two-Layer EWS Allocator
================================================================

Strict adherence to the canonical SIAM §7 frozen-normal protocol used by
`research/adaptive-friction/run_frozen_normal_simulation.py`.

PRIMARY ENGINE (the physics):
    MasterOperator.calibrate(X_normal)   ── frozen, never re-fit
    LedoitWolfNetwork.from_panel(...)
    CollapseGeometry(op=M)               ── §XIV three conditions (diagnostic)
    LyapunovCertificate(op=M)            ── §XVI Pt, dV/dt, margin
    InformationGeometry(op=M)            ── §XXIII χ² threshold
    EarlyWarning(op=M, geom=geom)        ── §XVII Layer B + §XVI.6 Layer A
    PrecursorScale.from_panel(M, X_normal) ── self-calibrated Layer A scale

ALARM (canonical two-layer):
    tl = ews.two_layer(snap, net, snap_prev, e_star, geometry_threshold)
       Layer A : precursor (leading, normalised vs P95 of normal window)
       Layer B : geometry (confirming, μ_normal + 2σ_normal threshold)
    tl["layer"] ∈ {"", "A", "B", "AB"}  → routes the allocator

CLOSED-FORM AUGMENTS (only when alarm asks):
    StochasticExtension.cross_probability   §XIX Kramers     → leverage damp
    LyapunovCertificate.channel_decomposition §XXV           → family tilt
    CollapseGeometry.{spectral,angular,energetic}_condition  → explainability

ALLOCATOR (four-state from the two-layer alarm):
    layer == ""    : full risk           (positions × 1.0,    cash 0%)
    layer == "A"   : light de-risking    (positions × 0.7,   cash 30%)
    layer == "B"   : heavy de-risking    (positions × 0.4,   cash 60%)
    layer == "AB"  : full cash           (positions × 0.0,   cash 100%)
    Leverage further damped by §XIX Kramers prob:  lev = lev_state × (1 − P_kramers)
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

# UTF-8 stdout on Windows so box-drawing characters survive cp1252.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── reuse v19 data + strategy stack verbatim ─────────────────────────────
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
    _build_state_panel, _CG_ASSETS,
    TRAIN_START, TRAIN_END, TEST_START, OUT_DIR,
    GAMMA_SCORE_WIN, ALARM_MIN_STEPS,
)

# ── canonical engine import (full §I–XXVII arsenal) ──────────────────────
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
#   v21 PARAMETERS
# ═══════════════════════════════════════════════════════════════════════
HISTORY_LEN        = 20            # canonical default (matches FDIC=12, ERCOT=8)
ALPHA_CONF         = 0.01          # §XXIII confidence (1% normal-period FPR)
N_SIGMA_THRESHOLD  = 2.0           # Layer B = μ_normal + 2σ_normal
ALARM_LATCH_DAYS   = 2             # 2-day persistence latch (same as v19)

# Four-state allocator weights:  (positions_scale, cash_share)
ALLOC_BY_LAYER = {
    "":   (1.00, 0.00),   # all-clear — full risk
    "A":  (0.70, 0.30),   # precursor only — light de-risking
    "B":  (0.40, 0.60),   # geometry only  — heavy de-risking
    "AB": (0.00, 1.00),   # both layers    — full cash
}

KRAMERS_TAU        = 5.0           # §XIX forward horizon (days)
SIGMA_N_FALLBACK   = 1e-2

LEV_LO             = 0.20
LEV_HI             = 1.15


# ═══════════════════════════════════════════════════════════════════════
#   PHASE A — Calibrate frozen engine on normal window
# ═══════════════════════════════════════════════════════════════════════
def calibrate_frozen_engine(X_panel: np.ndarray, train_mask: np.ndarray):
    """One-shot calibration on the frozen normal window (no lookahead).

    Mirrors `frozen_normal_scan` lines 78–103 exactly.

    Returns
    -------
    M           : calibrated MasterOperator (FROZEN — never re-fit)
    net         : LedoitWolfNetwork
    geom        : CollapseGeometry
    lyap        : LyapunovCertificate
    info        : InformationGeometry
    ews         : EarlyWarning with self-calibrated PrecursorScale
    e_star      : float (§XXIII χ² threshold)
    sigma_n     : float (§XIX noise scale)
    """
    X_normal = X_panel[train_mask]
    T0, N, d = X_normal.shape
    print(f"  [v21] Frozen normal window: {T0} days × {N} agents × {d} dims")

    M    = MasterOperator.calibrate(X_normal, k=min(4, d), theta=1.0)
    net  = LedoitWolfNetwork.from_panel(X_normal[..., 0])
    info = InformationGeometry(op=M)
    e_star = float(info.chi2_threshold(N, d, alpha_conf=ALPHA_CONF))

    geom = CollapseGeometry(op=M)
    lyap = LyapunovCertificate(op=M)
    ews  = EarlyWarning(op=M, geom=geom)
    ews.precursor_scale = PrecursorScale.from_panel(M, X_normal)

    print(f"  [v21] e* (χ²)        = {e_star:.4f}")
    print(f"  [v21] PrecursorScale : P={ews.precursor_scale.P_scale:.4f}  "
          f"ψ={ews.precursor_scale.psi_scale:.4f}  "
          f"S={ews.precursor_scale.S_scale:.4f}  "
          f"V={ews.precursor_scale.V_scale:.4f}")

    # σ_n for Kramers — residual after applying frozen operator on the train panel
    residuals = []
    for t in range(1, T0):
        snap = Snapshot(
            X=X_normal[t], X_prev=X_normal[t-1],
            history=X_normal[max(0, t-HISTORY_LEN):t],
        )
        try:
            F  = M.force(snap)
            dX = X_normal[t] - X_normal[t-1]
            residuals.append(np.linalg.norm(dX - F))
        except Exception:
            pass
    sigma_n = float(np.std(residuals)) if residuals else SIGMA_N_FALLBACK
    sigma_n = max(sigma_n, 1e-3)
    print(f"  [v21] σ_n (Kramers)  = {sigma_n:.4f}")

    return M, net, geom, lyap, info, ews, e_star, sigma_n


# ═══════════════════════════════════════════════════════════════════════
#   PHASE B — Self-calibrate Layer-B threshold from frozen normal window
# ═══════════════════════════════════════════════════════════════════════
def calibrate_layer_b_threshold(X_panel, train_mask, ews, net,
                                history_len=HISTORY_LEN,
                                n_sigma=N_SIGMA_THRESHOLD):
    """Layer-B EWS threshold = μ_normal + n·σ_normal of ews.score over the
    frozen normal window.  Mirrors `frozen_normal_scan` lines 110–123.
    """
    train_idx = np.where(train_mask)[0]
    normal_ews = []
    for t in train_idx:
        if t == 0:
            continue
        snap = Snapshot(
            X=X_panel[t], X_prev=X_panel[t-1],
            history=X_panel[max(0, t-history_len):t],
        )
        try:
            normal_ews.append(ews.score(snap, net))
        except Exception:
            pass
    mu_n = float(np.nanmean(normal_ews)) if normal_ews else 0.0
    sd_n = float(np.nanstd(normal_ews))  if normal_ews else 1.0
    if sd_n < 1e-10:
        sd_n = 1e-10
    threshold = mu_n + n_sigma * sd_n
    print(f"  [v21] Layer B EWS    : μ={mu_n:.4f}  σ={sd_n:.4f}  "
          f"→ threshold(μ+{n_sigma:.0f}σ)={threshold:.4f}")
    return threshold, mu_n, sd_n


# ═══════════════════════════════════════════════════════════════════════
#   PHASE C — Roll forward emitting two-layer alarm + diagnostics
# ═══════════════════════════════════════════════════════════════════════
def emit_two_layer_alarm(df, X_panel, train_mask, M, net, geom, lyap, ews,
                         e_star, sigma_n, geometry_threshold,
                         history_len=HISTORY_LEN):
    """For every day t emit:

      Primary (canonical engine):
        layer            "" / "A" / "B" / "AB"
        alarm            bool  (any layer fired)
        geom_score       Layer B ews.score
        precursor_score  Layer A normalised score
      Augments (closed-form, diagnostic-only):
        kramers_p        §XIX  forward 5-day Kramers crossing prob
        cond_count       §XIV  number of geometric conditions firing
        attr_C/G/A/T     §XXV  per-channel attribution
        Pt               §XVI  Lyapunov power
        margin           §XV.4 stability margin

    Returns a pd.DataFrame indexed by df.index.
    """
    T = len(df)
    stoch = StochasticExtension(op=M, lyap=lyap, sigma_n=sigma_n)

    rows = []
    t0 = time.time()
    for t in range(2, T):    # need t-2 for snap_prev
        snap = Snapshot(
            X=X_panel[t], X_prev=X_panel[t-1],
            history=X_panel[max(0, t-history_len):t],
        )
        snap_prev = Snapshot(
            X=X_panel[t-1], X_prev=X_panel[t-2],
            history=X_panel[max(0, t-1-history_len):t-1],
        )
        try:
            tl = ews.two_layer(snap, net, snap_prev, e_star,
                               geometry_threshold=geometry_threshold)
            geom_score = float(tl["geometry_score"])
            pre_score  = float(tl["precursor_score"])
            layer_str  = tl["layer"] or ""
            alarm      = bool(tl["alarm"])

            # closed-form augments (cheap; eval only when needed downstream)
            cond = geom.all_conditions(snap)
            cond_n = int(cond["spectral"]) + int(cond["angular"]) + int(cond["energetic"])

            try:
                p_kr = float(stoch.cross_probability(
                    snap, e_star=e_star, tau=KRAMERS_TAU, dt=1e-2))
            except Exception:
                p_kr = 0.0

            try:
                cd = lyap.channel_decomposition(snap)
                a_C = float(cd['C']['attribution'])
                a_G = float(cd['G']['attribution'])
                a_A = float(cd['A']['attribution'])
                a_T = float(cd['T']['attribution'])
            except Exception:
                a_C = a_G = a_A = a_T = 0.25

            try:
                Pt = float(lyap._bundle(snap)["Pt"])
            except Exception:
                Pt = 0.0
            try:
                margin = float(lyap.margin(snap))
            except Exception:
                margin = 0.0

            rows.append((t, layer_str, int(alarm), geom_score, pre_score,
                         cond_n, p_kr, a_C, a_G, a_A, a_T, Pt, margin))
        except Exception:
            pass

        if (t % 200) == 0:
            print(f"    t={t}/{T}  ({time.time()-t0:.1f}s)")

    print(f"  [v21] Two-layer sweep complete ({time.time()-t0:.1f}s, "
          f"{len(rows)}/{T} days)")

    cols = ['t_idx', 'layer', 'alarm_raw', 'geom_score', 'precursor_score',
            'cond_count', 'kramers_p',
            'attr_C', 'attr_G', 'attr_A', 'attr_T', 'Pt', 'margin']
    F = pd.DataFrame(rows, columns=cols).set_index('t_idx')
    F.index = df.index[F.index]
    F = F.reindex(df.index)
    F['layer'] = F['layer'].fillna('')
    F['alarm_raw'] = F['alarm_raw'].fillna(0).astype(int)
    return F


# ═══════════════════════════════════════════════════════════════════════
#   PHASE D — 2-day persistence latch on the two-layer alarm
# ═══════════════════════════════════════════════════════════════════════
def apply_alarm_latch(F, min_steps=ALARM_LATCH_DAYS):
    """Latch the alarm: requires `min_steps` consecutive fire days, then
    stays latched until a clear-day arrives (matches v19)."""
    raw = F['alarm_raw'].astype(int)
    roll = raw.rolling(min_steps, min_periods=min_steps).sum()
    alarm_arm = (roll >= min_steps).fillna(False).values
    raw_arr   = raw.values
    out = np.zeros(len(F), dtype=bool)
    latched = False
    for i in range(len(F)):
        if alarm_arm[i]:
            latched = True
        if latched and raw_arr[i] == 0:
            latched = False
        out[i] = latched
    return pd.Series(out, index=F.index, name='alarm_latched')


# ═══════════════════════════════════════════════════════════════════════
#   PHASE E — Four-state allocator + Kramers-damped leverage
# ═══════════════════════════════════════════════════════════════════════
def compute_state_allocation(F, alarm_latched,
                             alloc=ALLOC_BY_LAYER,
                             lev_lo=LEV_LO, lev_hi=LEV_HI):
    """For each day map (latched alarm × layer) → (pos_scale, cash_share, lev).

    Latched-alarm days carry the latched layer (so re-arm on AB stays AB).
    """
    layers = F['layer'].fillna('').values
    pos_scale = np.ones(len(F))
    cash_w    = np.zeros(len(F))
    last_layer = ""
    for i, (lat, ly) in enumerate(zip(alarm_latched.values, layers)):
        if lat:
            # use the latched-in layer or fall back to current if blank
            if ly:
                last_layer = ly
            ps, cs = alloc.get(last_layer or "B", alloc["B"])
        else:
            last_layer = ""
            ps, cs = alloc[""]
        pos_scale[i] = ps
        cash_w[i]    = cs

    p_kr = F['kramers_p'].fillna(0.0).clip(0.0, 1.0).values
    lev  = np.clip(pos_scale * (1.0 - p_kr), lev_lo, lev_hi)
    # smooth jitter
    lev = pd.Series(lev, index=F.index).ewm(span=5, adjust=False).mean()
    lev = lev.clip(lower=lev_lo, upper=lev_hi)

    return (pd.Series(pos_scale, index=F.index, name='pos_scale'),
            pd.Series(cash_w,    index=F.index, name='cash_w'),
            lev)


# ═══════════════════════════════════════════════════════════════════════
#   PHASE F — Compose final v21 PnL
# ═══════════════════════════════════════════════════════════════════════
def compose_v21_pnl(pnl_v18s, pos_scale, cash_w, lev):
    """v21 PnL = v18_smooth daily PnL × pos_scale × leverage (cash earns 0).

    Single-blender variant — the four-state allocator already captures the
    routing, so we don't need a separate family tilt or perf-feedback overlay
    for the canonical version (those become ablations).
    """
    base = pnl_v18s.fillna(0.0)
    risk_w = (1.0 - cash_w).clip(lower=0.0, upper=1.0)
    out = base * pos_scale.values * risk_w.values * lev.values
    return pd.Series(out.values, index=base.index, name='v21_full')


# ═══════════════════════════════════════════════════════════════════════
#   MAIN
# ═══════════════════════════════════════════════════════════════════════
def main():
    out_dir = Path(OUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 92)
    print("  CRYPTO BSDT v21 — Frozen-Normal Two-Layer EWS Allocator")
    print("  Canonical SIAM §7 protocol — frozen calibration · two-layer alarm")
    print("=" * 92)

    # ── [1] Data + features (verbatim v20 setup) ─────────────────────────
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

    # ── [2] Legacy BSDT signals (v18_smooth baseline + v19 alarm) ────────
    print("\n[2] Computing BSDT signals (legacy) ...")
    feats_strat = ['ret_eth_z', 'ret_btc_z', 'ret_sol_z', 'ret_bnb_z',
                   'vol_eth_z', 'vol_btc_z', 'btc_dom_z', 'cross_disp_z']
    feats_ext   = feats_strat + ['ret_spx_z', 'dvix_z', 'ret_dxy_z']
    omega_strat, mfls_eth, gamma_eth = compute_bsdt(df, feats_strat, window=60)
    omega_ext,   _,        _         = compute_bsdt(df, feats_ext,   window=60)
    A_eth, A_rank, dA_fast, dA_rank  = compute_activity_signals(mfls_eth, gamma_eth)
    gamma_rank = compute_gamma_rank(omega_ext, min_periods=60)
    lev_mult   = compute_leverage_dial(gamma_rank)

    # ── [3] Build (T, N=4, d=2) state panel ──────────────────────────────
    print("\n[3] Building (T, N=4, d=2) state panel ...")
    X_panel = _build_state_panel(df)
    print(f"  Panel shape: {X_panel.shape}")

    # ── [4] Frozen-normal calibration (canonical §7 protocol) ────────────
    print("\n[4] Calibrating frozen MasterOperator + two-layer EWS ...")
    train_mask_arr = train_mask.values if hasattr(train_mask, 'values') else np.asarray(train_mask)
    M, net, geom, lyap, info, ews, e_star, sigma_n = calibrate_frozen_engine(
        X_panel, train_mask_arr)

    # ── [5] Self-calibrate Layer-B threshold on normal window ────────────
    print("\n[5] Self-calibrating Layer-B threshold (μ + 2σ of normal EWS) ...")
    geom_thresh, mu_n, sd_n = calibrate_layer_b_threshold(
        X_panel, train_mask_arr, ews, net)

    # ── [6] Two-layer alarm sweep over the full timeline ─────────────────
    print("\n[6] Rolling two-layer alarm forward ...")
    F = emit_two_layer_alarm(df, X_panel, train_mask_arr, M, net, geom, lyap, ews,
                             e_star, sigma_n, geom_thresh)

    F_test = F[test_mask]
    print(f"\n  Test period diagnostics ({len(F_test)} days):")
    layer_counts = F_test['layer'].value_counts().to_dict()
    for k in ('', 'A', 'B', 'AB'):
        cnt = layer_counts.get(k, 0)
        print(f"    layer='{k or '<clear>':7s}': {cnt:4d} days  "
              f"({100*cnt/max(len(F_test),1):.1f}%)")
    print(f"    geom_score   : mean={F_test['geom_score'].mean():.4f}  "
          f"max={F_test['geom_score'].max():.4f}  thresh={geom_thresh:.4f}")
    print(f"    precursor    : mean={F_test['precursor_score'].mean():.4f}  "
          f"max={F_test['precursor_score'].max():.4f}  thresh=1.000")
    print(f"    Kramers P    : mean={F_test['kramers_p'].mean():.4f}  "
          f"max={F_test['kramers_p'].max():.4f}")

    # ── [7] Latch alarm + four-state allocation ──────────────────────────
    print("\n[7] Latching alarm + computing four-state allocation ...")
    alarm_latched = apply_alarm_latch(F, min_steps=ALARM_LATCH_DAYS)
    pos_scale, cash_w, lev = compute_state_allocation(F, alarm_latched)
    print(f"  Alarm latched days [test]: {int(alarm_latched[test_mask].sum())} / "
          f"{int(test_mask.sum())} "
          f"({100*alarm_latched[test_mask].mean():.1f}%)")
    print(f"  pos_scale [test]: mean={pos_scale[test_mask].mean():.3f}  "
          f"min={pos_scale[test_mask].min():.3f}")
    print(f"  cash_w    [test]: mean={cash_w[test_mask].mean():.3f}")
    print(f"  leverage  [test]: mean={lev[test_mask].mean():.3f}  "
          f"min={lev[test_mask].min():.3f}  max={lev[test_mask].max():.3f}")

    # ── [8] Build base strategies (verbatim v20) ─────────────────────────
    print("\n[8] Building strategy positions (reuse v19) ...")
    ret7  = df['ret_eth'].rolling(7).sum()
    ret3  = df['ret_eth'].rolling(3).sum()
    phase = detect_phase(omega_strat, ret7, ret3, df['btc_dom_z'])
    pos_A_dir = setup_a_directional(df, omega_strat, mfls_eth, gamma_eth, phase)
    pairs = [
        ('P1_ETH_BTC', 'log_eth', 'log_btc', 'ret_eth', 'ret_btc'),
        ('P2_ETH_SOL', 'log_eth', 'log_sol', 'ret_eth', 'ret_sol'),
        ('P3_ETH_BNB', 'log_eth', 'log_bnb', 'ret_eth', 'ret_bnb'),
    ]
    pair_data = {}
    for key, col_a, col_b, ret_a, ret_b in pairs:
        print(f"  {key}: computing spread ...", end='', flush=True)
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
    for key, _, _, _, _ in pairs:
        sd = pair_data[key]
        pair_pos[key] = route_pair_v7(
            omega_strat, A_rank, sd['z'], sd['udl_state'], sd['poa'],
            sd['manifold_valid'])
    pos_btc_macro, pos_alt_macro = route_btcalt_macro(df, omega_strat, A_rank, dA_rank)

    pnl_base = {
        'A_directional': get_daily_pnl(pos_A_dir, df['ret_eth']),
        'P1_ETH_BTC':    get_daily_pnl(pair_pos['P1_ETH_BTC'], pair_data['P1_ETH_BTC']['sret']),
        'P2_ETH_SOL':    get_daily_pnl(pair_pos['P2_ETH_SOL'], pair_data['P2_ETH_SOL']['sret']),
        'P3_ETH_BNB':    get_daily_pnl(pair_pos['P3_ETH_BNB'], pair_data['P3_ETH_BNB']['sret']),
        'M1_ALT_macro':  get_daily_pnl(pos_alt_macro, df['ret_eth']),
        'M1_BTC_macro':  get_daily_pnl(pos_btc_macro, df['ret_btc']),
    }

    # v18_smooth baseline
    V_state = compute_state_vector(omega_strat, gamma_rank, mfls_eth, dA_fast)
    phi_18s, align_18s = compute_geom_signals_v18_smooth(V_state)
    lev_v18_smooth = apply_geom_penalties_v18(lev_mult, phi_18s, align_18s)
    cs_wts_v10 = compute_cs_weights(pnl_base, window=GAMMA_SCORE_WIN)
    n_s = len(pnl_base)
    pnl_v10 = pd.Series(0.0, index=df.index)
    for k in pnl_base:
        pnl_v10 += cs_wts_v10[k].shift(1).fillna(1.0/n_s) * pnl_base[k]
    pnl_v18s = pnl_v10 * lev_v18_smooth.shift(1).fillna(1.0)

    # v19_alarm_only champion (cos_θC hard-lock)
    cos_tc_v19 = F['geom_score'].copy()  # use whatever cosine signal we have
    # use v19's actual alarm builder on the v19 channel cosine
    # (rebuild via v19 directly on the channel cosine signal it expects)
    from collapse_geometry import CollapseGeometry as _CG
    _geom_diag = _CG(op=M)
    cos_tc_series = pd.Series(np.nan, index=df.index)
    for t in range(2, len(df)):
        snap = Snapshot(X=X_panel[t], X_prev=X_panel[t-1],
                        history=X_panel[max(0,t-HISTORY_LEN):t])
        try:
            cos_tc_series.iloc[t] = float(_geom_diag.cos_theta_channel(snap))
        except Exception:
            pass
    alarm_v19 = v19.compute_hard_lock_alarm(cos_tc_series)
    pnl_v19_alarm = pnl_v18s.copy()
    pnl_v19_alarm[alarm_v19.shift(1).fillna(False)] = 0.0

    # ── [9] Compose v21 PnL (frozen-normal two-layer allocator) ──────────
    print("\n[9] Composing v21 PnL ...")
    pnl_v21 = compose_v21_pnl(pnl_v18s, pos_scale, cash_w, lev)

    # ── [10] Simulate test period ────────────────────────────────────────
    print("\n[10] Simulating test period ...")
    sims = {}
    for name, pnl in (('v18_smooth', pnl_v18s),
                      ('v19_alarm_only', pnl_v19_alarm),
                      ('v21_full', pnl_v21)):
        s = simulate_from_pnl(pnl[test_mask].fillna(0.0), label=name)
        sims[name] = s

    # ── [11] Print results ───────────────────────────────────────────────
    print("\n" + "=" * 92)
    print("  v21 RESULTS  (K=1 gross, test period)")
    print("=" * 92)
    print(f"  {'variant':<25}  {'Sharpe':>8}  {'MaxDD':>8}  {'CAGR%':>8}  "
          f"{'CumRet%':>8}  {'Active':>7}")
    print("  " + "─" * 86)
    pnl_lookup = {'v18_smooth': pnl_v18s, 'v19_alarm_only': pnl_v19_alarm, 'v21_full': pnl_v21}
    for k, s in sims.items():
        active_days = int(pnl_lookup[k][test_mask].abs().gt(1e-9).sum())
        marker = ''
        if k == 'v18_smooth':       marker = '  ← published baseline'
        if k == 'v19_alarm_only':   marker = '  ← v19 champion'
        if k == 'v21_full':         marker = '  ← v21 FULL'
        print(f"  {k:<25}  {s['sharpe']:+8.4f}  {s['max_dd']:+8.4f}  "
              f"{100*s['cagr']:+7.2f}%  {100*s['cum_return']:+7.2f}%  "
              f"{active_days:6d}d{marker}")

    sh21 = sims['v21_full']['sharpe']
    sh19 = sims['v19_alarm_only']['sharpe']
    print()
    print(f"  Δ(v21 − v19_alarm) Sharpe = {sh21 - sh19:+.4f}")
    if sh21 >= sh19:
        print(f"  ✓ v21 BEATS v19_alarm champion")
    else:
        print(f"  ✗ v21 below v19_alarm by {sh19-sh21:.4f}")

    # ── [12] K-sweep on best variant ─────────────────────────────────────
    best_name = max(sims, key=lambda k: sims[k]['sharpe'])
    best_pnl  = pnl_lookup[best_name]
    print(f"\n[12] K-sweep on best variant: {best_name}")
    print(f"  {'K':>6}  {'mode':<10}  {'Sharpe':>8}  {'CAGR%':>8}  "
          f"{'Final $':>12}  {'PnL $':>12}  {'MaxDD%':>8}")
    print("  " + "─" * 78)
    from run_crypto_pairs_v19 import equity_at_K
    for K in (1, 2, 3, 5, 10):
        for mode, bps in (('gross', 0.0), ('net 5bp', 5.0)):
            m = equity_at_K(best_pnl[test_mask].fillna(0.0), K=float(K), tcost_bps=bps, init=1200.0)
            print(f"  {K:6d}  {mode:<10}  {m['sh']:+8.3f}  "
                  f"{100*m['cagr']:+7.2f}%  ${m['final']:10,.2f}  "
                  f"${m['pnl']:+10,.2f}  {100*m['max_dd']:+7.2f}%")

    bestK = find_best_K(best_pnl[test_mask].fillna(0.0), tcost_bps=5.0, init=1200.0, max_dd_limit=0.40)
    if bestK is not None:
        print(f"\n  ★ Best K (net Sharpe, MaxDD ≤ 40%): K={bestK['K']:.2f}  "
              f"Final ${bestK['final']:,.2f}  Sharpe {bestK['sh']:+.3f}")
    else:
        print("\n  ★ Best K: none satisfies MaxDD constraint")
        bestK = {'K': float('nan'), 'final': float('nan'), 'sh': float('nan')}

    # ── [13] Save ─────────────────────────────────────────────────────────
    print("\n[13] Saving ...")
    json_path = out_dir / 'crypto_bsdt_v21_results.json'
    out = {
        'protocol': 'frozen-normal SIAM §7',
        'train': {'start': str(TRAIN_START), 'end': str(TRAIN_END),
                  'days': int(train_mask.sum())},
        'test':  {'start': str(TEST_START),  'end': str(df.index[-1].date()),
                  'days': int(test_mask.sum())},
        'engine': {
            'e_star_chi2':      e_star,
            'sigma_n':          sigma_n,
            'precursor_scale': {
                'P': ews.precursor_scale.P_scale,
                'psi': ews.precursor_scale.psi_scale,
                'S': ews.precursor_scale.S_scale,
                'V': ews.precursor_scale.V_scale,
            },
            'layer_b_threshold':   geom_thresh,
            'layer_b_normal_mu':   mu_n,
            'layer_b_normal_sd':   sd_n,
        },
        'layer_occupancy_test': {k: int(layer_counts.get(k, 0)) for k in ('', 'A', 'B', 'AB')},
        'alarm_latched_test_days': int(alarm_latched[test_mask].sum()),
        'sims': {k: {kk: float(vv) if isinstance(vv, (int, float, np.floating)) else vv
                     for kk, vv in v.items()} for k, v in sims.items()},
        'best_K_net5bp': {kk: (float(vv) if isinstance(vv, (int, float, np.floating)) else str(vv))
                          for kk, vv in bestK.items() if kk != 'eq'},
    }
    json_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"  Results → {json_path}")

    print("\n" + "=" * 92)
    print(f"  v21 SUMMARY  —  v21_full Sharpe {sh21:+.4f}  "
          f"vs v19_alarm {sh19:+.4f}  (Δ={sh21-sh19:+.4f})")
    print("=" * 92)


if __name__ == "__main__":
    main()
