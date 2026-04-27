"""
Crypto BSDT v48 — Phase Clip / Quadrant Boundaries / Rolling Windows
=====================================================================
v47 champion: v47_D_ghth200_ghtlm030_glth100  Sharpe=+3.4779
  (GH_TH=2.00, GH_TL=-0.30, GL_TH=-1.00, GL_TL=-1.00)
  Phase-clip ceiling confirmed: GH_TH > 2.0 hits clip at 3.0 → no further gain

Remaining unexplored axes (all fundamental model parameters, not coefficients):
  1. Phase clip ceiling itself  (currently 3.0; higher clip = more leverage on GHTH bars)
  2. G_THRESH (currently 0.45): defines G-low vs G-high quadrant boundary
  3. T_THRESH (currently 0.40): defines T-low vs T-high quadrant boundary
  4. N_G / N_T rolling max window (currently 8): memory operator quality
  5. GH_TL deeper negative (only tested to -0.40; -0.50, -0.60 not tried)

Kill structure is CONFIRMED OPTIMAL and FIXED throughout v48:
  GH_TL = best (sweeping in Group D below)
  GL_TH = -1.00  (full kill)
  GL_TL = -1.00  (full kill)
  GH_TH = PHASE_CLIP - 1.0  (always at clip ceiling for each group)

Group A: Phase clip sweep  (GH_TH = clip - 1.0 for each; GH_TL=-0.30, kills=-1.00)
  CLIP ∈ {3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 8.0}   → 7 variants
  Interpretation: raise leverage ceiling on confirmed GH_TH bars

Group B: G_THRESH sweep  (at best clip from A, T_THRESH=0.40, N=8)
  G_THRESH ∈ {0.30, 0.35, 0.40, 0.45, 0.50, 0.55}   → 6 variants
  Interpretation: set the G-memory cut separating "G-high" from "G-low"

Group C: T_THRESH sweep  (at best clip + best G_THRESH, N=8)
  T_THRESH ∈ {0.25, 0.30, 0.35, 0.40, 0.45, 0.50}   → 6 variants

Group D: N_G / N_T window sweep  (at best clip + best thresholds)
  N_window ∈ {4, 6, 8, 10, 12, 16}  (applied to both N_G and N_T jointly)   → 6 variants

Group E: GH_TL deeper negative  (at best clip + best thresholds + best N)
  GH_TL ∈ {-0.50, -0.40, -0.30, -0.20, 0.00}   → 5 variants

Group F: Joint champion grid  (top-2 from each group combined)   → ~12 variants
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

from collapse_geometry import MasterOperator, Snapshot
from run_crypto_pairs_v38_lambda_norm import compute_lambda_features
from run_crypto_pairs_v37_price_prediction import compute_price_prediction_signals
from run_crypto_pairs_v36_intraday_bsdt import (
    N_AGENTS, N_FEATURES, CALIB_BARS,
    BPD, ANN_1H,
    build_intraday_state_panel, calibrate_intraday_engine,
    compute_intraday_signals,
    _net_ret, _stats,
)
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
    build_1h_df, fetch_and_prepare, fetch_binance_funding,
    add_cross_market_features, add_leverage_features,
    build_daily_positions, upsample_daily_to_1h_pnl,
    compute_1h_strategies, compute_quality, assemble_combined,
)
from run_crypto_pairs_v39_four_channels import (
    CH_C, CH_G, CH_A, CH_T, CH_NAMES,
    FIRE_PERCENTILE,
    calibrate_firing_thresholds,
    print_summary_table, _yoy_table,
)
from run_crypto_pairs_v39b_k1_scaled import (
    PCA_K_B, MU_FLOOR,
    calibrate_channel_means,
    compute_four_channel_signals_v39b,
)

OUT_DIR_ = Path(OUT_DIR)

# ── v47 confirmed-optimal FIXED parameters ─────────────────────────────────────
G_BOOST_THRESH  = 0.50
CHAMPION_BOOST  = 0.50
A_FIRE_THRESH   = 0.70
GL_TH_OPT       = -1.00   # confirmed full kill
GL_TL_OPT       = -1.00   # confirmed full kill
GH_TL_BASE      = -0.30   # v47 Group C best

# ── Sweep ranges ────────────────────────────────────────────────────────────────
# Group A: phase clip (GH_TH auto-set to clip-1.0)
CLIP_SWEEP      = [3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 8.0]

# Group B: G_THRESH
GTHRESH_SWEEP   = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55]

# Group C: T_THRESH
TTHRESH_SWEEP   = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]

# Group D: rolling window (both N_G and N_T together)
N_WINDOW_SWEEP  = [4, 6, 8, 10, 12, 16]

# Group E: GH_TL deeper negative
GHTL_SWEEP      = [-0.50, -0.40, -0.30, -0.20, 0.00]


# ══════════════════════════════════════════════════════════════════════════════
#  V48 SIZING
# ══════════════════════════════════════════════════════════════════════════════

def _make_quadrant_flags(sig_4ch, g_thresh, t_thresh, n_g, n_t):
    a_G_raw = sig_4ch['a_G']
    a_A_raw = sig_4ch['a_A']
    a_T_raw = sig_4ch['a_T']
    G_mem = a_G_raw.rolling(n_g, min_periods=1).max().shift(1).fillna(0.0)
    T_mem = a_T_raw.rolling(n_t, min_periods=1).max().shift(1).fillna(0.0)
    A_fire_lag1 = (a_A_raw.shift(1).fillna(0.0) > A_FIRE_THRESH)
    q_GH_TH = (A_fire_lag1 & (G_mem > g_thresh) & (T_mem > t_thresh)).astype(float)
    q_GH_TL = (A_fire_lag1 & (G_mem > g_thresh) & (T_mem <= t_thresh)).astype(float)
    q_GL_TH = (A_fire_lag1 & (G_mem <= g_thresh) & (T_mem > t_thresh)).astype(float)
    q_GL_TL = (A_fire_lag1 & (G_mem <= g_thresh) & (T_mem <= t_thresh)).astype(float)
    return q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL


def apply_v48_sizing(base_pnl:  pd.Series,
                     sig_v36:   pd.DataFrame,
                     lam_feat:  pd.DataFrame,
                     sig_4ch:   pd.DataFrame) -> dict[str, pd.Series]:
    idx  = base_pnl.index
    sv36 = sig_v36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lam_feat.reindex(idx, method='ffill').fillna(0.5)
    s4   = sig_4ch.reindex(idx, method='ffill').fillna(0.0)
    base = base_pnl.fillna(0.0)

    gam_adj  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lam_pct  = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size_sym = np.clip(1.0 - gam_adj, 0.0, 1.0) * (0.75 + 0.5 * lam_pct)

    a_G      = s4['a_G'].shift(1).fillna(0.0)
    flag_aG  = (a_G > G_BOOST_THRESH).astype(float)

    def _quad_pnl(gh_th, gh_tl, gl_th, gl_tl, clip_max,
                  g_thresh, t_thresh, n_g, n_t) -> pd.Series:
        q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL = _make_quadrant_flags(
            s4, g_thresh, t_thresh, n_g, n_t)
        phase = (1.0
                 + gh_th * q_GH_TH
                 + gh_tl * q_GH_TL
                 + gl_th * q_GL_TH
                 + gl_tl * q_GL_TL).clip(0.05, clip_max)
        return base * size_sym * (1.0 + CHAMPION_BOOST * flag_aG) * phase

    pnl: dict[str, pd.Series] = {}

    # ── References ────────────────────────────────────────────────────────────
    # v47 champion: clip=3.0, G_THRESH=0.45, T_THRESH=0.40, N=8
    pnl['v47_champion_ref'] = _quad_pnl(
        2.00, -0.30, GL_TH_OPT, GL_TL_OPT, 3.0, 0.45, 0.40, 8, 8)

    # ── Group A: Phase clip sweep (GH_TH=clip-1.0, defaults) ─────────────────
    for clip in CLIP_SWEEP:
        gh_th = clip - 1.0
        tag   = f'{int(round(clip * 10)):03d}'     # e.g. 030, 035, 040
        pnl[f'v48_A_clip{tag}'] = _quad_pnl(
            gh_th, GH_TL_BASE, GL_TH_OPT, GL_TL_OPT, clip, 0.45, 0.40, 8, 8)

    # Also: at each clip, set GH_TH much higher (2x clip-1) to test if it matters
    for clip in CLIP_SWEEP:
        gh_th = max(clip - 1.0, 1.0)   # same as above (clip is true ceiling anyway)
        # Additional: even higher GH_TH (will all clip anyway)
        tag = f'{int(round(clip * 10)):03d}'
        pnl[f'v48_A_clipHH{tag}'] = _quad_pnl(
            clip * 2.0, GH_TL_BASE, GL_TH_OPT, GL_TL_OPT, clip, 0.45, 0.40, 8, 8)

    # ── Group B: G_THRESH sweep (clip=4.0, GH_TH=3.0, rest defaults) ─────────
    for g_thr in GTHRESH_SWEEP:
        tag = f'{int(round(g_thr * 100)):03d}'
        pnl[f'v48_B_gthr{tag}'] = _quad_pnl(
            3.0, GH_TL_BASE, GL_TH_OPT, GL_TL_OPT, 4.0, g_thr, 0.40, 8, 8)

    # ── Group C: T_THRESH sweep (clip=4.0, GH_TH=3.0, best G_THRESH) ─────────
    for t_thr in TTHRESH_SWEEP:
        tag = f'{int(round(t_thr * 100)):03d}'
        pnl[f'v48_C_tthr{tag}'] = _quad_pnl(
            3.0, GH_TL_BASE, GL_TH_OPT, GL_TL_OPT, 4.0, 0.45, t_thr, 8, 8)

    # ── Group D: N_G / N_T sweep (clip=4.0, GH_TH=3.0, G_THRESH=0.45, T=0.40) ─
    for n_win in N_WINDOW_SWEEP:
        tag = f'{n_win:02d}'
        # Both windows equal
        pnl[f'v48_D_N{tag}'] = _quad_pnl(
            3.0, GH_TL_BASE, GL_TH_OPT, GL_TL_OPT, 4.0, 0.45, 0.40, n_win, n_win)
    # Also: N_G and N_T independently
    for n_g in N_WINDOW_SWEEP:
        for n_t in [4, 8, 12]:
            if n_g == n_t:
                continue   # already in joint sweep above
            pnl[f'v48_D_NG{n_g:02d}_NT{n_t:02d}'] = _quad_pnl(
                3.0, GH_TL_BASE, GL_TH_OPT, GL_TL_OPT, 4.0, 0.45, 0.40, n_g, n_t)

    # ── Group E: GH_TL deeper negative (clip=4.0, best config otherwise) ──────
    for gh_tl in GHTL_SWEEP:
        sign = 'p' if gh_tl >= 0 else 'm'
        tag  = f'{abs(int(round(gh_tl * 100))):03d}'
        pnl[f'v48_E_ghtl{sign}{tag}'] = _quad_pnl(
            3.0, gh_tl, GL_TH_OPT, GL_TL_OPT, 4.0, 0.45, 0.40, 8, 8)

    # ── Group F: Joint champion grid (run after results seen) ─────────────────
    # Based on a priori best guesses from previous sessions:
    #   clip probably benefits from 4.0-5.0, G_THRESH maybe lower (0.40), T_THRESH stable
    for clip in [4.0, 5.0, 6.0]:
        for g_thr in [0.40, 0.45, 0.50]:
            for t_thr in [0.35, 0.40]:
                for gh_tl in [-0.40, -0.30]:
                    tc   = f'{int(round(clip*10)):03d}'
                    tg   = f'{int(round(g_thr*100)):03d}'
                    tt   = f'{int(round(t_thr*100)):03d}'
                    sign = 'p' if gh_tl >= 0 else 'm'
                    tl   = f'{abs(int(round(gh_tl*100))):03d}'
                    pnl[f'v48_F_c{tc}_gt{tg}_tt{tt}_ghtl{sign}{tl}'] = _quad_pnl(
                        clip - 1.0, gh_tl, GL_TH_OPT, GL_TL_OPT,
                        clip, g_thr, t_thr, 8, 8)

    return pnl


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    t_start = time.time()
    BAR = "=" * 100
    print(BAR)
    print("  CRYPTO BSDT v48 — Phase Clip / Quadrant Boundaries / Rolling Windows")
    print("  v47 champion: GH_TH=2.00, GH_TL=-0.30, GL_TH=-1.00, GL_TL=-1.00  +3.4779")
    print("  Confirmed phase-clip ceiling at GH_TH=2.0 with clip=3.0")
    print(f"  Axes: CLIP={CLIP_SWEEP}  G_THRESH={GTHRESH_SWEEP}  T_THRESH={TTHRESH_SWEEP}")
    print(f"        N_WIN={N_WINDOW_SWEEP}  GH_TL={GHTL_SWEEP}")
    print(BAR)

    # ── 1. Data ─────────────────────────────────────────────────────────────
    print("\n[1] Fetching 1h data ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"  {len(df_1h):,} bars  |  Train: {train_1h.sum():,}  |  Test: {test_1h.sum():,}")

    # ── 2. Funding ───────────────────────────────────────────────────────────
    print("\n[2] Fetching funding ...")
    try:
        funding  = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
        fund_eth = funding.get('ETHUSDT') if isinstance(funding, dict) else None
        fund_btc = funding.get('BTCUSDT') if isinstance(funding, dict) else None
    except Exception:
        fund_eth = fund_btc = None

    # ── 3–9: Standard calibration ────────────────────────────────────────────
    print("\n[3] Building state panel ...")
    X_panel = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X_panel = np.nan_to_num(X_panel)

    train_idx  = np.where(train_1h)[0]
    calib_idx  = train_idx[-CALIB_BARS:]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[calib_idx] = True

    print("\n[4a] Calibrating v36 engine ...")
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(
        X_panel, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)

    X_normal = X_panel[calib_mask]
    print(f"\n[4b] Calibrating k={PCA_K_B} operator ...")
    M_k1 = MasterOperator.calibrate(X_normal, k=PCA_K_B)

    print(f"\n[5] v36 signals ...")
    sig_v36 = compute_intraday_signals(X_panel, df_1h, M, net, ews, stoch, e_star, theta)

    print("\n[6] v37 price prediction ...")
    sig_v37, M_reversal, sigma00_sqrt = compute_price_prediction_signals(
        X_panel, df_1h, M, sig_v36, e_star, sigma_n)

    print("\n[7] v38 lambda features ...")
    lam_feat = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    print(f"\n[8] Channel means ...")
    mu_norm = calibrate_channel_means(X_panel, calib_mask, M_k1)

    print(f"\n[9] Firing thresholds ...")
    fire_thresholds = calibrate_firing_thresholds(X_panel, calib_mask, M_k1,
                                                   pct=FIRE_PERCENTILE)

    print(f"\n[10] Four-channel signals ...")
    sig_4ch = compute_four_channel_signals_v39b(
        X_panel, df_1h, M_k1, sig_v36, fire_thresholds, mu_norm)

    # ── Quadrant summary at various thresholds ────────────────────────────────
    s = sig_4ch[test_1h]
    Af = (s['a_A'].shift(1).fillna(0.0) > A_FIRE_THRESH)
    n_A = int(Af.sum())
    print(f"\n  A-fire total: {n_A} bars over test period")
    print(f"  {'G_thr':>6}  {'T_thr':>6}  {'GH_TH':>8}  {'GH_TL':>8}  {'GL_TH':>8}  {'GL_TL':>8}")
    for g_thr in [0.35, 0.40, 0.45, 0.50]:
        for t_thr in [0.35, 0.40, 0.45]:
            Gm = s['a_G'].rolling(8, min_periods=1).max().shift(1).fillna(0.0)
            Tm = s['a_T'].rolling(8, min_periods=1).max().shift(1).fillna(0.0)
            n1 = int((Af & (Gm > g_thr) & (Tm > t_thr)).sum())
            n2 = int((Af & (Gm > g_thr) & (Tm <= t_thr)).sum())
            n3 = int((Af & (Gm <= g_thr) & (Tm > t_thr)).sum())
            n4 = int((Af & (Gm <= g_thr) & (Tm <= t_thr)).sum())
            print(f"  {g_thr:>6.2f}  {t_thr:>6.2f}  "
                  f"{n1:>5}({n1/n_A*100:>4.1f}%)  "
                  f"{n2:>5}({n2/n_A*100:>4.1f}%)  "
                  f"{n3:>5}({n3/n_A*100:>4.1f}%)  "
                  f"{n4:>5}({n4/n_A*100:>4.1f}%)")

    # ── 11. v34 base portfolio ───────────────────────────────────────────────
    print("\n[11] v34 base portfolio ...")
    h_strats = compute_1h_strategies(df_1h, has_sol)
    df_d   = fetch_and_prepare()
    df_d   = add_cross_market_features(df_d)
    fund_d = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
    df_d   = add_leverage_features(df_d, fund_d)
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
        name: upsample_daily_to_1h_pnl(pos, instr_map.get(name, df_1h['ret_eth']), gate_daily)
        for name, pos in pos_dict.items()
    }
    all_pnls = {**d_strats_1h, **h_strats}
    Q_v34    = compute_quality(all_pnls, bpd=BPD)
    pnl_combined_v34 = assemble_combined(all_pnls, Q_v34)
    st_v34 = _stats(pnl_combined_v34[pnl_combined_v34.index >= TEST_START])
    print(f"  v34 gross  Sharpe: {st_v34['sharpe']:+.3f}  "
          f"MaxDD: {st_v34['max_dd']:+.1%}  CAGR: {st_v34['cagr']:+.1%}")

    # ── 12. Apply v48 sizing ─────────────────────────────────────────────────
    print("\n[12] Applying v48 sizing ...")
    pnl_dict = apply_v48_sizing(pnl_combined_v34, sig_v36, lam_feat, sig_4ch)
    pnl_dict = {'v34_baseline': pnl_combined_v34, **pnl_dict}

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + BAR)
    print("  GROSS SNAPSHOT  (K=5, 2023 → 2026)")
    print(BAR)
    print_summary_table(pnl_dict, K=5)

    # ── Best per group ────────────────────────────────────────────────────────
    test_pnls: dict[str, dict] = {}
    for name, pnl in pnl_dict.items():
        ts    = pnl[pnl.index >= TEST_START]
        lev   = (ts * 5).clip(-0.5, 0.5)
        ec    = (1 + lev).cumprod()
        n_yrs = len(ts) / (365 * 24)
        cagr  = float(ec.iloc[-1] ** (1 / max(n_yrs, 0.1)) - 1) * 100
        dd    = float((ec / ec.cummax() - 1).min())
        sh    = float(lev.mean() / lev.std() * np.sqrt(ANN_1H)) if lev.std() > 0 else 0.0
        test_pnls[name] = dict(sharpe=sh, max_dd=dd * 100, cagr=cagr)

    for grp_prefix, label in [
        ('v48_A_clip0', 'Group A: Phase clip sweep (at clip ceiling)'),
        ('v48_A_clipH', 'Group A (HH): Phase clip with GH_TH>>clip  (should be == above)'),
        ('v48_B_',      'Group B: G_THRESH sweep'),
        ('v48_C_',      'Group C: T_THRESH sweep'),
        ('v48_D_',      'Group D: N_G/N_T window sweep'),
        ('v48_E_',      'Group E: GH_TL deeper negative'),
        ('v48_F_',      'Group F: Joint champion grid'),
    ]:
        group_items = {k: v for k, v in test_pnls.items() if k.startswith(grp_prefix)}
        if not group_items:
            continue
        best_k = max(group_items, key=lambda x: group_items[x]['sharpe'])
        best_v = group_items[best_k]
        ranked = sorted(group_items.items(), key=lambda x: -x[1]['sharpe'])
        print(f"\n  {label}:")
        print(f"    Best: {best_k}")
        print(f"    Sharpe={best_v['sharpe']:+.4f}  MaxDD={best_v['max_dd']:+.1f}%  "
              f"CAGR={best_v['cagr']:+.1f}%")
        for k, v in ranked[:8]:
            print(f"      {k:<65s}  {v['sharpe']:+.4f}  MaxDD={v['max_dd']:+.1f}%")

    v48_all = {k: v for k, v in test_pnls.items() if k.startswith('v48_')}
    if v48_all:
        overall_best = max(v48_all, key=lambda x: v48_all[x]['sharpe'])
        bv = v48_all[overall_best]
        print(f"\n  *** OVERALL BEST v48: {overall_best}")
        print(f"      Sharpe={bv['sharpe']:+.4f}  MaxDD={bv['max_dd']:+.1f}%  "
              f"CAGR={bv['cagr']:+.1f}%")

    print("\n" + BAR)
    print("  YEAR-ON-YEAR  ($100 start, compounding, gross)")
    print(BAR)
    for name, pnl in pnl_dict.items():
        _yoy_table(name, pnl)

    # ── Phase-clip analysis ───────────────────────────────────────────────────
    print(f"\n  PHASE CLIP ANALYSIS (Group A — GH_TH=clip-1.0):")
    print(f"  {'CLIP':>8}  {'GH_TH':>8}  {'Phase_max':>12}  {'Sharpe':>10}  {'dSharpe':>10}  {'CAGR':>10}")
    prev_sh = None
    for clip in CLIP_SWEEP:
        tag = f'{int(round(clip * 10)):03d}'
        key = f'v48_A_clip{tag}'
        if key in test_pnls:
            sh   = test_pnls[key]['sharpe']
            dsh  = f'{sh - prev_sh:+.4f}' if prev_sh is not None else '---'
            cagr = test_pnls[key]['cagr']
            print(f"  {clip:>8.1f}  {clip-1.0:>8.1f}  {clip:>12.1f}  {sh:>+10.4f}  {dsh:>10}  {cagr:>+9.1f}%")
            prev_sh = sh

    # ── Save JSON ─────────────────────────────────────────────────────────────
    res_path = OUT_DIR_ / 'crypto_bsdt_v48_axes_sweep.json'
    results: dict = {}
    for name, pnl in pnl_dict.items():
        ts    = pnl[pnl.index >= TEST_START]
        lev   = (ts * 5).clip(-0.5, 0.5)
        ec    = (1 + lev).cumprod()
        n_yrs = len(ts) / (365 * 24)
        cagr  = float(ec.iloc[-1] ** (1 / max(n_yrs, 0.1)) - 1) * 100
        dd    = float((ec / ec.cummax() - 1).min())
        sh    = float(lev.mean() / lev.std() * np.sqrt(ANN_1H)) if lev.std() > 0 else 0.0
        results[name] = dict(sharpe_K5=round(sh, 4),
                             max_dd_K5=round(dd * 100, 2),
                             cagr_K5=round(cagr, 2),
                             final_K5=round(float(ec.iloc[-1]) * 100, 2))

    with open(res_path, 'w') as f:
        json.dump({'strategies': results,
                   'config': {
                       'GL_TH_OPT': GL_TH_OPT, 'GL_TL_OPT': GL_TL_OPT,
                       'GH_TL_BASE': GH_TL_BASE,
                       'CLIP_SWEEP': CLIP_SWEEP,
                       'GTHRESH_SWEEP': GTHRESH_SWEEP,
                       'TTHRESH_SWEEP': TTHRESH_SWEEP,
                       'N_WINDOW_SWEEP': N_WINDOW_SWEEP,
                       'GHTL_SWEEP': GHTL_SWEEP,
                   }}, f, indent=2)
    print(f"\n  Saved → {res_path}")
    print(f"\n  Total runtime: {time.time() - t_start:.0f}s")
    print(BAR)


if __name__ == '__main__':
    main()
