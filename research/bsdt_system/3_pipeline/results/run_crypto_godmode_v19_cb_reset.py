"""
Crypto Godmode v19 — Circuit Breaker Deque-Reset Fix
======================================================

v18 finding: max_halt_hours alone does NOT fix 2026 flatness.
Root cause:  When force-resume triggers, the CB deque still holds the 180-day
             rolling peak from the 2025Q4 bull run.  On the very next bar,
             cb_dd >= 8% again → strategy immediately re-halts.
             Result: pattern is "720 bars halted, 1 bar trading" → 100% halt.

v19 fix:     On forced-resume, CLEAR the CB deque.
             The next bar's rolling peak = current equity → cb_dd ≈ 0%
             → no immediate re-halt.  The CB still fires if the market
             drops ≥ CB_HALT % from the NEW reference level.

Sweep grid:
  CB_HALT    : 0.08, 0.12, 0.15        (wider gate = less aggressive halt)
  max_halt_h : None, 720, 1440, 2160   (off, 30d, 60d, 90d force-resume)
  CB_RESUME  : 0.01 (fixed at champion value)

Total = 3 × 4 = 12 combos

Outputs:
  crypto_bsdt_v19_cb_reset.json
  crypto_bsdt_v19_cb_reset_report.md
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
    DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
    equity_metrics, INIT, HOURS_PER_DAY,
)
from simulate_v63_quadrant import CB_RESUME, CB_WINDOW_DAYS
from test_daily_geometry_stop_tp_ohlc import get_channel_series
import run_crypto_godmode_v12_filter_innovate as v12

OUT_DIR_ = Path(OUT_DIR)
BAR = "=" * 112
REALISTIC_RT_BPS = 6.0
K_NORMAL = 6.0

# ─── sweep grid ───────────────────────────────────────────────────────────────
CB_HALT_GRID    = [0.08, 0.12, 0.15]          # wider halt gate options
MAX_HALT_H_GRID = [None, 720, 1440, 2160]     # None=off, 30d, 60d, 90d
CB_RESUME_FIXED = CB_RESUME                   # keep champion value (0.01)


# ─── simulate_combined_v19: deque-reset on forced resume ─────────────────────

def simulate_combined_v19(
    unit_normal: pd.Series,
    unit_crash:  pd.Series,
    K_normal:    float,
    K_crash:     float,
    dd_soft:     float,
    dd_stop:     float,
    y_floor:     float,
    cb_halt:     float,
    cb_resume:   float,
    cb_window_days: int,
    max_halt_hours: int | None = None,
    use_cb: bool = True,
) -> dict:
    """simulate_combined extended with:
    1. max_halt_hours  — force-resume after N consecutive halted bars
    2. deque clear     — on forced-resume, reset the rolling CB window so the
                         new peak reference = current equity (prevents immediate re-halt)
    """
    window_bars  = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq           = INIT
    peak_alltime = INIT
    halted       = False
    halt_since_bar: int = 0
    eq_vals      = []
    y_vals       = []
    cb_flags     = []
    halt_hours_vals = []

    for bar_i in range(len(unit_normal)):
        ur_n = float(unit_normal.iloc[bar_i])
        ur_c = float(unit_crash.iloc[bar_i])

        # Sliding-window monotonic deque for CB rolling peak
        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
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
                halt_since_bar = bar_i
            elif halted:
                hours_halted   = bar_i - halt_since_bar
                normal_resume  = cb_dd <= cb_resume
                force_resume   = (max_halt_hours is not None
                                  and hours_halted >= max_halt_hours)
                if normal_resume:
                    halted = False
                elif force_resume:
                    halted = False
                    # KEY FIX: reset the CB window so peak reference = current
                    # equity → prevents immediate re-halt on the next bar
                    mono_dq.clear()
        else:
            halted = False

        # Adaptive Y
        if halted:
            y = 0.0
        elif dd_aty <= dd_soft:
            y = 1.0
        elif dd_aty >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        r  = K_normal * y * ur_n + K_crash * ur_c
        r  = max(r, -0.95)
        eq *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)
        eq_vals.append(eq)
        y_vals.append(y)
        cb_flags.append(int(halted))
        halt_hours_vals.append(bar_i - halt_since_bar if halted else 0)

    eqs  = pd.Series(eq_vals, index=unit_normal.index)
    rets = eqs.pct_change().fillna(eqs.iloc[0] / INIT - 1.0)
    dd_s = (eqs - eqs.cummax()) / eqs.cummax()
    years = max((eqs.index[-1] - eqs.index[0]).days / 365.25, 1e-9)
    return dict(
        eq         = eqs,
        final      = float(eqs.iloc[-1]),
        cagr       = float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe     = float(np.sqrt(24 * 365.25) * rets.mean() / rets.std()) if rets.std() > 0 else 0.0,
        maxdd      = float(dd_s.min()),
        pct_halted = float(np.mean(cb_flags)),
        n_trips    = int(sum(cb_flags[i] > cb_flags[i - 1] for i in range(1, len(cb_flags)))),
        avg_y      = float(np.mean(y_vals)),
        cb_flags   = cb_flags,
    )


# ─── period helpers ───────────────────────────────────────────────────────────

def _period_metrics(eq: pd.Series, cb_flags: list[int], period: str, label: str) -> list[dict]:
    rows = []
    cb_s     = pd.Series(cb_flags, index=eq.index)
    grp_eq   = eq.groupby(eq.index.to_period(period))
    grp_cb   = cb_s.groupby(cb_s.index.to_period(period))
    for p, s in grp_eq:
        if s.empty:
            continue
        cb_period  = grp_cb.get_group(p) if p in grp_cb.groups else pd.Series([], dtype=float)
        start_eq   = float(s.iloc[0])
        end_eq     = float(s.iloc[-1])
        ret        = end_eq / start_eq - 1.0 if start_eq else float("nan")
        dd         = float((s / s.cummax() - 1.0).min())
        r          = s.pct_change().replace([float("inf"), float("-inf")], float("nan")).dropna()
        sharpe     = float(r.mean() / (r.std() + 1e-12) * np.sqrt(365 * 24)) if len(r) > 3 else 0.0
        pct_halt   = float(cb_period.mean()) if len(cb_period) > 0 else 0.0
        rows.append({
            "label":      label,
            "period":     str(p),
            "start":      str(s.index[0]),
            "end":        str(s.index[-1]),
            "start_eq":   start_eq,
            "end_eq":     end_eq,
            "profit":     end_eq - start_eq,
            "return_pct": 100.0 * ret,
            "maxdd_pct":  100.0 * dd,
            "sharpe":     sharpe,
            "pct_halted": 100.0 * pct_halt,
            "bars":       int(len(s)),
        })
    return rows


def _fmt_money(x: float)  -> str: return f"${x:,.2f}"
def _fmt_pct(x: float)    -> str: return f"{x:+,.2f}%"
def _fmt_float(x: float)  -> str: return f"{x:+.3f}"


def _markdown_table(df: pd.DataFrame, cols: list[str]) -> str:
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, row in df.iterrows():
        vals = []
        for c in cols:
            v = row[c]
            if c in {"start_eq", "end_eq", "profit"}:
                vals.append(_fmt_money(float(v)))
            elif c in {"return_pct", "maxdd_pct", "cagr_pct", "pct_halted", "ret_2026_pct", "halted_2026_pct", "cb_halt_pct"}:
                vals.append(_fmt_pct(float(v)))
            elif c in {"sharpe", "calmar"}:
                vals.append(_fmt_float(float(v)))
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(BAR)
    print("  CRYPTO GODMODE v19 — CIRCUIT BREAKER DEQUE-RESET FIX")
    print(f"  v18 finding: 2026_halt=100% on all combos (CB re-fires immediately after force-resume)")
    print(f"  v19 fix:     Clear CB deque on forced-resume → peak resets to current equity")
    print(BAR)

    # ── Step 1: rebuild unit series ──────────────────────────────────────────
    print("\n[1] Rebuilding be50_btc_sol unit series ...")
    df, _ = build_1h_df(start="2021-01-01", end="2026-05-15")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    ohlc_map   = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch         = get_channel_series()

    w_star    = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag_cal = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v19")
    log_ann   = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_f, theta,
                                   kappa=KAPPA_A, anneal=True, label="v19_anneal")

    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs     = attach_q_hot(inputs_noq, inputs_q)
    sig_map    = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                  for asset, _, _, idx in ASSETS}
    cfg        = next(c for c in v12.VARIANTS if c["name"] == "be50_btc_sol")
    v12.RT_COST = REALISTIC_RT_BPS / 10_000.0
    unit_res   = v12.run_variant(cfg, inputs, sig_map, log_ann)
    unit       = unit_res["unit"]
    zero       = pd.Series(np.zeros(len(unit)), index=unit.index)
    test_ts    = pd.Timestamp(TEST_START)
    print(f"  unit: {unit.index[0].date()} → {unit.index[-1].date()}  n={len(unit):,}")

    # ── Step 2: sweep CB_HALT × max_halt_hours (with deque reset) ────────────
    print(f"\n[2] Sweeping CB_HALT × max_halt_hours  (CB_RESUME={CB_RESUME_FIXED:.0%} fixed, K={K_NORMAL})")
    print(f"  ** deque-reset on forced-resume is ACTIVE **")
    sweep_rows = []

    for cb_halt in CB_HALT_GRID:
        for mh in MAX_HALT_H_GRID:
            label = f"halt{int(cb_halt*100):02d}%_maxhalt{'off' if mh is None else f'{mh//24}d'}"
            res   = simulate_combined_v19(
                unit, zero,
                K_normal=K_NORMAL, K_crash=0.0,
                dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                cb_halt=cb_halt, cb_resume=CB_RESUME_FIXED,
                cb_window_days=CB_WINDOW_DAYS,
                max_halt_hours=mh, use_cb=True,
            )
            eq_test = res["eq"][res["eq"].index >= test_ts]
            cb_test_flags = [res["cb_flags"][i] for i, ts in enumerate(res["eq"].index) if ts >= test_ts]

            # 2026 sub-period stats
            eq_2026  = eq_test[eq_test.index >= "2026-01-01"]
            ret_2026 = (float(eq_2026.iloc[-1]) / float(eq_2026.iloc[0]) - 1.0) if len(eq_2026) > 1 else float("nan")
            cb_2026  = [res["cb_flags"][i] for i, ts in enumerate(res["eq"].index) if ts >= pd.Timestamp("2026-01-01")]
            halted_2026_pct = float(np.mean(cb_2026)) if cb_2026 else 0.0

            m      = equity_metrics(eq_test, label)
            calmar = float(m["cagr"]) / max(abs(float(m["maxdd"])), 1e-9)
            sweep_rows.append({
                "label":            label,
                "cb_halt_pct":      cb_halt * 100,
                "max_halt_days":    None if mh is None else mh // 24,
                "final":            float(m["final"]),
                "cagr_pct":         float(m["cagr"]) * 100,
                "sharpe":           float(m["sharpe"]),
                "maxdd_pct":        float(m["maxdd"]) * 100,
                "calmar":           calmar,
                "pct_halted":       res["pct_halted"] * 100,
                "n_trips":          res["n_trips"],
                "ret_2026_pct":     (ret_2026 * 100) if not np.isnan(ret_2026) else 0.0,
                "halted_2026_pct":  halted_2026_pct * 100,
            })
            print(f"  {label:<35}  CAGR={m['cagr']:+.1%}  Sharpe={m['sharpe']:+.3f}  "
                  f"MaxDD={m['maxdd']:+.1%}  Calmar={calmar:+.3f}  "
                  f"halt={res['pct_halted']:.0%}  2026_ret={ret_2026:+.1%}  2026_halt={halted_2026_pct:.0%}")

    sweep_df = pd.DataFrame(sweep_rows).sort_values("calmar", ascending=False).reset_index(drop=True)

    # ── Step 3: period tables for winners ────────────────────────────────────
    # Show top-3 for comparison
    top3 = sweep_df.head(3)
    period_results = {}
    for _, w in top3.iterrows():
        w_halt  = float(w["cb_halt_pct"]) / 100.0
        w_mh_d  = w["max_halt_days"]
        w_mh_h  = None if (pd.isna(w_mh_d) or w_mh_d is None) else int(w_mh_d) * 24
        print(f"\n[3] Period tables for: {w['label']}")
        r_win = simulate_combined_v19(
            unit, zero,
            K_normal=K_NORMAL, K_crash=0.0,
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
            cb_halt=w_halt, cb_resume=CB_RESUME_FIXED,
            cb_window_days=CB_WINDOW_DAYS,
            max_halt_hours=w_mh_h, use_cb=True,
        )
        eq_win    = r_win["eq"][r_win["eq"].index >= test_ts]
        test_mask = r_win["eq"].index >= test_ts
        cb_w_test = [f for f, m2 in zip(r_win["cb_flags"], test_mask) if m2]

        yr  = _period_metrics(eq_win, cb_w_test, "Y", w["label"])
        qtr = _period_metrics(eq_win, cb_w_test, "Q", w["label"])
        period_results[w["label"]] = {"yearly": yr, "quarterly": qtr}

        print("  Year-on-Year:")
        for row in yr:
            print(f"    {row['period']}  return={row['return_pct']:+.1f}%  "
                  f"halted={row['pct_halted']:.0f}%  maxdd={row['maxdd_pct']:+.1f}%")

    winner = sweep_df.iloc[0]

    # ── Step 4: save outputs ──────────────────────────────────────────────────
    print("\n[4] Saving outputs ...")
    payload = {
        "meta": {
            "version":          "godmode_v19_cb_reset",
            "strategy":         "be50_btc_sol",
            "K_normal":         K_NORMAL,
            "rt_bps":           REALISTIC_RT_BPS,
            "cb_resume_fixed":  CB_RESUME_FIXED,
            "cb_window_days":   CB_WINDOW_DAYS,
            "sweep_cb_halt":    CB_HALT_GRID,
            "sweep_max_halt_h": MAX_HALT_H_GRID,
            "fix":              "deque_reset_on_force_resume",
            "theta":            diag_cal["theta"],
            "elapsed":          time.time() - t0,
        },
        "sweep":          sweep_df.to_dict(orient="records"),
        "winner": {
            "label":         winner["label"],
            "cb_halt_pct":   float(winner["cb_halt_pct"]),
            "max_halt_days": None if pd.isna(winner["max_halt_days"]) else int(winner["max_halt_days"]),
            "cagr_pct":      float(winner["cagr_pct"]),
            "sharpe":        float(winner["sharpe"]),
            "maxdd_pct":     float(winner["maxdd_pct"]),
            "calmar":        float(winner["calmar"]),
        },
        "period_results": period_results,
    }

    json_path = OUT_DIR_ / "crypto_bsdt_v19_cb_reset.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)

    # Markdown report
    w_halt_str = f"{float(winner['cb_halt_pct']):.0f}%"
    w_mh_str   = "off" if pd.isna(winner["max_halt_days"]) else f"{int(winner['max_halt_days'])}d"
    md_lines   = [
        "# Crypto Godmode v19 — Circuit Breaker Deque-Reset Fix",
        "",
        "## Problem Recap",
        "",
        "- **v17**: all of 2026 flat ($0 profit). Root cause: CB locked out after 2025Q4 +411% bull run.",
        "- **v18**: max_halt_hours sweep → all 16 combos still 2026_halt=100%.",
        "  - Why: on force-resume the old 180-day rolling peak is still in the deque → cb_dd ≥ 8% → immediate re-halt.",
        "",
        "## v19 Fix",
        "",
        "> On forced-resume, **clear the CB deque**. The next bar's rolling peak = current equity.",
        "> cb_dd ≈ 0% → no immediate re-halt. CB only fires again on a NEW ≥ CB_HALT drawdown.",
        "",
        f"**K:** {K_NORMAL}  **CB_RESUME:** {CB_RESUME_FIXED:.0%}  **CB_WINDOW:** {CB_WINDOW_DAYS}d  "
        f"**Strategy:** be50_btc_sol  **Costs:** {REALISTIC_RT_BPS} bps RT",
        "",
        "## Sweep Results (ranked by Calmar)",
        "",
        _markdown_table(sweep_df, [
            "label", "cb_halt_pct", "max_halt_days",
            "cagr_pct", "sharpe", "maxdd_pct", "calmar",
            "pct_halted", "ret_2026_pct", "halted_2026_pct",
        ]),
        "",
        f"## Winner: `{winner['label']}`",
        "",
        f"CB_HALT = {w_halt_str}  |  max_halt = {w_mh_str}  |  "
        f"CAGR = {winner['cagr_pct']:+.1f}%  |  Sharpe = {winner['sharpe']:+.3f}  |  "
        f"MaxDD = {winner['maxdd_pct']:+.1f}%  |  Calmar = {winner['calmar']:+.3f}",
        "",
    ]

    for lbl, pdata in period_results.items():
        md_lines += [
            f"### Period: `{lbl}`",
            "",
            "**Year-on-Year**",
            "",
            _markdown_table(pd.DataFrame(pdata["yearly"]),
                            ["period", "start_eq", "end_eq", "profit", "return_pct", "maxdd_pct", "sharpe", "pct_halted"]),
            "",
            "**Quarterly**",
            "",
            _markdown_table(pd.DataFrame(pdata["quarterly"]),
                            ["period", "start_eq", "end_eq", "profit", "return_pct", "maxdd_pct", "sharpe", "pct_halted"]),
            "",
        ]

    md_path = OUT_DIR_ / "crypto_bsdt_v19_cb_reset_report.md"
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines))

    print(f"  saved: {json_path}")
    print(f"  saved: {md_path}")
    el = time.time() - t0
    print(f"\n  Elapsed: {el:.1f}s  ({el/60:.1f} min)")
    print(BAR)


if __name__ == "__main__":
    main()
