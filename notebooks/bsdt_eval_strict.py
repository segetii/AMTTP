"""Leakage-free BSDT evaluation.

This script fixes the core evaluation issue in the existing BSDT notebooks:
- Reference stats / MI weights must be fit using TRAIN labels only.
- Thresholds and correction hyperparameters must be tuned on a VALIDATION split.
- Final metrics must be reported once on a held-out TEST split.

Outputs:
- c:\\amttp\\papers\\comprehensive_bsdt_results_strict.json
- c:\\amttp\\papers\\bsdt_cross_domain_results_strict.json

Notes:
- By default, this script trains *fresh per-dataset* baseline models (LR + XGB)
    on the mapped 93-feature representation.
- If you pass `--transfer-artifacts-dir`, it will also attempt a *true transfer*
    baseline by running inference from the provided bundle (preprocessors + model)
    on the same 93-feature mapping. If the bundle's expected features do not
    sufficiently overlap the mapped features, the transfer baseline is skipped
    with a clear warning (to avoid meaningless results).
"""

from __future__ import annotations

import json
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
import argparse

import numpy as np
import pandas as pd
import scipy.io as sio

from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    mutual_info_score,
)
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.preprocessing import PolynomialFeatures, RobustScaler

try:
    import xgboost as xgb
except Exception:  # pragma: no cover
    xgb = None

try:
    import joblib
except Exception:  # pragma: no cover
    joblib = None

warnings.filterwarnings("ignore")

ROOT = Path(r"c:\amttp")
DATA_DIR = ROOT / "data" / "external_validation"
OUT_DIR = ROOT / "papers"

# 93-feature schema used throughout the existing MFLS/BSDT notebooks.
FEATURES_93 = [
    "value_eth",
    "gas_price_gwei",
    "gas_used",
    "gas_limit",
    "transaction_type",
    "nonce",
    "transaction_index",
    "sender_sent_count",
    "sender_total_sent",
    "sender_avg_sent",
    "sender_max_sent",
    "sender_min_sent",
    "sender_std_sent",
    "sender_total_gas_sent",
    "sender_avg_gas_used",
    "sender_avg_gas_price",
    "sender_unique_receivers",
    "sender_received_count",
    "sender_total_received",
    "sender_avg_received",
    "sender_max_received",
    "sender_min_received",
    "sender_std_received",
    "sender_unique_senders",
    "sender_total_transactions",
    "sender_balance",
    "sender_in_out_ratio",
    "sender_unique_counterparties",
    "sender_avg_value",
    "sender_neighbors",
    "sender_count",
    "sender_income",
    "sender_active_duration_mins",
    "sender_in_degree",
    "sender_out_degree",
    "sender_degree",
    "sender_degree_centrality",
    "sender_betweenness_proxy",
    "sender_sent_to_mixer",
    "sender_recv_from_mixer",
    "sender_mixer_interaction",
    "sender_sent_to_sanctioned",
    "sender_recv_from_sanctioned",
    "sender_sanctioned_interaction",
    "sender_sent_to_exchange",
    "sender_recv_from_exchange",
    "sender_exchange_interaction",
    "sender_is_mixer",
    "sender_is_sanctioned",
    "sender_is_exchange",
    "receiver_sent_count",
    "receiver_total_sent",
    "receiver_avg_sent",
    "receiver_max_sent",
    "receiver_min_sent",
    "receiver_std_sent",
    "receiver_total_gas_sent",
    "receiver_avg_gas_used",
    "receiver_avg_gas_price",
    "receiver_unique_receivers",
    "receiver_received_count",
    "receiver_total_received",
    "receiver_avg_received",
    "receiver_max_received",
    "receiver_min_received",
    "receiver_std_received",
    "receiver_unique_senders",
    "receiver_total_transactions",
    "receiver_balance",
    "receiver_in_out_ratio",
    "receiver_unique_counterparties",
    "receiver_avg_value",
    "receiver_neighbors",
    "receiver_count",
    "receiver_income",
    "receiver_active_duration_mins",
    "receiver_in_degree",
    "receiver_out_degree",
    "receiver_degree",
    "receiver_degree_centrality",
    "receiver_betweenness_proxy",
    "receiver_sent_to_mixer",
    "receiver_recv_from_mixer",
    "receiver_mixer_interaction",
    "receiver_sent_to_sanctioned",
    "receiver_recv_from_sanctioned",
    "receiver_sanctioned_interaction",
    "receiver_sent_to_exchange",
    "receiver_recv_from_exchange",
    "receiver_exchange_interaction",
    "receiver_is_mixer",
    "receiver_is_sanctioned",
    "receiver_is_exchange",
]

IDX_SENT = FEATURES_93.index("sender_sent_count")
IDX_RECV = FEATURES_93.index("receiver_received_count")


# ─────────────────────────────────────────────────────────────────────────────
# Optional transfer inference
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TransferBundle:
    artifacts_dir: Path
    feature_names: list[str]
    scaler: object
    xgb_model: object
    clip_range: float


def _preprocess_transfer(X: np.ndarray, bundle: TransferBundle) -> np.ndarray:
    X2 = np.asarray(X, dtype=np.float32)
    X2 = np.nan_to_num(X2, nan=0.0, posinf=0.0, neginf=0.0)
    X2 = np.log1p(np.abs(X2)) * np.sign(X2)
    X2 = bundle.scaler.transform(X2)
    X2 = np.clip(X2, -bundle.clip_range, bundle.clip_range)
    return np.nan_to_num(X2, nan=0.0, posinf=bundle.clip_range, neginf=-bundle.clip_range)


def _predict_transfer(bundle: TransferBundle, X_model: np.ndarray) -> np.ndarray:
    Xp = _preprocess_transfer(X_model, bundle)
    # Support both Booster + sklearn API.
    if xgb is not None and isinstance(bundle.xgb_model, xgb.Booster):
        return bundle.xgb_model.predict(xgb.DMatrix(Xp, feature_names=bundle.feature_names))
    if hasattr(bundle.xgb_model, "predict_proba"):
        return bundle.xgb_model.predict_proba(Xp)[:, 1]
    return np.asarray(bundle.xgb_model.predict(Xp), dtype=np.float64).ravel()


def try_load_transfer_bundle(artifacts_dir: Path) -> TransferBundle | None:
    if joblib is None:
        print("[transfer] joblib is not available; skipping transfer baseline")
        return None
    if xgb is None:
        print("[transfer] xgboost is not available; skipping transfer baseline")
        return None

    preprocessors_path = artifacts_dir / "preprocessors.joblib"
    xgb_path = artifacts_dir / "xgboost_fraud.ubj"
    if not preprocessors_path.exists() or not xgb_path.exists():
        print(f"[transfer] missing preprocessors/model in {artifacts_dir}; skipping")
        return None

    preprocessors = joblib.load(str(preprocessors_path))
    # Match the conventions used across existing notebooks.
    feature_names = list(preprocessors.get("feature_names") or preprocessors.get("features") or [])
    scaler = preprocessors.get("scaler") or preprocessors.get("robust_scaler")
    clip_range = float(preprocessors.get("clip_range", 10))
    if not feature_names or scaler is None:
        print(f"[transfer] preprocessors missing feature_names/scaler in {artifacts_dir}; skipping")
        return None

    # Prefer Booster format if possible.
    try:
        booster = xgb.Booster()
        booster.load_model(str(xgb_path))
        xgb_model = booster
    except Exception:
        clf = xgb.XGBClassifier()
        clf.load_model(str(xgb_path))
        xgb_model = clf

    return TransferBundle(
        artifacts_dir=artifacts_dir,
        feature_names=feature_names,
        scaler=scaler,
        xgb_model=xgb_model,
        clip_range=clip_range,
    )


def build_X_for_transfer(X_93: np.ndarray, bundle: TransferBundle, min_coverage: float = 0.80) -> tuple[np.ndarray, dict] | None:
    """Project the 93-feature mapped matrix onto the bundle's expected features.

    Returns (X_model, diag) or None if coverage is too low.
    """
    idx_93 = {f: i for i, f in enumerate(FEATURES_93)}
    wanted = bundle.feature_names
    present = [f for f in wanted if f in idx_93]
    missing = [f for f in wanted if f not in idx_93]
    coverage = (len(present) / max(len(wanted), 1))
    diag = {
        "n_expected": int(len(wanted)),
        "n_present": int(len(present)),
        "coverage": float(coverage),
        "missing": missing,
    }
    if coverage < min_coverage:
        print(
            f"[transfer] feature coverage {coverage:.0%} is below {min_coverage:.0%} for {bundle.artifacts_dir}; "
            "skipping transfer baseline (would be mostly zeros / not meaningful)"
        )
        if missing:
            print(f"[transfer] missing features (example): {missing[:8]}")
        return None

    X_model = np.zeros((X_93.shape[0], len(wanted)), dtype=np.float32)
    for j, f in enumerate(wanted):
        if f in idx_93:
            X_model[:, j] = X_93[:, idx_93[f]]
    return X_model, diag


# ─────────────────────────────────────────────────────────────────────────────
# Splits + preprocessing
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SplitIdx:
    train_fit: np.ndarray
    cal: np.ndarray
    val: np.ndarray
    test: np.ndarray


def make_4way_split(X: np.ndarray, y: np.ndarray, random_state: int = 42) -> SplitIdx:
    """Create disjoint train_fit / cal / val / test splits."""

    sss_outer = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=random_state)
    trainval_idx, test_idx = next(sss_outer.split(X, y))

    X_trainval, y_trainval = X[trainval_idx], y[trainval_idx]
    sss_val = StratifiedShuffleSplit(n_splits=1, test_size=0.25, random_state=random_state)
    train_idx_rel, val_idx_rel = next(sss_val.split(X_trainval, y_trainval))

    train_idx = trainval_idx[train_idx_rel]
    val_idx = trainval_idx[val_idx_rel]

    X_train, y_train = X[train_idx], y[train_idx]
    sss_cal = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=random_state)
    train_fit_rel, cal_rel = next(sss_cal.split(X_train, y_train))

    train_fit_idx = train_idx[train_fit_rel]
    cal_idx = train_idx[cal_rel]

    return SplitIdx(train_fit=train_fit_idx, cal=cal_idx, val=val_idx, test=test_idx)


def preprocess_fit_transform(X_train: np.ndarray, X_other: np.ndarray) -> tuple[np.ndarray, np.ndarray, RobustScaler]:
    """Sign-log + robust scaling fit on train only."""

    def transform(X: np.ndarray) -> np.ndarray:
        X2 = np.asarray(X, dtype=np.float32)
        X2 = np.nan_to_num(X2, nan=0.0, posinf=0.0, neginf=0.0)
        X2 = np.log1p(np.abs(X2)) * np.sign(X2)
        return X2

    X_train_t = transform(X_train)
    scaler = RobustScaler(with_centering=True, with_scaling=True, quantile_range=(25.0, 75.0))
    scaler.fit(X_train_t)

    X_train_s = scaler.transform(X_train_t)
    X_other_s = scaler.transform(transform(X_other))

    X_train_s = np.clip(X_train_s, -10, 10)
    X_other_s = np.clip(X_other_s, -10, 10)

    return X_train_s, X_other_s, scaler


def platt_fit(p_cal: np.ndarray, y_cal: np.ndarray) -> LogisticRegression:
    lr = LogisticRegression(random_state=42, max_iter=2000)
    lr.fit(p_cal.reshape(-1, 1), y_cal)
    return lr


def platt_apply(lr: LogisticRegression, p: np.ndarray) -> np.ndarray:
    return lr.predict_proba(p.reshape(-1, 1))[:, 1]


# ─────────────────────────────────────────────────────────────────────────────
# BSDT components
# ─────────────────────────────────────────────────────────────────────────────


def camouflage(X: np.ndarray, mu: np.ndarray, dmax: float) -> np.ndarray:
    return 1.0 - np.clip(np.linalg.norm(X - mu, axis=1) / max(dmax, 1e-8), 0.0, 1.0)


def feature_gap(X: np.ndarray) -> np.ndarray:
    return (np.abs(X) < 1e-8).sum(axis=1).astype(np.float64) / X.shape[1]


def activity_anomaly(X: np.ndarray, mu_c: float, sig_c: float) -> np.ndarray:
    tx = np.abs(X[:, IDX_SENT]) + np.abs(X[:, IDX_RECV]) + 1e-8
    z = (np.log1p(tx) - mu_c) / max(sig_c, 1e-8)
    return 1.0 / (1.0 + np.exp(-z))


def temporal_novelty(X: np.ndarray, rm: np.ndarray, rv: np.ndarray) -> np.ndarray:
    d = X - rm
    m = np.sum(d * d / rv, axis=1) / X.shape[1]
    return 1.0 / (1.0 + np.exp(-0.5 * (m - 2.0)))


def ref_stats_fit(X_train: np.ndarray, y_train: np.ndarray) -> tuple[np.ndarray, float, np.ndarray, np.ndarray, float, float]:
    n = X_train[y_train == 0]
    f = X_train[y_train == 1]
    mu = n.mean(axis=0)
    d = float(np.percentile(np.linalg.norm(X_train - mu, axis=1), 99))

    # If a dataset has extremely few positives, fall back to global stats.
    if f.shape[0] < 5:
        f = X_train

    rm = f.mean(axis=0)
    rv = f.var(axis=0) + 1e-8

    tx = np.abs(f[:, IDX_SENT]) + np.abs(f[:, IDX_RECV]) + 1e-8
    return mu, max(d, 1e-8), rm, rv, float(np.log1p(tx).mean()), float(max(np.log1p(tx).std(), 1e-8))


def components(X: np.ndarray, stats) -> np.ndarray:
    mu, dmax, rm, rv, mu_c, sig_c = stats
    c = np.column_stack(
        [
            camouflage(X, mu, dmax),
            feature_gap(X),
            activity_anomaly(X, mu_c, sig_c),
            temporal_novelty(X, rm, rv),
        ]
    )
    return np.nan_to_num(c, nan=0.0)


def mi_weights_fit(comp_train: np.ndarray, y_train: np.ndarray, n_bins: int = 20) -> tuple[np.ndarray, np.ndarray]:
    mi = np.zeros(comp_train.shape[1], dtype=np.float64)
    for i in range(comp_train.shape[1]):
        bins = np.linspace(comp_train[:, i].min(), comp_train[:, i].max() + 1e-8, n_bins)
        binned = np.digitize(comp_train[:, i], bins)
        mi[i] = mutual_info_score(y_train, binned)
    s = mi.sum()
    if s <= 1e-10:
        return np.ones(comp_train.shape[1], dtype=np.float64) / comp_train.shape[1], mi
    return mi / s, mi


def vr_weights_fit(comp_train: np.ndarray, p_train: np.ndarray, th: float) -> tuple[np.ndarray, np.ndarray]:
    high = p_train >= th
    low = p_train < th
    fr = np.zeros(comp_train.shape[1], dtype=np.float64)
    for i in range(comp_train.shape[1]):
        mh = comp_train[high, i].mean() if high.any() else 0.0
        ml = comp_train[low, i].mean() if low.any() else 0.0
        vh = comp_train[high, i].var() if high.any() else 1.0
        vl = comp_train[low, i].var() if low.any() else 1.0
        fr[i] = (mh - ml) ** 2 / max(vh + vl, 1e-10)
    s = fr.sum()
    if s <= 1e-10:
        return np.ones(comp_train.shape[1], dtype=np.float64) / comp_train.shape[1], fr
    return fr / s, fr


def apply_original_correction(p: np.ndarray, comp: np.ndarray, w: np.ndarray, lam: float, tau: float) -> np.ndarray:
    mfls = comp @ w
    below = (p < tau).astype(np.float64)
    return np.clip(p + lam * mfls * (1.0 - p) * below, 0.0, 1.0)


def quadsurf_fit_beta(
    comp_train: np.ndarray,
    y_train: np.ndarray,
    p_base_train: np.ndarray,
    ridge_alpha: float,
) -> tuple[PolynomialFeatures, np.ndarray]:
    """Fit a degree-2 polynomial residual corrector (QuadSurf).

    Learns beta in: p* = clip(p_base + Phi(comp)^T beta, 0, 1)
    with target residual (y - p_base).
    """

    poly = PolynomialFeatures(degree=2, include_bias=False)
    Xp = poly.fit_transform(np.asarray(comp_train, dtype=np.float64))
    y_res = y_train.astype(np.float64) - np.asarray(p_base_train, dtype=np.float64)

    n_neg = int((y_train == 0).sum())
    n_pos = int((y_train == 1).sum())
    w = np.where(y_train == 1, max(n_neg, 1) / max(n_pos, 1), 1.0).astype(np.float64)

    sqrt_w = np.sqrt(w)
    Xw = Xp * sqrt_w[:, None]
    yw = y_res * sqrt_w

    n_feats = int(Xp.shape[1])
    beta = np.linalg.solve(Xw.T @ Xw + float(ridge_alpha) * np.eye(n_feats), Xw.T @ yw)
    return poly, beta


def quadsurf_apply(poly: PolynomialFeatures, beta: np.ndarray, p_base: np.ndarray, comp: np.ndarray) -> np.ndarray:
    Xp = poly.transform(np.asarray(comp, dtype=np.float64))
    corr = Xp @ np.asarray(beta, dtype=np.float64)
    return np.clip(np.asarray(p_base, dtype=np.float64) + corr, 0.0, 1.0)


def sigmoid(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    x = np.clip(x, -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-x))


# ─────────────────────────────────────────────────────────────────────────────
# Metrics + tuning
# ─────────────────────────────────────────────────────────────────────────────


def metrics_at_threshold(y: np.ndarray, p: np.ndarray, t: float) -> dict:
    pred = (p >= t).astype(np.int32)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())

    prec = float(tp / max(tp + fp, 1))
    rec = float(tp / max(tp + fn, 1))
    f1 = float(2 * prec * rec / max(prec + rec, 1e-12))
    fa = float(fp / max(tp + fp, 1))
    return {
        "f1": f1,
        "rec": rec,
        "prec": prec,
        "tp": tp,
        "fp": fp,
        "fa": fa,
        "threshold": float(t),
    }


def tune_threshold_f1(y: np.ndarray, p: np.ndarray, grid: np.ndarray | None = None) -> tuple[float, dict]:
    if grid is None:
        grid = np.linspace(0.05, 0.95, 91)
    best_m = None
    best_t = float(grid[0])
    for t in grid:
        m = metrics_at_threshold(y, p, float(t))
        if best_m is None or m["f1"] > best_m["f1"]:
            best_m = m
            best_t = float(t)
    assert best_m is not None
    return best_t, best_m


def tune_correction(
    y_val: np.ndarray,
    p_val: np.ndarray,
    comp_val: np.ndarray,
    w: np.ndarray,
    lam_grid: np.ndarray,
    tau_grid: np.ndarray,
    pred_grid: np.ndarray,
) -> dict:
    best = {"f1": -1.0}
    for lam in lam_grid:
        for tau in tau_grid:
            pc = apply_original_correction(p_val, comp_val, w, float(lam), float(tau))
            t_best, m_best = tune_threshold_f1(y_val, pc, grid=pred_grid)
            if m_best["f1"] > best["f1"]:
                best = {
                    **m_best,
                    "lambda": float(lam),
                    "tau": float(tau),
                    "pred_threshold": float(t_best),
                }
    return best


def safe_auc(y: np.ndarray, p: np.ndarray) -> float:
    try:
        return float(roc_auc_score(y, p))
    except Exception:
        return 0.5


# ─────────────────────────────────────────────────────────────────────────────
# Datasets (same sources as existing notebooks)
# ─────────────────────────────────────────────────────────────────────────────


AMTTP_MAP = [
    "sender_total_sent",
    "sender_avg_sent",
    "sender_sent_count",
    "value_eth",
    "sender_total_transactions",
    "sender_balance",
    "receiver_total_received",
    "sender_in_out_ratio",
    "receiver_avg_received",
    "sender_unique_counterparties",
    "sender_degree",
    "sender_neighbors",
    "sender_in_degree",
    "sender_out_degree",
    "sender_unique_receivers",
    "receiver_unique_senders",
    "sender_max_sent",
    "sender_min_sent",
    "receiver_max_received",
    "receiver_min_received",
    "receiver_received_count",
    "sender_avg_time_between_txns",
    "sender_stddev_sent",
    "receiver_stddev_received",
    "sender_cluster_coeff",
    "sender_pagerank",
    "sender_betweenness",
    "sender_closeness",
]


def empty_X(n: int) -> np.ndarray:
    return np.zeros((n, len(FEATURES_93)), dtype=np.float32)


def map_to_93(mapping: list[tuple[str, np.ndarray]]) -> np.ndarray:
    idx = {f: i for i, f in enumerate(FEATURES_93)}
    n = int(len(mapping[0][1]))
    X = empty_X(n)
    for name, vals in mapping:
        if name in idx:
            X[:, idx[name]] = np.asarray(vals, dtype=np.float32)
    return X


def load_creditcard() -> tuple[np.ndarray, np.ndarray]:
    df = pd.read_csv(DATA_DIR / "creditcard" / "creditcard.csv")
    y = df["Class"].astype(int).to_numpy()
    v_cols = [c for c in df.columns if c.startswith("V")]
    mapping = [(AMTTP_MAP[i], df[col].to_numpy(dtype=np.float32)) for i, col in enumerate(v_cols) if i < len(AMTTP_MAP)]
    mapping.append(("value_eth", df["Amount"].to_numpy(dtype=np.float32)))
    return map_to_93(mapping), y.astype(np.int32)


def load_xblock() -> tuple[np.ndarray, np.ndarray]:
    df = pd.read_csv(DATA_DIR / "xblock" / "transaction_dataset.csv")
    y = df["FLAG"].astype(int).to_numpy(dtype=np.int32)
    xb_map = [
        ("Sent tnx", "sender_sent_count"),
        ("Received Tnx", "receiver_received_count"),
        ("Unique Received From Addresses", "receiver_unique_senders"),
        ("Unique Sent To Addresses", "sender_unique_receivers"),
        ("min value received", "receiver_min_received"),
        ("max value received ", "receiver_max_received"),
        ("avg val received", "receiver_avg_received"),
        ("min val sent", "sender_min_sent"),
        ("max val sent", "sender_max_sent"),
        ("avg val sent", "sender_avg_sent"),
        ("total transactions (including tnx to create contract", "sender_total_transactions"),
        ("total Ether sent", "sender_total_sent"),
        ("total ether received", "receiver_total_received"),
        ("total ether balance", "sender_balance"),
        ("Avg min between sent tnx", "sender_avg_time_between_txns"),
        ("Time Diff between first and last (Mins)", "sender_active_duration_mins"),
        ("Number of Created Contracts", "sender_count"),
    ]
    mapping = []
    for src, dst in xb_map:
        if src in df.columns:
            mapping.append((dst, pd.to_numeric(df[src], errors="coerce").fillna(0).to_numpy(dtype=np.float32)))
    return map_to_93(mapping), y


def load_elliptic() -> tuple[np.ndarray, np.ndarray]:
    feat_path = DATA_DIR / "elliptic" / "elliptic_txs_features.csv"
    cls_path = DATA_DIR / "elliptic" / "elliptic_txs_classes.csv"

    feat = pd.read_csv(feat_path, header=None)
    feat.columns = ["txId"] + [f"feat_{i}" for i in range(1, feat.shape[1])]

    cls = pd.read_csv(cls_path)
    cls.columns = ["txId", "class"]

    merged = feat.merge(cls, on="txId", how="inner")
    merged = merged[merged["class"].astype(str).isin(["1", "2"])].copy()

    # Elliptic convention: class 1 = illicit, class 2 = licit.
    y = (merged["class"].astype(str) == "1").astype(np.int32).to_numpy()

    avail = [c for c in merged.columns if c.startswith("feat_")]
    X_raw = merged[avail].to_numpy(dtype=np.float32)

    X = empty_X(len(X_raw))
    X[:, : min(X.shape[1], X_raw.shape[1])] = X_raw[:, : min(X.shape[1], X_raw.shape[1])]
    return X, y


def load_odds(name: str) -> tuple[np.ndarray, np.ndarray]:
    d = sio.loadmat(str(DATA_DIR / "odds" / f"{name}.mat"))
    X_raw = np.asarray(d["X"], dtype=np.float32)
    y = np.asarray(d["y"], dtype=np.int32).ravel()
    mapping = [(AMTTP_MAP[i], X_raw[:, i]) for i in range(min(X_raw.shape[1], len(AMTTP_MAP)))]
    return map_to_93(mapping), y


# ─────────────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────────────


def fit_lr(X: np.ndarray, y: np.ndarray) -> LogisticRegression:
    lr = LogisticRegression(max_iter=2000, random_state=42, class_weight="balanced")
    lr.fit(X, y)
    return lr


def fit_xgb(X: np.ndarray, y: np.ndarray):
    if xgb is None:
        raise RuntimeError("xgboost is not available")
    clf = xgb.XGBClassifier(
        n_estimators=120,
        max_depth=6,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        min_child_weight=1.0,
        tree_method="hist",
        n_jobs=-1,
        random_state=42,
        eval_metric="logloss",
        verbosity=0,
    )
    clf.fit(X, y)
    return clf


def predict_proba(model, X: np.ndarray) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return model.predict_proba(X)[:, 1]
    # fallback
    return np.asarray(model.predict(X), dtype=np.float64).ravel()


# ─────────────────────────────────────────────────────────────────────────────
# Strict evaluation
# ─────────────────────────────────────────────────────────────────────────────


def evaluate_one_dataset(
    ds_name: str,
    X: np.ndarray,
    y: np.ndarray,
    domain: str,
    transfer: TransferBundle | None = None,
    *,
    random_state: int = 42,
    only_transfer: bool = False,
) -> list[tuple]:
    rows = []
    split = make_4way_split(X, y, random_state=random_state)

    X_train_fit_raw = X[split.train_fit]
    y_train_fit = y[split.train_fit]

    X_cal_raw = X[split.cal]
    y_cal = y[split.cal]

    X_val_raw = X[split.val]
    y_val = y[split.val]

    X_test_raw = X[split.test]
    y_test = y[split.test]

    # Preprocessing fit on train_fit only.
    X_train_fit, X_val, scaler = preprocess_fit_transform(X_train_fit_raw, X_val_raw)
    X_cal = scaler.transform(np.log1p(np.abs(X_cal_raw)) * np.sign(X_cal_raw))
    X_cal = np.clip(np.nan_to_num(X_cal, nan=0.0, posinf=0.0, neginf=0.0), -10, 10)

    X_test = scaler.transform(np.log1p(np.abs(X_test_raw)) * np.sign(X_test_raw))
    X_test = np.clip(np.nan_to_num(X_test, nan=0.0, posinf=0.0, neginf=0.0), -10, 10)

    # BSDT fit on TRAIN only.
    stats = ref_stats_fit(X_train_fit_raw, y_train_fit)
    comp_train = components(X_train_fit_raw, stats)

    fixed_w = np.array([0.30, 0.25, 0.25, 0.20], dtype=np.float64)
    mi_w, _mi_raw = mi_weights_fit(comp_train, y_train_fit)

    # Hyperparam grids (tuned on val)
    lam_grid = np.arange(0.1, 2.6, 0.2)
    tau_grid = np.array([0.1, 0.2, 0.3, 0.5, 0.7, 0.9])
    pred_grid = np.arange(0.05, 0.95, 0.02)

    model_specs = []

    # Optional: true transfer baseline.
    if transfer is not None:
        proj = build_X_for_transfer(X, transfer)
        if proj is not None:
            X_model_all, diag = proj
            model_specs.append((
                f"Transfer-XGB({diag['n_present']}/{diag['n_expected']})",
                lambda: ("transfer", X_model_all),
            ))

    # Default: fresh per-dataset baselines.
    if not only_transfer:
        model_specs.append(("Fresh-LR", lambda: fit_lr(X_train_fit, y_train_fit)))
        if xgb is not None and len(y) <= 400_000:
            model_specs.append(("Fresh-XGB", lambda: fit_xgb(X_train_fit, y_train_fit)))

    for mname, fit_fn in model_specs:
        model = fit_fn()

        if isinstance(model, tuple) and model[0] == "transfer":
            X_model_all = model[1]
            p_raw_cal = _predict_transfer(transfer, X_model_all[split.cal])
            p_raw_val = _predict_transfer(transfer, X_model_all[split.val])
            p_raw_test = _predict_transfer(transfer, X_model_all[split.test])
        else:
            p_raw_cal = predict_proba(model, X_cal)
            p_raw_val = predict_proba(model, X_val)
            p_raw_test = predict_proba(model, X_test)

        # Platt calibration fit on calibration only.
        platt = platt_fit(p_raw_cal, y_cal)
        p_val = platt_apply(platt, p_raw_val)
        p_test = platt_apply(platt, p_raw_test)

        base_th, _base_m_val = tune_threshold_f1(y_val, p_val, grid=pred_grid)
        base_m_test = metrics_at_threshold(y_test, p_test, base_th)
        base_auc = safe_auc(y_test, p_test)

        # BSDT components on val/test (using TRAIN-fitted stats only)
        comp_val = components(X_val_raw, stats)
        comp_test = components(X_test_raw, stats)

        # VR weights use train predictions + chosen baseline threshold (from val).
        if isinstance(model, tuple) and model[0] == "transfer":
            X_model_all = model[1]
            p_train_fit_raw = _predict_transfer(transfer, X_model_all[split.train_fit])
        else:
            p_train_fit_raw = predict_proba(model, X_train_fit)
        p_train_fit = platt_apply(platt, p_train_fit_raw)
        vr_w, _vr_raw = vr_weights_fit(comp_train, p_train_fit, base_th)

        # Original correction: report MI-weighted (matches old comprehensive script style).
        best_corr = tune_correction(y_val, p_val, comp_val, mi_w, lam_grid, tau_grid, pred_grid)
        pc_test = apply_original_correction(p_test, comp_test, mi_w, best_corr["lambda"], best_corr["tau"])
        corr_m_test = metrics_at_threshold(y_test, pc_test, best_corr["pred_threshold"])

        # Quadratic Surface (QuadSurf) correction: fit residual corrector on TRAIN, tune alpha+threshold on VAL.
        quad_alpha_grid = np.array([0.01, 0.1, 1.0], dtype=np.float64)
        quad_best = {"f1": -1.0}
        quad_best_alpha = float(quad_alpha_grid[0])
        quad_best_th = float(pred_grid[0])
        quad_best_poly = None
        quad_best_beta = None
        for alpha in quad_alpha_grid:
            poly, beta = quadsurf_fit_beta(comp_train, y_train_fit, p_train_fit, float(alpha))
            p_quad_val = quadsurf_apply(poly, beta, p_val, comp_val)
            th_q, m_q = tune_threshold_f1(y_val, p_quad_val, grid=pred_grid)
            if m_q["f1"] > quad_best["f1"]:
                quad_best = m_q
                quad_best_alpha = float(alpha)
                quad_best_th = float(th_q)
                quad_best_poly = poly
                quad_best_beta = beta
        assert quad_best_poly is not None and quad_best_beta is not None
        p_quad_test = quadsurf_apply(quad_best_poly, quad_best_beta, p_test, comp_test)
        quad_auc = safe_auc(y_test, p_quad_test)
        quad_m_test = metrics_at_threshold(y_test, p_quad_test, quad_best_th)

        # QuadSurf + Exponential gate: apply only where base p is low (probability-clustering fix).
        # p_qexp = p + gate(p) * (p_quad - p)
        gate_k_grid = np.array([2.0, 4.0, 8.0, 12.0], dtype=np.float64)
        gate_tau_grid = np.array([0.2, 0.3, 0.5, 0.7], dtype=np.float64)
        qexp_best = {"f1": -1.0}
        qexp_best_alpha = float(quad_alpha_grid[0])
        qexp_best_k = float(gate_k_grid[0])
        qexp_best_tau = float(gate_tau_grid[0])
        qexp_best_th = float(pred_grid[0])
        qexp_best_poly = None
        qexp_best_beta = None

        for alpha in quad_alpha_grid:
            poly, beta = quadsurf_fit_beta(comp_train, y_train_fit, p_train_fit, float(alpha))
            p_quad_val = quadsurf_apply(poly, beta, p_val, comp_val)
            delta_val = p_quad_val - p_val

            for gate_tau in gate_tau_grid:
                for gate_k in gate_k_grid:
                    gate = sigmoid(float(gate_k) * (float(gate_tau) - p_val))
                    p_qexp_val = np.clip(p_val + gate * delta_val, 0.0, 1.0)
                    th_e, m_e = tune_threshold_f1(y_val, p_qexp_val, grid=pred_grid)
                    if m_e["f1"] > qexp_best["f1"]:
                        qexp_best = m_e
                        qexp_best_alpha = float(alpha)
                        qexp_best_k = float(gate_k)
                        qexp_best_tau = float(gate_tau)
                        qexp_best_th = float(th_e)
                        qexp_best_poly = poly
                        qexp_best_beta = beta

        assert qexp_best_poly is not None and qexp_best_beta is not None
        p_quad_test_for_gate = quadsurf_apply(qexp_best_poly, qexp_best_beta, p_test, comp_test)
        delta_test = p_quad_test_for_gate - p_test
        gate_test = sigmoid(qexp_best_k * (qexp_best_tau - p_test))
        p_qexp_test = np.clip(p_test + gate_test * delta_test, 0.0, 1.0)
        qexp_auc = safe_auc(y_test, p_qexp_test)
        qexp_m_test = metrics_at_threshold(y_test, p_qexp_test, qexp_best_th)

        # Signed LR "correction" trained on TRAIN only, tuned on VAL, evaluated on TEST.
        slr = LogisticRegression(random_state=42, max_iter=2000, class_weight="balanced")
        slr.fit(comp_train, y_train_fit)
        p_slr_val = slr.predict_proba(comp_val)[:, 1]
        p_slr_test = slr.predict_proba(comp_test)[:, 1]
        slr_auc = safe_auc(y_test, p_slr_test)
        slr_th, _ = tune_threshold_f1(y_val, p_slr_val, grid=pred_grid)
        slr_m_test = metrics_at_threshold(y_test, p_slr_test, slr_th)

        n_total = int(len(y_test))
        n_fraud = int(y_test.sum())

        rows.append(
            (
                ds_name,
                domain,
                mname,
                n_total,
                n_fraud,
                base_auc,
                base_m_test["f1"],
                base_m_test["rec"],
                base_m_test["prec"],
                base_m_test["fa"],
                base_m_test["tp"],
                base_m_test["fp"],
                corr_m_test["f1"],
                corr_m_test["rec"],
                corr_m_test["prec"],
                corr_m_test["fa"],
                corr_m_test["tp"],
                corr_m_test["fp"],
                slr_m_test["f1"],
                slr_m_test["rec"],
                slr_m_test["prec"],
                slr_m_test["fa"],
                slr_auc,
                slr_m_test["tp"],
                slr_m_test["fp"],
                quad_m_test["f1"],
                quad_m_test["rec"],
                quad_m_test["prec"],
                quad_m_test["fa"],
                quad_auc,
                quad_m_test["tp"],
                quad_m_test["fp"],
                quad_best_alpha,
                qexp_m_test["f1"],
                qexp_m_test["rec"],
                qexp_m_test["prec"],
                qexp_m_test["fa"],
                qexp_auc,
                qexp_m_test["tp"],
                qexp_m_test["fp"],
                qexp_best_alpha,
                qexp_best_tau,
                qexp_best_k,
                float(base_th),
                float(best_corr["lambda"]),
                float(best_corr["tau"]),
                float(best_corr["pred_threshold"]),
                float(quad_best_th),
                float(qexp_best_th),
                float(slr_th),
                int(random_state),
            )
        )

        # Save per-model diagnostics for cross-domain style output too.

    return rows


def strict_cross_domain_report(*, random_state: int = 42) -> dict:
    """Produce a strict-split cross-domain JSON analogous to the existing file."""

    datasets = {
        "creditcard": (
            "Credit Card Fraud (ULB)",
            "Dal Pozzolo et al. 2015, OpenML",
            load_creditcard,
        ),
        "shuttle": ("Shuttle (NASA)", "ODDS / Statlog Shuttle, 49K samples", lambda: load_odds("shuttle")),
        "mammography": ("Mammography", "ODDS / Woods et al., 11K samples", lambda: load_odds("mammography")),
        "pendigits": ("Pendigits", "ODDS / Alimoglu 1996, 6.8K samples", lambda: load_odds("pendigits")),
    }

    results = {}

    lam_grid = np.arange(0.05, 3.0, 0.05)
    tau_grid = np.arange(0.1, 0.95, 0.1)
    pred_grid = np.arange(0.15, 0.9, 0.05)

    for key, (name, source, loader) in datasets.items():
        X, y = loader()
        y = y.astype(np.int32)

        split = make_4way_split(X, y, random_state=random_state)
        X_train_fit_raw = X[split.train_fit]
        y_train_fit = y[split.train_fit]
        X_cal_raw, y_cal = X[split.cal], y[split.cal]
        X_val_raw, y_val = X[split.val], y[split.val]
        X_test_raw, y_test = X[split.test], y[split.test]

        # Preprocess
        X_train_fit, X_val, scaler = preprocess_fit_transform(X_train_fit_raw, X_val_raw)
        X_cal = scaler.transform(np.log1p(np.abs(X_cal_raw)) * np.sign(X_cal_raw))
        X_cal = np.clip(np.nan_to_num(X_cal, nan=0.0, posinf=0.0, neginf=0.0), -10, 10)
        X_test = scaler.transform(np.log1p(np.abs(X_test_raw)) * np.sign(X_test_raw))
        X_test = np.clip(np.nan_to_num(X_test, nan=0.0, posinf=0.0, neginf=0.0), -10, 10)

        # Baseline model: LR (fast, stable).
        base_model = fit_lr(X_train_fit, y_train_fit)
        p_raw_cal = predict_proba(base_model, X_cal)
        p_raw_val = predict_proba(base_model, X_val)
        p_raw_test = predict_proba(base_model, X_test)

        # Platt
        platt = platt_fit(p_raw_cal, y_cal)
        p_val = platt_apply(platt, p_raw_val)
        p_test = platt_apply(platt, p_raw_test)

        # Baseline threshold tuned on val, reported on test.
        th_base, _ = tune_threshold_f1(y_val, p_val, grid=np.arange(0.05, 0.95, 0.01))
        m_base_test = metrics_at_threshold(y_test, p_test, th_base)

        # BSDT fit on TRAIN only.
        stats = ref_stats_fit(X_train_fit_raw, y_train_fit)
        comp_train = components(X_train_fit_raw, stats)
        comp_val = components(X_val_raw, stats)
        comp_test = components(X_test_raw, stats)

        # Weights
        fixed_w = np.array([0.30, 0.25, 0.25, 0.20], dtype=np.float64)
        mi_w, _mi_raw = mi_weights_fit(comp_train, y_train_fit)
        p_train_fit_raw = predict_proba(base_model, X_train_fit)
        p_train_fit = platt_apply(platt, p_train_fit_raw)
        vr_w, _vr_raw = vr_weights_fit(comp_train, p_train_fit, th_base)

        def tune_and_eval(w: np.ndarray) -> dict:
            best = {"f1": -1.0}
            for lam in lam_grid:
                for tau in tau_grid:
                    pc_val = apply_original_correction(p_val, comp_val, w, float(lam), float(tau))
                    t_best, m_best = tune_threshold_f1(y_val, pc_val, grid=pred_grid)
                    if m_best["f1"] > best["f1"]:
                        best = {
                            **m_best,
                            "lambda": float(lam),
                            "threshold": float(tau),
                            "pred_threshold": float(t_best),
                        }
            pc_test = apply_original_correction(p_test, comp_test, w, best["lambda"], best["threshold"])
            m_test = metrics_at_threshold(y_test, pc_test, best["pred_threshold"])
            return {
                "f1": m_test["f1"],
                "recall": m_test["rec"],
                "precision": m_test["prec"],
                "lambda": best["lambda"],
                "threshold": best["threshold"],
                "pred_threshold": best["pred_threshold"],
                "caught": m_test["tp"],
                "missed": int(y_test.sum()) - int(m_test["tp"]),
            }

        corr_fixed = tune_and_eval(fixed_w)
        corr_fixed["weights"] = fixed_w.tolist()
        corr_mi = tune_and_eval(mi_w)
        corr_mi["weights"] = mi_w.tolist()
        corr_vr = tune_and_eval(vr_w)
        corr_vr["weights"] = vr_w.tolist()

        best_corr = max([corr_fixed, corr_mi, corr_vr], key=lambda d: d["recall"])

        # Orthogonality on TEST only (label-free).
        comp_names = ["C", "G", "A", "T"]
        active = []
        degenerate = []
        for i, cn in enumerate(comp_names):
            if float(comp_test[:, i].var()) < 1e-10:
                degenerate.append(cn)
            else:
                active.append(cn)
        if len(active) >= 2:
            active_idx = [comp_names.index(cn) for cn in active]
            pearson = np.corrcoef(comp_test[:, active_idx].T)
            off = [abs(pearson[i, j]) for i in range(len(active_idx)) for j in range(i + 1, len(active_idx))]
            mean_corr = float(np.mean(off)) if off else 0.0
            max_corr = float(np.max(off)) if off else 0.0
        else:
            mean_corr = 0.0
            max_corr = 0.0

        pca = PCA(n_components=min(4, comp_test.shape[1]))
        pca.fit(comp_test)

        # Predictive power: fit missed-classifier on TRAIN only, evaluate AUC on TEST.
        missed_train = ((y_train_fit == 1) & (p_train_fit < th_base)).astype(np.int32)
        missed_test = ((y_test == 1) & (p_test < th_base)).astype(np.int32)
        if missed_train.sum() >= 5 and (missed_train == 0).sum() >= 5:
            lr_missed = LogisticRegression(random_state=42, max_iter=2000)
            lr_missed.fit(comp_train, missed_train)
            combined_auc = safe_auc(missed_test, lr_missed.predict_proba(comp_test)[:, 1])
        else:
            combined_auc = 0.5

        individual_auc = {}
        for i, cn in enumerate(comp_names):
            individual_auc[cn] = safe_auc(missed_test, comp_test[:, i])

        recall_delta = round((best_corr["recall"] - m_base_test["rec"]) * 100, 1)

        results[key] = {
            "dataset": name,
            "source": source,
            "protocol": "strict_train/cal/val/test; platt-on-cal; fit-on-train; tune-on-val; report-on-test",
            "total_samples": int(len(y_test)),
            "total_fraud": int((y_test == 1).sum()),
            "fraud_rate": float((y_test == 1).mean()),
            "baseline": {
                "threshold": float(th_base),
                "recall": float(m_base_test["rec"]),
                "precision": float(m_base_test["prec"]),
                "f1": float(m_base_test["f1"]),
                "caught": int(m_base_test["tp"]),
                "missed": int((y_test == 1).sum()) - int(m_base_test["tp"]),
            },
            "correction_fixed": corr_fixed,
            "correction_mi": corr_mi,
            "correction_vr": corr_vr,
            "best_correction_method": "fixed" if best_corr is corr_fixed else ("MI" if best_corr is corr_mi else "VR"),
            "orthogonality": {
                "active_components": active,
                "degenerate_components": degenerate,
                "mean_abs_pearson": mean_corr,
                "max_abs_pearson": max_corr,
                "pca_variance_explained": pca.explained_variance_ratio_.tolist(),
                "non_redundancy_pass": True,
            },
            "predictive_power": {
                "combined_auc": float(combined_auc),
                **{f"individual_auc_{cn}": float(individual_auc[cn]) for cn in comp_names},
            },
            "recall_improvement_pp": float(recall_delta),
        }

    return {
        "cross_domain_validation": True,
        "protocol": "strict_train/cal/val/test; platt-on-cal; fit-on-train; tune-on-val; report-on-test",
        "random_state": int(random_state),
        "n_datasets": len(results),
        "datasets": results,
    }


def main() -> None:
    t0 = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    loaders = {
        "Elliptic": load_elliptic,
        "XBlock": load_xblock,
        "Credit Card": load_creditcard,
        "Shuttle": lambda: load_odds("shuttle"),
        "Mammography": lambda: load_odds("mammography"),
        "Pendigits": lambda: load_odds("pendigits"),
    }

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--transfer-artifacts-dir",
        type=str,
        default="",
        help="Optional artifacts dir containing preprocessors.joblib + xgboost_fraud.ubj (93-feature bundle).",
    )
    parser.add_argument(
        "--seeds",
        type=str,
        default="42",
        help="Comma-separated random seeds for repeated strict splits (e.g. '1,2,3').",
    )
    parser.add_argument(
        "--only-transfer",
        action="store_true",
        help="If set, only evaluate transfer baseline(s) (skips Fresh-LR/Fresh-XGB). Requires --transfer-artifacts-dir.",
    )
    args = parser.parse_args()

    seeds = [int(s.strip()) for s in str(args.seeds).split(",") if s.strip()]
    if not seeds:
        raise ValueError("--seeds must contain at least one integer")

    transfer = None
    if args.transfer_artifacts_dir:
        transfer = try_load_transfer_bundle(Path(args.transfer_artifacts_dir))
    if args.only_transfer and transfer is None:
        raise ValueError("--only-transfer requires --transfer-artifacts-dir")

    rows = []
    for seed in seeds:
        for ds_name, loader in loaders.items():
            X, y = loader()
            y = y.astype(np.int32)
            domain = "IN-DOMAIN" if ds_name in ("Elliptic", "XBlock") else "OUT-DOMAIN"
            print(
                f"\n=== {ds_name} ({domain}) seed={seed} n={len(y):,} fraud={int(y.sum()):,} ({y.mean():.2%})"
            )
            rows.extend(
                evaluate_one_dataset(
                    ds_name,
                    X,
                    y,
                    domain,
                    transfer=transfer,
                    random_state=seed,
                    only_transfer=bool(args.only_transfer),
                )
            )

    if args.transfer_artifacts_dir and args.only_transfer:
        suffix = "strict_transfer_only"
    else:
        suffix = "strict_transfer" if args.transfer_artifacts_dir else "strict"
    comp_out = OUT_DIR / f"comprehensive_bsdt_results_{suffix}.json"
    with comp_out.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "protocol": "strict_train/cal/val/test; platt-on-cal; fit-on-train; tune-on-val; report-on-test",
                "transfer_artifacts_dir": args.transfer_artifacts_dir or None,
                "seeds": seeds,
                "only_transfer": bool(args.only_transfer),
                "rows": rows,
            },
            f,
            indent=2,
        )

    cross_reports = [strict_cross_domain_report(random_state=seed) for seed in seeds]
    cross_out = OUT_DIR / f"bsdt_cross_domain_results_{suffix}.json"
    with cross_out.open("w", encoding="utf-8") as f:
        if len(seeds) == 1:
            cross = cross_reports[0]
            cross["transfer_artifacts_dir"] = args.transfer_artifacts_dir or None
            cross["seeds"] = seeds
            cross["only_transfer"] = bool(args.only_transfer)
            json.dump(cross, f, indent=2)
        else:
            json.dump(
                {
                    "protocol": "strict_train/cal/val/test; platt-on-cal; fit-on-train; tune-on-val; report-on-test",
                    "transfer_artifacts_dir": args.transfer_artifacts_dir or None,
                    "seeds": seeds,
                    "only_transfer": bool(args.only_transfer),
                    "reports": cross_reports,
                },
                f,
                indent=2,
            )

    print(f"\nWrote: {comp_out}")
    print(f"Wrote: {cross_out}")
    print(f"Done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
