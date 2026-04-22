#!/usr/bin/env python3
"""
Physics Engine — ERCOT Hourly (n≈8760, paper Table 4 protocol)
===============================================================
Runs MolecularEngine / GravityModeEngine / HybridGravityEngine on the raw
HOURLY ERCOT data without daily aggregation, matching the paper's
reported n ≈ 8760 and AUC = 0.9940 (Table 4).

Two variants:
  1. SUPPLY-ONLY hourly (d=5)  — wind_cf, solar_cf, gas_cf, coal_cf, nuclear_cf
  2. COMBINED    hourly (d=10) — demand (5) + supply (5)

Reference window: first 8760 hours (Jan 2019 – Dec 2019)
Test window: full 35064-hour span (2019-2022).

Usage:
  py -3 -X utf8 research/udl/energyv3/test_physics_ercot_hourly.py > ercot_hourly_results.txt
"""
from __future__ import annotations
import sys, os, time, warnings, json, argparse
import numpy as np

warnings.filterwarnings("ignore")

ROOT = r"c:\amttp"
HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.join(ROOT, "research", "udl"))
sys.path.insert(0, os.path.join(ROOT, "research", "udl", "src"))
sys.path.insert(0, HERE)

from test_full_collapse_x_domains import (
    build_reps, auc_manual, clean_array,
    ERCOT_DIR,
)
from udl.system_mode import MolecularEngine, GravityModeEngine, HybridGravityEngine

W = 110
ENGINE_NAMES = ['Molecular(LJ)', 'Gravity(N-body)', 'Hybrid(Mol+Grav)']


# ─────────────────────────────────────────────────────────────────
# DATA LOADER — HOURLY (no daily aggregation)
# ─────────────────────────────────────────────────────────────────

def _load_ercot_hourly(mode="supply"):
    """Load ERCOT hourly data, returning X_ref (2019) and X_all from 2021 (n=8760).

    Paper Table 4: n=8760 refers to calendar year 2021 (non-leap year = 8760 hours),
    which contains WinterStorm Uri (Feb 10) and WinterStorm Elliott (Dec 22).
    Reference: calendar year 2019 (stable pre-crisis baseline).
    """
    if not os.path.exists(ERCOT_DIR):
        return None

    dem = np.load(os.path.join(ERCOT_DIR, "ercot_demand_hourly.npz"), allow_pickle=True)
    sup = np.load(os.path.join(ERCOT_DIR, "ercot_supply_hourly.npz"), allow_pickle=True)

    if mode == "supply":
        X = sup["X"]
        features = list(sup["feature_names"])
    elif mode == "demand":
        X = dem["X"]
        features = list(dem["feature_names"])
    else:  # combined
        X = np.column_stack([dem["X"], sup["X"]])
        features = list(dem["feature_names"]) + list(sup["feature_names"])

    dates = np.array(dem["dates"])
    y = dem["y"].astype(int)
    labels = np.array(dem["labels"])
    event_onsets = json.loads(str(dem["event_onsets"]))

    # Fill NaNs with column means
    for col in range(X.shape[1]):
        nans = np.isnan(X[:, col])
        if nans.any():
            X[nans, col] = np.nanmean(X[~nans, col])

    # Reference: Jan 2019 – Dec 2019 (8760 hours, pre-crisis stable year)
    ref_mask = np.array(["2019-01" <= d[:7] <= "2019-12" for d in dates])
    X_ref = X[ref_mask]

    # Test window: calendar year 2021 (n=8760, contains Uri + Elliott)
    test_mask = np.array(["2021-01" <= d[:7] <= "2021-12" for d in dates])
    X_test = X[test_mask]
    y_test = y[test_mask]
    labels_test = labels[test_mask]
    dates_test = dates[test_mask]

    return dict(
        X_ref=X_ref, X_all=X_test, y=y_test, dates=dates_test,
        labels=labels_test, features=features, event_onsets=event_onsets,
        mode=mode,
    )


# ─────────────────────────────────────────────────────────────────
# ENGINE RUNNER
# ─────────────────────────────────────────────────────────────────

def _run_single_engine(name, X, y, target_far: float):
    t0 = time.perf_counter()
    try:
        if name == 'Molecular(LJ)':
            eng = MolecularEngine(calibrate='combined', target_far=target_far)
        elif name == 'Gravity(N-body)':
            eng = GravityModeEngine(calibrate='combined', target_far=target_far)
        else:
            eng = HybridGravityEngine(calibrate='combined', target_far=target_far)
        scores = eng.fit_score(X, y)
        elapsed = (time.perf_counter() - t0) * 1000
        return scores, elapsed
    except Exception as ex:
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"      [{name} FAILED: {ex}]")
        return None, elapsed


def _run_all(data, tag, target_far: float):
    X_ref, X_all, y = data['X_ref'], data['X_all'], data['y']

    print(f"\n  Building UDL representations on {len(X_ref)}-hour reference …")
    reps = build_reps(X_ref, X_all)
    rep_names = ['Raw'] + list(reps.keys())
    print(f"  Built: {rep_names}")

    results = {}
    for rn in rep_names:
        Ra = X_all if rn == 'Raw' else reps[rn]['all']
        D = Ra.shape[1]
        print(f"\n  ── {rn} ({D}D) ──")
        results[rn] = {}
        for eng_name in ENGINE_NAMES:
            print(f"    {eng_name:<22s} …", end='', flush=True)
            scores, t_ms = _run_single_engine(eng_name, Ra, y, target_far)
            if scores is not None:
                auc = auc_manual(y, scores)
                results[rn][eng_name] = dict(scores=scores, time_ms=t_ms, auc=auc)
                print(f"  AUC={auc:.4f}  ({t_ms:.0f}ms)")
            else:
                results[rn][eng_name] = None
                print(f"  FAILED ({t_ms:.0f}ms)")

    return results, rep_names


def _print_auc_table(tag, results, rep_names):
    print(f"\n{'═' * W}")
    print(f"  AUC TABLE — {tag}")
    print(f"{'═' * W}")
    col_w = 16
    header = f"  {'Engine':<22s}"
    for rn in rep_names:
        header += f" │ {rn:^{col_w}}"
    header += f" │ {'Mean':^8s} │ {'Best':^8s}"
    print(header)
    print("  " + "─" * (len(header) - 2))
    for eng in ENGINE_NAMES:
        row = f"  {eng:<22s}"
        aucs = []
        for rn in rep_names:
            res = results.get(rn, {}).get(eng)
            if res:
                aucs.append(res['auc'])
                row += f" │ {res['auc']:^{col_w}.4f}"
            else:
                row += f" │ {'—':^{col_w}}"
        if aucs:
            row += f" │ {np.mean(aucs):^8.4f} │ {max(aucs):^8.4f}"
        print(row)


# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ERCOT hourly physics engine evaluation")
    parser.add_argument("--target-far", type=float, default=0.05,
                        help="Target FAR for calibration (0.10 corresponds to P90)")
    args = parser.parse_args()

    np.set_printoptions(precision=4, suppress=True)

    print("=" * W)
    print("  ERCOT HOURLY — PHYSICS ENGINE EVALUATION")
    print("  Protocol: raw hourly (n≈35064), ref=year-2019 (8760h), paper Table 4")
    print(f"  Calibration: method=combined, target_far={args.target_far:.2f} (P{int((1.0-args.target_far)*100):d})")
    print("=" * W)

    for mode, label in [("supply", "SUPPLY-ONLY (d=5)"), ("combined", "COMBINED (d=10)")]:
        print(f"\n{'█' * W}")
        print(f"  ERCOT {label}")
        print(f"{'█' * W}")

        data = _load_ercot_hourly(mode)
        if data is None:
            print("  SKIPPED: ERCOT data not found at", ERCOT_DIR)
            continue

        print(f"  Hourly total:  {data['X_all'].shape[0]} obs × {data['X_all'].shape[1]} features")
        print(f"  Reference (2019): {data['X_ref'].shape[0]} hours")
        print(f"  Features: {data['features']}")
        print(f"  Events:   {list(data['event_onsets'].keys())}")
        print(f"  Crisis fraction: {data['y'].mean():.2%}")

        results, rep_names = _run_all(data, label, args.target_far)
        _print_auc_table(label, results, rep_names)

    print(f"\n{'=' * W}")
    print("  DONE")
    print(f"{'=' * W}")


if __name__ == "__main__":
    main()
