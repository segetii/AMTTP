#!/usr/bin/env python3
"""Quick single-domain run: ERCOT collapse-only (Uri + Elliott)."""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

from test_causal_physics import _load_ercot, run_domain, cross_domain_summary, W

t0 = time.perf_counter()
print('=' * W)
print('  ERCOT COLLAPSE-ONLY — Causal Physics (SIAM Protocol)')
print('  Events: WinterStormUri + WinterStormElliott only')
print('  COVID demand-drop and SummerPeak excluded')
print('=' * W)

ercot = _load_ercot()
if ercot:
    n1, n0 = int(ercot['y'].sum()), int((ercot['y'] == 0).sum())
    print(f"  y=1 (collapse) days: {n1}, y=0 (normal+other) days: {n0}")
    print(f"  Events: {list(ercot['event_onsets'].keys())}")
    res = run_domain('ERCOT Collapse-Only', ercot, mode='frozen')
    domain_results = {'ERCOT_collapse': dict(results=res, y=ercot['y'])}
    cross_domain_summary(domain_results)

elapsed = time.perf_counter() - t0
print(f"\n{'=' * W}")
print(f"  COMPLETED in {elapsed:.1f}s")
print(f"{'=' * W}")
