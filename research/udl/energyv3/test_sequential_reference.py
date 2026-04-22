#!/usr/bin/env python3
"""
Test: fit_sequential() — The Natural Way
==========================================
Just take the first few quarters of data. All we track is divergence
from the normal distribution at the start.

  cg.fit_sequential(X_full)   # first W rows = "normal"
  scores = cg.score(X_full)   # divergence from normal

No searching, no sliding window.  Sequential time ordering IS
the guarantee.

Tests:
  1. Synthetic — first 200 clean, then crisis → detect divergence
  2. TerraLuna — first ~20h = peg, rest = collapse
  3. ERCOT — first quarter = normal, then events
  4. Banks — first 8 quarters = pre-crisis baseline
"""
from __future__ import annotations
import sys, os, warnings
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from collapse_geometry import CollapseGeometry

W = 100


# ═══════════════════════════════════════════════════════════════
# A. SYNTHETIC — clean start, then divergence
# ═══════════════════════════════════════════════════════════════

def test_sequential_synthetic():
    print("=" * W)
    print("  A. SEQUENTIAL — SYNTHETIC")
    print("=" * W)

    rng = np.random.default_rng(42)
    d = 5
    T = 500

    # [0:200) normal  [200:500) crisis (shifted + inflated)
    X = rng.standard_normal((T, d))
    X[200:] = X[200:] * 5 + 3

    cg = CollapseGeometry()
    cg.fit_sequential(X, n_ref=200, verbose=True)

    scores = cg.score(X)
    ref_mean = float(scores[:200].mean())
    ref_p90 = float(np.percentile(scores[:200], 90))
    crisis_mean = float(scores[200:].mean())

    print(f"\n  Reference [0:200]: mean={ref_mean:.4f}, p90={ref_p90:.4f}")
    print(f"  Crisis [200:500]:  mean score = {crisis_mean:.4f}")

    # Reference: *mean* should be low.  Max can be high (tail of 200 draws).
    # Crisis: mean should be much higher than reference mean.
    assert ref_mean < 0.5, f"Reference mean should be low, got {ref_mean:.4f}"
    assert crisis_mean > 0.8, f"Crisis should diverge strongly, got {crisis_mean:.4f}"
    assert crisis_mean > ref_mean + 0.3, \
        f"Crisis ({crisis_mean:.3f}) should clearly exceed ref ({ref_mean:.3f})"
    assert cg._ref_start == 0
    assert cg._ref_end == 200
    assert cg._ref_validation['n_passed'] >= 4

    print(f"  ✓ Sequential: ref [0:{cg._ref_end}] "
          f"({cg._ref_validation['n_passed']}/5), "
          f"crisis detected (mean={crisis_mean:.3f})")
    return True


# ═══════════════════════════════════════════════════════════════
# B. TERRA/LUNA — first hours are peg
# ═══════════════════════════════════════════════════════════════

def build_terra_features():
    UST_PRICE = {
        0:1.000, 6:0.999, 12:0.998, 18:0.997, 21:0.995,
        22:0.990, 23:0.985,
        24:0.980, 27:0.975, 30:0.985, 33:0.990, 36:0.975,
        40:0.950, 44:0.920, 47:0.900,
        48:0.800, 50:0.700, 52:0.600, 54:0.500, 56:0.400,
        60:0.350, 64:0.400, 68:0.350, 71:0.300,
        72:0.280, 76:0.250, 80:0.220, 84:0.200, 88:0.180,
        92:0.150, 95:0.120,
        96:0.150, 100:0.180, 104:0.120, 108:0.100, 112:0.080,
        116:0.060, 119:0.050,
        120:0.060, 124:0.050, 128:0.040, 132:0.030, 136:0.025,
        140:0.020, 143:0.020,
        144:0.020, 148:0.020, 152:0.015, 156:0.015, 160:0.010,
        164:0.010, 168:0.010,
    }
    LUNA_PRICE = {
        0:77.0, 6:76.0, 12:75.0, 18:73.0, 22:70.0, 23:68.0,
        24:65.0, 30:62.0, 36:55.0, 40:50.0, 44:42.0, 47:35.0,
        48:30.0, 52:25.0, 56:20.0, 60:17.0, 64:18.0, 68:15.0, 71:12.0,
        72:10.0, 76:8.0, 80:6.0, 84:4.0, 88:3.0, 92:2.0, 95:1.0,
        96:7.0, 100:3.0, 104:0.50, 108:0.10, 112:0.01, 116:0.001,
        119:0.0002,
        120:0.0001, 124:5e-5, 128:3e-5, 132:2e-5, 136:2e-5,
        140:1e-5, 143:1e-5,
        144:1e-5, 148:1e-5, 152:1e-5, 156:1e-5, 160:1e-5,
        164:1e-5, 168:1e-5,
    }

    def interp(d, n=169):
        h = sorted(d.keys()); v = [d[k] for k in h]
        return np.interp(np.arange(n), h, v)

    ust = interp(UST_PRICE)
    luna = interp(LUNA_PRICE)
    T = len(ust)
    depeg = (1.0 - ust) * 100.0
    luna_safe = np.maximum(luna, 1e-10)
    luna_log = np.log(luna_safe / luna_safe[0])
    depeg_rate = np.zeros(T); depeg_rate[1:] = np.diff(depeg)
    luna_rate = np.zeros(T); luna_rate[1:] = np.diff(luna_log)
    vol_6h = np.zeros(T)
    for t in range(6, T):
        vol_6h[t] = np.std(depeg_rate[t-6:t])
    return np.column_stack([depeg, luna_log, depeg_rate, luna_rate, vol_6h])


def test_sequential_terra():
    print("\n" + "=" * W)
    print("  B. SEQUENTIAL — TERRA/LUNA")
    print("=" * W)

    X = build_terra_features()
    T, d = X.shape
    print(f"  Timeline: {T} hours, {d} features")

    # Natural pattern: first ~20 hours are peg period
    # n_ref = 15 (= 3d) is the minimum for 5D geometry
    cg = CollapseGeometry()
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        cg.fit_sequential(X, n_ref=15, verbose=True)

    print(f"\n  Reference: [0:{cg._ref_end}] "
          f"({cg._ref_validation['n_passed']}/5)")

    scores = cg.score(X)
    S_f = cg.score_with_friction(X)

    # The pre-attack window IS short and may not pass all 5 tests
    # — that's honest.  But detection should still work.

    # Find first hour where friction score > 0.5
    alarm_hours = np.where(S_f > 0.5)[0]
    first_alarm = int(alarm_hours[0]) if len(alarm_hours) > 0 else -1

    # Death spiral detection
    crisis_max = float(scores[24:72].max())

    print(f"\n  Friction score trajectory:")
    for h in [0, 10, 18, 20, 22, 24, 30, 48, 72, 96, 120]:
        if h < T:
            print(f"    h={h:3d}: S={scores[h]:.4f}  S_f={S_f[h]:.4f}")

    print(f"\n  First S_f alarm (>0.5): hour {first_alarm}")
    print(f"  Crisis [24:72] max score: {crisis_max:.4f}")

    # The short reference window means geometry is noisy,
    # but the collapse signal is SO strong it still shows
    assert crisis_max > 0.7, \
        f"Should detect death spiral even with short ref, got {crisis_max:.4f}"
    assert cg._ref_start == 0, "Sequential always starts at 0"

    print(f"\n  ✓ Terra/Luna sequential: collapse detected "
          f"(crisis max={crisis_max:.4f})")
    print(f"    Validation: {cg._ref_validation['n_passed']}/5 — "
          f"{'honest: short window limits geometry' if cg._ref_validation['n_passed'] < 5 else 'clean'}")
    return True


# ═══════════════════════════════════════════════════════════════
# C. ERCOT — first quarter = baseline
# ═══════════════════════════════════════════════════════════════

def test_sequential_ercot():
    print("\n" + "=" * W)
    print("  C. SEQUENTIAL — ERCOT")
    print("=" * W)

    data_dir = os.path.join(os.path.dirname(__file__), 'data', 'ercot')
    demand_path = os.path.join(data_dir, 'ercot_demand_hourly.npz')
    supply_path = os.path.join(data_dir, 'ercot_supply_hourly.npz')

    if not os.path.exists(demand_path):
        print("  [SKIP] ERCOT data not found")
        return True

    demand = np.load(demand_path)['data']
    supply = np.load(supply_path)['data']

    n_full_days = len(demand) // 24
    demand_daily = demand[:n_full_days*24].reshape(n_full_days, 24, -1).mean(axis=1)
    supply_daily = supply[:n_full_days*24].reshape(n_full_days, 24, -1).mean(axis=1)
    X_daily = np.hstack([demand_daily, supply_daily])
    T, d = X_daily.shape

    print(f"  Timeline: {T} days, {d} features (2019-2022)")

    # Natural: first 90 days (Jan-Mar 2019) = baseline
    cg = CollapseGeometry()
    cg.fit_sequential(X_daily, n_ref=90, verbose=True)

    print(f"\n  Reference: [0:{cg._ref_end}] "
          f"({cg._ref_validation['n_passed']}/5)")

    scores = cg.score(X_daily)

    # Key events (approximate days from 2019-01-01)
    events = {
        'WinterStormUri_2021': (395, 410),  # Feb 2021
        'COVID_2020': (60+365, 120+365),    # Mar-May 2020
    }

    print(f"\n  Event detection:")
    for name, (start, end) in events.items():
        if end <= T:
            peak = float(scores[start:end].max())
            print(f"    {name}: peak score = {peak:.4f}")

    uri_peak = float(scores[395:410].max()) if 410 <= T else 0
    assert uri_peak > 0.8, \
        f"Should detect Uri with first-quarter ref, got {uri_peak:.4f}"
    assert cg._ref_start == 0
    assert cg._ref_validation['n_passed'] >= 3

    print(f"\n  ✓ ERCOT sequential: Uri peak={uri_peak:.4f}, "
          f"ref validated ({cg._ref_validation['n_passed']}/5)")
    return True


# ═══════════════════════════════════════════════════════════════
# D. AUTO-GROW — reference too short → grows until valid
# ═══════════════════════════════════════════════════════════════

def test_sequential_grow():
    print("\n" + "=" * W)
    print("  D. AUTO-GROW — reference extends until valid")
    print("=" * W)

    rng = np.random.default_rng(77)
    d = 4
    T = 400

    # First 400 obs are all clean, but start with n_ref=10 (too few)
    X = rng.standard_normal((T, d))

    cg = CollapseGeometry()
    cg.fit_sequential(X, n_ref=10, min_pass=4, verbose=True)

    print(f"\n  Requested n_ref=10, got [0:{cg._ref_end}]")
    print(f"  Validation: {cg._ref_validation['n_passed']}/5")

    # Should have grown beyond 10 to get stable geometry
    assert cg._ref_end >= 12, \
        f"Should grow from 10, got {cg._ref_end}"
    assert cg._ref_validation['n_passed'] >= 4, \
        f"Should achieve ≥4/5, got {cg._ref_validation['n_passed']}"

    print(f"  ✓ Auto-grew from 10 to {cg._ref_end} observations")
    return True


# ═══════════════════════════════════════════════════════════════
# E. COMPARISON — sequential vs fit_auto (same result, simpler)
# ═══════════════════════════════════════════════════════════════

def test_sequential_vs_auto():
    print("\n" + "=" * W)
    print("  E. COMPARISON — sequential vs fit_auto")
    print("=" * W)

    rng = np.random.default_rng(42)
    d = 5
    T = 500

    # [0:200) normal, [200:500) crisis
    X = rng.standard_normal((T, d))
    X[200:] = X[200:] * 5 + 3

    # Sequential: one line
    cg_seq = CollapseGeometry()
    cg_seq.fit_sequential(X, n_ref=200)
    scores_seq = cg_seq.score(X)

    # fit_auto: heavier
    cg_auto = CollapseGeometry()
    cg_auto.fit_auto(X, min_window=50, max_window=200)
    scores_auto = cg_auto.score(X)

    # Both should detect the crisis
    seq_crisis = float(scores_seq[200:].mean())
    auto_crisis = float(scores_auto[200:].mean())

    print(f"  Sequential:  ref=[0:{cg_seq._ref_end}], "
          f"crisis mean={seq_crisis:.4f}")
    print(f"  fit_auto:    ref=[{cg_auto._ref_start}:{cg_auto._ref_end}], "
          f"crisis mean={auto_crisis:.4f}")

    assert seq_crisis > 0.8, f"Sequential should detect, got {seq_crisis:.4f}"
    assert auto_crisis > 0.8, f"Auto should detect, got {auto_crisis:.4f}"

    # Correlation between the two score trajectories
    corr = float(np.corrcoef(scores_seq, scores_auto)[0, 1])
    print(f"  Score correlation: {corr:.4f}")

    assert corr > 0.8, f"Both methods should agree, correlation {corr:.4f}"

    print(f"\n  ✓ Sequential matches fit_auto (r={corr:.4f}), "
          f"but uses one line, no search")
    return True


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    np.set_printoptions(precision=4, suppress=True)
    results = {}

    for name, fn in [
        ("Sequential_synthetic", test_sequential_synthetic),
        ("Sequential_terra_luna", test_sequential_terra),
        ("Sequential_ercot", test_sequential_ercot),
        ("Sequential_auto_grow", test_sequential_grow),
        ("Sequential_vs_auto", test_sequential_vs_auto),
    ]:
        try:
            passed = fn()
            results[name] = "PASS" if passed else "FAIL"
        except Exception as e:
            results[name] = f"FAIL: {e}"
            import traceback
            traceback.print_exc()

    print("\n" + "=" * W)
    print("  SUMMARY")
    print("=" * W)
    n_pass = sum(1 for v in results.values() if v == "PASS")
    for name, status in results.items():
        icon = "✓" if status == "PASS" else "✗"
        print(f"  {icon} {name}: {status}")
    print(f"\n  {n_pass}/{len(results)} tests passed")
    print("=" * W)

    assert n_pass >= 4, f"Expected ≥4/5 passes, got {n_pass}"


if __name__ == "__main__":
    main()
