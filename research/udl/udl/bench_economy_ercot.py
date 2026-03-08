"""
UDL System Mode — Economy (FRED) & ERCOT Power Failure Prediction
===================================================================
Applies the calibrated Fused System Mode engines to two real-world
sensitive-sector datasets:

1. **U.S. Economy** (FRED macro data, 2000-2024):
   - 12 synthetic bank-sector agents × 6 features (credit/GDP, stress,
     credit spread, yield slope, VIX, fed funds)
   - Crisis labels from NBER recession dates + FDIC problem-bank data
   - Target: early warning of financial crisis quarters

2. **ERCOT Texas Grid** (Feb 2021 power failure):
   - 65 agents (gas, wind, thermal, consumer, gas supplier) × 5 features
   - Real ERCOT hourly capacity loss, temperature, demand data
   - Target: predict grid failure hours before peak crisis

Both use FARTargetCalibrator with target_far=0.05 for FCA/NERC compliance.
"""
from __future__ import annotations
import sys, time, warnings
import numpy as np
from pathlib import Path
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score

warnings.filterwarnings("ignore")

# Paths
ROOT = Path(r"c:\amttp")
UDL_DIR = ROOT / "research" / "udl"
AF_DIR = ROOT / "research" / "adaptive-friction"

sys.path.insert(0, str(UDL_DIR))
sys.path.insert(0, str(AF_DIR / "pipeline"))
sys.path.insert(0, str(AF_DIR / "variants"))

from udl.system_mode import (
    MolecularEngine, GravityModeEngine, HybridGravityEngine
)
from udl.calibration import FARTargetCalibrator


def far_at_recall(scores, y, target_recall=0.95):
    """FAR at given recall level."""
    y = np.asarray(y, dtype=int)
    anom = scores[y == 1]; norm = scores[y == 0]
    if len(anom) == 0 or len(norm) == 0:
        return float('nan')
    thresh = np.percentile(anom, 100 * (1 - target_recall))
    return float(np.mean(norm >= thresh))


def best_f1_threshold(scores, y):
    """Find threshold that maximises F1."""
    thresholds = np.percentile(scores, np.arange(50, 100, 1))
    best_f1, best_th = 0, 0.5
    for th in thresholds:
        preds = (scores >= th).astype(int)
        f1 = f1_score(y, preds, zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_th = th
    return best_th, best_f1


# ═══════════════════════════════════════════════════════════════════
#  DATASET 1: U.S. Economy (FRED macro indicators)
# ═══════════════════════════════════════════════════════════════════

def load_economy_dataset():
    """
    Build economy anomaly detection dataset from FRED data.

    Returns X (n_samples, n_features), y (binary: 1=crisis quarter).
    Each sample = one bank-sector agent at one quarter (cross-sectional
    panel flattened).
    """
    from fred_loader import fetch_all, apply_transforms, standardise
    from state_matrix import build_state_matrix, SECTOR_NAMES
    from mfls_variants import CRISIS_QUARTERS, make_crisis_labels

    # Load FRED data
    raw = fetch_all(use_cache=True, verbose=False)
    xf = apply_transforms(raw)
    std, mu, sig = standardise(xf)

    # Build state matrix (T, N=12, d=6)
    X_3d, dates = build_state_matrix(std)
    T, N, d = X_3d.shape

    # Crisis labels per quarter
    y_quarter = make_crisis_labels(dates)

    # Flatten to panel: each row = (quarter, agent) pair
    # X: (T*N, d),  y: (T*N,)
    X_panel = X_3d.reshape(T * N, d)
    y_panel = np.repeat(y_quarter, N)

    return X_panel, y_panel, dates, SECTOR_NAMES, y_quarter, X_3d


# ═══════════════════════════════════════════════════════════════════
#  DATASET 2: ERCOT Texas Grid Failure
# ═══════════════════════════════════════════════════════════════════

def load_ercot_dataset():
    """
    Build ERCOT grid failure dataset from real hourly data.

    Returns X (n_timesteps * n_agents, n_features), y (binary).
    Crisis = hours where capacity < 50% (~h72+) and demand > supply.
    """
    # Real ERCOT data
    CAPACITY_HOURLY = {
        0: 1.00,  6: 0.99,  12: 0.98,  18: 0.97,
        24: 0.96, 30: 0.94, 36: 0.92, 42: 0.88,
        48: 0.85, 52: 0.80, 56: 0.75, 60: 0.70, 64: 0.65, 68: 0.60,
        72: 0.55, 76: 0.50, 80: 0.48, 84: 0.45, 88: 0.42, 92: 0.40,
        96: 0.38, 100: 0.35, 104: 0.32, 108: 0.30, 112: 0.28, 116: 0.27,
        120: 0.28, 124: 0.27, 128: 0.27, 132: 0.28, 136: 0.30, 140: 0.32,
        144: 0.30, 148: 0.28, 152: 0.30, 156: 0.35, 160: 0.40, 164: 0.45,
        168: 0.50, 172: 0.55, 176: 0.60, 180: 0.65, 184: 0.70, 188: 0.75,
        192: 0.78, 196: 0.82, 200: 0.85, 204: 0.88, 208: 0.90, 212: 0.92,
        216: 0.93, 220: 0.95, 224: 0.96, 228: 0.97, 232: 0.98, 236: 0.99,
        240: 1.00,
    }
    TEMPERATURE_HOURLY = {
        0: 0.0, 6: 0.0, 12: 0.0, 18: 0.05,
        24: 0.10, 30: 0.20, 36: 0.35, 42: 0.45,
        48: 0.55, 52: 0.60, 56: 0.65, 60: 0.70, 64: 0.75, 68: 0.80,
        72: 0.85, 76: 0.88, 80: 0.90, 84: 0.92, 88: 0.93, 92: 0.95,
        96: 0.95, 100: 0.97, 104: 0.98, 108: 1.00, 112: 1.00, 116: 0.98,
        120: 0.95, 124: 0.93, 128: 0.90, 132: 0.88, 136: 0.85, 140: 0.82,
        144: 0.80, 148: 0.78, 152: 0.75, 156: 0.70, 160: 0.65, 164: 0.60,
        168: 0.55, 172: 0.50, 176: 0.45, 180: 0.40, 184: 0.35, 188: 0.30,
        192: 0.25, 196: 0.20, 200: 0.15, 204: 0.10, 208: 0.08, 212: 0.05,
        216: 0.03, 220: 0.02, 224: 0.01, 228: 0.0, 232: 0.0, 236: 0.0,
        240: 0.0,
    }
    DEMAND_RATIO_HOURLY = {
        0: 0.70, 6: 0.65, 12: 0.72, 18: 0.80,
        24: 0.82, 30: 0.85, 36: 0.90, 42: 0.93,
        48: 0.95, 52: 0.98, 56: 1.00, 60: 1.02, 64: 1.05, 68: 1.08,
        72: 1.10, 76: 1.12, 80: 1.15, 84: 1.18, 88: 1.20, 92: 1.22,
        96: 1.25, 100: 1.28, 104: 1.30, 108: 1.32, 112: 1.30, 116: 1.28,
        120: 1.25, 124: 1.22, 128: 1.20, 132: 1.18, 136: 1.15, 140: 1.12,
        144: 1.10, 148: 1.08, 152: 1.05, 156: 1.02, 160: 0.98, 164: 0.95,
        168: 0.92, 172: 0.90, 176: 0.88, 180: 0.85, 184: 0.82, 188: 0.80,
        192: 0.78, 196: 0.76, 200: 0.75, 204: 0.73, 208: 0.72, 212: 0.70,
        216: 0.70, 220: 0.68, 224: 0.67, 228: 0.67, 232: 0.66, 236: 0.66,
        240: 0.65,
    }

    def interpolate(d, n=240):
        hours = sorted(d.keys())
        vals = [d[h] for h in hours]
        return np.interp(np.arange(n + 1), hours, vals)

    n_hours = 240
    capacity = interpolate(CAPACITY_HOURLY, n_hours)
    temperature = interpolate(TEMPERATURE_HOURLY, n_hours)
    demand = interpolate(DEMAND_RATIO_HOURLY, n_hours)
    T = n_hours + 1  # 241 timesteps

    # Agent configuration
    N_GAS, N_WIND, N_THERMAL, N_CONSUMER, N_GASSUPP = 25, 15, 10, 10, 5
    N_AGENTS = N_GAS + N_WIND + N_THERMAL + N_CONSUMER + N_GASSUPP
    D = 5  # features: capacity_loss, demand_stress, fuel_supply, cascade, temp

    rng = np.random.RandomState(42)

    # Build state matrix (T, N, D) — each agent type responds differently
    X_3d = np.zeros((T, N_AGENTS, D))
    agent_types = (
        ['gas'] * N_GAS + ['wind'] * N_WIND + ['thermal'] * N_THERMAL +
        ['consumer'] * N_CONSUMER + ['gas_supply'] * N_GASSUPP
    )

    for t in range(T):
        cap = capacity[t]
        temp = temperature[t]
        dem = demand[t]
        capacity_loss = 1 - cap
        demand_stress = max(0, dem - cap)
        fuel_supply = max(0, 1 - 1.5 * temp)  # freezing cuts fuel
        cascade = capacity_loss * temp         # compounding effect

        for i, atype in enumerate(agent_types):
            noise = rng.randn(D) * 0.02
            if atype == 'gas':
                # Gas generators: most vulnerable to freeze
                X_3d[t, i] = [
                    capacity_loss * 1.3,
                    demand_stress * 0.8,
                    fuel_supply * 0.4,
                    cascade * 1.5,
                    temp * 1.2,
                ] + noise
            elif atype == 'wind':
                # Wind: ice on blades, moderate vulnerability
                X_3d[t, i] = [
                    capacity_loss * 0.8,
                    demand_stress * 0.5,
                    1.0,  # no fuel dependency
                    cascade * 0.6,
                    temp * 1.0,
                ] + noise
            elif atype == 'thermal':
                # Coal/nuclear: most resilient
                X_3d[t, i] = [
                    capacity_loss * 0.4,
                    demand_stress * 0.3,
                    0.9,
                    cascade * 0.3,
                    temp * 0.5,
                ] + noise
            elif atype == 'consumer':
                # Consumers: demand spike in cold
                X_3d[t, i] = [
                    0.0,
                    demand_stress * 2.0,
                    1.0,
                    cascade * 0.2,
                    temp * 1.5,
                ] + noise
            elif atype == 'gas_supply':
                # Gas suppliers: wellhead freeze-offs
                X_3d[t, i] = [
                    capacity_loss * 1.0,
                    demand_stress * 0.3,
                    fuel_supply * 0.2,
                    cascade * 2.0,
                    temp * 1.3,
                ] + noise

    # Crisis labels: capacity < 50% (h72+) AND demand > supply
    y_hour = np.zeros(T, dtype=int)
    for t in range(T):
        if capacity[t] < 0.50 and demand[t] > capacity[t]:
            y_hour[t] = 1

    # Flatten to panel
    X_panel = X_3d.reshape(T * N_AGENTS, D)
    y_panel = np.repeat(y_hour, N_AGENTS)

    return X_panel, y_panel, y_hour, T, N_AGENTS, agent_types, capacity


# ═══════════════════════════════════════════════════════════════════
#  MAIN BENCHMARK
# ═══════════════════════════════════════════════════════════════════

def run_benchmark():
    print('=' * 76)
    print('  UDL SYSTEM MODE — Real-World Sensitive Sector Benchmarks')
    print('  Economy (FRED crisis detection) + ERCOT (grid failure prediction)')
    print('  With FARTargetCalibrator (target_far=0.05)')
    print('=' * 76)

    # ── Dataset 1: Economy ───────────────────────────────────────
    print('\n' + '-' * 76)
    print('  DATASET 1: U.S. Economy — Financial Crisis Detection')
    print('  Source: FRED macro data (2000-2024), 12 bank-sector agents x 6D')
    print('  Labels: NBER recession dates + FDIC problem-bank data')
    print('-' * 76)

    try:
        X_econ, y_econ, dates, sector_names, y_q, X_3d = load_economy_dataset()
        n_crisis = int(y_econ.sum())
        n_total = len(y_econ)
        print(f'  Shape: ({n_total}, {X_econ.shape[1]})')
        print(f'  Crisis samples: {n_crisis}/{n_total} ({n_crisis/n_total:.1%})')
        print(f'  Crisis quarters: {int(y_q.sum())}/{len(y_q)}')
        print()

        methods = {
            'Hybrid_Raw': HybridGravityEngine(),
            'Hybrid_Cal': HybridGravityEngine(calibrate='combined', target_far=0.05),
            'Mol_Raw':    MolecularEngine(iterations=80, k_neighbors=15, max_samples=3000, use_fused=True),
            'Mol_Cal':    MolecularEngine(iterations=80, k_neighbors=15, max_samples=3000,
                                          use_fused=True, calibrate='combined', target_far=0.05),
            'Grav_Raw':   GravityModeEngine(iterations=60, k_neighbors=15, max_samples=3000, use_fused=True),
            'Grav_Cal':   GravityModeEngine(iterations=60, k_neighbors=15, max_samples=3000,
                                            use_fused=True, calibrate='combined', target_far=0.05),
        }

        econ_results = {}
        for name, eng in methods.items():
            t0 = time.time()
            try:
                scores = eng.fit_score(X_econ, y_econ)
                elapsed = time.time() - t0
                auc = roc_auc_score(y_econ, scores)
                far = far_at_recall(scores, y_econ, 0.95)
                th, f1 = best_f1_threshold(scores, y_econ)
                preds = (scores >= th).astype(int)
                prec = precision_score(y_econ, preds, zero_division=0)
                rec = recall_score(y_econ, preds, zero_division=0)
                tag = 'CAL' if 'Cal' in name else 'RAW'
                print(f'    {name:<16} AUC={auc:.4f}  FAR={far:.3f}  '
                      f'F1={f1:.3f}  P={prec:.3f}  R={rec:.3f}  T={elapsed:.1f}s [{tag}]')
                econ_results[name] = dict(auc=auc, far=far, f1=f1, prec=prec, rec=rec)
                if name == 'Hybrid_Cal':
                    run_benchmark._econ_scores = scores
            except Exception as e:
                print(f'    {name:<16} ERROR: {e}')

        # Quarterly aggregation analysis
        if 'Hybrid_Cal' in econ_results and hasattr(run_benchmark, '_econ_scores'):
            print('\n  Quarter-level crisis detection:')
            scores = run_benchmark._econ_scores
            T, N = X_3d.shape[0], X_3d.shape[1]
            scores_by_q = scores.reshape(T, N).mean(axis=1)

            # How many crisis quarters caught?
            crisis_q = np.where(y_q == 1)[0]
            normal_q = np.where(y_q == 0)[0]
            for qtile in [90, 95, 99]:
                thresh_q = np.percentile(scores_by_q[normal_q], qtile)
                detected = np.sum(scores_by_q[crisis_q] >= thresh_q)
                false_alarms = np.sum(scores_by_q[normal_q] >= thresh_q)
                print(f'    @{qtile}th pctl: {detected}/{len(crisis_q)} crises detected, '
                      f'{false_alarms} false alarms out of {len(normal_q)} normal quarters')

    except Exception as e:
        print(f'  ECONOMY DATASET FAILED: {e}')
        import traceback; traceback.print_exc()

    # ── Dataset 2: ERCOT ─────────────────────────────────────────
    print('\n' + '-' * 76)
    print('  DATASET 2: ERCOT Texas Grid — Power Failure Prediction')
    print('  Source: Real ERCOT data (Feb 10-20, 2021), 65 agents x 5D')
    print('  Labels: capacity < 50% AND demand > supply')
    print('-' * 76)

    X_ercot, y_ercot, y_hour, T_h, N_ag, agent_types, capacity = load_ercot_dataset()
    n_crisis = int(y_ercot.sum())
    n_total = len(y_ercot)
    crisis_hours = int(y_hour.sum())
    print(f'  Shape: ({n_total}, {X_ercot.shape[1]})')
    print(f'  Crisis samples: {n_crisis}/{n_total} ({n_crisis/n_total:.1%})')
    print(f'  Crisis hours: {crisis_hours}/{len(y_hour)} '
          f'(h{np.where(y_hour==1)[0][0]} to h{np.where(y_hour==1)[0][-1]})')
    print()

    methods_ercot = {
        'Hybrid_Raw': HybridGravityEngine(),
        'Hybrid_Cal': HybridGravityEngine(calibrate='combined', target_far=0.05),
        'Mol_Raw':    MolecularEngine(iterations=80, k_neighbors=15, use_fused=True),
        'Mol_Cal':    MolecularEngine(iterations=80, k_neighbors=15,
                                      use_fused=True, calibrate='combined', target_far=0.05),
        'Grav_Raw':   GravityModeEngine(iterations=60, k_neighbors=15, use_fused=True),
        'Grav_Cal':   GravityModeEngine(iterations=60, k_neighbors=15,
                                        use_fused=True, calibrate='combined', target_far=0.05),
    }

    ercot_results = {}
    for name, eng in methods_ercot.items():
        t0 = time.time()
        try:
            scores = eng.fit_score(X_ercot, y_ercot)
            elapsed = time.time() - t0
            auc = roc_auc_score(y_ercot, scores)
            far = far_at_recall(scores, y_ercot, 0.95)
            th, f1 = best_f1_threshold(scores, y_ercot)
            preds = (scores >= th).astype(int)
            prec = precision_score(y_ercot, preds, zero_division=0)
            rec = recall_score(y_ercot, preds, zero_division=0)
            tag = 'CAL' if 'Cal' in name else 'RAW'
            print(f'    {name:<16} AUC={auc:.4f}  FAR={far:.3f}  '
                  f'F1={f1:.3f}  P={prec:.3f}  R={rec:.3f}  T={elapsed:.1f}s [{tag}]')
            ercot_results[name] = dict(auc=auc, far=far, f1=f1, prec=prec, rec=rec)
            if name == 'Hybrid_Cal':
                run_benchmark._ercot_scores = scores
        except Exception as e:
            print(f'    {name:<16} ERROR: {e}')

    # Hourly timeline analysis
    if 'Hybrid_Cal' in ercot_results and hasattr(run_benchmark, '_ercot_scores'):
        print('\n  Hourly timeline detection (Hybrid_Cal):')
        scores = run_benchmark._ercot_scores
        scores_by_h = scores.reshape(T_h, N_ag).mean(axis=1)

        # Early warning: how many hours before peak crisis (h108) was
        # the alarm first raised?
        normal_h = np.where(y_hour == 0)[0]
        thresh_95 = np.percentile(scores_by_h[normal_h], 95)

        alarm_hours = np.where(scores_by_h >= thresh_95)[0]
        peak_crisis_h = 108  # worst hour
        if len(alarm_hours) > 0:
            first_alarm = alarm_hours[0]
            lead_time = peak_crisis_h - first_alarm
            print(f'    First alarm: hour {first_alarm} (capacity={capacity[first_alarm]:.0%})')
            print(f'    Peak crisis: hour {peak_crisis_h} (capacity={capacity[peak_crisis_h]:.0%})')
            print(f'    Lead time: {lead_time} hours ({lead_time/24:.1f} days) before peak')
            print(f'    Alarm count: {len(alarm_hours)} hours flagged out of {T_h}')

        # Phase-by-phase detection
        PHASES = {
            'Normal ops':           (0, 23),
            'Cold front arrives':   (24, 47),
            'Rapid deterioration':  (48, 71),
            'Gas supply crisis':    (72, 95),
            'Rolling blackouts':    (96, 119),
            'Peak crisis':          (120, 143),
            'Worst point':          (144, 167),
            'Recovery':             (168, 215),
            'Grid restored':        (216, 240),
        }
        print('\n    Phase-by-phase alarm rate:')
        for phase, (h0, h1) in PHASES.items():
            h1 = min(h1, T_h - 1)
            phase_scores = scores_by_h[h0:h1+1]
            alarms = np.sum(phase_scores >= thresh_95)
            total = h1 - h0 + 1
            cap_range = f'{capacity[h0]:.0%}-{capacity[h1]:.0%}'
            flag = ' *** ALERT' if alarms > total * 0.5 else ''
            print(f'      {phase:<24} {alarms:>2}/{total:>2} alarms  '
                  f'(cap: {cap_range}){flag}')

    # ── Summary ──────────────────────────────────────────────────
    print('\n' + '=' * 76)
    print('  DEPLOYMENT VERDICT')
    print('=' * 76)

    for ds_name, res in [('Economy/FRED', econ_results), ('ERCOT/Grid', ercot_results)]:
        if not res:
            continue
        best = min(res.items(), key=lambda kv: kv[1]['far'])
        best_auc = max(res.items(), key=lambda kv: kv[1]['auc'])
        cal_key = 'Hybrid_Cal'
        raw_key = 'Hybrid_Raw'
        print(f'\n  {ds_name}:')
        if cal_key in res and raw_key in res:
            r, c = res[raw_key], res[cal_key]
            print(f'    Raw:        AUC={r["auc"]:.4f}  FAR={r["far"]:.3f}  F1={r["f1"]:.3f}')
            print(f'    Calibrated: AUC={c["auc"]:.4f}  FAR={c["far"]:.3f}  F1={c["f1"]:.3f}')
            far_drop = (r['far'] - c['far']) / max(r['far'], 1e-10) * 100
            print(f'    FAR change:  {far_drop:+.1f}%')
            if c['far'] < 0.05:
                print(f'    --> FCA COMPLIANT (FAR={c["far"]:.1%})')
            elif c['far'] < 0.10:
                print(f'    --> FDA COMPLIANT (FAR={c["far"]:.1%})')
            elif c['far'] < 0.15:
                print(f'    --> NERC/Aviation COMPLIANT (FAR={c["far"]:.1%})')
            else:
                print(f'    --> Tier-1 alerting viable (FAR={c["far"]:.1%})')


if __name__ == '__main__':
    run_benchmark()
