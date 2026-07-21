"""
New UDL variants not yet in full_benchmark_checkpoint.json:
  - QSExpo-lean       (mfls_method='quadratic_smooth')
  - SignedLR-lean     (mfls_method='logistic')
  - Magnifier-lean    (magnify=True + Fisher)
  - MetaFusion-BSDT   (all 6 strategies × BSDT operators)
  - MetaFusion-CombA  (all 6 strategies × CombA operators)
  - QSExpo-CombA      (quadratic_smooth on CombA)
  - SignedLR-CombA    (logistic on CombA)
  - Fuse-lean-max     (RankFusion max on lean)
  - Fuse-lean-softmax (RankFusion softmax on lean)
  - Fuse-BSDT-max     (RankFusion max on BSDT)
  - Fuse-CombA-max    (RankFusion max on CombA)
  - BSDT-QDA-Mag      (QDA-Magnified on BSDT operators)

Patches full_benchmark_checkpoint.json in-place.
Skips methods that are already present for a dataset.
"""
import sys, os, json, time, gc, warnings
import numpy as np
from copy import deepcopy
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(__file__))

from udl.compare_sota import load_all_datasets
from udl.pipeline import UDLPipeline
from udl.rank_fusion import RankFusionPipeline
from udl.meta_fusion import MetaFusionPipeline, default_operators
from udl.hybrid_pipeline import HybridPipeline
from udl.experimental_spectra import (
    FourierBasisSpectrum, BSplineBasisSpectrum,
    WaveletBasisSpectrum, LegendreBasisSpectrum,
)
from udl.experimental_spectra import PhaseCurveSpectrum
from udl.bsdt_bridge import BSDTSpectrum

CKPT = 'results/full_benchmark_checkpoint.json'
PROG = 'results/new_variants_progress.json'

def load_ckpt():
    with open(CKPT) as f:
        return json.load(f)

def save_ckpt(data):
    with open(CKPT, 'w') as f:
        json.dump(data, f, indent=2)

def load_prog():
    if os.path.exists(PROG):
        with open(PROG) as f:
            return json.load(f)
    return {}

def save_prog(p):
    with open(PROG, 'w') as f:
        json.dump(p, f, indent=2)

# ── operator factories ───────────────────────────────────────────────────────
def lean_ops():
    return default_operators()

def bsdt_lean_ops():
    ops = default_operators()
    ops.append(('bsdt', BSDTSpectrum()))
    return ops

def comb_a_ops():
    return [
        ('fourier',  FourierBasisSpectrum(n_coeffs=8)),
        ('bspline',  BSplineBasisSpectrum(n_basis=6)),
        ('wavelet',  WaveletBasisSpectrum(max_levels=4)),
        ('legendre', LegendreBasisSpectrum(n_degree=6)),
        ('phase',    PhaseCurveSpectrum()),
    ]

# ── method registry ──────────────────────────────────────────────────────────
def build_methods():
    ALL_STRATEGIES = ['fisher','fusion','quadsurf','qs_expo','signed_lr','magnifier']
    return {
        # mfls variants on lean
        'QSExpo-lean':      lambda: UDLPipeline(operators=lean_ops(), centroid_method='auto',
                                projection_method='fisher', mfls_method='quadratic_smooth'),
        'SignedLR-lean':    lambda: UDLPipeline(operators=lean_ops(), centroid_method='auto',
                                projection_method='fisher', mfls_method='logistic'),
        'Magnifier-lean':   lambda: UDLPipeline(operators=lean_ops(), centroid_method='auto',
                                projection_method='fisher', magnify=True),
        # MetaFusion on different operator sets
        'MetaFusion-BSDT':  lambda: MetaFusionPipeline(operators=bsdt_lean_ops(),
                                strategies=ALL_STRATEGIES, verbose=False),
        'MetaFusion-CombA': lambda: MetaFusionPipeline(operators=comb_a_ops(),
                                strategies=ALL_STRATEGIES, verbose=False),
        # mfls variants on CombA
        'QSExpo-CombA':     lambda: UDLPipeline(operators=comb_a_ops(), centroid_method='auto',
                                projection_method='fisher', mfls_method='quadratic_smooth'),
        'SignedLR-CombA':   lambda: UDLPipeline(operators=comb_a_ops(), centroid_method='auto',
                                projection_method='fisher', mfls_method='logistic'),
        # RankFusion top2 / softmax
        'Fuse-lean-top2':   lambda: RankFusionPipeline(operators=lean_ops(), fusion='top2'),
        'Fuse-lean-softmax':lambda: RankFusionPipeline(operators=lean_ops(), fusion='softmax'),
        'Fuse-BSDT-top2':   lambda: RankFusionPipeline(operators=bsdt_lean_ops(), fusion='top2'),
        'Fuse-CombA-top2':  lambda: RankFusionPipeline(operators=comb_a_ops(), fusion='top2'),
        # QDA-Magnified on BSDT
        'BSDT-QDA-Mag':     lambda: UDLPipeline(operators=bsdt_lean_ops(), centroid_method='auto',
                                projection_method='qda-magnified', magnify=True,
                                score_method='v3e'),
    }

# ── single method evaluator ──────────────────────────────────────────────────
def run_method(builder, X_tr, X_te, y_tr, y_te, top_k, timeout=600):
    import signal
    t0 = time.time()
    try:
        pipe = builder()
        pipe.fit(X_tr, y_tr)
        scores = pipe.score(X_te)
        if scores is None or np.all(np.isnan(scores)):
            return {'auc': 0.0, 'info': 'all-nan'}
        auc = float(roc_auc_score(y_te, scores))
        return {'auc': auc, 'info': '', 'elapsed': round(time.time()-t0, 1)}
    except Exception as e:
        return {'auc': 0.0, 'info': str(e)[:80], 'elapsed': round(time.time()-t0,1)}

DATASETS = ['mammography','pendigits','annthyroid','arrhythmia','satellite','glass','cardio']

def main():
    os.chdir('c:/amttp/research/udl')
    ckpt = load_ckpt()
    prog = load_prog()
    methods = build_methods()

    ds_map = load_all_datasets()

    for ds_name in DATASETS:
        print(f'\n=== {ds_name} ===')
        if ds_name not in ckpt:
            ckpt[ds_name] = {}
        if ds_name not in prog:
            prog[ds_name] = []

        X, y = ds_map[ds_name]
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=42
        )
        anom_rate = y_te.mean()
        top_k = min(max(anom_rate * 2, 0.05), 0.30)

        for mname, builder in methods.items():
            if mname in ckpt[ds_name]:
                r = ckpt[ds_name][mname]
                auc = r.get('auc', r) if isinstance(r, dict) else r
                print(f'  {mname:<22s}  AUC={auc:.4f}  (cached)')
                continue

            t0 = time.time()
            result = run_method(builder, X_tr, X_te, y_tr, y_te, top_k)
            elapsed = time.time() - t0
            auc = result['auc']
            info = result.get('info','')
            tag = f'  ERROR: {info}' if info else ''
            print(f'  {mname:<22s}  AUC={auc:.4f}  ({elapsed:.1f}s){tag}')

            ckpt[ds_name][mname] = result
            save_ckpt(ckpt)
            prog[ds_name].append(mname)
            save_prog(prog)

        gc.collect()

    print('\n\n' + '='*90)
    print('  FULL RESULTS TABLE (all methods)')
    print('='*90)
    print_table(ckpt)

def print_table(ckpt):
    datasets  = DATASETS
    ds_short  = ['mammo','pendig','annthy','arrhyt','satell','glass','cardio']

    groups = [
        ('Lean 5-op',   ['Fisher-lean','Fuse-lean','QuadSurf-lean','QSExpo-lean',
                         'SignedLR-lean','Magnifier-lean',
                         'MetaFusion','MetaFusion+','Hybrid-lean',
                         'Fuse-lean-top2','Fuse-lean-softmax']),
        ('QDA',         ['QDA-lean','QDA-Mag-lean']),
        ('BSDT',        ['BSDT-Fisher','BSDT-Fuse','BSDT-Hybrid',
                         'BSDT-QDA-Mag','MetaFusion-BSDT','Fuse-BSDT-top2']),
        ('CombA',       ['CombA-Fisher','CombA-Fuse','CombA-Hybrid','CombA-QDA-Mag',
                         'QSExpo-CombA','SignedLR-CombA',
                         'MetaFusion-CombA','Fuse-CombA-top2']),
        ('Old 4-op',    ['Fisher-4op','Fuse-4op','Hybrid-4op']),
    ]

    hdr = f"  {'Method':<24s}"
    for s in ds_short:
        hdr += f'  {s:>7s}'
    hdr += f'  {"mAUC":>7s}'
    print(hdr)
    print('  ' + '-'*(len(hdr)-2))

    for gname, methods in groups:
        print(f'  -- {gname} --')
        for m in methods:
            row = f'  {m:<24s}'
            aucs = []
            for d in datasets:
                r = ckpt.get(d,{}).get(m)
                auc = (r.get('auc',0.0) if isinstance(r,dict) else (r or 0.0))
                row += f'  {auc:>7.4f}'
                aucs.append(auc)
            row += f'  {np.mean(aucs):>7.4f}'
            print(row)

if __name__ == '__main__':
    main()
