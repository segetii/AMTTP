"""
run_crypto_godmode_v28_canonical_stability.py
=============================================

Implements the practical improvements suggested by canonical_v4_gap_closure.md:

  G2 stochastic/noise guidance:
    - Use extra microstructure as SOFT friction / sizing, not only hard vetoes.

  G4 effective-rate guidance:
    - Use canonical rho_eff as a soft throttle when convergence is weak.

  G7 calibration conditioning guidance:
    - Inspect and optionally regularise Sigma_f to cap condition number.

Base strategy is the current best algorithm:
  v27 funding_hot_guard = be50_btc_sol + tbr0p47 + hot-funding long guard.

All microstructure features are shifted one bar before use to avoid lookahead.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

import run_crypto_godmode_v12_filter_innovate as v12
import run_crypto_godmode_v27_all_microstructure as v27
from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import KAPPA_A, W_TARGET_A1, build_b_aligned, build_w_star, calibrate, run_godmode_sweep
from run_crypto_godmode_v8_multiasset_shell import ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from test_psi_adaptive_y import BASE
from simulate_master_strategy import (
    DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
    simulate_combined, equity_metrics, period_table,
)


BAR = "=" * 104
OUT_DIR_ = Path(OUT_DIR) / "v28_canonical_stability"

K_NORMAL = 6.0
REALISTIC_RT_BPS = 6.0
CB_HALT = 0.08
CB_RESUME = 0.01
CB_WINDOW_DAYS = 180
KAPPA_CAP = 20.0
APPLY_SIGMA_REG = os.environ.get("V28_APPLY_SIGMA_REG", "1") != "0"


VARIANTS = [
    # Current champion from v27: hard filter only.
    dict(name="v27_funding_hot_guard", hard_funding_z_long_max=1.50,
         tbr_long_min=0.47, tbr_short_max=0.53, soft=False, rho=False),

    # Soft versions: TBR remains the proven base entry-quality filter.
    dict(name="soft_funding", tbr_long_min=0.47, tbr_short_max=0.53,
         soft=True, rho=False, w_funding=0.35),
    dict(name="soft_funding_rho", tbr_long_min=0.47, tbr_short_max=0.53,
         soft=True, rho=True, w_funding=0.35),
    dict(name="soft_all_micro", tbr_long_min=0.47, tbr_short_max=0.53,
         soft=True, rho=False, w_funding=0.25, w_oi=0.18, w_lsr=0.16, w_taker=0.16),
    dict(name="soft_all_micro_rho", tbr_long_min=0.47, tbr_short_max=0.53,
         soft=True, rho=True, w_funding=0.25, w_oi=0.18, w_lsr=0.16, w_taker=0.16),

    # Less hard: test whether using all features softly can replace the TBR veto.
    dict(name="soft_all_no_tbr_veto", tbr_long_min=None, tbr_short_max=None,
         soft=True, rho=True, w_funding=0.25, w_oi=0.20, w_lsr=0.18, w_taker=0.25),
]


def condition_cap_sigma(Sigma: np.ndarray, cap: float = KAPPA_CAP) -> tuple[np.ndarray, dict]:
    """Regularise Sigma to cap condition number, then rescale to correlation."""
    vals = np.linalg.eigvalsh(Sigma)
    lam_min = float(max(vals[0], 1e-12))
    lam_max = float(vals[-1])
    cond0 = lam_max / lam_min
    if cond0 <= cap:
        return Sigma, dict(cond_before=cond0, cond_after=cond0, lambda_added=0.0, regularized=False)

    lam = max(0.0, (lam_max - cap * lam_min) / (cap - 1.0))
    S = Sigma + lam * np.eye(Sigma.shape[0])
    d = np.sqrt(np.diag(S))
    S = S / np.outer(d, d)
    vals2 = np.linalg.eigvalsh(S)
    cond1 = float(vals2[-1] / max(vals2[0], 1e-12))
    return S, dict(cond_before=cond0, cond_after=cond1, lambda_added=float(lam), regularized=True)


def _stress_pos(x: float, threshold: float, scale: float = 1.0) -> float:
    if np.isnan(x):
        return 0.0
    return max(0.0, (x - threshold) / max(scale, 1e-9))


def _stress_neg(x: float, threshold: float, scale: float = 1.0) -> float:
    if np.isnan(x):
        return 0.0
    return max(0.0, (threshold - x) / max(scale, 1e-9))


def apply_soft_friction(psi_y: np.ndarray,
                        hpos_arr: np.ndarray,
                        features: dict[str, np.ndarray],
                        rho_arr: np.ndarray,
                        cfg: dict) -> tuple[np.ndarray, dict]:
    """Convert noisy microstructure into soft friction: scale/(1+gamma_micro)."""
    if not cfg.get("soft") and not cfg.get("rho"):
        return psi_y.copy(), dict(avg_micro_gamma=0.0, avg_rho_scale=1.0, avg_total_scale=1.0)

    out = psi_y.astype(float).copy()
    gammas = np.zeros(len(out), dtype=float)
    rho_scale = np.ones(len(out), dtype=float)

    funding_z = features.get("funding_z")
    oi24 = features.get("oi_pct_24h")
    oi_z = features.get("oi_z")
    lsr_z = features.get("lsr_z")
    top_lsr_z = features.get("top_lsr_z")
    tbr_z = features.get("tbr_z")
    taker_ls_z = features.get("taker_ls_z")

    for i, hpos in enumerate(hpos_arr):
        if hpos == 0:
            continue

        g = 0.0
        if cfg.get("soft"):
            if hpos > 0:
                # Long danger: hot funding/crowded longs, OI deleveraging, negative taker flow.
                if funding_z is not None:
                    g += cfg.get("w_funding", 0.0) * _stress_pos(float(funding_z[i]), 1.0, 1.0)
                if oi24 is not None:
                    g += cfg.get("w_oi", 0.0) * _stress_neg(float(oi24[i]), -0.02, 0.03)
                if oi_z is not None:
                    g += cfg.get("w_oi", 0.0) * _stress_neg(float(oi_z[i]), -1.25, 1.0)
                if lsr_z is not None:
                    g += cfg.get("w_lsr", 0.0) * _stress_pos(float(lsr_z[i]), 1.0, 1.0)
                if top_lsr_z is not None:
                    g += cfg.get("w_lsr", 0.0) * _stress_pos(float(top_lsr_z[i]), 1.0, 1.0)
                if tbr_z is not None:
                    g += cfg.get("w_taker", 0.0) * _stress_neg(float(tbr_z[i]), -0.25, 1.0)
                if taker_ls_z is not None:
                    g += cfg.get("w_taker", 0.0) * _stress_neg(float(taker_ls_z[i]), -0.25, 1.0)
            else:
                # Short danger: positive taker flow against the short.
                if tbr_z is not None:
                    g += cfg.get("w_taker", 0.0) * _stress_pos(float(tbr_z[i]), 0.25, 1.0)
                if taker_ls_z is not None:
                    g += cfg.get("w_taker", 0.0) * _stress_pos(float(taker_ls_z[i]), 0.25, 1.0)

        gammas[i] = min(g, 3.0)

    if cfg.get("rho"):
        finite = rho_arr[np.isfinite(rho_arr) & (rho_arr > 0)]
        rho_ref = float(np.nanpercentile(finite, 25)) if len(finite) else 1.0
        rho_scale = np.clip(rho_arr / max(rho_ref, 1e-12), 0.50, 1.10)
        rho_scale[~np.isfinite(rho_scale)] = 1.0

    total_scale = rho_scale / (1.0 + gammas)
    total_scale = np.clip(total_scale, 0.20, 1.10)
    out *= total_scale
    return out, dict(
        avg_micro_gamma=float(np.mean(gammas[hpos_arr != 0])) if np.any(hpos_arr != 0) else 0.0,
        avg_rho_scale=float(np.mean(rho_scale[hpos_arr != 0])) if np.any(hpos_arr != 0) else 1.0,
        avg_total_scale=float(np.mean(total_scale[hpos_arr != 0])) if np.any(hpos_arr != 0) else 1.0,
    )


def run_variant_v28(cfg: dict,
                    inputs: dict,
                    sig_map: dict[str, pd.Series],
                    log_ann: pd.DataFrame) -> dict:
    unit_sum = None
    per_asset = {}
    asset_to_sym = {"btc": "BTCUSDT", "sol": "SOLUSDT", "eth": "ETHUSDT"}

    for asset, p0 in inputs.items():
        p, diag = v12.prepare_input(p0, asset, v27.CHAMPION_CFG, sig_map[asset], log_ann)
        sl = BASE["sl_mult"] * p["daily_vol"]
        tp = BASE["tp_mult"] * p["daily_vol"]
        trail_trigger = 1.50 * p["daily_vol"]
        trail_dist = 0.75 * p["daily_vol"]
        be_trigger = float(v27.CHAMPION_CFG["be_frac"]) * tp if asset in v27.CHAMPION_CFG["be_assets"] else None
        hours_idx = p["hours"]

        ms = v27._get_ms(asset_to_sym.get(asset, asset.upper() + "USDT"))

        def _align_shift(col: str, default: float = np.nan) -> np.ndarray:
            if col not in ms.columns:
                return np.full(len(hours_idx), default, dtype=float)
            s = ms[col]
            if s.index.tz is not None:
                s = s.tz_convert("UTC").tz_localize(None)
            return s.shift(1).reindex(hours_idx, method="ffill").fillna(default).values.astype(float)

        feature_cols = [
            "taker_buy_ratio", "funding_rate", "tbr_z", "funding_z",
            "oi_pct_1h", "oi_pct_24h", "oi_z", "lsr_z", "top_lsr_z", "taker_ls_z",
            "oi_usd", "lsr", "top_lsr", "taker_ls",
        ]
        features = {c: _align_shift(c, 0.5 if c == "taker_buy_ratio" else np.nan) for c in feature_cols}

        rho = log_ann["rho_eff"].reindex(hours_idx, method="ffill").fillna(1.0).values.astype(float)
        psi_soft, soft_diag = apply_soft_friction(p["psi_y"], p["hpos"], features, rho, cfg)

        # Hard part: retain proven TBR base; optional hard funding guard reproduces v27 champion.
        fcfg_hard = dict(
            tbr_long_min=cfg.get("tbr_long_min"),
            tbr_short_max=cfg.get("tbr_short_max"),
            funding_z_long_max=cfg.get("hard_funding_z_long_max"),
        )

        arr, _, _, counts = v27.simulate_unit_v27(
            p["op"], p["hi"], p["lo"], p["cl"],
            p["hpos"], p["dpos"], p["dactive"], psi_soft,
            sl, tp, trail_trigger, trail_dist, p["ze7"], v12.BASE_ZE7,
            be_trigger=be_trigger, be_buffer=float(v27.CHAMPION_CFG["be_buf"]),
            features=features, fcfg=fcfg_hard,
        )
        unit = pd.Series(arr, index=hours_idx)
        unit_sum = unit if unit_sum is None else unit_sum.add(unit, fill_value=0.0)
        per_asset[asset] = dict(counts=counts, diag=diag, soft=soft_diag)

    return dict(unit=unit_sum.sort_index().fillna(0.0), per_asset=per_asset)


def simulate_combined_v28(unit: pd.Series) -> dict:
    return simulate_combined(
        unit_normal=unit,
        unit_crash=pd.Series(0.0, index=unit.index),
        K_normal=K_NORMAL,
        K_crash=0.0,
        dd_soft=DYN_DD_SOFT,
        dd_stop=DYN_DD_STOP,
        y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT,
        cb_resume=CB_RESUME,
        cb_window_days=CB_WINDOW_DAYS,
        use_cb=True,
    )


def _yoy_table(eq: pd.Series) -> list[dict]:
    rows = []
    for row in period_table(eq, "Y"):
        row["period"] = row["period"][:4]
        rows.append(row)
    return rows


def main() -> None:
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v28 — CANONICAL STABILITY + SOFT MICROSTRUCTURE FRICTION")
    print(BAR)

    print("\n[1] Building canonical engine with conditioning check ...")
    df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask = np.asarray(df.index >= TEST_START)
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v28")
    Sigma_reg, cond_diag = condition_cap_sigma(Sigma_f, KAPPA_CAP)
    if not APPLY_SIGMA_REG:
        Sigma_reg = Sigma_f
        cond_diag = dict(**cond_diag, applied=False)
        print(f"  [v28] Sigma regularization disabled for control run; cond={cond_diag['cond_before']:.2f}")
    elif cond_diag["regularized"]:
        cond_diag = dict(**cond_diag, applied=True)
        theta = theta * (cond_diag["cond_before"] / KAPPA_CAP)
        print(f"  [v28] Sigma regularized: cond {cond_diag['cond_before']:.2f} → {cond_diag['cond_after']:.2f}; theta adjusted to {theta:.4f}")
    else:
        cond_diag = dict(**cond_diag, applied=True)
        print(f"  [v28] Sigma conditioning OK: cond={cond_diag['cond_before']:.2f}")

    log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_reg, theta,
                                kappa=KAPPA_A, anneal=True, label="v28_anneal")
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs = attach_q_hot(inputs_noq, inputs_q)
    sig_map = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}") for asset, _, _, idx in ASSETS}
    test_ts = pd.Timestamp(TEST_START)

    print("\n[2] Preloading cached microstructure ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = v27._get_ms(sym)
        print(f"  {sym}: shape={ms.shape}")

    print(f"\n[3] Running {len(VARIANTS)} v28 variants ...")
    results = []
    for cfg in VARIANTS:
        res = run_variant_v28(cfg, inputs, sig_map, log_ann)
        sim = simulate_combined_v28(res["unit"])
        eq_oos = sim["eq"][sim["eq"].index >= test_ts]
        m = equity_metrics(eq_oos, cfg["name"])
        yoy = {r["period"]: r["return_pct"] for r in _yoy_table(eq_oos)}

        counts_total = {}
        soft_rows = []
        for pa in res["per_asset"].values():
            for k, v in pa["counts"].items():
                counts_total[k] = counts_total.get(k, 0) + int(v)
            soft_rows.append(pa["soft"])
        veto_keys = [k for k in counts_total if k.startswith("vetoed_") and k != "vetoed_ze7"]
        vetoes = sum(counts_total[k] for k in veto_keys)
        entries = counts_total.get("entries", 0)
        soft_avg = {k: float(np.mean([s[k] for s in soft_rows])) for k in soft_rows[0]}

        row = dict(
            name=cfg["name"], final=m["final"], cagr=m["cagr"], calmar=m["calmar"],
            sharpe=m["sharpe"], maxdd=m["maxdd"], pct_halted=sim["pct_halted"],
            entries=entries, veto_pct=vetoes / max(vetoes + entries, 1),
            r2023=yoy.get("2023", np.nan), r2024=yoy.get("2024", np.nan),
            r2025=yoy.get("2025", np.nan), r2026=yoy.get("2026", np.nan),
            counts=counts_total, soft=soft_avg, config=cfg,
        )
        results.append(row)
        print(f"  {cfg['name']:<24} final=${m['final']:>10,.0f} CAGR={m['cagr']:+7.2%} "
              f"Calmar={m['calmar']:+6.3f} MaxDD={m['maxdd']:+.2%} "
              f"soft={soft_avg['avg_total_scale']:.3f} veto={row['veto_pct']:.1%}")

    best = max(results, key=lambda x: x["calmar"])
    best_final = max(results, key=lambda x: x["final"])
    print("\n" + BAR)
    print("  v28 RESULTS")
    print(BAR)
    for r in sorted(results, key=lambda x: -x["calmar"]):
        print(f"  {r['name']:<24} ${r['final']:>10,.0f}  CAGR={r['cagr']:+7.2%}  "
              f"Calmar={r['calmar']:+6.3f}  Sharpe={r['sharpe']:+.3f}  MaxDD={r['maxdd']:+.2%}  "
              f"2023={r['r2023']:+.1%} 2024={r['r2024']:+.1%} 2025={r['r2025']:+.1%}")
    print(f"\n  Best Calmar: {best['name']}  Calmar={best['calmar']:+.3f} final=${best['final']:,.0f}")
    print(f"  Best final : {best_final['name']}  final=${best_final['final']:,.0f} Calmar={best_final['calmar']:+.3f}")

    out_name = "crypto_godmode_v28_canonical_stability.json" if APPLY_SIGMA_REG else "crypto_godmode_v28_canonical_stability_noreg.json"
    out = OUT_DIR_ / out_name
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dict(
            meta=dict(version="v28_canonical_stability", base="v27_funding_hot_guard",
                      oos_start=TEST_START, K_normal=K_NORMAL, rt_bps=REALISTIC_RT_BPS,
                      kappa_cap=KAPPA_CAP, cond=cond_diag, calibration=diag,
                      elapsed=time.time() - t0),
            results=results,
            best_calmar=best,
            best_final=best_final,
        ), f, indent=2, default=float)
    print(f"\n  Saved → {out}")
    print(f"  Elapsed: {time.time() - t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()