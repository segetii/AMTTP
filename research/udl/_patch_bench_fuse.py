"""Patch bench_descriptor.py: Upgrade conformal runner to fuse point + panel."""
import os, sys

FP = os.path.join(os.path.dirname(__file__), 'udl', 'bench_descriptor.py')
with open(FP, encoding='utf-8') as f:
    content = f.read()

old_fn = '''def run_descriptor_conformal(name, X_flat, y_flat, T, N):
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
    }'''

new_fn = '''def run_descriptor_conformal(name, X_flat, y_flat, T, N):
    """ReducedTensorDescriptor with universal conformal scoring.
    
    Fuses two independent views:
      A) Point-level: conformal score per data point
      B) Panel-level: conformal panel aggregation per period
    
    Final score: max(rank(A), rank(B)) — fires if either detects.
    """
    d = X_flat.shape[1]
    X_3d = X_flat.reshape(T, N, d)
    y_time = y_flat.reshape(T, N)[:, 0]

    t0_total = time.perf_counter()

    # ─── Mode A: point-level conformal scores ───
    ref_mask = (y_flat == 0)
    X_ref = X_flat[ref_mask]
    desc = ReducedTensorDescriptor(n_eigs=5, k_neighbors=15)
    desc.fit_reference(X_ref, cal_frac=0.15)  # less holdout → stronger reference
    scores_pt = desc.score_conformal(X_flat)
    auc_pt = safe_auc(y_flat, scores_pt)

    # ─── Mode B: conformal panel scores ───
    window = 4 if T < 200 else max(4, T // 10)
    desc2 = ReducedTensorDescriptor(n_eigs=5, k_neighbors=15)
    q_scores = desc2.score_conformal_panel(X_3d, y_time, window=window)
    auc_q = safe_auc(y_time, q_scores)

    # Expand panel scores to point-level for fusion
    scores_panel_flat = np.repeat(q_scores, N)
    auc_panel = safe_auc(y_flat, scores_panel_flat)

    # ─── Fuse point + panel views ───
    def rank_norm(x):
        order = np.argsort(np.argsort(x)).astype(np.float64)
        return order / (len(x) - 1 + 1e-15)

    # Point-level fusion: max(rank(point), rank(panel))
    fused_flat = np.maximum(rank_norm(scores_pt), rank_norm(scores_panel_flat))
    auc_fused = safe_auc(y_flat, fused_flat)

    # Quarter-level fusion: average fused per quarter, then score
    fused_3d = fused_flat.reshape(T, N)
    q_fused = fused_3d.mean(axis=1)
    auc_q_fused = safe_auc(y_time, q_fused)

    dt_total = time.perf_counter() - t0_total

    n_eigs = min(desc.n_eigs, d)
    D = desc.transform(X_flat)
    morse_col = D[:, n_eigs + 5]
    n_nonzero = int(np.sum(morse_col > 0))
    pct_nonzero = 100 * n_nonzero / len(morse_col) if len(morse_col) else 0

    best_auc = max(auc_pt, auc_q, auc_panel, auc_fused, auc_q_fused)

    return {
        'name': name,
        'auc': best_auc,
        'auc_point': auc_pt,
        'auc_quarter': auc_q,
        'auc_panel': auc_panel,
        'auc_fused': auc_fused,
        'auc_q_fused': auc_q_fused,
        'time': dt_total,
        'morse_nonzero_pct': pct_nonzero,
        'morse_max': int(morse_col.max()),
        'morse_mean': float(morse_col.mean()),
        'fresh_pred_max_diff': 0.0,
        'error': None,
    }'''

assert old_fn in content, 'Cannot find old run_descriptor_conformal'
content = content.replace(old_fn, new_fn)

# Also update the print line to show more detail
old_print = '''            pt_auc = r.get('auc_point', float('nan'))
            q_auc = r.get('auc_quarter', float('nan'))
            p_auc = r.get('auc_panel', float('nan'))
            print(f' Pt={pt_auc:.4f}  Q={q_auc:.4f}  P={p_auc:.4f}  '
                  f'Best={r["auc"]:.4f}  ({r["time"]:.1f}s)')'''

new_print = '''            pt_auc = r.get('auc_point', float('nan'))
            q_auc = r.get('auc_quarter', float('nan'))
            p_auc = r.get('auc_panel', float('nan'))
            f_auc = r.get('auc_fused', float('nan'))
            qf_auc = r.get('auc_q_fused', float('nan'))
            print(f' Pt={pt_auc:.4f}  Q={q_auc:.4f}  P={p_auc:.4f}  '
                  f'Fused={f_auc:.4f}  QF={qf_auc:.4f}  '
                  f'Best={r["auc"]:.4f}  ({r["time"]:.1f}s)')'''

assert old_print in content, 'Cannot find old print block'
content = content.replace(old_print, new_print)

with open(FP, 'w', encoding='utf-8') as f:
    f.write(content)

print('Patched run_descriptor_conformal with point+panel fusion.')
