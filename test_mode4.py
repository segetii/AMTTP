"""Quick test: Mode4GravityEngine on the G-SIB prospective benchmark."""
import sys, os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, r'C:\amttp\research\udl')

# Monkey-patch: swap GravityModeEngine → Mode4GravityEngine for bench
from udl.system_mode import Mode4GravityEngine
import src.bench_bank_level_prospective as bench

# Replace engine config for "Gravity" to use Mode4
original_run = bench.run_prospective_benchmark

def run_mode4_only():
    """Run benchmark with Mode4GravityEngine only."""
    import udl.system_mode as sm
    # Temporarily alias
    _orig = sm.GravityModeEngine
    sm.GravityModeEngine = Mode4GravityEngine
    try:
        results = original_run()
    finally:
        sm.GravityModeEngine = _orig
    return results

results = run_mode4_only()
if results is None:
    # The function prints its own output; parse from stdout
    print("\n[Mode4 benchmark complete — check output above]")
else:
    for name, r in results.items():
        far = r['fp'] / max(r['fp'] + r['tn'], 1)
        print(f"{name}: AUROC={r['auc']:.4f}  TP={r['tp']}  FP={r['fp']}  FN={r['fn']}  TN={r['tn']}  FAR={far:.1%}")
