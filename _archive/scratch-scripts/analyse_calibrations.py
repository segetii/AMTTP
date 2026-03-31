"""Quick analysis: which calibration method gets the best out of the model?"""
import json, numpy as np

# Load full results
r = json.load(open(r'c:\amttp\results\ercot_fartarget_results.json'))
all_res = r['all_results']

for ds_name in ['supply', 'demand', 'combined']:
    if ds_name not in all_res:
        continue
    ds = all_res[ds_name]

    print('=' * 95)
    print(f'  CALIBRATION METHOD COMPARISON — {ds_name.upper()} DATASET')
    print('=' * 95)

    # Collect per-calibration aggregated stats
    cal_stats = {}
    for key, cals in ds.items():
        for cal_name, metrics in cals.items():
            if cal_name not in cal_stats:
                cal_stats[cal_name] = []
            cal_stats[cal_name].append({
                'config': key,
                'n_ev': int(metrics['n_ev']),
                'far': float(metrics['far']),
                'lead': int(metrics['lead']),
                'auc': float(metrics.get('auc') or 0),
            })

    # For each calibration: how many configs detect all 3 events?
    header = (f"  {'Calibration':<22} {'3/3 cfgs':>8} {'Avg FAR%':>10} "
              f"{'Avg Lead':>10} {'Best FAR%':>10} {'Best Lead':>10}")
    print(f"\n{header}")
    print(f"  {'-' * 72}")

    cal_summary = []
    for cal_name in sorted(cal_stats.keys()):
        entries = cal_stats[cal_name]
        full_det = [e for e in entries if e['n_ev'] == 3]
        n_full = len(full_det)
        if n_full > 0:
            avg_far = np.mean([e['far'] for e in full_det])
            avg_lead = np.mean([e['lead'] for e in full_det])
            best_far = min(e['far'] for e in full_det)
            best_lead = max(e['lead'] for e in full_det)
            best_cfg = min(full_det, key=lambda x: (x['far'], -x['lead']))
        else:
            avg_far = avg_lead = best_far = best_lead = 0
            best_cfg = None
        cal_summary.append((cal_name, n_full, avg_far, avg_lead,
                            best_far, best_lead, best_cfg))

    cal_summary.sort(key=lambda x: (-x[1], x[4], -x[5]))
    for cal_name, n_full, avg_far, avg_lead, best_far, best_lead, _ in cal_summary:
        print(f"  {cal_name:<22} {n_full:>8} {avg_far:>9.1f}% "
              f"{avg_lead:>9.0f}w {best_far:>9.1f}% {best_lead:>9.0f}w")

    # Best config per calibration
    print(f"\n  BEST CONFIG PER CALIBRATION (lowest FAR at 3/3 events)")
    print(f"  {'-' * 100}")
    print(f"  {'Calibration':<22} {'Config':<25} {'AUC':>7} {'FAR%':>6} "
          f"{'Lead':>6}  Events")
    print(f"  {'-' * 100}")
    for cal_name, n_full, _, _, _, _, best_cfg in cal_summary:
        if best_cfg:
            key = best_cfg['config']
            m = ds[key][cal_name]
            evs = ''
            if 'events_detected' in m:
                evs = ' '.join(f"{e}={l}w"
                               for e, l in m['events_detected'].items())
            print(f"  {cal_name:<22} {key:<25} {best_cfg['auc']:>7.4f} "
                  f"{best_cfg['far']:>5.1f}% {best_cfg['lead']:>5}w  {evs}")
    print()

# ===============================================================
# OVERALL WINNER: best (AUC, FAR, events) across everything
# ===============================================================
print('\n' + '#' * 95)
print('  OVERALL BEST CONFIGS — ALL DATASETS × ALL CALIBRATIONS')
print('#' * 95)

all_rows = []
for ds_name in ['supply', 'demand', 'combined']:
    if ds_name not in all_res:
        continue
    ds = all_res[ds_name]
    for key, cals in ds.items():
        for cal_name, m in cals.items():
            all_rows.append({
                'ds': ds_name,
                'config': key,
                'cal': cal_name,
                'n_ev': int(m['n_ev']),
                'far': float(m['far']),
                'lead': int(m['lead']),
                'auc': float(m.get('auc') or 0),
                'evs': m.get('events_detected', {}),
            })

# Filter: 3/3 events
full = [r for r in all_rows if r['n_ev'] == 3]

# Sort by: lowest FAR, then highest AUC, then highest lead
full.sort(key=lambda x: (x['far'], -x['auc'], -x['lead']))

print(f"\n  Top 30 configs (3/3 events, sorted by FAR then AUC):")
print(f"  {'#':<4} {'Dataset':<10} {'Config':<25} {'Calibration':<22} "
      f"{'AUC':>7} {'FAR%':>6} {'Lead':>5}  Events")
print(f"  {'-' * 110}")
for i, c in enumerate(full[:30], 1):
    evs = ' '.join(f"{e}={l}w" for e, l in c['evs'].items())
    print(f"  {i:<4} {c['ds']:<10} {c['config']:<25} {c['cal']:<22} "
          f"{c['auc']:>7.4f} {c['far']:>5.1f}% {c['lead']:>4}w  {evs}")

# Also sort by AUC (best discrimination)
full_auc = sorted(full, key=lambda x: -x['auc'])
print(f"\n  Top 20 by AUC (3/3 events, sorted by AUC):")
print(f"  {'#':<4} {'Dataset':<10} {'Config':<25} {'Calibration':<22} "
      f"{'AUC':>7} {'FAR%':>6} {'Lead':>5}  Events")
print(f"  {'-' * 110}")
for i, c in enumerate(full_auc[:20], 1):
    evs = ' '.join(f"{e}={l}w" for e, l in c['evs'].items())
    print(f"  {i:<4} {c['ds']:<10} {c['config']:<25} {c['cal']:<22} "
          f"{c['auc']:>7.4f} {c['far']:>5.1f}% {c['lead']:>4}w  {evs}")

# Best composite score: maximize AUC - FAR/100 + lead/200
print(f"\n  Top 20 by COMPOSITE score (AUC - FAR/100 + lead/200):")
print(f"  {'#':<4} {'Dataset':<10} {'Config':<25} {'Calibration':<22} "
      f"{'AUC':>7} {'FAR%':>6} {'Lead':>5} {'Score':>7}")
print(f"  {'-' * 110}")
for c in full:
    c['composite'] = c['auc'] - c['far']/100 + c['lead']/200
comp = sorted(full, key=lambda x: -x['composite'])
for i, c in enumerate(comp[:20], 1):
    print(f"  {i:<4} {c['ds']:<10} {c['config']:<25} {c['cal']:<22} "
          f"{c['auc']:>7.4f} {c['far']:>5.1f}% {c['lead']:>4}w {c['composite']:>7.3f}")

print(f"\n  Paper: AUC=0.9940, Hybrid/fused, FARTargetCalibrator, single-fit 1yr")
