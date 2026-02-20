"""
Benchmark: Auto-Selected Laws vs Full Stack
============================================
Mammography: 6 tabular features → auto should pick Geometric + Rank (8D)
vs full 6-law stack (25D).

Shuttle: 9 tabular features → same auto selection expected.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from udl import UDLPipeline, DataProfile, select_laws, get_law_matrix_table
from udl.datasets import load_dataset
from sklearn.metrics import f1_score, accuracy_score, confusion_matrix

# ═══════════════════════════════════════════════════════════
# Print the Law Matrix
# ═══════════════════════════════════════════════════════════
print("=" * 70)
print("LAW SELECTION MATRIX")
print("=" * 70)
print(get_law_matrix_table())
print()

# ═══════════════════════════════════════════════════════════
# Dataset loader
# ═══════════════════════════════════════════════════════════
def run_benchmark(dataset_name, cost_ratio=1.0):
    X, y = load_dataset(dataset_name)
    normal = X[y == 0]
    test_X, test_y = X, y

    # ── Profile the data (using normal reference) ──
    profile = DataProfile.detect(normal)
    print(f"\n{'─' * 60}")
    print(f"Dataset: {dataset_name}")
    print(profile.summary())
    print()

    # Auto-selected operators
    auto_ops = select_laws(profile)
    print(f"Auto-selected operators: {[n for n, _ in auto_ops]}")
    auto_dim = sum(op.fit(normal).transform(normal[:1]).shape[1]
                   for _, op in select_laws(profile))
    print(f"Auto representation dims: {auto_dim}")
    print()

    results = {}

    # ── Config A: Full stack (all 6 laws, 25D) ──
    pipe_full = UDLPipeline(
        projection_method='qda-magnified',
        magnify=True,
        cost_ratio=cost_ratio,
    )
    pipe_full.fit(X, y)
    pred_full = pipe_full.predict(test_X)
    results["Full (25D)"] = _metrics(test_y, pred_full, normal, test_X)
    print(f"Full stack dims: {pipe_full.stack.total_dim}")

    # ── Config B: Auto-selected laws ──
    pipe_auto = UDLPipeline(
        projection_method='qda-magnified',
        magnify=True,
        cost_ratio=cost_ratio,
        operators='auto',
    )
    pipe_auto.fit(X, y)
    pred_auto = pipe_auto.predict(test_X)
    results["Auto"] = _metrics(test_y, pred_auto, normal, test_X)
    print(f"Auto stack dims: {pipe_auto.stack.total_dim}")
    print(f"Auto stack laws: {pipe_auto.stack.law_names_}")

    # ── Config C: Auto + marginal laws ──
    pipe_marg = UDLPipeline(
        projection_method='qda-magnified',
        magnify=True,
        cost_ratio=cost_ratio,
        operators='auto',
        include_marginal=True,
    )
    pipe_marg.fit(X, y)
    pred_marg = pipe_marg.predict(test_X)
    results["Auto+Marginal"] = _metrics(test_y, pred_marg, normal, test_X)
    print(f"Auto+marginal dims: {pipe_marg.stack.total_dim}")
    print(f"Auto+marginal laws: {pipe_marg.stack.law_names_}")

    # ── Config D: Auto + Two-Pass gravity ──
    pipe_grav = UDLPipeline(
        projection_method='qda-magnified',
        magnify=True,
        cost_ratio=cost_ratio,
        operators='auto',
        gravity='two_pass',
        gravity_strength=0.5,
        gravity_passes=3,
    )
    pipe_grav.fit(X, y)
    pred_grav = pipe_grav.predict(test_X)
    results["Auto+Gravity"] = _metrics(test_y, pred_grav, normal, test_X)

    # ── Print comparison ──
    print(f"\n{'Config':<20} {'Acc':>6} {'F1':>6} {'FP':>5} {'FP%':>7} "
          f"{'FN':>5} {'FN%':>7} {'Caught':>7}")
    print("─" * 80)
    for name, m in results.items():
        print(f"{name:<20} {m['acc']:>6.1%} {m['f1']:>6.4f} "
              f"{m['fp']:>5d} {m['fp_rate']:>6.2%} "
              f"{m['fn']:>5d} {m['fn_rate']:>6.2%} "
              f"{m['caught']:>6.1%}")

    return results


def _metrics(y_true, y_pred, normal, X):
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    n_normal = (y_true == 0).sum()
    n_anomaly = (y_true == 1).sum()
    return {
        "acc": accuracy_score(y_true, y_pred),
        "f1": f1_score(y_true, y_pred),
        "fp": fp,
        "fp_rate": fp / n_normal,
        "fn": fn,
        "fn_rate": fn / n_anomaly,
        "caught": tp / n_anomaly,
        "tp": tp,
    }


# ═══════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "═" * 70)
    print("MAMMOGRAPHY BENCHMARK (cost=1)")
    print("═" * 70)
    run_benchmark("mammography", cost_ratio=1.0)

    print("\n" + "═" * 70)
    print("MAMMOGRAPHY BENCHMARK (cost=10)")
    print("═" * 70)
    run_benchmark("mammography", cost_ratio=10.0)

    print("\n" + "═" * 70)
    print("SHUTTLE BENCHMARK (cost=1)")
    print("═" * 70)
    run_benchmark("shuttle", cost_ratio=1.0)
