"""Official v58_full benchmark with OTHER top geometric extractors (excluding E7).

User request: E7 already tested. Test the other top extractors from §26.7 against
v58_full multi-portfolio:
  - E10 tangent ridge
  - E8 path integral
  - B1 pullback memory (ranked above E6, included for completeness)
  - E6 energy flux (next true closed-form extractor)

All overlays are additive:
  pnl_candidate = pnl_v58_full + k_i * pnl_extractor_i
where k_i = std(v58_full_calib) / std(extractor_calib), fitted on calib only.

Also tests equal-risk ensembles of the three/four overlays.
"""
from __future__ import annotations
import sys, time, json
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

PATH_WIN_E8 = 32
HISTORY_LEN = 48
CACHE_FG = Path(r'C:\amttp\data\geometric_extractor_engine_arrays_funded_v58_fg.npz')


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
    print("  OFFICIAL v58_full + OTHER TOP GEOMETRIC EXTRACTORS  (excluding E7)")
    print(BAR)
    t0 = time.time()

    # ── 1. official funded data/state panel ───────────────────────────
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

    # ── 2. official v58_full rebuild ─────────────────────────────────
    print(f"\n[2] rebuild official v58_full stack t={time.time()-t0:.0f}s", flush=True)
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
    pnl_v58_full = _apply_overlays(
        pnl_v58_dyn,
        cos=(diag['cos_theta'] > 0.0).astype(float),
        rho=(diag['rho_normalised'] > 0.5).astype(float),
        M=(diag['M_margin'] > 0.0).astype(float),
    )

    # ── 3. collect funded F and G arrays for extractors ───────────────
    print(f"\n[3] funded engine arrays F/G t={time.time()-t0:.0f}s", flush=True)
    if CACHE_FG.exists():
        z = np.load(CACHE_FG)
        F_all = z['F_all']; G_all = z['G_all']; valid = z['valid']
        print(f"    loaded cache {CACHE_FG}")
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
                valid[t] = True
                n_done += 1
                if n_done % 5000 == 0:
                    print(f"    arrays {n_done:,}/{T_total:,} elapsed={time.time()-t1:.1f}s", flush=True)
            except Exception:
                pass
        CACHE_FG.parent.mkdir(parents=True, exist_ok=True)
        np.savez(CACHE_FG, F_all=F_all, G_all=G_all, valid=valid)
        print(f"    cached -> {CACHE_FG}")

    F_flat = F_all.reshape(T_total, -1)
    G_flat = G_all.reshape(T_total, -1)
    Xt_flat = X.reshape(T_total, -1)
    dX = np.full_like(X, np.nan, dtype=np.float32); dX[:-1] = X[1:] - X[:-1]
    dX_flat = dX.reshape(T_total, -1)
    dX_prev = np.roll(dX_flat, 1, axis=0); dX_prev[0] = np.nan
    Fnorm = np.linalg.norm(F_flat, axis=1)

    # ── 4. compute other top extractor signals ────────────────────────
    print(f"\n[4] compute E10/E8/B1/E6 signals t={time.time()-t0:.0f}s", flush=True)
    sigs: dict[str, pd.Series] = {}

    # E8: path-integrated force against ΔX_{t-1}
    Fpath = np.full_like(F_flat, np.nan)
    csum = np.cumsum(np.nan_to_num(F_flat), axis=0)
    for t in range(PATH_WIN_E8, T_total):
        Fpath[t] = (csum[t] - csum[t - PATH_WIN_E8]) / PATH_WIN_E8
    sigs['E8_path_integral'] = pd.Series(np.einsum('ti,ti->t', Fpath, dX_prev), index=idx)

    # B1: pullback memory
    sigs['B1_pullback_memory'] = pd.Series(np.einsum('ti,ti->t', G_flat, dX_prev), index=idx)

    # E6: energy flux -<F, Sigma^-1 (X-mu)>
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

    # E10: tangent-bundle ridge on [F, ||F||F, X*F], fit on calib only
    print("    E10 tangent ridge fit...", flush=True)
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

    # ── 5. individual + ensemble additive overlays over v58_full ──────
    print(f"\n{BAR}")
    print("  RESULTS — other top extractors as additive overlays over v58_full")
    print(BAR)

    base_stats = _metric_row(pnl_v58_full, test_mask)
    rows = {'v58_full_best': base_stats}
    overlay_pnls = {}
    k_map = {}
    base_calib_std = pnl_v58_full[calib_mask].std()

    for name, sig in sigs.items():
        p = _extractor_pnl(sig, ret_eth).reindex(pnl_v58_full.index).fillna(0.0)
        k = float(base_calib_std / max(p[calib_mask].std(), 1e-12))
        k_map[name] = k
        overlay_pnls[name] = k * p
        rows[f'{name}_pure'] = _metric_row(p, test_mask)
        rows[f'v58_full_plus_{name}'] = _metric_row(pnl_v58_full + k * p, test_mask)

    # equal-risk ensemble of top 3 excluding E7: E10, E8, B1
    top3_names = ['E10_tangent_ridge', 'E8_path_integral', 'B1_pullback_memory']
    ens_top3 = sum(overlay_pnls[n] for n in top3_names) / len(top3_names)
    rows['v58_full_plus_top3_equal'] = _metric_row(pnl_v58_full + ens_top3, test_mask)

    # equal-risk ensemble of top 4 including E6
    top4_names = top3_names + ['E6_energy_flux']
    ens_top4 = sum(overlay_pnls[n] for n in top4_names) / len(top4_names)
    rows['v58_full_plus_top4_equal'] = _metric_row(pnl_v58_full + ens_top4, test_mask)

    print(f"  {'Variant':<38} {'Sharpe':>9} {'MaxDD':>8} {'CAGR':>8} {'Trades/yr':>10} {'Δ vs v58':>10}")
    print(f"  {'-'*38} {'-'*9} {'-'*8} {'-'*8} {'-'*10} {'-'*10}")
    for name, r in rows.items():
        print(f"  {name:<38} {r['sharpe']:>+9.4f} {r['maxdd']:>+7.1%} {r['cagr']:>+7.1%} "
              f"{r['trades_per_year']:>10.0f} {r['sharpe']-base_stats['sharpe']:>+10.4f}")

    best = max(((n, r) for n, r in rows.items() if n != 'v58_full_best'), key=lambda kv: kv[1]['sharpe'])
    print(f"\n  best non-E7 overlay: {best[0]}  Sharpe={best[1]['sharpe']:+.4f}  "
          f"Δ={best[1]['sharpe']-base_stats['sharpe']:+.4f}")
    print("  k scalers:")
    for n, k in k_map.items():
        print(f"    {n:<22} k={k:.4f}")

    out_path = Path(OUT_DIR) / 'v59_other_top_extractors_vs_v58_full_results.json'
    out_path.write_text(json.dumps({
        'config': {'path_win_e8': PATH_WIN_E8, 'core': CORE},
        'k_scalers': k_map,
        'results': rows,
        'best': {'name': best[0], **best[1]},
    }, indent=2, default=float))
    print(f"\n  saved -> {out_path}")
    print(f"  total elapsed: {time.time()-t0:.1f}s")
    print(BAR)


if __name__ == '__main__':
    main()
