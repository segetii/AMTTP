"""
Correlation Audit — find redundant operators and scoring strategies.
Computes per-sample Spearman correlation across ALL operators and strategies,
then recommends a lean non-redundant subset for the final paper.
"""
import gc, sys, os, copy, json
import numpy as np
from scipy.stats import spearmanr
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from copy import deepcopy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from udl.compare_sota import load_all_datasets
from udl.pipeline import UDLPipeline
from udl.rank_fusion import RankFusionPipeline

# ── All operators ──
from udl.experimental_spectra import (
    FourierBasisSpectrum, BSplineBasisSpectrum,
    WaveletBasisSpectrum, LegendreBasisSpectrum,
    PhaseCurveSpectrum,
)
from udl.spectra import (
    StatisticalSpectrum, GeometricSpectrum, ExponentialSpectrum,
    ReconstructionSpectrum, RankOrderSpectrum,
)
from udl.new_spectra import (
    TopologicalSpectrum, DependencyCopulaSpectrum,
    KernelRKHSSpectrum, CompressibilitySpectrum,
)

# ── Every operator we have (name, instance) ──
ALL_OPS = [
    ("Fourier",     FourierBasisSpectrum(n_coeffs=8)),
    ("BSpline",     BSplineBasisSpectrum(n_basis=6)),
    ("Wavelet",     WaveletBasisSpectrum(max_levels=4)),
    ("Legendre",    LegendreBasisSpectrum(n_degree=6)),
    ("Phase",       PhaseCurveSpectrum()),
    ("Statistical", StatisticalSpectrum()),
    ("Geometric",   GeometricSpectrum()),
    ("Exponential", ExponentialSpectrum()),
    ("Recon",       ReconstructionSpectrum()),
    ("Rank",        RankOrderSpectrum()),
    ("Topo",        TopologicalSpectrum(k=15)),
    ("Dependency",  DependencyCopulaSpectrum()),
    ("Kernel",      KernelRKHSSpectrum()),
    ("Compress",    CompressibilitySpectrum()),
]


def get_solo_scores(op_name, op_instance, X_tr, X_te, y_tr):
    """Get per-sample anomaly scores from a single operator via Fisher."""
    try:
        pipe = UDLPipeline(
            operators=[(op_name, copy.deepcopy(op_instance))],
            centroid_method='auto',
            projection_method='fisher',
        )
        pipe.fit(X_tr, y_tr)
        return pipe.score(X_te)
    except Exception as e:
        print(f"    SKIP {op_name}: {e}")
        return None
    finally:
        gc.collect()


def cov_at_k(scores, y, k):
    anom = np.where(y == 1)[0]
    if len(anom) == 0:
        return 0.0
    th = np.percentile(scores, 100 * (1 - k))
    return float(np.sum(scores[anom] >= th)) / len(anom)


def main():
    datasets = load_all_datasets()
    ds_order = [d for d in ["synthetic", "mimic", "mammography", "shuttle", "pendigits"]
                if d in datasets]

    # ── Phase 1: Per-operator solo scores on each dataset ──
    print("=" * 80)
    print("  PHASE 1: Solo operator scores (Fisher projection, single op each)")
    print("=" * 80)

    all_scores = {}  # {ds_name: {op_name: scores_array}}
    all_aucs = {}    # {op_name: [auc_per_ds]}
    all_covs = {}    # {op_name: [cov_per_ds]}

    for ds_name in ds_order:
        X, y = datasets[ds_name]
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=42
        )
        anom_rate = y_te.mean()
        top_k = min(max(anom_rate * 2, 0.05), 0.30)

        print(f"\n  {ds_name} (n={len(X_te)}, anom={int(y_te.sum())}, top_k={top_k:.2f})")
        ds_scores = {}

        for op_name, op_inst in ALL_OPS:
            scores = get_solo_scores(op_name, op_inst, X_tr, X_te, y_tr)
            if scores is not None:
                ds_scores[op_name] = scores
                auc = float(roc_auc_score(y_te, scores))
                cov = cov_at_k(scores, y_te, top_k)
                all_aucs.setdefault(op_name, []).append(auc)
                all_covs.setdefault(op_name, []).append(cov)
                print(f"    {op_name:<14s} AUC={auc:.4f}  Cov={100*cov:.0f}%")

        all_scores[ds_name] = ds_scores
        del X, y, X_tr, X_te, y_tr, y_te
        gc.collect()

    # ── Solo summary ──
    print(f"\n{'=' * 80}")
    print("  SOLO OPERATOR SUMMARY (mean across datasets)")
    print(f"{'=' * 80}")
    op_summary = []
    for op_name in [o[0] for o in ALL_OPS]:
        if op_name in all_aucs:
            mAUC = np.mean(all_aucs[op_name])
            mCov = np.mean(all_covs[op_name])
            minCov = min(all_covs[op_name])
            op_summary.append((op_name, mAUC, mCov, minCov))
            print(f"  {op_name:<14s} mAUC={mAUC:.4f}  mCov={100*mCov:.0f}%  minCov={100*minCov:.0f}%")

    # ── Phase 2: Spearman correlation between operators ──
    print(f"\n{'=' * 80}")
    print("  PHASE 2: Spearman correlation between operator scores")
    print(f"{'=' * 80}")

    # Average correlation across datasets
    op_names = [o[0] for o in ALL_OPS if o[0] in all_scores.get(ds_order[0], {})]
    n = len(op_names)
    avg_corr = np.zeros((n, n))
    n_ds = 0

    for ds_name in ds_order:
        ds_sc = all_scores[ds_name]
        valid = [o for o in op_names if o in ds_sc]
        if len(valid) < 2:
            continue
        # Build score matrix
        S = np.column_stack([ds_sc[o] for o in valid])
        rho, _ = spearmanr(S)
        if rho.ndim == 0:
            continue
        # Map back to full matrix
        for i, oi in enumerate(valid):
            for j, oj in enumerate(valid):
                ii = op_names.index(oi)
                jj = op_names.index(oj)
                avg_corr[ii, jj] += rho[i, j]
        n_ds += 1

    if n_ds > 0:
        avg_corr /= n_ds

    # Print correlation matrix
    header = "              " + "".join(f"{o[:6]:>7s}" for o in op_names)
    print(f"  {header}")
    for i, oi in enumerate(op_names):
        row = f"  {oi:<14s}"
        for j in range(n):
            v = avg_corr[i, j]
            row += f"  {v:5.2f}"
        print(row)

    # ── Phase 3: Find highly correlated pairs ──
    print(f"\n  REDUNDANT PAIRS (Spearman > 0.85):")
    redundant = []
    for i in range(n):
        for j in range(i + 1, n):
            if avg_corr[i, j] > 0.85:
                print(f"    {op_names[i]} <-> {op_names[j]}: rho={avg_corr[i,j]:.3f}")
                redundant.append((op_names[i], op_names[j], avg_corr[i, j]))

    # ── Phase 4: Greedy selection — pick non-redundant ops by coverage ──
    print(f"\n{'=' * 80}")
    print("  PHASE 3: Greedy non-redundant operator selection")
    print(f"{'=' * 80}")

    # Sort by mCov descending
    op_summary.sort(key=lambda x: x[2], reverse=True)
    selected = []
    selected_idx = []

    for op_name, mAUC, mCov, minCov in op_summary:
        if op_name not in op_names:
            continue
        idx = op_names.index(op_name)
        # Check if too correlated with any already selected
        too_close = False
        for sidx in selected_idx:
            if avg_corr[idx, sidx] > 0.80:
                too_close = True
                print(f"  SKIP {op_name} (rho={avg_corr[idx,sidx]:.2f} with {op_names[sidx]})")
                break
        if not too_close:
            selected.append(op_name)
            selected_idx.append(idx)
            print(f"  SELECT {op_name}  mCov={100*mCov:.0f}%  mAUC={mAUC:.4f}")

    print(f"\n  FINAL NON-REDUNDANT SET ({len(selected)} ops): {selected}")

    # ── Phase 5: Test strategies on the selected set ──
    print(f"\n{'=' * 80}")
    print("  PHASE 4: Strategies on selected operators")
    print(f"{'=' * 80}")

    # Map names back to instances
    op_map = {name: inst for name, inst in ALL_OPS}
    selected_ops = [(name, op_map[name]) for name in selected]

    strategies = {}  # {strat_name: {ds: scores}}

    for ds_name in ds_order:
        X, y = datasets[ds_name]
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=42
        )
        anom_rate = y_te.mean()
        top_k = min(max(anom_rate * 2, 0.05), 0.30)
        print(f"\n  {ds_name}:")

        def run_strat(name, builder_fn):
            try:
                pipe = builder_fn()
                pipe.fit(X_tr, y_tr)
                s = pipe.score(X_te)
                auc = float(roc_auc_score(y_te, s))
                cov = cov_at_k(s, y_te, top_k)
                strategies.setdefault(name, {})[ds_name] = {
                    "scores": s, "auc": auc, "cov": cov, "y": y_te, "top_k": top_k
                }
                print(f"    {name:<20s} AUC={auc:.4f}  Cov={100*cov:.0f}%")
                return s
            except Exception as e:
                print(f"    {name:<20s} ERR: {e}")
                return None
            finally:
                gc.collect()

        # A. Fisher on selected ops
        run_strat("Fisher", lambda: UDLPipeline(
            operators=deepcopy(selected_ops), centroid_method='auto',
            projection_method='fisher'))

        # B. RankFusion on selected ops
        run_strat("RankFuse", lambda: RankFusionPipeline(
            operators=deepcopy(selected_ops), fusion='mean'))

        # C. QuadSurf on selected ops
        run_strat("QuadSurf", lambda: UDLPipeline(
            operators=deepcopy(selected_ops), centroid_method='auto',
            projection_method='fisher', mfls_method='quadratic'))

        # D. QuadSurf+ExpoGate on selected ops
        run_strat("QS+Expo", lambda: UDLPipeline(
            operators=deepcopy(selected_ops), centroid_method='auto',
            projection_method='fisher', mfls_method='quadratic_smooth'))

        # E. SignedLR on selected ops
        run_strat("SignedLR", lambda: UDLPipeline(
            operators=deepcopy(selected_ops), centroid_method='auto',
            projection_method='fisher', mfls_method='logistic'))

        del X, y, X_tr, X_te, y_tr, y_te
        gc.collect()

    # ── Phase 6: Correlation between strategies ──
    print(f"\n{'=' * 80}")
    print("  PHASE 5: Spearman correlation between STRATEGIES")
    print(f"{'=' * 80}")

    strat_names = list(strategies.keys())
    ns = len(strat_names)
    strat_corr = np.zeros((ns, ns))
    n_ds = 0

    for ds_name in ds_order:
        valid = [s for s in strat_names if ds_name in strategies.get(s, {})]
        if len(valid) < 2:
            continue
        S = np.column_stack([strategies[s][ds_name]["scores"] for s in valid])
        rho, _ = spearmanr(S)
        if rho.ndim == 0:
            continue
        for i, si in enumerate(valid):
            for j, sj in enumerate(valid):
                ii = strat_names.index(si)
                jj = strat_names.index(sj)
                strat_corr[ii, jj] += rho[i, j]
        n_ds += 1

    if n_ds > 0:
        strat_corr /= n_ds

    header = "                    " + "".join(f"{s[:8]:>9s}" for s in strat_names)
    print(f"  {header}")
    for i, si in enumerate(strat_names):
        row = f"  {si:<20s}"
        for j in range(ns):
            row += f"  {strat_corr[i,j]:6.3f}"
        print(row)

    # ── Final summary ──
    print(f"\n{'=' * 80}")
    print("  FINAL SUMMARY")
    print(f"{'=' * 80}")

    print(f"\n  Non-redundant operators ({len(selected)}): {selected}")
    print(f"\n  Strategy results (mean across {len(ds_order)} datasets):")
    for sn in strat_names:
        aucs = [strategies[sn][d]["auc"] for d in ds_order if d in strategies[sn]]
        covs = [strategies[sn][d]["cov"] for d in ds_order if d in strategies[sn]]
        if aucs:
            print(f"    {sn:<20s} mAUC={np.mean(aucs):.4f}  mCov={100*np.mean(covs):.0f}%  minCov={100*min(covs):.0f}%")

    # ── Save for further analysis ──
    results = {
        "selected_ops": selected,
        "solo": {op: {"mAUC": float(np.mean(all_aucs[op])),
                       "mCov": float(np.mean(all_covs[op])),
                       "minCov": float(min(all_covs[op]))}
                 for op in selected if op in all_aucs},
        "strategies": {
            sn: {d: {"auc": strategies[sn][d]["auc"], "cov": strategies[sn][d]["cov"]}
                 for d in ds_order if d in strategies[sn]}
            for sn in strat_names
        },
        "op_correlation": {
            f"{op_names[i]}-{op_names[j]}": float(avg_corr[i, j])
            for i in range(n) for j in range(i + 1, n)
            if avg_corr[i, j] > 0.5
        },
        "strat_correlation": {
            f"{strat_names[i]}-{strat_names[j]}": float(strat_corr[i, j])
            for i in range(ns) for j in range(i + 1, ns)
        },
    }
    out_path = os.path.join(SCRIPT_DIR, "correlation_audit.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Saved to {out_path}")


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    main()
