"""
Anomaly Detection AUC Comparison — v23 supplement
===================================================

Evaluates each tensor representation as an anomaly detector on the
crypto test period, using multiple ground-truth label definitions.

Anomaly scores (one per day, aggregated over 4 agents by MAX):
  plain     -> Mahalanobis distance from train distribution in raw (d=2) space
  udl       -> UDLTransform (d=8): Mahalanobis in compressed space
  rtd       -> ReducedTensorDescriptor: picks the Mahalanobis feature (idx n_eigs)
  coverage  -> UDLPostSimScorer.score() = RMS z-deviation across all operator features
  mdn       -> AnomalyTensor.novelty (per-agent)
  engine    -> EarlyWarning.geom_score from the plain-panel physics engine (v22 baseline)

Ground-truth labels (crypto test period, 2023-01-01 -> 2026-04-25):
  crash_1p  -> daily ret_eth < -1%   (moderate drawdown)
  crash_3p  -> daily ret_eth < -3%   (significant drawdown)
  tail_5pct -> bottom 5th percentile of ret_eth in test period
  bigtail   -> |ret_eth| > 2% (any large move in either direction)
"""
from __future__ import annotations
import os, sys
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.spatial.distance import mahalanobis

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from run_crypto_pairs_v19 import (
    fetch_and_prepare, add_cross_market_features,
    fetch_binance_funding, add_leverage_features,
    _build_state_panel, TRAIN_START, TRAIN_END, TEST_START,
)
from run_crypto_pairs_v22 import (
    calibrate_frozen_engine, patch_precursor_scale, emit_global_signals,
    HISTORY_LEN, ROLL_WIN,
)

sys.path.insert(0, r'C:\amttp\research\adaptive-friction')
from collapse_geometry.udl_transform import (
    UDLTransform, _StatFeatures, _ChaosFeatures, _SpecFeatures, _GeomFeatures,
)

sys.path.insert(0, r'C:\amttp\src')
from system_mode import ReducedTensorDescriptor, UDLPostSimScorer

sys.path.insert(0, r'C:\amttp\research\udl')
from udl.tensor import AnomalyTensor

try:
    from sklearn.metrics import roc_auc_score
except ImportError:
    print("ERROR: sklearn not available"); sys.exit(1)


# ─────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────

def panel_to_flat(X_panel, train_mask_arr):
    """Return X_flat (T*N, d), X_train_flat (n_train*N, d)."""
    T, N, d = X_panel.shape
    return (X_panel.reshape(T*N, d),
            X_panel[train_mask_arr].reshape(-1, d))


def max_over_agents(scores_flat, T, N):
    """Aggregate per-agent anomaly score to per-day score by taking MAX."""
    return scores_flat.reshape(T, N).max(axis=1)


def mahal_scores(X_flat, X_train_flat):
    """Mahalanobis distance from train distribution for each point."""
    mu  = X_train_flat.mean(0)
    cov = np.cov(X_train_flat.T)
    if cov.ndim == 0:
        cov = np.array([[float(cov)]])
    # regularise
    cov += np.eye(cov.shape[0]) * 1e-6
    try:
        VI = np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        VI = np.eye(cov.shape[0])
    diff = X_flat - mu
    m = np.sqrt(np.einsum('ij,jk,ik->i', diff, VI, diff))
    return np.nan_to_num(m, nan=0.0)


def compute_auc(scores, labels):
    """Compute ROC-AUC; return nan if only one class present."""
    if labels.sum() == 0 or labels.sum() == len(labels):
        return float('nan')
    return roc_auc_score(labels, scores)


# ─────────────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("  AUC Comparison — Anomaly Detection per Tensor Representation")
    print("=" * 80)

    # ── data ─────────────────────────────────────────────────────────
    print("\n[1] Loading data ...")
    df = fetch_and_prepare()
    df = add_cross_market_features(df)
    funding = fetch_binance_funding(symbols=['ETHUSDT','BTCUSDT'], start='2020-06-01')
    df = add_leverage_features(df, funding)

    train_mask     = (df.index >= TRAIN_START) & (df.index <= TRAIN_END)
    test_mask      = df.index >= TEST_START
    train_mask_arr = np.asarray(train_mask, dtype=bool)
    test_mask_arr  = np.asarray(test_mask,  dtype=bool)

    T = len(df)

    # ── ground-truth labels (test period only) ─────────────────────
    ret_eth = df['ret_eth'].fillna(0.0)
    ret_test = ret_eth[test_mask_arr]
    tail5 = float(np.percentile(ret_test, 5))

    labels = {
        'crash_1p':  (ret_eth < -0.01).astype(int).values[test_mask_arr],
        'crash_3p':  (ret_eth < -0.03).astype(int).values[test_mask_arr],
        'tail_5pct': (ret_eth <= tail5).astype(int).values[test_mask_arr],
        'bigtail':   (ret_eth.abs() > 0.02).astype(int).values[test_mask_arr],
    }
    print(f"  Label counts in test ({int(test_mask_arr.sum())} days):")
    for k, v in labels.items():
        print(f"    {k}: {v.sum()} positive ({100*v.mean():.1f}%)")

    # ── plain panel ───────────────────────────────────────────────────
    print("\n[2] Building panels ...")
    X_plain = _build_state_panel(df)
    N = X_plain.shape[1]
    X_flat, X_tr = panel_to_flat(X_plain, train_mask_arr)
    print(f"  plain   : {X_plain.shape}")

    # UDL
    udl = UDLTransform(n_components=8, standardize=True)
    udl.fit(X_plain[train_mask_arr])
    X_udl = udl.transform(X_plain)
    X_udl_flat, X_udl_tr = panel_to_flat(X_udl, train_mask_arr)
    print(f"  udl     : {X_udl.shape}")

    # RTD
    rtd = ReducedTensorDescriptor(k_neighbors=15, eps_hessian=1e-4)
    rtd.fit(X_tr)
    X_rtd_flat = np.nan_to_num(rtd.transform(X_flat), nan=0.0)
    X_rtd_tr   = np.nan_to_num(rtd.transform(X_tr),   nan=0.0)
    print(f"  rtd     : {X_rtd_flat.reshape(T,N,-1).shape}")

    # Coverage
    cov_scorer = UDLPostSimScorer(k=15, max_dim=12, n_components=8)
    cov_scorer.fit(X_tr)
    print(f"  coverage: fitted")

    # MDN
    mu_in = X_tr.mean(0); sd_in = X_tr.std(0) + 1e-10
    X_std     = (X_flat - mu_in) / sd_in
    X_std_tr  = (X_tr   - mu_in) / sd_in
    stat  = _StatFeatures().fit(X_std_tr)
    chaos = _ChaosFeatures().fit(X_std_tr)
    spec  = _SpecFeatures().fit(X_std_tr)
    geom  = _GeomFeatures(n_pca=2).fit(X_std_tr)
    R_all   = np.nan_to_num(np.hstack([stat.transform(X_std),
                                        chaos.transform(X_std),
                                        spec.transform(X_std),
                                        geom.transform(X_std)]))
    R_train = np.nan_to_num(np.hstack([stat.transform(X_std_tr),
                                        chaos.transform(X_std_tr),
                                        spec.transform(X_std_tr),
                                        geom.transform(X_std_tr)]))
    at = AnomalyTensor()
    at.fit(R_train)
    res_tr  = at.build(R_train, [5,3,4,5])
    at.store_ref_law_stats(res_tr)
    res_all = at.build(R_all, [5,3,4,5])
    mdn_novelty_flat = np.nan_to_num(res_all.novelty)
    print(f"  mdn     : novelty shape {mdn_novelty_flat.shape}")

    # Engine geom_score on plain panel
    print("\n[3] Running physics engine (plain panel) for geom_score ...")
    M, net, geom_e, lyap, info, ews, e_star, sigma_n = calibrate_frozen_engine(
        X_plain, train_mask_arr)
    patch_precursor_scale(ews, M, X_plain[train_mask_arr])
    F = emit_global_signals(df, X_plain, M, net, geom_e, lyap, ews, sigma_n)
    engine_score_day = F['geom_score'].fillna(0.0).values    # (T,) per-day already

    # ── compute per-day anomaly scores ───────────────────────────────
    print("\n[4] Computing anomaly scores ...")

    scores = {}

    # plain: Mahalanobis in d=2 space, max over agents
    s_plain = max_over_agents(mahal_scores(X_flat, X_tr), T, N)
    scores['plain_mahal']   = s_plain

    # udl: Mahalanobis in d=8 UDL space, max over agents
    s_udl = max_over_agents(mahal_scores(X_udl_flat, X_udl_tr), T, N)
    scores['udl_mahal']     = s_udl

    # rtd: mahalanobis feature (index n_eigs = 2 for d=2), max over agents
    mahal_idx = 2   # position of Mahalanobis in ReducedTensorDescriptor output
    s_rtd = max_over_agents(np.abs(X_rtd_flat[:, mahal_idx]), T, N)
    scores['rtd_mahal']     = s_rtd

    # rtd: full RMS anomaly score using all descriptor features
    X_rtd_tr_mu = X_rtd_tr.mean(0);  X_rtd_tr_sd = X_rtd_tr.std(0) + 1e-10
    rtd_z = (X_rtd_flat - X_rtd_tr_mu) / X_rtd_tr_sd
    s_rtd_rms = max_over_agents(np.sqrt(np.mean(rtd_z**2, axis=1)), T, N)
    scores['rtd_rms']       = s_rtd_rms

    # coverage: RMS z-score (UDLPostSimScorer.score), max over agents
    s_cov = max_over_agents(
        np.nan_to_num(cov_scorer.score(X_flat)), T, N)
    scores['coverage_score'] = s_cov

    # mdn: novelty, max over agents
    s_mdn = max_over_agents(mdn_novelty_flat, T, N)
    scores['mdn_novelty']   = s_mdn

    # engine geom_score (already per-day)
    scores['engine_geom']   = engine_score_day

    # ── AUC table ─────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  ANOMALY DETECTION AUC  (test period 2023-01-01 -> 2026-04-25)")
    print("=" * 80)
    header = f"  {'Score':<20}" + "".join(f"  {k:<12}" for k in labels)
    print(header)
    print("  " + "-" * 74)

    best_per_label = {k: (0.0, '') for k in labels}
    auc_table = {}
    for score_name, score_arr in scores.items():
        score_test = score_arr[test_mask_arr]
        row = f"  {score_name:<20}"
        auc_table[score_name] = {}
        for lbl_name, lbl_arr in labels.items():
            auc = compute_auc(score_test, lbl_arr)
            auc_table[score_name][lbl_name] = auc
            row += f"  {auc:12.4f}"
            if auc > best_per_label[lbl_name][0]:
                best_per_label[lbl_name] = (auc, score_name)
        print(row)

    print()
    print("  Best scorer per label:")
    for lbl_name, (auc, name) in best_per_label.items():
        print(f"    {lbl_name:<14} -> {name:<20} AUC={auc:.4f}")

    # ── mean AUC rank ─────────────────────────────────────────────────
    print()
    rank = sorted(
        [(name, np.nanmean(list(d.values()))) for name, d in auc_table.items()],
        key=lambda x: -x[1])
    print("  Mean AUC ranking across all 4 label types:")
    for i, (name, mean_auc) in enumerate(rank, 1):
        print(f"    {i}. {name:<22}  mean AUC = {mean_auc:.4f}")
    print("=" * 80)


if __name__ == "__main__":
    main()
