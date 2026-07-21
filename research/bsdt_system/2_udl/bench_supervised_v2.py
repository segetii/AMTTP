"""
UDL Supervised Benchmark v2 — Definitive Comparison
=====================================================
Tests UDL as a feature engine + supervised classifier head across
5 ODDS datasets with varying anomaly rates and dimensionalities.

Key addition over v1: RAW+UDL combined features (concatenation),
which is the strongest supervised use of UDL.

Pipelines:
  1. XGB-raw          — XGBoost on original features
  2. LGB-raw          — LightGBM on original features
  3. XGB-UDL          — XGBoost on UDL representation only
  4. LGB-UDL          — LightGBM on UDL representation only
  5. XGB-raw+UDL      — XGBoost on [raw || UDL] concatenated
  6. LGB-raw+UDL      — LightGBM on [raw || UDL] concatenated
  7. UDL-Optimised    — UDL Magnifier+QDA (CV-tuned gamma)
"""

import sys, time, warnings
from pathlib import Path
import numpy as np

_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

warnings.filterwarnings("ignore")

from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.discriminant_analysis import QuadraticDiscriminantAnalysis

from src.stack import RepresentationStack
from src.centroid import CentroidEstimator
from src.magnifier import DimensionMagnifier
from src.datasets import load_dataset

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


# ── UDL Feature Extraction ──
class UDLFeatures:
    """Multi-spectrum feature extraction (unsupervised fit, transform all)."""

    def __init__(self):
        self.stack = RepresentationStack()
        self.centroid_est = CentroidEstimator(method='auto')

    def fit(self, X, y):
        X_ref = X[y == 0]
        self.stack.fit(X_ref)
        R_ref = self.stack.transform(X_ref)
        self.centroid_est.fit(R_ref)
        self.centroid_ = self.centroid_est.get_centroid()
        return self

    def transform(self, X):
        R = self.stack.transform(X)
        diff = R - self.centroid_
        # Per-operator deviation magnitudes
        mags = []
        start = 0
        for dim in self.stack.law_dims_:
            block = diff[:, start:start + dim]
            mags.append(np.linalg.norm(block, axis=1, keepdims=True))
            start += dim
        return np.hstack([R, np.hstack(mags),
                          np.linalg.norm(diff, axis=1, keepdims=True)])


# ── UDL-Optimised (inner CV on gamma + reg) ──
class UDLOptimised:
    GAMMA_GRID = [2.0, 4.0, 5.0, 6.0, 8.0]
    REG_GRID = [1e-5, 1e-4, 1e-3]

    def __init__(self):
        self.best_gamma = 5.0
        self.best_reg = 1e-4

    def fit(self, X, y):
        inner_cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=99)
        stack = RepresentationStack()
        stack.fit(X[y == 0])
        R = stack.transform(X)
        best_auc = -1

        for g in self.GAMMA_GRID:
            for reg in self.REG_GRID:
                aucs = []
                for itr, ite in inner_cv.split(R, y):
                    if y[itr].sum() < 2 or y[ite].sum() < 1:
                        continue
                    mag = DimensionMagnifier(gamma=g, verbose=False)
                    mag.fit(R[itr], y[itr],
                            law_names=stack.law_names_,
                            law_dims=stack.law_dims_)
                    Rm_tr = mag.magnify(R[itr])
                    Rm_te = mag.magnify(R[ite])
                    qda = QuadraticDiscriminantAnalysis(reg_param=reg)
                    qda.fit(Rm_tr, y[itr])
                    aucs.append(roc_auc_score(
                        y[ite], qda.predict_proba(Rm_te)[:, 1]))
                if aucs and np.mean(aucs) > best_auc:
                    best_auc = np.mean(aucs)
                    self.best_gamma, self.best_reg = g, reg

        # Refit on full data
        self._stack = stack
        self._mag = DimensionMagnifier(gamma=self.best_gamma, verbose=False)
        self._mag.fit(R, y, law_names=stack.law_names_,
                      law_dims=stack.law_dims_)
        Rm = self._mag.magnify(R)
        self._qda = QuadraticDiscriminantAnalysis(reg_param=self.best_reg)
        self._qda.fit(Rm, y)
        return self

    def score(self, X):
        R = self._stack.transform(X)
        Rm = self._mag.magnify(R)
        return self._qda.predict_proba(Rm)[:, 1]


# ── Benchmark ──
def run():
    DATASETS = [
        ('mammography', 'Mammo'),   # 11k, 6d,  2.3%
        ('annthyroid',  'AnnThy'),  # 7.2k, 6d, 7.4%
        ('pendigits',   'PenDig'),  # 1.8k, 64d, ~10%
        ('satellite',   'Satell'),  # 6.4k, 36d, 31.6%
        ('arrhythmia',  'Arrhyt'),  # 452, 274d, 15%
    ]
    N = 5  # folds

    grand = {}

    for ds_name, short in DATASETS:
        print(f"\n{'=' * 72}")
        X, y = load_dataset(ds_name)
        anom_pct = y.mean() * 100
        print(f"  {short:6s} | N={len(X):>5d}  D={X.shape[1]:>3d}  "
              f"anom={anom_pct:.1f}% ({int(y.sum())})")
        print(f"{'=' * 72}")

        cv = StratifiedKFold(n_splits=N, shuffle=True, random_state=42)
        results = {}

        for fi, (itr, ite) in enumerate(cv.split(X, y)):
            Xtr, Xte = X[itr], X[ite]
            ytr, yte = y[itr], y[ite]

            sc = StandardScaler().fit(Xtr)
            Xtr_s, Xte_s = sc.transform(Xtr), sc.transform(Xte)

            # UDL features (computed once per fold)
            udl = UDLFeatures()
            udl.fit(Xtr_s, ytr)
            Utr = udl.transform(Xtr_s)
            Ute = udl.transform(Xte_s)

            # Combined: [raw || UDL]
            Ctr = np.hstack([Xtr_s, Utr])
            Cte = np.hstack([Xte_s, Ute])

            methods = {}

            # Tree on raw
            if HAS_XGB:
                methods['XGB-raw'] = ('tree', Xtr_s, Xte_s,
                    XGBClassifier(n_estimators=200, max_depth=6, lr=0.1,
                                  eval_metric='logloss', verbosity=0,
                                  random_state=42))
            if HAS_LGB:
                methods['LGB-raw'] = ('tree', Xtr_s, Xte_s,
                    LGBMClassifier(n_estimators=200, max_depth=6, lr=0.1,
                                   verbosity=-1, random_state=42))

            # Tree on UDL features only
            if HAS_XGB:
                methods['XGB-UDL'] = ('tree', Utr, Ute,
                    XGBClassifier(n_estimators=200, max_depth=6, lr=0.1,
                                  eval_metric='logloss', verbosity=0,
                                  random_state=42))
            if HAS_LGB:
                methods['LGB-UDL'] = ('tree', Utr, Ute,
                    LGBMClassifier(n_estimators=200, max_depth=6, lr=0.1,
                                   verbosity=-1, random_state=42))

            # Tree on RAW+UDL (the key hybrid)
            if HAS_XGB:
                methods['XGB-raw+UDL'] = ('tree', Ctr, Cte,
                    XGBClassifier(n_estimators=200, max_depth=6, lr=0.1,
                                  eval_metric='logloss', verbosity=0,
                                  random_state=42))
            if HAS_LGB:
                methods['LGB-raw+UDL'] = ('tree', Ctr, Cte,
                    LGBMClassifier(n_estimators=200, max_depth=6, lr=0.1,
                                   verbosity=-1, random_state=42))

            # UDL-Optimised (Magnifier+QDA, CV-tuned)
            methods['UDL-Opt'] = ('udl', Xtr_s, Xte_s, UDLOptimised())

            for name, (tp, ftr, fte, mdl) in methods.items():
                t0 = time.perf_counter()
                try:
                    if tp == 'tree':
                        mdl.fit(ftr, ytr)
                        prob = mdl.predict_proba(fte)[:, 1]
                    else:
                        mdl.fit(ftr, ytr)
                        prob = mdl.score(fte)
                    auc = roc_auc_score(yte, prob)
                    ap  = average_precision_score(yte, prob)
                except Exception as e:
                    auc, ap = 0, 0
                    print(f"    ERR {name}: {e}")
                dt = time.perf_counter() - t0
                results.setdefault(name, []).append((auc, ap, dt))

            fold_line = f"  F{fi+1}"
            for name in results:
                auc_f = results[name][-1][0]
                fold_line += f"  {name}={auc_f:.4f}"
            print(fold_line)

        # Summary
        print(f"\n  {'Method':16s} {'AUC':>14s} {'AP':>14s} {'t/fold':>8s}")
        print(f"  {'-'*16} {'-'*14} {'-'*14} {'-'*8}")
        ds_aucs = {}
        for name in results:
            aucs = [r[0] for r in results[name]]
            aps  = [r[1] for r in results[name]]
            ts   = [r[2] for r in results[name]]
            m_auc, s_auc = np.mean(aucs), np.std(aucs)
            m_ap = np.mean(aps)
            m_t  = np.mean(ts)
            ds_aucs[name] = m_auc
            print(f"  {name:16s} {m_auc:.4f}+/-{s_auc:.4f} "
                  f"{m_ap:.4f}         {m_t:6.2f}s")

        best = max(ds_aucs, key=ds_aucs.get)
        print(f"  >> BEST: {best} (AUC {ds_aucs[best]:.4f})")

        # Delta: raw+UDL vs raw
        for t in ['XGB', 'LGB']:
            raw_k, hyb_k = f'{t}-raw', f'{t}-raw+UDL'
            if raw_k in ds_aucs and hyb_k in ds_aucs:
                d = ds_aucs[hyb_k] - ds_aucs[raw_k]
                sign = '+' if d >= 0 else ''
                tag = 'UDL helps!' if d > 0.001 else ('tie' if abs(d) < 0.001 else 'raw wins')
                print(f"  {t} raw+UDL vs raw: {sign}{d:.4f} ({tag})")

        grand[short] = ds_aucs

    # Grand table
    print(f"\n\n{'=' * 72}")
    print(f"  GRAND COMPARISON TABLE (AUC, 5-fold CV)")
    print(f"{'=' * 72}")
    all_m = sorted({m for d in grand.values() for m in d})
    header = f"  {'Method':16s}"
    for short_name in [s for _, s in DATASETS]:
        header += f" {short_name:>8s}"
    header += f" {'mAUC':>8s}"
    print(header)
    print(f"  {'-'*16}" + f" {'-'*8}" * (len(DATASETS) + 1))

    for m in all_m:
        line = f"  {m:16s}"
        vals = []
        for _, short_name in DATASETS:
            v = grand.get(short_name, {}).get(m, None)
            if v is not None:
                line += f" {v:8.4f}"
                vals.append(v)
            else:
                line += f" {'---':>8s}"
        if vals:
            line += f" {np.mean(vals):8.4f}"
        print(line)

    # Overall best
    mean_aucs = {}
    for m in all_m:
        vals = [grand[s].get(m, 0) for _, s in DATASETS]
        mean_aucs[m] = np.mean(vals)
    best_overall = max(mean_aucs, key=mean_aucs.get)
    print(f"\n  >> OVERALL BEST: {best_overall} (mAUC {mean_aucs[best_overall]:.4f})")


if __name__ == '__main__':
    run()
