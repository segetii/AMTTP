"""
Compact 5-seed validation: RankFusion vs Fisher.
Processes one seed at a time to avoid OOM.
"""
import numpy as np, sys, os, gc, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from copy import deepcopy
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from udl.compare_sota import load_all_datasets
from udl.pipeline import UDLPipeline
from udl.rank_fusion import RankFusionPipeline
from udl.experimental_spectra import PhaseCurveSpectrum
from udl.spectra import RankOrderSpectrum
from udl.new_spectra import TopologicalSpectrum, KernelRKHSSpectrum

OPS = [
    ("phase", PhaseCurveSpectrum()),
    ("topo", TopologicalSpectrum(k=15)),
    ("kernel", KernelRKHSSpectrum()),
    ("rank", RankOrderSpectrum()),
]

def cov_at_k(scores, y, k):
    anom = np.where(y == 1)[0]
    th = np.percentile(scores, 100*(1-k))
    return int(np.sum(scores[anom]>=th)), len(anom)

datasets = load_all_datasets()
ds_order = ["synthetic","mimic","mammography","shuttle","pendigits"]
seeds = [42, 123, 7, 99, 2024]

results = {}

for seed in seeds:
    print(f"\n=== Seed {seed} ===", flush=True)
    for dn in ds_order:
        X, y = datasets[dn]
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.3, stratify=y, random_state=seed)
        ar = yte.mean()
        tk = min(max(ar*2, 0.05), 0.30)

        # Fisher
        try:
            fp = UDLPipeline(operators=deepcopy(OPS), centroid_method='auto', projection_method='fisher')
            fp.fit(Xtr, ytr)
            fs = fp.score(Xte)
            fa = roc_auc_score(yte, fs)
            fd, fn = cov_at_k(fs, yte, tk)
            fc = fd/fn
        except:
            fa, fc, fd, fn = 0, 0, 0, int(yte.sum())
        del fp; gc.collect()

        # RankFusion
        try:
            rp = RankFusionPipeline(operators=deepcopy(OPS), fusion='mean')
            rp.fit(Xtr, ytr)
            rs = rp.score(Xte)
            ra = roc_auc_score(yte, rs)
            rd, rn = cov_at_k(rs, yte, tk)
            rc = rd/rn
        except:
            ra, rc, rd, rn = 0, 0, 0, int(yte.sum())
        del rp; gc.collect()

        key = f"{seed}_{dn}"
        results[key] = {"f_auc": fa, "f_cov": fc, "r_auc": ra, "r_cov": rc}
        print(f"  {dn:<13s}  Fisher: AUC={fa:.4f} Cov={fd}/{fn}({100*fc:.0f}%)  "
              f"Fuse: AUC={ra:.4f} Cov={rd}/{rn}({100*rc:.0f}%)", flush=True)

# Summary
print(f"\n{'='*90}")
print(f"  {'Dataset':<13s}  {'Fisher AUC':>12}  {'Fisher Cov':>11}  {'Fuse AUC':>12}  {'Fuse Cov':>11}  {'ΔCov':>6}")
print("-"*70)
for dn in ds_order:
    fa_list = [results[f"{s}_{dn}"]["f_auc"] for s in seeds]
    fc_list = [results[f"{s}_{dn}"]["f_cov"] for s in seeds]
    ra_list = [results[f"{s}_{dn}"]["r_auc"] for s in seeds]
    rc_list = [results[f"{s}_{dn}"]["r_cov"] for s in seeds]
    fa, fc = np.mean(fa_list), np.mean(fc_list)
    ra, rc = np.mean(ra_list), np.mean(rc_list)
    delta = rc - fc
    print(f"  {dn:<13s}  {fa:.4f}±{np.std(fa_list):.3f}  {100*fc:>5.1f}%±{100*np.std(fc_list):.1f}  "
          f"{ra:.4f}±{np.std(ra_list):.3f}  {100*rc:>5.1f}%±{100*np.std(rc_list):.1f}  "
          f"{100*delta:>+5.1f}%")

all_fc = [np.mean([results[f"{s}_{dn}"]["f_cov"] for s in seeds]) for dn in ds_order]
all_rc = [np.mean([results[f"{s}_{dn}"]["r_cov"] for s in seeds]) for dn in ds_order]
all_fa = [np.mean([results[f"{s}_{dn}"]["f_auc"] for s in seeds]) for dn in ds_order]
all_ra = [np.mean([results[f"{s}_{dn}"]["r_auc"] for s in seeds]) for dn in ds_order]
print("-"*70)
print(f"  {'MEAN':<13s}  {np.mean(all_fa):.4f}           {100*np.mean(all_fc):>5.1f}%        "
      f"{np.mean(all_ra):.4f}           {100*np.mean(all_rc):>5.1f}%       "
      f"{100*(np.mean(all_rc)-np.mean(all_fc)):>+5.1f}%")
print(f"  {'MIN':<13s}  {min(all_fa):.4f}           {100*min(all_fc):>5.1f}%        "
      f"{min(all_ra):.4f}           {100*min(all_rc):>5.1f}%")

json.dump(results, open(os.path.join(os.path.dirname(__file__), "validation_5seed.json"), "w"), indent=2)
print("\nSaved to udl/validation_5seed.json")
