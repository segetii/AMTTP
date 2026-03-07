"""
MISSED ANOMALY STRUCTURAL INVESTIGATION
========================================
For each dataset, identifies anomalies that are systematically missed
across multiple methods, then analyses:
  1. Feature-space geometry (distance to normal centroid, local density)
  2. Representation-space geometry (which operator dims are informative)
  3. Cross-dataset pattern: is there a unifying formula?
  4. Taxonomy: what structural class does each missed anomaly type fall into?
"""
import sys, os, json, warnings
import numpy as np
from copy import deepcopy
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
from scipy.stats import ks_2samp, mannwhitneyu

warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(__file__))

from udl.compare_sota import load_all_datasets
from udl.pipeline import UDLPipeline
from udl.rank_fusion import RankFusionPipeline
from udl.meta_fusion import MetaFusionPipeline, default_operators
from udl.bsdt_bridge import BSDTSpectrum
from udl.experimental_spectra import (
    FourierBasisSpectrum, BSplineBasisSpectrum,
    WaveletBasisSpectrum, LegendreBasisSpectrum, PhaseCurveSpectrum,
)

DATASETS = ['mammography','pendigits','annthyroid','arrhythmia','satellite','glass','cardio']

def lean_ops():    return default_operators()

def comb_a_ops():
    return [
        ('fourier',  FourierBasisSpectrum(n_coeffs=8)),
        ('bspline',  BSplineBasisSpectrum(n_basis=6)),
        ('wavelet',  WaveletBasisSpectrum(max_levels=4)),
        ('legendre', LegendreBasisSpectrum(n_degree=6)),
        ('phase',    PhaseCurveSpectrum()),
    ]

def bsdt_ops():
    ops = default_operators()
    ops.append(('bsdt', BSDTSpectrum()))
    return ops

# ── helpers ──────────────────────────────────────────────────────────────────

def get_scores(pipe_fn, X_tr, X_te, y_tr):
    pipe = pipe_fn()
    pipe.fit(X_tr, y_tr)
    return pipe.score(X_te)

def missed_mask(scores, y_te, top_k):
    """Return boolean mask: True = anomaly that was NOT in top-k predictions."""
    thresh = np.percentile(scores, 100*(1-top_k))
    anom_idx = np.where(y_te == 1)[0]
    missed = anom_idx[scores[anom_idx] < thresh]
    caught = anom_idx[scores[anom_idx] >= thresh]
    return missed, caught

def mahal_dist(X, mu, cov_inv):
    d = X - mu
    return np.sqrt(np.einsum('ij,jk,ik->i', d, cov_inv, d))

def safe_cov_inv(X_norm):
    cov = np.cov(X_norm.T)
    try:
        return np.linalg.inv(cov + 1e-6*np.eye(cov.shape[0]))
    except:
        return np.eye(cov.shape[0])

def knn_density(X_ref, X_query, k=5):
    """Return mean k-NN distance of each query point to reference set."""
    nn = NearestNeighbors(n_neighbors=min(k, len(X_ref)-1))
    nn.fit(X_ref)
    dist, _ = nn.kneighbors(X_query)
    return dist.mean(axis=1)

def overlap_score(a, b):
    """Bhattacharyya coefficient — 0=no overlap, 1=identical."""
    mu_a, s_a = a.mean(), a.std()+1e-9
    mu_b, s_b = b.mean(), b.std()+1e-9
    return (0.25 * np.log(0.25*(s_a**2/s_b**2 + s_b**2/s_a**2 + 2))
            + 0.25 * (mu_a-mu_b)**2/(s_a**2+s_b**2))

def rank_discriminability(X_norm, X_anom_caught, X_anom_missed, feature_names=None):
    """
    For each feature, compute AUC(normal vs missed) and AUC(normal vs caught).
    Returns discriminability gap per feature.
    """
    n_feat = X_norm.shape[1]
    gap = []
    for j in range(n_feat):
        fn = feature_names[j] if feature_names else str(j)
        if len(X_anom_caught) > 0:
            auc_caught = roc_auc_score(
                np.concatenate([np.zeros(len(X_norm)), np.ones(len(X_anom_caught))]),
                np.concatenate([X_norm[:,j], X_anom_caught[:,j]])
            )
        else:
            auc_caught = 0.5
        if len(X_anom_missed) > 0:
            auc_missed = roc_auc_score(
                np.concatenate([np.zeros(len(X_norm)), np.ones(len(X_anom_missed))]),
                np.concatenate([X_norm[:,j], X_anom_missed[:,j]])
            )
        else:
            auc_missed = 0.5
        gap.append((fn, auc_caught, auc_missed, auc_caught - auc_missed))
    return sorted(gap, key=lambda x: -abs(x[3]))

# ── taxonomy classifier ───────────────────────────────────────────────────────

def classify_anomaly_type(d_mahal_missed, d_mahal_caught, d_knn_missed, d_knn_caught,
                           n_missed, n_total_anom):
    """
    Rule-based taxonomy assignment for missed anomalies.
    Returns (type_name, description, formula)
    """
    # Mahalanobis position
    med_missed = np.median(d_mahal_missed) if len(d_mahal_missed) else 0
    med_caught = np.median(d_mahal_caught) if len(d_mahal_caught) else 0

    # KNN density (lower = more isolated; higher = embedded in normal)
    med_knn_missed = np.median(d_knn_missed) if len(d_knn_missed) else 0
    med_knn_caught = np.median(d_knn_caught) if len(d_knn_caught) else 0

    miss_rate = n_missed / max(n_total_anom, 1)

    if miss_rate < 0.05:
        return 'NEGLIGIBLE', 'Method catches >95% — near-perfect', 'N/A'

    # Type 1: Boundary anomalies — close to normal centroid, high KNN proximity to normals
    if med_missed < med_caught * 0.9 and med_knn_missed < med_knn_caught * 1.1:
        return ('TYPE-1: BOUNDARY',
                'Low Mahalanobis dist, embedded in normal cloud — margin violation',
                'δ(x) = ‖x - μ_N‖_Σ⁻¹ < θ_boundary')

    # Type 2: Manifold anomalies — high KNN distance to normals but low global Mahal
    if med_knn_missed > med_knn_caught * 1.3 and med_missed < med_caught * 1.1:
        return ('TYPE-2: MANIFOLD-GAP',
                'Isolated from normals locally but not globally displaced — off-manifold',
                'δ(x) = min_k d(x, X_N) > θ_knn  ∧  ‖x-μ_N‖_Σ⁻¹ ≈ ‖x_caught-μ_N‖_Σ⁻¹')

    # Type 3: Distributed anomalies — anomalous in many low-signal dimensions
    if med_missed < med_caught * 1.1 and med_knn_missed < med_knn_caught * 1.2:
        return ('TYPE-3: DISTRIBUTED',
                'No single discriminative feature — anomaly spread across many weak dims',
                'δ(x) = Σⱼ wⱼ·(xⱼ-μʲ_N)²/σʲ²  where all wⱼ small (no saturated dim)')

    # Type 4: Scale anomalies — normal direction but wrong magnitude
    if med_missed > med_caught * 0.8 and med_knn_missed > med_knn_caught * 0.9:
        return ('TYPE-4: SCALE-SHIFT',
                'Anomaly lies along normal data directions at atypical magnitude',
                'x = μ_N + α·v_normal,  α outside [μ_α ± 3σ_α]')

    return ('TYPE-5: MIXED',
            'Combination of boundary + distributed effects',
            'δ(x) = composite score across weak boundary + weak local signals')

# ── main analysis ─────────────────────────────────────────────────────────────

def main():
    os.chdir('c:/amttp/research/udl')
    ds_map = load_all_datasets()

    cross_dataset_evidence = {}

    for ds_name in DATASETS:
        X, y = ds_map[ds_name]
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=42
        )
        anom_rate = y_te.mean()
        top_k = min(max(anom_rate * 2, 0.05), 0.30)

        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_te_s  = scaler.transform(X_te)

        X_norm_tr = X_tr_s[y_tr == 0]
        mu_norm   = X_norm_tr.mean(axis=0)
        cov_inv   = safe_cov_inv(X_norm_tr)

        print(f'\n{"="*70}')
        print(f'  DATASET: {ds_name.upper()}')
        print(f'  N_test={len(y_te)}, anomalies={int(y_te.sum())}, '
              f'features={X.shape[1]}, top_k={top_k:.2f}')
        print(f'{"="*70}')

        # Run 3 methods, collect missed sets
        method_defs = {
            'Fuse-lean':       lambda: RankFusionPipeline(operators=lean_ops(), fusion='mean'),
            'BSDT-Fuse':       lambda: RankFusionPipeline(operators=bsdt_ops(), fusion='mean'),
            'MetaFusion-CombA': lambda: MetaFusionPipeline(
                                    operators=comb_a_ops(),
                                    strategies=['fisher','fusion','quadsurf','qs_expo','signed_lr','magnifier'],
                                    verbose=False),
        }

        all_missed_sets = []
        method_missed = {}
        for mname, fn in method_defs.items():
            try:
                scores = get_scores(fn, X_tr, X_te, y_tr)
                missed_idx, caught_idx = missed_mask(scores, y_te, top_k)
                auc = roc_auc_score(y_te, scores)
                n_m  = len(missed_idx)
                n_tot = int(y_te.sum())
                print(f'\n  [{mname}]  AUC={auc:.4f}  '
                      f'caught={n_tot-n_m}/{n_tot}  missed={n_m}')
                method_missed[mname] = set(missed_idx.tolist())
                all_missed_sets.append(set(missed_idx.tolist()))
            except Exception as e:
                print(f'  [{mname}]  ERROR: {e}')

        if not all_missed_sets:
            continue

        # Consistently missed = missed by ALL methods
        consistent_missed = set.intersection(*all_missed_sets) if all_missed_sets else set()
        any_caught = set.union(*[
            set(np.where(y_te==1)[0].tolist()) - ms
            for ms in all_missed_sets
        ]) if all_missed_sets else set()

        print(f'\n  Consistently missed (all 3 methods): {len(consistent_missed)}'
              f'/{int(y_te.sum())} ({100*len(consistent_missed)/max(y_te.sum(),1):.1f}%)')

        if len(consistent_missed) == 0:
            print('  → No consistent misses — all anomalies caught by at least one method')
            continue

        missed_list  = sorted(consistent_missed)
        caught_list  = sorted(any_caught)

        X_missed = X_te_s[missed_list]
        X_caught = X_te_s[caught_list] if caught_list else np.zeros((0, X_te_s.shape[1]))
        X_norm_te = X_te_s[y_te == 0]

        # ── Geometry analysis ──────────────────────────────────────────────
        d_mahal_missed = mahal_dist(X_missed, mu_norm, cov_inv)
        d_mahal_caught = mahal_dist(X_caught, mu_norm, cov_inv) if len(X_caught) else np.array([0])
        d_mahal_norm   = mahal_dist(X_norm_te, mu_norm, cov_inv)

        d_knn_missed = knn_density(X_norm_tr, X_missed, k=min(5, len(X_norm_tr)-1))
        d_knn_caught = knn_density(X_norm_tr, X_caught, k=min(5, len(X_norm_tr)-1)) if len(X_caught) else np.array([0])
        d_knn_norm   = knn_density(X_norm_tr, X_norm_te[:200], k=min(5, len(X_norm_tr)-1))

        print(f'\n  GEOMETRY (standardised feature space):')
        print(f'    Mahalanobis dist  missed={np.median(d_mahal_missed):.2f}  '
              f'caught={np.median(d_mahal_caught):.2f}  '
              f'normal={np.median(d_mahal_norm):.2f}')
        print(f'    kNN-dist-to-norm  missed={np.median(d_knn_missed):.3f}  '
              f'caught={np.median(d_knn_caught):.3f}  '
              f'normal={np.median(d_knn_norm):.3f}')

        ratio_mahal = np.median(d_mahal_missed) / (np.median(d_mahal_caught)+1e-9)
        ratio_knn   = np.median(d_knn_missed)   / (np.median(d_knn_norm)+1e-9)

        print(f'    Mahal(missed)/Mahal(caught) = {ratio_mahal:.3f}  '
              f'(< 1 = missed are CLOSER to normal cloud)')
        print(f'    kNN(missed)/kNN(normal)     = {ratio_knn:.3f}  '
              f'(~1 = missed BLEND into normal locally)')

        # ── Per-feature discriminability ───────────────────────────────────
        print(f'\n  FEATURE DISCRIMINABILITY (top 5 gaps):')
        feat_gaps = rank_discriminability(X_norm_te, X_caught, X_missed)
        for fname, auc_c, auc_m, gap in feat_gaps[:5]:
            direction = '↓ LOST' if gap > 0.08 else ('↑ GAINED' if gap < -0.08 else '  ~same')
            print(f'    feat-{fname:>3s}  AUC(caught)={auc_c:.3f}  '
                  f'AUC(missed)={auc_m:.3f}  gap={gap:+.3f}  {direction}')

        # ── KS test: are missed anomalies statistically different from caught? ──
        if len(X_caught) >= 3 and len(X_missed) >= 2:
            ks_stats = []
            for j in range(X.shape[1]):
                stat, p = ks_2samp(X_missed[:,j], X_caught[:,j])
                ks_stats.append((j, stat, p))
            ks_stats.sort(key=lambda x: -x[0])
            # Dominant separation dimension
            top_ks = max(ks_stats, key=lambda x: x[1])
            print(f'\n  KS-test (missed vs caught): max separation on feature {top_ks[0]}'
                  f'  D={top_ks[1]:.3f}  p={top_ks[2]:.4f}')
            sig = sum(1 for _,_,p in ks_stats if p < 0.05)
            print(f'    Features with significant difference (p<0.05): {sig}/{X.shape[1]}')

        # ── Taxonomy ──────────────────────────────────────────────────────
        atype, desc, formula = classify_anomaly_type(
            d_mahal_missed, d_mahal_caught,
            d_knn_missed, d_knn_caught,
            len(consistent_missed), int(y_te.sum())
        )
        print(f'\n  ANOMALY TYPE: {atype}')
        print(f'  Description: {desc}')
        print(f'  Formula:     {formula}')

        # ── Cross-dataset evidence accumulation ───────────────────────────
        cross_dataset_evidence[ds_name] = {
            'type':       atype,
            'miss_rate':  len(consistent_missed)/max(int(y_te.sum()),1),
            'ratio_mahal': float(ratio_mahal),
            'ratio_knn':   float(ratio_knn),
            'n_missed':   len(consistent_missed),
            'n_anom':     int(y_te.sum()),
            'n_features': X.shape[1],
            'formula':    formula,
        }

    # ── Cross-dataset synthesis ───────────────────────────────────────────────
    print(f'\n\n{"#"*70}')
    print('  CROSS-DATASET STRUCTURAL SYNTHESIS')
    print(f'{"#"*70}')
    print(f'  {"Dataset":<16s}  {"Type":<25s}  {"Miss%":>6s}  '
          f'{"MahalRatio":>10s}  {"kNNRatio":>8s}')
    print('  ' + '-'*75)
    for ds, ev in cross_dataset_evidence.items():
        print(f'  {ds:<16s}  {ev["type"]:<25s}  '
              f'{100*ev["miss_rate"]:>5.1f}%  '
              f'{ev["ratio_mahal"]:>10.3f}  '
              f'{ev["ratio_knn"]:>8.3f}')

    print(f'\n  UNIFYING OBSERVATIONS:')

    # Check if mahal ratio < 1 for most (missed are closer to normal)
    mahal_ratios = [ev['ratio_mahal'] for ev in cross_dataset_evidence.values()]
    frac_closer = sum(1 for r in mahal_ratios if r < 1.0) / len(mahal_ratios)
    print(f'\n  (1) Fraction of datasets where missed anomalies are CLOSER to normal'
          f'    centroid than caught: {frac_closer:.0%}')

    knn_ratios = [ev['ratio_knn'] for ev in cross_dataset_evidence.values()]
    frac_blend = sum(1 for r in knn_ratios if r < 1.5) / len(knn_ratios)
    print(f'  (2) Fraction of datasets where missed anomalies BLEND locally'
          f' into normals (kNN ratio<1.5): {frac_blend:.0%}')

    types = [ev['type'].split(':')[0] for ev in cross_dataset_evidence.values()]
    from collections import Counter
    type_counts = Counter(types)
    print(f'\n  (3) Taxonomy frequency: {dict(type_counts)}')

    print(f'''
  MASTER FORMULA — MISSED ANOMALY CONDITION
  ══════════════════════════════════════════

  An anomaly x is systematically missed when:

      miss(x) ← [δ_global(x) < θ_G]  AND  
                [∀j: disc_j(x) < θ_local]

  where:
      δ_global(x) = ‖x − μ_N‖_Σ⁻¹          (Mahalanobis = global displacement)
      disc_j(x)   = |xⱼ − μ_Nⱼ| / σ_Nⱼ     (per-dim discriminability)
      θ_G         = percentile-based global threshold
      θ_local     = per-dim saturation threshold

  This characterises BOUNDARY-EMBEDDED anomalies:
  • Globally close to normal cloud (low Mahalanobis)
  • No single feature stands out (all disc_j weak)
  • BUT locally anomalous in a subspace combination

  The COVERAGE GAP formula:
      gap(M, D) = E_x[1 - max_j disc_j(x)]   for x ∈ Anomaly_missed

  Operator families that partially close the gap:
      CombA-Fisher:     activates basis-frequency subspaces
      BSDT-Fuse:        spectral boundary decomposition
      MetaFusion-CombA: votes across all 6 scoring strategies
                        (catches residual boundary anomalies)
''')

if __name__ == '__main__':
    main()
