"""
run_crypto_godmode_v29_regularized_validation.py
================================================

Validate the NEW regularised canonical engine discovered in v28.

Important: this is NOT the same engine as v27.  v29 deliberately changes the
canonical geometry by regularising Sigma_f to cap its condition number.

Validation performed:
  1. 2023-2026 OOS K sweep for v28 regularised soft_all_micro.
  2. Fee/slippage stress for K=6.0 and the best K.
  3. Extended 2022-2026 OOS check to see whether it survives the bear market.

All microstructure features are shifted one hour in v28.run_variant_v28.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

import run_crypto_godmode_v27_all_microstructure as v27
import run_crypto_godmode_v28_canonical_stability as v28
from run_crypto_pairs_v34_full_combined import OUT_DIR, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import KAPPA_A, W_TARGET_A1, build_b_aligned, build_w_star, calibrate, run_godmode_sweep
from run_crypto_godmode_v8_multiasset_shell import ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR, INIT, equity_metrics, period_table, simulate_combined


BAR = "=" * 108
OUT_DIR_ = Path(OUT_DIR) / "v29_regularized_validation"
K_GRID = [3.0, 4.0, 5.0, 6.0, 6.5, 7.0]
COST_GRID_BPS = [0.0, 2.0, 6.0, 10.0, 20.0]
K_BASE = 6.0

# v28 regularised winner.
REG_VARIANT = dict(name="soft_all_micro", tbr_long_min=0.47, tbr_short_max=0.53,
                   soft=True, rho=False, w_funding=0.25, w_oi=0.18,
                   w_lsr=0.16, w_taker=0.16)


def simulate_k(unit: pd.Series, k: float) -> dict:
    return simulate_combined(
        unit_normal=unit,
        unit_crash=pd.Series(0.0, index=unit.index),
        K_normal=k,
        K_crash=0.0,
        dd_soft=DYN_DD_SOFT,
        dd_stop=DYN_DD_STOP,
        y_floor=DYN_Y_FLOOR,
        cb_halt=v28.CB_HALT,
        cb_resume=v28.CB_RESUME,
        cb_window_days=v28.CB_WINDOW_DAYS,
        use_cb=True,
    )


def yoy(eq: pd.Series) -> dict[str, float]:
    return {r["period"][:4]: r["return_pct"] for r in period_table(eq, "Y")}


def build_regularized_engine(test_start: str, label: str) -> dict:
    print(f"\n[build] {label}: train < {test_start}")
    df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < test_start))
    test_mask = np.asarray(df.index >= test_start)
    ohlc_map = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch = get_channel_series()
    w_star = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label=label)
    Sigma_reg, cond_diag = v28.condition_cap_sigma(Sigma_f, v28.KAPPA_CAP)
    theta_reg = theta * (cond_diag["cond_before"] / v28.KAPPA_CAP) if cond_diag["regularized"] else theta
    print(f"  [{label}] cond {cond_diag['cond_before']:.2f} → {cond_diag['cond_after']:.2f}; theta {theta:.4f} → {theta_reg:.4f}")

    log_ann = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_reg, theta_reg,
                                kappa=KAPPA_A, anneal=True, label=f"{label}_anneal")
    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs = attach_q_hot(inputs_noq, inputs_q)
    sig_map = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}") for asset, _, _, idx in ASSETS}
    return dict(df=df, train_mask=train_mask, test_mask=test_mask, log_ann=log_ann,
                inputs=inputs, sig_map=sig_map, test_ts=pd.Timestamp(test_start),
                theta=theta_reg, cond=cond_diag, calibration=diag)


def run_unit_for_cost(engine: dict, rt_bps: float) -> dict:
    v27.RT_COST = rt_bps / 10_000.0
    return v28.run_variant_v28(REG_VARIANT, engine["inputs"], engine["sig_map"], engine["log_ann"])


def row_from_sim(name: str, rt_bps: float, k: float, sim: dict, test_ts: pd.Timestamp) -> dict:
    eq = sim["eq"][sim["eq"].index >= test_ts]
    m = equity_metrics(eq, name)
    yy = yoy(eq)
    return dict(
        name=name, rt_bps=rt_bps, K=k,
        final=m["final"], profit=m["final"] - INIT,
        cagr=m["cagr"], sharpe=m["sharpe"], maxdd=m["maxdd"], calmar=m["calmar"],
        pct_halted=sim.get("pct_halted", np.nan),
        r2022=yy.get("2022", np.nan), r2023=yy.get("2023", np.nan),
        r2024=yy.get("2024", np.nan), r2025=yy.get("2025", np.nan), r2026=yy.get("2026", np.nan),
    )


def main() -> None:
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print(BAR)
    print("  CRYPTO GODMODE v29 — REGULARISED CANONICAL ENGINE VALIDATION")
    print(BAR)

    # Preload cache explicitly.
    print("\n[0] Preloading microstructure cache ...")
    for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        ms = v27._get_ms(sym)
        print(f"  {sym}: {ms.shape}")

    # 2023-2026 validation.
    engine_2023 = build_regularized_engine("2023-01-01", "v29_2023")

    print("\n[1] K sweep at realistic 6 bps RT ...")
    v27.RT_COST = 6.0 / 10_000.0
    unit_6bp = run_unit_for_cost(engine_2023, 6.0)["unit"]
    k_rows = []
    for k in K_GRID:
        sim = simulate_k(unit_6bp, k)
        row = row_from_sim(f"K{k:.1f}_6bps", 6.0, k, sim, engine_2023["test_ts"])
        k_rows.append(row)
        print(f"  K={k:.1f}: final=${row['final']:>10,.0f} CAGR={row['cagr']:+7.2%} Calmar={row['calmar']:+6.3f} MaxDD={row['maxdd']:+.2%}")
    best_k = max(k_rows, key=lambda r: r["calmar"])
    best_k_final = max(k_rows, key=lambda r: r["final"])

    print("\n[2] Cost stress for K=6.0 and best-Calmar K ...")
    cost_rows = []
    for rt in COST_GRID_BPS:
        unit = run_unit_for_cost(engine_2023, rt)["unit"]
        for k in sorted(set([K_BASE, best_k["K"]])):
            sim = simulate_k(unit, k)
            row = row_from_sim(f"K{k:.1f}_{rt:.0f}bps", rt, k, sim, engine_2023["test_ts"])
            cost_rows.append(row)
            print(f"  rt={rt:>4.0f}bps K={k:.1f}: final=${row['final']:>10,.0f} Calmar={row['calmar']:+6.3f} MaxDD={row['maxdd']:+.2%}")

    print("\n[3] Extended 2022-2026 bear-market validation ...")
    engine_2022 = build_regularized_engine("2022-01-01", "v29_2022")
    unit_ext = run_unit_for_cost(engine_2022, 6.0)["unit"]
    ext_rows = []
    for k in [K_BASE, best_k["K"]]:
        sim = simulate_k(unit_ext, k)
        row = row_from_sim(f"extended_K{k:.1f}", 6.0, k, sim, engine_2022["test_ts"])
        ext_rows.append(row)
        print(f"  extended K={k:.1f}: final=${row['final']:>10,.0f} CAGR={row['cagr']:+7.2%} Calmar={row['calmar']:+6.3f} MaxDD={row['maxdd']:+.2%} 2022={row['r2022']:+.1%}")

    print("\n" + BAR)
    print("  v29 VALIDATION SUMMARY")
    print(BAR)
    print(f"  Best 2023-2026 Calmar K: K={best_k['K']:.1f} final=${best_k['final']:,.0f} Calmar={best_k['calmar']:+.3f} MaxDD={best_k['maxdd']:+.2%}")
    print(f"  Best 2023-2026 Final  K: K={best_k_final['K']:.1f} final=${best_k_final['final']:,.0f} Calmar={best_k_final['calmar']:+.3f} MaxDD={best_k_final['maxdd']:+.2%}")
    best_ext = max(ext_rows, key=lambda r: r["calmar"])
    print(f"  Best 2022-2026 Extended: K={best_ext['K']:.1f} final=${best_ext['final']:,.0f} Calmar={best_ext['calmar']:+.3f} MaxDD={best_ext['maxdd']:+.2%}")

    out = OUT_DIR_ / "crypto_godmode_v29_regularized_validation.json"
    payload = dict(
        meta=dict(version="v29_regularized_validation", variant=REG_VARIANT,
                  k_grid=K_GRID, cost_grid_bps=COST_GRID_BPS,
                  elapsed=time.time() - t0),
        engine_2023=dict(cond=engine_2023["cond"], theta=engine_2023["theta"]),
        engine_2022=dict(cond=engine_2022["cond"], theta=engine_2022["theta"]),
        k_sweep=k_rows,
        cost_stress=cost_rows,
        extended=ext_rows,
        selected=dict(best_k_calmar=best_k, best_k_final=best_k_final, best_extended=best_ext),
    )
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=float)
    print(f"\n  Saved → {out}")
    print(f"  Elapsed: {time.time() - t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()