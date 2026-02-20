"""
UDL Input Mode Comparison — BSDT Component Integration
========================================================
Compares 3 pipeline configurations:
  Mode A: BSDT first → spectra on 4D (C,G,A,T)
  Mode B: Both BSDT(4D) + raw spectra combined (6 law domains)
  Mode C: BSDT components only (no raw features, no spectra)
  Baseline: Current pipeline (raw features only)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, f1_score, average_precision_score

from udl.spectra import (
    StatisticalSpectrum, ChaosSpectrum, SpectralSpectrum,
    GeometricSpectrum, ExponentialSpectrum,
)
from udl.bsdt_bridge import BSDTSpectrum, BSDTAugmentedStack
from udl.stack import RepresentationStack
from udl.pipeline import UDLPipeline
from udl.datasets import load_dataset

np.random.seed(42)


def build_pipeline_baseline():
    """Mode 0: Raw features → 5 spectra (current default)."""
    return UDLPipeline(centroid_method="auto", projection_method="fisher",
                       exp_alpha=1.0, score_weights=(0.7, 0.3))


def build_pipeline_mode_a():
    """Mode A: Raw → BSDT(4D) → 5 spectra on the 4D component vector."""
    # We need a two-stage pipeline: first compute C,G,A,T, then run spectra on that
    return UDLPipelineModeA()


def build_pipeline_mode_b():
    """Mode B: 6 law domains = BSDT(4D) + stat + chaos + freq + geom + exp from raw."""
    stack = BSDTAugmentedStack.build(activity_indices=None, exp_alpha=1.0)
    return UDLPipeline(centroid_method="auto", projection_method="fisher",
                       exp_alpha=1.0, score_weights=(0.7, 0.3), operators=stack.operators)


def build_pipeline_mode_c():
    """Mode C: BSDT components only — no spectra, just C,G,A,T as raw scores."""
    return UDLPipelineModeC()


# ═══════════════════════════════════════════════════════════════
# Mode A: Two-stage pipeline
# ═══════════════════════════════════════════════════════════════

class UDLPipelineModeA:
    """BSDT first → spectrum operators on the 4D component output."""

    def __init__(self):
        self.bsdt = BSDTSpectrum()
        self.inner_pipe = UDLPipeline(
            centroid_method="auto", projection_method="fisher",
            exp_alpha=1.0, score_weights=(0.7, 0.3)
        )

    def fit(self, X, y=None):
        X_ref = X[y == 0] if y is not None and (y == 0).any() else X
        self.bsdt.fit(X_ref)
        X_bsdt = self.bsdt.transform(X)  # (N, 4)
        self.inner_pipe.fit(X_bsdt, y)
        return self

    def score(self, X):
        X_bsdt = self.bsdt.transform(X)
        return self.inner_pipe.score(X_bsdt)

    def predict(self, X):
        X_bsdt = self.bsdt.transform(X)
        return self.inner_pipe.predict(X_bsdt)

    def get_diagnostics(self):
        d = self.inner_pipe.get_diagnostics()
        d["mode"] = "A: BSDT→Spectra(4D)"
        return d


# ═══════════════════════════════════════════════════════════════
# Mode C: BSDT-only pipeline (no spectra)
# ═══════════════════════════════════════════════════════════════

class UDLPipelineModeC:
    """BSDT components as direct features → centroid → projection."""

    def __init__(self):
        from udl.centroid import CentroidEstimator
        from udl.tensor import AnomalyTensor
        from udl.projection import HyperplaneProjector

        self.bsdt = BSDTSpectrum()
        self.centroid_est = CentroidEstimator(method="auto")
        self.tensor_builder = AnomalyTensor()
        self.projector = HyperplaneProjector(method="fisher")
        self._fitted = False

    def fit(self, X, y=None):
        X_ref = X[y == 0] if y is not None and (y == 0).any() else X
        self.bsdt.fit(X_ref)

        R_ref = self.bsdt.transform(X_ref)
        self.centroid_est.fit(R_ref)
        c = self.centroid_est.get_centroid()
        self.tensor_builder.fit(R_ref, centroid=c)

        R_all = self.bsdt.transform(X)
        self.projector.fit(R_all, y=y, centroid=c)
        self._law_dims = [4]  # single BSDT block
        self._fitted = True
        return self

    def score(self, X):
        R = self.bsdt.transform(X)
        tr = self.tensor_builder.build(R, self._law_dims)
        return tr.anomaly_score(weights=(0.7, 0.3))

    def predict(self, X):
        R = self.bsdt.transform(X)
        return self.projector.classify(R)

    def get_diagnostics(self):
        return {"mode": "C: BSDT-only(4D)", "centroid": repr(self.centroid_est)}


# ═══════════════════════════════════════════════════════════════
# Benchmark
# ═══════════════════════════════════════════════════════════════

MODES = {
    "Baseline (raw→spectra)":     build_pipeline_baseline,
    "A: BSDT→Spectra(4D)":       build_pipeline_mode_a,
    "B: BSDT+Raw combined(6law)": build_pipeline_mode_b,
    "C: BSDT-only(4D)":          build_pipeline_mode_c,
}

DATASETS = ["synthetic", "mimic", "pendigits", "mammography"]

print("=" * 100)
print("  UDL INPUT MODE COMPARISON — BSDT Component Integration")
print("  Comparing: Baseline (raw) | A (BSDT→spectra) | B (BSDT+raw) | C (BSDT-only)")
print("=" * 100)

# Collect results: results[dataset][mode] = {auc, ap, f1}
results = {}

for ds_name in DATASETS:
    print(f"\n  Loading {ds_name}...")
    try:
        X, y = load_dataset(ds_name)
    except Exception as e:
        print(f"    SKIPPED: {e}")
        continue

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=42
    )

    results[ds_name] = {}
    for mode_name, builder_fn in MODES.items():
        try:
            pipe = builder_fn()
            pipe.fit(X_train, y_train)
            scores = pipe.score(X_test)
            labels = pipe.predict(X_test)
            auc = roc_auc_score(y_test, scores)
            ap = average_precision_score(y_test, scores)
            f1 = f1_score(y_test, labels, zero_division=0)
            results[ds_name][mode_name] = {"auc": auc, "ap": ap, "f1": f1}
            print(f"    {mode_name:<30}  AUC={auc:.4f}  AP={ap:.4f}  F1={f1:.4f}")
        except Exception as e:
            results[ds_name][mode_name] = {"auc": 0, "ap": 0, "f1": 0}
            print(f"    {mode_name:<30}  ERROR: {e}")


# ─── Summary Table ────────────────────────────────────────────
print(f"\n\n{'═' * 100}")
print(f"  AUC-ROC COMPARISON TABLE")
print(f"{'═' * 100}")

header = f"  {'Dataset':<15}"
for mode_name in MODES:
    short = mode_name.split(":")[0] if ":" in mode_name else mode_name[:12]
    header += f" {short:>14}"
header += f" {'Best':>8}"
print(header)
print(f"  {'─' * 15}" + f" {'─' * 14}" * len(MODES) + f" {'─' * 8}")

mode_totals = {m: [] for m in MODES}
for ds_name in results:
    row = f"  {ds_name:<15}"
    best_auc = 0
    best_mode = ""
    for mode_name in MODES:
        r = results[ds_name].get(mode_name, {})
        auc = r.get("auc", 0)
        mode_totals[mode_name].append(auc)
        marker = ""
        if auc > best_auc:
            best_auc = auc
            best_mode = mode_name.split(":")[0] if ":" in mode_name else mode_name[:8]
        row += f" {auc:>14.4f}"
    row += f" {'★ ' + best_mode:>8}"
    print(row)

print(f"  {'─' * 15}" + f" {'─' * 14}" * len(MODES) + f" {'─' * 8}")
avg_row = f"  {'AVERAGE':<15}"
best_avg = 0
best_avg_mode = ""
for mode_name in MODES:
    avg = np.mean(mode_totals[mode_name]) if mode_totals[mode_name] else 0
    short = mode_name.split(":")[0] if ":" in mode_name else mode_name[:12]
    avg_row += f" {avg:>14.4f}"
    if avg > best_avg:
        best_avg = avg
        best_avg_mode = short
print(avg_row + f" {'★ ' + best_avg_mode:>8}")

print(f"\n{'═' * 100}")

# ─── Percent improvement over baseline ───────────────────────
print(f"\n  IMPROVEMENT OVER BASELINE (raw→spectra):")
for mode_name in list(MODES.keys())[1:]:
    improvements = []
    for ds_name in results:
        base_auc = results[ds_name].get(list(MODES.keys())[0], {}).get("auc", 0)
        mode_auc = results[ds_name].get(mode_name, {}).get("auc", 0)
        if base_auc > 0:
            pct = (mode_auc - base_auc) / base_auc * 100
            improvements.append(pct)
    short = mode_name
    avg_imp = np.mean(improvements) if improvements else 0
    print(f"    {short:<35}  Δ AUC = {avg_imp:+.2f}%")

print(f"\n{'═' * 100}")
