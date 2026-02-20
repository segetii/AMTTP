"""
UDL Deep Analysis — Full diagnostic report
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score, average_precision_score
from udl import UDLPipeline, load_dataset

np.random.seed(42)

DATASETS = ["synthetic", "mimic", "pendigits", "mammography", "shuttle"]

print("=" * 90)
print("  UNIVERSAL DEVIATION LAW — Deep Diagnostic Analysis")
print("  Date: 2026-02-18")
print("=" * 90)

all_results = []

for ds_name in DATASETS:
    try:
        X, y = load_dataset(ds_name)
    except Exception as e:
        print(f"\n  {ds_name}: LOAD FAILED ({e})")
        continue

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=42
    )

    pipe = UDLPipeline(centroid_method="auto", projection_method="fisher",
                       exp_alpha=1.0, score_weights=(0.7, 0.3))
    pipe.fit(X_train, y_train)

    scores = pipe.score(X_test)
    labels = pipe.predict(X_test)
    decomp = pipe.decompose(X_test)
    tr = decomp["tensor_result"]
    coupling = decomp["coupling_matrix"]
    proj_decomp = decomp["projection_decomp"]
    diag = pipe.get_diagnostics()

    auc = roc_auc_score(y_test, scores)
    ap = average_precision_score(y_test, scores)
    f1 = f1_score(y_test, labels, zero_division=0)
    prec = precision_score(y_test, labels, zero_division=0)
    rec = recall_score(y_test, labels, zero_division=0)

    # Per-law AUC
    R_test = pipe.transform(X_test)
    law_dims = diag["law_dims"]
    law_names = diag["law_names"]
    law_aucs = []
    offset = 0
    for k, (name, dim) in enumerate(zip(law_names, law_dims)):
        law_block = R_test[:, offset:offset + dim]
        law_score = np.linalg.norm(law_block - pipe.centroid_est.get_centroid()[offset:offset+dim], axis=1)
        try:
            la = roc_auc_score(y_test, law_score)
            law_aucs.append((name, la))
        except:
            law_aucs.append((name, float('nan')))
        offset += dim

    # Magnitude/novelty stats by class
    mag_normal = tr.magnitude[y_test == 0]
    mag_anomaly = tr.magnitude[y_test == 1]
    nov_normal = tr.novelty[y_test == 0]
    nov_anomaly = tr.novelty[y_test == 1]

    # Angular analysis
    angles = proj_decomp["angle"]
    ang_normal = angles[y_test == 0]
    ang_anomaly = angles[y_test == 1]

    # Parallel/perp decomposition
    par_normal = proj_decomp["parallel"][y_test == 0]
    par_anomaly = proj_decomp["parallel"][y_test == 1]
    perp_normal = proj_decomp["perpendicular"][y_test == 0]
    perp_anomaly = proj_decomp["perpendicular"][y_test == 1]

    # Cross-law coupling: off-diagonal
    off_diag = coupling[np.triu_indices_from(coupling, k=1)]
    strongest_pair_idx = np.argmax(np.abs(off_diag))
    K = coupling.shape[0]
    pairs = [(i, j) for i in range(K) for j in range(i+1, K)]
    strongest_i, strongest_j = pairs[strongest_pair_idx]

    print(f"\n{'─' * 90}")
    print(f"  DATASET: {ds_name.upper()}")
    print(f"{'─' * 90}")
    print(f"  Shape: N={len(X)}, d={X.shape[1]}   Anomaly rate: {y.mean():.2%}")
    print(f"  Train/Test: {len(X_train)} / {len(X_test)}")
    print(f"  Representation: {diag['total_representation_dim']}D from {X.shape[1]}D raw")
    print(f"  Centroid: {diag['centroid_method']}")
    print()
    print(f"  ┌──────────────────────────────────────────────────────────────┐")
    print(f"  │  CLASSIFICATION METRICS                                     │")
    print(f"  ├──────────────────────────────────────────────────────────────┤")
    print(f"  │  AUC-ROC:          {auc:.4f}                                │")
    print(f"  │  Average Precision: {ap:.4f}                                │")
    print(f"  │  F1 Score:          {f1:.4f}                                │")
    print(f"  │  Precision:         {prec:.4f}                                │")
    print(f"  │  Recall:            {rec:.4f}                                │")
    print(f"  └──────────────────────────────────────────────────────────────┘")
    print()
    print(f"  PER-LAW DOMAIN AUC (individual discriminative power):")
    for name, la in law_aucs:
        bar = "█" * int(la * 40) if not np.isnan(la) else "?"
        print(f"    {name:<8}  AUC={la:.4f}  {bar}")
    print()
    print(f"  MAGNITUDE-DIRECTION-NOVELTY DECOMPOSITION:")
    print(f"    Magnitude — Normal: μ={mag_normal.mean():.3f} σ={mag_normal.std():.3f}")
    print(f"                Anomaly: μ={mag_anomaly.mean():.3f} σ={mag_anomaly.std():.3f}")
    sep_mag = (mag_anomaly.mean() - mag_normal.mean()) / (mag_normal.std() + 1e-10)
    print(f"                Separation (Cohen's d): {sep_mag:.2f}")
    print(f"    Novelty  — Normal: μ={nov_normal.mean():.4f} σ={nov_normal.std():.4f}")
    print(f"                Anomaly: μ={nov_anomaly.mean():.4f} σ={nov_anomaly.std():.4f}")
    sep_nov = (nov_anomaly.mean() - nov_normal.mean()) / (nov_normal.std() + 1e-10)
    print(f"                Separation (Cohen's d): {sep_nov:.2f}")
    print()
    print(f"  HYPERPLANE PROJECTION DECOMPOSITION:")
    print(f"    Parallel (classifier-relevant):")
    print(f"      Normal:  μ={par_normal.mean():.3f}  σ={par_normal.std():.3f}")
    print(f"      Anomaly: μ={par_anomaly.mean():.3f}  σ={par_anomaly.std():.3f}")
    print(f"    Perpendicular (cluster-spread):")
    print(f"      Normal:  μ={perp_normal.mean():.3f}  σ={perp_normal.std():.3f}")
    print(f"      Anomaly: μ={perp_anomaly.mean():.3f}  σ={perp_anomaly.std():.3f}")
    print(f"    Angular deviation:")
    print(f"      Normal:  μ={np.degrees(ang_normal.mean()):.1f}°  σ={np.degrees(ang_normal.std()):.1f}°")
    print(f"      Anomaly: μ={np.degrees(ang_anomaly.mean()):.1f}°  σ={np.degrees(ang_anomaly.std()):.1f}°")
    print()
    print(f"  CROSS-LAW COUPLING:")
    print(f"    Mean off-diagonal: {off_diag.mean():.3f}")
    print(f"    Max coupling: {off_diag.max():.3f} ({law_names[strongest_i]}↔{law_names[strongest_j]})")
    print(f"    Min coupling: {off_diag.min():.3f}")

    all_results.append({
        "name": ds_name, "auc": auc, "ap": ap, "f1": f1,
        "prec": prec, "rec": rec,
        "mag_sep": sep_mag, "nov_sep": sep_nov,
        "coupling_mean": off_diag.mean(), "coupling_max": off_diag.max(),
        "n_features": X.shape[1], "rep_dim": diag["total_representation_dim"],
        "best_law": max(law_aucs, key=lambda x: x[1] if not np.isnan(x[1]) else 0),
    })

# ─── CROSS-DOMAIN SUMMARY ────────────────────────────────────
print(f"\n\n{'═' * 90}")
print(f"  CROSS-DOMAIN SYNTHESIS")
print(f"{'═' * 90}")
print(f"\n  {'Dataset':<15} {'AUC':>7} {'AP':>7} {'F1':>7} {'MagSep':>8} {'NovSep':>8} {'BestLaw':<10} {'Coupling':>9}")
print(f"  {'─'*15} {'─'*7} {'─'*7} {'─'*7} {'─'*8} {'─'*8} {'─'*10} {'─'*9}")
for r in all_results:
    bl_name, bl_auc = r["best_law"]
    print(f"  {r['name']:<15} {r['auc']:>7.4f} {r['ap']:>7.4f} {r['f1']:>7.4f} "
          f"{r['mag_sep']:>8.2f} {r['nov_sep']:>8.2f} {bl_name:<10} {r['coupling_max']:>9.3f}")

aucs = [r["auc"] for r in all_results]
aps = [r["ap"] for r in all_results]
print(f"\n  Mean AUC: {np.mean(aucs):.4f} ± {np.std(aucs):.4f}")
print(f"  Mean AP:  {np.mean(aps):.4f} ± {np.std(aps):.4f}")

print(f"\n  KEY FINDINGS:")
best = max(all_results, key=lambda r: r["auc"])
worst = min(all_results, key=lambda r: r["auc"])
print(f"  • Strongest domain: {best['name']} (AUC={best['auc']:.4f})")
print(f"  • Weakest domain: {worst['name']} (AUC={worst['auc']:.4f})")

mag_seps = [r["mag_sep"] for r in all_results]
nov_seps = [r["nov_sep"] for r in all_results]
print(f"  • Magnitude separation drives detection in {sum(1 for m in mag_seps if m > 1)}/{len(mag_seps)} domains (Cohen's d > 1)")
print(f"  • Novelty separation drives detection in {sum(1 for n in nov_seps if n > 0.5)}/{len(nov_seps)} domains (Cohen's d > 0.5)")

best_laws = [r["best_law"][0] for r in all_results]
from collections import Counter
law_counts = Counter(best_laws)
most_common_law = law_counts.most_common(1)[0]
print(f"  • Most discriminative law domain: '{most_common_law[0]}' (best in {most_common_law[1]}/{len(all_results)} datasets)")

couplings = [r["coupling_max"] for r in all_results]
print(f"  • Cross-law coupling range: [{min(couplings):.3f}, {max(couplings):.3f}]")
print(f"    → Anomalies co-activate {'multiple' if np.mean(couplings) > 0.5 else 'few'} law domains simultaneously")

print(f"\n{'═' * 90}")
