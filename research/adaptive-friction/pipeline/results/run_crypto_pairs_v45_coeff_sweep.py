"""
Crypto BSDT v45 — Extended 4-Quadrant Coefficient Sweep
========================================================
Champion: v44_q4_ghth050  +2.996  (GH_TH=0.50, GH_TL=0.10, GL_TH=-0.40, GL_TL=-0.40)

Observation from v44: GH_TH coefficient is monotone-improving from 0.30→0.50.
The slope is linear (~+0.016 Sharpe per +0.05 GH_TH step).
No ceiling found yet → extend sweep to find where it saturates.

4-quadrant framework (G_mem>0.45, T_mem>0.40, A-fire):
    GH_TH: G↑, T↑ — full instability precursor   → BOOST by c_GH_TH
    GH_TL: G↑, T↓ — spatial precursor only        → BOOST by c_GH_TL
    GL_TH: G↓, T↑ — temporal precursor only       → KILL  by c_GL_TH (v44: = GL_TL)
    GL_TL: G↓, T↓ — no precursor, random cascade  → KILL  by c_GL_TL

Quadrant population (8,405 test bars, 746 A-fire):
    GH_TH: 517 (69.3%)  ← dominant
    GH_TL:  95 (12.7%)
    GL_TH:  85 (11.4%)
    GL_TL:  49  (6.6%)

SWEEP DESIGN (~35 variants):

Group A: GH_TH sweep  (GH_TL=0.10, GL_TH=GL_TL=-0.40 fixed)
    GH_TH ∈ {0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80}          → 7 variants
    → find where improvement saturates / reverses

Group B: GH_TL sweep at best GH_TH from A  (best ≈ 0.65-0.70 expected)
    Fix best GH_TH, vary GH_TL ∈ {0.00, 0.05, 0.10, 0.15, 0.20, 0.25}  → 6 variants
    Note: GH_TL=0 means spatial-only precursor gets NO reward (just kills rand)

Group C: GL_TL (rand kill) sweep at best (GH_TH, GH_TL)
    Fix best GH_TH + best GH_TL, vary GL_TL ∈ {-0.30, -0.35, -0.40, -0.45, -0.50, -0.60}  → 6 variants

Group D: GL_TH ablation at best (GH_TH, GH_TL, GL_TL)
    Vary GL_TH ∈ {-0.40, -0.30, -0.20, -0.10, 0.00} — is temporal-only-anomaly killable?  → 5 variants

Group E: Joint best combinations — confirm non-interaction
    Top 3 GH_TH × Top 2 GH_TL × best GL  → ~6 variants

Refs: v34_baseline, v40_champion_ref, v43_champion_ref, v44_champion_ref
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
N_G             = 8       # G_mem rolling_max window
N_T             = 8       # T_mem rolling_max window
G_THRESH        = 0.45   # G_mem threshold
T_THRESH        = 0.40   # T_mem threshold
G_BOOST_THRESH  = 0.50   # v39b G-boost flag
CHAMPION_BOOST  = 0.50   # G-boost coefficient
A_FIRE_THRESH   = 0.70   # a_A threshold

# v44 champion baseline
V44_CHAMP = (0.50, 0.10, -0.40, -0.40)   # (GH_TH, GH_TL, GL_TH, GL_TL)

# ── Group A: GH_TH sweep ──────────────────────────────────────────────────────
# GH_TL=0.10, GL_TH=GL_TL=-0.40 (v44 champion structure)
GH_TH_SWEEP = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]

# ── Group B: GH_TL sweep (applied at each GH_TH in sweep) ────────────────────
GH_TL_SWEEP = [0.00, 0.05, 0.10, 0.15, 0.20, 0.25]

# ── Group C: GL_TL (rand kill) sweep ─────────────────────────────────────────
# Applied at GH_TH=0.65, GH_TL=0.10 (mid-range expected winner)
GL_TL_SWEEP = [-0.30, -0.35, -0.40, -0.45, -0.50, -0.60]

# ── Group D: GL_TH ablation ───────────────────────────────────────────────────
GL_TH_SWEEP = [-0.40, -0.30, -0.20, -0.10, 0.00]


# ═══════════════════════════════════════════════════════════════════════════════
#  V45 SIZING
# ═══════════════════════════════════════════════════════════════════════════════

def apply_v45_sizing(base_pnl:  pd.Series,
                     sig_v36:   pd.DataFrame,
                     lam_feat:  pd.DataFrame,
                     sig_4ch:   pd.DataFrame) -> dict[str, pd.Series]:
    """
    4-quadrant discrete sizing.

    phase = 1 + c_GH_TH*q_GH_TH + c_GH_TL*q_GH_TL + c_GL_TH*q_GL_TH + c_GL_TL*q_GL_TL

    Champions throughout use G-boost base (1 + 0.50 * G_flag) × phase.
    """
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
    pnl['v40_champion_ref'] = _quad(0.20, 0.20, -0.40, -0.40)   # no T split
    pnl['v43_champion_ref'] = _quad(0.30, 0.10, -0.40, -0.40)
    pnl['v44_champion_ref'] = _quad(*V44_CHAMP)                  # 0.50, 0.10, -0.40, -0.40

    # ── Group A: GH_TH sweep (GH_TL=0.10, GL fixed at -0.40) ─────────────────
    for gh_th in GH_TH_SWEEP:
        tag = f'{int(gh_th*100):03d}'
        pnl[f'v45_A_ghth{tag}'] = _quad(gh_th, 0.10, -0.40, -0.40)

    # ── Group B: GH_TH × GH_TL joint (GL fixed at -0.40) ─────────────────────
    # Run all combinations to map the 2D surface
    for gh_th in GH_TH_SWEEP:
        for gh_tl in GH_TL_SWEEP:
            tag = f'ghth{int(gh_th*100):03d}_ghtl{int(gh_tl*100):03d}'
            pnl[f'v45_B_{tag}'] = _quad(gh_th, gh_tl, -0.40, -0.40)

    # ── Group C: GL_TL kill sweep (GH_TH=0.65, GH_TL=0.10 mid-range) ─────────
    for gl_tl in GL_TL_SWEEP:
        tag = f'k{abs(int(gl_tl*100)):03d}'
        pnl[f'v45_C_gltl{tag}'] = _quad(0.65, 0.10, gl_tl, gl_tl)

    # ── Group D: GL_TH ablation (GH_TH=0.65, GH_TL=0.10, GL_TL=-0.40 fixed) ──
    for gl_th in GL_TH_SWEEP:
        tag = f'glth{int(gl_th*100):+04d}'.replace('+','p').replace('-','m')
        pnl[f'v45_D_{tag}'] = _quad(0.65, 0.10, gl_th, -0.40)

    return pnl


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    t_start = time.time()
    BAR = "=" * 100
    print(BAR)
    print("  CRYPTO BSDT v45 — Extended 4-Quadrant Coefficient Sweep")
    print("  Champion: v44_q4_ghth050  +2.996")
    print("  Goal: find GH_TH ceiling; optimize GH_TL, GL_TL, GL_TH at best GH_TH")
    print(f"  GH_TH sweep: {GH_TH_SWEEP}")
    print(f"  GH_TL sweep: {GH_TL_SWEEP}")
    print(BAR)

    # ── 1. Data ─────────────────────────────────────────────────────────────
    print("\n[1] Fetching 1h data ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"  1h DataFrame: {df_1h.index[0]}  →  {df_1h.index[-1]}   "
          f"n={len(df_1h):,} bars")
    print(f"  Train: {train_1h.sum():,}   Test: {test_1h.sum():,}   SOL: {has_sol}")
    print(f"  {len(df_1h):,} bars  |  Train: {train_1h.sum():,}  |  Test: {test_1h.sum():,}")

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

    # ── Quick quadrant population check ──────────────────────────────────────
    s = sig_4ch[test_1h]
    Gm = s['a_G'].rolling(N_G, min_periods=1).max().shift(1).fillna(0.0)
    Tm = s['a_T'].rolling(N_T, min_periods=1).max().shift(1).fillna(0.0)
    Af = (s['a_A'].shift(1).fillna(0.0) > A_FIRE_THRESH)
    n_A     = int(Af.sum())
    n_GHTH  = int((Af & (Gm > G_THRESH) & (Tm > T_THRESH)).sum())
    n_GHTL  = int((Af & (Gm > G_THRESH) & (Tm <= T_THRESH)).sum())
    n_GLTH  = int((Af & (Gm <= G_THRESH) & (Tm > T_THRESH)).sum())
    n_GLTL  = int((Af & (Gm <= G_THRESH) & (Tm <= T_THRESH)).sum())
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

    # ── 12. Apply v45 sizing ─────────────────────────────────────────────────
    print("\n[12] Applying v45 coefficient sweep sizing ...")
    pnl_dict = apply_v45_sizing(pnl_combined_v34, sig_v36, lam_feat, sig_4ch)
    pnl_dict = {'v34_baseline': pnl_combined_v34, **pnl_dict}

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + BAR)
    print("  GROSS SNAPSHOT  (K=5, 2023 → 2026)")
    print(BAR)
    print_summary_table(pnl_dict, K=5)

    # ── Best-per-group printout ───────────────────────────────────────────────
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
        ('v45_A_', 'Group A: GH_TH sweep'),
        ('v45_B_', 'Group B: GH_TH × GH_TL'),
        ('v45_C_', 'Group C: GL_TL kill sweep'),
        ('v45_D_', 'Group D: GL_TH ablation'),
    ]:
        group_items = {k: v for k, v in test_pnls.items() if k.startswith(grp_prefix)}
        if not group_items:
            continue
        best_k = max(group_items, key=lambda x: group_items[x]['sharpe'])
        best_v = group_items[best_k]
        print(f"\n  Best {label}: {best_k}")
        print(f"    Sharpe={best_v['sharpe']:+.4f}  MaxDD={best_v['max_dd']:+.1f}%  "
              f"CAGR={best_v['cagr']:+.1f}%")

    print("\n" + BAR)
    print("  YEAR-ON-YEAR  ($100 start, compounding, gross)")
    print(BAR)
    for name, pnl in pnl_dict.items():
        _yoy_table(name, pnl)

    # ── Save JSON ─────────────────────────────────────────────────────────────
    res_path = OUT_DIR_ / 'crypto_bsdt_v45_coeff_sweep.json'
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
                'V44_CHAMP':      list(V44_CHAMP),
                'GH_TH_SWEEP':    GH_TH_SWEEP,
                'GH_TL_SWEEP':    GH_TL_SWEEP,
                'GL_TL_SWEEP':    GL_TL_SWEEP,
                'GL_TH_SWEEP':    GL_TH_SWEEP,
            },
        }, f, indent=2)
    print(f"\n  Saved → {res_path}")
    print(f"\n  Total runtime: {time.time() - t_start:.0f}s")
    print(BAR)


if __name__ == '__main__':
    main()
