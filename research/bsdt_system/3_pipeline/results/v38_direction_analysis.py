"""
v38_direction_analysis.py
--------------------------
For each active segment in v38a, split into first-half / second-half PnL.
Determines: were losing trades right in direction but then reversed?
Cross-checks with the Omega filter (gamma * rhs_norm >= 0.02).
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from v38_trade_clustering import (
    simulate_extended, VARIANTS,
    build_1h_df, TEST_START,
    build_asset_inputs, run_godmode_det,
    CB_HALT, CB_RESUME, CB_WINDOW,
    DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
    c_sigma_per_bar,
)

OMEGA_THRESH = 0.02


def run_direction_analysis(variant: dict):
    label = variant["name"]
    print(f"\n{'='*75}")
    print(f"  DIRECTION ANALYSIS — variant {label}")
    print(f"{'='*75}")

    df = build_1h_df()
    asset_inputs = build_asset_inputs(df)
    test_ts = pd.Timestamp(TEST_START)

    # Run deterministic ODE + CB simulation
    out = run_godmode_det(
        df, asset_inputs,
        d=variant["d"],
        q=variant["q"],
        eta=variant["eta"],
        kappa_max=variant.get("kappa_max"),
        g7_on=variant.get("g7_on", False),
    )

    sim = simulate_extended(
        unit_normal     = out["unit_normal"],
        unit_crash      = out["unit_crash"],
        K_normal        = out["K_normal"],
        K_crash         = out["K_crash"],
        dd_soft         = DYN_DD_SOFT,
        dd_stop         = DYN_DD_STOP,
        y_floor         = DYN_Y_FLOOR,
        cb_halt         = CB_HALT,
        cb_resume       = CB_RESUME,
        cb_window_days  = CB_WINDOW,
        ito_c_sigma_bar = c_sigma_per_bar(variant["eta"]),
        lock_min        = variant["lock_min"],
    )

    ode_log = out["ode_log"].reindex(sim["cb_flag"].index, method="ffill")
    cb_flag = sim["cb_flag"]
    rets    = sim["rets"]
    eq      = sim["eq"]

    # Test window only
    test_cb   = cb_flag[cb_flag.index >= test_ts]
    test_rets = rets[rets.index >= test_ts]
    test_ode  = ode_log.reindex(test_cb.index, method="ffill")
    test_eq   = eq[eq.index >= test_ts]

    active = (test_cb == 0)
    arr    = active.values
    idx    = active.index

    # ── Detect actual market direction per segment ─────────────────────────────
    # w · R > 0 means position aligned with market = correct direction
    ret_cols = [c for c in df.columns if c in ("ret_btc", "ret_eth", "ret_sol")]
    df_test  = df.reindex(idx, method="ffill") if ret_cols else None

    segs = []
    in_seg = False
    for i in range(len(arr)):
        if arr[i] and not in_seg:
            in_seg = True
            seg_s  = i
        elif (not arr[i] or i == len(arr) - 1) and in_seg:
            seg_e  = i if not arr[i] else i + 1
            in_seg = False

            seg_ret = test_rets.iloc[seg_s:seg_e]
            seg_ode = test_ode.iloc[seg_s:seg_e]
            seg_eq  = test_eq[active].iloc[len(segs):len(segs)+1]  # just for start

            if len(seg_ret) < 4:
                continue

            n   = len(seg_ret)
            mid = n // 2
            h1  = float(seg_ret.iloc[:mid].sum())
            h2  = float(seg_ret.iloc[mid:].sum())
            tot = float(seg_ret.sum())

            # PnL skew
            skew = float(seg_ret.skew()) if n > 3 else 0.0

            # ODE state at segment START
            g_start = float(seg_ode.iloc[0]["gamma"])
            r_start = float(seg_ode.iloc[0]["rhs_norm"])
            omega   = g_start * r_start

            # Mean position direction (sign of avg weight)
            w_btc_mean = float(seg_ode["w_btc"].mean())
            w_eth_mean = float(seg_ode["w_eth"].mean())
            w_sol_mean = float(seg_ode["w_sol"].mean())

            # Actual market direction during segment (sign of cumulative return)
            if df_test is not None and "ret_btc" in df_test.columns:
                mkt_btc = float(df_test["ret_btc"].iloc[seg_s:seg_e].sum())
                mkt_eth = float(df_test["ret_eth"].iloc[seg_s:seg_e].sum()) if "ret_eth" in df_test.columns else 0.0
                mkt_sol = float(df_test["ret_sol"].iloc[seg_s:seg_e].sum()) if "ret_sol" in df_test.columns else 0.0
                # dot product: if >0, position was with market
                dot_prod = w_btc_mean * mkt_btc + w_eth_mean * mkt_eth + w_sol_mean * mkt_sol
                dir_correct = dot_prod > 0
            else:
                dot_prod    = float("nan")
                dir_correct = None

            # Direction-in-first-half vs second-half
            h1_ret = seg_ret.iloc[:mid]
            h2_ret = seg_ret.iloc[mid:]
            # Simple: did the market keep going the same way in H2 as H1?
            # Use sign of H1 cumulative as the "initial direction"
            # and H2 cumulative as "continuation"
            initial_dir_continued = (h1 >= 0) == (h2 >= 0)

            if h1 > 0 and h2 < 0:
                pattern = "REVERSAL"       # right then wrong
            elif h1 < 0 and h2 < 0:
                pattern = "CONSISTENT_LOSS"
            elif h1 > 0 and h2 > 0:
                pattern = "CONSISTENT_WIN"
            elif h1 < 0 and h2 > 0:
                pattern = "RECOVERY"
            else:
                pattern = "FLAT"

            # How fast did it turn? — peak PnL within segment before the reversal
            eq_from_start = (1 + seg_ret).cumprod()
            peak_gain  = float(eq_from_start.max() - 1.0)
            final_gain = float(eq_from_start.iloc[-1] - 1.0)
            gave_back  = float(peak_gain - final_gain)  # how much was surrendered

            segs.append(dict(
                start              = idx[seg_s],
                end                = idx[seg_e - 1],
                n_bars             = n,
                h1_pnl             = h1,
                h2_pnl             = h2,
                total_pnl          = tot,
                pnl_skew           = skew,
                gamma_start        = g_start,
                rhs_norm_start     = r_start,
                omega_start        = omega,
                filter_blocks      = omega >= OMEGA_THRESH,
                w_btc              = w_btc_mean,
                w_eth              = w_eth_mean,
                w_sol              = w_sol_mean,
                dot_prod           = dot_prod,
                dir_correct_overall = dir_correct,
                peak_gain          = peak_gain,
                gave_back          = gave_back,
                pattern            = pattern,
                label              = "WIN" if tot > 0 else "LOSE",
            ))

    # ── Print table ────────────────────────────────────────────────────────────
    print(f"\n  {'Start':20s}  {'Bars':>4s}  {'H1_PnL':>8s}  {'H2_PnL':>8s}  {'Total':>8s}  {'PeakGain':>9s}  {'GaveBack':>9s}  {'Omega':>7s}  {'Filter':>6s}  Pattern")
    print("  " + "-" * 115)
    for s in segs:
        flt = "BLOCK" if s["filter_blocks"] else "allow"
        print(f"  {str(s['start']):20s}  {s['n_bars']:>4d}  {s['h1_pnl']:>+8.4f}  {s['h2_pnl']:>+8.4f}  "
              f"{s['total_pnl']:>+8.4f}  {s['peak_gain']:>+9.4f}  {s['gave_back']:>+9.4f}  "
              f"{s['omega_start']:>7.5f}  {flt:>6s}  {s['pattern']}  ({s['label']})")

    # ── Summary ────────────────────────────────────────────────────────────────
    print()
    by_pattern = {}
    for s in segs:
        p = s["pattern"]
        by_pattern.setdefault(p, []).append(s)

    print("  PATTERN SUMMARY:")
    for pat, grp in sorted(by_pattern.items()):
        wins   = sum(1 for s in grp if s["label"] == "WIN")
        losses = sum(1 for s in grp if s["label"] == "LOSE")
        avg_gb = np.mean([s["gave_back"] for s in grp])
        avg_om = np.mean([s["omega_start"] for s in grp])
        would_block = sum(1 for s in grp if s["filter_blocks"])
        print(f"    {pat:20s}  n={len(grp):2d}  (win={wins} lose={losses})  "
              f"avg_gave_back={avg_gb:+.4f}  avg_omega={avg_om:.5f}  "
              f"filter_blocks={would_block}/{len(grp)}")

    # ── Reversal deep dive ─────────────────────────────────────────────────────
    reversals = by_pattern.get("REVERSAL", [])
    if reversals:
        print(f"\n  REVERSAL deep-dive ({len(reversals)} segments):")
        print(f"  These segments were profitable in the first half (right direction)")
        print(f"  then reversed in the second half.")
        print()
        for s in reversals:
            pct_returned = s["gave_back"] / s["peak_gain"] * 100 if s["peak_gain"] > 0 else 0
            print(f"    {str(s['start']):20s} → {str(s['end']):20s}")
            print(f"      Peak gain: {s['peak_gain']:+.2%}   Total: {s['total_pnl']:+.2%}   Gave back: {pct_returned:.0f}% of peak")
            print(f"      H1={s['h1_pnl']:+.4f}  H2={s['h2_pnl']:+.4f}  skew={s['pnl_skew']:+.2f}")
            print(f"      Omega at entry = {s['omega_start']:.5f}  → filter would {'BLOCK' if s['filter_blocks'] else 'not block'}")
            print(f"      Weights: BTC={s['w_btc']:+.3f}  ETH={s['w_eth']:+.3f}  SOL={s['w_sol']:+.3f}")
            print()

    print("  FILTER EFFECTIVENESS (Omega >= 0.02):")
    total_segs = len(segs)
    blocked    = [s for s in segs if s["filter_blocks"]]
    blocked_L  = [s for s in blocked if s["label"] == "LOSE"]
    blocked_W  = [s for s in blocked if s["label"] == "WIN"]
    passed     = [s for s in segs if not s["filter_blocks"]]
    passed_W   = [s for s in passed if s["label"] == "WIN"]
    passed_L   = [s for s in passed if s["label"] == "LOSE"]
    print(f"    Total segments    : {total_segs}")
    print(f"    BLOCKED : {len(blocked)}  (losers={len(blocked_L)} winners={len(blocked_W)})   false-positives={len(blocked_W)}")
    print(f"    PASSED  : {len(passed)}  (winners={len(passed_W)} losers={len(passed_L)})   false-negatives={len(passed_L)}")
    print(f"    Precision (blocks are losers): {100*len(blocked_L)/max(1,len(blocked)):.0f}%")
    print(f"    Recall (losers caught)        : {100*len(blocked_L)/max(1,sum(1 for s in segs if s['label']=='LOSE')):.0f}%")


if __name__ == "__main__":
    import time
    t0 = time.time()
    print("Loading market data...")
    for var in VARIANTS:
        run_direction_analysis(var)
    print(f"\nDone in {time.time()-t0:.0f}s")
