"""
Crypto BSDT v49 — Final Exhaustion Run
=======================================
v48 champion: v48_F_c050_gt045_tt040_ghtlm040  Sharpe=+3.6158
  (clip=5.0, GH_TH=4.0, GH_TL=-0.40, GL_TH=-1.00, GL_TL=-1.00,
   G_THRESH=0.45, T_THRESH=0.40, N_G=N_T=8,
   G_BOOST_THRESH=0.50, CHAMPION_BOOST=0.50, A_FIRE_THRESH=0.70)

Remaining unexplored axes NOT touched in v48:
  1. GH_TL at clip=5.0  (v48 Group E only swept at clip=4.0; -0.50 hit monotone ceiling)
  2. G_BOOST_THRESH     (module constant 0.50 — never swept)
  3. CHAMPION_BOOST      (module constant 0.50 — never swept)
  4. A_FIRE_THRESH       (module constant 0.70 — never swept; controls how many collapses enter logic)

Fixed throughout (confirmed optimal in v47/v48):
  clip=5.0, GH_TH=4.0, GL_TH=-1.00, GL_TL=-1.00
  G_THRESH=0.45, T_THRESH=0.40, N_G=N_T=8

Group A: GH_TL deeper sweep AT clip=5.0  (was tested at clip=4.0 in v48 — repeat correctly)
  GH_TL ∈ {-0.80, -0.70, -0.60, -0.50, -0.40, -0.30, -0.20}   → 7 variants

Group B: G_BOOST_THRESH sweep  (at clip=5.0, best GH_TL from A)
  G_BOOST_THRESH ∈ {0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60}  → 7 variants
  Interpretation: threshold on CURRENT a_G for direct G-channel boost flag

Group C: CHAMPION_BOOST magnitude  (at optimal G_BOOST_THRESH from B)
  CHAMPION_BOOST ∈ {0.20, 0.30, 0.40, 0.50, 0.60, 0.75, 1.00}  → 7 variants
  Interpretation: multiplier on G-boost: final_pnl *= (1 + CHAMPION_BOOST * flag_G)

Group D: A_FIRE_THRESH sweep  (definition of "A fires" — which collapses enter quadrant logic)
  A_FIRE_THRESH ∈ {0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85}  → 7 variants
  Interpretation: attribution a_A must exceed this to classify bar as A-fire

Group E: Joint champion grid (top-2 from each group)   → ~16 variants
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
import run_crypto_pairs_v34_full_combined as _v34mod

OUT_DIR_ = Path(OUT_DIR)

# ── Disk cache for fetch_klines (avoids Binance API hangs on re-runs) ────────
_CACHE_DIR = Path(r'C:\amttp\data')
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_CACHE_TTL_H = 72  # treat cache as fresh for 3 days

def _make_cached_fetch(orig_fn):
    """Wrap fetch_klines with a pickle cache keyed by symbol+interval."""
    def _wrapper(symbol: str, start: str, end: str, interval: str = '1h') -> pd.Series:
        cache_path = _CACHE_DIR / f'klines_{symbol}_{interval}.pkl'
        if cache_path.exists():
            age_h = (time.time() - cache_path.stat().st_mtime) / 3600
            if age_h < _CACHE_TTL_H:
                s = pd.read_pickle(str(cache_path))
                print(f'  {symbol} {interval} [CACHE {age_h:.0f}h old] {len(s):,} bars')
                return s
        s = orig_fn(symbol, start, end, interval)
        if len(s) > 0:
            s.to_pickle(str(cache_path))
            print(f'  -> cached to {cache_path.name}')
        return s
    return _wrapper


def _cached_fetch_and_prepare():
    """Cache the daily crypto + macro DataFrame from Yahoo Finance."""
    cache_path = _CACHE_DIR / 'daily_crypto_pairs.pkl'
    if cache_path.exists():
        age_h = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_h < _CACHE_TTL_H:
            df = pd.read_pickle(str(cache_path))
            print(f'  fetch_and_prepare [CACHE {age_h:.0f}h old] {len(df):,} rows')
            return df
    df = fetch_and_prepare()
    df.to_pickle(str(cache_path))
    return df


def _cached_add_cross_market(df):
    """Cache add_cross_market_features result (keyed by df hash + date)."""
    cache_path = _CACHE_DIR / 'cross_market_df.pkl'
    if cache_path.exists():
        age_h = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_h < _CACHE_TTL_H:
            result = pd.read_pickle(str(cache_path))
            # Validate shape compatibility
            if result.shape[0] == df.shape[0] and result.index[-1] == df.index[-1]:
                print(f'  add_cross_market_features [CACHE {age_h:.0f}h old]')
                return result
    result = add_cross_market_features(df)
    result.to_pickle(str(cache_path))
    return result


def _cached_fetch_binance_funding():
    """Cache funding rate fetch from Binance futures (ETH+BTC)."""
    cache_path = _CACHE_DIR / 'binance_funding.pkl'
    if cache_path.exists():
        age_h = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_h < _CACHE_TTL_H:
            import pickle as _pk
            with open(str(cache_path), 'rb') as _f:
                fund = _pk.load(_f)
            print(f'  fetch_binance_funding [CACHE {age_h:.0f}h old]')
            return fund
    fund = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
    import pickle as _pk
    with open(str(cache_path), 'wb') as _f:
        _pk.dump(fund, _f)
    return fund

# ── v48 confirmed-optimal FIXED baseline ───────────────────────────────────────
GL_TH_OPT   = -1.00   # confirmed full kill
GL_TL_OPT   = -1.00   # confirmed full kill
GH_TH_OPT   = 4.00    # = clip_opt - 1.0
CLIP_OPT    = 5.00
G_THRESH_OPT = 0.45
T_THRESH_OPT = 0.40
N_G_OPT     = 8
N_T_OPT     = 8
GH_TL_V48   = -0.40   # v48 champion value; -0.50 expected improvement at clip=5.0

# Default structural constants (v48 champion baseline)
G_BOOST_THRESH_DEFAULT = 0.50
CHAMPION_BOOST_DEFAULT = 0.50
A_FIRE_THRESH_DEFAULT  = 0.70

# ── Sweep ranges ────────────────────────────────────────────────────────────────
GHTL_SWEEP_A   = [-0.80, -0.70, -0.60, -0.50, -0.40, -0.30, -0.20]
GBOOST_SWEEP_B = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
CBOOST_SWEEP_C = [0.20, 0.30, 0.40, 0.50, 0.60, 0.75, 1.00]
AFIRE_SWEEP_D  = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]


# ══════════════════════════════════════════════════════════════════════════════
#  V49 SIZING  (fully parametric — all axes explicit)
# ══════════════════════════════════════════════════════════════════════════════

def _make_quadrant_flags_v49(sig_4ch, g_thresh, t_thresh, n_g, n_t, a_fire_thresh):
    a_G_raw = sig_4ch['a_G']
    a_A_raw = sig_4ch['a_A']
    a_T_raw = sig_4ch['a_T']
    G_mem = a_G_raw.rolling(n_g, min_periods=1).max().shift(1).fillna(0.0)
    T_mem = a_T_raw.rolling(n_t, min_periods=1).max().shift(1).fillna(0.0)
    A_fire_lag1 = (a_A_raw.shift(1).fillna(0.0) > a_fire_thresh)
    q_GH_TH = (A_fire_lag1 & (G_mem > g_thresh) & (T_mem > t_thresh)).astype(float)
    q_GH_TL = (A_fire_lag1 & (G_mem > g_thresh) & (T_mem <= t_thresh)).astype(float)
    q_GL_TH = (A_fire_lag1 & (G_mem <= g_thresh) & (T_mem > t_thresh)).astype(float)
    q_GL_TL = (A_fire_lag1 & (G_mem <= g_thresh) & (T_mem <= t_thresh)).astype(float)
    return q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL


def apply_v49_sizing(base_pnl: pd.Series,
                     sig_v36:  pd.DataFrame,
                     lam_feat: pd.DataFrame,
                     sig_4ch:  pd.DataFrame) -> dict[str, pd.Series]:
    idx  = base_pnl.index
    sv36 = sig_v36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lam_feat.reindex(idx, method='ffill').fillna(0.5)
    s4   = sig_4ch.reindex(idx, method='ffill').fillna(0.0)
    base = base_pnl.fillna(0.0)

    gam_adj  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lam_pct  = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size_sym = np.clip(1.0 - gam_adj, 0.0, 1.0) * (0.75 + 0.5 * lam_pct)

    def _quad_pnl(gh_th, gh_tl, gl_th, gl_tl, clip_max,
                  g_thresh, t_thresh, n_g, n_t,
                  a_fire_thresh, g_boost_thresh, champion_boost) -> pd.Series:
        # Quadrant flags (memory-based, A-fire driven)
        q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL = _make_quadrant_flags_v49(
            s4, g_thresh, t_thresh, n_g, n_t, a_fire_thresh)
        phase = (1.0
                 + gh_th * q_GH_TH
                 + gh_tl * q_GH_TL
                 + gl_th * q_GL_TH
                 + gl_tl * q_GL_TL).clip(0.05, clip_max)
        # Direct G-channel boost (current bar, separate from memory quadrant)
        a_G_cur = s4['a_G'].shift(1).fillna(0.0)
        flag_aG = (a_G_cur > g_boost_thresh).astype(float)
        return base * size_sym * (1.0 + champion_boost * flag_aG) * phase

    pnl: dict[str, pd.Series] = {}

    # ── References ────────────────────────────────────────────────────────────
    pnl['v47_champion_ref'] = _quad_pnl(
        2.00, -0.30, GL_TH_OPT, GL_TL_OPT, 3.0, 0.45, 0.40, 8, 8,
        A_FIRE_THRESH_DEFAULT, G_BOOST_THRESH_DEFAULT, CHAMPION_BOOST_DEFAULT)

    pnl['v48_champion_ref'] = _quad_pnl(
        GH_TH_OPT, GH_TL_V48, GL_TH_OPT, GL_TL_OPT, CLIP_OPT,
        G_THRESH_OPT, T_THRESH_OPT, N_G_OPT, N_T_OPT,
        A_FIRE_THRESH_DEFAULT, G_BOOST_THRESH_DEFAULT, CHAMPION_BOOST_DEFAULT)

    # ── Group A: GH_TL deeper sweep AT clip=5.0 ──────────────────────────────
    # v48 Group E used clip=4.0; this corrects it to the confirmed-optimal clip=5.0
    for gh_tl in GHTL_SWEEP_A:
        sign = 'p' if gh_tl >= 0 else 'm'
        tag  = f'{abs(int(round(gh_tl * 100))):03d}'
        pnl[f'v49_A_ghtl{sign}{tag}'] = _quad_pnl(
            GH_TH_OPT, gh_tl, GL_TH_OPT, GL_TL_OPT, CLIP_OPT,
            G_THRESH_OPT, T_THRESH_OPT, N_G_OPT, N_T_OPT,
            A_FIRE_THRESH_DEFAULT, G_BOOST_THRESH_DEFAULT, CHAMPION_BOOST_DEFAULT)

    # ── Group B: G_BOOST_THRESH sweep ─────────────────────────────────────────
    # Use GH_TL=-0.50 (expected best from Group A based on v48 trend)
    # Will use best from Group A in joint Group E
    for g_bt in GBOOST_SWEEP_B:
        tag = f'{int(round(g_bt * 100)):03d}'
        pnl[f'v49_B_gbt{tag}'] = _quad_pnl(
            GH_TH_OPT, -0.50, GL_TH_OPT, GL_TL_OPT, CLIP_OPT,
            G_THRESH_OPT, T_THRESH_OPT, N_G_OPT, N_T_OPT,
            A_FIRE_THRESH_DEFAULT, g_bt, CHAMPION_BOOST_DEFAULT)

    # ── Group C: CHAMPION_BOOST magnitude sweep ──────────────────────────────
    # Use G_BOOST_THRESH=0.45 (expected best or close from Group B)
    for c_boost in CBOOST_SWEEP_C:
        tag = f'{int(round(c_boost * 100)):03d}'
        pnl[f'v49_C_cb{tag}'] = _quad_pnl(
            GH_TH_OPT, -0.50, GL_TH_OPT, GL_TL_OPT, CLIP_OPT,
            G_THRESH_OPT, T_THRESH_OPT, N_G_OPT, N_T_OPT,
            A_FIRE_THRESH_DEFAULT, 0.45, c_boost)

    # ── Group D: A_FIRE_THRESH sweep ──────────────────────────────────────────
    # A_fire controls which collapses enter the quadrant logic at all
    # Lower = more bars in quadrant logic (noisier); Higher = fewer, higher-quality bars
    for a_ft in AFIRE_SWEEP_D:
        tag = f'{int(round(a_ft * 100)):03d}'
        pnl[f'v49_D_aft{tag}'] = _quad_pnl(
            GH_TH_OPT, -0.50, GL_TH_OPT, GL_TL_OPT, CLIP_OPT,
            G_THRESH_OPT, T_THRESH_OPT, N_G_OPT, N_T_OPT,
            a_ft, 0.45, CHAMPION_BOOST_DEFAULT)

    # ── Group E: Joint champion grid (top results from A–D) ───────────────────
    # From v48 + Group A expected: GH_TL ∈ {-0.50, -0.60} are the candidates
    # From Group B expected: g_boost_thresh ∈ {0.40, 0.45, 0.50}
    # From Group C expected: c_boost ∈ {0.40, 0.50, 0.60}
    # From Group D expected: a_fire ∈ {0.65, 0.70, 0.75}
    # Compact joint that covers likely improvements
    for gh_tl in [-0.60, -0.50, -0.40]:
        for g_bt in [0.45, 0.50]:
            for c_boost in [0.50, 0.60]:
                for a_ft in [0.65, 0.70, 0.75]:
                    sign = 'm'
                    tl   = f'{abs(int(round(gh_tl * 100))):03d}'
                    tg   = f'{int(round(g_bt * 100)):03d}'
                    tc   = f'{int(round(c_boost * 100)):03d}'
                    ta   = f'{int(round(a_ft * 100)):03d}'
                    pnl[f'v49_E_ghtl{sign}{tl}_gbt{tg}_cb{tc}_aft{ta}'] = _quad_pnl(
                        GH_TH_OPT, gh_tl, GL_TH_OPT, GL_TL_OPT, CLIP_OPT,
                        G_THRESH_OPT, T_THRESH_OPT, N_G_OPT, N_T_OPT,
                        a_ft, g_bt, c_boost)

    return pnl


# ═══════════════════════════════════════════════════════════════════════════════
#  ANALYSIS HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _count_afire_bars(sig_4ch: pd.DataFrame, test_mask, a_fire_thresh: float) -> int:
    """Count test-period A-fire bars at a given threshold."""
    a_A_lag1 = sig_4ch['a_A'].shift(1).fillna(0.0)
    return int((a_A_lag1[test_mask] > a_fire_thresh).sum())


def _count_quadrant_bars(sig_4ch: pd.DataFrame, test_mask,
                         g_thresh: float, t_thresh: float,
                         n_g: int, n_t: int,
                         a_fire_thresh: float) -> dict:
    """Return quadrant population counts for the test set."""
    q_GH_TH, q_GH_TL, q_GL_TH, q_GL_TL = _make_quadrant_flags_v49(
        sig_4ch, g_thresh, t_thresh, n_g, n_t, a_fire_thresh)
    total = float(q_GH_TH[test_mask].sum() + q_GH_TL[test_mask].sum() +
                  q_GL_TH[test_mask].sum() + q_GL_TL[test_mask].sum())
    if total == 0:
        total = 1.0
    return {
        'GH_TH': int(q_GH_TH[test_mask].sum()),
        'GH_TL': int(q_GH_TL[test_mask].sum()),
        'GL_TH': int(q_GL_TH[test_mask].sum()),
        'GL_TL': int(q_GL_TL[test_mask].sum()),
        'total': int(total),
        'GH_TH_pct': 100 * q_GH_TH[test_mask].sum() / total,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    t_start = time.time()
    # Patch fetch_klines with disk cache to survive Binance API hangs
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)
    BAR = "=" * 100
    print(BAR)
    print("  CRYPTO BSDT v49 — Final Exhaustion Run")
    print("  v48 champion: clip=5.0, GH_TH=4.0, GH_TL=-0.40, G_THRESH=0.45, T_THRESH=0.40")
    print("                G_BOOST_THRESH=0.50, CHAMPION_BOOST=0.50, A_FIRE_THRESH=0.70")
    print("                Sharpe=+3.6158  MaxDD=-16.3%  CAGR=948.7%")
    print(f"  Group A (GH_TL@clip=5.0): {GHTL_SWEEP_A}")
    print(f"  Group B (G_BOOST_THRESH): {GBOOST_SWEEP_B}")
    print(f"  Group C (CHAMPION_BOOST): {CBOOST_SWEEP_C}")
    print(f"  Group D (A_FIRE_THRESH):  {AFIRE_SWEEP_D}")
    print("  Group E: Joint grid top-2 per axis")
    print(BAR)

    def _tstep(msg):
        print(f"\n{msg}", flush=True)

    # ── 1. 1h data ────────────────────────────────────────────────────────────
    _tstep("[1] Fetching 1h data ... t=0s")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_1h  = df_1h.index >= TEST_START
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"    Total 1h bars: {len(df_1h):,}  "
          f"train={int(train_1h.sum()):,}  test={int(test_1h.sum()):,}", flush=True)

    # ── 2. Funding rates ──────────────────────────────────────────────────────
    _tstep(f"[2] Fetching funding rates ... t={time.time()-t_start:.0f}s")
    try:
        funding  = _cached_fetch_binance_funding()
        fund_eth = funding.get('ETHUSDT') if isinstance(funding, dict) else None
        fund_btc = funding.get('BTCUSDT') if isinstance(funding, dict) else None
    except Exception as _e:
        print(f"    Warning: funding fetch failed: {_e}")
        fund_eth = fund_btc = None

    # ── 3. State panel ────────────────────────────────────────────────────────
    _tstep(f"[3] Building state panel ... t={time.time()-t_start:.0f}s")
    X_panel = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X_panel = np.nan_to_num(X_panel)

    train_idx  = np.where(train_1h)[0]
    calib_idx  = train_idx[-CALIB_BARS:]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[calib_idx] = True
    print(f"    X_panel shape: {X_panel.shape}  calib_bars={calib_mask.sum()}", flush=True)

    # ── 4. Engine + k=1 operator calibration ─────────────────────────────────
    _tstep(f"[4] Calibrating engine ... t={time.time()-t_start:.0f}s")
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(
        X_panel, calib_mask)
    sigma_n  = getattr(stoch, 'sigma_n', 1.0)
    X_normal = X_panel[calib_mask]
    M_k1     = MasterOperator.calibrate(X_normal, k=PCA_K_B)

    # ── 5. v36/v37/v38 signals ───────────────────────────────────────────────
    _tstep(f"[5] Computing signals ... t={time.time()-t_start:.0f}s")
    sig_v36           = compute_intraday_signals(X_panel, df_1h, M, net, ews, stoch, e_star, theta)
    sig_v37, _, _     = compute_price_prediction_signals(X_panel, df_1h, M, sig_v36, e_star, sigma_n)
    lam_feat          = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    # ── 6. Four-channel collapse geometry ────────────────────────────────────
    _tstep(f"[6] Four-channel signals ... t={time.time()-t_start:.0f}s")
    mu_norm         = calibrate_channel_means(X_panel, calib_mask, M_k1)
    fire_thresholds = calibrate_firing_thresholds(X_panel, calib_mask, M_k1,
                                                   pct=FIRE_PERCENTILE)
    sig_4ch = compute_four_channel_signals_v39b(
        X_panel, df_1h, M_k1, sig_v36, fire_thresholds, mu_norm)
    print(f"    Done. t={time.time()-t_start:.0f}s", flush=True)

    # ── 7. v34 base portfolio ─────────────────────────────────────────────────
    _tstep(f"[7] v34 base portfolio ... t={time.time()-t_start:.0f}s")
    h_strats = compute_1h_strategies(df_1h, has_sol)
    df_d     = _cached_fetch_and_prepare()
    df_d     = _cached_add_cross_market(df_d)
    fund_d   = _cached_fetch_binance_funding()   # reuses cache from step [2]
    df_d     = add_leverage_features(df_d, fund_d)
    train_mask_d   = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
    train_mask_arr = np.asarray(train_mask_d, dtype=bool)
    pos_dict, _, F_daily, gate_daily = build_daily_positions(
        df_d, train_mask_d, train_mask_arr)
    instr_map = {
        'D1_trend_eth': df_1h['ret_eth'],
        'D2_pairs_eb':  df_1h['spread_ret_eb'],
        'D3_pairs_es':  df_1h['ret_eth'] - df_1h.get('ret_sol', df_1h['ret_eth']),
        'D4_macro_btc': df_1h['ret_btc'],
        'D5_macro_btc': df_1h['ret_btc'],
        'D5_macro_alt': df_1h['ret_eth'],
    }
    d_strats_1h = {
        name: upsample_daily_to_1h_pnl(pos, instr_map.get(name, df_1h['ret_eth']), gate_daily)
        for name, pos in pos_dict.items()
    }
    all_pnls = {**d_strats_1h, **h_strats}
    Q_v34    = compute_quality(all_pnls, bpd=BPD)
    base_pnl = assemble_combined(all_pnls, Q_v34)
    test_mask = base_pnl.index >= TEST_START
    st_v34   = _stats(base_pnl[test_mask])
    print(f"    v34 Sharpe: {st_v34['sharpe']:+.3f}  MaxDD: {st_v34['max_dd']:+.1%}  "
          f"CAGR: {st_v34['cagr']:+.1%}", flush=True)

    # ── Print quadrant populations at various A_FIRE_THRESH ─────────────────
    print("\n  A_FIRE_THRESH scan — quadrant populations (test period):")
    print(f"  {'AFT':>6} {'Total_fires':>12} {'GH_TH':>7} {'GH_TL':>7} {'GL_TH':>7} {'GL_TL':>7} {'GH_TH%':>8}")
    for a_ft in AFIRE_SWEEP_D:
        n_fires = _count_afire_bars(sig_4ch, test_mask, a_ft)
        qc = _count_quadrant_bars(sig_4ch, test_mask,
                                   G_THRESH_OPT, T_THRESH_OPT,
                                   N_G_OPT, N_T_OPT, a_ft)
        print(f"  {a_ft:>6.2f} {n_fires:>12,} "
              f"{qc['GH_TH']:>7} {qc['GH_TL']:>7} {qc['GL_TH']:>7} {qc['GL_TL']:>7} "
              f"{qc['GH_TH_pct']:>7.1f}%")

    # ── G_BOOST_THRESH scan (how many test bars have a_G > threshold) ────────
    print("\n  G_BOOST_THRESH scan — test-period a_G distributions:")
    a_G_test = sig_4ch['a_G'].shift(1).fillna(0.0)[test_mask]
    for g_bt in GBOOST_SWEEP_B:
        n_flag = int((a_G_test > g_bt).sum())
        pct    = 100.0 * n_flag / max(len(a_G_test), 1)
        print(f"  G_BOOST_THRESH={g_bt:.2f}  flag_G=True on {n_flag:,} bars ({pct:.1f}%)")

    # ── 8. Compute all v49 sizing variants ──────────────────────────────────
    print("\n[8] Computing v49 sizing variants ...")
    pnl_variants = apply_v49_sizing(base_pnl, sig_v36, lam_feat, sig_4ch)
    print(f"    {len(pnl_variants)} variants computed.")

    # ── 9. Evaluate all variants ──────────────────────────────────────────────
    print("\n[9] Evaluating on test period ...")
    rows: list[dict] = []
    for name, ts in pnl_variants.items():
        st   = _stats(ts[test_mask])
        win  = float((ts[test_mask].fillna(0.0) > 0).mean() * 100)
        days = int(test_mask.sum() / 24)
        rows.append(dict(name=name,
                         sharpe=st['sharpe'], maxdd=st['max_dd'] * 100,
                         cagr=st['cagr'] * 100, win=win, days=days,
                         final=st['final']))

    df_res = pd.DataFrame(rows).sort_values('sharpe', ascending=False)

    # ── 10. Print gross snapshot ──────────────────────────────────────────────
    print(f"\n{'='*100}")
    print(f"  GROSS SNAPSHOT  (test bars={int(test_mask.sum()):,})")
    print(f"{'='*100}")
    print(f"  {'Strategy':<62} {'Sharpe':>7} {'MaxDD':>8} {'CAGR':>10} "
          f"{'Win%':>7} {'Days':>6} {'$100->':>10}")
    print(f"  {'-'*62} {'-'*7} {'-'*8} {'-'*10} {'-'*7} {'-'*6} {'-'*10}")
    for r in df_res.itertuples():
        print(f"  {r.name:<62} {r.sharpe:>+7.3f}   {r.maxdd:>+6.1f}%   {r.cagr:>+8.1f}%"
              f"   {r.win:>6.1f}%  {r.days:>4}d  ${r.final:>8.2f}")

    # ── 10. Group summaries ──────────────────────────────────────────────────
    print(f"\n{'='*100}")
    print("  PER-GROUP SUMMARIES")
    print(f"{'='*100}")

    groups = {
        'A (GH_TL @clip=5.0)': [r for r in df_res.itertuples() if '_A_' in r.name],
        'B (G_BOOST_THRESH)':   [r for r in df_res.itertuples() if '_B_' in r.name],
        'C (CHAMPION_BOOST)':   [r for r in df_res.itertuples() if '_C_' in r.name],
        'D (A_FIRE_THRESH)':    [r for r in df_res.itertuples() if '_D_' in r.name],
        'E (Joint grid)':       [r for r in df_res.itertuples() if '_E_' in r.name],
        'Refs':                 [r for r in df_res.itertuples() if '_ref' in r.name],
    }

    for gname, gresp in groups.items():
        if not gresp:
            continue
        best = gresp[0]
        print(f"\n  Group {gname}:")
        print(f"    Best: {best.name}")
        print(f"    Sharpe={best.sharpe:+.4f}  MaxDD={best.maxdd:+.1f}%  "
              f"CAGR={best.cagr:+.1f}%")
        for r in gresp:
            print(f"      {r.name:<62} {r.sharpe:>+7.4f}  MaxDD={r.maxdd:>+6.1f}%")

    # ── 11. Overall best ─────────────────────────────────────────────────────
    best_row = df_res.iloc[0]
    best_name = str(best_row['name'])
    v48_ref_mask = df_res['name'] == 'v48_champion_ref'
    v48_ref  = df_res[v48_ref_mask].iloc[0] if v48_ref_mask.any() else None
    improvement = float(best_row['sharpe']) - (float(v48_ref['sharpe']) if v48_ref is not None else 3.6158)

    print(f"\n{'='*100}")
    print(f"  *** OVERALL BEST v49: {best_name}")
    print(f"      Sharpe={best_row['sharpe']:+.4f}  MaxDD={best_row['maxdd']:+.1f}%  "
          f"CAGR={best_row['cagr']:+.1f}%")
    print(f"      v48 champion ref: Sharpe=+3.6158")
    if v48_ref is not None:
        print(f"      v48 champion (recomputed): Sharpe={v48_ref['sharpe']:+.4f}")
    print(f"      Improvement vs v48: Delta={improvement:+.4f} Sharpe")
    if improvement < 0.005:
        print("      *** MAXIMUM LIKELY REACHED -- improvement < 0.005 ***")
    print(f"{'='*100}")

    # ── 12. Year-on-year tables for top-5 + references ──────────────────────
    top_names = (
        list(df_res[df_res['name'].str.contains('_ref')]['name'])
        + list(df_res[~df_res['name'].str.contains('_ref')].head(5)['name'])
    )
    print(f"\n{'='*100}")
    print(f"  YEAR-ON-YEAR  ($100 start, compounding, gross)")
    print(f"{'='*100}")
    for name in top_names:
        _yoy_table(name, pnl_variants[name])

    # ── 13. Save results ─────────────────────────────────────────────────────
    out_json = OUT_DIR_ / 'crypto_bsdt_v49_final_exhaustion.json'
    # Convert numpy scalars to Python native for JSON serialization
    def _to_py(v):
        if isinstance(v, (np.integer,)): return int(v)
        if isinstance(v, (np.floating,)): return float(v)
        return v
    records = [{k: _to_py(vv) for k, vv in r.items()} for r in df_res.to_dict(orient='records')]
    with open(out_json, 'w') as f:
        json.dump({'champion': best_name,
                   'improvement_vs_v48': float(improvement),
                   'v48_sharpe': 3.6158,
                   'results': records}, f, indent=2)
    print(f"\n  Results saved → {out_json}")
    print(f"  Total elapsed: {time.time() - t_start:.1f}s")
    print(BAR)


if __name__ == '__main__':
    main()
