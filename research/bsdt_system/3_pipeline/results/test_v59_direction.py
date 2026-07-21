"""Direction audit for E7 and v54 — do long bars and short bars BOTH make money?

For each signed system, split the test-window PnL into:
  long-only bars  (position = +1)   →  Sharpe, hit-rate, mean PnL
  short-only bars (position = -1)   →  Sharpe, hit-rate, mean PnL
  flat bars        (position =  0)

Also compute agree/disagree rates between E7 and v54, and the conditional
PnL when they agree vs disagree — the empirical proof of whether they
encode the same or independent directions.

Reuses the cached engine arrays + diagnostics.  Reuses the same builders
as test_v59_combined.  Run time ~6 minutes (rebuilds v54 base portfolio).
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

from collapse_geometry import MasterOperator                            # noqa: E402
from run_crypto_pairs_v36_intraday_bsdt import (                        # noqa: E402
    CALIB_BARS, BPD,
    build_intraday_state_panel, calibrate_intraday_engine, _stats,
    compute_intraday_signals,
)
from run_crypto_pairs_v37_price_prediction import compute_price_prediction_signals  # noqa: E402
from run_crypto_pairs_v38_lambda_norm    import compute_lambda_features            # noqa: E402
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
    _build_pnl, CORE,
    _make_cached_fetch, _cached_fetch_and_prepare, _cached_add_cross_market,
    _cached_fetch_binance_funding,
)
import run_crypto_pairs_v34_full_combined as _v34mod                    # noqa: E402

EMA_SPAN_E7 = 32
ENGINE_NPZ  = Path(r'C:\amttp\data\geometric_extractor_engine_arrays.npz')


def _split_stats(name: str, pos: pd.Series, ret: pd.Series, mask: pd.Series):
    """Print Sharpe/hit/mean PnL on long bars, short bars, flat bars."""
    pos = pos.shift(1).fillna(0.0)            # causal: act next bar
    pnl = (pos * ret.fillna(0.0))[mask]
    pos_t = pos[mask]
    n_long  = int((pos_t > 0).sum())
    n_short = int((pos_t < 0).sum())
    n_flat  = int((pos_t == 0).sum())
    n_total = len(pos_t)

    def _bucket(b_mask):
        if b_mask.sum() < 50:
            return dict(n=int(b_mask.sum()), sharpe=float('nan'),
                        hit=float('nan'), mean_bp=float('nan'),
                        cum_pct=float('nan'))
        p = pnl[b_mask]
        return dict(
            n      = int(b_mask.sum()),
            sharpe = float(_stats(p)['sharpe']),
            hit    = float((p > 0).mean()),
            mean_bp= float(p.mean() * 1e4),       # bps per bar
            cum_pct= float(p.sum() * 100.0),
        )

    long_b  = _bucket(pos_t > 0)
    short_b = _bucket(pos_t < 0)
    flat_b  = _bucket(pos_t == 0)
    total_b = _bucket(pos_t == pos_t)            # all bars

    print(f"\n  ── {name} ──")
    print(f"     bars: total={n_total:,}  long={n_long:,} ({n_long/n_total:.1%})  "
          f"short={n_short:,} ({n_short/n_total:.1%})  flat={n_flat:,} ({n_flat/n_total:.1%})")
    print(f"     {'bucket':<10} {'n':>7} {'Sharpe':>9} {'hit%':>7} "
          f"{'mean bp/bar':>13} {'cumulative %':>14}")
    for tag, st in [('LONG', long_b), ('SHORT', short_b),
                    ('FLAT', flat_b), ('TOTAL', total_b)]:
        print(f"     {tag:<10} {st['n']:>7,} {st['sharpe']:>+9.3f} "
              f"{st['hit']*100:>6.1f}% {st['mean_bp']:>+13.3f} "
              f"{st['cum_pct']:>+13.2f}%")
    return dict(long=long_b, short=short_b, flat=flat_b, total=total_b)


def main():
    BAR = '=' * 100
    print(BAR)
    print("  v59 DIRECTION AUDIT — long vs short profitability of E7 and v54")
    print(BAR)
    t0 = time.time()

    # ── 1. data + E7 signal ───────────────────────────────────────────
    print("\n[1] data + E7 …", flush=True)
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    train_idx = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True
    X = np.nan_to_num(build_intraday_state_panel(df_1h, None, None))
    T_total, N, d = X.shape

    z = np.load(ENGINE_NPZ)
    F_all = z['F_all']
    dX = np.full_like(X, np.nan, dtype=np.float32); dX[:-1] = X[1:] - X[:-1]
    F_flat = F_all.reshape(T_total, -1)
    dX_flat = dX.reshape(T_total, -1)
    dX_prev = np.roll(dX_flat, 1, axis=0); dX_prev[0] = np.nan

    alpha = 2.0 / (EMA_SPAN_E7 + 1)
    Fbar = np.full_like(F_flat, np.nan)
    Fbar[0] = F_flat[0]
    for t in range(1, T_total):
        if np.isnan(F_flat[t]).any():
            Fbar[t] = Fbar[t-1]
        elif np.isnan(Fbar[t-1]).any():
            Fbar[t] = F_flat[t]
        else:
            Fbar[t] = (1 - alpha) * Fbar[t-1] + alpha * F_flat[t]
    s_E7 = pd.Series(np.einsum('ti,ti->t', Fbar, dX_prev), index=df_1h.index)
    pos_E7 = np.sign(s_E7)                       # +1 long ETH, -1 short ETH

    ret_eth = df_1h['ret_eth']
    test_mask = df_1h.index >= TEST_START

    # ── 2. v54 base + plateau core (rebuild) ──────────────────────────
    print(f"\n[2] full v54 stack t={time.time()-t0:.0f}s …", flush=True)
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(X, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)
    M_k1 = MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)
    sig_v36       = compute_intraday_signals(X, df_1h, M, net, ews, stoch, e_star, theta)
    sig_v37, _, _ = compute_price_prediction_signals(X, df_1h, M, sig_v36, e_star, sigma_n)
    lam_feat      = compute_lambda_features(sig_v37, roll_windows=(100,200,500))
    mu_norm  = calibrate_channel_means(X, calib_mask, M_k1)
    fire_thr = calibrate_firing_thresholds(X, calib_mask, M_k1, pct=FIRE_PERCENTILE)
    sig_4ch  = compute_four_channel_signals_v39b(X, df_1h, M_k1, sig_v36, fire_thr, mu_norm)

    _v34mod.fetch_klines = _make_cached_fetch(_v34mod.fetch_klines)
    h_strats = compute_1h_strategies(df_1h, has_sol)
    df_d   = _cached_fetch_and_prepare()
    df_d   = _cached_add_cross_market(df_d)
    fund_d = _cached_fetch_binance_funding()
    df_d   = add_leverage_features(df_d, fund_d)
    tmask_d = (df_d.index >= TRAIN_START) & (df_d.index <= TRAIN_END)
    pos_dict, _, _, gate_daily = build_daily_positions(
        df_d, tmask_d, np.asarray(tmask_d, dtype=bool))
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
    pnl_v54 = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch,
                         CORE['clip'], CORE['tth'], CORE['aft'],
                         CORE['cb'],   CORE['gbt'], CORE['gth'])

    # v54 positional sign — PnL = pos * ret_eth implicitly, but v54 PnL is
    # already signed.  The implied per-bar position is sign(pnl_v54 / ret_eth)
    # for bars where ret_eth ≠ 0.  We approximate the "v54 direction" as
    # sign of its PnL contribution.  More principled: v54 trades MULTIPLE
    # instruments, so its scalar position is not well-defined — use the
    # sign of its ETH-attributable PnL contribution as a proxy.
    pos_v54 = np.sign(pnl_v54)

    # ── 3. direction audit ────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  DIRECTION AUDIT — does each side (long/short) make money on its own?")
    print(BAR)

    e7_buckets  = _split_stats("E7 pure  (sgn⟨F̄, ΔX⟩)", pos_E7, ret_eth, test_mask)
    v54_buckets = _split_stats("v54 (proxy: sgn(PnL))", pos_v54.shift(-1), ret_eth, test_mask)
    # ↑ v54's PnL[t] = pos[t-1]*ret[t], so its "current" implied position
    #   for bar t is sign(pnl[t+1]) — shift back by 1 so _split_stats's
    #   internal .shift(1) restores the right alignment.

    # ── 4. agreement / disagreement analysis ──────────────────────────
    print(f"\n{BAR}")
    print("  AGREEMENT — when do E7 and v54 agree on direction?")
    print(BAR)

    pos_E7_t  = pos_E7.shift(1).fillna(0.0)
    pos_v54_t = pos_v54.fillna(0.0)        # already at position-time alignment

    both_active = (pos_E7_t != 0) & (pos_v54_t != 0)
    agree       = both_active & (np.sign(pos_E7_t) == np.sign(pos_v54_t))
    disagree    = both_active & (np.sign(pos_E7_t) != np.sign(pos_v54_t))

    n_total    = int(test_mask.sum())
    n_active   = int((both_active & test_mask).sum())
    n_agree    = int((agree & test_mask).sum())
    n_disagree = int((disagree & test_mask).sum())

    print(f"\n  bars (test):  total={n_total:,}  both-active={n_active:,} "
          f"({n_active/n_total:.1%})")
    print(f"  agree     (same sign):  {n_agree:>6,} ({n_agree/max(n_active,1):.1%} of active)")
    print(f"  disagree  (opp  sign):  {n_disagree:>6,} ({n_disagree/max(n_active,1):.1%} of active)")

    # PnL of E7 alone on agree vs disagree bars
    pnl_e7_alone = (pos_E7_t * ret_eth.fillna(0.0))
    pnl_v54_alone = pnl_v54.fillna(0.0)

    def _by_set(name, p, mask):
        if mask.sum() < 50:
            print(f"    {name:<28} n={int(mask.sum()):>5}   (insufficient)")
            return
        s = _stats(p[mask])
        print(f"    {name:<28} n={int(mask.sum()):>5,}  Sharpe={s['sharpe']:+.3f}  "
              f"cum={p[mask].sum()*100:+.2f}%  hit={(p[mask]>0).mean()*100:.1f}%")

    print("\n  E7 PnL on agree-bars vs disagree-bars:")
    _by_set("E7 on AGREE bars",    pnl_e7_alone, agree    & test_mask)
    _by_set("E7 on DISAGREE bars", pnl_e7_alone, disagree & test_mask)

    print("\n  v54 PnL on agree-bars vs disagree-bars:")
    _by_set("v54 on AGREE bars",    pnl_v54_alone, agree    & test_mask)
    _by_set("v54 on DISAGREE bars", pnl_v54_alone, disagree & test_mask)

    print("\n  Combined (v54 + 0.118·E7) on agree vs disagree:")
    s_v54_calib  = pnl_v54[calib_mask[:len(pnl_v54)]].std()
    s_e7p_calib  = pnl_e7_alone[calib_mask[:len(pnl_e7_alone)]].std()
    k_scale = float(s_v54_calib / max(s_e7p_calib, 1e-12))
    pnl_v59 = pnl_v54_alone + k_scale * pnl_e7_alone
    _by_set("v59 on AGREE bars",    pnl_v59, agree    & test_mask)
    _by_set("v59 on DISAGREE bars", pnl_v59, disagree & test_mask)
    s_v59 = _stats(pnl_v59[test_mask])
    print(f"\n  v59 OVERALL test:  Sharpe={s_v59['sharpe']:+.4f}  "
          f"MaxDD={s_v59['max_dd']:+.1%}  CAGR={s_v59['cagr']:+.1%}  k={k_scale:.3f}")

    # ── 5. save + verdict ─────────────────────────────────────────────
    out = dict(
        e7_buckets=e7_buckets, v54_buckets=v54_buckets,
        n_active=n_active, n_agree=n_agree, n_disagree=n_disagree,
        k_scale=k_scale,
        v59_total=dict(sharpe=float(s_v59['sharpe']), maxdd=float(s_v59['max_dd']),
                       cagr=float(s_v59['cagr'])),
    )
    out_path = Path(OUT_DIR) / 'v59_direction_audit.json'
    out_path.write_text(json.dumps(out, indent=2, default=float))
    print(f"\n  saved -> {out_path}")
    print(f"  total elapsed: {time.time()-t0:.1f}s")
    print(BAR)


if __name__ == '__main__':
    main()
