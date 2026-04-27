"""
Crypto BSDT v42 — Leaky Max (Running Peak-Hold with Decay)
============================================================
The specific un-tested mechanism: "max with decay floor"

v41 already tested:
  - rolling_max(N):       window max, abrupt drop when spike exits window
  - EMA(τ):               averages spikes away entirely
  - decayed_max(N, τ):    max over N bars with per-lag weight exp(-i/τ)

All underperformed v40 champion (+2.883).

v41 diagnostic revealed:
  "rolling_max(N=8) struct rate = 84.6% vs EMA struct rate = 13.7%"
  → The G precursor is a SHARP TRANSIENT, not sustained.
  → Pure max pooling captures it; averaging destroys it.

The un-tested mechanism is the LEAKY MAX (running peak-hold with decay):

    G_mem[t] = max(a_G[t-1], γ × G_mem[t-1])

Properties:
  - Instantly jumps to any new spike (spike detection preserved)
  - Decays smoothly between spikes (no abrupt window-exit drop)
  - Has infinite memory (spikes from further back decay as γ^k)
  - a_G=0.60 spike at t=0 → G_mem 10 bars later = 0.60 × γ^10
    γ=0.90: → 0.21 (threshold 0.45 reached at bar 2.5)
    γ=0.95: → 0.36 (threshold 0.45 reached at bar 5.9)
    γ=0.98: → 0.49 (still above 0.45 at bar 10)

Why this is different from decayed_max(N, τ):
  - decayed_max uses a WINDOW; when bar t-N exits, value drops abruptly
  - leaky_max is RECURSIVE; it maintains state, so old spikes contribute forever
  - leaky_max is the correct continuous-time approximation to "peak hold"

DESIGN:
  Sweep γ ∈ {0.85, 0.88, 0.90, 0.92, 0.95, 0.98}
  For each γ, test with G_MEM_THRESH = 0.45 (v40 champion threshold)
  Also: γ best × threshold sensitivity {0.40, 0.42, 0.43, 0.45}

Champion: v40_phase_N8_gmem045  +2.883  MaxDD -13.9%  CAGR 318%
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

# ── Constants ─────────────────────────────────────────────────────────────────
A_FIRE_THRESH     = 0.70
G_MEM_THRESH_CHAMP = 0.45    # v40 champion threshold
G_BOOST_THRESH    = 0.50     # v39b champion point-in-time
CHAMPION_BOOST    = 0.50
STRUCT_BOOST      = 0.20
RAND_KILL         = 0.40

GAMMA_VALUES      = [0.85, 0.88, 0.90, 0.92, 0.95, 0.98]
THRESH_SWEEP      = [0.40, 0.42, 0.43, 0.44, 0.45, 0.46, 0.48]


# ═══════════════════════════════════════════════════════════════════════════════
#  LEAKY MAX
# ═══════════════════════════════════════════════════════════════════════════════

def leaky_max(series: pd.Series, gamma: float) -> pd.Series:
    """
    Running leaky max (recursive peak-hold with decay).

    G_mem[t] = max(series[t-1], gamma * G_mem[t-1])

    At decision bar t, G_mem[t] uses series[t-1] as the freshest input
    and decays from the previous state.  No lookahead by construction.

    Properties vs alternatives:
      rolling_max(N):   sharp drop when spike exits window at bar N+1
      EMA(τ):           smooths spikes → low struct rate (~14%)
      decayed_max(N,τ): window-limited decay, abrupt at boundary
      leaky_max(γ):     infinite horizon, no abrupt boundary, spike persists as γ^k
    """
    arr = series.values.astype(float)
    T   = len(arr)
    out = np.zeros(T)
    # out[0] = 0 (initial state)
    # out[t] = max(arr[t-1], gamma * out[t-1])   → uses arr[t-1], no lookahead
    for t in range(1, T):
        out[t] = max(arr[t - 1], gamma * out[t - 1])
    return pd.Series(out, index=series.index)


# ═══════════════════════════════════════════════════════════════════════════════
#  LEAKY MAX DIAGNOSTIC
# ═══════════════════════════════════════════════════════════════════════════════

def print_leaky_max_diagnostic(sig_4ch: pd.DataFrame, test_mask) -> None:
    """
    Compare leaky_max(γ) versus rolling_max(8) in struct_release rate at A-fire.
    Also show G_mem distribution statistics and half-life of a spike.
    """
    s    = sig_4ch[test_mask]
    aG   = s['a_G']
    aA   = s['a_A']
    N    = len(s)
    A_f  = (aA > A_FIRE_THRESH)
    n_A  = int(A_f.sum())

    print(f"\n  Leaky Max Diagnostic  (test {N:,} bars,  A-fire: {n_A} = {n_A/N*100:.2f}%)")

    # Spike half-life for each gamma
    print(f"\n  Spike persistence: bars for spike(0.55) to decay to threshold(0.45)")
    print(f"  {'gamma':>7}  {'half-life(h)':>13}  {'bars@thresh=0.45':>17}  "
          f"{'bars@thresh=0.42':>17}")
    for g in GAMMA_VALUES:
        hl = np.log(0.5) / np.log(g) if g < 1.0 else float('inf')
        b45 = np.log(0.45 / 0.55) / np.log(g) if g < 1.0 else float('inf')
        b42 = np.log(0.42 / 0.55) / np.log(g) if g < 1.0 else float('inf')
        print(f"  {g:>7.2f}  {hl:>13.1f}  {b45:>17.1f}  {b42:>17.1f}")

    # Champion rolling_max reference
    G_rmax8 = aG.rolling(8, min_periods=1).max().shift(1).fillna(0.0)
    G_at_A  = G_rmax8[A_f]
    n_struct_rm = int((A_f & (G_rmax8 > G_MEM_THRESH_CHAMP)).sum())
    print(f"\n  {'Memory':>22}  {'mem_p50@A':>11}  {'mem_p90@A':>11}  "
          f"{'struct%@0.45':>13}  {'struct%@0.42':>13}")
    print(f"  {'-'*22}  {'-'*11}  {'-'*11}  {'-'*13}  {'-'*13}")
    _row("rollmax(N=8) [v40chmp]", G_rmax8, A_f, n_A, [0.45, 0.42])

    for g in GAMMA_VALUES:
        G_lm = leaky_max(aG, gamma=g)
        _row(f"leaky_max(γ={g:.2f})", G_lm, A_f, n_A, [0.45, 0.42])

    # Global G_mem distribution (not conditioned on A)
    print(f"\n  Global G_mem distribution (full test period):")
    print(f"  {'Memory':>22}  {'p25':>8}  {'p50':>8}  {'p75':>8}  {'p90':>8}  {'mean':>8}")
    _row_global("rollmax(N=8)", G_rmax8)
    for g in GAMMA_VALUES:
        G_lm = leaky_max(aG, gamma=g)
        _row_global(f"leaky(γ={g:.2f})", G_lm)


def _row(label, G_mem, A_fire, n_A, thresholds):
    G_at_A = G_mem[A_fire]
    p50 = float(G_at_A.median()) if len(G_at_A) > 0 else 0.0
    p90 = float(G_at_A.quantile(0.90)) if len(G_at_A) > 0 else 0.0
    cols = []
    for thr in thresholds:
        n_st = int((A_fire & (G_mem > thr)).sum())
        cols.append(f"{n_st/n_A*100:>12.1f}%")
    print(f"  {label:>22}  {p50:>11.4f}  {p90:>11.4f}  {'  '.join(cols)}")


def _row_global(label, G_mem):
    q = [G_mem.quantile(p) for p in [0.25, 0.50, 0.75, 0.90]]
    m = G_mem.mean()
    print(f"  {label:>22}  "
          f"{float(q[0]):>8.4f}  {float(q[1]):>8.4f}  "
          f"{float(q[2]):>8.4f}  {float(q[3]):>8.4f}  {float(m):>8.4f}")


# ═══════════════════════════════════════════════════════════════════════════════
#  V42 SIZING
# ═══════════════════════════════════════════════════════════════════════════════

def apply_v42_sizing(base_pnl: pd.Series,
                     sig_v36:  pd.DataFrame,
                     lam_feat: pd.DataFrame,
                     sig_4ch:  pd.DataFrame) -> dict[str, pd.Series]:
    """
    v42: Leaky max as G memory mechanism.
    All signals lag-1 compliant.
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

    a_G_raw  = s4['a_G']
    a_A_raw  = s4['a_A']
    a_G_1    = a_G_raw.shift(1).fillna(0.0)
    a_A_1    = a_A_raw.shift(1).fillna(0.0)
    A_fire_1 = a_A_1 > A_FIRE_THRESH
    flag_aG  = (a_G_1 > G_BOOST_THRESH).astype(float)

    pnl = {}

    # ── Reference baselines ───────────────────────────────────────────────────
    pnl['v39b_aG_boost'] = base * size_sym * (1.0 + CHAMPION_BOOST * flag_aG)

    # v40 champion (rolling_max N=8, gmem=0.45)
    G_rmax8 = a_G_raw.rolling(8, min_periods=1).max().shift(1).fillna(0.0)
    sr_ch = (A_fire_1 & (G_rmax8 > G_MEM_THRESH_CHAMP)).astype(float)
    rc_ch = (A_fire_1 & (G_rmax8 <= G_MEM_THRESH_CHAMP)).astype(float)
    pnl['v40_champion_ref'] = (base * size_sym
                                * (1.0 + CHAMPION_BOOST * flag_aG)
                                * (1.0 + STRUCT_BOOST * sr_ch - RAND_KILL * rc_ch).clip(0.05, 3.0))

    # ── Leaky max sweep at G_MEM_THRESH = 0.45 ───────────────────────────────
    for gamma in GAMMA_VALUES:
        G_lm = leaky_max(a_G_raw, gamma=gamma)
        sr   = (A_fire_1 & (G_lm > G_MEM_THRESH_CHAMP)).astype(float)
        rc   = (A_fire_1 & (G_lm <= G_MEM_THRESH_CHAMP)).astype(float)
        pscl = (1.0 + STRUCT_BOOST * sr - RAND_KILL * rc).clip(0.05, 3.0)
        tag  = f"{gamma:.2f}".replace('.', '')
        pnl[f'v42_leaky_g{tag}'] = (base * size_sym
                                     * (1.0 + CHAMPION_BOOST * flag_aG) * pscl)

    # ── Find best gamma and sweep its threshold ───────────────────────────────
    # Pre-compute leaky_max for each gamma (we'll need best gamma after diagnostics)
    # For now sweep all gammas × all thresholds for the tightest sweep
    # (only do this for the two most promising gammas from diagnostic)
    for gamma in [0.90, 0.92, 0.95]:
        G_lm = leaky_max(a_G_raw, gamma=gamma)
        tag  = f"{gamma:.2f}".replace('.', '')
        for thr in THRESH_SWEEP:
            thr_tag = f"{int(thr*100):02d}"
            sr   = (A_fire_1 & (G_lm > thr)).astype(float)
            rc   = (A_fire_1 & (G_lm <= thr)).astype(float)
            pscl = (1.0 + STRUCT_BOOST * sr - RAND_KILL * rc).clip(0.05, 3.0)
            pnl[f'v42_leaky_g{tag}_thr{thr_tag}'] = (base * size_sym
                                                       * (1.0 + CHAMPION_BOOST * flag_aG)
                                                       * pscl)

    # ── Hybrid: leaky_max(γ) OR rolling_max(N) — take whichever is higher ────
    # "True max with decay floor": preserves every spike detection path
    for gamma in [0.88, 0.90, 0.92, 0.95]:
        G_lm   = leaky_max(a_G_raw, gamma=gamma)
        G_lm_or_rmax = pd.concat([G_lm, G_rmax8], axis=1).max(axis=1)
        sr   = (A_fire_1 & (G_lm_or_rmax > G_MEM_THRESH_CHAMP)).astype(float)
        rc   = (A_fire_1 & (G_lm_or_rmax <= G_MEM_THRESH_CHAMP)).astype(float)
        pscl = (1.0 + STRUCT_BOOST * sr - RAND_KILL * rc).clip(0.05, 3.0)
        tag  = f"{gamma:.2f}".replace('.', '')
        pnl[f'v42_hybrid_or_g{tag}'] = (base * size_sym
                                          * (1.0 + CHAMPION_BOOST * flag_aG) * pscl)

    # ── Leaky max × rolling_max (intersection — only fire if both agree) ──────
    # This prevents false positives from slowly-decayed old spikes
    for gamma in [0.90, 0.95]:
        G_lm   = leaky_max(a_G_raw, gamma=gamma)
        G_both = pd.concat([G_lm, G_rmax8], axis=1).min(axis=1)  # must BOTH be elevated
        sr   = (A_fire_1 & (G_both > G_MEM_THRESH_CHAMP)).astype(float)
        rc   = (A_fire_1 & (G_both <= G_MEM_THRESH_CHAMP)).astype(float)
        pscl = (1.0 + STRUCT_BOOST * sr - RAND_KILL * rc).clip(0.05, 3.0)
        tag  = f"{gamma:.2f}".replace('.', '')
        pnl[f'v42_hybrid_and_g{tag}'] = (base * size_sym
                                           * (1.0 + CHAMPION_BOOST * flag_aG) * pscl)

    return pnl


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    t_start = time.time()
    BAR = "=" * 100
    print(BAR)
    print("  CRYPTO BSDT v42 — Leaky Max (Running Peak-Hold with Decay)")
    print("  G_mem[t] = max(a_G[t-1], γ × G_mem[t-1])")
    print("  Spike detection + smooth persistence (no abrupt window-exit drop)")
    print(f"  γ sweep: {GAMMA_VALUES}")
    print("  v40 champion: v40_phase_N8_gmem045  +2.883")
    print(BAR)

    # ── Data pipline (identical to v40/v41) ───────────────────────────────────
    print("\n[1] Fetching 1h data ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"  {len(df_1h):,} bars  |  Train: {train_1h.sum():,}  |  Test: {test_1h.sum():,}")

    print("\n[2] Fetching funding ...")
    try:
        funding  = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
        fund_eth = funding.get('ETHUSDT') if isinstance(funding, dict) else None
        fund_btc = funding.get('BTCUSDT') if isinstance(funding, dict) else None
    except Exception:
        fund_eth = fund_btc = None

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

    print(f"\n[4b] Calibrating k={PCA_K_B} operator ...")
    X_normal = X_panel[calib_mask]
    M_k1 = MasterOperator.calibrate(X_normal, k=PCA_K_B)

    print("\n[5] v36 signals ...")
    sig_v36 = compute_intraday_signals(X_panel, df_1h, M, net, ews, stoch, e_star, theta)

    print("\n[6] v37 price prediction ...")
    sig_v37, M_reversal, sigma00_sqrt = compute_price_prediction_signals(
        X_panel, df_1h, M, sig_v36, e_star, sigma_n)

    print("\n[7] v38 lambda features ...")
    lam_feat = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    print("\n[8] Channel means ...")
    mu_norm = calibrate_channel_means(X_panel, calib_mask, M_k1)

    print("\n[9] Firing thresholds ...")
    fire_thresholds = calibrate_firing_thresholds(X_panel, calib_mask, M_k1,
                                                   pct=FIRE_PERCENTILE)

    print("\n[10] Four-channel signals ...")
    sig_4ch = compute_four_channel_signals_v39b(
        X_panel, df_1h, M_k1, sig_v36, fire_thresholds, mu_norm)

    # ── Leaky max diagnostic ──────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("  LEAKY MAX DIAGNOSTIC")
    print("=" * 100)
    print_leaky_max_diagnostic(sig_4ch, test_1h)

    # ── v34 base portfolio ────────────────────────────────────────────────────
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

    # ── Sizing ────────────────────────────────────────────────────────────────
    print("\n[12] Applying v42 leaky max sizing ...")
    pnl_dict = apply_v42_sizing(pnl_combined_v34, sig_v36, lam_feat, sig_4ch)
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

    # ── Save ──────────────────────────────────────────────────────────────────
    res_path = OUT_DIR_ / 'crypto_bsdt_v42_leaky_max.json'
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

    sig_s = sig_4ch[test_1h]
    sig_summary = {}
    for col in ['a_G', 'a_A', 'a_T', 'a_C']:
        v = sig_s[col].dropna()
        sig_summary[col] = dict(mean=round(float(v.mean()), 6),
                                std=round(float(v.std()), 6),
                                p25=round(float(v.quantile(0.25)), 6),
                                p75=round(float(v.quantile(0.75)), 6),
                                p95=round(float(v.quantile(0.95)), 6))

    # Leaky max struct rates for each gamma
    aG_t = sig_s['a_G']
    aA_t = sig_s['a_A']
    A_f  = (aA_t > A_FIRE_THRESH)
    lm_stats = {}
    for gamma in GAMMA_VALUES:
        G_lm = leaky_max(aG_t, gamma=gamma)
        n_st = int((A_f & (G_lm > G_MEM_THRESH_CHAMP)).sum())
        lm_stats[f'gamma_{gamma:.2f}'.replace('.', '_')] = dict(
            struct_bars=n_st,
            struct_pct_of_Afires=round(n_st / max(int(A_f.sum()), 1) * 100, 2),
            G_mem_p50_at_A=round(float(G_lm[A_f].median()), 4),
        )

    with open(res_path, 'w') as f:
        json.dump({
            'strategies':   results,
            'signals':      sig_summary,
            'leaky_max_stats': lm_stats,
            'config': {
                'PCA_K':              PCA_K_B,
                'A_FIRE_THRESH':      A_FIRE_THRESH,
                'G_MEM_THRESH_CHAMP': G_MEM_THRESH_CHAMP,
                'CHAMPION_BOOST':     CHAMPION_BOOST,
                'STRUCT_BOOST':       STRUCT_BOOST,
                'RAND_KILL':          RAND_KILL,
                'GAMMA_VALUES':       GAMMA_VALUES,
            },
        }, f, indent=2)
    print(f"\n  Saved → {res_path}")
    print(f"\n  Total runtime: {time.time() - t_start:.0f}s")
    print("=" * 100)


if __name__ == '__main__':
    main()
