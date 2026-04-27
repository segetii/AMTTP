"""
Crypto BSDT v26 - Continuous Allocator Multi-Strategy Portfolio
================================================================

Architecture: continuous mapping from engine state (geom, precursor, cos_theta,
kramers_p) to per-strategy weights via multiplicative AND-gates. No regimes,
no softmax, no W matrix lookup. Five strategies always running; weights are
smooth signed functions of physics state, EWM(span=3) smoothed.

Strategy book:
  S0 trend       v18_smooth blend (existing)            signed
  S1 pairs       mean of P1/P2/P3 stat-arb (existing)   >= 0 only (market-neutral)
  S2 breakout    Donchian 20-in / 10-out on log ETH     signed              [NEW]
  S3 mean_rev    z-score reversion on 5d ETH return     signed              [NEW]
  S4 macro       BTC/ALT macro rotation (existing)      signed

Weight functions (LOCKED design):
  geom_n = sigmoid(rolling_z(geom,      win=252, lag=1))   in [0,1]
  prec_n = sigmoid(rolling_z(precursor, win=252, lag=1))   in [0,1]
  cos    = cos_theta                                       in [-1,+1]
  kp     = kramers_p                                       in [0,1]

  mag_trend    = (1 - geom_n) * (1 - prec_n)
  mag_breakout = kp * (1 - geom_n)
  mag_mr       = (1 - |cos|) * prec_n
  mag_macro    = geom_n * (1 - kp)
  mag_pairs    = geom_n * (1 - kp)

  w_trend     =  sign(cos) * mag_trend
  w_breakout  =  sign(cos) * mag_breakout
  w_mr        = -sign(cos) * mag_mr           # countertrend
  w_macro     =  sign(cos) * mag_macro
  w_pairs     =  mag_pairs                    # never inverted

  W = stack(...) / (|stack|.sum(axis=1) + 1e-8)   # signed L1
  W = W.ewm(span=3).mean()                         # smooth zero-crossings

Final: pnl_v26[t] = lev[t-1] * sum_s W[t-1, s] * pnl_s[t]
"""
from __future__ import annotations
import os, sys, json
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
from pathlib import Path
import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
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
    GAMMA_SCORE_WIN,
)
from run_crypto_pairs_v22 import (
    calibrate_frozen_engine, patch_precursor_scale, emit_global_signals,
    LEV_LO, LEV_HI,
)
from run_crypto_pairs_v23 import run_repr_pipeline
from run_crypto_pairs_v24 import compute_mahal_risk, hard_gate, GATE_SIGMA, GATE_DAMP
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')


# =====================================================================
#   PHASE 1 - NEW STRATEGY MODULES
# =====================================================================

def compute_donchian_breakout(df: pd.DataFrame, win_in: int = 20,
                              win_out: int = 10) -> pd.Series:
    """Donchian channel breakout on log ETH price. Signed daily PnL.

    Position state (computed at close of day t-1, applied to ret_eth[t]):
      +1  if close > rolling max of last `win_in` days (excluding today)
      -1  if close < rolling min of last `win_out` days
       prev otherwise (channel hold)
    Returns daily PnL series indexed like df.
    """
    px = df['log_eth']
    high_in  = px.rolling(win_in,  min_periods=win_in).max().shift(1)
    low_out  = px.rolling(win_out, min_periods=win_out).min().shift(1)
    high_out = px.rolling(win_out, min_periods=win_out).max().shift(1)
    low_in   = px.rolling(win_in,  min_periods=win_in).min().shift(1)

    pos = pd.Series(0.0, index=df.index)
    cur = 0.0
    for i, t in enumerate(df.index):
        p  = px.iloc[i]
        hi = high_in.iloc[i]
        li = low_in.iloc[i]
        ho = high_out.iloc[i]
        lo = low_out.iloc[i]
        if not np.isnan(hi) and p > hi:
            cur = 1.0
        elif not np.isnan(li) and p < li:
            cur = -1.0
        elif cur == 1.0 and not np.isnan(lo) and p < lo:
            cur = 0.0
        elif cur == -1.0 and not np.isnan(ho) and p > ho:
            cur = 0.0
        pos.iloc[i] = cur

    # Apply 1-day lag to position before multiplying with ret
    return get_daily_pnl(pos, df['ret_eth'])


def compute_mean_reversion(df: pd.DataFrame, win: int = 10,
                            z_in: float = 2.0, z_out: float = 0.5) -> pd.Series:
    """Z-score mean reversion on rolling 5d ETH return.
    Position:
      -1 (short) if z > +z_in
      +1 (long)  if z < -z_in
      hold until |z| < z_out, then flat
    Returns daily PnL signed.
    """
    r5 = df['ret_eth'].rolling(5, min_periods=5).sum()
    mu = r5.rolling(win, min_periods=win).mean()
    sd = r5.rolling(win, min_periods=win).std().clip(lower=1e-6)
    z  = ((r5 - mu) / sd).fillna(0.0)

    pos = pd.Series(0.0, index=df.index)
    cur = 0.0
    for i, zv in enumerate(z.values):
        if cur == 0.0:
            if zv >  z_in: cur = -1.0
            elif zv < -z_in: cur = +1.0
        elif cur > 0 and zv >= -z_out:
            cur = 0.0
        elif cur < 0 and zv <=  z_out:
            cur = 0.0
        pos.iloc[i] = cur

    return get_daily_pnl(pos, df['ret_eth'])


# =====================================================================
#   PHASE 2 - CONTINUOUS WEIGHT ENGINE
# =====================================================================

def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50.0, 50.0)))


def _rolling_z(s: pd.Series, win: int = 252, lag: int = 1) -> pd.Series:
    mu = s.rolling(win, min_periods=60).mean().shift(lag)
    sd = s.rolling(win, min_periods=60).std().shift(lag).clip(lower=1e-6)
    return ((s - mu) / sd).clip(-5.0, 5.0).fillna(0.0)


def compute_continuous_weights(F: pd.DataFrame, win: int = 252,
                                smooth_span: int = 3) -> pd.DataFrame:
    """Map engine state F to a (T, 5) signed weight DataFrame.
    Columns: [w_trend, w_pairs, w_breakout, w_mr, w_macro].
    Signed L1 normalized then EWM(span=smooth_span) smoothed.
    """
    geom = F['geom_score'].fillna(0.0)
    prec = F['precursor_score'].fillna(0.0)
    cos  = F['cos_theta'].fillna(0.0).clip(-1.0, 1.0)
    kp   = F['kramers_p'].fillna(0.0).clip(0.0, 1.0)

    geom_n = _sigmoid(_rolling_z(geom, win=win, lag=1))
    prec_n = _sigmoid(_rolling_z(prec, win=win, lag=1))

    sgn      = np.sign(cos.values)
    sgn[sgn == 0] = 1.0
    abs_cos  = np.abs(cos.values)

    # Magnitudes (always >= 0)
    mag_trend    = (1.0 - geom_n.values) * (1.0 - prec_n.values)
    mag_breakout = kp.values * (1.0 - geom_n.values)
    mag_mr       = (1.0 - abs_cos) * prec_n.values
    mag_macro    = geom_n.values * (1.0 - kp.values)
    mag_pairs    = geom_n.values * (1.0 - kp.values)

    # Signed weights
    w_trend     =  sgn * mag_trend
    w_breakout  =  sgn * mag_breakout
    w_mr        = -sgn * mag_mr
    w_macro     =  sgn * mag_macro
    w_pairs     =  mag_pairs                # market-neutral, never inverted

    W = pd.DataFrame({
        'w_trend':    w_trend,
        'w_pairs':    w_pairs,
        'w_breakout': w_breakout,
        'w_mr':       w_mr,
        'w_macro':    w_macro,
    }, index=F.index)

    # Signed L1 normalize (|.|.sum across rows = 1)
    denom = W.abs().sum(axis=1).replace(0.0, np.nan)
    W = W.div(denom, axis=0).fillna(0.0)

    # EWM smoothing at the weight level
    if smooth_span and smooth_span > 1:
        W = W.ewm(span=smooth_span, adjust=False).mean()
        # Re-normalize after smoothing (small drift possible)
        denom2 = W.abs().sum(axis=1).replace(0.0, np.nan)
        W = W.div(denom2, axis=0).fillna(0.0)

    return W


# =====================================================================
#   PHASE 3 - PORTFOLIO ASSEMBLY
# =====================================================================

def build_v26_pnl(strats: dict, W: pd.DataFrame, lev: pd.Series,
                  index: pd.Index) -> pd.Series:
    """pnl_t = lev[t-1] * sum_s W[t-1, s] * pnl_s[t]   (everything 1-day lagged)
    """
    cols = ['w_trend', 'w_pairs', 'w_breakout', 'w_mr', 'w_macro']
    keys = ['trend',   'pairs',   'breakout',   'mr',   'macro']

    W_lag   = W.shift(1).fillna(0.0)
    lev_lag = lev.shift(1).fillna(1.0)

    pnl = pd.Series(0.0, index=index)
    for c, k in zip(cols, keys):
        pnl = pnl + W_lag[c] * strats[k]
    return pnl * lev_lag


# =====================================================================
#   MAIN
# =====================================================================

def main():
    out_dir = Path(OUT_DIR); out_dir.mkdir(parents=True, exist_ok=True)
    print("=" * 96)
    print("  CRYPTO BSDT v26 - Continuous-Allocator Multi-Strategy Portfolio")
    print("  Engine state -> continuous signed weights -> 5 strategies always running")
    print("=" * 96)

    # ---- data ------------------------------------------------------------
    print("\n[1] Loading data ...")
    df = fetch_and_prepare()
    df = add_cross_market_features(df)
    funding = fetch_binance_funding(symbols=['ETHUSDT','BTCUSDT'], start='2020-06-01')
    df = add_leverage_features(df, funding)

    train_mask     = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask      = df.index >= TEST_START
    train_mask_arr = np.asarray(train_mask, dtype=bool)
    print(f"  Train: {df[train_mask].index[0].date()} -> {df[train_mask].index[-1].date()} "
          f"({int(train_mask.sum())}d)  "
          f"Test: {df[test_mask].index[0].date()} -> {df[test_mask].index[-1].date()} "
          f"({int(test_mask.sum())}d)")

    # ---- shared signals --------------------------------------------------
    print("\n[2] Building shared signals (omega, mfls, gamma, phase) ...")
    feats_strat = ['ret_eth_z','ret_btc_z','ret_sol_z','ret_bnb_z',
                   'vol_eth_z','vol_btc_z','btc_dom_z','cross_disp_z']
    feats_ext   = feats_strat + ['ret_spx_z','dvix_z','ret_dxy_z']
    omega_strat, mfls_eth, gamma_eth = compute_bsdt(df, feats_strat, window=60)
    omega_ext,   _,        _         = compute_bsdt(df, feats_ext,   window=60)
    A_eth, A_rank, dA_fast, dA_rank  = compute_activity_signals(mfls_eth, gamma_eth)
    gamma_rank  = compute_gamma_rank(omega_ext, min_periods=60)
    lev_mult    = compute_leverage_dial(gamma_rank)
    ret7  = df['ret_eth'].rolling(7).sum()
    ret3  = df['ret_eth'].rolling(3).sum()
    phase = detect_phase(omega_strat, ret7, ret3, df['btc_dom_z'])

    # ---- existing strategies (v19/v22 reproduction) ---------------------
    print("\n[3] Building existing strategies (S0 trend, S1 pairs, S4 macro) ...")
    pos_A_dir = setup_a_directional(df, omega_strat, mfls_eth, gamma_eth, phase)
    pairs_def = [
        ('P1_ETH_BTC','log_eth','log_btc','ret_eth','ret_btc'),
        ('P2_ETH_SOL','log_eth','log_sol','ret_eth','ret_sol'),
        ('P3_ETH_BNB','log_eth','log_bnb','ret_eth','ret_bnb'),
    ]
    pair_data = {}
    for key, col_a, col_b, ret_a, ret_b in pairs_def:
        sd = compute_rolling_spread_v8(
            df[col_a], df[col_b], df[ret_a], df[ret_b],
            train_mask=train_mask, beta_window=252)
        clf = SpreadUDLClassifier(window=20, n_ref_dirs=100).fit(
            sd['spread'][train_mask].dropna())
        udl_s, _, _ = clf.classify_series(sd['spread'])
        sd['udl_state'] = udl_s
        mval, _ = compute_manifold_validity(sd['z'], sd['sret'])
        sd['manifold_valid'] = mval
        pair_data[key] = sd
    pair_pos = {k: route_pair_v7(omega_strat, A_rank, pair_data[k]['z'],
                                  pair_data[k]['udl_state'], pair_data[k]['poa'],
                                  pair_data[k]['manifold_valid'])
                for k, *_ in pairs_def}
    pos_btc_macro, pos_alt_macro = route_btcalt_macro(df, omega_strat, A_rank, dA_rank)

    pnl_base_dict = {
        'A_directional': get_daily_pnl(pos_A_dir, df['ret_eth']),
        'P1_ETH_BTC':    get_daily_pnl(pair_pos['P1_ETH_BTC'], pair_data['P1_ETH_BTC']['sret']),
        'P2_ETH_SOL':    get_daily_pnl(pair_pos['P2_ETH_SOL'], pair_data['P2_ETH_SOL']['sret']),
        'P3_ETH_BNB':    get_daily_pnl(pair_pos['P3_ETH_BNB'], pair_data['P3_ETH_BNB']['sret']),
        'M1_ALT_macro':  get_daily_pnl(pos_alt_macro, df['ret_eth']),
        'M1_BTC_macro':  get_daily_pnl(pos_btc_macro, df['ret_btc']),
    }

    # S0 trend = v18_smooth (the full blend with leverage)
    V_state  = compute_state_vector(omega_strat, gamma_rank, mfls_eth, dA_fast)
    phi_18s, align_18s = compute_geom_signals_v18_smooth(V_state)
    lev_v18s = apply_geom_penalties_v18(lev_mult, phi_18s, align_18s)
    cs_wts   = compute_cs_weights(pnl_base_dict, window=GAMMA_SCORE_WIN)
    pnl_v10  = pd.Series(0.0, index=df.index)
    for k in pnl_base_dict:
        pnl_v10 += cs_wts[k].shift(1).fillna(1.0/len(pnl_base_dict)) * pnl_base_dict[k]
    pnl_v18s = pnl_v10 * lev_v18s.shift(1).fillna(1.0)

    # S1 pairs = unweighted mean of P1/P2/P3 PnL
    pnl_pairs = (pnl_base_dict['P1_ETH_BTC']
                 + pnl_base_dict['P2_ETH_SOL']
                 + pnl_base_dict['P3_ETH_BNB']) / 3.0

    # S4 macro = mean of BTC + ALT macro
    pnl_macro = (pnl_base_dict['M1_BTC_macro']
                 + pnl_base_dict['M1_ALT_macro']) / 2.0

    # ---- new strategies --------------------------------------------------
    print("\n[4] Building NEW strategies (S2 Donchian, S3 mean reversion) ...")
    pnl_breakout = compute_donchian_breakout(df, win_in=20, win_out=10)
    pnl_mr       = compute_mean_reversion(df, win=10, z_in=2.0, z_out=0.5)

    strats = {
        'trend':    pnl_v18s,
        'pairs':    pnl_pairs,
        'breakout': pnl_breakout,
        'mr':       pnl_mr,
        'macro':    pnl_macro,
    }

    print("\n  Per-strategy STANDALONE Sharpe (test):")
    print(f"    {'strategy':<12}  {'Sharpe':>8}  {'CAGR%':>7}  {'MaxDD%':>8}  {'Active':>7}")
    for k, p in strats.items():
        s = simulate_from_pnl(p[test_mask].fillna(0.0))
        act = int(p[test_mask].abs().gt(1e-9).sum())
        print(f"    {k:<12}  {s['sharpe']:+8.4f}  {100*s['cagr']:+6.2f}%  "
              f"{100*s['max_dd']:+7.2f}%  {act:6d}d")

    # ---- engine signals --------------------------------------------------
    print("\n[5] Running physics engine for state signals ...")
    X_panel = _build_state_panel(df)
    M, net, geom_e, lyap, info, ews, e_star, sigma_n = calibrate_frozen_engine(
        X_panel, train_mask_arr)
    patch_precursor_scale(ews, M, X_panel[train_mask_arr])
    F = emit_global_signals(df, X_panel, M, net, geom_e, lyap, ews, sigma_n)

    print(f"  Engine signal stats [test]:")
    for col in ['geom_score', 'precursor_score', 'cos_theta', 'kramers_p']:
        s = F[col][test_mask].dropna()
        print(f"    {col:<18}  mean={s.mean():+.4f}  std={s.std():.4f}  "
              f"min={s.min():+.4f}  max={s.max():+.4f}")

    # ---- continuous weights ---------------------------------------------
    print("\n[6] Computing continuous weights (full design + ablations) ...")
    W_full   = compute_continuous_weights(F, win=252, smooth_span=3)
    W_raw    = compute_continuous_weights(F, win=252, smooth_span=1)

    print(f"\n  Weight statistics [test, EWM(3)]:")
    print(f"    {'strategy':<12}  {'mean(|w|)':>10}  {'mean(w)':>10}  "
          f"{'sign-flips':>10}  {'%active':>8}")
    for c in W_full.columns:
        ws = W_full[c][test_mask]
        sgns = np.sign(ws.values)
        flips = int(np.sum(np.diff(sgns) != 0))
        pct_active = 100 * (np.abs(ws.values) > 1e-3).sum() / len(ws)
        print(f"    {c:<12}  {ws.abs().mean():10.4f}  {ws.mean():+10.4f}  "
              f"{flips:10d}  {pct_active:7.1f}%")

    # ---- portfolio assembly ----------------------------------------------
    print("\n[7] Assembling portfolio variants ...")
    # v22 reference: run the full v23 pipeline (which is v22 with rolling Layer A)
    print("\n  Reproducing v22 reference:")
    sim_v22, pnl_v22, _ = run_repr_pipeline(
        X_panel, train_mask_arr, df, test_mask, pnl_v18s)

    # Kramers leverage (same formula as v22 Layer 2)
    lev_kramers = (LEV_LO + (LEV_HI - LEV_LO) * F['kramers_p'].fillna(0.5)).clip(LEV_LO, LEV_HI)

    variants = {}
    variants['v22_baseline']    = pnl_v22

    # v26 full design
    variants['v26_full']        = build_v26_pnl(strats, W_full, lev_kramers, df.index)

    # ablations
    variants['v26_no_smooth']   = build_v26_pnl(strats, W_raw,  lev_kramers, df.index)

    strats_no_brk = dict(strats); strats_no_brk['breakout'] = pd.Series(0.0, index=df.index)
    variants['v26_no_breakout'] = build_v26_pnl(strats_no_brk, W_full, lev_kramers, df.index)

    strats_no_mr = dict(strats); strats_no_mr['mr'] = pd.Series(0.0, index=df.index)
    variants['v26_no_meanrev']  = build_v26_pnl(strats_no_mr, W_full, lev_kramers, df.index)

    strats_no_pairs = dict(strats); strats_no_pairs['pairs'] = pd.Series(0.0, index=df.index)
    variants['v26_no_pairs']    = build_v26_pnl(strats_no_pairs, W_full, lev_kramers, df.index)

    # Identity reduction sanity: trend-only with sign(cos)
    sgn_only = np.sign(F['cos_theta'].fillna(0.0).clip(-1, 1).values)
    sgn_only[sgn_only == 0] = 1.0
    W_trend_only = pd.DataFrame({
        'w_trend':    sgn_only,
        'w_pairs':    0.0,
        'w_breakout': 0.0,
        'w_mr':       0.0,
        'w_macro':    0.0,
    }, index=df.index)
    variants['v26_trend_only']  = build_v26_pnl(strats, W_trend_only, lev_kramers, df.index)

    # v26 + v25a Mahal hard gate (final tail layer)
    risk_z = pd.Series(compute_mahal_risk(X_panel, train_mask_arr).values, index=df.index)
    ps_gate = pd.Series(hard_gate(risk_z.values, GATE_SIGMA, GATE_DAMP), index=df.index)
    variants['v26_full_mgate']  = variants['v26_full'] * ps_gate

    # ---- comparison table ------------------------------------------------
    print("\n" + "=" * 96)
    print("  v26 ABLATION TABLE  (test period, K=1 gross)")
    print("=" * 96)
    print(f"  {'Variant':<24}  {'Sharpe':>8}  {'MaxDD%':>8}  {'CAGR%':>7}  "
          f"{'HitRate':>8}  {'Active':>7}  {'Calmar':>7}")
    print("  " + "-" * 84)
    best_sharpe, best_key = -999.0, 'v22_baseline'
    all_sims = {}
    for k, p in variants.items():
        s = simulate_from_pnl(p[test_mask].fillna(0.0))
        all_sims[k] = s
        act = int(p[test_mask].abs().gt(1e-9).sum())
        calmar = s['cagr'] / abs(s['max_dd']) if s['max_dd'] != 0 else float('nan')
        flag = ' <--' if s['sharpe'] > best_sharpe else ''
        if s['sharpe'] > best_sharpe:
            best_sharpe, best_key = s['sharpe'], k
        print(f"  {k:<24}  {s['sharpe']:+8.4f}  {100*s['max_dd']:+7.2f}%  "
              f"{100*s['cagr']:+6.2f}%  {s['hit_rate']:8.4f}  {act:6d}d  "
              f"{calmar:+7.3f}{flag}")
    print(f"\n  Best: {best_key}  Sharpe {best_sharpe:+.4f}")

    # ---- per-strategy contribution analysis ------------------------------
    print(f"\n[8] Per-strategy contribution analysis [v26_full]:")
    W_lag   = W_full.shift(1).fillna(0.0)
    lev_lag = lev_kramers.shift(1).fillna(1.0)
    print(f"    {'strategy':<12}  {'contrib Sh':>11}  {'mean*1e4':>9}  "
          f"{'%abs PnL':>9}  {'sign(corr)':>11}")
    pnl_v26_full = variants['v26_full']
    total_abs = pnl_v26_full[test_mask].abs().sum()
    for c, k in zip(W_full.columns, ['trend','pairs','breakout','mr','macro']):
        contrib = W_lag[c] * strats[k] * lev_lag
        ct = contrib[test_mask].fillna(0.0)
        sh = simulate_from_pnl(ct)['sharpe']
        share = 100 * ct.abs().sum() / max(total_abs, 1e-12)
        # sign sanity: trend should track sign(cos), mr should counter it
        cos_sign = np.sign(F['cos_theta'][test_mask].fillna(0.0).values)
        w_sign   = np.sign(W_full[c][test_mask].values)
        agree    = float((cos_sign == w_sign).mean())
        print(f"    {k:<12}  {sh:+11.4f}  {1e4*ct.mean():+9.3f}  "
              f"{share:8.1f}%  {agree:11.3f}")

    # ---- K-sweep on best -------------------------------------------------
    best_pnl = variants[best_key]
    print(f"\n[9] K-sweep on [{best_key}]:")
    print(f"  {'K':>5}  {'mode':<10}  {'Sharpe':>8}  {'CAGR%':>7}  "
          f"{'Final $':>12}  {'PnL $':>12}  {'MaxDD%':>8}")
    print("  " + "-" * 78)
    for K in (1, 2, 3, 5, 8, 10, 12):
        for mode, bps in (('gross', 0.0), ('net 5bp', 5.0)):
            m = equity_at_K(best_pnl[test_mask].fillna(0.0),
                            K=float(K), tcost_bps=bps, init=1200.0)
            print(f"  {K:5d}  {mode:<10}  {m['sh']:+8.3f}  {100*m['cagr']:+6.2f}%  "
                  f"${m['final']:10,.2f}  ${m['pnl']:+10,.2f}  {100*m['max_dd']:+7.2f}%")

    bK = find_best_K(best_pnl[test_mask].fillna(0.0),
                     tcost_bps=5.0, init=1200.0, max_dd_limit=0.40)
    if bK:
        print(f"\n  Best K net 5bp (MaxDD<=40%): K={bK['K']:.2f}  "
              f"Final ${bK['final']:,.2f}  Sharpe {bK['sh']:+.3f}  "
              f"CAGR {100*bK['cagr']:.1f}%")
    print(f"  v22 reference best K: K=8.75 -> Final $2,649.71 Sharpe +0.679 CAGR 17.9%")

    # ---- save -----------------------------------------------------------
    out = {
        'protocol': 'v26 continuous-allocator multi-strategy',
        'design': 'Engine state -> sigmoid+product weight functions -> EWM(3) smoothed',
        'strategies': list(strats.keys()),
        'variants': {k: {kk: (float(vv) if isinstance(vv, (int,float,np.floating)) else vv)
                         for kk, vv in s.items()}
                     for k, s in all_sims.items()},
        'best_variant': best_key,
        'best_sharpe':  float(best_sharpe),
        'v22_reference_sharpe': float(sim_v22['sharpe']),
        'v22_reference_max_dd': float(sim_v22['max_dd']),
    }
    jp = Path(OUT_DIR) / 'crypto_bsdt_v26_results.json'
    jp.write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Saved -> {jp}")
    print("=" * 96)


if __name__ == "__main__":
    main()
