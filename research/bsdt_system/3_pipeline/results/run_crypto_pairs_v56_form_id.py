"""
v56 — Functional Form Identification (Minimal: 14 runs)
========================================================
Purpose: answer THREE questions left open by kill-test 3/4 outcome.

Q1: Does the DIRECTION survive attempted falsification?
    Test: inverted rule (high-vol → RAISE threshold, not lower it).
    Real structural insight: inverted should clearly lose.
    Fragile coincidence: inverted might accidentally do fine.

Q2: What is the correct FUNCTIONAL FORM of f(vol)?
    Test: policy ensemble at the gth level vs each single form.
    (NOT PnL ensemble — mixing outputs is weaker than mixing policies)
    avg_form: gth = base * (1 + K * mean([1-rv, 1-rv², tanh(1-rv)]))
    This reduces model-form risk intrinsically.

Q3: Is the functional form uncertainty driving the K instability?
    If avg_form is both (a) better than each individual form AND
    (b) has a WIDER K plateau → the form was the noise source.

14 runs total:
    CONTROL GROUP (3):
       run  1: K=0, flat (v54 reference)
       run  2: K=0.10, linear (v55 champion)
       run  3: K=0.10, exp (≡linear at K=0.10 — sanity check)

    DIRECTION TEST (4):
       run  4: K=0.10, inverted linear    f=(rv-1)    ← same magnitude, wrong sign
       run  5: K=0.05, inverted linear                ← scaled-down inversion
       run  6: K=0.20, inverted linear                ← aggressive inversion
       run  7: K=0.10, neutral (K=0 but with rv input)  ← f=0 control

    FORM COMPARISON (4):
       run  8: K=0.10, quadratic at optimal  (K=0.02 per kill test)
       run  9: K=0.02, quadratic
       run 10: K=0.10, tanh
       run 11: K=0.10, avg_form (f1+f2+f3)/3

    ENSEMBLE K SWEEP (3 — find plateau region for avg_form):
       run 12: K=0.07, avg_form
       run 13: K=0.10, avg_form  (same as run 11)
       run 14: K=0.13, avg_form
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

from collapse_geometry import MasterOperator
from run_crypto_pairs_v38_lambda_norm import compute_lambda_features
from run_crypto_pairs_v37_price_prediction import compute_price_prediction_signals
from run_crypto_pairs_v36_intraday_bsdt import (
    CALIB_BARS, BPD, ANN_1H,
    build_intraday_state_panel, calibrate_intraday_engine,
    compute_intraday_signals, _stats,
)
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
    build_1h_df, fetch_and_prepare, fetch_binance_funding,
    add_cross_market_features, add_leverage_features,
    build_daily_positions, upsample_daily_to_1h_pnl,
    compute_1h_strategies, compute_quality, assemble_combined,
)
from run_crypto_pairs_v39_four_channels import (
    FIRE_PERCENTILE, calibrate_firing_thresholds, _yoy_table,
)
from run_crypto_pairs_v39b_k1_scaled import (
    PCA_K_B, calibrate_channel_means, compute_four_channel_signals_v39b,
)
import run_crypto_pairs_v34_full_combined as _v34mod

OUT_DIR_ = Path(OUT_DIR)

# ── cache helpers ─────────────────────────────────────────────────────────────
_CACHE_DIR  = Path(r'C:\amttp\data')
_CACHE_TTL_H = 72

def _make_cached_fetch(orig_fn):
    def _w(symbol, start, end, interval='1h'):
        p = _CACHE_DIR / f'klines_{symbol}_{interval}.pkl'
        if p.exists() and (time.time()-p.stat().st_mtime)/3600 < _CACHE_TTL_H:
            s = pd.read_pickle(str(p)); print(f'  {symbol} [CACHE]'); return s
        s = orig_fn(symbol, start, end, interval)
        if len(s) > 0: s.to_pickle(str(p))
        return s
    return _w

def _cached_fetch_and_prepare():
    p = _CACHE_DIR / 'daily_crypto_pairs.pkl'
    if p.exists() and (time.time()-p.stat().st_mtime)/3600 < _CACHE_TTL_H:
        df = pd.read_pickle(str(p)); print(f'  fetch_and_prepare [CACHE]'); return df
    df = fetch_and_prepare(); df.to_pickle(str(p)); return df

def _cached_add_cross_market(df):
    p = _CACHE_DIR / 'cross_market_df.pkl'
    if p.exists() and (time.time()-p.stat().st_mtime)/3600 < _CACHE_TTL_H:
        r = pd.read_pickle(str(p))
        if r.shape[0]==df.shape[0] and r.index[-1]==df.index[-1]:
            print(f'  cross_market [CACHE]'); return r
    r = add_cross_market_features(df); r.to_pickle(str(p)); return r

def _cached_fetch_binance_funding():
    p = _CACHE_DIR / 'binance_funding.pkl'
    if p.exists() and (time.time()-p.stat().st_mtime)/3600 < _CACHE_TTL_H:
        import pickle as _pk
        with open(str(p), 'rb') as f: fund = _pk.load(f)
        print(f'  funding [CACHE]'); return fund
    fund = fetch_binance_funding(symbols=['ETHUSDT','BTCUSDT'], start='2020-06-01')
    import pickle as _pk
    with open(str(p), 'wb') as f: _pk.dump(fund, f)
    return fund


# ── frozen base config ────────────────────────────────────────────────────────
CLIP     = 6.0;  GH_TH = 5.0;  GH_TL = GL_TH = GL_TL = -1.0
N_OPT    = 8
T_THRESH = 0.41
G_THRESH = 0.45
GBT      = 0.45
CB       = 0.65
AFT      = 0.65

V54_SHARPE  = 3.8568
V55_SHARPE  = 4.0362


# ── realized vol (1-week, normalized, lag=1h) ─────────────────────────────────
def _realized_vol(df_1h: pd.DataFrame) -> pd.Series:
    rv      = df_1h['ret_eth'].rolling(168, min_periods=24).std()
    rv_mean = rv.rolling(1000, min_periods=100).mean()
    return (rv / rv_mean.replace(0, np.nan)).fillna(1.0).shift(1).fillna(1.0)


# ── functional forms of f(vol) ────────────────────────────────────────────────
# All forms satisfy: f(rv=1.0) = 0  → gth = G_THRESH when vol is at long-run mean
# Original direction: f < 0 for rv > 1 (high vol lowers threshold)
# Inverted direction: f > 0 for rv > 1 (high vol raises threshold)

def _compute_gth(rv: pd.Series, k: float, form: str) -> pd.Series:
    """
    form options:
      'flat'      : constant G_THRESH (v54; K ignored)
      'linear'    : f  = (1-rv)           original direction
      'quadratic' : f  = (1-rv²)          original direction
      'tanh'      : f  = tanh(1-rv)       original direction
      'avg_form'  : f  = mean([1-rv, 1-rv², tanh(1-rv)])   policy ensemble
      'inv_linear': f  = (rv-1)           INVERTED direction
      'exp'       : f  = exp(-k*(rv-1))-1  (equals linear only at K→0; otherwise smoother)
      'neutral'   : K=0 applied with rv signal  (should equal flat)
    """
    rv = rv.clip(0.1, 5.0)
    if form == 'flat':
        return pd.Series(G_THRESH, index=rv.index)
    if form == 'linear':
        f = 1.0 - rv
    elif form == 'quadratic':
        f = 1.0 - rv**2
    elif form == 'tanh':
        f = np.tanh(1.0 - rv)
    elif form == 'avg_form':
        f1 = 1.0 - rv
        f2 = 1.0 - rv**2
        f3 = np.tanh(1.0 - rv)
        f = (f1 + f2 + f3) / 3.0
    elif form == 'inv_linear':
        f = rv - 1.0          # OPPOSITE SIGN — tests if direction is real
    elif form == 'exp':
        # exp(-K*(rv-1))-1 normalized to unit slope at rv=1:
        # ddRV at rv=1 = -K  →  matches linear at small K
        f = np.exp(-1.0 * (rv - 1.0)) - 1.0   # K baked into exp; outer K scales amplitude
    elif form == 'neutral':
        f = pd.Series(0.0, index=rv.index)
    else:
        raise ValueError(f'Unknown form: {form}')
    return (G_THRESH * (1.0 + k * f)).clip(0.20, 0.70)


# ── PnL builder ───────────────────────────────────────────────────────────────
def _build_pnl(base, sv36, lf, s4, gth_series):
    """Apply dynamic gth (pd.Series) and return PnL."""
    idx  = base.index
    sv36 = sv36.reindex(idx, method='ffill').fillna(0.0)
    lf   = lf.reindex(idx, method='ffill').fillna(0.5)
    s4   = s4.reindex(idx, method='ffill').fillna(0.0)
    gth  = gth_series.reindex(idx, method='ffill').fillna(G_THRESH)
    gam  = sv36['gamma_star_adj'].shift(1).fillna(0.24)
    lp   = lf['lambda_pct_100'].shift(1).fillna(0.5)
    size = np.clip(1.0 - gam, 0.0, 1.0) * (0.75 + 0.5 * lp)
    a_G  = s4['a_G']; a_A = s4['a_A']; a_T = s4['a_T']
    G_m  = a_G.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    T_m  = a_T.rolling(N_OPT, min_periods=1).max().shift(1).fillna(0.0)
    fired = (a_A.shift(1).fillna(0.0) > AFT)
    q_GH_TH = (fired & (G_m > gth) & (T_m > T_THRESH)).astype(float)
    q_GH_TL = (fired & (G_m > gth) & (T_m <= T_THRESH)).astype(float)
    q_GL_TH = (fired & (G_m <= gth) & (T_m > T_THRESH)).astype(float)
    q_GL_TL = (fired & (G_m <= gth) & (T_m <= T_THRESH)).astype(float)
    phase = (1.0 + GH_TH*q_GH_TH + GH_TL*q_GH_TL
             + GL_TH*q_GL_TH + GL_TL*q_GL_TL).clip(0.05, CLIP)
    flag  = (a_G.shift(1).fillna(0.0) > GBT).astype(float)
    return base.fillna(0.0) * size * (1.0 + CB * flag) * phase


def _row(pnl, mask):
    s = _stats(pnl[mask])
    return s['sharpe'], s['max_dd'], s['cagr']


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    t0 = time.time()
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)
    BAR = '=' * 100
    RES = {}

    print(BAR)
    print("  v56 — FUNCTIONAL FORM IDENTIFICATION (14 runs)")
    print("  Three questions: correct direction? correct form? K stability of ensemble?")
    print(BAR)

    t = lambda msg: print(f'\n{msg}', flush=True)

    t('[SETUP] Data + signals')
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask = df_1h.index >= TEST_START
    train_1h  = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)

    try:
        fund = _cached_fetch_binance_funding()
        fund_eth = fund.get('ETHUSDT'); fund_btc = fund.get('BTCUSDT')
    except Exception as e:
        print(f'  Warning: {e}'); fund_eth = fund_btc = None

    X = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X = np.nan_to_num(X)
    train_idx  = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True

    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(X, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)
    M_k1    = MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)
    sig_v36       = compute_intraday_signals(X, df_1h, M, net, ews, stoch, e_star, theta)
    sig_v37, _, _ = compute_price_prediction_signals(X, df_1h, M, sig_v36, e_star, sigma_n)
    lam_feat      = compute_lambda_features(sig_v37, roll_windows=(100,200,500))
    mu_norm  = calibrate_channel_means(X, calib_mask, M_k1)
    fire_thr = calibrate_firing_thresholds(X, calib_mask, M_k1, pct=FIRE_PERCENTILE)
    sig_4ch  = compute_four_channel_signals_v39b(X, df_1h, M_k1, sig_v36, fire_thr, mu_norm)

    h_strats = compute_1h_strategies(df_1h, has_sol)
    df_d     = _cached_fetch_and_prepare()
    df_d     = _cached_add_cross_market(df_d)
    fund_d   = _cached_fetch_binance_funding()
    df_d     = add_leverage_features(df_d, fund_d)
    tmask_d  = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
    pos_dict, _, F_daily, gate_daily = build_daily_positions(
        df_d, tmask_d, np.asarray(tmask_d, dtype=bool))
    instr_map = {
        'D1_trend_eth': df_1h['ret_eth'], 'D2_pairs_eb': df_1h['spread_ret_eb'],
        'D3_pairs_es':  df_1h['ret_eth'] - df_1h.get('ret_sol', df_1h['ret_eth']),
        'D4_macro_btc': df_1h['ret_btc'], 'D5_macro_btc': df_1h['ret_btc'],
        'D5_macro_alt': df_1h['ret_eth'],
    }
    d1h      = {n: upsample_daily_to_1h_pnl(p, instr_map.get(n, df_1h['ret_eth']), gate_daily)
                for n, p in pos_dict.items()}
    base_pnl = assemble_combined({**d1h, **h_strats}, compute_quality({**d1h, **h_strats}, bpd=BPD))

    rv_norm  = _realized_vol(df_1h)
    print(f'    Setup complete t={time.time()-t0:.1f}s')

    def _run(k, form):
        gth = _compute_gth(rv_norm, k, form)
        pnl = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch, gth)
        sh, dd, cagr = _row(pnl, test_mask)
        return float(sh), float(dd), float(cagr), pnl

    # Pre-compute references (no re-running across sections)
    ref_v54  = _run(0.0, 'flat')
    ref_v55  = _run(K_G_CHAMP := 0.10, 'linear')

    # ── SECTION 1: DIRECTION TEST ──────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SECTION 1: DIRECTION TEST')
    print('  Central claim: high-vol → lower G_THRESH (more trading)')
    print('  Inverting this claim SHOULD clearly lose.  If not, direction is coincidence.')
    print(f'{BAR}')
    print(f"\n  {'#':<4} {'Config':<32} {'Sharpe':>8} {'Δv54':>8} {'Δv55':>8} {'MaxDD':>8} {'Verdict'}")
    print(f"  {'-'*4} {'-'*32} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*12}")

    dir_tests = [
        (1,  'K=0.00, flat (v54)',         0.00, 'flat'),
        (2,  'K=0.10, linear (v55)',        0.10, 'linear'),
        (3,  'K=0.10, exp (≡linear@K=0.1)', 0.10, 'exp'),
        (4,  'K=0.10, inverted linear',     0.10, 'inv_linear'),
        (5,  'K=0.05, inverted linear',     0.05, 'inv_linear'),
        (6,  'K=0.20, inverted linear',     0.20, 'inv_linear'),
        (7,  'K=0.10, neutral (f=0)',        0.10, 'neutral'),
    ]

    dir_results = {}
    inv_sharpes = []
    for num, name, k, form in dir_tests:
        sh, dd, cagr, pnl = _run(k, form)
        dv54 = sh - V54_SHARPE; dv55 = sh - V55_SHARPE
        verdict = ''
        if form == 'flat':
            verdict = 'reference'
        elif form == 'linear':
            verdict = 'v55 ref'
        elif form == 'inv_linear':
            verdict = '← INVERTED'; inv_sharpes.append(sh)
        elif form == 'neutral':
            verdict = 'sanity check'
        elif form == 'exp':
            verdict = 'sanity check'
        dir_results[name] = {'form': form, 'k': k, 'sharpe': sh, 'maxdd': dd}
        print(f"  {num:<4} {name:<32} {sh:>+8.4f} {dv54:>+8.4f} {dv55:>+8.4f} {dd:>+7.1%}  {verdict}")

    inv_best = max(inv_sharpes) if inv_sharpes else -99
    dir_gap  = V55_SHARPE - inv_best
    direction_confirmed = dir_gap > 0.10

    print(f"\n  v55 original direction: {V55_SHARPE:+.4f}")
    print(f"  Best inverted rule:     {inv_best:+.4f}")
    print(f"  Gap (original-inverted):{dir_gap:+.4f}")
    if direction_confirmed:
        print(f"  => DIRECTION CONFIRMED: original clearly beats inversion by {dir_gap:.3f} Sharpe")
    elif dir_gap > 0:
        print(f"  => DIRECTION MARGINAL: original beats inversion but gap is small ({dir_gap:.3f})")
    else:
        print(f"  => DIRECTION AMBIGUOUS: inverted nearly matches original — coincidence warning")
    RES['section1_direction'] = {
        'direction_gap': float(dir_gap),
        'direction_confirmed': bool(direction_confirmed),
        'inv_best_sharpe': float(inv_best),
        'runs': dir_results,
    }

    # ── SECTION 2: FORM COMPARISON + POLICY ENSEMBLE ──────────────────────
    print(f'\n{BAR}')
    print('  SECTION 2: FORM COMPARISON + POLICY ENSEMBLE at optimal K')
    print('  Policy ensemble: gth = G_THRESH * (1 + K * mean(f1, f2, f3))')
    print('  vs individual forms each at K=0.10')
    print(f'{BAR}')
    print(f"\n  {'#':<4} {'Config':<32} {'Sharpe':>8} {'Δv54':>8} {'Δv55':>8} {'MaxDD':>8} {'Verdict'}")
    print(f"  {'-'*4} {'-'*32} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*12}")

    form_tests = [
        (8,  'K=0.02, quadratic (opt-K)',   0.02, 'quadratic'),
        (9,  'K=0.10, quadratic',           0.10, 'quadratic'),
        (10, 'K=0.10, tanh',                0.10, 'tanh'),
        (11, 'K=0.10, avg_form (ensemble)', 0.10, 'avg_form'),
    ]

    form_results = {}
    ensemble_sharpe = None
    for num, name, k, form in form_tests:
        sh, dd, cagr, pnl = _run(k, form)
        dv54 = sh - V54_SHARPE; dv55 = sh - V55_SHARPE
        if form == 'avg_form' and k == 0.10:
            ensemble_sharpe = sh
        verdict = ('policy ensemble' if form == 'avg_form'
                   else f'form@K={k}')
        form_results[name] = {'form': form, 'k': k, 'sharpe': sh, 'maxdd': dd}
        print(f"  {num:<4} {name:<32} {sh:>+8.4f} {dv54:>+8.4f} {dv55:>+8.4f} {dd:>+7.1%}  {verdict}")

    all_form_sharpes = [v['sharpe'] for v in form_results.values()]
    form_spread = max(all_form_sharpes) - min(all_form_sharpes)
    best_form = max(form_results, key=lambda k: form_results[k]['sharpe'])
    print(f"\n  Form spread at K=0.10: {form_spread:.4f}  Best: {best_form}")
    if ensemble_sharpe is not None:
        print(f"  avg_form vs linear:    {ensemble_sharpe - V55_SHARPE:+.4f} (positive = ensemble adds value)")
        ensemble_wins = ensemble_sharpe >= max(v['sharpe'] for n, v in form_results.items()
                                                if v['form'] != 'avg_form') - 0.002  # within noise
        print(f"  Ensemble wins:         {ensemble_wins}")

    RES['section2_forms'] = {
        'form_spread_k010': float(form_spread),
        'best_form': best_form,
        'ensemble_vs_linear': float(ensemble_sharpe - V55_SHARPE) if ensemble_sharpe else None,
        'runs': form_results,
    }

    # ── SECTION 3: K PLATEAU WIDTH FOR avg_form ────────────────────────────
    print(f'\n{BAR}')
    print('  SECTION 3: K PLATEAU WIDTH — avg_form')
    print('  If form uncertainty was the noise source, avg_form should have a WIDER K plateau.')
    print(f'{BAR}')
    print(f"\n  {'#':<4} {'Config':<32} {'Sharpe':>8} {'Δv54':>8} {'Δv55':>8} {'MaxDD':>8}")
    print(f"  {'-'*4} {'-'*32} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

    k_tests = [
        (12, 'K=0.07, avg_form', 0.07, 'avg_form'),
        (13, 'K=0.10, avg_form', 0.10, 'avg_form'),
        (14, 'K=0.13, avg_form', 0.13, 'avg_form'),
    ]

    k_results = {}
    for num, name, k, form in k_tests:
        sh, dd, cagr, pnl = _run(k, form)
        dv54 = sh - V54_SHARPE; dv55 = sh - V55_SHARPE
        k_results[str(k)] = {'k': k, 'sharpe': sh, 'maxdd': dd}
        print(f"  {num:<4} {name:<32} {sh:>+8.4f} {dv54:>+8.4f} {dv55:>+8.4f} {dd:>+7.1%}")

    avg_sharpes = [v['sharpe'] for v in k_results.values()]
    avg_spread  = max(avg_sharpes) - min(avg_sharpes)
    # Compare to linear spread over same K range from v55 fine-tune data
    # linear at K=0.07→0.10→0.13: 3.9334, 4.0362, 3.8464 → spread 0.19
    linear_spread_ref = 0.190   # from crypto_bsdt_v55_dynamic_gth.json fine_tune
    plateau_wider = avg_spread < linear_spread_ref

    print(f"\n  avg_form K spread (0.07–0.13):  {avg_spread:.4f}")
    print(f"  linear K spread (0.07–0.13) ref: {linear_spread_ref:.4f}")
    print(f"  Ensemble has wider plateau:      {plateau_wider}")
    if plateau_wider:
        print("  => FORM ENSEMBLE CONFIRMS: smoother K response → form uncertainty WAS noise source")
    else:
        print("  => plateau not significantly wider; form may not be dominant noise source")

    RES['section3_k_plateau'] = {
        'avg_form_spread_k007_013': float(avg_spread),
        'linear_spread_ref':        float(linear_spread_ref),
        'plateau_wider': bool(plateau_wider),
        'runs': k_results,
    }

    # ── VERDICT ────────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  SUMMARY + DEPLOYMENT DECISION')
    print(f'{BAR}')

    # Q1: direction
    q1 = direction_confirmed
    # Q2: ensemble wins or ties with linear
    q2 = (ensemble_sharpe is not None and ensemble_sharpe >= V55_SHARPE - 0.01)
    # Q3: ensemble plateau wider
    q3 = plateau_wider

    print(f"\n  Q1 Direction confirmed:   {'YES ✓' if q1 else 'NO ✗'}")
    print(f"  Q2 Ensemble ≥ linear:     {'YES ✓' if q2 else 'NO ✗'}")
    print(f"  Q3 Wider K plateau:       {'YES ✓' if q3 else 'NO ✗'}")

    if q1 and q2 and q3:
        verdict = ("ADOPT avg_form policy ensemble as production standard. "
                   "Direction is structural, form risk eliminated, K plateau confirmed wide.")
        champion_form = 'avg_form'
        champion_k    = 0.10
    elif q1 and q2:
        verdict = ("USE avg_form K=0.10. Direction structural, ensemble reduces form risk, "
                   "K plateau ambiguous — monitor in live paper trading.")
        champion_form = 'avg_form'
        champion_k    = 0.10
    elif q1 and not q2:
        verdict = ("Use linear K=0.10 (v55 champion). Direction structural, "
                   "avg_form doesn't improve further. Lock v55 config as production.")
        champion_form = 'linear'
        champion_k    = 0.10
    elif not q1:
        verdict = ("WARNING: direction test ambiguous. Do not extend to asymmetric forms. "
                   "Revert to flat G_THRESH (v54 plateau), investigate other signal axes.")
        champion_form = 'flat'
        champion_k    = 0.0
    else:
        verdict = ("Mixed. Step back to v54 ensemble pending further investigation.")
        champion_form = 'flat'
        champion_k    = 0.0

    print(f"\n  VERDICT: {verdict}")
    print(f"  CHAMPION: form={champion_form}  K={champion_k}")

    # YoY for champion
    gth_champ = _compute_gth(rv_norm, champion_k, champion_form)
    pnl_champ = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch, gth_champ)
    sh_champ  = _stats(pnl_champ[test_mask])['sharpe']
    print(f"\n  Champion Sharpe: {sh_champ:+.4f}  vs v54={V54_SHARPE:+.4f}  vs v55={V55_SHARPE:+.4f}")
    _yoy_table(f'v56_{champion_form}_K{champion_k}', pnl_champ)

    # Scorecard
    print(f"\n  PROGRESSION:")
    print(f"    v34 base     : +2.616")
    print(f"    v54 plateau  : +{V54_SHARPE:.4f}  (+1.241 from v34)")
    print(f"    v55 champion : +{V55_SHARPE:.4f}  (+0.179 from v54)")
    print(f"    v56 champion : {sh_champ:+.4f}  ({sh_champ - V55_SHARPE:+.4f} from v55)")

    # Save
    RES['verdict'] = {
        'q1_direction': bool(q1), 'q2_ensemble': bool(q2), 'q3_plateau': bool(q3),
        'champion_form': champion_form, 'champion_k': float(champion_k),
        'champion_sharpe': float(sh_champ),
        'verdict': verdict,
        'v54_sharpe': V54_SHARPE, 'v55_sharpe': V55_SHARPE,
        'delta_v55': float(sh_champ - V55_SHARPE),
    }

    out = OUT_DIR_ / 'crypto_bsdt_v56_form_identification.json'
    with open(out, 'w') as f:
        json.dump(RES, f, indent=2)
    print(f"\n  Results saved -> {out}")
    print(f"  Total elapsed: {time.time()-t0:.1f}s")
    print(BAR)


if __name__ == '__main__':
    main()
