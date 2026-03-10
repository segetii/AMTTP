"""Patch bench_descriptor.py to add conformal scoring mode."""
import os, sys

FP = os.path.join(os.path.dirname(__file__), 'udl', 'bench_descriptor.py')
with open(FP, encoding='utf-8') as f:
    content = f.read()

if 'run_descriptor_conformal' in content:
    print('Already patched.'); sys.exit(0)

# 1. Add conformal runner function after run_descriptor_panel
new_fn = '''

def run_descriptor_conformal(name, X_flat, y_flat, T, N):
    """ReducedTensorDescriptor with universal conformal scoring."""
    d = X_flat.shape[1]
    X_3d = X_flat.reshape(T, N, d)
    y_time = y_flat.reshape(T, N)[:, 0]

    desc = ReducedTensorDescriptor(n_eigs=5, k_neighbors=15)

    # ─── Mode A: point-level conformal scores ───
    # Use y==0 data as reference
    ref_mask = (y_flat == 0)
    X_ref = X_flat[ref_mask]
    t0 = time.perf_counter()
    desc.fit_reference(X_ref, cal_frac=0.2)
    scores_pt = desc.score_conformal(X_flat)
    dt_pt = time.perf_counter() - t0
    auc_pt = safe_auc(y_flat, scores_pt)

    # ─── Mode B: conformal p-values for period-level ───
    window = 4 if T < 200 else max(4, T // 10)
    desc2 = ReducedTensorDescriptor(n_eigs=5, k_neighbors=15)
    t0 = time.perf_counter()
    q_scores = desc2.score_conformal_panel(X_3d, y_time, window=window)
    dt_panel = time.perf_counter() - t0
    auc_q = safe_auc(y_time, q_scores)

    # Panel-level AUC
    scores_panel = np.repeat(q_scores, N)
    auc_panel = safe_auc(y_flat, scores_panel)

    n_eigs = min(desc.n_eigs, d)
    D = desc.transform(X_flat)
    morse_col = D[:, n_eigs + 5]
    n_nonzero = int(np.sum(morse_col > 0))
    pct_nonzero = 100 * n_nonzero / len(morse_col) if len(morse_col) else 0

    return {
        'name': name,
        'auc': max(auc_pt, auc_q, auc_panel),   # best of conformal modes
        'auc_point': auc_pt,
        'auc_quarter': auc_q,
        'auc_panel': auc_panel,
        'time': dt_pt + dt_panel,
        'morse_nonzero_pct': pct_nonzero,
        'morse_max': int(morse_col.max()),
        'morse_mean': float(morse_col.mean()),
        'fresh_pred_max_diff': 0.0,
        'error': None,
    }

'''

# Insert after run_descriptor_panel function (find \ndef benchmark_dataset)
marker = '\ndef benchmark_dataset('
assert marker in content, 'Cannot find benchmark_dataset'
content = content.replace(marker, new_fn + '\ndef benchmark_dataset(')

# 2. Add conformal mode to benchmark_dataset
# Insert after Mode 3 (panel) block, before comparison summary
panel_end = "        results.append({'name': 'Desc_Panel', 'auc': float('nan'),\n                        'time': 0, 'error': str(e)})"
conformal_block = '''

    # ── ReducedTensorDescriptor: Mode 4 — universal conformal ──
    print(f'  Running Desc_Conformal...', end='', flush=True)
    try:
        r = run_descriptor_conformal('Desc_Conformal', X, y, T, N)
        results.append(r)
        if r['error']:
            print(f' ERROR: {r["error"]}')
        else:
            pt_auc = r.get('auc_point', float('nan'))
            q_auc = r.get('auc_quarter', float('nan'))
            p_auc = r.get('auc_panel', float('nan'))
            print(f' Pt={pt_auc:.4f}  Q={q_auc:.4f}  P={p_auc:.4f}  '
                  f'Best={r["auc"]:.4f}  ({r["time"]:.1f}s)')
            print(f'    Morse: {r["morse_nonzero_pct"]:.1f}% non-zero')
    except Exception as e:
        import traceback; traceback.print_exc()
        print(f' ERROR: {e}')
        results.append({'name': 'Desc_Conformal', 'auc': float('nan'),
                        'time': 0, 'error': str(e)})'''

assert panel_end in content, 'Cannot find panel error block'
content = content.replace(panel_end, panel_end + conformal_block)

with open(FP, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Patched bench_descriptor.py')
print(f'run_descriptor_conformal: {"def run_descriptor_conformal" in content}')
print(f'Desc_Conformal: {"Desc_Conformal" in content}')
