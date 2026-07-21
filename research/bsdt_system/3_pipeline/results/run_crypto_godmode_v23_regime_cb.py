"""
Crypto Godmode v23 — Regime-Gated Directional CB
=================================================

v22 revealed: allowing shorts during ALL CB halts destroys 2023-2024.
  2023: -17%  (was +292% in v17)
  2024: -9%   (was +70%  in v17)

Why: the CB was halted in 2023-2024 BULL corrections too.  Freeing shorts
during a bull-market CB halt means shorting into an uptrend → losses.

v23 fix — "regime gate":
  Only unlock shorts if the short leg has RECENTLY been profitable.
  Specifically, if the trailing short P&L sum over the last SHORT_WINDOW
  bars is > 0, the market is in a bear regime and shorts are working.

  When CB is NOT halted:
      both long + short at  K * y(dd_aty)              (unchanged)

  When CB IS halted:
      if rolling_short_pnl(window) > 0  [bear regime]:
          long  → y = 0       (blocked, as always)
          short → K_short_halt (allowed — shorts are earning)
      else                              [bull correction]:
          long  → y = 0       (blocked)
          short → y = 0       (also blocked — shorts are losing here)

This is causal: at bar i we use the sum of short P&L over bars [i-window, i-1].
No lookahead.

Sweep:
  short_window ∈ {360, 720, 1440}  (15 / 30 / 60 days of 1h bars)
  K_short_halt ∈ {0.5, 1.0, 1.5}

Compare against v17 baseline (CAGR=+206%, Calmar=+8.53, 2026=+0%).

Outputs:
  crypto_bsdt_v23_regime_cb.json
  crypto_bsdt_v23_regime_cb_report.md
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
warnings.filterwarnings("ignore")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, r"C:\amttp\research\adaptive-friction")

from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v1 import KAPPA_A, W_TARGET_A1, build_b_aligned, build_w_star, calibrate, run_godmode_sweep
from run_crypto_godmode_v8_multiasset_shell import ASSETS, build_asset_inputs, fetch_futures_ohlcv_symbol
from run_crypto_godmode_v9_multiasset_tune import attach_q_hot
from simulate_master_strategy import (
    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
    FUND_HOURLY, equity_metrics, INIT, HOURS_PER_DAY,
)
from simulate_v63_quadrant import CB_HALT, CB_RESUME, CB_WINDOW_DAYS
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from test_psi_adaptive_y import BASE
import run_crypto_godmode_v12_filter_innovate as v12

# Import the long/short-split unit builder from v22
from run_crypto_godmode_v22_directional_cb import (
    simulate_unit_breakeven_v22,
    run_variant_v22,
)

OUT_DIR_         = Path(OUT_DIR)
BAR              = "=" * 112
REALISTIC_RT_BPS = 6.0
RT_COST          = REALISTIC_RT_BPS / 10_000.0
K_NORMAL         = 6.0

# ── Sweep grid ─────────────────────────────────────────────────────────────
SHORT_WINDOW_GRID = [360, 720, 1440]   # 15, 30, 60 days of 1h bars
K_SHORT_HALT_GRID = [0.5, 1.0, 1.5]   # short leverage multiplier during bear CB


# ─── simulate_combined_v23: regime-gated directional CB ───────────────────

def simulate_combined_v23(
    unit_long:      pd.Series,
    unit_short:     pd.Series,
    K_normal:       float,
    K_short_halt:   float,   # short K when CB halted AND bear regime
    short_window:   int,     # bars to look back when evaluating short regime
    dd_soft:        float,
    dd_stop:        float,
    y_floor:        float,
    cb_halt:        float,
    cb_resume:      float,
    cb_window_days: int,
    use_cb:         bool = True,
) -> dict:
    """Regime-gated directional circuit breaker.

    Bear regime detection: trailing `short_window`-bar sum of unit_short > 0.
      True  → shorts have been gaining recently   → allow shorts during CB halt
      False → shorts have been losing recently    → block shorts during CB halt too

    The trailing sum at bar i uses bars [i-short_window, i-1] (causal, no lookahead).
    """
    n             = len(unit_long)
    window_cb     = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq            = INIT
    peak_alltime  = INIT
    halted        = False

    # Precompute cumulative short P&L for O(1) rolling sums
    us_arr  = unit_short.values.astype(float)
    cum_us  = np.empty(n + 1, dtype=float)
    cum_us[0] = 0.0
    for i in range(n):
        cum_us[i + 1] = cum_us[i] + us_arr[i]

    eq_vals:   list[float] = []
    y_vals:    list[float] = []
    cb_flags:  list[int]   = []
    regime_flags: list[int] = []

    for bar_i in range(n):
        ul = float(unit_long.iloc[bar_i])
        us = float(unit_short.iloc[bar_i])

        # CB rolling-peak deque
        while mono_dq and mono_dq[0][0] <= bar_i - window_cb:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak,    1e-12))

        if use_cb:
            if not halted and cb_dd >= cb_halt:
                halted = True
            elif halted and cb_dd <= cb_resume:
                halted = False
        else:
            halted = False

        # Adaptive Y for normal regime
        if dd_aty <= dd_soft:
            y_normal = 1.0
        elif dd_aty >= dd_stop:
            y_normal = y_floor
        else:
            y_normal = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        # Regime gate: lagged rolling sum of short P&L
        # Use bars [bar_i - short_window, bar_i - 1] → cum_us[bar_i] - cum_us[max(0, bar_i-short_window)]
        lag_start = max(0, bar_i - short_window)
        rolling_short_pnl = cum_us[bar_i] - cum_us[lag_start]
        bear_regime = rolling_short_pnl > 0.0

        if halted:
            if bear_regime:
                # Bear market CB: shorts are earning → allow them
                r_long  = 0.0
                r_short = K_short_halt * us
                y       = 0.0
            else:
                # Bull correction CB: shorts losing → block everything (v17 behaviour)
                r_long  = 0.0
                r_short = 0.0
                y       = 0.0
        else:
            r_long  = K_normal * y_normal * ul
            r_short = K_normal * y_normal * us
            y       = y_normal

        r  = r_long + r_short
        r  = max(r, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq)
        y_vals.append(y)
        cb_flags.append(int(halted))
        regime_flags.append(int(bear_regime and halted))

    eqs  = pd.Series(eq_vals,  index=unit_long.index)
    rets = eqs.pct_change().fillna(eqs.iloc[0] / INIT - 1.0)
    dd_s = (eqs - eqs.cummax()) / eqs.cummax()
    years = max((eqs.index[-1] - eqs.index[0]).days / 365.25, 1e-9)

    return dict(
        eq            = eqs,
        final         = float(eqs.iloc[-1]),
        cagr          = float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe        = float(np.sqrt(24 * 365.25) * rets.mean() / rets.std()) if rets.std() > 0 else 0.0,
        maxdd         = float(dd_s.min()),
        pct_halted    = float(np.mean(cb_flags)),
        pct_bear_cb   = float(np.mean(regime_flags)),
        n_trips       = int(sum(cb_flags[i] > cb_flags[i - 1] for i in range(1, len(cb_flags)))),
        avg_y         = float(np.mean(y_vals)),
        cb_flags      = cb_flags,
        regime_flags  = regime_flags,
    )


# ─── period helpers ───────────────────────────────────────────────────────────

def _period_metrics(eq: pd.Series, cb_flags: list[int], period: str, label: str) -> list[dict]:
    rows   = []
    cb_s   = pd.Series(cb_flags, index=eq.index)
    grp_eq = eq.groupby(eq.index.to_period(period))
    grp_cb = cb_s.groupby(cb_s.index.to_period(period))
    for p, s in grp_eq:
        if s.empty:
            continue
        cb_p  = grp_cb.get_group(p) if p in grp_cb.groups else pd.Series([], dtype=float)
        start = float(s.iloc[0])
        end   = float(s.iloc[-1])
        ret   = end / start - 1.0 if start else float("nan")
        dd    = float((s / s.cummax() - 1.0).min())
        r_ch  = s.pct_change().replace([float("inf"), float("-inf")], float("nan")).dropna()
        sh    = float(r_ch.mean() / (r_ch.std() + 1e-12) * np.sqrt(365 * 24)) if len(r_ch) > 3 else 0.0
        ph    = float(cb_p.mean()) if len(cb_p) > 0 else 0.0
        rows.append({
            "label": label, "period": str(p),
            "start_eq": start, "end_eq": end, "profit": end - start,
            "return_pct": 100.0 * ret, "maxdd_pct": 100.0 * dd,
            "sharpe": sh, "pct_halted": 100.0 * ph,
        })
    return rows


def _fmt_money(x)  -> str: return f"${float(x):,.2f}"
def _fmt_pct(x)    -> str: return f"{float(x):+,.2f}%"
def _fmt_float(x)  -> str: return f"{float(x):+.3f}"


def _md_table(df: pd.DataFrame, cols: list[str]) -> str:
    pct_cols  = {"return_pct", "maxdd_pct", "cagr_pct", "pct_halted", "pct_bear_cb",
                 "ret_2026_pct", "halted_2026_pct", "bear_cb_pct"}
    money_cols = {"start_eq", "end_eq", "profit", "final"}
    float_cols = {"sharpe", "calmar", "k_short_halt_val", "short_window_days"}
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, row in df.iterrows():
        vals = []
        for c in cols:
            v = row[c]
            if c in money_cols:
                vals.append(_fmt_money(v))
            elif c in pct_cols:
                vals.append(_fmt_pct(v))
            elif c in float_cols:
                vals.append(_fmt_float(v))
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(BAR)
    print("  CRYPTO GODMODE v23 — REGIME-GATED DIRECTIONAL CB")
    print(f"  Fix: only allow shorts during CB halt when recent short P&L > 0 (bear regime)")
    print(BAR)

    # ── Step 1: build unit series (long + short split) ────────────────────
    print("\n[1] Building be50_btc_sol unit series with long/short split ...")
    df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    ohlc_map   = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch         = get_channel_series()

    w_star    = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag_cal = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v23")
    log_ann   = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_f, theta,
                                   kappa=KAPPA_A, anneal=True, label="v23_anneal")

    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs     = attach_q_hot(inputs_noq, inputs_q)
    sig_map    = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                  for asset, _, _, idx in ASSETS}
    cfg        = next(c for c in v12.VARIANTS if c["name"] == "be50_btc_sol")

    unit_res   = run_variant_v22(cfg, inputs, sig_map, log_ann)
    unit       = unit_res["unit"]
    unit_long  = unit_res["unit_long"]
    unit_short = unit_res["unit_short"]
    test_ts    = pd.Timestamp(TEST_START)

    ul_test = unit_long[unit_long.index   >= test_ts]
    us_test = unit_short[unit_short.index >= test_ts]
    print(f"  unit: {unit.index[0].date()} -> {unit.index[-1].date()}  n={len(unit):,}")
    print(f"  long bars (OOS):  {int((ul_test!=0).sum()):,}  ({(ul_test!=0).mean():.1%})")
    print(f"  short bars (OOS): {int((us_test!=0).sum()):,}  ({(us_test!=0).mean():.1%})")

    # ── Step 2: v17 baseline ──────────────────────────────────────────────
    print("\n[2] Baseline: v17 original CB (both legs halted) ...")
    from simulate_master_strategy import simulate_combined as sim_orig
    zero        = pd.Series(np.zeros(len(unit)), index=unit.index)
    res_base    = sim_orig(
        unit, zero,
        K_normal=K_NORMAL, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window_days=CB_WINDOW_DAYS, use_cb=True,
    )
    eq_base     = res_base["eq"][res_base["eq"].index >= test_ts]
    m_base      = equity_metrics(eq_base, "baseline_v17")
    calmar_base = float(m_base["cagr"]) / max(abs(float(m_base["maxdd"])), 1e-9)
    eq_2026b    = eq_base[eq_base.index >= "2026-01-01"]
    ret_2026b   = float(eq_2026b.iloc[-1]) / float(eq_2026b.iloc[0]) - 1.0 if len(eq_2026b) > 1 else 0.0
    print(f"  CAGR={m_base['cagr']:+.1%}  Sharpe={m_base['sharpe']:+.3f}  "
          f"MaxDD={m_base['maxdd']:+.1%}  Calmar={calmar_base:+.3f}  2026={ret_2026b:+.1%}")

    # ── Step 3: sweep ─────────────────────────────────────────────────────
    print(f"\n[3] Sweeping short_window × K_short_halt ...")
    print(f"  CB_HALT={CB_HALT:.0%}  CB_RESUME={CB_RESUME:.0%}  CB_WINDOW={CB_WINDOW_DAYS}d  K_normal={K_NORMAL}")
    sweep_rows = []

    for sw in SHORT_WINDOW_GRID:
        for ksh in K_SHORT_HALT_GRID:
            label = f"sw{sw:04d}_ksh{int(ksh*10):03d}"
            res   = simulate_combined_v23(
                unit_long, unit_short,
                K_normal=K_NORMAL, K_short_halt=ksh, short_window=sw,
                dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                cb_halt=CB_HALT, cb_resume=CB_RESUME,
                cb_window_days=CB_WINDOW_DAYS, use_cb=True,
            )
            eq_t    = res["eq"][res["eq"].index >= test_ts]
            cb_t    = [res["cb_flags"][i] for i, ts in enumerate(res["eq"].index) if ts >= test_ts]

            eq_2026  = eq_t[eq_t.index >= "2026-01-01"]
            ret_2026 = float(eq_2026.iloc[-1]) / float(eq_2026.iloc[0]) - 1.0 if len(eq_2026) > 1 else 0.0
            cb_2026  = [res["cb_flags"][i] for i, ts in enumerate(res["eq"].index)
                        if ts >= pd.Timestamp("2026-01-01")]
            halted_2026_pct = float(np.mean(cb_2026)) if cb_2026 else 0.0
            bear_2026 = [res["regime_flags"][i] for i, ts in enumerate(res["eq"].index)
                         if ts >= pd.Timestamp("2026-01-01")]
            bear_cb_2026 = float(np.mean(bear_2026)) if bear_2026 else 0.0

            m      = equity_metrics(eq_t, label)
            calmar = float(m["cagr"]) / max(abs(float(m["maxdd"])), 1e-9)
            sweep_rows.append({
                "label":              label,
                "short_window":       sw,
                "short_window_days":  sw / 24.0,
                "k_short_halt":       ksh,
                "k_short_halt_val":   ksh,
                "final":              float(m["final"]),
                "cagr_pct":           float(m["cagr"]) * 100,
                "sharpe":             float(m["sharpe"]),
                "maxdd_pct":          float(m["maxdd"]) * 100,
                "calmar":             calmar,
                "pct_halted":         res["pct_halted"] * 100,
                "pct_bear_cb":        res["pct_bear_cb"] * 100,
                "ret_2026_pct":       ret_2026 * 100,
                "halted_2026_pct":    halted_2026_pct * 100,
                "bear_cb_pct":        bear_cb_2026 * 100,
            })
            print(f"  sw={sw}h  ksh={ksh:.1f}  "
                  f"CAGR={m['cagr']:+.1%}  Sharpe={m['sharpe']:+.3f}  "
                  f"MaxDD={m['maxdd']:+.1%}  Calmar={calmar:+.3f}  "
                  f"halt={res['pct_halted']:.0%}  bear_cb={res['pct_bear_cb']:.0%}  "
                  f"2026={ret_2026:+.1%}")

    sweep_df = pd.DataFrame(sweep_rows).sort_values("calmar", ascending=False).reset_index(drop=True)

    print(f"\n  {'='*90}")
    print(f"  Baseline v17:  CAGR={m_base['cagr']:+.1%}  Calmar={calmar_base:+.3f}  2026={ret_2026b:+.1%}")
    print(f"  Best v23:      CAGR={sweep_df.iloc[0]['cagr_pct']:+.1f}%  "
          f"Calmar={sweep_df.iloc[0]['calmar']:+.3f}  "
          f"2026={sweep_df.iloc[0]['ret_2026_pct']:+.1f}%  [{sweep_df.iloc[0]['label']}]")

    # ── Step 4: year-by-year for top 3 + baseline ─────────────────────────
    print("\n[4] Year-on-year tables ...")
    top3 = sweep_df.head(3)
    period_results: dict = {}

    print(f"\n  Baseline v17:")
    yr_base = _period_metrics(eq_base, [0] * len(eq_base), "Y", "v17_baseline")
    for row in yr_base:
        print(f"    {row['period']}  return={row['return_pct']:+.1f}%  maxdd={row['maxdd_pct']:+.1f}%")

    for _, w in top3.iterrows():
        sw  = int(w["short_window"])
        ksh = float(w["k_short_halt"])
        lbl = w["label"]
        print(f"\n  {lbl}  (window={sw}h / {sw/24:.0f}d, K_short={ksh:.1f}):")
        r_win = simulate_combined_v23(
            unit_long, unit_short,
            K_normal=K_NORMAL, K_short_halt=ksh, short_window=sw,
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
            cb_halt=CB_HALT, cb_resume=CB_RESUME,
            cb_window_days=CB_WINDOW_DAYS, use_cb=True,
        )
        eq_win  = r_win["eq"][r_win["eq"].index >= test_ts]
        t_mask  = r_win["eq"].index >= test_ts
        cb_w_t  = [f for f, m2 in zip(r_win["cb_flags"],     t_mask) if m2]
        rg_w_t  = [f for f, m2 in zip(r_win["regime_flags"], t_mask) if m2]

        yr  = _period_metrics(eq_win, cb_w_t, "Y", lbl)
        qtr = _period_metrics(eq_win, cb_w_t, "Q", lbl)
        period_results[lbl] = {"yearly": yr, "quarterly": qtr, "regime_flags": rg_w_t}
        for row in yr:
            print(f"    {row['period']}  return={row['return_pct']:+.1f}%  "
                  f"halted={row['pct_halted']:.0f}%  maxdd={row['maxdd_pct']:+.1f}%")

    winner = sweep_df.iloc[0]

    # ── Step 5: save outputs ──────────────────────────────────────────────
    print("\n[5] Saving outputs ...")
    payload = {
        "meta": {
            "version":          "godmode_v23_regime_cb",
            "strategy":         "be50_btc_sol",
            "K_normal":         K_NORMAL,
            "rt_bps":           REALISTIC_RT_BPS,
            "cb_halt":          CB_HALT,
            "cb_resume":        CB_RESUME,
            "cb_window_days":   CB_WINDOW_DAYS,
            "short_window_grid": SHORT_WINDOW_GRID,
            "k_short_halt_grid": K_SHORT_HALT_GRID,
            "theta":            diag_cal["theta"],
            "elapsed":          time.time() - t0,
            "fix":              "regime_gated_directional_cb",
        },
        "baseline": {
            "label":     "v17_original_cb",
            "cagr_pct":  float(m_base["cagr"]) * 100,
            "sharpe":    float(m_base["sharpe"]),
            "maxdd_pct": float(m_base["maxdd"]) * 100,
            "calmar":    calmar_base,
            "ret_2026":  ret_2026b * 100,
        },
        "sweep":   sweep_df.drop(columns=["k_short_halt_val", "short_window_days"], errors="ignore")
                           .to_dict(orient="records"),
        "winner": {
            "label":          winner["label"],
            "short_window":   int(winner["short_window"]),
            "k_short_halt":   float(winner["k_short_halt"]),
            "cagr_pct":       float(winner["cagr_pct"]),
            "sharpe":         float(winner["sharpe"]),
            "maxdd_pct":      float(winner["maxdd_pct"]),
            "calmar":         float(winner["calmar"]),
            "ret_2026_pct":   float(winner["ret_2026_pct"]),
        },
        "period_results": {k: {"yearly": v["yearly"], "quarterly": v["quarterly"]}
                           for k, v in period_results.items()},
    }

    json_path = OUT_DIR_ / "crypto_bsdt_v23_regime_cb.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)

    md_lines = [
        "# Crypto Godmode v23 — Regime-Gated Directional CB",
        "",
        "## Problem (from v22)",
        "",
        "v22 allowed shorts during ALL CB halts → shorts run during 2023-2024 bull",
        "corrections → 2023: -17%, 2024: -9% (vs baseline +292%, +70%).",
        "",
        "## Fix",
        "",
        "Regime gate: only unlock the short leg when its own trailing P&L",
        f"(over `short_window` bars) is **positive** (bear regime).",
        "",
        "| Condition | Long | Short |",
        "|-----------|------|-------|",
        "| Not halted | K × y | K × y |",
        "| Halted + bear regime (short rolling PnL > 0) | blocked | K_short_halt |",
        "| Halted + bull pullback (short rolling PnL ≤ 0) | blocked | blocked |",
        "",
        f"**K_normal:** {K_NORMAL}  **CB_HALT:** {CB_HALT:.0%}  **CB_RESUME:** {CB_RESUME:.0%}  "
        f"**CB_WINDOW:** {CB_WINDOW_DAYS}d  **Strategy:** be50_btc_sol  **RT:** {REALISTIC_RT_BPS} bps",
        "",
        "## Baseline (v17 original CB)",
        "",
        f"CAGR = {m_base['cagr']:+.1%}  |  Sharpe = {m_base['sharpe']:+.3f}  |  "
        f"MaxDD = {m_base['maxdd']:+.1%}  |  Calmar = {calmar_base:+.3f}  |  "
        f"2026 = {ret_2026b:+.1%}",
        "",
        "## Sweep Results",
        "",
        _md_table(sweep_df, [
            "label", "short_window", "k_short_halt",
            "cagr_pct", "sharpe", "maxdd_pct", "calmar",
            "pct_halted", "pct_bear_cb",
            "ret_2026_pct", "halted_2026_pct",
        ]),
        "",
        f"## Winner: `{winner['label']}`",
        f"short_window = {int(winner['short_window'])} bars ({int(winner['short_window'])/24:.0f} days)  |  "
        f"K_short_halt = {float(winner['k_short_halt']):.1f}  |  "
        f"CAGR = {float(winner['cagr_pct']):+.1f}%  |  "
        f"Calmar = {float(winner['calmar']):+.3f}  |  "
        f"2026 = {float(winner['ret_2026_pct']):+.1f}%",
        "",
    ]

    for lbl, pdata in period_results.items():
        md_lines += [
            f"### Period: `{lbl}`",
            "",
            "**Year-on-Year**",
            "",
            _md_table(pd.DataFrame(pdata["yearly"]),
                      ["period", "start_eq", "end_eq", "profit",
                       "return_pct", "maxdd_pct", "sharpe", "pct_halted"]),
            "",
            "**Quarterly**",
            "",
            _md_table(pd.DataFrame(pdata["quarterly"]),
                      ["period", "start_eq", "end_eq", "profit",
                       "return_pct", "maxdd_pct", "sharpe", "pct_halted"]),
            "",
        ]

    md_path = OUT_DIR_ / "crypto_bsdt_v23_regime_cb_report.md"
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines))

    print(f"  saved: {json_path}")
    print(f"  saved: {md_path}")
    el = time.time() - t0
    print(f"\n  Elapsed: {el:.1f}s  ({el/60:.1f} min)")
    print(BAR)


if __name__ == "__main__":
    main()
