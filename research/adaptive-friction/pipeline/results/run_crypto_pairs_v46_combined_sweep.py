"""
Crypto BSDT v46 — Combined Best + GH_TH Extension
===================================================
Champion: v45_B_ghth080_ghtl000  +3.098  (GH_TH=0.80, GH_TL=0.00, GL_TH=-0.40, GL_TL=-0.40)

v45 findings:
  1. GH_TH: no ceiling at 0.80 — +0.0157 Sharpe per +0.05 step, still linear
  2. GH_TL: 0.00 strictly dominates all positive values (+0.016 vs 0.10 default)
  3. GL_TL: harder kill monotone better → -0.60 (+3.079 at GH_TH=0.65) vs -0.40 (+3.040)
  4. GL_TH: -0.40 is best; easing toward 0 degrades both Sharpe and MaxDD

Two independent edges NOT yet combined:
    Best GH_TH/GH_TL: +3.098 (at GL_TL=-0.40)
    Best GL_TL kill:  +0.039 gain (tested at GH_TH=0.65, not at 0.80)

v46 PLAN (~30 variants):

Group A: Joint best combo — GH_TH extended sweep
    New baseline: GH_TL=0.00, GL_TH=-0.40, GL_TL=-0.60  (combined v45 winners)
    GH_TH ∈ {0.80, 0.90, 1.00, 1.10, 1.20, 1.50}         → 6 variants

Group B: GL_TL kill sweep at best GH_TH (from A)
    Fix GH_TH=best, GH_TL=0.00, GL_TH=-0.40
    GL_TL ∈ {-0.40, -0.50, -0.60, -0.70, -0.80, -1.00}   → 6 variants
    (-1.00 → phase clips to 0.05 = near-zero on random bars)

Group C: GL_TH deep kill sweep at best (GH_TH, GH_TL, GL_TL)
    Fix best A+B combo, vary GL_TH ∈ {-0.40, -0.50, -0.60, -0.80, -1.00} → 5 variants

Group D: GH_TL negative sweep at best GH_TH
    Fix GH_TH=best, GL_TH=-0.40, GL_TL=-0.60
    GH_TL ∈ {-0.20, -0.10, 0.00, 0.05, 0.10}             → 5 variants
    (Test if punishing spatial-only pre-events helps)

Group E: Verify joint champion across all 4 dimensions
    Top-2 GH_TH × top GH_TL × top GL_TL × top GL_TH      → ~6 variants
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
    print_transmission_lag_analysis,
    print_summary_table, _yoy_table,
)
from run_crypto_pairs_v39b_k1_scaled import (
    PCA_K_B, MU_FLOOR,
    calibrate_channel_means,
    compute_four_channel_signals_v39b,
)

OUT_DIR_ = Path(OUT_DIR)

# ── Fixed champion parameters ──────────────────────────────────────────────────
N_G             = 8
N_T             = 8
G_THRESH        = 0.45
T_THRESH        = 0.40
G_BOOST_THRESH  = 0.50
CHAMPION_BOOST  = 0.50
A_FIRE_THRESH   = 0.70

# v45 champion baseline
V45_CHAMP = (0.80, 0.00, -0.40, -0.40)   # GH_TH, GH_TL, GL_TH, GL_TL

# ── Sweep definitions ──────────────────────────────────────────────────────────
# Group A: GH_TH extended sweep (new baseline = GH_TL=0, GL_TH=-0.40, GL_TL=-0.60)
GH_TH_EXT = [0.80, 0.90, 1.00, 1.10, 1.20, 1.50]

# Group B: GL_TL kill sweep at best GH_TH from A
GL_TL_EXT  = [-0.40, -0.50, -0.60, -0.70, -0.80, -1.00]

# Group C: GL_TH deep kill sweep
GL_TH_EXT  = [-0.40, -0.50, -0.60, -0.80, -1.00]

# Group D: GH_TL negative sweep
GH_TL_NEG  = [-0.20, -0.10, 0.00, 0.05, 0.10]


# ═══════════════════════════════════════════════════════════════════════════════
#  V46 SIZING
# ═══════════════════════════════════════════════════════════════════════════════

def apply_v46_sizing(base_pnl:  pd.Series,
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

    a_G_raw = s4['a_G']
    a_A_raw = s4['a_A']
    a_T_raw = s4['a_T']

    a_G          = a_G_raw.shift(1).fillna(0.0)
    flag_aG_high = (a_G > G_BOOST_THRESH).astype(float)

    G_mem = a_G_raw.rolling(N_G, min_periods=1).max().shift(1).fillna(0.0)
    T_mem = a_T_raw.rolling(N_T, min_periods=1).max().shift(1).fillna(0.0)

    A_fire_lag1 = (a_A_raw.shift(1).fillna(0.0) > A_FIRE_THRESH)

    q_GH_TH = (A_fire_lag1 & (G_mem > G_THRESH) & (T_mem > T_THRESH)).astype(float)
    q_GH_TL = (A_fire_lag1 & (G_mem > G_THRESH) & (T_mem <= T_THRESH)).astype(float)
    q_GL_TH = (A_fire_lag1 & (G_mem <= G_THRESH) & (T_mem > T_THRESH)).astype(float)
    q_GL_TL = (A_fire_lag1 & (G_mem <= G_THRESH) & (T_mem <= T_THRESH)).astype(float)

    def _quad(a, b, c, d) -> pd.Series:
        phase = (1.0
                 + a * q_GH_TH
                 + b * q_GH_TL
                 + c * q_GL_TH
                 + d * q_GL_TL).clip(0.05, 3.0)
        return base * size_sym * (1.0 + CHAMPION_BOOST * flag_aG_high) * phase

    pnl: dict[str, pd.Series] = {}

    # ── References ────────────────────────────────────────────────────────────
    pnl['v44_champion_ref'] = _quad(0.50, 0.10, -0.40, -0.40)
    pnl['v45_champion_ref'] = _quad(0.80, 0.00, -0.40, -0.40)   # v45_B_ghth080_ghtl000

    # ── Group A: GH_TH extended sweep  (new baseline: GH_TL=0, GL_TL=-0.60) ──
    for gh_th in GH_TH_EXT:
        tag = f'{int(round(gh_th*100)):03d}'
        pnl[f'v46_A_ghth{tag}_b060'] = _quad(gh_th, 0.00, -0.40, -0.60)

    # ── Group B: GL_TL kill sweep at each GH_TH (GH_TL=0.00, GL_TH=-0.40) ───
    for gh_th in GH_TH_EXT:
        for gl_tl in GL_TL_EXT:
            tgh = f'{int(round(gh_th*100)):03d}'
            tkl = f'{abs(int(round(gl_tl*100))):03d}'
            pnl[f'v46_B_ghth{tgh}_gltl{tkl}'] = _quad(gh_th, 0.00, -0.40, gl_tl)

    # ── Group C: GL_TH deep kill sweep (GH_TH=1.00, GH_TL=0.00, GL_TL=-0.60) ─
    for gl_th in GL_TH_EXT:
        tk = f'{abs(int(round(gl_th*100))):03d}'
        pnl[f'v46_C_glth{tk}_ghth100'] = _quad(1.00, 0.00, gl_th, -0.60)

    # ── Group D: GH_TL negative sweep (GH_TH=1.00, GL_TH=-0.40, GL_TL=-0.60) ─
    for gh_tl in GH_TL_NEG:
        sign = 'p' if gh_tl >= 0 else 'm'
        tag = f'{abs(int(round(gh_tl*100))):03d}'
        pnl[f'v46_D_ghtl{sign}{tag}'] = _quad(1.00, gh_tl, -0.40, -0.60)

    # ── Group E: Joint grid — top-2 GH_TH × top GL_TL × top GL_TH ───────────
    for gh_th in [1.00, 1.10, 1.20]:
        for gl_tl in [-0.60, -0.80]:
            for gl_th in [-0.40, -0.60]:
                tgh  = f'{int(round(gh_th*100)):03d}'
                tkl  = f'{abs(int(round(gl_tl*100))):03d}'
                tkth = f'{abs(int(round(gl_th*100))):03d}'
                pnl[f'v46_E_ghth{tgh}_gltl{tkl}_glth{tkth}'] = _quad(gh_th, 0.00, gl_th, gl_tl)

    return pnl


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    t_start = time.time()
    BAR = "=" * 100
    print(BAR)
    print("  CRYPTO BSDT v46 — Combined Best + GH_TH Extension")
    print("  v45 champion: v45_B_ghth080_ghtl000  +3.098")
    print("  New baseline: GH_TL=0.00, GL_TL=-0.60 (combining v45 group-A and group-C best)")
    print(f"  GH_TH_EXT: {GH_TH_EXT}")
    print(f"  GL_TL_EXT: {GL_TL_EXT}")
    print(BAR)

    # ── 1. Data ─────────────────────────────────────────────────────────────
    print("\n[1] Fetching 1h data ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"  1h DataFrame: {df_1h.index[0]}  →  {df_1h.index[-1]}   "
          f"n={len(df_1h):,} bars")
    print(f"  Train: {train_1h.sum():,}   Test: {test_1h.sum():,}   SOL: {has_sol}")

    # ── 2. Funding ───────────────────────────────────────────────────────────
    print("\n[2] Fetching funding ...")
    try:
        funding  = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
        fund_eth = funding.get('ETHUSDT') if isinstance(funding, dict) else None
        fund_btc = funding.get('BTCUSDT') if isinstance(funding, dict) else None
    except Exception:
        fund_eth = fund_btc = None

    # ── 3. State panel ───────────────────────────────────────────────────────
    print("\n[3] Building state panel ...")
    X_panel = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X_panel = np.nan_to_num(X_panel)

    # ── 4a. v36 engine ───────────────────────────────────────────────────────
    train_idx  = np.where(train_1h)[0]
    calib_idx  = train_idx[-CALIB_BARS:]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[calib_idx] = True

    print("\n[4a] Calibrating v36 engine ...")
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(
        X_panel, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)

    # ── 4b. k=1 operator ─────────────────────────────────────────────────────
    X_normal = X_panel[calib_mask]
    print(f"\n[4b] Calibrating k={PCA_K_B} operator ...")
    M_k1 = MasterOperator.calibrate(X_normal, k=PCA_K_B)

    # ── 5. v36 signals ───────────────────────────────────────────────────────
    print(f"\n[5] v36 signals ...")
    sig_v36 = compute_intraday_signals(X_panel, df_1h, M, net, ews, stoch,
                                        e_star, theta)

    # ── 6. v37 price prediction ──────────────────────────────────────────────
    print("\n[6] v37 price prediction ...")
    sig_v37, M_reversal, sigma00_sqrt = compute_price_prediction_signals(
        X_panel, df_1h, M, sig_v36, e_star, sigma_n)

    # ── 7. v38 lambda features ───────────────────────────────────────────────
    print("\n[7] v38 lambda features ...")
    lam_feat = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    # ── 8. Channel means ─────────────────────────────────────────────────────
    print(f"\n[8] Channel means ...")
    mu_norm = calibrate_channel_means(X_panel, calib_mask, M_k1)

    # ── 9. Firing thresholds ─────────────────────────────────────────────────
    print(f"\n[9] Firing thresholds ...")
    fire_thresholds = calibrate_firing_thresholds(X_panel, calib_mask, M_k1,
                                                   pct=FIRE_PERCENTILE)

    # ── 10. Four-channel signals ─────────────────────────────────────────────
    print(f"\n[10] Four-channel signals ...")
    sig_4ch = compute_four_channel_signals_v39b(
        X_panel, df_1h, M_k1, sig_v36, fire_thresholds, mu_norm)

    # ── Quadrant population ───────────────────────────────────────────────────
    s = sig_4ch[test_1h]
    Gm = s['a_G'].rolling(N_G, min_periods=1).max().shift(1).fillna(0.0)
    Tm = s['a_T'].rolling(N_T, min_periods=1).max().shift(1).fillna(0.0)
    Af = (s['a_A'].shift(1).fillna(0.0) > A_FIRE_THRESH)
    n_A    = int(Af.sum())
    n_GHTH = int((Af & (Gm > G_THRESH) & (Tm > T_THRESH)).sum())
    n_GHTL = int((Af & (Gm > G_THRESH) & (Tm <= T_THRESH)).sum())
    n_GLTH = int((Af & (Gm <= G_THRESH) & (Tm > T_THRESH)).sum())
    n_GLTL = int((Af & (Gm <= G_THRESH) & (Tm <= T_THRESH)).sum())
    print(f"\n  Quadrant pop: total A-fire={n_A}  |  "
          f"GH_TH={n_GHTH}({n_GHTH/n_A*100:.1f}%)  "
          f"GH_TL={n_GHTL}({n_GHTL/n_A*100:.1f}%)  "
          f"GL_TH={n_GLTH}({n_GLTH/n_A*100:.1f}%)  "
          f"GL_TL={n_GLTL}({n_GLTL/n_A*100:.1f}%)")

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

    # ── 12. Apply v46 sizing ─────────────────────────────────────────────────
    print("\n[12] Applying v46 combined sweep sizing ...")
    pnl_dict = apply_v46_sizing(pnl_combined_v34, sig_v36, lam_feat, sig_4ch)
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
        ('v46_A_', 'Group A: GH_TH extended (new GL_TL=-0.60 baseline)'),
        ('v46_B_', 'Group B: GL_TL kill × GH_TH'),
        ('v46_C_', 'Group C: GL_TH deep kill'),
        ('v46_D_', 'Group D: GH_TL negative'),
        ('v46_E_', 'Group E: Joint champion grid'),
    ]:
        group_items = {k: v for k, v in test_pnls.items() if k.startswith(grp_prefix)}
        if not group_items:
            continue
        best_k = max(group_items, key=lambda x: group_items[x]['sharpe'])
        best_v = group_items[best_k]
        print(f"\n  Best {label}:")
        print(f"    {best_k}")
        print(f"    Sharpe={best_v['sharpe']:+.4f}  MaxDD={best_v['max_dd']:+.1f}%  "
              f"CAGR={best_v['cagr']:+.1f}%")

    # ── Overall best ──────────────────────────────────────────────────────────
    v46_items = {k: v for k, v in test_pnls.items() if k.startswith('v46_')}
    if v46_items:
        overall_best = max(v46_items, key=lambda x: v46_items[x]['sharpe'])
        bv = v46_items[overall_best]
        print(f"\n  *** OVERALL BEST v46: {overall_best}")
        print(f"      Sharpe={bv['sharpe']:+.4f}  MaxDD={bv['max_dd']:+.1f}%  "
              f"CAGR={bv['cagr']:+.1f}%")

    print("\n" + BAR)
    print("  YEAR-ON-YEAR  ($100 start, compounding, gross)")
    print(BAR)
    for name, pnl in pnl_dict.items():
        _yoy_table(name, pnl)

    # ── Save JSON ─────────────────────────────────────────────────────────────
    res_path = OUT_DIR_ / 'crypto_bsdt_v46_combined_sweep.json'
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
        json.dump({
            'strategies': results,
            'quadrants': {'GH_TH': n_GHTH, 'GH_TL': n_GHTL,
                          'GL_TH': n_GLTH, 'GL_TL': n_GLTL,
                          'total_A_fire': n_A},
            'config': {
                'PCA_K':          PCA_K_B,
                'N_G':            N_G,
                'N_T':            N_T,
                'G_THRESH':       G_THRESH,
                'T_THRESH':       T_THRESH,
                'G_BOOST_THRESH': G_BOOST_THRESH,
                'CHAMPION_BOOST': CHAMPION_BOOST,
                'A_FIRE_THRESH':  A_FIRE_THRESH,
                'V45_CHAMP':      list(V45_CHAMP),
                'GH_TH_EXT':      GH_TH_EXT,
                'GL_TL_EXT':      GL_TL_EXT,
                'GL_TH_EXT':      GL_TH_EXT,
                'GH_TL_NEG':      GH_TL_NEG,
            },
        }, f, indent=2)
    print(f"\n  Saved → {res_path}")
    print(f"\n  Total runtime: {time.time() - t_start:.0f}s")
    print(BAR)


if __name__ == '__main__':
    main()
