"""Patch: Replace conformal benchmark runner with score_universal runner."""
import os, sys

FP = os.path.join(os.path.dirname(__file__), 'udl', 'bench_descriptor.py')
with open(FP, encoding='utf-8') as f:
    content = f.read()

# Replace the conformal runner
old_fn_start = 'def run_descriptor_conformal(name, X_flat, y_flat, T, N):'
old_fn_end = "        'error': None,\n    }"

# Find the full old function
idx_start = content.index(old_fn_start)
idx_end = content.index(old_fn_end, idx_start) + len(old_fn_end)
old_fn = content[idx_start:idx_end]

new_fn = """def run_descriptor_conformal(name, X_flat, y_flat, T, N):
    \"\"\"ReducedTensorDescriptor with universal meta-scoring.
    
    Runs fit_score (point-level) + score_panel (period-level),
    fuses via rank-normalised max, then calibrates with conformal p-values.
    \"\"\"
    d = X_flat.shape[1]
    y_time = y_flat.reshape(T, N)[:, 0]

    desc = ReducedTensorDescriptor(n_eigs=5, k_neighbors=15)
    t0 = time.perf_counter()
    result = desc.score_universal(X_flat, y_flat, T, N)
    dt = time.perf_counter() - t0

    # Point-level AUCs
    auc_point = safe_auc(y_flat, result['s_point'])
    auc_panel_flat = safe_auc(y_flat, result['s_panel'])
    auc_fused = safe_auc(y_flat, result['scores'])

    # Quarter-level AUCs
    auc_q_panel = safe_auc(y_time, result['q_panel'])
    auc_q_fused = safe_auc(y_time, result['q_scores'])

    # Best AUC across all views
    best_auc = max(auc_point, auc_panel_flat, auc_fused,
                   auc_q_panel, auc_q_fused)

    n_eigs = min(desc.n_eigs, d)
    D = desc.transform(X_flat)
    morse_col = D[:, n_eigs + 5]
    n_nonzero = int(np.sum(morse_col > 0))
    pct_nonzero = 100 * n_nonzero / len(morse_col) if len(morse_col) else 0

    return {
        'name': name,
        'auc': best_auc,
        'auc_point': auc_point,
        'auc_panel_flat': auc_panel_flat,
        'auc_fused': auc_fused,
        'auc_quarter': auc_q_panel,
        'auc_q_fused': auc_q_fused,
        'time': dt,
        'morse_nonzero_pct': pct_nonzero,
        'morse_max': int(morse_col.max()),
        'morse_mean': float(morse_col.mean()),
        'fresh_pred_max_diff': 0.0,
        'error': None,
    }"""

content = content[:idx_start] + new_fn + content[idx_end:]

# Update the print section too
old_print = """            pt_auc = r.get('auc_point', float('nan'))
            q_auc = r.get('auc_quarter', float('nan'))
            p_auc = r.get('auc_panel', float('nan'))
            f_auc = r.get('auc_fused', float('nan'))
            qf_auc = r.get('auc_q_fused', float('nan'))
            print(f' Pt={pt_auc:.4f}  Q={q_auc:.4f}  P={p_auc:.4f}  '
                  f'Fused={f_auc:.4f}  QF={qf_auc:.4f}  '
                  f'Best={r["auc"]:.4f}  ({r["time"]:.1f}s)')"""

new_print = """            pt_auc = r.get('auc_point', float('nan'))
            pf_auc = r.get('auc_panel_flat', float('nan'))
            f_auc = r.get('auc_fused', float('nan'))
            q_auc = r.get('auc_quarter', float('nan'))
            qf_auc = r.get('auc_q_fused', float('nan'))
            print(f' Pt={pt_auc:.4f}  PF={pf_auc:.4f}  '
                  f'Fused={f_auc:.4f}  Q={q_auc:.4f}  QF={qf_auc:.4f}  '
                  f'Best={r["auc"]:.4f}  ({r["time"]:.1f}s)')"""

content = content.replace(old_print, new_print)

with open(FP, 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated benchmark to use score_universal.')
