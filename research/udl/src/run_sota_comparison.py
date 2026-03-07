"""
SOTA comparison benchmark.
Runs standard PyOD methods on the same 7 datasets used in the UDL benchmark.
Saves results to results/sota_checkpoint.json and prints combined comparison table.
"""
import sys, os, json, time, warnings
import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(__file__))

# ── dataset loader ──────────────────────────────────────────────────────────
from datasets import (
    load_mammography, load_pendigits, load_annthyroid,
    load_arrhythmia, load_satellite, load_glass, load_cardio,
)

DATASETS = {
    'mammography': load_mammography,
    'pendigits':   load_pendigits,
    'annthyroid':  load_annthyroid,
    'arrhythmia':  load_arrhythmia,
    'satellite':   load_satellite,
    'glass':       load_glass,
    'cardio':      load_cardio,
}

# ── SOTA method registry ────────────────────────────────────────────────────
def get_sota_methods():
    from pyod.models.iforest   import IForest
    from pyod.models.lof       import LOF
    from pyod.models.ocsvm     import OCSVM
    from pyod.models.copod     import COPOD
    from pyod.models.ecod      import ECOD
    from pyod.models.hbos      import HBOS
    from pyod.models.knn       import KNN
    from pyod.models.pca       import PCA as PyOD_PCA
    from pyod.models.loda      import LODA

    base = [
        ('IForest',   IForest(n_estimators=200, random_state=42)),
        ('LOF',       LOF(n_neighbors=20)),
        ('OCSVM',     OCSVM(kernel='rbf', nu=0.1)),
        ('COPOD',     COPOD()),
        ('ECOD',      ECOD()),
        ('HBOS',      HBOS(n_bins=20)),
        ('KNN',       KNN(n_neighbors=10)),
        ('PCA-PyOD',  PyOD_PCA(n_components=None, random_state=42)),
        ('LODA',      LODA(n_bins=10, n_random_cuts=100)),
    ]
    return base

# ── checkpoint helpers ───────────────────────────────────────────────────────
CKPT_PATH = 'results/sota_checkpoint.json'

def load_ckpt():
    if os.path.exists(CKPT_PATH):
        with open(CKPT_PATH) as f:
            return json.load(f)
    return {}

def save_ckpt(data):
    with open(CKPT_PATH, 'w') as f:
        json.dump(data, f, indent=2)

# ── eval one method on one dataset ──────────────────────────────────────────
def evaluate(clf, X_train, X_test, y_test):
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)
    clf.fit(X_train_s)
    scores = clf.decision_function(X_test_s)
    return float(roc_auc_score(y_test, scores))

# ── main ────────────────────────────────────────────────────────────────────
def main():
    ckpt = load_ckpt()

    for ds_name, loader in DATASETS.items():
        if ds_name not in ckpt:
            ckpt[ds_name] = {}

        print(f'\n=== {ds_name} ===')
        try:
            X, y = loader()
            # Same 70/30 stratified split as UDL worker_eval.py for fair comparison
            from sklearn.model_selection import train_test_split
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.3, stratify=y, random_state=42
            )
        except Exception as e:
            print(f'  LOAD ERROR: {e}')
            continue

        print(f'  train={X_train.shape}, test={X_test.shape}, '
              f'anomaly_rate={y_test.mean():.3f}')

        sota_methods = get_sota_methods()
        for mname, clf in sota_methods:
            if mname in ckpt[ds_name]:
                print(f'  {mname:<12s}  AUC={ckpt[ds_name][mname]:.4f}  (cached)')
                continue
            t0 = time.time()
            try:
                auc = evaluate(clf, X_train, X_test, y_test)
                ckpt[ds_name][mname] = auc
                save_ckpt(ckpt)
                print(f'  {mname:<12s}  AUC={auc:.4f}  ({time.time()-t0:.1f}s)')
            except Exception as e:
                print(f'  {mname:<12s}  ERROR: {e}')
                ckpt[ds_name][mname] = 0.0
                save_ckpt(ckpt)

    # ── print combined comparison table ─────────────────────────────────────
    print_combined_table(ckpt)

def print_combined_table(sota_ckpt):
    udl_path = 'results/full_benchmark_checkpoint.json'
    if not os.path.exists(udl_path):
        print('\nNo UDL results found.')
        return

    with open(udl_path) as f:
        udl = json.load(f)

    datasets = ['mammography','pendigits','annthyroid','arrhythmia','satellite','glass','cardio']
    ds_short  = ['mammo','pendig','annthy','arrhyt','satell','glass','cardio']

    # Best UDL methods to include in comparison
    udl_methods = [
        ('Fuse-lean',    'UDL'),
        ('BSDT-Fuse',    'UDL'),
        ('CombA-QDA-Mag','UDL'),
        ('Fuse-4op',     'UDL'),
    ]

    sota_names = ['IForest','LOF','OCSVM','COPOD','ECOD','HBOS','KNN','PCA-PyOD','LODA']

    pad = 18
    hdr = f"  {'Method':<{pad}s}  {'Group':<12s}"
    for s in ds_short:
        hdr += f'  {s:>7s}'
    hdr += f'  {"mAUC":>7s}'
    print('\n\n' + '='*len(hdr))
    print('  SOTA COMPARISON TABLE')
    print('='*len(hdr))
    print(hdr)
    print('  ' + '-'*(len(hdr)-2))

    def print_row(name, group, aucs):
        row = f"  {name:<{pad}s}  {group:<12s}"
        for a in aucs:
            row += f'  {a:>7.4f}'
        row += f'  {np.mean(aucs):>7.4f}'
        print(row)

    print('  -- SOTA Baselines --')
    for mname in sota_names:
        aucs = [(sota_ckpt.get(d,{}).get(mname) or 0.0) for d in datasets]
        print_row(mname, 'SOTA', aucs)

    print('  -- UDL Methods (ours) --')
    for mname, group in udl_methods:
        aucs = [(udl.get(d,{}).get(mname,{}).get('auc') or 0.0) for d in datasets]
        print_row(mname, group, aucs)

    # Highlight best per dataset
    print('\n  -- Per-dataset BEST --')
    all_methods_aucs = {}
    for mname in sota_names:
        all_methods_aucs[mname] = [(sota_ckpt.get(d,{}).get(mname) or 0.0) for d in datasets]
    for mname, _ in udl_methods:
        all_methods_aucs[mname] = [(udl.get(d,{}).get(mname,{}).get('auc') or 0.0) for d in datasets]

    row = f"  {'Best method':<{pad}s}  {'':12s}"
    for i, d in enumerate(datasets):
        col_aucs = {m: all_methods_aucs[m][i] for m in all_methods_aucs}
        best_m = max(col_aucs, key=lambda x: col_aucs[x])
        best_v = col_aucs[best_m]
        row += f'  {best_v:>7.4f}'
    print(row)

if __name__ == '__main__':
    import os
    os.chdir('c:/amttp/research/udl')
    main()
