"""§XXIX — v59 candidate: E7 directional readout × §XXIV gates × v54 base.

Background
----------
- §26.7 found E7 (EMA-aligned force F̄_t, span=32) is the gate-free Sharpe
  champion at +2.19 on the test window using sign(⟨F̄_t, ΔX_{t-1}⟩) · ret_eth.
- §10 found v54 plateau core (no E7) at Sharpe +3.857 using v36/v37 features
  + v39b 4-channel quadrant phase amplifier.
- The two systems use orthogonal information: E7 is a continuous geometric
  forecast on the engine field; v54 is a regime-amplifier on multi-strategy
  portfolio PnL.  The conjecture (§29.x): if E7's information is genuine,
  multiplying its sign mask onto v54 should *add* edge or at worst preserve.

What this script does
---------------------
Reuses the two cached artefacts:
  C:\\amttp\\data\\geometric_extractor_engine_arrays.npz   (F_t, ΔX_t, valid)
  C:\\amttp\\data\\corrected_diagnostics_v58_default.pkl   (cos_theta,
                                                            rho_normalised,
                                                            M_margin)

Computes the E7 signal in one pass, then evaluates 12 variants:

  Pure E7:
    v0  B0_naive_§24.6        — reference baseline (loses money)
    v1  E7_pure               — sign(s_E7).shift(1) · ret_eth          (the +2.19)
    v2  E7_×cosθ              — block bars where cos θ ≤ 0
    v3  E7_×ρⁿ                — block bars where ρⁿ ≤ 0.5
    v4  E7_×M                 — block bars where M_t ≤ 0
    v5  E7_×cosθ×ρⁿ           — §XXIV pair gate
    v6  E7_×cosθ×ρⁿ×M         — full §XXIV+§VII+§XVI gate

  Combined with v54 base portfolio (loaded via v34 base + v36/v37 features):
    v7  v54_static            — frozen v54 plateau core (Sharpe ≈ +3.86)
    v8  v54_×E7sign           — multiplied by sign(s_E7).shift(1)
    v9  v54_×E7sign_when_fire — multiplied by sign(s_E7) only when |s_E7|>median
    v10 v54_×(E7sign or 0)    — replace v54 by 0 when sign(E7)≠sign(v54)  (anti-veto)
    v11 v54_+E7scaled         — additive PnL combination (E7_pure scaled to v54 vol)

Reports Sharpe / MaxDD / CAGR / active-bars on test window, ΔSharpe vs both
v1 (E7 alone) and v7 (v54 static).
"""
from __future__ import annotations
import os, sys, time, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

# Engine + helpers
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
    add_leverage_features, add_cross_market_features,
    fetch_and_prepare, fetch_binance_funding,
)
from run_crypto_pairs_v39_four_channels import (                        # noqa: E402
    FIRE_PERCENTILE, calibrate_firing_thresholds,
)
from run_crypto_pairs_v39b_k1_scaled import (                           # noqa: E402
    compute_four_channel_signals_v39b, calibrate_channel_means, PCA_K_B,
)
# v54 builder pieces + cache helpers lifted from run_robustness_validation
from run_robustness_validation import (                                  # noqa: E402
    _build_pnl, _apply_overlays, CORE,
    _make_cached_fetch, _cached_fetch_and_prepare, _cached_add_cross_market,
    _cached_fetch_binance_funding,
)
import run_crypto_pairs_v34_full_combined as _v34mod                    # noqa: E402
from corrected_diagnostics import v58_dynamic_gth                       # noqa: E402

# ── 0. configuration ──────────────────────────────────────────────────────
EMA_SPAN_E7   = 32
ENGINE_NPZ    = Path(r'C:\amttp\data\geometric_extractor_engine_arrays.npz')
DIAG_PKL      = Path(r'C:\amttp\data\corrected_diagnostics_v58_default.pkl')


def _trades_per_year(pnl: pd.Series, mask: pd.Series) -> float:
    nz = int((pnl[mask].abs() > 1e-12).sum())
    yrs = max((pnl[mask].index[-1] - pnl[mask].index[0]).days / 365.25, 1e-3)
    return nz / yrs


def main():
    BAR = '=' * 100
    print(BAR)
    print("  §XXIX  v59 candidate  —  E7 directional × §XXIV gates × v54 base")
    print(BAR)
    t0 = time.time()

    # ── 1. data + engine ──────────────────────────────────────────────
    print("\n[1] 1h panel …", flush=True)
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    train_idx = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True
    X = np.nan_to_num(build_intraday_state_panel(df_1h, None, None))
    T_total, N, d = X.shape
    print(f"    bars={T_total:,}  N={N}  d={d}  test_start={TEST_START}")

    # ── 2. load engine arrays + compute E7 signal ─────────────────────
    print("\n[2] loading engine arrays + computing E7 EMA-aligned force …", flush=True)
    if not ENGINE_NPZ.exists():
        raise FileNotFoundError(
            f"Engine array cache missing.  Run test_geometric_extractors.py first "
            f"to populate {ENGINE_NPZ}.")
    z = np.load(ENGINE_NPZ)
    F_all = z['F_all']
    valid = z['valid']
    print(f"    F_all shape={F_all.shape}  valid={int(valid.sum()):,}")

    dX = np.full_like(X, np.nan, dtype=np.float32)
    dX[:-1] = X[1:] - X[:-1]
    F_flat  = F_all.reshape(T_total, -1)
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
    s_E7 = np.einsum('ti,ti->t', Fbar, dX_prev)
    s_E7 = pd.Series(s_E7, index=df_1h.index, name='s_E7')

    # ── 3. load corrected diagnostics → §XXIV gates ───────────────────
    print(f"\n[3] loading corrected diagnostics  {DIAG_PKL.name} …", flush=True)
    if not DIAG_PKL.exists():
        raise FileNotFoundError(
            f"Diagnostics cache missing.  Run run_robustness_validation.py "
            f"first to populate {DIAG_PKL}.")
    diag = pd.read_pickle(DIAG_PKL)
    print(f"    diag rows={len(diag):,}  span={diag.index.min()}..{diag.index.max()}")

    # paper-correct gates (each shifted in the variant builder)
    g_cos = (diag['cos_theta'] > 0.0).astype(float)            # §VII
    g_rho = (diag['rho_normalised'] > 0.5).astype(float)        # §XXIV scale-fixed
    g_M   = (diag['M_margin'] > 0.0).astype(float)              # §XVI

    # align to df_1h
    g_cos = g_cos.reindex(df_1h.index).fillna(0.0)
    g_rho = g_rho.reindex(df_1h.index).fillna(0.0)
    g_M   = g_M.reindex(df_1h.index).fillna(0.0)

    print(f"    gate fire rates : cosθ>0={g_cos.mean():.1%}   "
          f"ρⁿ>0.5={g_rho.mean():.1%}   M>0={g_M.mean():.1%}")

    # ── 4. ret_eth + helper to build E7-flavoured PnL ─────────────────
    ret_eth = df_1h['ret_eth']
    test_mask = df_1h.index >= TEST_START

    pos_E7 = np.sign(s_E7).shift(1).fillna(0.0)

    def _gated(pos: pd.Series, *gates) -> pd.Series:
        out = pos.copy()
        for g in gates:
            out = out * g.shift(1).fillna(0.0)
        return out

    pnl_E7_pure   = pos_E7                          * ret_eth.fillna(0.0)
    pnl_E7_cos    = _gated(pos_E7, g_cos)           * ret_eth.fillna(0.0)
    pnl_E7_rho    = _gated(pos_E7, g_rho)           * ret_eth.fillna(0.0)
    pnl_E7_M      = _gated(pos_E7, g_M)             * ret_eth.fillna(0.0)
    pnl_E7_cosrho = _gated(pos_E7, g_cos, g_rho)    * ret_eth.fillna(0.0)
    pnl_E7_full   = _gated(pos_E7, g_cos, g_rho, g_M) * ret_eth.fillna(0.0)

    # B0 baseline for reference (recompute quickly from cached arrays)
    G_all = z['G_all']
    G_flat = G_all.reshape(T_total, -1)
    Gnorm = np.linalg.norm(G_flat, axis=1)
    raw = np.einsum('ti,ti->t', F_flat, G_flat)
    with np.errstate(invalid='ignore', divide='ignore'):
        s_B0 = pd.Series(raw / np.maximum(Gnorm, 1e-12), index=df_1h.index)
    pnl_B0 = np.sign(s_B0).shift(1).fillna(0.0) * ret_eth.fillna(0.0)

    # ── 5. build v54 base portfolio + v54 plateau core PnL ────────────
    print("\n[5] full v54 stack — engine + v36/v37/v39b + base portfolio …", flush=True)
    print(f"    [3] engine calib t={time.time()-t0:.0f}s")
    M, net, geom, lyap, ews, stoch, e_star, theta = calibrate_intraday_engine(X, calib_mask)
    sigma_n = getattr(stoch, 'sigma_n', 1.0)
    M_k1 = MasterOperator.calibrate(X[calib_mask], k=PCA_K_B)

    print(f"    [4] v36/v37 features t={time.time()-t0:.0f}s")
    sig_v36       = compute_intraday_signals(X, df_1h, M, net, ews, stoch, e_star, theta)
    sig_v37, _, _ = compute_price_prediction_signals(X, df_1h, M, sig_v36, e_star, sigma_n)
    lam_feat      = compute_lambda_features(sig_v37, roll_windows=(100,200,500))

    print(f"    [5] 4-channel t={time.time()-t0:.0f}s")
    mu_norm  = calibrate_channel_means(X, calib_mask, M_k1)
    fire_thr = calibrate_firing_thresholds(X, calib_mask, M_k1, pct=FIRE_PERCENTILE)
    sig_4ch  = compute_four_channel_signals_v39b(X, df_1h, M_k1, sig_v36, fire_thr, mu_norm)

    print(f"    [6] base portfolio t={time.time()-t0:.0f}s")
    # use cached fetchers (same convention as run_robustness_validation)
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

    print(f"    [7] v54 plateau core t={time.time()-t0:.0f}s")
    pnl_v54 = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch,
                         CORE['clip'], CORE['tth'], CORE['aft'],
                         CORE['cb'],   CORE['gbt'], CORE['gth'])

    # also build v58 dynamic θ_G base for reference
    gth_dyn = v58_dynamic_gth(df_1h)
    pnl_v58 = _build_pnl(base_pnl, sig_v36, lam_feat, sig_4ch,
                         CORE['clip'], CORE['tth'], CORE['aft'],
                         CORE['cb'],   CORE['gbt'], gth_dyn)

    # v58_full is the serious benchmark: v58 dynamic θ_G plus the corrected
    # §VII/§XXIV/§XVI gates, exactly matching run_robustness_validation Section 10.
    pnl_v58_full = _apply_overlays(pnl_v58, cos=g_cos, rho=g_rho, M=g_M)

    # ── 6. combined variants (v54 × E7 sign mask, etc.) ───────────────
    # E7 sign aligned to v54 PnL index
    sign_E7 = np.sign(s_E7).shift(1).fillna(0.0).reindex(pnl_v54.index).fillna(0.0)
    s_E7_aligned = s_E7.reindex(pnl_v54.index)

    # v8: hard mask — keep v54 PnL only when sign(E7) is non-zero (it's almost
    # always non-zero, so this is essentially a polarity vote)
    pnl_v54_x_E7sign = pnl_v54 * sign_E7

    # v9: fire only when |s_E7| above median on calib window (selective)
    s_E7_calib = s_E7_aligned[calib_mask[:len(s_E7_aligned)]]
    s_med = float(np.nanmedian(np.abs(s_E7_calib))) if s_E7_calib.notna().any() else 0.0
    fire_E7 = (np.abs(s_E7_aligned) > s_med).shift(1).fillna(False).astype(float)
    pnl_v54_x_E7fire = pnl_v54 * sign_E7 * fire_E7 + pnl_v54 * (1 - fire_E7)

    # v10: anti-veto — zero out v54 PnL on bars where its sign disagrees with
    #                  E7's signed forecast.  Preserves bars when E7 is silent
    #                  (sign_E7 = 0 → keep v54 untouched as a fail-open).
    pnl_v54_sign = np.sign(pnl_v54)
    agree = ((sign_E7 == 0) | (pnl_v54_sign == 0) |
             (sign_E7 == pnl_v54_sign)).astype(float)
    pnl_v54_antiveto = pnl_v54 * agree

    # v11: additive — scale E7_pure to match v54's std on calib then sum
    s_v54_calib = pnl_v54[calib_mask[:len(pnl_v54)]].std()
    s_E7p_calib = pnl_E7_pure[calib_mask[:len(pnl_E7_pure)]].std()
    k_scale = float(s_v54_calib / max(s_E7p_calib, 1e-12)) if s_E7p_calib > 0 else 0.0
    pnl_additive = pnl_v54 + k_scale * pnl_E7_pure.reindex(pnl_v54.index).fillna(0.0)
    print(f"    additive scaler  k = std(v54_calib)/std(E7_calib) = {k_scale:.3f}")

    # v58_full + E7: this is the corrected v59 candidate benchmarked against
    # the best multi-portfolio paper-gated variant, not against v54.
    s_v58f_calib = pnl_v58_full[calib_mask[:len(pnl_v58_full)]].std()
    s_E7p_calib  = pnl_E7_pure[calib_mask[:len(pnl_E7_pure)]].std()
    k58_scale = float(s_v58f_calib / max(s_E7p_calib, 1e-12)) if s_E7p_calib > 0 else 0.0
    pnl_v58full_additive = pnl_v58_full + k58_scale * pnl_E7_pure.reindex(pnl_v58_full.index).fillna(0.0)
    print(f"    additive scaler  k58 = std(v58_full_calib)/std(E7_calib) = {k58_scale:.3f}")

    # ── 7. report all variants on the test window ─────────────────────
    print(f"\n{BAR}")
    print(f"  RESULTS  (test window  {TEST_START} → {df_1h.index[-1].date()})")
    print(BAR)

    variants = [
        # name                               pnl                    family
        ('v0  B0_naive_§24.6',               pnl_B0,                'baseline'),
        ('v1  E7_pure',                      pnl_E7_pure,           'E7'),
        ('v2  E7_×cosθ',                     pnl_E7_cos,            'E7'),
        ('v3  E7_×ρⁿ',                       pnl_E7_rho,            'E7'),
        ('v4  E7_×M',                        pnl_E7_M,              'E7'),
        ('v5  E7_×cosθ×ρⁿ',                  pnl_E7_cosrho,         'E7'),
        ('v6  E7_×cosθ×ρⁿ×M',                pnl_E7_full,           'E7'),
        ('v7  v54_static',                   pnl_v54,               'v54'),
        ('v7b v58_dyn_gth',                  pnl_v58,               'v54'),
        ('v7c v58_full_best',                 pnl_v58_full,          'v58'),
        ('v8  v54_×E7sign',                  pnl_v54_x_E7sign,      'combined'),
        ('v9  v54_×E7sign_above_med',        pnl_v54_x_E7fire,      'combined'),
        ('v10 v54_antiveto_E7',              pnl_v54_antiveto,      'combined'),
        ('v11 v54_+E7_scaled_std',           pnl_additive,          'combined'),
        ('v12 v58full_+E7_scaled_std',        pnl_v58full_additive,  'combined_v58'),
    ]

    print(f"  {'Variant':<32} {'Sharpe':>9} {'MaxDD':>8} {'CAGR':>8} "
          f"{'Trades/yr':>10} {'ΔvE7':>8} {'Δv54':>8}")
    print(f"  {'-'*32} {'-'*9} {'-'*8} {'-'*8} {'-'*10} {'-'*8} {'-'*8}")

    rows = {}
    sh_E7  = sh_v54 = None
    for name, pnl, fam in variants:
        pt = pnl.reindex(df_1h.index).fillna(0.0)
        s = _stats(pt[test_mask])
        tpy = _trades_per_year(pt, test_mask)
        if name.startswith('v1 '):
            sh_E7 = s['sharpe']
        if name.startswith('v7 '):
            sh_v54 = s['sharpe']
        d_E7  = (s['sharpe'] - sh_E7)  if sh_E7  is not None else float('nan')
        d_v54 = (s['sharpe'] - sh_v54) if sh_v54 is not None else float('nan')
        print(f"  {name:<32} {s['sharpe']:>+9.4f} {s['max_dd']:>+7.1%} {s['cagr']:>+7.1%} "
              f"{tpy:>10.0f} {d_E7:>+8.3f} {d_v54:>+8.3f}")
        rows[name] = dict(sharpe=float(s['sharpe']), maxdd=float(s['max_dd']),
                          cagr=float(s['cagr']), trades_per_year=float(tpy),
                          family=fam)

    # ── 8. verdict ────────────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  VERDICT  —  does E7 add genuine edge to v54?")
    print(BAR)
    v54_sh  = rows['v7  v54_static']['sharpe']
    v58f_sh = rows['v7c v58_full_best']['sharpe']
    best_combined = max(
        ((n, r) for n, r in rows.items() if r['family'] == 'combined'),
        key=lambda kv: kv[1]['sharpe'])
    best_combined_v58 = max(
        ((n, r) for n, r in rows.items() if r['family'] == 'combined_v58'),
        key=lambda kv: kv[1]['sharpe'])
    print(f"  v54 static baseline             Sharpe = {v54_sh:+.4f}")
    print(f"  v58_full best benchmark         Sharpe = {v58f_sh:+.4f}")
    print(f"  best combined variant           {best_combined[0]:<28}  "
          f"Sharpe = {best_combined[1]['sharpe']:+.4f}  "
          f"Δ vs v54 = {best_combined[1]['sharpe'] - v54_sh:+.4f}")
    print(f"  best v58-based combined         {best_combined_v58[0]:<28}  "
          f"Sharpe = {best_combined_v58[1]['sharpe']:+.4f}  "
          f"Δ vs v58_full = {best_combined_v58[1]['sharpe'] - v58f_sh:+.4f}")
    best_E7 = max(((n, r) for n, r in rows.items() if r['family'] == 'E7'),
                  key=lambda kv: kv[1]['sharpe'])
    print(f"  best E7-only variant            {best_E7[0]:<28}  "
          f"Sharpe = {best_E7[1]['sharpe']:+.4f}")

    # ── 9. save ───────────────────────────────────────────────────────
    out_path = Path(OUT_DIR) / 'v59_combined_results.json'
    out_path.write_text(json.dumps({
        'config': {
            'ema_span_e7': EMA_SPAN_E7,
            'core': CORE,
        },
        'gate_fire_rates': {
            'cos_theta_pos': float(g_cos.mean()),
            'rho_norm_gt_05': float(g_rho.mean()),
            'M_margin_pos':  float(g_M.mean()),
        },
        'additive_scaler_k': k_scale,
        'additive_scaler_k58': k58_scale,
        'variants': rows,
    }, indent=2, default=float))
    print(f"\n  saved -> {out_path}")
    print(f"  total elapsed: {time.time()-t0:.1f}s")
    print(BAR)


if __name__ == '__main__':
    main()
