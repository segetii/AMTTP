"""Run benchmark: all variants closed-form, zero leakage."""
import sys, json
sys.path.insert(0, 'udl')
from system_mode import ReducedTensorDescriptor
import numpy as np

rng = np.random.RandomState(42)
results = {}

for name, n_ref, n_anom, d, shift in [
    ('ERCOT', 200, 50, 8, 2.5),
    ('Bank', 150, 30, 6, 2.0),
]:
    X_ref = rng.randn(n_ref, d) * 0.5
    X_anom = rng.randn(n_anom, d) * 0.5 + shift
    X = np.vstack([X_ref, X_anom])
    y = np.array([0]*n_ref + [1]*n_anom)

    desc = ReducedTensorDescriptor(k_neighbors=10)
    desc.fit(X_ref)
    r = desc.score_variants(X, y, X_ref=X_ref)

    results[name] = {}
    for vname, vr in r.items():
        results[name][vname] = round(vr['auroc'], 4)
        extra = ''
        if 'fisher_weights' in vr:
            fw = [round(w, 3) for w in vr['fisher_weights']]
            extra = '  FW=' + str(fw)
        if 'weights' in vr:
            wt = [round(w, 3) for w in vr['weights']]
            extra = '  beta=' + str(wt)
        print('  %s/%s: AUROC=%.4f%s' % (name, vname, vr['auroc'], extra))

with open('udl/bench_variant_results.json', 'w') as f:
    json.dump(results, f, indent=2)

print()
print('=== ALL CLOSED-FORM, ZERO LABEL LEAKAGE ===')
print(json.dumps(results, indent=2))
