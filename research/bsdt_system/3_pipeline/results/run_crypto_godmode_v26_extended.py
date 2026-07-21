"""
run_crypto_godmode_v26_extended.py
====================================
OBJECTIVE: Test the previous best microstructure filter (tbr0p47 from v25)
           over an EXTENDED out-of-sample window starting 2022-01-01.

KEY DIFFERENCES vs v25:
  1. TEST_START overridden to "2022-01-01" (training = 2021 only, OOS = 2022-2026)
  2. Only 4 focused variants:
       baseline          — no filters (v17 equivalent on extended window)
       tbr0p47           — best from v25 (Calmar=+8.789)
       fr0003            — second best from v25 (Calmar=+8.659)
       tbr0p47+fr0003    — untested combination (first time!)
  3. Year breakdown shows 5 years: 2022 (bear), 2023, 2024, 2025, 2026

CONTEXT:
  v25 tested 13 filter variants over 2023-2026.
  Best result: tbr0p47  Calmar=+8.789 (+3% over baseline 8.530)
  2nd result:  fr0003   Calmar=+8.659 (+1.5%)
  Combo tbr0p47+fr0003 was not tested — we had tbr0.48+fr but not tbr0.47+fr.

  Now we extend the OOS to include 2022 (the -65% BTC bear market) to:
   (a) stress-test the CB mechanism in a genuine multi-month bear market
   (b) observe whether tbr0p47 adds value during the 2022 crash
   (c) test the never-tried tbr0p47+fr0003 combination

DATA AVAILABILITY (2022-01-01 forward):
  TBR (taker_buy_ratio): BTC/ETH/SOL ✓
  FR  (funding_rate):    BTC/ETH/SOL ✓
  DV  (OI, LSR):         ETH/SOL ✓  BTC from 2023 only  ← not used in these variants
  OHLCV 1h:             BTC/ETH ✓   SOL from 2021 ✓

BENCHMARK (v25, 2023-2026):
  BASELINE:  CAGR=+205.71%  Calmar=+8.530  MaxDD=-24.11%
  tbr0p47:   CAGR=+206.10%  Calmar=+8.789  MaxDD=-23.45%
  fr0003:    CAGR=+208.80%  Calmar=+8.659  MaxDD=-24.11%
"""
from __future__ import annotations

import sys
import time
import json
from pathlib import Path

import numpy as np
import pandas as pd

# ─── imports from existing pipeline ──────────────────────────────────────────

sys.path.insert(0, str(Path(__file__).parent))

import run_crypto_godmode_v12_filter_innovate as v12
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TRAIN_START, build_1h_df,
)
from run_crypto_godmode_v1 import (
    KAPPA_A, W_TARGET_A1, build_w_star, build_b_aligned, calibrate, run_godmode_sweep,
)
from run_crypto_godmode_v8_multiasset_shell import (
    fetch_futures_ohlcv_symbol, ASSETS, build_asset_inputs,
)
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from simulate_master_strategy import (
    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
    FUND_HOURLY, simulate_combined, equity_metrics, period_table, INIT,
)
from simulate_master_strategy import RT_COST as _RT_COST
from run_crypto_microstructure_data import load_microstructure

# ─── EXTENDED OOS override ───────────────────────────────────────────────────
# Override TEST_START to 2022-01-01 (vs v25/v17 which used 2023-01-01)
# Training window = 2021-01-01 to 2021-12-31 (1 year)
# OOS window      = 2022-01-01 to 2026-05-13 (4.5 years incl. 2022 bear market)

TEST_START_V26  = "2022-01-01"   # OOS starts here
TRAIN_START_V26 = TRAIN_START    # '2021-01-01' — unchanged

# ─── champion config from v17 ────────────────────────────────────────────────

CHAMPION_CFG = dict(
    name="be50_btc_sol",
    persist=0,
    be_assets={"btc", "sol"},
    be_frac=0.50,
    be_buf=0.0005,
    sol_halve=False,
    gamma_max=None,
    cos_min=None,
)

K_NORMAL          = 6.0
REALISTIC_RT_BPS  = 6.0
RT_COST           = REALISTIC_RT_BPS / 1e4   # override module-level RT_COST

CB_HALT        = 0.08
CB_RESUME      = 0.01
CB_WINDOW_DAYS = 180

OUT_DIR_ = Path(OUT_DIR) / "v26_extended"

# ─── 4 focused filter variants ───────────────────────────────────────────────

FILTER_VARIANTS = [
    # Baseline: no filters (v17 equivalent)
    dict(name="baseline",        tbr_long_min=None, tbr_short_max=None, fr_long_max=None, oi_long_floor=None),
    # Best from v25 — TBR threshold only
    dict(name="tbr0p47",         tbr_long_min=0.47, tbr_short_max=0.53, fr_long_max=None, oi_long_floor=None),
    # 2nd best from v25 — funding rate only
    dict(name="fr0003",          tbr_long_min=None, tbr_short_max=None, fr_long_max=0.0003, oi_long_floor=None),
    # FIRST TIME: tbr0p47 + fr0003 combined
    dict(name="tbr0p47+fr0003",  tbr_long_min=0.47, tbr_short_max=0.53, fr_long_max=0.0003, oi_long_floor=None),
]


# ─── simulation (identical to v25) ───────────────────────────────────────────

def simulate_unit_breakeven_v26(
    op, hi, lo, cl,
    hpos_arr, dpos_arr, dactive_arr, psi_y,
    sl: float, tp: float,
    trail_trigger: float, trail_dist: float,
    ze7_arr: np.ndarray, ze7_min: float,
    be_trigger: float | None, be_buffer: float = 0.0,
    tbr_arr:      np.ndarray | None = None,
    fr_arr:       np.ndarray | None = None,
    oi_pct1h_arr: np.ndarray | None = None,
    tbr_long_min:  float | None = None,
    tbr_short_max: float | None = None,
    fr_long_max:   float | None = None,
    oi_long_floor: float | None = None,
):
    n = len(op)
    ret       = np.zeros(n, dtype=float)
    long_arr  = np.zeros(n, dtype=float)
    short_arr = np.zeros(n, dtype=float)

    pos = 0.0; size = 1.0; entry = 0.0
    stop_px = 0.0; take_px = 0.0; trail_ext = 0.0
    trail_active = False; be_active = False

    counts = dict(
        entries=0, exits=0, longs=0, shorts=0,
        stop=0, tp=0, trail_exit=0, signal_exit=0, close_end=0,
        vetoed_ze7=0, skipped_daily_filter=0,
        active_hours=0, breakeven_exit=0, be_armed=0,
        vetoed_tbr_long=0, vetoed_tbr_short=0,
        vetoed_fr_long=0, vetoed_oi_long=0,
    )

    for i in range(n):
        hpos  = int(hpos_arr[i]);  hactive = hpos != 0
        dpos  = int(dpos_arr[i]);  dact    = bool(dactive_arr[i])
        scale = float(psi_y[i])
        if hactive:
            if dact and hpos == dpos:
                pass
            elif dact and hpos != dpos:
                hactive = False; hpos = 0; counts["skipped_daily_filter"] += 1
            else:
                scale *= 0.5
        if hactive and scale <= 1e-12:
            hactive = False; hpos = 0

        bar_dir = int(pos)

        if pos != 0:
            counts["active_hours"] += 1
            exit_ret = None; reason = None

            if pos > 0:
                if hi[i] >= take_px:
                    exit_ret = take_px / entry - 1.0; reason = "tp"
                else:
                    trail_ext = max(trail_ext, hi[i])
                    if be_trigger is not None and (trail_ext / entry - 1.0) >= be_trigger:
                        new_stop = entry * (1.0 + be_buffer)
                        if new_stop > stop_px:
                            stop_px = new_stop
                            if not be_active:
                                counts["be_armed"] += 1
                            be_active = True
                    if trail_ext / entry - 1.0 >= trail_trigger:
                        trail_active = True
                    if trail_active:
                        stop_px = max(stop_px, trail_ext * (1.0 - trail_dist))
                    if lo[i] <= stop_px:
                        exit_ret = stop_px / entry - 1.0
                        reason = "trail_exit" if trail_active else ("breakeven_exit" if be_active else "stop")
            else:  # short
                if lo[i] <= take_px:
                    exit_ret = entry / take_px - 1.0; reason = "tp"
                else:
                    trail_ext = min(trail_ext, lo[i])
                    if be_trigger is not None and (entry / trail_ext - 1.0) >= be_trigger:
                        new_stop = entry * (1.0 - be_buffer)
                        if new_stop < stop_px:
                            stop_px = new_stop
                            if not be_active:
                                counts["be_armed"] += 1
                            be_active = True
                    if entry / trail_ext - 1.0 >= trail_trigger:
                        trail_active = True
                    if trail_active:
                        stop_px = min(stop_px, trail_ext * (1.0 + trail_dist))
                    if hi[i] >= stop_px:
                        exit_ret = entry / stop_px - 1.0
                        reason = "trail_exit" if trail_active else ("breakeven_exit" if be_active else "stop")

            if exit_ret is None and hactive and hpos == -pos:
                exit_ret = (op[i] / entry - 1.0) if pos > 0 else (entry / op[i] - 1.0)
                reason = "signal_exit"

            if exit_ret is not None:
                bar_pnl = size * (float(exit_ret) - RT_COST)
                ret[i] += bar_pnl
                if bar_dir > 0: long_arr[i]  += bar_pnl
                else:           short_arr[i] += bar_pnl
                counts[reason] += 1; counts["exits"] += 1
                pos = 0.0; size = 1.0; entry = 0.0
                stop_px = 0.0; take_px = 0.0
                trail_ext = 0.0; trail_active = False; be_active = False
            else:
                funding = size * FUND_HOURLY
                ret[i] -= funding
                if bar_dir > 0: long_arr[i]  -= funding
                else:           short_arr[i] -= funding

        if pos == 0 and hactive:
            if abs(float(ze7_arr[i])) < ze7_min:
                counts["vetoed_ze7"] += 1
                continue

            tbr = None if tbr_arr       is None else float(tbr_arr[i])
            fr  = None if fr_arr        is None else float(fr_arr[i])
            oi1 = None if oi_pct1h_arr  is None else float(oi_pct1h_arr[i])

            if hpos > 0:
                if tbr_long_min is not None and tbr is not None and not np.isnan(tbr) and tbr < tbr_long_min:
                    counts["vetoed_tbr_long"] += 1;  continue
                if fr_long_max  is not None and fr  is not None and not np.isnan(fr)  and fr  > fr_long_max:
                    counts["vetoed_fr_long"]  += 1;  continue
                if oi_long_floor is not None and oi1 is not None and not np.isnan(oi1) and oi1 < oi_long_floor:
                    counts["vetoed_oi_long"]  += 1;  continue

            if hpos < 0:
                if tbr_short_max is not None and tbr is not None and not np.isnan(tbr) and tbr > tbr_short_max:
                    counts["vetoed_tbr_short"] += 1; continue

            pos = float(hpos); size = float(scale); entry = float(op[i])
            trail_ext = entry; be_active = False
            if pos > 0:
                stop_px = entry * (1.0 - sl); take_px = entry * (1.0 + tp); counts["longs"] += 1
            else:
                stop_px = entry * (1.0 + sl); take_px = entry * (1.0 - tp); counts["shorts"] += 1
            counts["entries"] += 1

    if pos != 0:
        gross = (cl[-1] / entry - 1.0) if pos > 0 else (entry / cl[-1] - 1.0)
        bar_pnl = size * (gross - RT_COST)
        ret[-1] += bar_pnl
        if pos > 0: long_arr[-1]  += bar_pnl
        else:       short_arr[-1] += bar_pnl
        counts["close_end"] += 1; counts["exits"] += 1

    return ret, long_arr, short_arr, counts


# ─── microstructure cache ─────────────────────────────────────────────────────

_MS_CACHE: dict[str, pd.DataFrame] = {}

def _get_ms(symbol: str) -> pd.DataFrame:
    if symbol not in _MS_CACHE:
        _MS_CACHE[symbol] = load_microstructure(symbol, start="2022-01-01", end="2026-06-01")
    return _MS_CACHE[symbol]


# ─── run one variant ──────────────────────────────────────────────────────────

def run_variant_v26(
    cfg:     dict,
    fcfg:    dict,
    inputs:  dict,
    sig_map: dict[str, pd.Series],
    log_ann: pd.DataFrame,
) -> dict:
    from test_psi_adaptive_y import BASE
    unit_sum:       pd.Series | None = None
    unit_long_sum:  pd.Series | None = None
    unit_short_sum: pd.Series | None = None
    per_asset = {}

    asset_to_sym = {"btc": "BTCUSDT", "sol": "SOLUSDT", "eth": "ETHUSDT"}

    for asset, p0 in inputs.items():
        p, diag = v12.prepare_input(p0, asset, cfg, sig_map[asset], log_ann)

        sl            = BASE["sl_mult"]   * p["daily_vol"]
        tp            = BASE["tp_mult"]   * p["daily_vol"]
        trail_trigger = 1.50 * p["daily_vol"]
        trail_dist    = 0.75 * p["daily_vol"]
        be_trigger    = None
        if asset in cfg["be_assets"] and cfg["be_frac"] is not None:
            be_trigger = float(cfg["be_frac"]) * tp

        hours_idx = p["hours"]
        sym = asset_to_sym.get(asset, asset.upper() + "USDT")
        ms  = _get_ms(sym)

        def _align_shift(col: str, default: float) -> np.ndarray:
            if col not in ms.columns:
                return np.full(len(hours_idx), np.nan)
            s = ms[col]
            if s.index.tz is not None:
                s = s.tz_convert("UTC").tz_localize(None)
            aligned = s.shift(1).reindex(hours_idx, method="ffill").fillna(default)
            return aligned.values.astype(float)

        tbr_arr      = _align_shift("taker_buy_ratio", 0.5)
        fr_arr       = _align_shift("funding_rate",    0.0)
        oi_pct1h_arr = _align_shift("oi_pct_1h",       0.0) if "oi_pct_1h" in ms.columns else None

        arr, long_arr, short_arr, counts = simulate_unit_breakeven_v26(
            p["op"], p["hi"], p["lo"], p["cl"],
            p["hpos"], p["dpos"], p["dactive"], p["psi_y"],
            sl, tp, trail_trigger, trail_dist, p["ze7"], v12.BASE_ZE7,
            be_trigger=be_trigger, be_buffer=float(cfg["be_buf"]),
            tbr_arr=tbr_arr,
            fr_arr=fr_arr,
            oi_pct1h_arr=oi_pct1h_arr,
            tbr_long_min=fcfg.get("tbr_long_min"),
            tbr_short_max=fcfg.get("tbr_short_max"),
            fr_long_max=fcfg.get("fr_long_max"),
            oi_long_floor=fcfg.get("oi_long_floor"),
        )

        unit  = pd.Series(arr,       index=hours_idx)
        unitL = pd.Series(long_arr,  index=hours_idx)
        unitS = pd.Series(short_arr, index=hours_idx)

        unit_sum       = unit  if unit_sum       is None else unit_sum.add(unit,  fill_value=0.0)
        unit_long_sum  = unitL if unit_long_sum  is None else unit_long_sum.add(unitL, fill_value=0.0)
        unit_short_sum = unitS if unit_short_sum is None else unit_short_sum.add(unitS, fill_value=0.0)
        per_asset[asset] = dict(counts=counts, diag=diag)

    assert unit_sum is not None
    unit_sum       = unit_sum.sort_index().fillna(0.0)
    unit_long_sum  = unit_long_sum.sort_index().fillna(0.0)
    unit_short_sum = unit_short_sum.sort_index().fillna(0.0)
    return dict(
        unit=unit_sum,
        unit_long=unit_long_sum,
        unit_short=unit_short_sum,
        per_asset=per_asset,
    )


# ─── CB simulation ────────────────────────────────────────────────────────────

def simulate_combined_v26(unit: pd.Series) -> dict:
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


# ─── helpers ──────────────────────────────────────────────────────────────────

BAR = "=" * 70

def _yoy_table(eq: pd.Series) -> list[dict]:
    rows = []
    for row in period_table(eq, "Y"):
        row["period"] = row["period"][:4]
        rows.append(row)
    return rows


def _print_yoy(eq: pd.Series, label: str) -> None:
    print(f"\n  {label} year-by-year:")
    for r in _yoy_table(eq):
        print(f"    {r['period']}: ${r['start_eq']:>9,.0f} → ${r['end_eq']:>9,.0f}  "
              f"ret={r['return_pct']:+.1%}  sharpe={r['sharpe']:+.3f}  maxdd={r['maxdd']:+.1%}")


def _m(eq: pd.Series, label: str) -> dict:
    return equity_metrics(eq, label)


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    OUT_DIR_.mkdir(parents=True, exist_ok=True)

    print(BAR)
    print("  CRYPTO GODMODE v26 — EXTENDED OOS (2022-2026)")
    print(BAR)
    print(f"  Champion: {CHAMPION_CFG['name']}")
    print(f"  CB: halt={CB_HALT:.0%}  resume={CB_RESUME:.0%}  window={CB_WINDOW_DAYS}d")
    print(f"  K_NORMAL={K_NORMAL}  RT_BPS={REALISTIC_RT_BPS}")
    print(f"  Training: {TRAIN_START_V26} → 2021-12-31  (1 year)")
    print(f"  OOS:      {TEST_START_V26} → 2026  (4.5 years, includes 2022 bear)")
    print(f"  Variants: {len(FILTER_VARIANTS)}")
    print()

    # ── 1. Build canonical engine ─────────────────────────────────────────────
    print("[1] Building canonical engine (train=2021, OOS=2022-2026)...")
    df, has_sol = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask  = np.asarray((df.index >= TRAIN_START_V26) & (df.index < TEST_START_V26))
    test_mask   = np.asarray(df.index >= TEST_START_V26)
    ohlc_map    = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch          = get_channel_series()
    w_star      = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned   = build_b_aligned(w_star)
    Sigma_f, theta, _ = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v26")
    log_ann     = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned,
                                     Sigma_f, theta, kappa=KAPPA_A, anneal=True, label="v26_anneal")
    inputs_noq  = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                      signal_kind="wstar", use_quadrant=False)
    inputs_q    = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map,
                                      signal_kind="wstar", use_quadrant=True)
    inputs      = attach_q_hot(inputs_noq, inputs_q)
    sig_map     = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                   for asset, _, _, idx in ASSETS}
    test_ts     = pd.Timestamp(TEST_START_V26)
    n_train     = int(train_mask.sum())
    n_test      = int(test_mask.sum())
    print(f"  Engine built. Data: {df.index[0].date()} → {df.index[-1].date()}  "
          f"train={n_train:,}h ({n_train//8760:.1f}yr)  test={n_test:,}h ({n_test//8760:.1f}yr)")

    # ── 2. Load microstructure data ───────────────────────────────────────────
    print("\n[2] Loading microstructure data (2022-01-01 onward)...")
    _ASSET_TO_SYM = {"btc": "BTCUSDT", "sol": "SOLUSDT", "eth": "ETHUSDT"}
    for asset in inputs.keys():
        sym = _ASSET_TO_SYM.get(asset, asset.upper() + "USDT")
        ms  = _get_ms(sym)
        tbr_avail = "taker_buy_ratio" in ms.columns
        fr_avail  = "funding_rate" in ms.columns
        # Find earliest non-NaN TBR in 2022
        if tbr_avail:
            tbr_2022 = ms.loc["2022-01-01":"2022-12-31", "taker_buy_ratio"].dropna()
            tbr_coverage = f"{len(tbr_2022):,} bars in 2022" if len(tbr_2022) > 0 else "NO 2022 data"
        else:
            tbr_coverage = "TBR column missing"
        print(f"    {sym}: TBR={tbr_coverage}  FR={'✓' if fr_avail else '✗'}")

    # ── 3. Run variants ───────────────────────────────────────────────────────
    print(f"\n[3] Running {len(FILTER_VARIANTS)} variants ...")
    results = []
    for fcfg in FILTER_VARIANTS:
        fname = fcfg["name"]
        res   = run_variant_v26(CHAMPION_CFG, fcfg, inputs, sig_map, log_ann)
        sim   = simulate_combined_v26(res["unit"])
        eq    = sim["eq"]
        oos   = eq[eq.index >= test_ts]
        m     = _m(oos, fname)

        total_vetoes  = sum(
            sum(pa["counts"].get(k, 0) for k in
                ["vetoed_tbr_long", "vetoed_tbr_short", "vetoed_fr_long", "vetoed_oi_long"])
            for pa in res["per_asset"].values()
        )
        total_entries = sum(pa["counts"].get("entries", 0) for pa in res["per_asset"].values())
        veto_pct      = total_vetoes / max(total_entries + total_vetoes, 1)

        yoy = {r["period"]: r["return_pct"] for r in _yoy_table(oos)}

        results.append(dict(
            name=fname,
            final=m["final"], cagr=m["cagr"], calmar=m["calmar"],
            sharpe=m["sharpe"], maxdd=m["maxdd"],
            pct_halted=sim["pct_halted"],
            veto_pct=veto_pct,
            entries=total_entries,
            r2022=yoy.get("2022", np.nan),
            r2023=yoy.get("2023", np.nan),
            r2024=yoy.get("2024", np.nan),
            r2025=yoy.get("2025", np.nan),
            r2026=yoy.get("2026", np.nan),
            tbr_long_min=fcfg.get("tbr_long_min"),
            fr_long_max=fcfg.get("fr_long_max"),
        ))

        print(f"  {fname:<22}: ${m['final']:>10,.0f}  CAGR={m['cagr']:+7.2%}  "
              f"Calmar={m['calmar']:+6.3f}  MaxDD={m['maxdd']:+.2%}  "
              f"veto={veto_pct:.1%}  "
              f"2022={yoy.get('2022', float('nan')):+.1%}  "
              f"2026={yoy.get('2026', float('nan')):+.1%}")

        # Full year breakdown for each variant
        _print_yoy(oos, fname)

    # ── 4. Summary ────────────────────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  v26 EXTENDED OOS RESULTS  (OOS 2022-2026)")
    print(BAR)
    print(f"  {'name':<22}  {'final':>9}  {'CAGR':>7}  {'Calmar':>8}  {'MaxDD':>7}  "
          f"{'2022':>6}  {'2023':>6}  {'2024':>6}  {'2025':>6}  {'2026':>6}  {'veto':>5}")
    print("  " + "-"*110)

    def _r(v): return f"{v:+.0%}" if not np.isnan(v) else "  N/A"

    for r in sorted(results, key=lambda x: -x["calmar"]):
        print(f"  {r['name']:<22}  ${r['final']:>9,.0f}  {r['cagr']:+7.2%}  "
              f"{r['calmar']:+8.3f}  {r['maxdd']:+7.2%}  "
              f"{_r(r['r2022']):>6}  {_r(r['r2023']):>6}  {_r(r['r2024']):>6}  "
              f"{_r(r['r2025']):>6}  {_r(r['r2026']):>6}  {r['veto_pct']:>5.1%}")

    best = max(results, key=lambda x: x["calmar"])
    base = next(r for r in results if r["name"] == "baseline")
    print(f"\n  Best Calmar: {best['name']}  Calmar={best['calmar']:+.3f}")
    delta = best["calmar"] - base["calmar"]
    if delta > 0:
        print(f"  IMPROVEMENT vs baseline: Calmar +{delta:.3f}  "
              f"({best['calmar']:+.3f} vs {base['calmar']:+.3f})")
    else:
        print(f"  No Calmar improvement over baseline ({base['calmar']:+.3f})")

    # Compare with v25 benchmark (2023-2026 only)
    print(f"\n  --- v25 vs v26 comparison ---")
    print(f"  v25 baseline (2023-2026): Calmar=+8.530  CAGR=+205.71%  MaxDD=-24.11%")
    print(f"  v25 tbr0p47  (2023-2026): Calmar=+8.789  CAGR=+206.10%  MaxDD=-23.45%")
    print(f"  v26 baseline (2022-2026): Calmar={base['calmar']:+.3f}  "
          f"CAGR={base['cagr']:+.2%}  MaxDD={base['maxdd']:+.2%}")
    v26_tbr = next((r for r in results if r["name"] == "tbr0p47"), None)
    if v26_tbr:
        print(f"  v26 tbr0p47  (2022-2026): Calmar={v26_tbr['calmar']:+.3f}  "
              f"CAGR={v26_tbr['cagr']:+.2%}  MaxDD={v26_tbr['maxdd']:+.2%}")

    # Save
    out = OUT_DIR_ / "crypto_godmode_v26_extended.json"
    payload = dict(
        meta=dict(
            version="v26_extended",
            oos_start=TEST_START_V26,
            train_start=TRAIN_START_V26,
            train_end="2021-12-31",
            cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window_days=CB_WINDOW_DAYS,
            K_normal=K_NORMAL, rt_bps=REALISTIC_RT_BPS,
            elapsed=time.time() - t0,
        ),
        baseline=dict(
            final=base["final"], cagr=base["cagr"], calmar=base["calmar"],
            maxdd=base["maxdd"], pct_halted=base["pct_halted"],
        ),
        results=results,
        best=best,
        v25_benchmark=dict(
            oos_start="2023-01-01",
            baseline_calmar=8.530,
            tbr0p47_calmar=8.789,
            fr0003_calmar=8.659,
        ),
    )
    with open(out, "w") as f:
        json.dump(payload, f, indent=2, default=float)
    print(f"\n  Saved → {out}")
    print(f"  Elapsed: {time.time()-t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
