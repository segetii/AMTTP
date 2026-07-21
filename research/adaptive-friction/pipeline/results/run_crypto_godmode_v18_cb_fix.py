"""
Crypto Godmode v18 — Circuit Breaker Resume Fix
================================================

Diagnosis from v17:  2026 is completely flat (zero profit Jan–Apr 2026)
Root cause:          CB_RESUME=0.01 (1%) — after the massive 2025Q4 bull run
                     (+411%), any ≥8% pullback triggers a halt.  The equity
                     must recover to within 1% of the 180-day rolling peak to
                     resume.  In a sideways / mild-bear 2026 it never does.

Fix approach — two independent levers swept together:
  1. CB_RESUME loosening : allow resume at 3%, 5%, or 7% below rolling peak
  2. max_halt_hours      : force-resume after being halted N hours (720=30d,
                           1440=60d, 2160=90d) regardless of CB state

Sweep grid (4 × 4 = 16 combos):
  CB_RESUME  : 0.01, 0.03, 0.05, 0.07
  max_halt_h : None, 720, 1440, 2160

Reports:
  - Per-combo: overall CAGR / Sharpe / MaxDD / Calmar / pct_halted
  - Top-5 configs, ranked by Calmar
  - Full year-on-year and quarterly tables for the winner
  - 2026 detailed breakdown (bars, months active vs halted)

Outputs:
  crypto_bsdt_v18_cb_fix.json
  crypto_bsdt_v18_cb_fix_report.md
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
from simulate_v63_quadrant import CB_HALT, CB_RESUME, CB_WINDOW_DAYS
from test_daily_geometry_stop_tp_ohlc import get_channel_series
import run_crypto_godmode_v12_filter_innovate as v12

OUT_DIR_ = Path(OUT_DIR)
BAR = "=" * 112
REALISTIC_RT_BPS = 6.0
K_NORMAL = 6.0  # champion K from v17

# ─── sweep grid ───────────────────────────────────────────────────────────────
CB_RESUME_GRID   = [0.01, 0.03, 0.05, 0.07]
MAX_HALT_H_GRID  = [None, 720, 1440, 2160]   # None=off, 720=30d, 1440=60d, 2160=90d


# ─── modified simulate_combined with max_halt_hours ───────────────────────────

def simulate_combined_v18(
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
    """Extend simulate_combined with a max_halt_hours force-resume feature.

    If the CB has kept trading halted for >= max_halt_hours consecutive bars
    (each bar = 1 hour), trading is force-resumed regardless of cb_dd.
    This prevents the CB from locking out indefinitely after a big bull run.
    """
    window_bars = cb_window_days * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq = INIT
    peak_alltime = INIT
    halted = False
    halt_since_bar: int = 0   # bar index when halt started
    eq_vals = []
    y_vals = []
    cb_flags = []
    halt_hours_vals = []   # consecutive bars halted (resets on resume)

    for bar_i in range(len(unit_normal)):
        ur_n = float(unit_normal.iloc[bar_i])
        ur_c = float(unit_crash.iloc[bar_i])

        # Sliding-window max for CB
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
                hours_halted = bar_i - halt_since_bar
                normal_resume = cb_dd <= cb_resume
                force_resume  = (max_halt_hours is not None
                                 and hours_halted >= max_halt_hours)
                if normal_resume or force_resume:
                    halted = False
        else:
            halted = False

        # Adaptive Y for normal leg
        if halted:
            y = 0.0
        elif dd_aty <= dd_soft:
            y = 1.0
        elif dd_aty >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        r = K_normal * y * ur_n + K_crash * ur_c
        r = max(r, -0.95)
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
        eq          = eqs,
        final       = float(eqs.iloc[-1]),
        cagr        = float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe      = float(np.sqrt(24 * 365.25) * rets.mean() / rets.std()) if rets.std() > 0 else 0.0,
        maxdd       = float(dd_s.min()),
        pct_halted  = float(np.mean(cb_flags)),
        n_trips     = int(sum(cb_flags[i] > cb_flags[i - 1] for i in range(1, len(cb_flags)))),
        avg_y       = float(np.mean(y_vals)),
        cb_flags    = cb_flags,
        halt_hours  = halt_hours_vals,
    )


# ─── period helpers ───────────────────────────────────────────────────────────

def _period_metrics(eq: pd.Series, cb_flags: list[int], period: str, label: str) -> list[dict]:
    rows = []
    cb_s = pd.Series(cb_flags, index=eq.index)
    grouped_eq = eq.groupby(eq.index.to_period(period))
    grouped_cb = cb_s.groupby(cb_s.index.to_period(period))
    for p, s in grouped_eq:
        if s.empty:
            continue
        cb_period = grouped_cb.get_group(p) if p in grouped_cb.groups else pd.Series([], dtype=float)
        start_eq = float(s.iloc[0])
        end_eq   = float(s.iloc[-1])
        profit   = end_eq - start_eq
        ret      = end_eq / start_eq - 1.0 if start_eq else float("nan")
        dd       = float((s / s.cummax() - 1.0).min())
        r        = s.pct_change().replace([float("inf"), float("-inf")], float("nan")).dropna()
        sharpe   = float(r.mean() / (r.std() + 1e-12) * np.sqrt(365 * 24)) if len(r) > 3 else 0.0
        pct_halt = float(cb_period.mean()) if len(cb_period) > 0 else 0.0
        rows.append({
            "label":       label,
            "period":      str(p),
            "start":       str(s.index[0]),
            "end":         str(s.index[-1]),
            "start_eq":    start_eq,
            "end_eq":      end_eq,
            "profit":      profit,
            "return_pct":  100.0 * ret,
            "maxdd_pct":   100.0 * dd,
            "sharpe":      sharpe,
            "pct_halted":  100.0 * pct_halt,
            "bars":        int(len(s)),
        })
    return rows


def _fmt_money(x: float) -> str:  return f"${x:,.2f}"
def _fmt_pct(x: float) -> str:    return f"{x:+,.2f}%"
def _fmt_float(x: float) -> str:  return f"{x:+.3f}"


def _markdown_table(df: pd.DataFrame, cols: list[str]) -> str:
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, r in df.iterrows():
        vals = []
        for c in cols:
            v = r[c]
            if c in {"start_eq", "end_eq", "profit", "final", "profit_total"}:
                vals.append(_fmt_money(float(v)))
            elif c in {"return_pct", "maxdd_pct", "cagr_pct", "total_return_pct", "pct_halted"}:
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
    print("  CRYPTO GODMODE v18 — CIRCUIT BREAKER RESUME FIX")
    print(f"  Diagnosing why 2026 is flat; sweeping CB_RESUME × max_halt_hours")
    print(BAR)

    # ── Step 1: rebuild the same unit series as v17 ──────────────────────────
    print("\n[1] Rebuilding be50_btc_sol unit series (same as v17) ...")
    df, _ = build_1h_df(start="2021-01-01", end="2026-05-15")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    ohlc_map   = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch         = get_channel_series()

    w_star    = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag_cal = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v18")
    log_ann   = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_f, theta,
                                   kappa=KAPPA_A, anneal=True, label="v18_anneal")

    inputs_noq = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=False)
    inputs_q   = build_asset_inputs(df, log_ann, w_star, ch, ohlc_map, signal_kind="wstar", use_quadrant=True)
    inputs     = attach_q_hot(inputs_noq, inputs_q)
    sig_map    = {asset: pd.Series(w_star[:, idx], index=df.index, name=f"wstar_{asset}")
                  for asset, _, _, idx in ASSETS}
    cfg        = next(c for c in v12.VARIANTS if c["name"] == "be50_btc_sol")
    v12.RT_COST = REALISTIC_RT_BPS / 10_000.0
    unit_res   = v12.run_variant(cfg, inputs, sig_map, log_ann)
    unit       = unit_res["unit"]
    print(f"  unit series: {unit.index[0].date()} → {unit.index[-1].date()}  n={len(unit):,}")

    # ── Step 2: sweep CB parameters ──────────────────────────────────────────
    print("\n[2] Sweeping CB_RESUME × max_halt_hours ...")
    print(f"  base CB_HALT={CB_HALT:.0%}  CB_WINDOW={CB_WINDOW_DAYS}d  K={K_NORMAL}")
    zero     = pd.Series(np.zeros(len(unit)), index=unit.index)
    test_ts  = pd.Timestamp(TEST_START)
    sweep_rows = []

    for cb_res in CB_RESUME_GRID:
        for mh in MAX_HALT_H_GRID:
            label = f"resume{int(cb_res*100):02d}%_maxhalt{'off' if mh is None else f'{mh//24}d'}"
            res   = simulate_combined_v18(
                unit, zero,
                K_normal=K_NORMAL, K_crash=0.0,
                dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
                cb_halt=CB_HALT, cb_resume=cb_res,
                cb_window_days=CB_WINDOW_DAYS,
                max_halt_hours=mh, use_cb=True,
            )
            eq_test = res["eq"][res["eq"].index >= test_ts]
            cb_test = [res["cb_flags"][i] for i, ts in enumerate(res["eq"].index) if ts >= test_ts]

            # 2026 sub-period
            eq_2026 = eq_test[eq_test.index >= "2026-01-01"]
            ret_2026 = (float(eq_2026.iloc[-1]) / float(eq_2026.iloc[0]) - 1.0) if len(eq_2026) > 0 else float("nan")
            cb_2026  = [res["cb_flags"][i] for i, ts in enumerate(res["eq"].index) if ts >= pd.Timestamp("2026-01-01")]
            halted_2026_pct = float(np.mean(cb_2026)) if cb_2026 else 0.0

            m = equity_metrics(eq_test, label)
            years  = max((eq_test.index[-1] - eq_test.index[0]).days / 365.25, 1e-9)
            calmar = float(m["cagr"]) / max(abs(float(m["maxdd"])), 1e-9)
            sweep_rows.append({
                "label":         label,
                "cb_resume_pct": cb_res * 100,
                "max_halt_days": None if mh is None else mh // 24,
                "final":         float(m["final"]),
                "cagr_pct":      float(m["cagr"]) * 100,
                "sharpe":        float(m["sharpe"]),
                "maxdd_pct":     float(m["maxdd"]) * 100,
                "calmar":        calmar,
                "pct_halted":    res["pct_halted"] * 100,
                "n_trips":       res["n_trips"],
                "ret_2026_pct":  ret_2026 * 100,
                "halted_2026_pct": halted_2026_pct * 100,
            })
            print(f"  {label:<35}  CAGR={m['cagr']:+.1%}  Sharpe={m['sharpe']:+.3f}  "
                  f"MaxDD={m['maxdd']:+.1%}  Calmar={calmar:+.3f}  "
                  f"halt={res['pct_halted']:.0%}  2026_ret={ret_2026:+.1%}  2026_halt={halted_2026_pct:.0%}")

    sweep_df = pd.DataFrame(sweep_rows).sort_values("calmar", ascending=False).reset_index(drop=True)

    # ── Step 3: full period tables for the winner ─────────────────────────────
    winner   = sweep_df.iloc[0]
    w_res_cb = float(winner["cb_resume_pct"]) / 100.0
    w_mh_d   = winner["max_halt_days"]
    w_mh_h   = None if pd.isna(w_mh_d) or w_mh_d is None else int(w_mh_d) * 24
    print(f"\n[3] Winner: {winner['label']}")
    print(f"    CB_RESUME={w_res_cb:.0%}  max_halt_days={w_mh_d}  "
          f"Calmar={winner['calmar']:+.3f}  CAGR={winner['cagr_pct']:+.1f}%  "
          f"Sharpe={winner['sharpe']:+.3f}  MaxDD={winner['maxdd_pct']:+.1f}%")

    res_win = simulate_combined_v18(
        unit, zero,
        K_normal=K_NORMAL, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=w_res_cb,
        cb_window_days=CB_WINDOW_DAYS,
        max_halt_hours=w_mh_h, use_cb=True,
    )
    eq_win    = res_win["eq"][res_win["eq"].index >= test_ts]
    test_mask = res_win["eq"].index >= test_ts
    cb_w_test = [f for f, in_test in zip(res_win["cb_flags"], test_mask) if in_test]

    quarterly = _period_metrics(eq_win, cb_w_test, "Q", winner["label"])
    yearly    = _period_metrics(eq_win, cb_w_test, "Y", winner["label"])

    print("\n  Year-on-Year (winner):")
    for r in yearly:
        print(f"    {r['period']}  return={r['return_pct']:+.1f}%  halted={r['pct_halted']:.0f}%  "
              f"maxdd={r['maxdd_pct']:+.1f}%")

    # ── Step 4: save outputs ──────────────────────────────────────────────────
    print("\n[4] Saving outputs ...")
    payload = {
        "meta": {
            "version": "godmode_v18_cb_fix",
            "strategy": "be50_btc_sol",
            "K_normal": K_NORMAL,
            "rt_bps": REALISTIC_RT_BPS,
            "cb_halt": CB_HALT,
            "cb_window_days": CB_WINDOW_DAYS,
            "sweep_cb_resume": CB_RESUME_GRID,
            "sweep_max_halt_hours": MAX_HALT_H_GRID,
            "theta": diag_cal["theta"],
            "elapsed": time.time() - t0,
        },
        "sweep": sweep_df.to_dict(orient="records"),
        "winner": {
            "label":           winner["label"],
            "cb_resume_pct":   float(winner["cb_resume_pct"]),
            "max_halt_days":   None if pd.isna(w_mh_d) or w_mh_d is None else int(w_mh_d),
            "cagr_pct":        float(winner["cagr_pct"]),
            "sharpe":          float(winner["sharpe"]),
            "maxdd_pct":       float(winner["maxdd_pct"]),
            "calmar":          float(winner["calmar"]),
        },
        "winner_yearly":    yearly,
        "winner_quarterly": quarterly,
    }
    json_path = OUT_DIR_ / "crypto_bsdt_v18_cb_fix.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=float)

    # Markdown report
    sweep_top5 = sweep_df.head(5)
    md_lines = [
        "# Crypto Godmode v18 — Circuit Breaker Resume Fix",
        "",
        f"**Root cause:** After the 2025Q4 bull run (+411%), `CB_RESUME=1%` locks out trading indefinitely in 2026.",
        f"**Fix:** Sweep `CB_RESUME` ∈ {CB_RESUME_GRID} × `max_halt_hours` ∈ {MAX_HALT_H_GRID}.",
        f"**K:** {K_NORMAL}  **CB_HALT:** {CB_HALT:.0%}  **CB_WINDOW:** {CB_WINDOW_DAYS}d  "
        f"**Strategy:** be50_btc_sol  **Costs:** {REALISTIC_RT_BPS} bps RT",
        "",
        "## Top-5 Sweep Configurations",
        "",
        _markdown_table(sweep_top5, [
            "label", "cb_resume_pct", "max_halt_days",
            "cagr_pct", "sharpe", "maxdd_pct", "calmar",
            "pct_halted", "ret_2026_pct", "halted_2026_pct",
        ]),
        "",
        "## Full Sweep Results",
        "",
        _markdown_table(sweep_df, [
            "label", "cb_resume_pct", "max_halt_days",
            "cagr_pct", "sharpe", "maxdd_pct", "calmar",
            "pct_halted", "ret_2026_pct",
        ]),
        "",
        f"## Winner: `{winner['label']}`",
        "",
        f"CB_RESUME = {w_res_cb:.0%}  | max_halt_days = {w_mh_d}  | "
        f"CAGR = {winner['cagr_pct']:+.1f}%  | Sharpe = {winner['sharpe']:+.3f}  | "
        f"MaxDD = {winner['maxdd_pct']:+.1f}%  | Calmar = {winner['calmar']:+.3f}",
        "",
        "### Year-on-Year (winner)",
        "",
        _markdown_table(pd.DataFrame(yearly),
                        ["period", "start_eq", "end_eq", "profit", "return_pct", "maxdd_pct", "sharpe", "pct_halted"]),
        "",
        "### Quarterly (winner)",
        "",
        _markdown_table(pd.DataFrame(quarterly),
                        ["period", "start_eq", "end_eq", "profit", "return_pct", "maxdd_pct", "sharpe", "pct_halted"]),
        "",
    ]
    md_path = OUT_DIR_ / "crypto_bsdt_v18_cb_fix_report.md"
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines))

    print(f"  saved: {json_path}")
    print(f"  saved: {md_path}")
    print(f"\n  elapsed={time.time() - t0:.1f}s")
    print(BAR)


if __name__ == "__main__":
    main()
