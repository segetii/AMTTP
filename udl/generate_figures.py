"""
Generate all UDL paper figures.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from sklearn.model_selection import train_test_split
from udl import UDLPipeline, load_dataset
from udl.visualisation import (
    plot_spectrum_heatmap,
    plot_mdn_decomposition,
    plot_hyperplane_projection,
    plot_coupling_matrix,
    plot_cross_domain_results,
)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "papers", "udl_figures")
os.makedirs(OUT_DIR, exist_ok=True)

np.random.seed(42)

# ─── 1. Fit pipeline on mimic dataset ────────────────────────
print("Fitting pipeline on mimic dataset...")
X, y = load_dataset("mimic")
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, stratify=y, random_state=42
)
pipe = UDLPipeline(centroid_method="auto", projection_method="fisher")
pipe.fit(X_train, y_train)
decomp = pipe.decompose(X_test)
tr = decomp["tensor_result"]

# ─── 2. Generate figures ─────────────────────────────────────
law_names = pipe.stack.law_names_

print("Fig 1: Spectrum heatmap...")
plot_spectrum_heatmap(
    tr, law_names=law_names, n_samples=80,
    title="Fig 1: Multi-Spectrum Representation Stack",
    save_path=os.path.join(OUT_DIR, "fig1_spectrum_heatmap.png")
)

print("Fig 2: MDN decomposition...")
plot_mdn_decomposition(
    tr, y=y_test,
    title="Fig 2: Magnitude-Direction-Novelty Decomposition",
    save_path=os.path.join(OUT_DIR, "fig2_mdn_decomposition.png")
)

print("Fig 3: Hyperplane projection...")
R_test = pipe.transform(X_test)
plot_hyperplane_projection(
    pipe.projector, R_test, y=y_test,
    title="Fig 3: Fisher Hyperplane Projection",
    save_path=os.path.join(OUT_DIR, "fig3_hyperplane_projection.png")
)

print("Fig 4: Cross-law coupling...")
coupling = decomp["coupling_matrix"]
plot_coupling_matrix(
    coupling, law_names=law_names,
    title="Fig 4: Cross-Law Coupling Matrix",
    save_path=os.path.join(OUT_DIR, "fig4_coupling_matrix.png")
)

print("Fig 5: Cross-domain AUC comparison...")
from sklearn.metrics import roc_auc_score

auc_results = {}
for ds_name in ["synthetic", "mimic"]:
    Xi, yi = load_dataset(ds_name)
    Xtr, Xte, ytr, yte = train_test_split(Xi, yi, test_size=0.3,
                                            stratify=yi, random_state=42)
    p = UDLPipeline(centroid_method="auto", projection_method="fisher")
    p.fit(Xtr, ytr)
    s = p.score(Xte)
    auc_results[ds_name] = roc_auc_score(yte, s)

# Add real-world
for ds_name in ["pendigits", "mammography", "shuttle"]:
    try:
        Xi, yi = load_dataset(ds_name)
        Xtr, Xte, ytr, yte = train_test_split(Xi, yi, test_size=0.3,
                                                stratify=yi, random_state=42)
        p = UDLPipeline(centroid_method="auto", projection_method="fisher")
        p.fit(Xtr, ytr)
        s = p.score(Xte)
        auc_results[ds_name] = roc_auc_score(yte, s)
    except Exception as e:
        print(f"  {ds_name}: skipped ({e})")

plot_cross_domain_results(
    auc_results,
    title="Fig 5: UDL Cross-Domain AUC-ROC (No Retraining)",
    save_path=os.path.join(OUT_DIR, "fig5_cross_domain_auc.png")
)

print(f"\nAll figures saved to: {OUT_DIR}")
print("Done.")
