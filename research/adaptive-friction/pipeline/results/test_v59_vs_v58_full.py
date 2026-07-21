"""Official v59 benchmark: v58_full multi-portfolio vs v58_full + E7.

This is the serious comparison.  It mirrors run_robustness_validation.py:
  - funding-aware 1h state panel (fund_btc, fund_eth)
  - v36/v37/v38/v39b feature stack
  - v58 dynamic θ_G(t)
  - corrected §VII/§XXIV/§XVI full gates: cosθ>0, ρⁿ>0.5, M>0

Then it adds E7 as an additive ETH-perp directional overlay:
  s_E7(t) = < EMA32(F_t), ΔX_{t-1} >
  pnl_E7(t+1) = sign(s_E7(t)) * ret_eth(t+1)
  pnl_v59 = pnl_v58_full + k * pnl_E7, k fitted on calib window only.
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

EMA_SPAN_E7 = 32
HISTORY_LEN = 48
CACHE_F = Path(r'C:\amttp\data\geometric_extractor_engine_arrays_funded_v58.npz')


def _trades_per_year(pnl: pd.Series, test_mask: pd.Series) -> float:
    nz = int((pnl[test_mask].abs() > 1e-12).sum())
    yrs = max((pnl[test_mask].index[-1] - pnl[test_mask].index[0]).days / 365.25, 1e-3)
    return nz / yrs


def _metric_row(pnl: pd.Series, test_mask: pd.Series) -> dict:
    s = _stats(pnl[test_mask])
    return dict(
        sharpe=float(s['sharpe']),
        maxdd=float(s['max_dd']),
        cagr=float(s['cagr']),
        trades_per_year=float(_trades_per_year(pnl, test_mask)),
        cum=float(pnl[test_mask].sum()),
    )


def main():
    BAR = '=' * 100
    print(BAR)
    print("  OFFICIAL BENCHMARK — v58_full multi-portfolio vs v58_full + E7")
    print(BAR)
    t0 = time.time()

    # ── 1. official funded data/state panel ───────────────────────────
    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)
    print("\n[1] 1h data + funding-aware state panel", flush=True)
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    fund = _cached_fetch_binance_funding()
    fund_eth = fund.get('ETHUSDT')
    fund_btc = fund.get('BTCUSDT')
    X = np.nan_to_num(build_intraday_state_panel(df_1h, fund_btc, fund_eth))
    T_total, N, d = X.shape
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    train_idx = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True
    test_mask = df_1h.index >= TEST_START
    print(f"    bars={T_total:,} train={train_1h.sum():,} test={test_mask.sum():,} N={N} d={d}")

    # ── 2. engine and official v36/v37/v39b stack ─────────────────────
    print(f"\n[2] engine + v36/v37/v39b stack t={time.time()-t0:.0f}s", flush=True)
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(X, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)
    M_k1 = MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)

    sig_v36 = compute_intraday_signals(X, df_1h, M, net, ews, stoch, e_star, theta)
    sig_v37, _, _ = compute_price_prediction_signals(X, df_1h, M, sig_v36, e_star, sigma_n)
    lam_feat = compute_lambda_features(sig_v37, roll_windows=(100, 200, 500))

    mu_norm = calibrate_channel_means(X, calib_mask, M_k1)
    fire_thr = calibrate_firing_thresholds(X, calib_mask, M_k1, pct=FIRE_PERCENTILE)
    sig_4ch = compute_four_channel_signals_v39b(X, df_1h, M_k1, sig_v36, fire_thr, mu_norm)

    # ── 3. official multi-portfolio base ──────────────────────────────
    print(f"\n[3] multi-portfolio base t={time.time()-t0:.0f}s", flush=True)
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

    # ── 4. official v58 variants ──────────────────────────────────────
    print(f"\n[4] v58 full gates t={time.time()-t0:.0f}s", flush=True)
    gth_dyn = v58_dynamic_gth(df_1h)
    pnl_v54 = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch,
                         CORE['clip'], CORE['tth'], CORE['aft'], CORE['cb'], CORE['gbt'], CORE['gth'])
    pnl_v58_dyn = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch,
                             CORE['clip'], CORE['tth'], CORE['aft'], CORE['cb'], CORE['gbt'], gth_dyn)

    # Use the same diagnostics builder as robustness_validation; it will reuse the official cache.
    diag = compute_corrected_diagnostics(
        X, df_1h, M, lyap, start_idx=0, history_len=168,
        cache_key='v58_default', use_cache=True, verbose=True)
    g_cos = (diag['cos_theta'] > 0.0).astype(float)
    g_rho = (diag['rho_normalised'] > 0.5).astype(float)
    g_M = (diag['M_margin'] > 0.0).astype(float)
    pnl_v58_full = _apply_overlays(pnl_v58_dyn, cos=g_cos, rho=g_rho, M=g_M)

    # ── 5. E7 from the SAME funded engine/state panel ─────────────────
    print(f"\n[5] E7 funded engine force t={time.time()-t0:.0f}s", flush=True)
    if CACHE_F.exists():
        z = np.load(CACHE_F)
        F_all = z['F_all']
        print(f"    loaded funded F cache: {CACHE_F}")
    else:
        F_all = np.full((T_total, N, d), np.nan, dtype=np.float32)
        t1 = time.time()
        n_done = 0
        for t in range(1, T_total):
            try:
                snap = Snapshot(X=X[t], X_prev=X[t-1], history=X[max(0, t-HISTORY_LEN):t])
                F_all[t] = np.asarray(M.pipeline(snap)['F_t'], dtype=np.float32)
                n_done += 1
                if n_done % 5000 == 0:
                    print(f"    E7 force {n_done:,}/{T_total:,}  elapsed={time.time()-t1:.1f}s", flush=True)
            except Exception:
                pass
        CACHE_F.parent.mkdir(parents=True, exist_ok=True)
        np.savez(CACHE_F, F_all=F_all)
        print(f"    cached funded F -> {CACHE_F}")

    dX = np.full_like(X, np.nan, dtype=np.float32)
    dX[:-1] = X[1:] - X[:-1]
    F_flat = F_all.reshape(T_total, -1)
    dX_flat = dX.reshape(T_total, -1)
    dX_prev = np.roll(dX_flat, 1, axis=0)
    dX_prev[0] = np.nan

    alpha = 2.0 / (EMA_SPAN_E7 + 1)
    Fbar = np.full_like(F_flat, np.nan)
    Fbar[0] = F_flat[0]
    for t in range(1, T_total):
        if np.isnan(F_flat[t]).any():
            Fbar[t] = Fbar[t-1]
        elif np.isnan(Fbar[t-1]).any():
            Fbar[t] = F_flat[t]
        else:
            Fbar[t] = (1.0 - alpha) * Fbar[t-1] + alpha * F_flat[t]
    s_E7 = pd.Series(np.einsum('ti,ti->t', Fbar, dX_prev), index=df_1h.index)
    pnl_E7 = np.sign(s_E7).shift(1).fillna(0.0) * df_1h['ret_eth'].fillna(0.0)

    # Calib-only vol matching vs official v58_full.
    k = float(pnl_v58_full[calib_mask].std() / max(pnl_E7[calib_mask].std(), 1e-12))
    pnl_v59 = pnl_v58_full + k * pnl_E7.reindex(pnl_v58_full.index).fillna(0.0)

    # Also check whether E7 should be added to v58_dyn before full gates.
    k_dyn = float(pnl_v58_dyn[calib_mask].std() / max(pnl_E7[calib_mask].std(), 1e-12))
    pnl_v59_dyn = pnl_v58_dyn + k_dyn * pnl_E7.reindex(pnl_v58_dyn.index).fillna(0.0)

    # ── 6. report ─────────────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  OFFICIAL RESULTS — same funded state panel as v58 robustness")
    print(BAR)
    rows = {
        'v54_static': _metric_row(pnl_v54, test_mask),
        'v58_dyn_gth': _metric_row(pnl_v58_dyn, test_mask),
        'v58_full_best': _metric_row(pnl_v58_full, test_mask),
        'E7_funded_pure': _metric_row(pnl_E7, test_mask),
        'v58_dyn_plus_E7': _metric_row(pnl_v59_dyn, test_mask),
        'v59_v58full_plus_E7': _metric_row(pnl_v59, test_mask),
    }
    base = rows['v58_full_best']['sharpe']
    print(f"  {'Variant':<24} {'Sharpe':>9} {'MaxDD':>8} {'CAGR':>8} {'Trades/yr':>10} {'Δ vs v58_full':>15}")
    print(f"  {'-'*24} {'-'*9} {'-'*8} {'-'*8} {'-'*10} {'-'*15}")
    for name, r in rows.items():
        print(f"  {name:<24} {r['sharpe']:>+9.4f} {r['maxdd']:>+7.1%} {r['cagr']:>+7.1%} "
              f"{r['trades_per_year']:>10.0f} {r['sharpe']-base:>+15.4f}")

    print(f"\n  k_dyn  = {k_dyn:.4f}  (std(v58_dyn_calib)  / std(E7_calib))")
    print(f"  k_full = {k:.4f}  (std(v58_full_calib) / std(E7_calib))")
    print(f"\n  verdict: v59_v58full_plus_E7 ΔSharpe vs v58_full = "
          f"{rows['v59_v58full_plus_E7']['sharpe'] - base:+.4f}")

    out_path = Path(OUT_DIR) / 'v59_vs_v58_full_results.json'
    out_path.write_text(json.dumps({
        'config': {'ema_span_e7': EMA_SPAN_E7, 'core': CORE, 'k_full': k, 'k_dyn': k_dyn},
        'results': rows,
        'delta_v59_vs_v58_full': rows['v59_v58full_plus_E7']['sharpe'] - base,
    }, indent=2, default=float))
    print(f"\n  saved -> {out_path}")
    print(f"  total elapsed: {time.time()-t0:.1f}s")
    print(BAR)


if __name__ == '__main__':
    main()
