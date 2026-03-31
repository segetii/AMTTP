import sys, os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, r'C:\amttp\research\udl')
from src.bench_bank_level_prospective import run_prospective_benchmark

results = run_prospective_benchmark()
for name, r in results.items():
    far = r['fp'] / max(r['fp'] + r['tn'], 1)
    print(f"{name}: AUROC={r['auc']:.4f}  TP={r['tp']}  FP={r['fp']}  FN={r['fn']}  TN={r['tn']}  FAR={far:.1%}")
