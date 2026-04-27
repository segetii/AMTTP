"""
Crypto BSDT v38 — Normalised-λ Enhancement
============================================
Diagnostic from v37: raw λ_price ≈ 0.19 uniformly (calibration used Oct-Dec 2022
crash period with σ_return=1.67%/hr; test period 2023-2026 is calmer → λ structurally
small → acts as 81% dampener, not a selective filter → all v37 variants < v36).

FIX: replace raw λ with λ_pct = rolling-percentile-rank(λ, 200 bars) ∈ [0,1].
Now the question is "is today's price energy HIGH or LOW relative to recent history?"
rather than "is it above the Oct-2022 crash baseline?"

FIVE v38 VARIANTS
──────────────────
  v38_lam_pct    — (1−γ*) × λ_pct                  half-scale, always active
  v38_lam_boost  — (1−γ*) × (0.5 + 0.5·λ_pct)      full-scale, λ_pct amplifies ±50%
  v38_sym        — (1−γ*) × (1 + 0.5·(λ_pct−0.5))  mean-neutral amplifier [PRIMARY]
                   i.e. size = (1−γ*) × (0.75 + 0.5·λ_pct)   ∈ [(1−γ*)·0.75, (1−γ*)·1.25]
  v38_dlam_soft  — (1−γ*) × (0.75 + 0.25·𝟙[dλ≥0])  soft dλ gate (not binary)
  v38_full_pct   — (1−γ*) × λ_pct × (0.5 + 0.5·𝟙[dλ≥0])  combined (low sizing)

ALSO RE-PRINTED: v34_baseline, v36_BSDT_scaled, v36_BSDT_filtered from v37 for reference.

ROLLBACK WINDOW: 200 bars (≈8 days of hourly data). Long enough to adapt to regimes,
short enough to be responsive.  100, 500 sensitivity are also tested as diagnostics.

Usage:
    py -3 run_crypto_pairs_v38_lambda_norm.py
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

# ── pull everything from v37 and v36 ──────────────────────────────────────
from run_crypto_pairs_v37_price_prediction import (
    compute_price_prediction_signals,
    _extract_sigma00, compute_price_energy,
)
from run_crypto_pairs_v36_intraday_bsdt import (
    N_AGENTS, N_FEATURES, CALIB_BARS, ALPHA_CONF, PCA_K,
    BPD, ANN_1H,
    build_intraday_state_panel, calibrate_intraday_engine,
    compute_intraday_signals,
    apply_bsdt_decision_tree,
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
LAM_ROLL_MAIN = 200   # primary rolling window for λ percentile rank
RETURN_FEAT   = 0


# ═══════════════════════════════════════════════════════════════════════════
#  NORMALISED-λ + DERIVATIVE COMPUTATION
# ═══════════════════════════════════════════════════════════════════════════

def compute_lambda_features(sig_v37: pd.DataFrame,
                             roll_windows: tuple[int, ...] = (100, 200, 500)
                             ) -> pd.DataFrame:
    """
    From the v37 lambda_price series compute:
      - lambda_pct_W   : rolling percentile rank over W bars (for each W in roll_windows)
      - dlambda_dt     : standardised first difference  (dλ / rolling std)
      - dlambda_sign   : +1 / −1 binary direction

    Returns a DataFrame with these features aligned to sig_v37's index.
    """
    lam = sig_v37['lambda_price'].copy()            # raw λ from v37

    df = pd.DataFrame(index=lam.index)
    for W in roll_windows:
        pct = lam.rolling(W, min_periods=W // 2).rank(pct=True)
        df[f'lambda_pct_{W}'] = pct.fillna(0.5)    # fill with 0.5 until full window

    # Finite-difference dλ / rolling-std(dλ) over 50 bars
    dlam_raw = lam.diff().fillna(0.0)
    dlam_std = dlam_raw.rolling(50, min_periods=10).std().fillna(1e-6).clip(lower=1e-6)
    df['dlambda_norm'] = (dlam_raw / dlam_std).clip(-3.0, 3.0)   # z-score, capped
    df['dlambda_sign'] = np.sign(dlam_raw).fillna(0.0)

    # λ_pct for primary window separately named
    df['lambda_pct'] = df[f'lambda_pct_{LAM_ROLL_MAIN}']

    return df


# ═══════════════════════════════════════════════════════════════════════════
#  V38 POSITION SIZING — FIVE NEW VARIANTS
# ═══════════════════════════════════════════════════════════════════════════

def apply_v38_sizing(base_pnl:   pd.Series,
                     sig_v36:    pd.DataFrame,
                     lam_feat:   pd.DataFrame) -> dict[str, pd.Series]:
    """
    Returns dict of PnL series for all variants (baseline + v38 variants).

    All sizing signals are lagged by 1 bar (no look-ahead).

    v38 variants
    ─────────────
    v38_lam_pct   : (1−γ*) × λ_pct
                    Mean sizing ≈ 0.5 × v36  (λ_pct has mean 0.5)

    v38_lam_boost : (1−γ*) × (0.5 + 0.5·λ_pct)
                    Range: [(1−γ*)·0.5, (1−γ*)·1.0]
                    Mean sizing ≈ 0.75 × v36

    v38_sym       : (1−γ*) × (0.75 + 0.5·λ_pct)       [PRIMARY]
                    Equivalent to  (1−γ*) × (1 + 0.5·(λ_pct − 0.5))
                    Range: [(1−γ*)·0.75, (1−γ*)·1.25]
                    Mean sizing ≈ 1.0 × v36  (NEUTRAL — same average as v36)

    v38_dlam_soft : (1−γ*) × (0.75 + 0.25·𝟙[dλ≥0])
                    = full (1−γ*) when dλ≥0, 0.75·(1−γ*) when dλ<0
                    Mean sizing ≈ 0.875 × v36

    v38_full_pct  : (1−γ*) × λ_pct × (0.5 + 0.5·𝟙[dλ≥0])
                    Range: [0, 1.0·(1−γ*)]
                    Mean sizing ≈ 0.375 × v36
    """
    idx   = base_pnl.index
    sv36  = sig_v36.reindex(idx, method='ffill').fillna(0.0)
    lf    = lam_feat.reindex(idx, method='ffill').fillna(0.5)
    base  = base_pnl.fillna(0.0)

    # Lag by 1 bar (apply today what was known at close of yesterday)
    gam_adj      = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lam_pct      = lf['lambda_pct'].shift(1).fillna(0.5)
    dlam_sign    = lf['dlambda_sign'].shift(1).fillna(0.0)
    dlam_ok      = (dlam_sign >= 0.0).astype(float)     # 0 or 1

    size_base    = np.clip(1.0 - gam_adj, 0.0, 1.0)    # core (1−γ*) from v36

    pnl = {}
    pnl['v34_baseline']    = base
    pnl['v36_BSDT_scaled'] = base * size_base
    pnl['v38_lam_pct']     = base * size_base * lam_pct
    pnl['v38_lam_boost']   = base * size_base * (0.5 + 0.5 * lam_pct)
    pnl['v38_sym']         = base * size_base * (0.75 + 0.5 * lam_pct)   # PRIMARY
    pnl['v38_dlam_soft']   = base * size_base * (0.75 + 0.25 * dlam_ok)
    pnl['v38_full_pct']    = base * size_base * lam_pct * (0.5 + 0.5 * dlam_ok)

    # Sensitivity: also test different roll windows for λ_pct
    for W, col in [(100, f'lambda_pct_100'), (500, f'lambda_pct_500')]:
        lp_W = lf[col].shift(1).fillna(0.5)
        pnl[f'v38_sym_W{W}'] = base * size_base * (0.75 + 0.5 * lp_W)

    return pnl


# ═══════════════════════════════════════════════════════════════════════════
#  YoY TABLE  (same helper as v36/v37)
# ═══════════════════════════════════════════════════════════════════════════

def _yoy_table(name: str, pnl_series: pd.Series, K_list=(1, 2, 5, 10)):
    test_mask = pnl_series.index >= TEST_START
    years = sorted(pnl_series[test_mask].index.year.unique())
    print(f"\n  {name}")
    print(f"    {'K':<5}  " + "  ".join(f"{y:>7}" for y in years) +
          f"  {'$100→':>8}  {'MaxDD':>7}  {'CAGR':>9}")
    print("  " + "-" * (5 + 9 * len(years) + 25))
    for K in K_list:
        r = _net_ret(pnl_series, K)    # applies K× leverage and subtracts fees
        # Year-by-year via hourly compounding (exact, consistent with v36/v37)
        eq   = 100.0
        yr_r = {}
        for yr in years:
            m  = (pnl_series.index.year == yr) & test_mask
            ret = float((1.0 + r[m]).prod() - 1.0)
            yr_r[yr] = ret
            eq  *= (1.0 + ret)
        # MaxDD from hourly equity over the full (train+test) period
        ec  = 100.0 * (1.0 + r).cumprod()
        mdd = float((ec / ec.cummax() - 1.0).min())
        n_yrs = len(r[test_mask]) / (365 * 24)
        cagr = float((eq / 100.0) ** (1.0 / max(n_yrs, 0.01)) - 1.0) * 100

        yr_str = "  ".join(f"{yr_r.get(y, 0)*100:>+6.0f}%" for y in years)
        print(f"    {K:<5d}  {yr_str}  ${eq:>7.2f}  {mdd*100:>+6.1f}%  {cagr:>+7.1f}%/yr")


# ═══════════════════════════════════════════════════════════════════════════
#  SUMMARY TABLE  (like v37's layer-ablation table)
# ═══════════════════════════════════════════════════════════════════════════

def print_summary_table(pnl_dict: dict[str, pd.Series], K: int = 5):
    """Gross snapshot (K leverage) over test 2023-2026, consistent with v36/v37 stats."""
    test = lambda s: s[s.index >= TEST_START]
    print(f"\n  {'Strategy':<25}  {'Sharpe':>7}  {'MaxDD':>7}  {'CAGR':>8}  "
          f"{'Active%':>8}  {'ActDays':>8}  {'$100→':>8}")
    print("  " + "-" * 90)
    for name, pnl in pnl_dict.items():
        ts = test(pnl)
        levered = (ts * K).clip(-0.5, 0.5)
        # Sharpe: hourly stats (consistent with v37's _stats)
        sh = float(levered.mean() / levered.std() * np.sqrt(ANN_1H)) if levered.std() > 0 else 0.0
        # MaxDD: from hourly equity cumprod (correct, not resampled)
        ec = (1 + levered).cumprod()
        dd = float((ec / ec.cummax() - 1).min())
        final = float(ec.iloc[-1]) * 100
        n_yrs = len(ts) / (365 * 24)
        cagr  = float(ec.iloc[-1] ** (1 / max(n_yrs, 0.1)) - 1) * 100
        active = float((ts != 0).mean()) * 100
        act_d  = int(active / 100 * len(ts) / 24)
        print(f"  {name:<25}  {sh:>+7.3f}  {dd*100:>6.1f}%  {cagr:>7.1f}%  "
              f"  {active:>6.1f}%  {act_d:>5d}d  ${final:>6.2f}")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    t_start = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)

    print("=" * 100)
    print("  CRYPTO BSDT v38 — NORMALISED-λ ENHANCEMENT")
    print("  rolling-percentile λ_pct  |  mean-neutral amplifier  |  soft-dλ gate")
    print("=" * 100)

    # ─────────────────────────────────── 1h DATA ──
    print("\n[1] Fetching Binance 1h data ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"  {len(df_1h):,} bars  |  Train: {train_1h.sum():,}  |  Test: {test_1h.sum():,}")

    # ──────────────────────────────────── FUNDING ──
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

    print(f"\n[4] Calibrating intraday physics engine ...")
    M, net, geom, lyap, ews, stoch, e_star, theta = \
        calibrate_intraday_engine(X_panel, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)

    # ───────────────────────────── V36 SIGNALS ──
    print(f"\n[5] Computing v36 signals ({len(df_1h):,} bars) ...")
    sig_v36 = compute_intraday_signals(X_panel, df_1h, M, net, ews, stoch,
                                       e_star, theta, history_len=48)
    print(f"  v36 signals: {len(sig_v36.columns)} columns")

    # ─────────────────────── V37 PRICE PREDICTION LAYER ──
    print(f"\n[6] Computing v37 price prediction layer ...")
    sig_v37, M_reversal, sigma00_sqrt = compute_price_prediction_signals(
        X_panel, df_1h, M, sig_v36, e_star, sigma_n)
    print(f"  v37 price signals: {len(sig_v37.columns)} columns")

    # ─────────────────────── V38 NORMALISED-λ FEATURES ──
    print(f"\n[7] Computing v38 normalised-λ features ...")
    lam_feat = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    # Report λ_pct distributions (test period)
    lf_test = lam_feat[test_1h]
    lam_raw_test = sig_v37['lambda_price'][test_1h]
    for col, label in [('lambda_pct', f'λ_pct (W={LAM_ROLL_MAIN})'),
                       ('lambda_pct_100', 'λ_pct (W=100)'),
                       ('lambda_pct_500', 'λ_pct (W=500)')]:
        s = lf_test[col]
        print(f"    {label:<22}  mean={s.mean():+.3f}  std={s.std():.3f}  "
              f"  p5={s.quantile(0.05):+.3f}  p95={s.quantile(0.95):+.3f}")

    print(f"    raw λ_price              mean={lam_raw_test.mean():+.4f}  "
          f"  → λ_pct re-centres to 0.5")

    print(f"\n  Mean v38 sizing multipliers (test period, K=1):")
    gam_test = sig_v36['gamma_star_adj'][test_1h]
    lp_test  = lam_feat['lambda_pct'][test_1h]
    size_v36_mean = (1 - gam_test).clip(0,1).mean()
    print(f"    v36_BSDT_scaled  : mean (1−γ*)          = {size_v36_mean:.3f}")
    print(f"    v38_lam_pct      : mean (1−γ*)×λ_pct    = {(size_v36_mean * 0.5):.3f}  "
          f"[λ_pct mean≈0.5]")
    print(f"    v38_lam_boost    : mean (1−γ*)×(0.5+0.5λ_pct) = {(size_v36_mean * 0.75):.3f}")
    print(f"    v38_sym          : mean (1−γ*)×(0.75+0.5λ_pct)= {(size_v36_mean * 1.0):.3f}  "
          f"[neutral — same as v36]")
    print(f"    v38_dlam_soft    : mean (1−γ*)×(0.75+0.25·ok) = {(size_v36_mean * 0.875):.3f}")
    print(f"    v38_full_pct     : mean (1−γ*)×λ_pct×(0.5+0.5·ok) = {(size_v36_mean * 0.375):.3f}")

    # ─────────────────────────── BUILD V34 BASE PORTFOLIO ──
    print("\n[8] Building v34 base portfolio ...")
    h_strats = compute_1h_strategies(df_1h, has_sol)
    df_d = fetch_and_prepare()
    df_d = add_cross_market_features(df_d)
    fund_d = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
    df_d = add_leverage_features(df_d, fund_d)
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
          f"MaxDD: {st_v34['max_dd']:+.1f}%  CAGR: {st_v34['cagr']:+.1f}%")

    # ──────────────────────────── APPLY V38 SIZING ──
    print("\n[9] Applying v38 normalised-λ sizing ...")
    pnl_dict = apply_v38_sizing(pnl_combined_v34, sig_v36, lam_feat)

    # ──────────────────── GROSS SNAPSHOT TABLE ──
    print("\n" + "=" * 100)
    print("  GROSS SNAPSHOT  (K=5, test 2023 → 2026)")
    print("=" * 100)
    print_summary_table(pnl_dict, K=5)

    # ──────────────────── YEAR-ON-YEAR TABLES ──
    print("\n" + "=" * 100)
    print("  YEAR-ON-YEAR  ($100 start, compounding, gross)")
    print("=" * 100)
    for name, pnl in pnl_dict.items():
        if name.startswith('v38_sym') and 'W' in name:
            continue   # skip sensitivity variants in yoy (printed in summary only)
        _yoy_table(name, pnl, K_list=(1, 2, 5, 10))

    # ──────────────── SENSITIVITY: λ WINDOW SIZE ──
    print("\n" + "=" * 100)
    print("  SENSITIVITY: rolling window for λ_pct  (K=5 gross, sym variant)")
    print("=" * 100)
    print_summary_table(
        {k: v for k, v in pnl_dict.items() if 'sym' in k},
        K=5
    )

    # ─────────────────────── λ_pct SIGNAL DIAGNOSTICS ──
    print("\n" + "=" * 100)
    print("  λ_pct SIGNAL DIAGNOSTICS  (2023-2026 test period)")
    print("=" * 100)

    lf_t = lam_feat[test_1h]
    lam_raw_t = sig_v37['lambda_price'][test_1h]
    print(f"\n  λ_pct quintile analysis (W=200):")
    print(f"  {'Quintile':<18}  {'λ_raw_mean':>12}  {'λ_pct_mean':>12}  "
          f"{'#bars':>8}  {'% of test':>10}")
    for q_lo, q_hi, label in [
        (0.0, 0.2, 'Q1 (bot 20%)'),
        (0.2, 0.4, 'Q2'),
        (0.4, 0.6, 'Q3 (median)'),
        (0.6, 0.8, 'Q4'),
        (0.8, 1.0, 'Q5 (top 20%)'),
    ]:
        m = (lf_t['lambda_pct'] >= q_lo) & (lf_t['lambda_pct'] < q_hi)
        n  = m.sum()
        pct = n / len(lf_t) * 100
        lr  = lam_raw_t[m].mean() if n > 0 else 0
        lp  = lf_t['lambda_pct'][m].mean() if n > 0 else 0
        print(f"  {label:<18}  {lr:>12.4f}  {lp:>12.4f}  {n:>8d}  {pct:>9.1f}%")

    # does high λ_pct predict outperformance? — show v34_baseline vs v38_sym
    # split bars into top-50% vs bottom-50% λ_pct
    lf_full = lam_feat.reindex(pnl_combined_v34.index, method='ffill').fillna(0.5)
    sv36_full = sig_v36.reindex(pnl_combined_v34.index, method='ffill').fillna(0.0)
    mask_test_pnl = pnl_combined_v34.index >= TEST_START
    lp_shifted = lf_full['lambda_pct'].shift(1).fillna(0.5)
    top_lam   = (lp_shifted > 0.5) & mask_test_pnl
    bot_lam   = (lp_shifted <= 0.5) & mask_test_pnl

    base_all = pnl_combined_v34[mask_test_pnl]
    print(f"\n  Does λ_pct predict v34_baseline PnL outcome? (K=5)")
    for label, m in [('Top-50% λ  (high price energy)', top_lam),
                     ('Bot-50% λ  (low price energy)',  bot_lam)]:
        sub = (pnl_combined_v34[m] * 5).clip(-0.5, 0.5)
        n   = len(sub)
        ann_ret = float((1 + sub).prod() ** (365 * 24 / max(n, 1)) - 1) * 100
        sr  = float(sub.resample('D').sum().pipe(
            lambda d: d.mean() / d.std() * np.sqrt(365) if d.std() > 0 else 0
        ))
        print(f"    {label:<40}  n={n:>5d}  annualised={ann_ret:>+7.1f}%  Sharpe={sr:>+5.2f}")

    # ─────────────────────────────────────── SAVE ──
    res_path = OUT_DIR_ / 'crypto_bsdt_v38_lambda_norm.json'
    results = {}
    for name, pnl in pnl_dict.items():
        ts = pnl[pnl.index >= TEST_START]
        lev = (ts * 5).clip(-0.5, 0.5)
        ec  = (1 + lev).cumprod()
        n_yrs = len(ts) / (365 * 24)
        cagr  = float(ec.iloc[-1] ** (1 / max(n_yrs, 0.1)) - 1) * 100
        dd    = float((ec / ec.cummax() - 1).min())
        sh    = float(lev.mean() / lev.std() * np.sqrt(ANN_1H)) if lev.std() > 0 else 0.0
        results[name] = {'sharpe_K5': round(sh, 4),
                         'max_dd_K5': round(dd * 100, 2),
                         'cagr_K5':   round(cagr, 2),
                         'final_K5':  round(float(ec.iloc[-1]) * 100, 2)}
    with open(res_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n  Saved → {res_path}")

    print(f"\n  Total runtime: {time.time()-t_start:.0f}s")
    print("=" * 100)


if __name__ == '__main__':
    main()
