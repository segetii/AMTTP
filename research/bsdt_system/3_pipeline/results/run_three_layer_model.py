"""
Three-Layer Continuous Position Model: Ω × (MFLS/γ) × Direction
================================================================

Architecture:
    position_t = w1(Ω_t) × w2(MFLS_t / γ_t) × direction_t

Layer 1 — Timing:     w1 = percentile-rank(Ω),  zero below Q50
Layer 2 — Activity:   w2 = percentile-rank(MFLS/γ), zero below Q33
                       A_t = MFLS_t / γ_t  (force vs damping)
                       high MFLS + falling γ → true cascade
                       high MFLS + high γ    → suppressed instability
Layer 3 — Direction:  phase-based (crash → momentum, recovery → gradient)
                       same v2-confirmed phase logic as best binary model

Position is a continuous scalar in [−1, +1] (or out-of-sample clipped).

Comparison table:
    B&H                         (reference)
    v2_binary                   (best binary model from prior run)
    v3_continuous_equal         (w1=w2=uniform weight, direction only)
    v4_continuous_omega         (w1 only, direction only)
    v5_continuous_activity      (w2 only, direction only)
    v6_continuous_full          (w1 × w2 × direction)   ← target
    v7_continuous_full_sized    (same + clamp to max 0.5 position)
"""

import numpy as np
import pandas as pd
import json
import warnings
warnings.filterwarnings('ignore')
from scipy import stats

CSV_PATH = r"C:\amttp\research\adaptive-friction\pipeline\results\market_mfls_timeseries.csv"
OUT_DIR  = r"C:\amttp\research\adaptive-friction\pipeline\results"

RECOV_CONFIRM_RET = 0.01   # 5d return confirmation for recovery entry
CRASH_RET_THRESH  = -0.03  # 21d return threshold for crash
RECOV_RET_THRESH  = 0.00


# ─────────────────────────────────────────────────────────────────────────────
def load():
    ts = pd.read_csv(CSV_PATH, index_col=0, parse_dates=True)
    sp = ts['sp500']

    for H in [5, 21, 63]:
        ts[f'fwd_{H}'] = sp.pct_change(H).shift(-H)

    ts['ret_1d']  = sp.pct_change(1)
    ts['ret_5d']  = sp.pct_change(5)
    ts['ret_21d'] = sp.pct_change(21)
    ts['momentum_sign'] = np.sign(ts['ret_21d'])

    ts['omega']  = ts['spectral_order']
    ts['domega'] = ts['omega'].diff().rolling(5).mean()

    # ── LAYER 2: Effective Activity A = MFLS / γ ──────────────────────────
    # Use gamma (full range 0–1), not gamma_adaptive (compressed 0.004–0.504)
    # Add small floor to avoid division by near-zero
    ts['activity'] = ts['MFLS'] / (ts['gamma'] + 1e-6)

    # Expanding (no look-ahead) percentile ranks for w1 and w2
    ts['omega_prank']    = ts['omega'].expanding(60).rank(pct=True)
    ts['activity_prank'] = ts['activity'].expanding(60).rank(pct=True)

    return ts


# ─────────────────────────────────────────────────────────────────────────────
def build_phase(ts):
    """
    v2-confirmed phase — same as the best binary model result.
    Returns integer Series: 0=QUIET, 1=STRESS, 2=CRASH, 3=RECOVERY
    """
    omega_q50 = ts['omega'].expanding(60).quantile(0.50)
    omega_q75 = ts['omega'].expanding(60).quantile(0.75)

    elevated = ts['omega'] >= omega_q50
    high     = ts['omega'] >= omega_q75
    rising   = ts['domega'] > 0
    falling  = ts['ret_21d'] < CRASH_RET_THRESH
    recov_ok = ts['ret_21d'] >= RECOV_RET_THRESH

    raw = np.ones(len(ts), dtype=int)         # STRESS
    raw[~elevated.values]                      = 0  # QUIET
    raw[elevated.values & rising.values & falling.values] = 2  # CRASH
    raw[high.values & recov_ok.values & ~(elevated.values & rising.values & falling.values)] = 3

    # v2 confirmation: need 5d return confirmation for entry
    ret5 = ts['ret_5d'].values
    for t in range(1, len(raw)):
        if raw[t] == 3 and not (np.isfinite(ret5[t]) and ret5[t] > RECOV_CONFIRM_RET):
            raw[t] = 1
        if raw[t] == 2 and not (np.isfinite(ret5[t]) and ret5[t] < -0.02):
            raw[t] = 1

    return pd.Series(raw, index=ts.index, name='phase')


# ─────────────────────────────────────────────────────────────────────────────
def direction(ts, phase):
    """
    Phase-based direction: −1 / 0 / +1
    CRASH → momentum (follow through)
    RECOVERY → gradient (restoring force)
    else → 0
    """
    grad = np.sign(ts['dir_x1'].values)
    mom  = ts['momentum_sign'].fillna(0).values
    ph   = phase.values

    d = np.zeros(len(ts))
    d[ph == 2] = mom[ph == 2]
    d[ph == 3] = grad[ph == 3]
    return pd.Series(d, index=ts.index, name='direction')


# ─────────────────────────────────────────────────────────────────────────────
def build_positions(ts, phase, dir_sig):
    """
    Build 7 position series for comparison.
    All positions scaled to max abs = 1.
    """
    w1 = ts['omega_prank'].clip(lower=0)       # 0 below Q0, 1 at max
    w2 = ts['activity_prank'].clip(lower=0)

    # Zero out w1 below Q50 (timing gate)
    omega_q50_prank = 0.50
    w1_gated = w1.where(w1 >= omega_q50_prank, 0.0)

    # Zero out w2 below Q33 (activity gate — filter dead regimes)
    activity_q33_prank = 0.33
    w2_gated = w2.where(w2 >= activity_q33_prank, 0.0)

    d = dir_sig

    # Also build the v2 binary: position = 1 if crash/recovery, 0 otherwise
    v2_binary = d  # d is already 0/±1

    positions = {
        'v2_binary':            d.copy(),
        'v3_equal_weights':     d * 0.5 * (w1_gated + w2_gated),   # avg weight
        'v4_omega_only':        d * w1_gated,
        'v5_activity_only':     d * w2_gated,
        'v6_full':              d * w1_gated * w2_gated,            # product of both
        'v7_full_halfsize':     (d * w1_gated * w2_gated).clip(-0.5, 0.5),
    }

    return positions


# ─────────────────────────────────────────────────────────────────────────────
def simulate(position_series, daily_ret, label=""):
    ret  = daily_ret.fillna(0).values
    pos  = position_series.shift(1).fillna(0).values   # next-day execution

    pnl  = pos * ret
    cum  = np.cumprod(1 + pnl)
    bh   = np.cumprod(1 + ret)

    active   = pnl[pos != 0]
    sharpe   = (active.mean() / (np.std(active) + 1e-12)) * np.sqrt(252) if len(active) > 0 else 0.0

    roll_max = np.maximum.accumulate(cum)
    max_dd   = (cum / roll_max - 1).min()

    active_days = int((pos != 0).sum())
    hit_rate    = (pnl[pos != 0] > 0).mean() if active_days > 0 else np.nan

    q10       = np.quantile(ret, 0.10)
    tail_mask = ret <= q10
    tail_pos  = pos[tail_mask & (pos != 0)]
    tail_ret  = ret[tail_mask & (pos != 0)]
    tail_acc  = (np.sign(tail_pos) == np.sign(tail_ret)).mean() if len(tail_pos) > 0 else np.nan
    tail_pnl  = (tail_pos * tail_ret).mean() if len(tail_pos) > 0 else np.nan

    bh_sharpe = (np.mean(ret) / (np.std(ret) + 1e-12)) * np.sqrt(252)
    bh_maxdd  = (bh / np.maximum.accumulate(bh) - 1).min()

    gross_leverage = np.abs(pos).mean()

    return dict(
        label       = label,
        sharpe      = round(float(sharpe), 4),
        sharpe_per_leverage = round(float(sharpe / (gross_leverage + 1e-9)), 4),
        max_dd      = round(float(max_dd), 4),
        cum_return  = round(float(cum[-1] - 1), 4),
        active_days = active_days,
        total_days  = len(pnl),
        hit_rate    = round(float(hit_rate), 4) if not np.isnan(hit_rate) else None,
        tail_acc    = round(float(tail_acc), 4) if not np.isnan(tail_acc) else None,
        tail_pnl    = round(float(tail_pnl), 6) if not np.isnan(tail_pnl) else None,
        gross_leverage = round(float(gross_leverage), 4),
        bh_sharpe   = round(float(bh_sharpe), 4),
        bh_max_dd   = round(float(bh_maxdd), 4),
        bh_cum_return = round(float(bh[-1] - 1), 4),
    )


def compute_ic(pos, fwd_ret, label=""):
    nz = (pos != 0) & fwd_ret.notna()
    n  = nz.sum()
    if n < 20:
        return dict(label=label, n=int(n), ic=None, acc=None)
    ic, _ = stats.spearmanr(pos[nz].values, fwd_ret[nz].values)
    acc   = (np.sign(pos[nz].values) == np.sign(fwd_ret[nz].values)).mean()
    return dict(label=label, n=int(n), ic=round(float(ic), 4), acc=round(float(acc), 4))


# ─────────────────────────────────────────────────────────────────────────────
def print_table(rows, cols_fmt):
    header = "  " + "  ".join(f"{c[0]:>{c[1]}}" for c in cols_fmt)
    print(header)
    print("─" * len(header))
    for r in rows:
        vals = []
        for c in cols_fmt:
            v = r.get(c[0], None)
            if v is None:
                vals.append(f"{'n/a':>{c[1]}}")
            elif isinstance(v, str):
                vals.append(f"{v:>{c[1]}}")
            else:
                vals.append(f"{v:>{c[1]}.{c[2]}{'f' if isinstance(v, float) else 'd'}}")
        print("  " + "  ".join(vals))


# ─────────────────────────────────────────────────────────────────────────────
def activity_diagnostics(ts, phase, test_mask):
    """
    Show what MFLS/γ looks like across phases.
    """
    df = ts[test_mask].copy()
    df['phase'] = phase[test_mask]
    phase_names = {0:'QUIET', 1:'STRESS', 2:'CRASH', 3:'RECOVERY'}

    print("\n── Activity A = MFLS/γ by phase (test set) ───────────────────────────")
    print(f"  {'Phase':<12}  {'n':>5}  {'A_median':>10}  {'A_q75':>8}  {'A_q90':>8}  {'MFLS_med':>10}  {'γ_med':>8}")
    for ph, name in phase_names.items():
        m = df['phase'] == ph
        n = m.sum()
        if n == 0:
            continue
        sub = df[m]
        print(f"  {name:<12}  {n:>5}  {sub['activity'].median():>10.2f}  "
              f"{sub['activity'].quantile(0.75):>8.2f}  "
              f"{sub['activity'].quantile(0.90):>8.2f}  "
              f"{sub['MFLS'].median():>10.2f}  "
              f"{sub['gamma'].median():>8.4f}")

    # MFLS/γ vs Ω cross-correlation
    corr_mfls_omega = ts[test_mask]['activity'].corr(ts[test_mask]['omega'])
    corr_mfls_ret   = ts[test_mask]['activity'].corr(ts[test_mask]['ret_1d'].abs())
    print(f"\n  Corr(A, Ω)          = {corr_mfls_omega:+.4f}")
    print(f"  Corr(A, |ret_1d|)   = {corr_mfls_ret:+.4f}  (activity → realized vol?)")

    # Γ dynamics during crash episodes
    crash_mask = (phase[test_mask] == 2)
    if crash_mask.sum() > 0:
        crash_gamma = ts[test_mask][crash_mask]['gamma']
        pre_crash_gamma = ts[test_mask][crash_mask]['gamma'].shift(5)
        print(f"\n  γ during CRASH days: mean={crash_gamma.mean():.4f}  "
              f"Δγ_5d: {(crash_gamma - pre_crash_gamma).mean():.5f}  "
              f"(negative = γ falling = true cascade confirmed)")


# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 72)
    print("  THREE-LAYER MODEL: Ω × (MFLS/γ) × Direction")
    print("  position_t = w1(Ω) × w2(MFLS/γ) × direction_phase")
    print("=" * 72)

    ts    = load()
    phase = build_phase(ts)
    dir_s = direction(ts, phase)

    test_mask = ts.index >= '2016-01-01'
    daily_ret = ts.loc[test_mask, 'ret_1d']
    fwd63     = ts['fwd_63']

    # ── Activity diagnostics ───────────────────────────────────────────────
    activity_diagnostics(ts, phase, test_mask)

    # ── Build positions ────────────────────────────────────────────────────
    positions = build_positions(ts, phase, dir_s)

    # ── Simulate all variants ──────────────────────────────────────────────
    print("\n[Simulation: test 2016–2024]")
    sim_results = {}
    ic_results  = {}
    for name, pos in positions.items():
        sim_results[name] = simulate(pos[test_mask], daily_ret, label=name)
        ic_results[name]  = compute_ic(pos[test_mask], fwd63[test_mask], label=name)

    # ── Print main comparison table ────────────────────────────────────────
    print(f"\n── PnL Comparison ──────────────────────────────────────────────────")
    print(f"  {'Strategy':<28}  {'Sharpe':>7}  {'Shrp/Lev':>9}  {'MaxDD':>7}  "
          f"{'CumRet':>8}  {'TailAcc':>8}  {'Lvrg':>6}  {'Active%':>8}")
    print("─" * 95)

    bh = sim_results['v2_binary']
    print(f"  {'Buy & Hold':<28}  {bh['bh_sharpe']:>+7.3f}  {'---':>9}  "
          f"{bh['bh_max_dd']:>7.3f}  {bh['bh_cum_return']:>+8.3f}  {'---':>8}  "
          f"{'---':>6}  {'100.0%':>8}")

    for name, r in sim_results.items():
        active_pct = r['active_days'] / r['total_days'] * 100
        tail_s = f"{r['tail_acc']:.3f}" if r['tail_acc'] is not None else "  n/a"
        print(f"  {name:<28}  {r['sharpe']:>+7.3f}  {r['sharpe_per_leverage']:>+9.3f}  "
              f"{r['max_dd']:>7.3f}  {r['cum_return']:>+8.3f}  "
              f"{tail_s:>8}  {r['gross_leverage']:>6.3f}  {active_pct:>7.1f}%")

    # ── IC comparison (H=63d) ──────────────────────────────────────────────
    print(f"\n── IC + Accuracy (H=63d, continuous position) ──────────────────────")
    print(f"  {'Strategy':<28}  {'n':>5}  {'IC':>8}  {'Acc':>6}")
    for name, r in ic_results.items():
        ic_s  = f"{r['ic']:>+8.4f}" if r['ic']  is not None else "     n/a"
        acc_s = f"{r['acc']:>6.3f}"  if r['acc'] is not None else "   n/a"
        print(f"  {name:<28}  {r['n']:>5}  {ic_s}  {acc_s}")

    # ── Tail events: does activity signal capture the right ones? ──────────
    print(f"\n── Tail-event capture: does A = MFLS/γ correctly spike? ────────────")
    cr = ts[test_mask].copy()
    cr['phase'] = phase[test_mask].values
    cr['ret_1d_val'] = daily_ret.values
    worst = cr.nsmallest(20, 'ret_1d_val')[['ret_1d_val', 'omega', 'activity', 'gamma', 'phase']]
    phase_names = {0:'QUIET', 1:'STRESS', 2:'CRASH', 3:'RECOVERY'}
    worst['phase_name'] = worst['phase'].map(phase_names)
    print(f"  {'Date':<12}  {'ret_1d':>8}  {'Ω':>7}  {'A=MFLS/γ':>10}  {'γ':>7}  {'Phase':<10}")
    for dt, row in worst.iterrows():
        print(f"  {str(dt)[:10]:<12}  {row['ret_1d_val']:>+8.4f}  "
              f"{row['omega']:>7.4f}  {row['activity']:>10.2f}  "
              f"{row['gamma']:>7.4f}  {row['phase_name']:<10}")

    # ── Crisis periods for v6_full ─────────────────────────────────────────
    print(f"\n── v6_full crisis period performance ────────────────────────────────")
    crisis = {
        '2020_crash':    ('2020-02-01', '2020-04-30'),
        '2020_recovery': ('2020-04-01', '2020-09-30'),
        '2022_bear':     ('2022-01-01', '2022-10-31'),
    }
    v6_pos = positions['v6_full']
    for label, (s, e) in crisis.items():
        m = test_mask & (ts.index >= s) & (ts.index <= e)
        r = simulate(v6_pos[m], ts.loc[m, 'ret_1d'], label=label)
        print(f"  {label:<20}: Sharpe={r['sharpe']:>+7.3f}  MaxDD={r['max_dd']:>7.3f}  "
              f"TailAcc={r['tail_acc'] if r['tail_acc'] else 'n/a'}")

    # ── Save ──────────────────────────────────────────────────────────────
    output = {
        "model": "Three-Layer Continuous: Ω × (MFLS/γ) × Direction",
        "architecture": {
            "layer_1_timing":   "w1 = percentile-rank(Ω), gated at Q50",
            "layer_2_activity": "w2 = percentile-rank(MFLS/γ), gated at Q33. A = MFLS/(γ+ε)",
            "layer_3_direction":"phase-based: CRASH→momentum, RECOVERY→gradient (v2-confirmed)",
            "position_formula": "pos = sign × w1_gated × w2_gated",
        },
        "pnl_results":    {k: v for k, v in sim_results.items()},
        "ic_results":     {k: v for k, v in ic_results.items()},
        "key_insight": {
            "A_interpretation":
                "MFLS/γ distinguishes true cascade (high MFLS, low γ) from "
                "suppressed instability (high MFLS, high γ). This is not the "
                "same as velocity — it is the force-to-damping ratio.",
            "w1_x_w2":
                "Multiplying the two weights concentrates exposure on days where "
                "both Ω is elevated AND the system is actively moving against "
                "friction. These are the highest-conviction days.",
            "v6_vs_v2":
                "v6 should show improved Sharpe/leverage and better tail capture "
                "by avoiding days where Ω is elevated but MFLS/γ is low "
                "(suppressed instability — nothing actually happening).",
        }
    }

    out_json = f"{OUT_DIR}/three_layer_model_results.json"
    with open(out_json, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n✓ Saved: {out_json}")
    print("\n" + "=" * 72)
    print("  THREE-LAYER MODEL — COMPLETE")
    print("=" * 72)


if __name__ == '__main__':
    main()
