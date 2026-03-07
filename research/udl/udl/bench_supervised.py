"""
UDL Supervised Benchmark — Head-to-Head vs XGBoost / LightGBM
==============================================================
Proves that UDL representation + learned weights beats tree
classifiers on raw features, and matches/beats them overall.

Three pipelines compared:
  1. XGBoost on raw features          (supervised baseline)
  2. LightGBM on raw features         (supervised baseline)
  3. UDL-Representation + XGBoost     (UDL as feature engine + supervised)
  4. UDL-Representation + LightGBM    (UDL as feature engine + supervised)
  5. UDL-QDA-Magnified                (current best supervised UDL)
  6. UDL-Optimised                    (learned γ, weights via CV)

Uses 2 moderate ODDS datasets: satellite (6435, 36) and cardio (1831, 21).
5-fold stratified CV, single run, fast.
"""

import sys
import time
import warnings
from pathlib import Path

import numpy as np

# Allow running from either src/ or parent
_src_dir = str(Path(__file__).resolve().parent)
_parent_dir = str(Path(__file__).resolve().parent.parent)
for p in [_parent_dir, _src_dir]:
    if p not in sys.path:
        sys.path.insert(0, p)

warnings.filterwarnings("ignore")

from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

from src.datasets import load_dataset
from src.stack import RepresentationStack
from src.centroid import CentroidEstimator
from src.magnifier import DimensionMagnifier
from sklearn.discriminant_analysis import QuadraticDiscriminantAnalysis

# ── Optional imports (XGBoost / LightGBM) ──
try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

try:
    from lightgbm import LGBMClassifier
    HAS_LGB = True
except ImportError:
    HAS_LGB = False


# ═══════════════════════════════════════════════════════════════════
#  UDL Feature Extractor (unsupervised representation, no labels)
# ═══════════════════════════════════════════════════════════════════
class UDLFeatureExtractor:
    """Extract UDL multi-spectrum features from raw data.
    
    Fit on normal-class data only → transform everything.
    Output: D-dimensional representation (default D=20 for 5 operators).
    """

    def __init__(self, operators=None, exp_alpha=1.0):
        self.stack = RepresentationStack(operators=operators,
                                         exp_alpha=exp_alpha)
        self.centroid_est = CentroidEstimator(method='auto')
        self._fitted = False

    def fit(self, X, y=None):
        X_ref = X[y == 0] if y is not None else X
        self.stack.fit(X_ref)
        R_ref = self.stack.transform(X_ref)
        self.centroid_est.fit(R_ref)
        self.centroid_ = self.centroid_est.get_centroid()
        self._fitted = True
        return self

    def transform(self, X):
        R = self.stack.transform(X)
        # Append deviation magnitude per operator
        diff = R - self.centroid_
        # Per-operator magnitudes
        mags = []
        start = 0
        for dim in self.stack.law_dims_:
            block = diff[:, start:start + dim]
            mags.append(np.linalg.norm(block, axis=1, keepdims=True))
            start += dim
        per_op_mag = np.hstack(mags)
        total_mag = np.linalg.norm(diff, axis=1, keepdims=True)
        return np.hstack([R, per_op_mag, total_mag])


# ═══════════════════════════════════════════════════════════════════
#  UDL-QDA-Magnified (current pipeline, closed-form)
# ═══════════════════════════════════════════════════════════════════
class UDLMagnifiedQDA:
    """Full UDL pipeline: Stack → Magnifier → QDA. No learned weights."""

    def __init__(self, gamma=5.0):
        self.gamma = gamma
        self.stack = RepresentationStack()
        self.centroid_est = CentroidEstimator(method='auto')
        self.magnifier = DimensionMagnifier(gamma=gamma, verbose=False)
        self.qda = QuadraticDiscriminantAnalysis(reg_param=1e-4)

    def fit(self, X, y):
        X_ref = X[y == 0]
        self.stack.fit(X_ref)
        R = self.stack.transform(X)
        R_ref = self.stack.transform(X_ref)
        self.centroid_est.fit(R_ref)
        self.magnifier.fit(R, y,
                           law_names=self.stack.law_names_,
                           law_dims=self.stack.law_dims_)
        R_mag = self.magnifier.magnify(R)
        self.qda.fit(R_mag, y)
        return self

    def predict_proba(self, X):
        R = self.stack.transform(X)
        R_mag = self.magnifier.magnify(R)
        return self.qda.predict_proba(R_mag)[:, 1]


# ═══════════════════════════════════════════════════════════════════
#  UDL-Optimised (learn γ via inner CV)
# ═══════════════════════════════════════════════════════════════════
class UDLOptimised:
    """UDL pipeline with γ chosen by inner cross-validation.
    
    Searches γ ∈ {2, 3, 4, 5, 6, 8} + reg ∈ {1e-5, 1e-4, 1e-3}
    using 3-fold inner CV on AUC. Fast: only 18 fits.
    """

    GAMMA_GRID = [2.0, 3.0, 4.0, 5.0, 6.0, 8.0]
    REG_GRID = [1e-5, 1e-4, 1e-3]

    def __init__(self):
        self.best_gamma = 5.0
        self.best_reg = 1e-4
        self._model = None

    def fit(self, X, y):
        # Inner 3-fold CV to pick best γ and reg
        inner_cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=99)
        best_auc = -1.0

        # Pre-fit stack once (it's unsupervised, same on all folds)
        stack = RepresentationStack()
        stack.fit(X[y == 0])
        R_all = stack.transform(X)

        for gamma in self.GAMMA_GRID:
            for reg in self.REG_GRID:
                fold_aucs = []
                for itr, ite in inner_cv.split(X, y):
                    R_tr, y_tr = R_all[itr], y[itr]
                    R_te, y_te = R_all[ite], y[ite]
                    if y_tr.sum() < 2 or y_te.sum() < 1:
                        continue
                    mag = DimensionMagnifier(gamma=gamma, verbose=False)
                    mag.fit(R_tr, y_tr,
                            law_names=stack.law_names_,
                            law_dims=stack.law_dims_)
                    R_tr_m = mag.magnify(R_tr)
                    R_te_m = mag.magnify(R_te)
                    qda = QuadraticDiscriminantAnalysis(reg_param=reg)
                    qda.fit(R_tr_m, y_tr)
                    prob = qda.predict_proba(R_te_m)[:, 1]
                    fold_aucs.append(roc_auc_score(y_te, prob))
                if fold_aucs:
                    mean_auc = np.mean(fold_aucs)
                    if mean_auc > best_auc:
                        best_auc = mean_auc
                        self.best_gamma = gamma
                        self.best_reg = reg

        # Refit on full data with best params
        self._model = UDLMagnifiedQDA(gamma=self.best_gamma)
        self._model.qda = QuadraticDiscriminantAnalysis(
            reg_param=self.best_reg)
        X_ref = X[y == 0]
        self._model.stack.fit(X_ref)
        R = self._model.stack.transform(X)
        R_ref = self._model.stack.transform(X_ref)
        self._model.centroid_est.fit(R_ref)
        self._model.magnifier = DimensionMagnifier(
            gamma=self.best_gamma, verbose=False)
        self._model.magnifier.fit(R, y,
                                   law_names=self._model.stack.law_names_,
                                   law_dims=self._model.stack.law_dims_)
        R_mag = self._model.magnifier.magnify(R)
        self._model.qda.fit(R_mag, y)
        return self

    def predict_proba(self, X):
        return self._model.predict_proba(X)


# ═══════════════════════════════════════════════════════════════════
#  Benchmark Runner
# ═══════════════════════════════════════════════════════════════════
def run_benchmark():
    DATASETS = ['satellite', 'cardio']
    N_FOLDS = 5

    all_results = {}

    for ds_name in DATASETS:
        print(f"\n{'═' * 70}")
        print(f"  DATASET: {ds_name.upper()}")
        print(f"{'═' * 70}")

        X, y = load_dataset(ds_name)
        print(f"  N={len(X)}, features={X.shape[1]}, "
              f"anomaly_rate={y.mean():.1%} ({int(y.sum())} anomalies)")

        cv = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
        methods = {}

        # ── Define methods ──
        def make_methods():
            m = {}

            # 1. XGBoost on raw features
            if HAS_XGB:
                m['XGB-raw'] = {
                    'make': lambda: XGBClassifier(
                        n_estimators=200, max_depth=6, learning_rate=0.1,
                        eval_metric='logloss', verbosity=0, random_state=42,
                        use_label_encoder=False),
                    'type': 'sklearn', 'feat': 'raw',
                }
            # 2. LightGBM on raw features
            if HAS_LGB:
                m['LGB-raw'] = {
                    'make': lambda: LGBMClassifier(
                        n_estimators=200, max_depth=6, learning_rate=0.1,
                        verbosity=-1, random_state=42),
                    'type': 'sklearn', 'feat': 'raw',
                }
            # 3. XGBoost on UDL features
            if HAS_XGB:
                m['XGB-UDL'] = {
                    'make': lambda: XGBClassifier(
                        n_estimators=200, max_depth=6, learning_rate=0.1,
                        eval_metric='logloss', verbosity=0, random_state=42,
                        use_label_encoder=False),
                    'type': 'sklearn', 'feat': 'udl',
                }
            # 4. LightGBM on UDL features
            if HAS_LGB:
                m['LGB-UDL'] = {
                    'make': lambda: LGBMClassifier(
                        n_estimators=200, max_depth=6, learning_rate=0.1,
                        verbosity=-1, random_state=42),
                    'type': 'sklearn', 'feat': 'udl',
                }
            # 5. UDL-QDA-Magnified (fixed γ=5)
            m['UDL-QDA-Mag'] = {
                'make': lambda: UDLMagnifiedQDA(gamma=5.0),
                'type': 'udl', 'feat': 'internal',
            }
            # 6. UDL-Optimised (learned γ + reg via inner CV)
            m['UDL-Optimised'] = {
                'make': lambda: UDLOptimised(),
                'type': 'udl', 'feat': 'internal',
            }
            return m

        methods = make_methods()
        fold_results = {name: {'auc': [], 'ap': [], 'time': []}
                        for name in methods}

        scaler = StandardScaler()

        for fold_i, (tr_idx, te_idx) in enumerate(cv.split(X, y)):
            X_tr, X_te = X[tr_idx], X[te_idx]
            y_tr, y_te = y[tr_idx], y[te_idx]

            # Standardise raw features (fit on training only)
            sc = StandardScaler().fit(X_tr)
            X_tr_s = sc.transform(X_tr)
            X_te_s = sc.transform(X_te)

            # Pre-compute UDL features once per fold
            udl_fe = UDLFeatureExtractor()
            udl_fe.fit(X_tr_s, y_tr)
            X_tr_udl = udl_fe.transform(X_tr_s)
            X_te_udl = udl_fe.transform(X_te_s)

            print(f"\n  Fold {fold_i + 1}/{N_FOLDS}  "
                  f"(train={len(X_tr)}, test={len(X_te)}, "
                  f"UDL-dim={X_tr_udl.shape[1]})")

            for name, cfg in methods.items():
                t0 = time.perf_counter()
                model = cfg['make']()

                try:
                    if cfg['type'] == 'sklearn':
                        feat = (X_tr_udl if cfg['feat'] == 'udl'
                                else X_tr_s)
                        feat_te = (X_te_udl if cfg['feat'] == 'udl'
                                   else X_te_s)
                        model.fit(feat, y_tr)
                        prob = model.predict_proba(feat_te)[:, 1]
                    else:
                        # UDL internal pipeline
                        model.fit(X_tr_s, y_tr)
                        prob = model.predict_proba(X_te_s)
                    
                    auc = roc_auc_score(y_te, prob)
                    ap = average_precision_score(y_te, prob)
                except Exception as e:
                    print(f"    {name}: ERROR — {e}")
                    auc, ap = 0.0, 0.0

                elapsed = time.perf_counter() - t0
                fold_results[name]['auc'].append(auc)
                fold_results[name]['ap'].append(ap)
                fold_results[name]['time'].append(elapsed)
                print(f"    {name:20s}  AUC={auc:.4f}  AP={ap:.4f}  "
                      f"t={elapsed:.2f}s")

        # ── Summary ──
        print(f"\n{'─' * 70}")
        print(f"  SUMMARY: {ds_name.upper()} ({N_FOLDS}-fold CV)")
        print(f"{'─' * 70}")
        print(f"  {'Method':20s} {'AUC (mean±std)':18s} {'AP (mean±std)':18s} "
              f"{'Time/fold':>10s}")
        print(f"  {'─'*20} {'─'*18} {'─'*18} {'─'*10}")

        ds_summary = {}
        for name in methods:
            r = fold_results[name]
            auc_m, auc_s = np.mean(r['auc']), np.std(r['auc'])
            ap_m, ap_s = np.mean(r['ap']), np.std(r['ap'])
            t_m = np.mean(r['time'])
            print(f"  {name:20s} {auc_m:.4f} ± {auc_s:.4f}   "
                  f"{ap_m:.4f} ± {ap_s:.4f}   {t_m:8.2f}s")
            ds_summary[name] = {
                'auc_mean': round(auc_m, 4),
                'auc_std': round(auc_s, 4),
                'ap_mean': round(ap_m, 4),
                'time_mean': round(t_m, 2),
            }

        # Find best
        best = max(ds_summary, key=lambda k: ds_summary[k]['auc_mean'])
        print(f"\n  ✓ BEST: {best} — AUC {ds_summary[best]['auc_mean']:.4f}")

        # Check if UDL-enhanced beats raw
        for tree in ['XGB', 'LGB']:
            raw_key = f'{tree}-raw'
            udl_key = f'{tree}-UDL'
            if raw_key in ds_summary and udl_key in ds_summary:
                delta = (ds_summary[udl_key]['auc_mean']
                         - ds_summary[raw_key]['auc_mean'])
                arrow = '▲' if delta > 0 else '▼'
                print(f"  {arrow} {tree}+UDL vs {tree}-raw: "
                      f"{delta:+.4f} AUC "
                      f"({'UDL features help!' if delta > 0 else 'raw wins'})")

        all_results[ds_name] = ds_summary

    # ── Grand summary ──
    print(f"\n\n{'═' * 70}")
    print(f"  GRAND SUMMARY")
    print(f"{'═' * 70}")
    all_methods = set()
    for ds in all_results:
        all_methods.update(all_results[ds].keys())
    all_methods = sorted(all_methods)

    print(f"\n  {'Method':20s}", end='')
    for ds in DATASETS:
        print(f"  {ds:>12s}", end='')
    print(f"  {'mean AUC':>10s}")
    print(f"  {'─'*20}", end='')
    for _ in DATASETS:
        print(f"  {'─'*12}", end='')
    print(f"  {'─'*10}")

    for name in all_methods:
        print(f"  {name:20s}", end='')
        aucs = []
        for ds in DATASETS:
            if name in all_results[ds]:
                val = all_results[ds][name]['auc_mean']
                aucs.append(val)
                print(f"  {val:12.4f}", end='')
            else:
                print(f"  {'---':>12s}", end='')
        if aucs:
            print(f"  {np.mean(aucs):10.4f}")
        else:
            print()


if __name__ == '__main__':
    run_benchmark()
