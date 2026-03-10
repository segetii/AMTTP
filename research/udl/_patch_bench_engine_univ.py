"""Patch: Add engine universal scoring to benchmark."""
import os, sys

FP = os.path.join(os.path.dirname(__file__), 'udl', 'bench_descriptor.py')
with open(FP, encoding='utf-8') as f:
    content = f.read()

if 'run_engine_universal' in content:
    print('Already patched.'); sys.exit(0)

# 1. Add the engine universal runner function
new_fn = '''
def run_engine_universal(name, engine, X, y, T, N):
    """Run engine with universal scoring (physics + conformal + panel)."""
    t0 = time.perf_counter()
    try:
        result = engine.score_universal(X, y, T, N)
    except Exception as e:
        return {'name': name, 'auc': float('nan'), 'time': 0, 'error': str(e)}
    dt = time.perf_counter() - t0

    y_time = y.reshape(T, N)[:, 0]
    auc_pt = safe_auc(y, result['scores'])
    auc_q = safe_auc(y_time, result['q_scores'])
    best = max(auc_pt, auc_q)

    return {
        'name': name,
        'auc': best,
        'auc_point': auc_pt,
        'auc_quarter': auc_q,
        'time': dt,
        'error': None,
    }


'''

# Insert before benchmark_dataset
marker = 'def benchmark_dataset(dataset_name, X, y, T, N):'
assert marker in content, 'Cannot find benchmark_dataset'
content = content.replace(marker, new_fn + marker)

# 2. Add engine universal runs to benchmark_dataset
# Insert after the full engine loop, before the descriptor runs
old_block = '''    # ── ReducedTensorDescriptor: Mode 1 — raw unsupervised ──'''

new_engine_universal = '''    # ── Full engines: universal scoring (physics + conformal + panel) ──
    universal_engines = [
        ('Gravity_Univ', GravityModeEngine(iterations=60, k_neighbors=10,
                                            use_fused=True)),
        ('Molecular_Univ', MolecularEngine(iterations=80, k_neighbors=10,
                                            use_fused=True)),
        ('Hybrid_Univ', HybridGravityEngine()),
    ]
    for ename, eng in universal_engines:
        print(f'  Running {ename}...', end='', flush=True)
        try:
            r = run_engine_universal(ename, eng, X, y, T, N)
            results.append(r)
            if r['error']:
                print(f' ERROR: {r["error"]}')
            else:
                pt = r.get('auc_point', float('nan'))
                q = r.get('auc_quarter', float('nan'))
                print(f' Pt={pt:.4f}  Q={q:.4f}  Best={r["auc"]:.4f}  ({r["time"]:.1f}s)')
        except Exception as e:
            print(f' ERROR: {e}')
            results.append({'name': ename, 'auc': float('nan'),
                            'time': 0, 'error': str(e)})

    # ── ReducedTensorDescriptor: Mode 1 — raw unsupervised ──'''

assert old_block in content, 'Cannot find Mode 1 block'
content = content.replace(old_block, new_engine_universal)

# 3. Update comparison summary to count engine universal as full engines
# The comparison currently excludes anything with 'Desc' in name as full engines
# and considers 'Desc' as descriptor. The '_Univ' ones should count as full.
# Let's update the filter to include them:
old_filter = '''    full_aucs = [r['auc'] for r in results
                 if 'Desc' not in r['name'] and not np.isnan(r.get('auc', float('nan')))]
    desc_results = [(r['name'], r['auc']) for r in results
                    if 'Desc' in r['name'] and not np.isnan(r.get('auc', float('nan')))]'''

new_filter = '''    full_aucs = [r['auc'] for r in results
                 if 'Desc' not in r['name'] and not np.isnan(r.get('auc', float('nan')))]
    desc_results = [(r['name'], r['auc']) for r in results
                    if 'Desc' in r['name'] and not np.isnan(r.get('auc', float('nan')))]
    univ_results = [(r['name'], r['auc']) for r in results
                    if '_Univ' in r['name'] and not np.isnan(r.get('auc', float('nan')))]'''

content = content.replace(old_filter, new_filter)

# Add a universal comparison line
old_summary = '''        print(f'  >> Gap:                  {gap:+.4f}  '
              f\'{"*** DEGENERATE ***" if gap > 0.10 else "COMPETITIVE" if gap < 0.05 else "ACCEPTABLE"}\')'''

new_summary = '''        print(f'  >> Gap:                  {gap:+.4f}  '
              f\'{"*** DEGENERATE ***" if gap > 0.10 else "COMPETITIVE" if gap < 0.05 else "ACCEPTABLE"}\')
        if univ_results:
            best_univ_name, best_univ_auc = max(univ_results, key=lambda x: x[1])
            gap_univ = best_full - best_univ_auc
            print(f'  >> Best engine-univ AUC: {best_univ_auc:.4f}  ({best_univ_name})')
            print(f'  >> Gap vs best:          {gap_univ:+.4f}')'''

content = content.replace(old_summary, new_summary)

with open(FP, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Added engine universal scoring to benchmark.')
print(f'run_engine_universal: {"def run_engine_universal" in content}')
print(f'Gravity_Univ: {"Gravity_Univ" in content}')
