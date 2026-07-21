"""Best-combo search: v58 gates/interpreter + all top geometry extractors.

Goal
----
Find the strongest combination of:
  - v58 signal interpreter / multi-portfolio stack
  - v58 gates (dynamic θ_G + full §VII/§XXIV/§XVI gates)
  - top geometric extractors: E7, E8, B1, E6, E10

Method
------
1. Rebuild official funded v58 stack exactly as robustness_validation.py.
2. Compute geometry extractor PnLs from the same funded engine/state panel.
3. Convert each extractor to a signed ETH-perp PnL.
4. Vol-match every extractor to the base on calibration only.
5. Exhaustively test all non-empty subsets of extractors, equal-risk averaged,
   added to either:
      - v58_dyn_gth  (dynamic interpreter without full paper gates)
      - v58_full     (dynamic interpreter + full cos/rho/M gates)
6. Sweep an overlay multiplier alpha ∈ {0.25, 0.50, 0.75, 1.00, 1.25, 1.50}
   for each subset.  This is exploratory OOS search, NOT final promotion.

Outputs
-------
  v59_best_combo_search_results.json
"""
from __future__ import annotations
import sys, time, json, itertools
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

from collapse_geometry import Snapshot, MasterOperator                  # noqa: E402
from run_crypto_pairs_v36_intraday_bsdt import (                        # noqa: E402
    CALIB_BARS, BPD,
    build_intraday_state_panel, calibrate_intraday_engine, _stats,
    compute_intraday_signals,
)
from run_crypto_pairs_v37_price_prediction import compute_price_prediction_signals  # noqa: E402
from run_crypto_pairs_v38_lambda_norm import compute_lambda_features              # noqa: E402
from run_crypto_pairs_v34_full_combined import (                        # noqa: E402
    build_1h_df, OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
    compute_1h_strategies, compute_quality, assemble_combined,
    upsample_daily_to_1h_pnl, build_daily_positions,
    add_leverage_features,
)
from run_crypto_pairs_v39_four_channels import (                        # noqa: E402
    FIRE_PERCENTILE, calibrate_firing_thresholds,
)
from run_crypto_pairs_v39b_k1_scaled import (                           # noqa: E402
    compute_four_channel_signals_v39b, calibrate_channel_means, PCA_K_B,
)
from run_robustness_validation import (                                  # noqa: E402
    _build_pnl, _apply_overlays, CORE,
    _make_cached_fetch, _cached_fetch_binance_funding,
    _cached_fetch_and_prepare, _cached_add_cross_market,
)
from corrected_diagnostics import compute_corrected_diagnostics, v58_dynamic_gth  # noqa: E402
import run_crypto_pairs_v34_full_combined as _v34mod                    # noqa: E402

EMA_SPAN_E7 = 32
PATH_WIN_E8 = 32
HISTORY_LEN = 48
CACHE_FG = Path(r'C:\amttp\data\geometric_extractor_engine_arrays_funded_v58_fg.npz')
ALPHAS = [0.25, 0.50, 0.75, 1.00, 1.25, 1.50]


def _trades_per_year(pnl: pd.Series, test_mask: pd.Series) -> float:
    nz = int((pnl[test_mask].abs() > 1e-12).sum())
    yrs = max((pnl[test_mask].index[-1] - pnl[test_mask].index[0]).days / 365.25, 1e-3)
    return nz / yrs


def _metric_row(pnl: pd.Series, test_mask: pd.Series) -> dict:
    s = _stats(pnl[test_mask])
    return dict(sharpe=float(s['sharpe']), maxdd=float(s['max_dd']),
                cagr=float(s['cagr']), trades_per_year=float(_trades_per_year(pnl, test_mask)),
                cum=float(pnl[test_mask].sum()))


def _extractor_pnl(sig: pd.Series, ret_eth: pd.Series) -> pd.Series:
    return np.sign(sig).shift(1).fillna(0.0) * ret_eth.fillna(0.0)


def main():
    BAR = '=' * 100
    print(BAR)
    print("  BEST COMBO SEARCH — v58 interpreter/gates + top geometry extractors")
    print(BAR)
    t0 = time.time()

    # ── 1. official funded state panel ────────────────────────────────
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)
    print("\n[1] data + funded state panel", flush=True)
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    fund = _cached_fetch_binance_funding()
    X = np.nan_to_num(build_intraday_state_panel(df_1h, fund.get('BTCUSDT'), fund.get('ETHUSDT')))
    T_total, N, d = X.shape
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    train_idx = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True
    test_mask = df_1h.index >= TEST_START
    ret_eth = df_1h['ret_eth']
    idx = df_1h.index
    print(f"    bars={T_total:,} train={train_1h.sum():,} test={test_mask.sum():,} N={N} d={d}")

    # ── 2. v58 stack ──────────────────────────────────────────────────
    print(f"\n[2] rebuild official v58 stack t={time.time()-t0:.0f}s", flush=True)
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(X, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)
    M_k1 = MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)
    sig_v36 = compute_intraday_signals(X, df_1h, M, net, ews, stoch, e_star, theta)
    sig_v37, _, _ = compute_price_prediction_signals(X, df_1h, M, sig_v36, e_star, sigma_n)
    lam_feat = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))
    mu_norm = calibrate_channel_means(X, calib_mask, M_k1)
    fire_thr = calibrate_firing_thresholds(X, calib_mask, M_k1, pct=FIRE_PERCENTILE)
    sig_4ch = compute_four_channel_signals_v39b(X, df_1h, M_k1, sig_v36, fire_thr, mu_norm)

    h_strats = compute_1h_strategies(df_1h, has_sol)
    df_d = _cached_fetch_and_prepare()
    df_d = _cached_add_cross_market(df_d)
    fund_d = _cached_fetch_binance_funding()
    df_d = add_leverage_features(df_d, fund_d)
    tmask_d = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
    pos_dict, _, _, gate_daily = build_daily_positions(df_d, tmask_d, np.asarray(tmask_d, dtype=bool))
    instr_map = {
        'D1_trend_eth': df_1h['ret_eth'],
        'D2_pairs_eb':  df_1h['spread_ret_eb'],
        'D3_pairs_es':  df_1h['ret_eth'] - df_1h.get('ret_sol', df_1h['ret_eth']),
        'D4_macro_btc': df_1h['ret_btc'],
        'D5_macro_btc': df_1h['ret_btc'],
        'D5_macro_alt': df_1h['ret_eth'],
    }
    d1h = {n: upsample_daily_to_1h_pnl(p, instr_map.get(n, df_1h['ret_eth']), gate_daily)
           for n, p in pos_dict.items()}
    base_pnl = assemble_combined({**d1h, **h_strats}, compute_quality({**d1h, **h_strats}, bpd=BPD))

    gth_dyn = v58_dynamic_gth(df_1h)
    pnl_v58_dyn = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch,
                             CORE['clip'], CORE['tth'], CORE['aft'], CORE['cb'], CORE['gbt'], gth_dyn)
    diag = compute_corrected_diagnostics(
        X, df_1h, M, lyap, start_idx=0, history_len=168,
        cache_key='v58_default', use_cache=True, verbose=True)
    gates = dict(
        cos=(diag['cos_theta'] > 0.0).astype(float),
        rho=(diag['rho_normalised'] > 0.5).astype(float),
        M=(diag['M_margin'] > 0.0).astype(float),
    )
    pnl_v58_full = _apply_overlays(pnl_v58_dyn, **gates)
    bases = {
        'v58_dyn_gth': pnl_v58_dyn,
        'v58_full': pnl_v58_full,
    }

    # ── 3. funded F/G arrays ──────────────────────────────────────────
    print(f"\n[3] funded F/G arrays t={time.time()-t0:.0f}s", flush=True)
    if CACHE_FG.exists():
        z = np.load(CACHE_FG)
        F_all = z['F_all']; G_all = z['G_all']; valid = z['valid']
        print(f"    loaded {CACHE_FG}")
    else:
        F_all = np.full((T_total, N, d), np.nan, dtype=np.float32)
        G_all = np.full((T_total, N, d), np.nan, dtype=np.float32)
        valid = np.zeros(T_total, dtype=bool)
        t1 = time.time(); n_done = 0
        for t in range(1, T_total):
            try:
                snap = Snapshot(X=X[t], X_prev=X[t-1], history=X[max(0, t-HISTORY_LEN):t])
                F_all[t] = np.asarray(M.pipeline(snap)['F_t'], dtype=np.float32)
                G_all[t] = np.asarray(M.mfls.state_pullback(snap), dtype=np.float32)
                valid[t] = True; n_done += 1
                if n_done % 5000 == 0:
                    print(f"    arrays {n_done:,}/{T_total:,} elapsed={time.time()-t1:.1f}s", flush=True)
            except Exception:
                pass
        CACHE_FG.parent.mkdir(parents=True, exist_ok=True)
        np.savez(CACHE_FG, F_all=F_all, G_all=G_all, valid=valid)

    F_flat = F_all.reshape(T_total, -1)
    G_flat = G_all.reshape(T_total, -1)
    Xt_flat = X.reshape(T_total, -1)
    dX = np.full_like(X, np.nan, dtype=np.float32); dX[:-1] = X[1:] - X[:-1]
    dX_flat = dX.reshape(T_total, -1)
    dX_prev = np.roll(dX_flat, 1, axis=0); dX_prev[0] = np.nan
    Fnorm = np.linalg.norm(F_flat, axis=1)

    # ── 4. extractor signals: E7,E8,B1,E6,E10 ────────────────────────
    print(f"\n[4] compute extractor signals t={time.time()-t0:.0f}s", flush=True)
    sigs: dict[str, pd.Series] = {}

    # E7 EMA force
    alpha_e7 = 2.0 / (EMA_SPAN_E7 + 1)
    Fbar = np.full_like(F_flat, np.nan)
    Fbar[0] = F_flat[0]
    for t in range(1, T_total):
        if np.isnan(F_flat[t]).any():
            Fbar[t] = Fbar[t-1]
        elif np.isnan(Fbar[t-1]).any():
            Fbar[t] = F_flat[t]
        else:
            Fbar[t] = (1.0 - alpha_e7) * Fbar[t-1] + alpha_e7 * F_flat[t]
    sigs['E7_ema_force'] = pd.Series(np.einsum('ti,ti->t', Fbar, dX_prev), index=idx)

    # E8 path integral
    Fpath = np.full_like(F_flat, np.nan)
    csum = np.cumsum(np.nan_to_num(F_flat), axis=0)
    for t in range(PATH_WIN_E8, T_total):
        Fpath[t] = (csum[t] - csum[t - PATH_WIN_E8]) / PATH_WIN_E8
    sigs['E8_path_integral'] = pd.Series(np.einsum('ti,ti->t', Fpath, dX_prev), index=idx)

    # B1 pullback memory
    sigs['B1_pullback_memory'] = pd.Series(np.einsum('ti,ti->t', G_flat, dX_prev), index=idx)

    # E6 energy flux
    Xc = Xt_flat[calib_mask]
    mu_calib = Xc.mean(axis=0)
    Sigma = np.cov(Xc, rowvar=False) + 1e-6 * np.eye(N * d)
    Sigma_inv = np.linalg.inv(Sigma)
    e6 = np.full(T_total, np.nan, dtype=np.float64)
    for t in range(1, T_total):
        if not valid[t]:
            continue
        try:
            e6[t] = float(-(F_flat[t] @ (Sigma_inv @ (Xt_flat[t] - mu_calib))))
        except Exception:
            pass
    sigs['E6_energy_flux'] = pd.Series(e6, index=idx)

    # E10 tangent ridge
    print("    E10 ridge fit...", flush=True)
    e10 = np.full(T_total, np.nan, dtype=np.float64)
    try:
        feat = np.concatenate([F_flat, Fnorm[:, None] * F_flat, Xt_flat * F_flat], axis=1)
        feat = np.nan_to_num(feat)
        calib_msk = calib_mask & valid
        Xfit = feat[calib_msk]
        yfit = ret_eth.shift(-1).reindex(idx).values[calib_msk]
        ok = ~np.isnan(yfit)
        Xfit = Xfit[ok]; yfit = yfit[ok]
        d_feat = Xfit.shape[1]
        lam = 1e-2 * np.trace(Xfit.T @ Xfit) / max(d_feat, 1)
        w = np.linalg.solve(Xfit.T @ Xfit + lam * np.eye(d_feat), Xfit.T @ yfit)
        e10 = feat @ w
    except Exception as e:
        print(f"    E10 failed: {e}")
    sigs['E10_tangent_ridge'] = pd.Series(e10, index=idx)

    extractor_pnls = {n: _extractor_pnl(s, ret_eth).reindex(idx).fillna(0.0)
                      for n, s in sigs.items()}

    # ── 5. exhaustive subset × alpha search ───────────────────────────
    print(f"\n[5] subset × alpha search t={time.time()-t0:.0f}s", flush=True)
    results = []
    base_rows = {name: _metric_row(p, test_mask) for name, p in bases.items()}
    names = list(extractor_pnls.keys())

    for base_name, base in bases.items():
        base_std = base[calib_mask].std()
        # Vol-match each overlay to this base, calib only.
        scaled = {}
        k_map = {}
        for n in names:
            p = extractor_pnls[n]
            k = float(base_std / max(p[calib_mask].std(), 1e-12))
            k_map[n] = k
            scaled[n] = k * p

        for r in range(1, len(names) + 1):
            for subset in itertools.combinations(names, r):
                basket = sum(scaled[n] for n in subset) / len(subset)
                for a in ALPHAS:
                    pnl = base + a * basket
                    m = _metric_row(pnl, test_mask)
                    results.append({
                        'base': base_name,
                        'subset': list(subset),
                        'alpha': a,
                        'k_map': {n: k_map[n] for n in subset},
                        **m,
                        'delta_vs_v58_full': m['sharpe'] - base_rows['v58_full']['sharpe'],
                        'delta_vs_base': m['sharpe'] - base_rows[base_name]['sharpe'],
                    })

    results_sorted = sorted(results, key=lambda x: (x['sharpe'], -abs(x['maxdd'])), reverse=True)

    # ── 6. report ─────────────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  BEST COMBOS (exploratory OOS search)")
    print(BAR)
    print("  Base benchmarks:")
    for name, r in base_rows.items():
        print(f"    {name:<12} Sharpe={r['sharpe']:+.4f}  MaxDD={r['maxdd']:+.1%}  CAGR={r['cagr']:+.1%}")

    print(f"\n  {'Rank':>4} {'Base':<12} {'Subset':<58} {'α':>4} {'Sharpe':>9} {'MaxDD':>8} {'CAGR':>8} {'Δv58':>8}")
    print(f"  {'-'*4} {'-'*12} {'-'*58} {'-'*4} {'-'*9} {'-'*8} {'-'*8} {'-'*8}")
    for i, r in enumerate(results_sorted[:20], 1):
        subset = '+'.join(s.replace('_', '').replace('pathintegral','E8').replace('pullbackmemory','B1') for s in r['subset'])
        if len(subset) > 58:
            subset = subset[:55] + '...'
        print(f"  {i:>4} {r['base']:<12} {subset:<58} {r['alpha']:>4.2f} "
              f"{r['sharpe']:>+9.4f} {r['maxdd']:>+7.1%} {r['cagr']:>+7.1%} {r['delta_vs_v58_full']:>+8.4f}")

    best = results_sorted[0]
    print(f"\n  BEST: base={best['base']}  subset={best['subset']}  alpha={best['alpha']:.2f}")
    print(f"        Sharpe={best['sharpe']:+.4f}  MaxDD={best['maxdd']:+.1%}  "
          f"CAGR={best['cagr']:+.1%}  Δ vs v58_full={best['delta_vs_v58_full']:+.4f}")
    print("        k scalers:")
    for n, k in best['k_map'].items():
        print(f"          {n:<22} {k:.4f}")

    out_path = Path(OUT_DIR) / 'v59_best_combo_search_results.json'
    out_path.write_text(json.dumps({
        'config': {'alphas': ALPHAS, 'ema_span_e7': EMA_SPAN_E7, 'path_win_e8': PATH_WIN_E8, 'core': CORE},
        'base_rows': base_rows,
        'best': best,
        'top20': results_sorted[:20],
        'all_results': results_sorted,
    }, indent=2, default=float))
    print(f"\n  saved -> {out_path}")
    print(f"  total elapsed: {time.time()-t0:.1f}s")
    print(BAR)


if __name__ == '__main__':
    main()
