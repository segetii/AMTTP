"""
Crypto BSDT v39d — G×A Conditional Interaction
================================================
Extends v39c with the correct treatment of Channel A as CONDITIONAL RISK.

Key insight from v39c falsification:
    - Simple A kill (a_A > 0.70 → 0.30×) HURTS: Sharpe 2.660 < base 2.687
    - A is NOT uniformly bullish or bearish
    - A is a REGIME SWITCH: dangerous only when G (structural context) is absent

The correct decomposition:
    HIGH A + LOW  G  →  chaotic, non-structural cascade  →  DANGEROUS → kill
    HIGH A + HIGH G  →  structured stress, fast snapback →  SAFE/BOOST → hold or boost
    LOW  A + HIGH G  →  structural novelty, orderly      →  OPPORTUNITY → boost
    LOW  A + LOW  G  →  baseline                         →  1× baseline

Three mechanisms proposed for testing:

  1. CONDITIONAL KILL:
       kill_A = (a_A > 0.70) & (a_G < 0.30)
       size  *= (1 - 0.70 * kill_A)   → 0.30× on dangerous cascade bars

  2. CONDITIONAL BOOST:
       boost_A = (a_A > 0.70) & (a_G > 0.50)
       size   *= (1 + 0.40 * boost_A) → 1.40× on structured-stress bars

  3. CONTINUOUS INTERACTION:
       size *= (1 + 0.30 * a_G - 0.20 * a_A * (1 - a_G))
       Encodes: A only hurts when G is absent

Champion baseline: v39b_aG_boost  +2.762
v39c best (no A):  v39c_GT_Gz     +2.721

NOTE ON DATA STRUCTURE:
    From v39c diagnostics, G and A are mutually exclusive in this market —
    G_high (>p75) × A_high (>0.70) fires 0 times.
    This means condBoost (a_G > 0.50 & a_A > 0.70) will also fire 0 times.
    THIS IS EXPECTED AND INFORMATIVE — the theory predicts condKill, not condBoost.
    We test all three mechanisms to see which gain survives.
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

# ── Thresholds ────────────────────────────────────────────────────────────────
# Channel A thresholds
A_KILL_THRESH   = 0.70   # a_A threshold — same as v39b/c to maintain comparability
# G conditioning thresholds
G_LOW_THRESH    = 0.30   # "G absent"    — a_G < 0.30 → structural context missing
G_HIGH_THRESH   = 0.50   # "G present"   — a_G > 0.50 → structural context active
# Champion carry-over
G_BOOST_THRESH  = 0.50   # v39b_aG_boost threshold (upper quartile)

# Sizing coefficients
COND_KILL_FRAC  = 0.70   # kill_A: size *= (1 - 0.70 * kill_A)  → 0.30× on danger bars
COND_BOOST_FAC  = 0.40   # boost_A: size *= (1 + 0.40 * boost_A) → 1.40× on struct-stress
CHAMPION_BOOST  = 0.50   # v39b champion: size *= (1 + 0.50 * (a_G > 0.50))
CONT_G_COEFF    = 0.30   # continuous interaction G term
CONT_A_COEFF    = 0.20   # continuous interaction A penalty term


# ═══════════════════════════════════════════════════════════════════════════════
#  ROLLING HELPERS  (identical to v39c)
# ═══════════════════════════════════════════════════════════════════════════════

def rolling_zscore(s: pd.Series, window: int) -> pd.Series:
    mu  = s.rolling(window, min_periods=50).mean()
    sig = s.rolling(window, min_periods=50).std().clip(lower=0.01)
    return ((s - mu) / sig).clip(-5.0, 5.0).fillna(0.0)


# ═══════════════════════════════════════════════════════════════════════════════
#  V39d SIZING — G×A CONDITIONAL INTERACTION
# ═══════════════════════════════════════════════════════════════════════════════

def apply_v39d_sizing(base_pnl: pd.Series,
                      sig_v36:  pd.DataFrame,
                      lam_feat: pd.DataFrame,
                      sig_4ch:  pd.DataFrame) -> dict[str, pd.Series]:
    """
    v39d: Test the correct G×A interaction model.

    The 3 proposed mechanisms plus full ablation suite for clean attribution.
    All signals shifted by 1 bar for no-lookahead compliance.
    """
    idx  = base_pnl.index
    sv36 = sig_v36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lam_feat.reindex(idx, method='ffill').fillna(0.5)
    s4   = sig_4ch.reindex(idx, method='ffill').fillna(0.0)
    base = base_pnl.fillna(0.0)

    # v38 core sizing (lag-1)
    gam_adj  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lam_pct  = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size_sym = np.clip(1.0 - gam_adj, 0.0, 1.0) * (0.75 + 0.5 * lam_pct)

    # Raw channel attributions (lag-1)
    a_G = s4['a_G'].shift(1).fillna(0.0)
    a_A = s4['a_A'].shift(1).fillna(0.0)

    # ── Champion (v39b): fixed upper-quartile G boost ────────────────────────
    # Reference: Sharpe +2.762  (keep exact formula unchanged)
    flag_aG_high  = (a_G > G_BOOST_THRESH).astype(float)   # ~upper quartile

    # ── G conditioning flags ─────────────────────────────────────────────────
    flag_G_low    = (a_G < G_LOW_THRESH).astype(float)      # G absent  (<0.30)
    flag_G_high   = (a_G > G_HIGH_THRESH).astype(float)     # G present (>0.50)

    # ── A firing flag ─────────────────────────────────────────────────────────
    flag_A_fire   = (a_A > A_KILL_THRESH).astype(float)     # 8.88% of bars

    # ── Mechanism 1: CONDITIONAL KILL ────────────────────────────────────────
    # Fires when A fires AND G is absent (structural context missing)
    # → non-structural cascade = dangerous
    flag_condKill = flag_A_fire * flag_G_low                 # A>0.70 & G<0.30
    cond_kill_scl = 1.0 - COND_KILL_FRAC * flag_condKill    # 0.30× on danger bars

    # ── Mechanism 2: CONDITIONAL BOOST ───────────────────────────────────────
    # Fires when A fires AND G is present (structured stress → snapback)
    # Expected to fire 0 times (G and A are mutually exclusive in this market)
    # We test it anyway — data may reveal edge cases or contradict expectation
    flag_condBoost = flag_A_fire * flag_G_high               # A>0.70 & G>0.50
    cond_boost_scl = 1.0 + COND_BOOST_FAC * flag_condBoost  # 1.40× on struct-stress

    # ── Mechanism 3: CONTINUOUS INTERACTION ──────────────────────────────────
    # Encodes: G always adds edge; A only penalises when G is absent
    # Formula: size *= (1 + 0.30 * a_G - 0.20 * a_A * (1 - a_G))
    # → when G=1: term = 1 + 0.30 - 0 = 1.30 (boost)
    # → when G=0: term = 1 + 0    - 0.20*a_A (mild penalty proportional to A)
    cont_scl = (1.0 + CONT_G_COEFF * a_G
                    - CONT_A_COEFF * a_A * (1.0 - a_G)).clip(0.10, 3.0)

    # ── Diagnostic-only: simple kill for comparison ───────────────────────────
    simple_kill_scl = 1.0 - COND_KILL_FRAC * flag_A_fire    # 0.30× unconditional

    pnl = {}

    # ── Reference baselines ───────────────────────────────────────────────────
    pnl['v38_sym_W100']      = base * size_sym
    pnl['v39b_aG_boost']     = base * size_sym * (1.0 + CHAMPION_BOOST * flag_aG_high)

    # ── Simple unconditional kill (v39c baseline — known to hurt) ─────────────
    pnl['v39c_killA_simple'] = base * size_sym * simple_kill_scl

    # ── Mechanism 1: conditional kill in isolation ────────────────────────────
    pnl['v39d_condKill']     = base * size_sym * cond_kill_scl

    # ── Mechanism 2: conditional boost in isolation ───────────────────────────
    pnl['v39d_condBoost']    = base * size_sym * cond_boost_scl

    # ── Mechanism 3: continuous interaction in isolation ──────────────────────
    pnl['v39d_continuous']   = base * size_sym * cont_scl

    # ── Compound: champion G boost + conditional kill ─────────────────────────
    # Hypothesis: isolate G (for boost) and use condKill to protect dangerous A
    pnl['v39d_aGboost_condKill']  = (base * size_sym
                                      * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                      * cond_kill_scl)

    # ── Compound: champion G boost + conditional boost ────────────────────────
    # Hypothesis: G boost + structured-stress boost (likely no-op if condBoost=0)
    pnl['v39d_aGboost_condBoost'] = (base * size_sym
                                      * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                      * cond_boost_scl)

    # ── Compound: champion G boost + continuous interaction ───────────────────
    pnl['v39d_aGboost_continuous']= (base * size_sym
                                      * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                      * cont_scl)

    # ── Compound: condKill + condBoost (full conditional A routing) ───────────
    pnl['v39d_condKill_condBoost']= (base * size_sym
                                      * cond_kill_scl
                                      * cond_boost_scl)

    # ── Compound: all three mechanisms ────────────────────────────────────────
    pnl['v39d_all3']              = (base * size_sym
                                      * cond_kill_scl
                                      * cond_boost_scl
                                      * cont_scl)

    # ── Sensitivity: champion + all3 mechanisms ───────────────────────────────
    pnl['v39d_champion_plus_all3']= (base * size_sym
                                      * (1.0 + CHAMPION_BOOST * flag_aG_high)
                                      * cond_kill_scl
                                      * cond_boost_scl
                                      * cont_scl)

    # ── Threshold sensitivity: condKill with wider G_low bounds ──────────────
    # Tests if a looser G_low definition captures more dangerous bars
    for g_thresh_str, g_thresh in [('040', 0.40), ('050', 0.50)]:
        flag_ck_t = flag_A_fire * (a_G < g_thresh).astype(float)
        scl_t     = 1.0 - COND_KILL_FRAC * flag_ck_t
        pnl[f'v39d_condKill_glo{g_thresh_str}'] = base * size_sym * scl_t

    return pnl


# ═══════════════════════════════════════════════════════════════════════════════
#  CONDITIONAL REGIME DIAGNOSTICS
# ═══════════════════════════════════════════════════════════════════════════════

def print_conditional_regime_stats(sig_4ch: pd.DataFrame, test_mask) -> None:
    """
    Print the conditional G×A regime table with activation rates for all
    three mechanisms.  Critically shows whether condBoost ever fires.
    """
    s   = sig_4ch[test_mask]
    aG  = s['a_G']
    aA  = s['a_A']
    N   = len(s)

    def pct(mask): return f"{mask.mean()*100:5.2f}%  (n={int(mask.sum()):>4})"

    print(f"\n  Conditional G×A Regime Table  (test {N:,} bars)")
    print(f"  {'Condition':<40}  {'%bars / count':>18}")
    print(f"  {'-'*40}  {'-'*18}")

    # Raw marginals
    fire_A    = aA > A_KILL_THRESH
    low_G     = aG < G_LOW_THRESH
    high_G    = aG > G_HIGH_THRESH
    mid_G     = ~low_G & ~high_G

    print(f"  {'A fires  (a_A > 0.70)':<40}  {pct(fire_A)}")
    print(f"  {'G absent (a_G < 0.30)':<40}  {pct(low_G)}")
    print(f"  {'G mid    (0.30 ≤ a_G ≤ 0.50)':<40}  {pct(mid_G)}")
    print(f"  {'G present(a_G > 0.50)':<40}  {pct(high_G)}")
    print()

    # Conditional splits
    print(f"  {'MECH 1 — condKill: A>0.70 & G<0.30':<40}  {pct(fire_A & low_G)}")
    print(f"  {'MECH 2 — condBoost: A>0.70 & G>0.50':<40}  {pct(fire_A & high_G)}")
    print(f"  {'         (A fires + G mid middle)':<40}  {pct(fire_A & mid_G)}")
    print()

    # Threshold sensitivity for condKill
    for g_lo in [0.30, 0.40, 0.50]:
        tag = f"condKill(G<{g_lo:.2f})"
        print(f"  {tag:<40}  {pct(fire_A & (aG < g_lo))}")
    print()

    # a_G distribution within A-firing bars
    aG_fire = aG[fire_A]
    if len(aG_fire) > 0:
        print(f"  a_G distribution conditioned on a_A > 0.70  ({len(aG_fire)} bars):")
        for q, label in [(0.10, 'p10'), (0.25, 'p25'), (0.50, 'p50'),
                         (0.75, 'p75'), (0.90, 'p90')]:
            print(f"    {label}: a_G = {float(aG_fire.quantile(q)):.4f}")
        print(f"    mean: a_G = {float(aG_fire.mean()):.4f}  (vs full-period mean {float(aG.mean()):.4f})")

    print(f"\n  a_A distribution:")
    for q, label in [(0.50,'p50'), (0.75,'p75'), (0.90,'p90'), (0.95,'p95'), (0.99,'p99')]:
        print(f"    {label}: a_A = {float(aA.quantile(q)):.4f}")

    # Continuous interaction values
    cont_mean = float((1.0 + CONT_G_COEFF * aG - CONT_A_COEFF * aA * (1-aG)).mean())
    cont_std  = float((1.0 + CONT_G_COEFF * aG - CONT_A_COEFF * aA * (1-aG)).std())
    print(f"\n  Continuous interaction term: mean={cont_mean:.4f}  std={cont_std:.4f}")
    print(f"  (1.0 = neutral, >1.0 = net boost, <1.0 = net drag)")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    t_start = time.time()
    BAR = "=" * 100
    print(BAR)
    print("  CRYPTO BSDT v39d — G×A Conditional Interaction")
    print("  Testing: A = CONDITIONAL RISK (dangerous only when G is absent)")
    print("  Mech 1: condKill  — a_A>0.70 & a_G<0.30 → 0.30×")
    print("  Mech 2: condBoost — a_A>0.70 & a_G>0.50 → 1.40×")
    print("  Mech 3: continuous — size × (1 + 0.30*G - 0.20*A*(1-G))")
    print("  Champion: v39b_aG_boost +2.762")
    print(BAR)

    # ── 1. Data ────────────────────────────────────────────────────────────────
    print("\n[1] Fetching Binance 1h data ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"  {len(df_1h):,} bars  |  Train: {train_1h.sum():,}  |  Test: {test_1h.sum():,}")

    # ── 2. Funding ─────────────────────────────────────────────────────────────
    print("\n[2] Fetching funding data ...")
    try:
        funding  = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
        fund_eth = funding.get('ETHUSDT') if isinstance(funding, dict) else None
        fund_btc = funding.get('BTCUSDT') if isinstance(funding, dict) else None
    except Exception:
        fund_eth = fund_btc = None

    # ── 3. State panel ─────────────────────────────────────────────────────────
    print("\n[3] Building 8×8 intraday state panel ...")
    X_panel = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X_panel = np.nan_to_num(X_panel)
    print(f"  Shape: {X_panel.shape}")

    # ── 4a. v36 engine ─────────────────────────────────────────────────────────
    train_idx  = np.where(train_1h)[0]
    calib_idx  = train_idx[-CALIB_BARS:]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[calib_idx] = True

    print("\n[4a] Calibrating v36 engine (k=4) ...")
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(
        X_panel, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)

    # ── 4b. k=1 operator for gap channel ──────────────────────────────────────
    X_normal = X_panel[calib_mask]
    print(f"\n[4b] Calibrating k={PCA_K_B} operator for delta_G ...")
    M_k1 = MasterOperator.calibrate(X_normal, k=PCA_K_B)

    # ── 5. v36 signals ─────────────────────────────────────────────────────────
    print(f"\n[5] Computing v36 signals ...")
    sig_v36 = compute_intraday_signals(X_panel, df_1h, M, net, ews, stoch,
                                        e_star, theta)

    # ── 6. v37 price prediction ────────────────────────────────────────────────
    print("\n[6] Computing v37 price prediction layer ...")
    sig_v37, M_reversal, sigma00_sqrt = compute_price_prediction_signals(
        X_panel, df_1h, M, sig_v36, e_star, sigma_n)

    # ── 7. v38 lambda features ─────────────────────────────────────────────────
    print("\n[7] Computing v38 normalised-lambda features ...")
    lam_feat = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    # ── 8. Channel means + firing thresholds ──────────────────────────────────
    print(f"\n[8] Calibrating channel means (k={PCA_K_B}) ...")
    mu_norm = calibrate_channel_means(X_panel, calib_mask, M_k1)

    print(f"\n[9] Calibrating firing thresholds (k={PCA_K_B}) ...")
    fire_thresholds = calibrate_firing_thresholds(X_panel, calib_mask, M_k1,
                                                   pct=FIRE_PERCENTILE)

    # ── 10. Four-channel signals ───────────────────────────────────────────────
    print(f"\n[10] Computing four-channel signals ...")
    sig_4ch = compute_four_channel_signals_v39b(
        X_panel, df_1h, M_k1, sig_v36, fire_thresholds, mu_norm)
    print(f"  Signals: {len(sig_4ch.columns)} columns")

    # ── Regime diagnostics ────────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("  CONDITIONAL G×A REGIME DIAGNOSTICS")
    print("=" * 100)
    print_transmission_lag_analysis(sig_4ch, test_1h)
    print_conditional_regime_stats(sig_4ch, test_1h)

    # ── 11. v34 base portfolio ─────────────────────────────────────────────────
    print("\n[11] Building v34 base portfolio ...")
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

    # ── 12. Apply v39d sizing ──────────────────────────────────────────────────
    print("\n[12] Applying v39d conditional G×A sizing ...")
    pnl_dict = apply_v39d_sizing(pnl_combined_v34, sig_v36, lam_feat, sig_4ch)
    pnl_dict = {'v34_baseline': pnl_combined_v34, **pnl_dict}

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("  GROSS SNAPSHOT  (K=5, 2023 → 2026)")
    print("=" * 100)
    print_summary_table(pnl_dict, K=5)

    print("\n" + "=" * 100)
    print("  YEAR-ON-YEAR  ($100 start, compounding, gross)")
    print("=" * 100)
    for name, pnl in pnl_dict.items():
        _yoy_table(name, pnl)

    # ── Save JSON ──────────────────────────────────────────────────────────────
    res_path = OUT_DIR_ / 'crypto_bsdt_v39d_ga_interaction.json'
    results  = {}
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

    # Signal summary
    sig_s = sig_4ch[test_1h]
    sig_summary = {}
    for col in ['a_G', 'a_A', 'a_T', 'a_C']:
        v = sig_s[col].dropna()
        sig_summary[col] = dict(mean=round(float(v.mean()), 6),
                                std=round(float(v.std()), 6),
                                p5=round(float(v.quantile(0.05)), 6),
                                p25=round(float(v.quantile(0.25)), 6),
                                p75=round(float(v.quantile(0.75)), 6),
                                p95=round(float(v.quantile(0.95)), 6))

    # Regime activation rates
    aG_test = sig_s['a_G']
    aA_test = sig_s['a_A']
    fire_A   = aA_test > A_KILL_THRESH
    regime_stats = {
        'condKill_bars':  int((fire_A & (aG_test < G_LOW_THRESH)).sum()),
        'condKill_pct':   round(float((fire_A & (aG_test < G_LOW_THRESH)).mean() * 100), 3),
        'condBoost_bars': int((fire_A & (aG_test > G_HIGH_THRESH)).sum()),
        'condBoost_pct':  round(float((fire_A & (aG_test > G_HIGH_THRESH)).mean() * 100), 3),
        'simpleKill_bars':int(fire_A.sum()),
        'simpleKill_pct': round(float(fire_A.mean() * 100), 3),
        'aG_mean_when_A_fires': round(float(aG_test[fire_A].mean()), 6) if fire_A.any() else 0.0,
    }

    with open(res_path, 'w') as f:
        json.dump({
            'strategies': results,
            'signals':    sig_summary,
            'regimes':    regime_stats,
            'config': {
                'PCA_K':          PCA_K_B,
                'A_KILL_THRESH':  A_KILL_THRESH,
                'G_LOW_THRESH':   G_LOW_THRESH,
                'G_HIGH_THRESH':  G_HIGH_THRESH,
                'COND_KILL_FRAC': COND_KILL_FRAC,
                'COND_BOOST_FAC': COND_BOOST_FAC,
                'CONT_G_COEFF':   CONT_G_COEFF,
                'CONT_A_COEFF':   CONT_A_COEFF,
            },
        }, f, indent=2)
    print(f"\n  Saved → {res_path}")
    print(f"\n  Total runtime: {time.time() - t_start:.0f}s")
    print("=" * 100)


if __name__ == '__main__':
    main()
