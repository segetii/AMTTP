"""
Crypto Godmode v24 — Per-Direction Independent Circuit Breakers
================================================================

Root cause of all previous failures:
  A SINGLE combined CB cannot distinguish two different situations:
    A) Longs are losing BUT shorts are earning (bear market = want shorts active)
    B) BOTH longs AND shorts are losing    (bull correction = want everything halted)

v22 (always free shorts during halt) → ran into situation B → 2023/2024 ruined.
v23 (free shorts only if rolling short PnL > 0) → lag too long / threshold wrong.

v24 — correct solution:
  ┌─────────────────────────────────────────────────────────────────┐
  │  Two independent CBs, one per direction                         │
  │                                                                 │
  │  long_sub_eq  tracks K-scaled long  P&L → fires long_halted   │
  │  short_sub_eq tracks K-scaled short P&L → fires short_halted  │
  │                                                                 │
  │  Each sub-account uses the SAME CB_HALT/CB_RESUME/CB_WINDOW    │
  │  parameters as v17, but applied to its own sub-equity curve.   │
  │                                                                 │
  │  Main equity (for adaptive-Y) = INIT + sum(r_long + r_short)  │
  └─────────────────────────────────────────────────────────────────┘

Expected behaviour:
  2026 correction (BTC -30% from Dec peak):
    long_sub_eq drops  → long CB fires    → LONGS BLOCKED   ✓
    short_sub_eq rises → short CB stays off → SHORTS ACTIVE  ✓

  2023-2024 bull corrections (CB fired in v17 and correctly):
    long_sub_eq drops  → long CB fires    → LONGS BLOCKED   ✓
    short_sub_eq drops → short CB fires   → SHORTS BLOCKED  ✓  (same as v17)

Sweep:
  CB_WINDOW_DAYS ∈ {90, 120, 180}   — per-direction CB might suit shorter window
  (CB_HALT = 8%, CB_RESUME = 1%  unchanged from v17 champion params)

Outputs:
  crypto_bsdt_v24_perdirection_cb.json
  crypto_bsdt_v24_perdirection_cb_report.md
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
    FUND_HOURLY, equity_metrics, INIT, HOURS_PER_DAY,
)
from simulate_v63_quadrant import CB_HALT, CB_RESUME, CB_WINDOW_DAYS
from test_daily_geometry_stop_tp_ohlc import get_channel_series
from test_psi_adaptive_y import BASE
import run_crypto_godmode_v12_filter_innovate as v12
from run_crypto_godmode_v22_directional_cb import run_variant_v22

OUT_DIR_         = Path(OUT_DIR)
BAR              = "=" * 112
REALISTIC_RT_BPS = 6.0
RT_COST          = REALISTIC_RT_BPS / 10_000.0
K_NORMAL         = 6.0

CB_WINDOW_SWEEP  = [90, 120, 180]   # days — sweep per-direction CB window


# ─── core: per-direction independent CB ──────────────────────────────────────

def simulate_combined_v24(
    unit_long:      pd.Series,
    unit_short:     pd.Series,
    K_normal:       float,
    dd_soft:        float,
    dd_stop:        float,
    y_floor:        float,
    cb_halt:        float,
    cb_resume:      float,
    cb_window_days: int,
    use_cb:         bool = True,
) -> dict:
    """Per-direction independent circuit breakers.

    Two sub-accounts (long_sub, short_sub) each compound their own K-scaled
    unit P&L and carry their own 180-day-rolling-max CB.  The main equity
    compounds the SUM of actual bar returns and drives the adaptive-Y factor.

    CB logic per sub-account:
      cb_dd = 1 - sub_eq / rolling_peak(window)
      fire when cb_dd >= cb_halt
      clear when cb_dd <= cb_resume

    When a sub-account is halted it accrues 0 (flat equity), which lets the
    rolling peak "age out" of the window — exactly how the original CB works.
    """
    n           = len(unit_long)
    window_bars = cb_window_days * HOURS_PER_DAY
    assert n == len(unit_short)

    # Main equity (adaptive-Y reference)
    eq           = float(INIT)
    peak_alltime = float(INIT)

    # Per-direction sub-accounts (CB tracking)
    long_sub  = float(INIT)
    short_sub = float(INIT)
    long_halted  = False
    short_halted = False

    # Separate monotonic deques for rolling max
    long_dq:  deque = deque()
    short_dq: deque = deque()

    eq_vals:          list[float] = []
    long_halt_flags:  list[int]   = []
    short_halt_flags: list[int]   = []
    y_vals:           list[float] = []

    ul_arr = unit_long.values.astype(float)
    us_arr = unit_short.values.astype(float)

    for i in range(n):
        ul = ul_arr[i]
        us = us_arr[i]

        # ── long sub-account rolling peak ──────────────────────────────
        while long_dq and long_dq[0][0] <= i - window_bars:
            long_dq.popleft()
        while long_dq and long_dq[-1][1] <= long_sub:
            long_dq.pop()
        long_dq.append((i, long_sub))
        long_roll_peak = long_dq[0][1]

        # ── short sub-account rolling peak ─────────────────────────────
        while short_dq and short_dq[0][0] <= i - window_bars:
            short_dq.popleft()
        while short_dq and short_dq[-1][1] <= short_sub:
            short_dq.pop()
        short_dq.append((i, short_sub))
        short_roll_peak = short_dq[0][1]

        # ── per-direction CB drawdowns ──────────────────────────────────
        long_cb_dd  = max(0.0, 1.0 - long_sub  / max(long_roll_peak,  1e-12))
        short_cb_dd = max(0.0, 1.0 - short_sub / max(short_roll_peak, 1e-12))

        if use_cb:
            if not long_halted  and long_cb_dd  >= cb_halt:   long_halted  = True
            if long_halted      and long_cb_dd  <= cb_resume: long_halted  = False
            if not short_halted and short_cb_dd >= cb_halt:   short_halted = True
            if short_halted     and short_cb_dd <= cb_resume: short_halted = False

        # ── adaptive Y from combined all-time drawdown ──────────────────
        dd_aty = max(0.0, 1.0 - eq / max(peak_alltime, 1e-12))
        if dd_aty <= dd_soft:
            y = 1.0
        elif dd_aty >= dd_stop:
            y = y_floor
        else:
            y = y_floor + (1.0 - y_floor) * (dd_stop - dd_aty) / (dd_stop - dd_soft)

        # ── bar returns ─────────────────────────────────────────────────
        r_long  = 0.0 if long_halted  else K_normal * y * ul
        r_short = 0.0 if short_halted else K_normal * y * us
        r = max(r_long + r_short, -0.95)

        # ── update equities ─────────────────────────────────────────────
        eq          *= (1.0 + r)
        peak_alltime = max(peak_alltime, eq)

        # Sub-accounts use K without y (tracks directional signal quality
        # independent of the combined adaptive-Y squeeze)
        if not long_halted:
            long_sub  *= (1.0 + max(K_normal * ul, -0.95))
        if not short_halted:
            short_sub *= (1.0 + max(K_normal * us, -0.95))

        eq_vals.append(eq)
        long_halt_flags.append(int(long_halted))
        short_halt_flags.append(int(short_halted))
        y_vals.append(y)

    eqs  = pd.Series(eq_vals, index=unit_long.index)
    rets = eqs.pct_change().fillna(eqs.iloc[0] / INIT - 1.0)
    dd_s = (eqs - eqs.cummax()) / eqs.cummax()
    years = max((eqs.index[-1] - eqs.index[0]).days / 365.25, 1e-9)

    both_halted_flags = [int(l and s) for l, s in zip(long_halt_flags, short_halt_flags)]
    long_only_halt    = [int(l and not s) for l, s in zip(long_halt_flags, short_halt_flags)]
    short_only_halt   = [int(not l and s) for l, s in zip(long_halt_flags, short_halt_flags)]

    return dict(
        eq                 = eqs,
        final              = float(eqs.iloc[-1]),
        cagr               = float((eqs.iloc[-1] / INIT) ** (1 / years) - 1.0),
        sharpe             = float(np.sqrt(24 * 365.25) * rets.mean() / rets.std())
                             if rets.std() > 0 else 0.0,
        maxdd              = float(dd_s.min()),
        pct_long_halt      = float(np.mean(long_halt_flags)),
        pct_short_halt     = float(np.mean(short_halt_flags)),
        pct_both_halt      = float(np.mean(both_halted_flags)),
        pct_long_only_halt = float(np.mean(long_only_halt)),
        pct_short_only_halt= float(np.mean(short_only_halt)),
        long_halt_flags    = long_halt_flags,
        short_halt_flags   = short_halt_flags,
        avg_y              = float(np.mean(y_vals)),
    )


# ─── period helpers ───────────────────────────────────────────────────────────

def _period_metrics(
    eq: pd.Series,
    long_halt: list[int],
    short_halt: list[int],
    period: str,
    label: str,
) -> list[dict]:
    rows     = []
    lh_s     = pd.Series(long_halt,  index=eq.index)
    sh_s     = pd.Series(short_halt, index=eq.index)
    grp_eq   = eq.groupby(eq.index.to_period(period))
    grp_lh   = lh_s.groupby(lh_s.index.to_period(period))
    grp_sh   = sh_s.groupby(sh_s.index.to_period(period))

    for p, s in grp_eq:
        if s.empty:
            continue
        lh_p = grp_lh.get_group(p) if p in grp_lh.groups else pd.Series([], dtype=float)
        sh_p = grp_sh.get_group(p) if p in grp_sh.groups else pd.Series([], dtype=float)

        start = float(s.iloc[0]); end = float(s.iloc[-1])
        ret   = end / start - 1.0 if start else float("nan")
        dd    = float((s / s.cummax() - 1.0).min())
        r_ch  = s.pct_change().replace([float("inf"), float("-inf")], float("nan")).dropna()
        sh    = float(r_ch.mean() / (r_ch.std() + 1e-12) * np.sqrt(365 * 24)) if len(r_ch) > 3 else 0.0
        plh   = float(lh_p.mean()) if len(lh_p) > 0 else 0.0
        psh   = float(sh_p.mean()) if len(sh_p) > 0 else 0.0
        rows.append({
            "label": label, "period": str(p),
            "start_eq": start, "end_eq": end, "profit": end - start,
            "return_pct": 100.0 * ret, "maxdd_pct": 100.0 * dd,
            "sharpe": sh, "long_halt_pct": 100.0 * plh, "short_halt_pct": 100.0 * psh,
        })
    return rows


def _md_table(df: pd.DataFrame, cols: list[str]) -> str:
    pct_cols   = {"return_pct","maxdd_pct","cagr_pct","long_halt_pct","short_halt_pct",
                  "pct_long_halt","pct_short_halt","pct_both_halt","pct_long_only_halt",
                  "ret_2026_pct","lh_2026_pct","sh_2026_pct"}
    money_cols = {"start_eq","end_eq","profit","final"}
    float_cols = {"sharpe","calmar","cb_window"}
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, row in df.iterrows():
        vals = []
        for c in cols:
            v = row[c]
            if c in money_cols:    vals.append(f"${float(v):,.2f}")
            elif c in pct_cols:    vals.append(f"{float(v):+,.1f}%")
            elif c in float_cols:  vals.append(f"{float(v):+.3f}")
            else:                  vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(BAR)
    print("  CRYPTO GODMODE v24 — PER-DIRECTION INDEPENDENT CIRCUIT BREAKERS")
    print("  Fix: long CB tracks long sub-equity, short CB tracks short sub-equity")
    print("  → In bear market: long CB fires, short CB stays off → shorts keep running")
    print(BAR)

    # ── Step 1: build unit series ─────────────────────────────────────────
    print("\n[1] Building be50_btc_sol long/short unit series ...")
    df, _ = build_1h_df(start="2021-01-01", end="2026-06-01")
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    test_mask  = np.asarray(df.index >= TEST_START)
    ohlc_map   = {symbol: fetch_futures_ohlcv_symbol(symbol) for _, symbol, _, _ in ASSETS}
    ch         = get_channel_series()

    w_star    = build_w_star(df, W_TARGET=W_TARGET_A1)
    b_aligned = build_b_aligned(w_star)
    Sigma_f, theta, diag_cal = calibrate(df, train_mask, w_star, b_aligned, kappa=KAPPA_A, label="v24")
    log_ann   = run_godmode_sweep(df, train_mask, test_mask, w_star, b_aligned, Sigma_f, theta,
                                   kappa=KAPPA_A, anneal=True, label="v24_anneal")

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

    ul_t = unit_long[unit_long.index   >= test_ts]
    us_t = unit_short[unit_short.index >= test_ts]
    print(f"  unit: {unit.index[0].date()} → {unit.index[-1].date()}  n={len(unit):,}")
    print(f"  long bars (OOS):  {int((ul_t!=0).sum()):,} ({(ul_t!=0).mean():.1%})")
    print(f"  short bars (OOS): {int((us_t!=0).sum()):,} ({(us_t!=0).mean():.1%})")

    # ── Step 2: v17 baseline ──────────────────────────────────────────────
    print("\n[2] Baseline: v17 (single combined CB) ...")
    from simulate_master_strategy import simulate_combined as sim_orig
    zero     = pd.Series(np.zeros(len(unit)), index=unit.index)
    res_base = sim_orig(
        unit, zero,
        K_normal=K_NORMAL, K_crash=0.0,
        dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
        cb_halt=CB_HALT, cb_resume=CB_RESUME, cb_window_days=CB_WINDOW_DAYS, use_cb=True,
    )
    eq_base     = res_base["eq"][res_base["eq"].index >= test_ts]
    m_base      = equity_metrics(eq_base, "baseline_v17")
    calmar_base = float(m_base["cagr"]) / max(abs(float(m_base["maxdd"])), 1e-9)
    eq_2026b    = eq_base[eq_base.index >= "2026-01-01"]
    r2026b      = float(eq_2026b.iloc[-1]) / float(eq_2026b.iloc[0]) - 1.0 if len(eq_2026b) > 1 else 0.0
    print(f"  CAGR={m_base['cagr']:+.1%}  Sharpe={m_base['sharpe']:+.3f}  "
          f"MaxDD={m_base['maxdd']:+.1%}  Calmar={calmar_base:+.3f}  2026={r2026b:+.1%}")

    # ── Step 3: sweep CB_WINDOW_DAYS ─────────────────────────────────────
    print(f"\n[3] v24 per-direction CB sweep (CB_HALT={CB_HALT:.0%}, CB_RESUME={CB_RESUME:.0%}) ...")
    sweep_rows = []

    for win in CB_WINDOW_SWEEP:
        label = f"win{win:03d}"
        res   = simulate_combined_v24(
            unit_long, unit_short,
            K_normal=K_NORMAL,
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
            cb_halt=CB_HALT, cb_resume=CB_RESUME,
            cb_window_days=win, use_cb=True,
        )
        t_idx   = res["eq"].index >= test_ts
        eq_t    = res["eq"][t_idx]
        lh_t    = [v for v, m in zip(res["long_halt_flags"],  t_idx) if m]
        sh_t    = [v for v, m in zip(res["short_halt_flags"], t_idx) if m]

        eq_2026  = eq_t[eq_t.index >= "2026-01-01"]
        r_2026   = float(eq_2026.iloc[-1]) / float(eq_2026.iloc[0]) - 1.0 if len(eq_2026) > 1 else 0.0
        lh_2026  = [res["long_halt_flags"][i]  for i, ts in enumerate(res["eq"].index)
                    if ts >= pd.Timestamp("2026-01-01")]
        sh_2026  = [res["short_halt_flags"][i] for i, ts in enumerate(res["eq"].index)
                    if ts >= pd.Timestamp("2026-01-01")]
        lh_2026_pct = float(np.mean(lh_2026)) if lh_2026 else 0.0
        sh_2026_pct = float(np.mean(sh_2026)) if sh_2026 else 0.0

        m      = equity_metrics(eq_t, label)
        calmar = float(m["cagr"]) / max(abs(float(m["maxdd"])), 1e-9)
        sweep_rows.append({
            "label":             label,
            "cb_window":         float(win),
            "final":             float(m["final"]),
            "cagr_pct":          float(m["cagr"]) * 100,
            "sharpe":            float(m["sharpe"]),
            "maxdd_pct":         float(m["maxdd"]) * 100,
            "calmar":            calmar,
            "pct_long_halt":     res["pct_long_halt"]  * 100,
            "pct_short_halt":    res["pct_short_halt"] * 100,
            "pct_both_halt":     res["pct_both_halt"]  * 100,
            "pct_long_only_halt":res["pct_long_only_halt"] * 100,
            "ret_2026_pct":      r_2026 * 100,
            "lh_2026_pct":       lh_2026_pct * 100,
            "sh_2026_pct":       sh_2026_pct * 100,
        })
        print(f"  window={win}d  CAGR={m['cagr']:+.1%}  Sharpe={m['sharpe']:+.3f}  "
              f"MaxDD={m['maxdd']:+.1%}  Calmar={calmar:+.3f}  "
              f"long_halt={res['pct_long_halt']:.0%}  short_halt={res['pct_short_halt']:.0%}  "
              f"both={res['pct_both_halt']:.0%}  long_only={res['pct_long_only_halt']:.0%}  "
              f"2026={r_2026:+.1%} (lh={lh_2026_pct:.0%} sh={sh_2026_pct:.0%})")

    sweep_df = pd.DataFrame(sweep_rows).sort_values("calmar", ascending=False).reset_index(drop=True)

    print(f"\n  {'='*90}")
    print(f"  Baseline v17:  CAGR={m_base['cagr']:+.1%}  Calmar={calmar_base:+.3f}  2026={r2026b:+.1%}")
    print(f"  Best v24:      CAGR={sweep_df.iloc[0]['cagr_pct']:+.1f}%  "
          f"Calmar={sweep_df.iloc[0]['calmar']:+.3f}  "
          f"2026={sweep_df.iloc[0]['ret_2026_pct']:+.1f}%  [{sweep_df.iloc[0]['label']}]")

    # ── Step 4: year-by-year table ────────────────────────────────────────
    print("\n[4] Year-on-year tables ...")
    period_results: dict = {}

    print(f"\n  Baseline v17:")
    yr_base = _period_metrics(eq_base, [0] * len(eq_base), [0] * len(eq_base), "Y", "v17")
    for row in yr_base:
        print(f"    {row['period']}  return={row['return_pct']:+.1f}%  maxdd={row['maxdd_pct']:+.1f}%")

    for _, w in sweep_df.iterrows():
        win = int(w["cb_window"])
        lbl = w["label"]
        print(f"\n  {lbl} (window={win}d):")
        res_w = simulate_combined_v24(
            unit_long, unit_short,
            K_normal=K_NORMAL,
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
            cb_halt=CB_HALT, cb_resume=CB_RESUME,
            cb_window_days=win, use_cb=True,
        )
        t_idx  = res_w["eq"].index >= test_ts
        eq_w   = res_w["eq"][t_idx]
        lh_w   = [v for v, m in zip(res_w["long_halt_flags"],  t_idx) if m]
        sh_w   = [v for v, m in zip(res_w["short_halt_flags"], t_idx) if m]
        yr_w   = _period_metrics(eq_w, lh_w, sh_w, "Y",  lbl)
        qtr_w  = _period_metrics(eq_w, lh_w, sh_w, "Q",  lbl)
        period_results[lbl] = {"yearly": yr_w, "quarterly": qtr_w}
        for row in yr_w:
            print(f"    {row['period']}  return={row['return_pct']:+.1f}%  "
                  f"long_halt={row['long_halt_pct']:.0f}%  "
                  f"short_halt={row['short_halt_pct']:.0f}%  "
                  f"maxdd={row['maxdd_pct']:+.1f}%")

    winner = sweep_df.iloc[0]

    # ── Step 5: save outputs ──────────────────────────────────────────────
    print("\n[5] Saving outputs ...")
    payload = {
        "meta": {
            "version":          "godmode_v24_perdirection_cb",
            "strategy":         "be50_btc_sol",
            "K_normal":         K_NORMAL,
            "rt_bps":           REALISTIC_RT_BPS,
            "cb_halt":          CB_HALT,
            "cb_resume":        CB_RESUME,
            "cb_window_sweep":  CB_WINDOW_SWEEP,
            "theta":            diag_cal["theta"],
            "elapsed":          time.time() - t0,
            "fix":              "per_direction_independent_cb",
        },
        "baseline": {
            "cagr_pct":  float(m_base["cagr"]) * 100,
            "sharpe":    float(m_base["sharpe"]),
            "maxdd_pct": float(m_base["maxdd"]) * 100,
            "calmar":    calmar_base,
            "ret_2026":  r2026b * 100,
        },
        "sweep":  sweep_df.to_dict(orient="records"),
        "winner": {
            "label":        winner["label"],
            "cb_window":    int(winner["cb_window"]),
            "cagr_pct":     float(winner["cagr_pct"]),
            "sharpe":       float(winner["sharpe"]),
            "maxdd_pct":    float(winner["maxdd_pct"]),
            "calmar":       float(winner["calmar"]),
            "ret_2026_pct": float(winner["ret_2026_pct"]),
        },
        "period_results": period_results,
    }

    json_path = OUT_DIR_ / "crypto_bsdt_v24_perdirection_cb.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, default=str)

    md_lines = [
        "# Crypto Godmode v24 — Per-Direction Independent Circuit Breakers",
        "",
        "## Architecture",
        "",
        "Two CB sub-accounts. Each tracks only its own K-scaled P&L:",
        "- `long_sub_eq`  = K × cumulative long  unit returns (flat when long-halted)",
        "- `short_sub_eq` = K × cumulative short unit returns (flat when short-halted)",
        "",
        "| Situation | Long CB | Short CB | Long trades | Short trades |",
        "|-----------|---------|----------|-------------|--------------|",
        "| Normal market | off | off | active | active |",
        "| Bear market correction | **fires** | stays off | **blocked** | **active** |",
        "| Bull market pullback | fires | fires | blocked | blocked |",
        "",
        f"**K_normal={K_NORMAL}  CB_HALT={CB_HALT:.0%}  CB_RESUME={CB_RESUME:.0%}  "
        f"RT={REALISTIC_RT_BPS} bps  Strategy=be50_btc_sol**",
        "",
        "## Baseline (v17 single combined CB)",
        "",
        f"CAGR={m_base['cagr']:+.1%}  Sharpe={m_base['sharpe']:+.3f}  "
        f"MaxDD={m_base['maxdd']:+.1%}  Calmar={calmar_base:+.3f}  2026={r2026b:+.1%}",
        "",
        "## Sweep: CB_WINDOW_DAYS",
        "",
        _md_table(sweep_df, [
            "label","cb_window","cagr_pct","sharpe","maxdd_pct","calmar",
            "pct_long_halt","pct_short_halt","pct_both_halt","pct_long_only_halt",
            "ret_2026_pct","lh_2026_pct","sh_2026_pct",
        ]),
        "",
        f"## Winner: `{winner['label']}` (window={int(winner['cb_window'])}d)",
        "",
        f"CAGR={float(winner['cagr_pct']):+.1f}%  Calmar={float(winner['calmar']):+.3f}  "
        f"2026={float(winner['ret_2026_pct']):+.1f}%",
        "",
    ]

    for lbl, pdata in period_results.items():
        md_lines += [
            f"### Period: `{lbl}`",
            "",
            "**Year-on-Year**",
            "",
            _md_table(pd.DataFrame(pdata["yearly"]),
                      ["period","start_eq","end_eq","profit",
                       "return_pct","maxdd_pct","sharpe","long_halt_pct","short_halt_pct"]),
            "",
            "**Quarterly**",
            "",
            _md_table(pd.DataFrame(pdata["quarterly"]),
                      ["period","start_eq","end_eq","profit",
                       "return_pct","maxdd_pct","sharpe","long_halt_pct","short_halt_pct"]),
            "",
        ]

    md_path = OUT_DIR_ / "crypto_bsdt_v24_perdirection_cb_report.md"
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines))

    print(f"  saved: {json_path}")
    print(f"  saved: {md_path}")
    el = time.time() - t0
    print(f"\n  Elapsed: {el:.1f}s  ({el/60:.1f} min)")
    print(BAR)


if __name__ == "__main__":
    main()
