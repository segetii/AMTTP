"""
Crypto BSDT v39c — 4-Factor Regime Decomposition
==================================================
Extends v39b (k=1 + mean normalization) with proper treatment of ALL 4 channels.

The channels are now understood as:

    C (Mahal)  = baseline structural distance from equilibrium
    G (Gap)    = structural novelty — energy in PCA residual directions
    A (Vel)    = cascade velocity — how fast the state is moving away from eq.
    T (Novel)  = temporal anticipation — regime transition onset

A's physical interpretation (diagonal h_A = -0.41, 77% negative):
  δ_A = velocity opposing the restoring force.
  High δ_A = momentum state: price moving fast against the mean-reversion pull.

This creates a 2×2 regime table (G × A) for a mean-reversion strategy:
  ─────────────────────────────────────────────────────────────
  G low  × A low  = Normal         → 1.0× (baseline)
  G high × A low  = Novel+Orderly  → BOOST (structural opportunity)
  G low  × A high = Known Cascade  → 0.9× (hold, wait for turn)
  G high × A high = Chaos          → EXIT  (stop loss precaution)
  ─────────────────────────────────────────────────────────────

New sizing mechanisms vs v39b:
  1. G z-score boost  : continuous, proportional to how far G is above its rolling mean
     size *= (1 + BOOST_G_Z * clip(z_G, 0, 3))            [replaces fixed-level boost]
  2. Joint G+T boost  : G and T both above 75th percentile  [new — strongest signal]
     size *= (1 + BOOST_GT)
  3. A kill switch    : a_G > 0.40 AND a_A > 0.70 (chaos)  → 0.2× [new]
  4. A cascade hold   : a_A > 0.70 alone → 0.8×            [mild, wait for reversion]

All strategies are tested in isolation and combinations to cleanly attribute any
Sharpe change to each mechanism.

Output: crypto_bsdt_v39c_regime_decomp.json
Champion baseline: v39b_aG_boost +2.762
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

# ── Sizing constants ──────────────────────────────────────────────────────────
ZSCORE_WINDOW = 500   # rolling window for a_G z-score (bars; matches CALIB_BARS)
BOOST_G_Z     = 0.30  # size += 0.30 per σ above rolling mean of a_G
BOOST_GT      = 0.40  # additional boost when G+T jointly elevated
PCT_WINDOW    = 500   # rolling window for percentile thresholds
G_PCT_THRESH  = 0.75  # percentile threshold for G "elevated"
T_PCT_THRESH  = 0.75  # percentile threshold for T "elevated"
A_KILL_THRESH = 0.70  # a_A threshold for chaos kill switch
G_CHAOS_THRESH= 0.50  # a_G threshold required for chaos (G high + A high = exit)
KILL_SCALE    = 0.20  # size factor in chaos regime (80% reduction)
CASCADE_SCALE = 0.80  # size factor in pure cascade regime (A high, G low)


# ═══════════════════════════════════════════════════════════════════════════════
#  ROLLING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def rolling_zscore(s: pd.Series, window: int) -> pd.Series:
    """Z-score of s relative to its own rolling window. Clipped [-5, 5]."""
    mu  = s.rolling(window, min_periods=50).mean()
    sig = s.rolling(window, min_periods=50).std().clip(lower=0.01)
    return ((s - mu) / sig).clip(-5.0, 5.0).fillna(0.0)


def rolling_pct_rank(s: pd.Series, window: int) -> pd.Series:
    """Rolling percentile rank of s within its own window. Returns [0, 1]."""
    return s.rolling(window, min_periods=50).apply(
        lambda x: (x[:-1] < x[-1]).mean() if len(x) > 1 else 0.5,
        raw=True,
    ).fillna(0.5)


# ═══════════════════════════════════════════════════════════════════════════════
#  V39c SIZING — FULL 4-FACTOR REGIME DECOMPOSITION
# ═══════════════════════════════════════════════════════════════════════════════

def apply_v39c_sizing(base_pnl: pd.Series,
                      sig_v36:  pd.DataFrame,
                      lam_feat: pd.DataFrame,
                      sig_4ch:  pd.DataFrame) -> dict[str, pd.Series]:
    """
    v39c strategies — each mechanism isolated for clean attribution testing.

    All mechanics use lag-1 signals (no lookahead).

    Channel interpretation:
        G high, A low  = structural novelty, orderly  → OPPORTUNITY
        G high, A high = structural novelty + cascade  → CHAOS (exit)
        G low,  A high = known cascade, orderly        → HOLD (mild reduce)
        G low,  A low  = baseline                      → 1×
    """
    idx  = base_pnl.index
    sv36 = sig_v36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lam_feat.reindex(idx, method='ffill').fillna(0.5)
    s4   = sig_4ch.reindex(idx, method='ffill').fillna(0.0)
    base = base_pnl.fillna(0.0)

    # v38_sym_W100 core size (lag-1)
    gam_adj  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lam_pct  = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size_sym = np.clip(1.0 - gam_adj, 0.0, 1.0) * (0.75 + 0.5 * lam_pct)

    # Raw attributions (lag-1)
    a_G = s4['a_G'].shift(1).fillna(0.0)
    a_A = s4['a_A'].shift(1).fillna(0.0)
    a_T = s4['a_T'].shift(1).fillna(0.0)

    # ── Mechanism 1: G z-score continuous boost ───────────────────────────
    # Replaces the fixed-level boost in v39b.
    # Scales size up in proportion to how far above normal G currently is.
    z_G      = rolling_zscore(a_G, ZSCORE_WINDOW)
    boost_Gz = 1.0 + BOOST_G_Z * np.clip(z_G, 0.0, 3.0)

    # ── Mechanism 2: Joint G+T boost ──────────────────────────────────────
    # Fires when BOTH G and T are simultaneously elevated above their 75th pctile.
    # T high = move onset; G high = structure breaking → strongest combined signal.
    pct_G    = rolling_pct_rank(a_G, PCT_WINDOW)
    pct_T    = rolling_pct_rank(a_T, PCT_WINDOW)
    joint_GT = ((pct_G > G_PCT_THRESH) & (pct_T > T_PCT_THRESH)).astype(float)
    boost_GT = 1.0 + BOOST_GT * joint_GT

    # ── Mechanism 3 (original v2 proposal): A kill — simple, any a_A > 0.70 ──
    # Exactly as proposed: risk_scl = 1.0 - 0.70 * (a_A > 0.70)
    # → 1.0 normally, 0.30× whenever a_A fires (no G condition).
    # "replace nothing — new risk gate"
    kill_A_simple = (a_A > A_KILL_THRESH).astype(float)
    risk_scl      = 1.0 - 0.70 * kill_A_simple   # 1.0 normally, 0.30 when A fires

    # ── Mechanism 3 (v39c internal): chaos = joint G high + A high ────────
    # More conservative: only reduces when both G and A are elevated.
    # (resulted in 0 firing bars — G and A are mutually exclusive in data)
    chaos    = ((a_G > G_CHAOS_THRESH) & (a_A > A_KILL_THRESH)).astype(float)
    kill_ch  = 1.0 - (1.0 - KILL_SCALE) * chaos

    # ── Mechanism 4: A cascade-only hold (G low + A high) ─────────────────
    cascade_only = ((a_A > A_KILL_THRESH) & (a_G <= G_CHAOS_THRESH)).astype(float)
    casc_scl     = 1.0 - (1.0 - CASCADE_SCALE) * cascade_only

    pnl = {}

    # ── Reference baselines ───────────────────────────────────────────────
    pnl['v38_sym_W100']    = base * size_sym
    pnl['v39b_aG_boost']   = base * size_sym * (1.0 + 0.50 * (a_G > 0.50).astype(float))

    # ── EXACT PROPOSED COMBINATION (the three mechanisms as-specified) ────
    # boost_G = 1 + 0.30 * clip(z_G, 0, 3)
    # boost_GT = 1 + 0.40 * joint_GT
    # risk_scl = 1 - 0.70 * (a_A > 0.70)   ← simple kill, no G condition
    pnl['v39c_proposed']   = base * size_sym * boost_Gz * boost_GT * risk_scl

    # ── Each mechanism in isolation ───────────────────────────────────────
    pnl['v39c_Gz_only']    = base * size_sym * boost_Gz
    pnl['v39c_GT_only']    = base * size_sym * boost_GT
    pnl['v39c_killA_only'] = base * size_sym * risk_scl      # simple 0.30× kill
    pnl['v39c_cascA_only'] = base * size_sym * casc_scl      # mild 0.80× cascade

    # ── Pairwise combinations ─────────────────────────────────────────────
    pnl['v39c_Gz_killA']   = base * size_sym * boost_Gz * risk_scl
    pnl['v39c_GT_killA']   = base * size_sym * boost_GT * risk_scl
    pnl['v39c_GT_Gz']      = base * size_sym * boost_Gz * boost_GT

    # ── Full with joint-chaos kill (original v39c internal) ───────────────
    pnl['v39c_full_chaos'] = base * size_sym * boost_Gz * boost_GT * kill_ch * casc_scl

    return pnl


# ═══════════════════════════════════════════════════════════════════════════════
#  REGIME DIAGNOSTICS
# ═══════════════════════════════════════════════════════════════════════════════

def print_regime_stats(sig_4ch: pd.DataFrame, test_mask) -> None:
    """Print the 2×2 G×A regime table and mechanism activation rates."""
    s     = sig_4ch[test_mask]
    a_G   = s['a_G']
    a_A   = s['a_A']
    a_T   = s['a_T']

    # Rolling stats (computed as of each bar — forward-fill from training)
    # For diagnostic purposes use full test period stats
    pct75_G = float(a_G.quantile(0.75))
    pct75_T = float(a_T.quantile(0.75))

    g_high = a_G > pct75_G
    t_high = a_T > pct75_T
    a_high = a_A > A_KILL_THRESH

    print(f"\n  4-Factor Regime Table (test period {len(s):,} bars)")
    print(f"  {'Regime':<28}  {'% bars':>7}  {'n bars':>7}")
    print(f"  {'-'*28}  {'-'*7}  {'-'*7}")
    quads = [
        ("G_low  × A_low  (Normal)",    (~g_high) & (~a_high)),
        ("G_high × A_low  (Boost)",       g_high  & (~a_high)),
        ("G_low  × A_high (Cascade)",  (~g_high) &   a_high),
        ("G_high × A_high (Chaos)",      g_high  &   a_high),
    ]
    for label, mask in quads:
        pct = mask.mean() * 100
        n   = mask.sum()
        print(f"  {label:<28}  {pct:>6.1f}%  {n:>7}")

    print(f"\n  Mechanism activation rates (test period):")
    print(f"  G+T joint (both > p75):  {(g_high & t_high).mean()*100:.1f}%  (n={int((g_high & t_high).sum())})")
    print(f"  A kill switch fires:     {a_high.mean()*100:.1f}%  (n={int(a_high.sum())})")

    # a_A distribution detail
    print(f"\n  a_A detailed distribution (kill switch channel):")
    for q in [0.50, 0.75, 0.90, 0.95, 0.99]:
        print(f"    p{int(q*100):>2}: {float(a_A.quantile(q)):.4f}")
    n_fire = (a_A > A_KILL_THRESH).sum()
    print(f"    Fires (a_A > {A_KILL_THRESH}): {n_fire} bars  ({n_fire/len(s)*100:.2f}% of test)")

    # a_G z-score activation
    z_G = rolling_zscore(a_G.reset_index(drop=True), ZSCORE_WINDOW)
    print(f"\n  a_G z-score (rolling {ZSCORE_WINDOW}-bar):")
    for q in [0.25, 0.50, 0.75, 0.90, 0.95]:
        print(f"    p{int(q*100):>2}: z={float(z_G.quantile(q)):+.3f}")
    mean_boost = float((1.0 + BOOST_G_Z * np.clip(z_G, 0, 3)).mean())
    print(f"    Mean size multiplier from Gz boost: {mean_boost:.4f}×")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    t_start = time.time()
    BAR = "=" * 100
    print(BAR)
    print("  CRYPTO BSDT v39c — 4-Factor Regime Decomposition")
    print("  G × A regime table: Normal / Boost / Cascade / Chaos")
    print("  Mechanism 1: G z-score boost (continuous)")
    print("  Mechanism 2: G+T joint boost (structural novelty + trend onset)")
    print("  Mechanism 3: A kill switch (chaos: high G + high A)")
    print("  Mechanism 4: A cascade hold (orderly cascade: high A alone)")
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

    # ── 4a. v36 engine (k=4 for e_t / gamma_star) ─────────────────────────────
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
    print(f"\n[4b] Calibrating k={PCA_K_B} operator for δ_G ...")
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
    print("\n[7] Computing v38 normalised-λ features ...")
    lam_feat = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    # ── 8. Channel means + firing thresholds (k=1) ────────────────────────────
    print(f"\n[8] Calibrating channel means (k={PCA_K_B}) ...")
    mu_norm = calibrate_channel_means(X_panel, calib_mask, M_k1)

    print(f"\n[9] Calibrating firing thresholds (k={PCA_K_B}) ...")
    fire_thresholds = calibrate_firing_thresholds(X_panel, calib_mask, M_k1,
                                                   pct=FIRE_PERCENTILE)

    # ── 10. Four-channel sweep (reuses v39b sweep unchanged) ──────────────────
    print(f"\n[10] Computing four-channel signals ...")
    sig_4ch = compute_four_channel_signals_v39b(
        X_panel, df_1h, M_k1, sig_v36, fire_thresholds, mu_norm)
    print(f"  Signals: {len(sig_4ch.columns)} columns")

    # ── Regime diagnostics ────────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("  REGIME DIAGNOSTICS  (4-factor G × A table)")
    print("=" * 100)
    print_transmission_lag_analysis(sig_4ch, test_1h)
    print_regime_stats(sig_4ch, test_1h)

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

    # ── 12. Apply v39c sizing ──────────────────────────────────────────────────
    print("\n[12] Applying v39c sizing ...")
    pnl_dict = apply_v39c_sizing(pnl_combined_v34, sig_v36, lam_feat, sig_4ch)
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
    res_path = OUT_DIR_ / 'crypto_bsdt_v39c_regime_decomp_v2.json'
    results  = {}
    for name, pnl in pnl_dict.items():
        ts    = pnl[pnl.index >= TEST_START]
        lev   = (ts * 5).clip(-0.5, 0.5)
        ec    = (1 + lev).cumprod()
        n_yrs = len(ts) / (365 * 24)
        cagr  = float(ec.iloc[-1] ** (1 / max(n_yrs, 0.1)) - 1) * 100
        dd    = float((ec / ec.cummax() - 1).min())
        sh    = float(lev.mean() / lev.std() * np.sqrt(ANN_1H)) if lev.std() > 0 else 0.0
        results[name] = dict(sharpe_K5=round(sh, 4), max_dd_K5=round(dd * 100, 2),
                             cagr_K5=round(cagr, 2), final_K5=round(float(ec.iloc[-1]) * 100, 2))

    # Signal summary (for regime stats)
    sig_s = sig_4ch[test_1h]
    sig_summary = {}
    for col in ['a_G', 'a_A', 'a_T', 'a_C']:
        v = sig_s[col].dropna()
        sig_summary[col] = dict(mean=round(float(v.mean()), 6),
                                std=round(float(v.std()), 6),
                                p25=round(float(v.quantile(0.25)), 6),
                                p75=round(float(v.quantile(0.75)), 6),
                                p95=round(float(v.quantile(0.95)), 6))

    with open(res_path, 'w') as f:
        json.dump({'strategies': results, 'signals': sig_summary,
                   'config': {'PCA_K': PCA_K_B,
                               'ZSCORE_WINDOW': ZSCORE_WINDOW,
                               'BOOST_G_Z': BOOST_G_Z,
                               'BOOST_GT': BOOST_GT,
                               'A_KILL_THRESH': A_KILL_THRESH,
                               'G_CHAOS_THRESH': G_CHAOS_THRESH,
                               'KILL_SCALE': KILL_SCALE,
                               'CASCADE_SCALE': CASCADE_SCALE}},
                  f, indent=2)
    print(f"\n  Saved → {res_path}")
    print(f"\n  Total runtime: {time.time() - t_start:.0f}s")
    print("=" * 100)


if __name__ == '__main__':
    main()
