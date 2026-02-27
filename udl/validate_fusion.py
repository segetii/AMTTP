"""
Final validation: RankFusionPipeline vs Fisher UDLPipeline
==========================================================
Test the coverage-optimal 4-operator stack:
  Phase + Topological + KernelRKHS + RankOrder

Metrics: AUC, Coverage at optimal-k, per-operator decomposition
"""
import numpy as np
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

from udl.compare_sota import load_all_datasets
from udl.pipeline import UDLPipeline
from udl.rank_fusion import RankFusionPipeline
from udl.experimental_spectra import PhaseCurveSpectrum
from udl.spectra import RankOrderSpectrum
from udl.new_spectra import TopologicalSpectrum, KernelRKHSSpectrum


def coverage_at_k(scores, y_test, k_pct):
    """Fraction of true anomalies in top k% of scores."""
    anom_idx = np.where(y_test == 1)[0]
    if len(anom_idx) == 0:
        return 0.0
    threshold = np.percentile(scores, 100 * (1 - k_pct))
    return np.sum(scores[anom_idx] >= threshold) / len(anom_idx)


def count_detected(scores, y_test, k_pct):
    """Count of anomalies detected."""
    anom_idx = np.where(y_test == 1)[0]
    threshold = np.percentile(scores, 100 * (1 - k_pct))
    return int(np.sum(scores[anom_idx] >= threshold)), len(anom_idx)


def main():
    ds = load_all_datasets()
    ds_order = [d for d in ["synthetic", "mimic", "mammography", "shuttle", "pendigits"]
                if d in ds]

    OPS = [
        ("phase", PhaseCurveSpectrum()),
        ("topo", TopologicalSpectrum(k=15)),
        ("kernel", KernelRKHSSpectrum()),
        ("rank", RankOrderSpectrum()),
    ]

    seeds = [42, 123, 7, 99, 2024]

    print("=" * 100)
    print("  FINAL VALIDATION: RankFusionPipeline vs Fisher UDLPipeline")
    print("  Stack: Phase + Topological + KernelRKHS + RankOrder (4 ops)")
    print(f"  Seeds: {seeds}")
    print("=" * 100)

    fisher_aucs = {d: [] for d in ds_order}
    fisher_covs = {d: [] for d in ds_order}
    fusion_aucs = {d: [] for d in ds_order}
    fusion_covs = {d: [] for d in ds_order}

    for seed in seeds:
        print(f"\n  --- Seed {seed} ---")
        for ds_name in ds_order:
            X, y = ds[ds_name]
            X_tr, X_te, y_tr, y_te = train_test_split(
                X, y, test_size=0.3, stratify=y, random_state=seed
            )
            anom_rate = y_te.mean()
            top_k = min(max(anom_rate * 2, 0.05), 0.30)

            # ── Fisher pipeline ──
            from copy import deepcopy
            try:
                fisher_pipe = UDLPipeline(
                    operators=deepcopy(OPS),
                    centroid_method='auto',
                    projection_method='fisher',
                )
                fisher_pipe.fit(X_tr, y_tr)
                f_scores = fisher_pipe.score(X_te)
                f_auc = roc_auc_score(y_te, f_scores)
                f_det, f_n = count_detected(f_scores, y_te, top_k)
                f_cov = f_det / f_n if f_n > 0 else 0
            except Exception as e:
                f_auc, f_cov, f_det, f_n = 0, 0, 0, int(y_te.sum())
                print(f"    {ds_name:<14s}  Fisher FAILED: {e}")
            fisher_aucs[ds_name].append(f_auc)
            fisher_covs[ds_name].append(f_cov)

            # ── Rank fusion pipeline ──
            try:
                fuse_pipe = RankFusionPipeline(
                    operators=deepcopy(OPS),
                    centroid_method='auto',
                    fusion='mean',
                )
                fuse_pipe.fit(X_tr, y_tr)
                r_scores = fuse_pipe.score(X_te)
                r_auc = roc_auc_score(y_te, r_scores)
                r_det, r_n = count_detected(r_scores, y_te, top_k)
                r_cov = r_det / r_n if r_n > 0 else 0
            except Exception as e:
                r_auc, r_cov, r_det, r_n = 0, 0, 0, int(y_te.sum())
                print(f"    {ds_name:<14s}  RankFuse FAILED: {e}")
            fusion_aucs[ds_name].append(r_auc)
            fusion_covs[ds_name].append(r_cov)

            print(f"    {ds_name:<14s}  Fisher: AUC={f_auc:.4f} Cov={f_det}/{f_n} ({100*f_cov:.0f}%)  "
                  f"RankFuse: AUC={r_auc:.4f} Cov={r_det}/{r_n} ({100*r_cov:.0f}%)")

    # ── Summary ──
    print(f"\n\n{'='*100}")
    print("  MEAN ± STD ACROSS 5 SEEDS")
    print(f"{'='*100}")
    print(f"  {'Dataset':<14s}  {'Fisher AUC':>12s}  {'Fisher Cov':>12s}  {'RankFuse AUC':>12s}  {'RankFuse Cov':>12s}  {'Winner':>10s}")
    print("-" * 80)

    all_f_auc, all_f_cov = [], []
    all_r_auc, all_r_cov = [], []

    for ds_name in ds_order:
        fa = np.array(fisher_aucs[ds_name])
        fc = np.array(fisher_covs[ds_name])
        ra = np.array(fusion_aucs[ds_name])
        rc = np.array(fusion_covs[ds_name])

        winner_auc = "Fusion" if ra.mean() > fa.mean() else "Fisher"
        winner_cov = "Fusion" if rc.mean() > fc.mean() else "Fisher"

        print(f"  {ds_name:<14s}  {fa.mean():.4f}±{fa.std():.3f}  {100*fc.mean():>5.1f}%±{100*fc.std():.1f}  "
              f"{ra.mean():.4f}±{ra.std():.3f}  {100*rc.mean():>5.1f}%±{100*rc.std():.1f}  "
              f"AUC:{winner_auc} COV:{winner_cov}")

        all_f_auc.append(fa.mean())
        all_f_cov.append(fc.mean())
        all_r_auc.append(ra.mean())
        all_r_cov.append(rc.mean())

    print("-" * 80)
    print(f"  {'MEAN':<14s}  {np.mean(all_f_auc):.4f}          {100*np.mean(all_f_cov):>5.1f}%          "
          f"{np.mean(all_r_auc):.4f}          {100*np.mean(all_r_cov):>5.1f}%")
    print(f"  {'MIN':<14s}  {min(all_f_auc):.4f}          {100*min(all_f_cov):>5.1f}%          "
          f"{min(all_r_auc):.4f}          {100*min(all_r_cov):>5.1f}%")

    # ── Per-operator decomposition (seed=42, mammography only) ──
    if "mammography" in ds:
        print(f"\n\n{'='*100}")
        print("  PER-OPERATOR DECOMPOSITION (mammography, seed=42)")
        print(f"{'='*100}")

        X, y = ds["mammography"]
        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, stratify=y, random_state=42)
        anom_rate = y_te.mean()
        top_k = min(max(anom_rate * 2, 0.05), 0.30)

        from copy import deepcopy
        fuse = RankFusionPipeline(operators=deepcopy(OPS), fusion='mean')
        fuse.fit(X_tr, y_tr)
        decomp = fuse.score_decomposition(X_te)

        anom_idx = np.where(y_te == 1)[0]
        print(f"\n  Anomaly rate: {anom_rate:.3f}, top_k: {top_k:.1%}, n_anom: {len(anom_idx)}")

        for op_name, ranks in decomp.items():
            threshold = np.percentile(ranks, 100 * (1 - top_k))
            caught = set()
            for i, idx in enumerate(anom_idx):
                if ranks[idx] >= threshold:
                    caught.add(i)
            unique = caught.copy()
            for other_name, other_ranks in decomp.items():
                if other_name == op_name:
                    continue
                other_th = np.percentile(other_ranks, 100 * (1 - top_k))
                for i, idx in enumerate(anom_idx):
                    if other_ranks[idx] >= other_th:
                        unique.discard(i)
            print(f"  {op_name:<12s}  detects {len(caught):>3d}/{len(anom_idx)}  "
                  f"({100*len(caught)/len(anom_idx):>5.1f}%)  "
                  f"UNIQUE: {len(unique)} anomalies only this operator catches")

        # Union
        all_caught = set()
        for op_name, ranks in decomp.items():
            threshold = np.percentile(ranks, 100 * (1 - top_k))
            for i, idx in enumerate(anom_idx):
                if ranks[idx] >= threshold:
                    all_caught.add(i)
        print(f"  {'UNION':<12s}  detects {len(all_caught):>3d}/{len(anom_idx)}  "
              f"({100*len(all_caught)/len(anom_idx):>5.1f}%)  "
              f"= theoretical max from these 4 ops")


if __name__ == "__main__":
    main()
