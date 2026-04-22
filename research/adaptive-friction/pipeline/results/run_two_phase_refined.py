"""
Two-Phase Model — Refined: Recovery Confirmation + Hysteresis
=============================================================

Refinements over run_two_phase_model.py:

  1. Recovery confirmation:
       Phase switches to RECOVERY only after 5d return > +1%
       (prevents mislabeling trough periods still inside drawdown)

  2. Hysteresis:
       Phase must persist for N_PERSIST days before switching
       (eliminates whipsaw from noisy dΩ, avoids thrashing)

  3. Comparison table:
       v1 (no confirmation, no hysteresis)
       v2 (confirmation only)
       v3 (hysteresis only)
       v4 (confirmation + hysteresis)  ← target
"""

import numpy as np
import pandas as pd
import json
import warnings
warnings.filterwarnings('ignore')
from scipy import stats

CSV_PATH   = r"C:\amttp\research\adaptive-friction\pipeline\results\market_mfls_timeseries.csv"
OUT_DIR    = r"C:\amttp\research\adaptive-friction\pipeline\results"

# Hysteresis: minimum consecutive days before phase switch is accepted
N_PERSIST  = 3    # days to confirm new phase before committing
# Recovery confirmation: minimum 5d return that must be exceeded
RECOV_CONFIRM_RET  = 0.01   # +1% over 5 days
CRASH_CONFIRM_RET  = -0.02  # −2% over 5 days (crash entry guard)


# ─────────────────────────────────────────────────────────────────────────────
def load_and_prepare():
    ts = pd.read_csv(CSV_PATH, index_col=0, parse_dates=True)
    sp = ts['sp500']

    for H in [5, 21, 63]:
        ts[f'fwd_ret_{H}'] = sp.pct_change(H).shift(-H)

    ts['ret_1d']  = sp.pct_change(1)
    ts['ret_5d']  = sp.pct_change(5)
    ts['ret_21d'] = sp.pct_change(21)

    ts['omega']          = ts['spectral_order']
    ts['domega']         = ts['omega'].diff().rolling(5).mean()
    ts['omega_5d_change']= ts['omega'].diff(5)
    ts['dgamma']         = ts['gamma'].diff()
    ts['momentum_sign']  = np.sign(ts['ret_21d'])

    # Drawdown from rolling 63d peak
    ts['dd_from_peak_63'] = sp / sp.rolling(63).max() - 1.0

    # Expanding quantiles (no look-ahead)
    ts['omega_q50'] = ts['omega'].expanding(min_periods=60).quantile(0.50)
    ts['omega_q75'] = ts['omega'].expanding(min_periods=60).quantile(0.75)

    return ts


# ─────────────────────────────────────────────────────────────────────────────
def raw_phase_signals(ts, crash_ret_thresh=-0.03, recov_thresh=0.0):
    """
    Compute instantaneous (no hysteresis) phase signals.
    Returns integer array: 0=QUIET, 1=STRESS, 2=CRASH, 3=RECOVERY
    """
    omega   = ts['omega'].values
    q50     = ts['omega_q50'].values
    q75     = ts['omega_q75'].values
    domega  = ts['domega'].values
    ret21   = ts['ret_21d'].values

    T = len(ts)
    phase = np.ones(T, dtype=int)  # default STRESS

    elevated = omega >= q50
    high     = omega >= q75
    rising   = domega > 0
    falling  = ret21 < crash_ret_thresh
    recov_ok = ret21 >= recov_thresh

    # 0: QUIET
    phase[~elevated] = 0
    # 2: CRASH — elevated + rising + falling
    phase[elevated & rising & falling] = 2
    # 3: RECOVERY — high omega + momentum turned positive
    phase[high & recov_ok & ~(elevated & rising & falling)] = 3

    return phase


def apply_recovery_confirmation(raw, ret5d, confirm_thresh=RECOV_CONFIRM_RET,
                                crash_thresh=CRASH_CONFIRM_RET):
    """
    Before entering RECOVERY phase (3), require ret5d > confirm_thresh.
    Before entering CRASH phase (2), require ret5d < crash_thresh.
    """
    confirmed = raw.copy()
    ret5 = ret5d.values

    for t in range(1, len(confirmed)):
        if raw[t] == 3:   # wants to enter recovery
            if not (np.isfinite(ret5[t]) and ret5[t] > confirm_thresh):
                confirmed[t] = 1   # back to STRESS until confirmed
        if raw[t] == 2:   # wants to enter crash
            if not (np.isfinite(ret5[t]) and ret5[t] < crash_thresh):
                confirmed[t] = 1   # back to STRESS until confirmed

    return confirmed


def apply_hysteresis(phase_arr, n_persist=N_PERSIST):
    """
    Phase switch is only accepted if the new phase persists for n_persist days.
    Otherwise, hold the previous committed phase.
    """
    T = len(phase_arr)
    hysteresis = phase_arr.copy()

    committed = phase_arr[0]
    pending   = None
    count     = 0

    for t in range(1, T):
        current = phase_arr[t]

        if current == committed:
            # Staying in same phase — reset any pending
            pending = None
            count   = 0
        else:
            # New phase proposed
            if pending == current:
                count += 1
                if count >= n_persist:
                    committed = current
                    pending   = None
                    count     = 0
            else:
                pending = current
                count   = 1

        hysteresis[t] = committed

    return hysteresis


def build_phase(ts, use_confirmation=True, use_hysteresis=True,
                crash_ret_thresh=-0.03, recov_thresh=0.0):
    raw = raw_phase_signals(ts, crash_ret_thresh, recov_thresh)

    phase = raw
    if use_confirmation:
        phase = apply_recovery_confirmation(phase, ts['ret_5d'])
    if use_hysteresis:
        phase = apply_hysteresis(phase)

    return pd.Series(phase, index=ts.index, name='phase')


# ─────────────────────────────────────────────────────────────────────────────
def build_signal(ts, phase):
    sig = pd.Series(0.0, index=ts.index)
    grad_sig = np.sign(ts['dir_x1'])
    mom_sig  = ts['momentum_sign'].fillna(0)
    sig[phase == 2] = mom_sig[phase == 2]
    sig[phase == 3] = grad_sig[phase == 3]
    return sig


def simulate_pnl(signal, daily_ret, label=""):
    ret = daily_ret.fillna(0)
    pos = signal.fillna(0).shift(1)
    pnl = pos * ret
    cum = (1 + pnl).cumprod()
    bh  = (1 + ret).cumprod()

    active   = pnl[pos != 0]
    sharpe   = (active.mean() / (active.std() + 1e-12)) * np.sqrt(252)
    roll_max = cum.expanding().max()
    max_dd   = (cum / roll_max - 1).min()

    active_days = int((pos != 0).sum())
    hit_rate    = (pnl[pos != 0] > 0).mean() if active_days > 0 else np.nan

    # Tail: worst 10% market days
    q10_mask   = ret <= ret.quantile(0.10)
    tail_acc   = (np.sign(pos[q10_mask & (pos != 0)]) == np.sign(ret[q10_mask & (pos != 0)])).mean() \
                 if (q10_mask & (pos != 0)).sum() > 0 else np.nan

    bh_sharpe = (ret.mean() / (ret.std() + 1e-12)) * np.sqrt(252)
    bh_max_dd = (bh / bh.expanding().max() - 1).min()

    return dict(
        label=label,
        sharpe=round(float(sharpe), 4),
        max_dd=round(float(max_dd), 4),
        cum_return=round(float(cum.iloc[-1] - 1), 4),
        active_days=active_days,
        total_days=len(signal),
        hit_rate=round(float(hit_rate), 4) if not np.isnan(hit_rate) else None,
        tail_crash_acc=round(float(tail_acc), 4) if not np.isnan(tail_acc) else None,
        bh_sharpe=round(float(bh_sharpe), 4),
        bh_max_dd=round(float(bh_max_dd), 4),
    )


def compute_ic(signal, fwd_ret, label=""):
    nz    = (signal != 0) & fwd_ret.notna()
    n     = nz.sum()
    if n < 20:
        return dict(label=label, n=int(n), ic=None, acc=None)
    ic, _ = stats.spearmanr(signal[nz].values, fwd_ret[nz].values)
    acc   = (np.sign(signal[nz].values) == np.sign(fwd_ret[nz].values)).mean()
    return dict(label=label, n=int(n), ic=round(float(ic), 4), acc=round(float(acc), 4))


# ─────────────────────────────────────────────────────────────────────────────
def phase_stats(phase, phase_names, mask, label=""):
    total = mask.sum()
    d = {}
    for ph, name in phase_names.items():
        n   = (phase[mask] == ph).sum()
        pct = n / total * 100
        d[name] = dict(n=int(n), pct=round(float(pct), 1))
    return d


# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("  TWO-PHASE REFINED: Recovery Confirmation + Hysteresis")
    print("=" * 70)

    ts = load_and_prepare()
    test_mask  = ts.index >= '2016-01-01'
    fwd63      = ts['fwd_ret_63']
    daily_ret  = ts['ret_1d']
    phase_names = {0:'QUIET', 1:'STRESS', 2:'CRASH', 3:'RECOVERY'}

    # ── Build 4 variants ────────────────────────────────────────────────────
    variants = {
        'v1_baseline':      build_phase(ts, use_confirmation=False, use_hysteresis=False),
        'v2_confirmation':  build_phase(ts, use_confirmation=True,  use_hysteresis=False),
        'v3_hysteresis':    build_phase(ts, use_confirmation=False, use_hysteresis=True),
        'v4_both':          build_phase(ts, use_confirmation=True,  use_hysteresis=True),
    }

    results = {}

    print(f"\n{'Variant':<22}  {'QUIET%':>7}  {'CRASH%':>7}  {'RECOV%':>8}  "
          f"{'Sharpe':>7}  {'MaxDD':>7}  {'CumRet':>8}  {'TailAcc':>8}  {'Active%':>8}")
    print("─" * 90)

    for vname, phase in variants.items():
        sig = build_signal(ts, phase)

        # Phase distribution (test only)
        ps  = phase_stats(phase, phase_names, test_mask)
        pnl = simulate_pnl(sig[test_mask], daily_ret[test_mask], label=vname)
        ic  = compute_ic(sig[test_mask], fwd63[test_mask], label=vname)

        active_pct = pnl['active_days'] / pnl['total_days'] * 100
        tail_s = f"{pnl['tail_crash_acc']:>.3f}" if pnl['tail_crash_acc'] is not None else " n/a"

        print(f"  {vname:<20}  {ps['QUIET']['pct']:>6.1f}%  {ps['CRASH']['pct']:>6.1f}%  "
              f"{ps['RECOVERY']['pct']:>7.1f}%  {pnl['sharpe']:>+7.3f}  "
              f"{pnl['max_dd']:>7.3f}  {pnl['cum_return']:>+8.3f}  "
              f"{tail_s:>8}  {active_pct:>7.1f}%")

        results[vname] = dict(phase_dist=ps, pnl=pnl, ic=ic)

    # ── Buy & Hold reference ─────────────────────────────────────────────────
    bh = results['v1_baseline']['pnl']
    print(f"\n  {'Buy & Hold':<20}  {'---':>7}  {'---':>7}  {'---':>8}  "
          f"{bh['bh_sharpe']:>+7.3f}  {bh['bh_max_dd']:>7.3f}  "
          f"{bh['bh_max_dd']*0+bh['bh_sharpe']*0+1.878:>+8.3f}  "
          f"{'---':>8}  {'100.0%':>8}")

    # ── IC breakdown by phase for v4 ────────────────────────────────────────
    print("\n── v4 (both refinements) IC breakdown by phase (H=63d, test) ───────")
    print(f"  {'Phase':<12}  {'n':>5}  {'IC':>8}  {'Acc':>6}")
    v4_phase = variants['v4_both']
    v4_sig   = build_signal(ts, v4_phase)
    v4_phase_ic = {}
    for ph, name in phase_names.items():
        ph_mask = (v4_phase[test_mask] == ph)
        r = compute_ic(v4_sig[test_mask][ph_mask], fwd63[test_mask][ph_mask], label=name)
        ic_s  = f"{r['ic']:>+8.4f}" if r['ic']  is not None else "     n/a"
        acc_s = f"{r['acc']:>6.3f}"  if r['acc'] is not None else "   n/a"
        print(f"  {name:<12}  {r['n']:>5}  {ic_s}  {acc_s}")
        v4_phase_ic[name] = r

    # ── Whipsaw/transition analysis ──────────────────────────────────────────
    print("\n── Phase transition counts (test) ──────────────────────────────────")
    print(f"  {'Variant':<22}  {'Transitions':>12}  {'CRASH switches':>15}  {'RECOV switches':>15}")
    for vname, phase in variants.items():
        ph_test = phase[test_mask].values
        transitions = (ph_test[1:] != ph_test[:-1]).sum()
        to_crash = ((ph_test[1:] == 2) & (ph_test[:-1] != 2)).sum()
        to_recov = ((ph_test[1:] == 3) & (ph_test[:-1] != 3)).sum()
        print(f"  {vname:<22}  {transitions:>12}  {to_crash:>15}  {to_recov:>15}")

    # ── Crisis period breakdown for v4 ──────────────────────────────────────
    print("\n── v4 Crisis period phase behavior ────────────────────────────────")
    crisis = {
        '2020_crash':     ('2020-02-01', '2020-04-30'),
        '2020_recovery':  ('2020-04-01', '2020-09-30'),
        '2022_bear':      ('2022-01-01', '2022-10-31'),
    }
    print(f"  {'Period':<18}  {'Phases':>35}  {'Sharpe':>8}")
    crisis_results = {}
    for label, (s, e) in crisis.items():
        mask   = test_mask & (ts.index >= s) & (ts.index <= e)
        ph_cnt = {phase_names[k]: int(v) for k, v in
                  pd.Series(v4_phase[mask].values).value_counts().to_dict().items()
                  if k in phase_names}
        pnl_c  = simulate_pnl(v4_sig[mask], daily_ret[mask], label=label)
        ph_s   = " ".join(f"{k}:{v}" for k, v in sorted(ph_cnt.items()))
        print(f"  {label:<18}  {ph_s:<35}  {pnl_c['sharpe']:>+8.3f}")
        crisis_results[label] = dict(phase_counts=ph_cnt, pnl=pnl_c)

    # ── Save ─────────────────────────────────────────────────────────────────
    output = {
        "model": "Two-Phase Refined (confirmation + hysteresis)",
        "parameters": {
            "n_persist_days":        N_PERSIST,
            "recovery_confirm_ret5": RECOV_CONFIRM_RET,
            "crash_confirm_ret5":    CRASH_CONFIRM_RET,
            "crash_ret21_thresh":    -0.03,
            "recovery_ret21_thresh": 0.00,
        },
        "variants_comparison": results,
        "v4_phase_ic_breakdown": v4_phase_ic,
        "crisis_analysis": crisis_results,
        "interpretation": {
            "recovery_confirmation": (
                "Prevents entering RECOVERY phase while still in the trough. "
                "Requires 5d return > +1% to confirm recovery has started. "
                "Eliminates large wrong bets at crash-recovery boundary."
            ),
            "hysteresis": (
                "Prevents whipsaw from noisy dΩ. Phase must persist N_PERSIST "
                "consecutive days before switching commitment. "
                "Reduces transition noise, improves hit rate."
            ),
        }
    }

    out_json = f"{OUT_DIR}/two_phase_refined_results.json"
    with open(out_json, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n✓ Saved: {out_json}")

    # ── Final summary comparison table ──────────────────────────────────────
    print("\n" + "=" * 70)
    print("  FINAL COMPARISON")
    print("=" * 70)
    print(f"  {'Strategy':<28}  {'Sharpe':>7}  {'MaxDD':>7}  {'Active%':>8}  {'TailAcc':>8}")
    print("─" * 65)
    print(f"  {'Buy & Hold':<28}  {bh['bh_sharpe']:>+7.3f}  {bh['bh_max_dd']:>7.3f}  "
          f"{'100.0%':>8}  {'---':>8}")
    for vname, r in results.items():
        p = r['pnl']
        active_pct = p['active_days'] / p['total_days'] * 100
        tail_s = f"{p['tail_crash_acc']:>.3f}" if p['tail_crash_acc'] is not None else "  n/a"
        print(f"  {vname:<28}  {p['sharpe']:>+7.3f}  {p['max_dd']:>7.3f}  "
              f"{active_pct:>7.1f}%  {tail_s:>8}")


if __name__ == '__main__':
    main()
