"""Quick production test -- mammography + shuttle with all modes."""
import sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, r'c:\amttp')
import numpy as np
from udl.pipeline import UDLPipeline
from udl.datasets import load_mammography, load_shuttle
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, f1_score, roc_auc_score

def run_dataset(ds_name, X, y):
    if ds_name == 'shuttle' and len(X) > 15000:
        rng = np.random.RandomState(42)
        idx = rng.choice(len(X), 10000, replace=False)
        X, y = X[idx], y[idx]

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.3, random_state=42, stratify=y)
    n_normal = int((y_te == 0).sum())
    n_anomaly = int((y_te == 1).sum())

    print(f"\n  DATASET: {ds_name.upper()}  ({len(X_te)} test, {n_anomaly} anomalies, {n_anomaly/len(y_te)*100:.1f}% rate)")
    print(f"  {'Mode':<22} {'Threshold':>10} {'TP':>5} {'TN':>6} {'FP':>5} {'FN':>4} {'FNR':>8} {'FPR':>8} {'Prec':>7} {'F1':>8} {'Acc':>7}")
    print(f"  {'-'*22} {'-'*10} {'-'*5} {'-'*6} {'-'*5} {'-'*4} {'-'*8} {'-'*8} {'-'*7} {'-'*8} {'-'*7}")

    for cost, label in [(1.0, "F1-optimal"), (10.0, "High-stakes 10x"), (50.0, "Ultra-safe 50x")]:
        p = UDLPipeline(projection_method='qda-magnified', cost_ratio=cost)
        p.magnifier_.verbose = False
        p.fit(X_tr, y_tr)
        preds = p.predict(X_te)
        probs = p.predict_proba(X_te)
        info = p.get_threshold_info()
        tn, fp, fn, tp = confusion_matrix(y_te, preds).ravel()
        f1 = f1_score(y_te, preds)
        prec = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
        thr = info["active_threshold"]
        fnr = fn / n_anomaly * 100
        fpr = fp / n_normal * 100
        acc = (tp + tn) / len(y_te) * 100
        print(f"  {label:<22} {thr:>10.6f} {tp:>5} {tn:>6} {fp:>5} {fn:>4} {fnr:>7.2f}% {fpr:>7.2f}% {prec:>6.1f}% {f1:>8.4f} {acc:>6.1f}%")

    # Tiered output for cost=10
    p10 = UDLPipeline(projection_method='qda-magnified', cost_ratio=10.0)
    p10.magnifier_.verbose = False
    p10.fit(X_tr, y_tr)
    tiers, tier_probs = p10.predict_tiered(X_te)
    info10 = p10.get_threshold_info()

    lo, hi = info10['review_band']
    print(f"\n  TIERED OUTPUT (cost=10x, band={lo:.3f}-{hi:.3f}):")
    for tier_val, tier_label in [(0, "CLEAR"), (1, "REVIEW"), (2, "ALERT")]:
        mask = tiers == tier_val
        n = mask.sum()
        if n > 0:
            anom = (y_te[mask] == 1).sum()
            norm = (y_te[mask] == 0).sum()
            if tier_val == 0:
                leak_pct = anom / max(n_anomaly, 1) * 100
                print(f"    {tier_label:<6s}: {n:>5d} ({n/len(y_te)*100:>5.1f}%)  -- {norm} normals correct, {anom} anomalies leaked ({leak_pct:.1f}% of all anomalies)")
            elif tier_val == 2:
                fa_pct = norm / max(n, 1) * 100
                print(f"    {tier_label:<6s}: {n:>5d} ({n/len(y_te)*100:>5.1f}%)  -- {anom} real anomalies, {norm} false alarms ({fa_pct:.1f}% false alarm rate)")
            else:
                print(f"    {tier_label:<6s}: {n:>5d} ({n/len(y_te)*100:>5.1f}%)  -- {anom} anomalies + {norm} normals need human review")
        else:
            print(f"    {tier_label:<6s}: {n:>5d} ( 0.0%)")


print("=" * 100)
print("  PRODUCTION-GRADE FP/FN ANALYSIS -- QDA-MAGNIFIED WITH AUTO-CALIBRATION")
print("=" * 100)

for ds_name, loader in [("mammography", load_mammography), ("shuttle", load_shuttle)]:
    X, y = loader()
    run_dataset(ds_name, X, y)

print("\n" + "=" * 100)
print("  DONE")
print("=" * 100)
