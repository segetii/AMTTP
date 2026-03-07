"""
UDL Standalone Benchmark — DeviationLayer (Theory Second Pass)
===============================================================
Proves UDL stands on its own: all UDL methods use ONLY UDL
components (RepresentationStack, Magnifier, DeviationLayer, QDA).

XGBoost and LightGBM appear ONLY as external baselines to
benchmark against — they are never mixed into the UDL pipeline.

UDL Methods (all ours):
  1. UDL-QDA            — Stack + Magnifier + QDA (fixed gamma=5)
  2. UDL-QDA-Opt        — Stack + Magnifier + QDA (CV-tuned gamma)
  3. UDL-L2-Score       — Stack + DeviationLayer score (Theorem 1-4)
  4. UDL-L2-QDA         — Stack + DeviationLayer features + QDA
  5. UDL-Full           — Stack + Magnifier + DeviationLayer + QDA

External Baselines (benchmarked against, NOT mixed in):
  B1. XGBoost-raw       — XGBoost on raw features
  B2. LightGBM-raw      — LightGBM on raw features
"""

import sys, time, warnings, json
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
from src.deviation_layer import DeviationLayer
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


# ═══════════════════════════════════════════════════════════════════
#  UDL METHOD 1: Stack + Magnifier + QDA (fixed gamma)
# ═══════════════════════════════════════════════════════════════════
class UDL_QDA:
    def __init__(self, gamma=5.0, reg=1e-4):
        self.gamma = gamma
        self.reg = reg

    def fit(self, X, y):
        self.stack = RepresentationStack()
        self.stack.fit(X[y == 0])
        R = self.stack.transform(X)
        self.mag = DimensionMagnifier(gamma=self.gamma, verbose=False)
        self.mag.fit(R, y, law_names=self.stack.law_names_,
                     law_dims=self.stack.law_dims_)
        Rm = self.mag.magnify(R)
        self.qda = QuadraticDiscriminantAnalysis(reg_param=self.reg)
        self.qda.fit(Rm, y)
        return self

    def predict_proba(self, X):
        R = self.stack.transform(X)
        Rm = self.mag.magnify(R)
        return self.qda.predict_proba(Rm)[:, 1]


# ═══════════════════════════════════════════════════════════════════
#  UDL METHOD 2: Stack + Magnifier + QDA (CV-tuned gamma + reg)
# ═══════════════════════════════════════════════════════════════════
class UDL_QDA_Opt:
    GAMMA_GRID = [2.0, 4.0, 5.0, 6.0, 8.0]
    REG_GRID = [1e-5, 1e-4, 1e-3]

    def fit(self, X, y):
        inner_cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=99)
        stack = RepresentationStack()
        stack.fit(X[y == 0])
        R = stack.transform(X)
        best_auc, best_g, best_r = -1, 5.0, 1e-4

        for g in self.GAMMA_GRID:
            for reg in self.REG_GRID:
                aucs = []
                for itr, ite in inner_cv.split(R, y):
                    if y[itr].sum() < 2 or y[ite].sum() < 1:
                        continue
                    mag = DimensionMagnifier(gamma=g, verbose=False)
                    mag.fit(R[itr], y[itr], law_names=stack.law_names_,
                            law_dims=stack.law_dims_)
                    q = QuadraticDiscriminantAnalysis(reg_param=reg)
                    q.fit(mag.magnify(R[itr]), y[itr])
                    aucs.append(roc_auc_score(
                        y[ite], q.predict_proba(mag.magnify(R[ite]))[:, 1]))
                if aucs and np.mean(aucs) > best_auc:
                    best_auc, best_g, best_r = np.mean(aucs), g, reg

        # Refit on full data
        self.stack = stack
        self.mag = DimensionMagnifier(gamma=best_g, verbose=False)
        self.mag.fit(R, y, law_names=stack.law_names_,
                     law_dims=stack.law_dims_)
        Rm = self.mag.magnify(R)
        self.qda = QuadraticDiscriminantAnalysis(reg_param=best_r)
        self.qda.fit(Rm, y)
        self.best_gamma, self.best_reg = best_g, best_r
        return self

    def predict_proba(self, X):
        R = self.stack.transform(X)
        return self.qda.predict_proba(self.mag.magnify(R))[:, 1]


# ═══════════════════════════════════════════════════════════════════
#  UDL METHOD 3: Stack + DeviationLayer score (unsupervised-compatible)
# ═══════════════════════════════════════════════════════════════════
class UDL_L2_Score:
    """Purely theory-driven score: SDP-weighted composite + bound ratio."""

    def fit(self, X, y):
        self.stack = RepresentationStack()
        self.stack.fit(X[y == 0])
        self.layer2 = DeviationLayer(weight_method='sdp')
        self.layer2.fit(self.stack, X, y=y)
        return self

    def predict_proba(self, X):
        return self.layer2.score(self.stack, X)


# ═══════════════════════════════════════════════════════════════════
#  UDL METHOD 4: Stack + DeviationLayer features + QDA
# ═══════════════════════════════════════════════════════════════════
class UDL_L2_QDA:
    """DeviationLayer theory features fed into QDA for classification."""

    def __init__(self, reg=1e-4):
        self.reg = reg

    def fit(self, X, y):
        self.stack = RepresentationStack()
        self.stack.fit(X[y == 0])
        self.layer2 = DeviationLayer(weight_method='sdp')
        self.layer2.fit(self.stack, X, y=y)
        F = self.layer2.transform(self.stack, X)
        self.qda = QuadraticDiscriminantAnalysis(reg_param=self.reg)
        self.qda.fit(F, y)
        return self

    def predict_proba(self, X):
        F = self.layer2.transform(self.stack, X)
        return self.qda.predict_proba(F)[:, 1]


# ═══════════════════════════════════════════════════════════════════
#  UDL METHOD 5: Stack + Magnifier + DeviationLayer + QDA (full)
# ═══════════════════════════════════════════════════════════════════
class UDL_Full:
    """
    Complete UDL pipeline with both first and second layers:
      Stack -> [Magnifier features || DeviationLayer features] -> QDA

    This is the strongest UDL method — combines boundary-centred
    magnification (first pass) with theory-grounded deviation
    features (second pass) into a single QDA classifier.
    """

    GAMMA_GRID = [3.0, 5.0, 8.0]
    REG_GRID = [1e-4, 1e-3]

    def fit(self, X, y):
        # Stack (unsupervised)
        self.stack = RepresentationStack()
        self.stack.fit(X[y == 0])
        R = self.stack.transform(X)

        # DeviationLayer (theory second pass)
        self.layer2 = DeviationLayer(weight_method='sdp')
        self.layer2.fit(self.stack, X, y=y)
        F_l2 = self.layer2.transform(self.stack, X)

        # Inner CV to pick gamma + reg for magnifier
        inner_cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=99)
        best_auc, best_g, best_r = -1, 5.0, 1e-4

        for g in self.GAMMA_GRID:
            for reg in self.REG_GRID:
                aucs = []
                for itr, ite in inner_cv.split(X, y):
                    if y[itr].sum() < 2 or y[ite].sum() < 1:
                        continue
                    mag = DimensionMagnifier(gamma=g, verbose=False)
                    mag.fit(R[itr], y[itr], law_names=self.stack.law_names_,
                            law_dims=self.stack.law_dims_)
                    Rm_tr = mag.magnify(R[itr])
                    Rm_te = mag.magnify(R[ite])
                    # Concatenate magnified + L2
                    combo_tr = np.hstack([Rm_tr, F_l2[itr]])
                    combo_te = np.hstack([Rm_te, F_l2[ite]])
                    q = QuadraticDiscriminantAnalysis(reg_param=reg)
                    q.fit(combo_tr, y[itr])
                    aucs.append(roc_auc_score(
                        y[ite], q.predict_proba(combo_te)[:, 1]))
                if aucs and np.mean(aucs) > best_auc:
                    best_auc, best_g, best_r = np.mean(aucs), g, reg

        # Refit on full data
        self.mag = DimensionMagnifier(gamma=best_g, verbose=False)
        self.mag.fit(R, y, law_names=self.stack.law_names_,
                     law_dims=self.stack.law_dims_)
        Rm = self.mag.magnify(R)
        combo = np.hstack([Rm, F_l2])
        self.qda = QuadraticDiscriminantAnalysis(reg_param=best_r)
        self.qda.fit(combo, y)
        self.best_gamma, self.best_reg = best_g, best_r
        return self

    def predict_proba(self, X):
        R = self.stack.transform(X)
        Rm = self.mag.magnify(R)
        F_l2 = self.layer2.transform(self.stack, X)
        combo = np.hstack([Rm, F_l2])
        return self.qda.predict_proba(combo)[:, 1]


# ═══════════════════════════════════════════════════════════════════
#  BENCHMARK RUNNER
# ═══════════════════════════════════════════════════════════════════
def run():
    DATASETS = [
        ('mammography', 'Mammo'),   # 11k, 6d,  2.3%
        ('annthyroid',  'AnnThy'),  # 7.2k, 6d, 7.4%
        ('pendigits',   'PenDig'),  # 1.8k, 64d, ~10%
        ('satellite',   'Satell'),  # 6.4k, 36d, 31.6%
    ]
    N_FOLDS = 5
    grand = {}

    for ds_name, short in DATASETS:
        print(f"\n{'=' * 72}")
        X, y = load_dataset(ds_name)
        anom_pct = y.mean() * 100
        print(f"  {short:6s} | N={len(X):>5d}  D={X.shape[1]:>3d}  "
              f"anom={anom_pct:.1f}% ({int(y.sum())})")
        print(f"{'=' * 72}")

        cv = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
        results = {}

        for fi, (itr, ite) in enumerate(cv.split(X, y)):
            Xtr, Xte = X[itr], X[ite]
            ytr, yte = y[itr], y[ite]

            sc = StandardScaler().fit(Xtr)
            Xtr_s, Xte_s = sc.transform(Xtr), sc.transform(Xte)

            # ── Define all methods ──
            methods = {}

            # === UDL Methods (all ours) ===
            methods['UDL-QDA']      = ('udl', UDL_QDA(gamma=5.0))
            methods['UDL-QDA-Opt']  = ('udl', UDL_QDA_Opt())
            methods['UDL-L2-Score'] = ('udl', UDL_L2_Score())
            methods['UDL-L2-QDA']   = ('udl', UDL_L2_QDA())
            methods['UDL-Full']     = ('udl', UDL_Full())

            # === External Baselines (NOT mixed into UDL) ===
            if HAS_XGB:
                methods['XGB-raw'] = ('baseline', XGBClassifier(
                    n_estimators=200, max_depth=6, learning_rate=0.1,
                    eval_metric='logloss', verbosity=0, random_state=42))
            if HAS_LGB:
                methods['LGB-raw'] = ('baseline', LGBMClassifier(
                    n_estimators=200, max_depth=6, learning_rate=0.1,
                    verbosity=-1, random_state=42))

            # ── Run all methods ──
            for name, (mtype, mdl) in methods.items():
                t0 = time.perf_counter()
                try:
                    if mtype == 'udl':
                        mdl.fit(Xtr_s, ytr)
                        prob = mdl.predict_proba(Xte_s)
                    else:  # baseline — runs ONLY on raw features
                        mdl.fit(Xtr_s, ytr)
                        prob = mdl.predict_proba(Xte_s)[:, 1]

                    auc = roc_auc_score(yte, prob)
                    ap  = average_precision_score(yte, prob)
                except Exception as e:
                    auc, ap = 0, 0
                    print(f"    ERR {name}: {e}")
                dt = time.perf_counter() - t0
                results.setdefault(name, []).append((auc, ap, dt))

            # Fold line
            fold_line = f"  F{fi+1}"
            for name in results:
                auc_f = results[name][-1][0]
                fold_line += f"  {name}={auc_f:.4f}"
            print(fold_line)

        # ── Dataset summary ──
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
            ds_aucs[name] = round(m_auc, 4)
            marker = " <-- OURS" if 'UDL' in name else ""
            print(f"  {name:16s} {m_auc:.4f}+/-{s_auc:.4f} "
                  f"{m_ap:.4f}         {m_t:6.2f}s{marker}")

        best_udl = max((k for k in ds_aucs if 'UDL' in k),
                       key=lambda k: ds_aucs[k])
        best_all = max(ds_aucs, key=ds_aucs.get)
        print(f"  >> BEST UDL: {best_udl} (AUC {ds_aucs[best_udl]})")
        print(f"  >> BEST ALL: {best_all} (AUC {ds_aucs[best_all]})")

        # UDL-Full vs baselines
        if 'UDL-Full' in ds_aucs:
            for b in ['XGB-raw', 'LGB-raw']:
                if b in ds_aucs:
                    d = ds_aucs['UDL-Full'] - ds_aucs[b]
                    tag = 'UDL wins!' if d > 0.001 else (
                        'tie' if abs(d) <= 0.001 else 'baseline leads')
                    print(f"  UDL-Full vs {b}: {d:+.4f} ({tag})")

        grand[short] = ds_aucs

    # ═════════════════════════════════════════════════════════════
    #  GRAND TABLE
    # ═════════════════════════════════════════════════════════════
    print(f"\n\n{'=' * 80}")
    print(f"  GRAND TABLE — UDL Standalone vs External Baselines ({N_FOLDS}-fold CV)")
    print(f"{'=' * 80}")

    # Separate UDL from baselines
    all_m = sorted({m for d in grand.values() for m in d})
    udl_methods = [m for m in all_m if 'UDL' in m]
    baseline_methods = [m for m in all_m if 'UDL' not in m]

    header = f"  {'Method':16s}"
    for _, short_name in DATASETS:
        header += f" {short_name:>8s}"
    header += f" {'mAUC':>8s}"
    print(header)
    print(f"  {'-'*16}" + f" {'-'*8}" * (len(DATASETS) + 1))

    def print_row(m):
        line = f"  {m:16s}"
        vals = []
        for _, sn in DATASETS:
            v = grand.get(sn, {}).get(m, None)
            if v is not None:
                line += f" {v:8.4f}"
                vals.append(v)
            else:
                line += f" {'---':>8s}"
        if vals:
            line += f" {np.mean(vals):8.4f}"
        return line, np.mean(vals) if vals else 0

    print(f"  {'--- UDL (Ours) ---':^{16 + 9*(len(DATASETS)+1)}}")
    mean_aucs = {}
    for m in udl_methods:
        line, ma = print_row(m)
        mean_aucs[m] = ma
        print(line)

    print(f"  {'--- Baselines ---':^{16 + 9*(len(DATASETS)+1)}}")
    for m in baseline_methods:
        line, ma = print_row(m)
        mean_aucs[m] = ma
        print(line)

    best_udl_overall = max(udl_methods, key=lambda k: mean_aucs.get(k, 0))
    best_baseline = max(baseline_methods, key=lambda k: mean_aucs.get(k, 0)) if baseline_methods else None
    print(f"\n  >> BEST UDL: {best_udl_overall} (mAUC {mean_aucs[best_udl_overall]:.4f})")
    if best_baseline:
        print(f"  >> BEST BASELINE: {best_baseline} (mAUC {mean_aucs[best_baseline]:.4f})")
        gap = mean_aucs[best_udl_overall] - mean_aucs[best_baseline]
        verdict = "UDL WINS" if gap > 0.001 else ("TIE" if abs(gap) <= 0.001 else "BASELINE LEADS")
        print(f"  >> GAP: {gap:+.4f} mAUC ({verdict})")

    # Save results
    results_path = Path(__file__).resolve().parent / 'results' / 'layer2_standalone.json'
    results_path.parent.mkdir(exist_ok=True)
    with open(results_path, 'w') as f:
        json.dump(grand, f, indent=2)
    print(f"\n  Results saved to {results_path}")


if __name__ == '__main__':
    run()
