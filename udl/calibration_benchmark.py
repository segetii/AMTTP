"""
Full Calibration Results — All datasets × All methods × All calibrators
========================================================================
"""
import numpy as np, sys, os, copy, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from udl import UDLPipeline, ScoreCalibrator
from udl.datasets import make_synthetic, make_mimic_anomalies, load_mammography, load_shuttle, load_pendigits
from udl.experimental_spectra import (
    PolarSpectrum, RadarPolygonSpectrum, PhaseCurveSpectrum, GramEigenSpectrum,
    FourierBasisSpectrum, BSplineBasisSpectrum, WaveletBasisSpectrum, LegendreBasisSpectrum,
)
from udl.spectra import ReconstructionSpectrum, RankOrderSpectrum
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score

# ── Datasets ──
datasets = {}
datasets["Synthetic"] = make_synthetic()
datasets["Mimic"] = make_mimic_anomalies()
try: datasets["Mammography"] = load_mammography()
except: pass
try:
    X, y = load_shuttle()
    rng = np.random.RandomState(42)
    idx = rng.choice(len(y), min(len(y), 10000), replace=False)
    datasets["Shuttle"] = (X[idx], y[idx])
except: pass
try: datasets["Pendigits"] = load_pendigits()
except: pass

# ── UDL Configs ──
configs = {
    "UDL-v3e-CombB+R": ([
        ("B1_polar", PolarSpectrum()), ("B2_radar", RadarPolygonSpectrum()),
        ("B3_phase", PhaseCurveSpectrum()), ("B4_gram", GramEigenSpectrum()),
        ("recon", ReconstructionSpectrum()), ("rank", RankOrderSpectrum()),
    ], 'v3e'),
    "UDL-v3e-CombA+R": ([
        ("A1_fourier", FourierBasisSpectrum(n_coeffs=8)),
        ("A2_bspline", BSplineBasisSpectrum(n_basis=6)),
        ("A3_wavelet", WaveletBasisSpectrum(max_levels=4)),
        ("A4_legendre", LegendreBasisSpectrum(n_degree=6)),
        ("recon", ReconstructionSpectrum()), ("rank", RankOrderSpectrum()),
    ], 'v3e'),
    "UDL-v1-CombB+R": ([
        ("B1_polar", PolarSpectrum()), ("B2_radar", RadarPolygonSpectrum()),
        ("B3_phase", PhaseCurveSpectrum()), ("B4_gram", GramEigenSpectrum()),
        ("recon", ReconstructionSpectrum()), ("rank", RankOrderSpectrum()),
    ], 'v1'),
}

cal_methods = ['isotonic', 'platt', 'beta']

print("=" * 110)
print("  CALIBRATION RESULTS — UDL Pipeline with Score Calibration")
print("=" * 110)

for ds_name, (X, y) in datasets.items():
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, stratify=y, random_state=42)
    n_anom = int(y_te.sum())
    n_norm = int((y_te == 0).sum())

    print(f"\n{'─' * 110}")
    print(f"  DATASET: {ds_name}  (test: {n_norm} normal + {n_anom} anomalies)")
    print(f"{'─' * 110}")
    print(f"  {'Config':<22s} {'Calibrator':<10s} │ {'AUC':>7s} │ {'ECE':>7s} │ {'Brier':>7s} │ {'F1':>7s} │ {'Caught':>12s} │ {'FalseAlarm':>12s} │ {'Prob Range':>14s}")
    print(f"  {'─'*22} {'─'*10}─┼─{'─'*7}─┼─{'─'*7}─┼─{'─'*7}─┼─{'─'*7}─┼─{'─'*12}─┼─{'─'*12}─┼─{'─'*14}")

    for cname, (ops, sm) in configs.items():
        # Uncalibrated baseline
        pipe_raw = UDLPipeline(operators=copy.deepcopy(ops), score_method=sm,
                               centroid_method='auto', projection_method='fisher')
        pipe_raw.fit(X_tr, y_tr)
        raw_scores = pipe_raw.score(X_te)
        raw_auc = roc_auc_score(y_te, raw_scores)
        raw_probs = pipe_raw.predict_proba(X_te)

        print(f"  {cname:<22s} {'(none)':>10s} │ {raw_auc:>7.4f} │ {'  n/a':>7s} │ {'  n/a':>7s} │ {'  n/a':>7s} │ {'  n/a':>12s} │ {'  n/a':>12s} │ [{raw_probs.min():.3f},{raw_probs.max():.3f}]")

        for cal_m in cal_methods:
            try:
                pipe_cal = UDLPipeline(operators=copy.deepcopy(ops), score_method=sm,
                                       centroid_method='auto', projection_method='fisher',
                                       calibrate=cal_m)
                pipe_cal.fit(X_tr, y_tr)
                probs = pipe_cal.predict_proba(X_te)
                summ = pipe_cal.calibration_summary(X_te, y_te)
                auc = roc_auc_score(y_te, probs)
                tp, fn, fp, tn = summ['tp'], summ['fn'], summ['fp'], summ['tn']
                caught_str = f"{tp:>4d}/{tp+fn:<4d}"
                fa_str = f"{fp:>4d}/{fp+tn:<4d}"
                print(f"  {'':<22s} {cal_m:>10s} │ {auc:>7.4f} │ {summ['ece']:>7.4f} │ {summ['brier']:>7.4f} │ {summ['f1']:>7.4f} │ {caught_str:>12s} │ {fa_str:>12s} │ [{probs.min():.3f},{probs.max():.3f}]")
            except Exception as e:
                print(f"  {'':<22s} {cal_m:>10s} │ ERROR: {e}")
        print()

print("=" * 110)
print("  DONE")
print("=" * 110)
