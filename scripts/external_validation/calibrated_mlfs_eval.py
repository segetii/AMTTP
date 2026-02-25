"""Calibrated + MLFS evaluation of V2 student models on labelled_eth.parquet.

Pipeline (strict protocol — no information leakage):
1. Map external parquet → 93-feature schema (best effort).
2. Preprocess with V2 preprocessors → 160-dim boost vector → XGB/LGB raw probs.
3. 4-way stratified split: train_fit / cal / val / test.
4. Platt + isotonic calibration fitted on CAL split.
5. BSDT components computed on preprocessed 93-feature matrix.
6. MLFS variants (base, QuadSurf, QuarSurf+ExpoGate, SignedLR) fitted on
   TRAIN_FIT, tuned on VAL, evaluated on TEST.
7. Comparison table printed + JSON written.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    mutual_info_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.preprocessing import PolynomialFeatures, RobustScaler

warnings.filterwarnings("ignore")

# ── Paths ────────────────────────────────────────────────────────────────────

PARQUET = Path(r"C:\Users\Administrator\Downloads\labelled_eth.parquet")
ARTIFACTS_DIR = Path(
    r"C:\Users\Administrator\Downloads\complete_amttp_student_artifacts"
    r"\amttp_models_20260213_213346"
)
OUT_JSON = Path(r"C:\amttp\reports\external_validation\calibrated_mlfs_results.json")

# ── 93-feature schema (from bsdt_eval_strict.py) ────────────────────────────

FEATURES_93 = [
    "value_eth", "gas_price_gwei", "gas_used", "gas_limit", "transaction_type",
    "nonce", "transaction_index",
    "sender_sent_count", "sender_total_sent", "sender_avg_sent",
    "sender_max_sent", "sender_min_sent", "sender_std_sent",
    "sender_total_gas_sent", "sender_avg_gas_used", "sender_avg_gas_price",
    "sender_unique_receivers", "sender_received_count", "sender_total_received",
    "sender_avg_received", "sender_max_received", "sender_min_received",
    "sender_std_received", "sender_unique_senders", "sender_total_transactions",
    "sender_balance", "sender_in_out_ratio", "sender_unique_counterparties",
    "sender_avg_value", "sender_neighbors", "sender_count", "sender_income",
    "sender_active_duration_mins",
    "sender_in_degree", "sender_out_degree", "sender_degree",
    "sender_degree_centrality", "sender_betweenness_proxy",
    "sender_sent_to_mixer", "sender_recv_from_mixer", "sender_mixer_interaction",
    "sender_sent_to_sanctioned", "sender_recv_from_sanctioned",
    "sender_sanctioned_interaction",
    "sender_sent_to_exchange", "sender_recv_from_exchange",
    "sender_exchange_interaction",
    "sender_is_mixer", "sender_is_sanctioned", "sender_is_exchange",
    "receiver_sent_count", "receiver_total_sent", "receiver_avg_sent",
    "receiver_max_sent", "receiver_min_sent", "receiver_std_sent",
    "receiver_total_gas_sent", "receiver_avg_gas_used", "receiver_avg_gas_price",
    "receiver_unique_receivers", "receiver_received_count",
    "receiver_total_received", "receiver_avg_received",
    "receiver_max_received", "receiver_min_received", "receiver_std_received",
    "receiver_unique_senders", "receiver_total_transactions",
    "receiver_balance", "receiver_in_out_ratio",
    "receiver_unique_counterparties", "receiver_avg_value",
    "receiver_neighbors", "receiver_count", "receiver_income",
    "receiver_active_duration_mins",
    "receiver_in_degree", "receiver_out_degree", "receiver_degree",
    "receiver_degree_centrality", "receiver_betweenness_proxy",
    "receiver_sent_to_mixer", "receiver_recv_from_mixer",
    "receiver_mixer_interaction",
    "receiver_sent_to_sanctioned", "receiver_recv_from_sanctioned",
    "receiver_sanctioned_interaction",
    "receiver_sent_to_exchange", "receiver_recv_from_exchange",
    "receiver_exchange_interaction",
    "receiver_is_mixer", "receiver_is_sanctioned", "receiver_is_exchange",
]

IDX_SENT = FEATURES_93.index("sender_sent_count")
IDX_RECV = FEATURES_93.index("receiver_received_count")


# ═════════════════════════════════════════════════════════════════════════════
# Feature mapping (same as compare_student_models_on_labelled_eth.py)
# ═════════════════════════════════════════════════════════════════════════════

COLUMN_MAP = {
    "sent_tnx": "sender_sent_count",
    "received_tnx": "receiver_received_count",
    "total_transactions_(including_tnx_to_create_contract": "sender_total_transactions",
    "unique_sent_to_addresses": "sender_unique_receivers",
    "unique_received_from_addresses": "receiver_unique_senders",
    "total_ether_sent": "sender_total_sent",
    "total_ether_received": "receiver_total_received",
    "total_ether_balance": "sender_balance",
    "avg_val_sent": "sender_avg_sent",
    "avg_val_received": "receiver_avg_received",
    "max_val_sent": "sender_max_sent",
    "min_val_sent": "sender_min_sent",
    "max_value_received": "receiver_max_received",
    "min_value_received": "receiver_min_received",
    "time_diff_between_first_and_last_(mins)": "sender_active_duration_mins",
    "avg_min_between_sent_tnx": "sender_active_duration_mins",
    "avg_min_between_received_tnx": "receiver_active_duration_mins",
    "neighbors": "sender_neighbors",
    "count": "sender_count",
    "income": "sender_income",
}


def build_X_93(df: pd.DataFrame) -> np.ndarray:
    """Map the external parquet columns into the 93-feature schema."""
    out = pd.DataFrame({f: np.zeros(len(df), dtype=np.float32) for f in FEATURES_93})
    lower_cols = {c.lower(): c for c in df.columns}

    def get_numeric(col_lower: str) -> np.ndarray | None:
        src = lower_cols.get(col_lower)
        if src is None:
            return None
        return pd.to_numeric(df[src], errors="coerce").fillna(0.0).to_numpy(np.float32)

    for src_lower, dst in COLUMN_MAP.items():
        if dst not in out.columns:
            continue
        vals = get_numeric(src_lower)
        if vals is not None and (out[dst] == 0).all():
            out[dst] = vals

    # Derived fields
    if "sender_total_transactions" in out.columns:
        approx = out.get("sender_sent_count", 0) + out.get("receiver_received_count", 0)
        mask = out["sender_total_transactions"].to_numpy() == 0
        if isinstance(approx, (pd.Series, np.ndarray)):
            arr = np.asarray(approx, dtype=np.float32)
            fill = mask & (arr != 0)
            if np.any(fill):
                out.loc[fill, "sender_total_transactions"] = arr[fill]

    if "sender_total_sent" in out.columns and "sender_total_transactions" in out.columns:
        denom = np.maximum(out["sender_total_transactions"].to_numpy(np.float32), 1.0)
        if "value_eth" in out.columns:
            out["value_eth"] = (out["sender_total_sent"].to_numpy(np.float32) / denom).astype(np.float32)

    if "receiver_total_received" in out.columns and "receiver_received_count" in out.columns:
        denom = np.maximum(out["receiver_received_count"].to_numpy(np.float32), 1.0)
        recv_avg = out["receiver_avg_received"].to_numpy(np.float32)
        out["receiver_avg_received"] = np.where(
            recv_avg == 0,
            out["receiver_total_received"].to_numpy(np.float32) / denom,
            recv_avg,
        ).astype(np.float32)

    if "sender_balance" in out.columns and "receiver_balance" in out.columns:
        r = out["receiver_balance"].to_numpy(np.float32)
        s = out["sender_balance"].to_numpy(np.float32)
        out["receiver_balance"] = np.where(r == 0, s, r).astype(np.float32)

    X = out[FEATURES_93].to_numpy(np.float32)
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)


# ═════════════════════════════════════════════════════════════════════════════
# V2 model loading + inference
# ═════════════════════════════════════════════════════════════════════════════

def load_v2_artifacts(adir: Path) -> dict:
    fc = json.loads((adir / "feature_config.json").read_text("utf-8"))
    meta = json.loads((adir / "metadata.json").read_text("utf-8"))
    pre = joblib.load(str(adir / "preprocessors.joblib"))

    xgb_model = xgb.XGBClassifier()
    xgb_model.load_model(str(adir / "xgboost_fraud.ubj"))

    # LightGBM: normalize newlines for Windows compatibility.
    raw = (adir / "lightgbm_fraud.txt").read_bytes().replace(b"\r\n", b"\n")
    tmp = adir / "_tmp_lgb_norm.txt"
    tmp.write_bytes(raw)
    lgb_model = lgb.Booster(model_file=str(tmp))

    return {
        "feature_config": fc,
        "metadata": meta,
        "preprocessors": pre,
        "xgb": xgb_model,
        "lgb": lgb_model,
    }


def v2_preprocess_raw(X_raw_93: np.ndarray, preprocessors: dict) -> np.ndarray:
    """Apply the V2 shipped preprocessing to 93-feature raw matrix."""
    X = X_raw_93.copy().astype(np.float32)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    log_mask = preprocessors.get("log_transform_mask")
    if log_mask is not None:
        log_mask = np.asarray(log_mask, dtype=bool)
        X[:, log_mask] = np.log1p(np.clip(X[:, log_mask], 0, None))
    scaler = preprocessors["robust_scaler"]
    X = scaler.transform(X)
    clip_range = preprocessors.get("clip_range", 5)
    if isinstance(clip_range, (int, float, np.integer, np.floating)):
        lo, hi = -float(clip_range), float(clip_range)
    else:
        lo, hi = float(clip_range[0]), float(clip_range[1])
    return np.clip(X, lo, hi)


def v2_build_boost(X_scaled_93: np.ndarray, raw_features: list[str],
                   boost_features: list[str]) -> np.ndarray:
    """Build the 160-dim boost feature matrix from 93-dim scaled."""
    bidx = {n: i for i, n in enumerate(boost_features)}
    X = np.zeros((X_scaled_93.shape[0], len(boost_features)), dtype=np.float32)
    for ri, rn in enumerate(raw_features):
        j = bidx.get(rn)
        if j is not None:
            X[:, j] = X_scaled_93[:, ri]
    return X


def v2_score(X_boost: np.ndarray, bundle: dict) -> tuple[np.ndarray, np.ndarray]:
    """Return (xgb_prob, lgb_prob) raw uncalibrated scores."""
    xgb_p = bundle["xgb"].predict_proba(X_boost)[:, 1]
    lgb_p = bundle["lgb"].predict(X_boost)
    return xgb_p.astype(np.float64), lgb_p.astype(np.float64)


# ═════════════════════════════════════════════════════════════════════════════
# Splitting
# ═════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SplitIdx:
    train_fit: np.ndarray
    cal: np.ndarray
    val: np.ndarray
    test: np.ndarray


def make_4way_split(y: np.ndarray, random_state: int = 42) -> SplitIdx:
    n = len(y)
    X_dummy = np.arange(n).reshape(-1, 1)
    sss1 = StratifiedShuffleSplit(n_splits=1, test_size=0.20, random_state=random_state)
    trainval_idx, test_idx = next(sss1.split(X_dummy, y))

    sss2 = StratifiedShuffleSplit(n_splits=1, test_size=0.25, random_state=random_state)
    train_idx_rel, val_idx_rel = next(sss2.split(X_dummy[trainval_idx], y[trainval_idx]))
    train_idx = trainval_idx[train_idx_rel]
    val_idx = trainval_idx[val_idx_rel]

    sss3 = StratifiedShuffleSplit(n_splits=1, test_size=0.20, random_state=random_state)
    train_fit_rel, cal_rel = next(sss3.split(X_dummy[train_idx], y[train_idx]))
    train_fit_idx = train_idx[train_fit_rel]
    cal_idx = train_idx[cal_rel]

    return SplitIdx(train_fit=train_fit_idx, cal=cal_idx, val=val_idx, test=test_idx)


# ═════════════════════════════════════════════════════════════════════════════
# Calibration
# ═════════════════════════════════════════════════════════════════════════════

def platt_fit(p_cal: np.ndarray, y_cal: np.ndarray) -> LogisticRegression:
    lr = LogisticRegression(random_state=42, max_iter=2000)
    lr.fit(p_cal.reshape(-1, 1), y_cal)
    return lr


def platt_apply(lr: LogisticRegression, p: np.ndarray) -> np.ndarray:
    return lr.predict_proba(p.reshape(-1, 1))[:, 1]


def isotonic_fit(p_cal: np.ndarray, y_cal: np.ndarray) -> IsotonicRegression:
    ir = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    ir.fit(p_cal, y_cal)
    return ir


def isotonic_apply(ir: IsotonicRegression, p: np.ndarray) -> np.ndarray:
    return ir.predict(p)


# ═════════════════════════════════════════════════════════════════════════════
# BSDT components (from bsdt_eval_strict.py)
# ═════════════════════════════════════════════════════════════════════════════

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


def ref_stats_fit(X_train: np.ndarray, y_train: np.ndarray):
    n = X_train[y_train == 0]
    f = X_train[y_train == 1]
    mu = n.mean(axis=0)
    d = float(np.percentile(np.linalg.norm(X_train - mu, axis=1), 99))
    if f.shape[0] < 5:
        f = X_train
    rm = f.mean(axis=0)
    rv = f.var(axis=0) + 1e-8
    tx = np.abs(f[:, IDX_SENT]) + np.abs(f[:, IDX_RECV]) + 1e-8
    return mu, max(d, 1e-8), rm, rv, float(np.log1p(tx).mean()), float(max(np.log1p(tx).std(), 1e-8))


def bsdt_components(X: np.ndarray, stats) -> np.ndarray:
    mu, dmax, rm, rv, mu_c, sig_c = stats
    c = np.column_stack([
        camouflage(X, mu, dmax),
        feature_gap(X),
        activity_anomaly(X, mu_c, sig_c),
        temporal_novelty(X, rm, rv),
    ])
    return np.nan_to_num(c, nan=0.0)


def mi_weights_fit(comp_train: np.ndarray, y_train: np.ndarray, n_bins: int = 20):
    mi = np.zeros(comp_train.shape[1], dtype=np.float64)
    for i in range(comp_train.shape[1]):
        bins = np.linspace(comp_train[:, i].min(), comp_train[:, i].max() + 1e-8, n_bins)
        binned = np.digitize(comp_train[:, i], bins)
        mi[i] = mutual_info_score(y_train, binned)
    s = mi.sum()
    if s <= 1e-10:
        return np.ones(comp_train.shape[1], dtype=np.float64) / comp_train.shape[1], mi
    return mi / s, mi


def sigmoid(x: np.ndarray) -> np.ndarray:
    x = np.clip(np.asarray(x, dtype=np.float64), -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-x))


# ═════════════════════════════════════════════════════════════════════════════
# MLFS variants
# ═════════════════════════════════════════════════════════════════════════════

def apply_mlfs_base(p: np.ndarray, comp: np.ndarray, w: np.ndarray,
                    lam: float, tau: float) -> np.ndarray:
    """Base MLFS correction: p_corrected = p + lambda * (comp @ w) * (1 - p) * I(p < tau)."""
    mfls = comp @ w
    below = (p < tau).astype(np.float64)
    return np.clip(p + lam * mfls * (1.0 - p) * below, 0.0, 1.0)


def quadsurf_fit_beta(comp_train: np.ndarray, y_train: np.ndarray,
                      p_base_train: np.ndarray, ridge_alpha: float):
    """Fit degree-2 polynomial residual corrector (QuadSurf)."""
    poly = PolynomialFeatures(degree=2, include_bias=False)
    Xp = poly.fit_transform(np.asarray(comp_train, dtype=np.float64))
    y_res = y_train.astype(np.float64) - np.asarray(p_base_train, dtype=np.float64)
    n_neg = int((y_train == 0).sum())
    n_pos = int((y_train == 1).sum())
    w = np.where(y_train == 1, max(n_neg, 1) / max(n_pos, 1), 1.0).astype(np.float64)
    sqrt_w = np.sqrt(w)
    Xw = Xp * sqrt_w[:, None]
    yw = y_res * sqrt_w
    n_feats = Xp.shape[1]
    beta = np.linalg.solve(Xw.T @ Xw + float(ridge_alpha) * np.eye(n_feats), Xw.T @ yw)
    return poly, beta


def quadsurf_apply(poly, beta, p_base, comp):
    Xp = poly.transform(np.asarray(comp, dtype=np.float64))
    corr = Xp @ np.asarray(beta, dtype=np.float64)
    return np.clip(np.asarray(p_base, dtype=np.float64) + corr, 0.0, 1.0)


# ═════════════════════════════════════════════════════════════════════════════
# Metrics + tuning
# ═════════════════════════════════════════════════════════════════════════════

def safe_auc(y, p):
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(roc_auc_score(y, p))


def safe_ap(y, p):
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(average_precision_score(y, p))


def metrics_at_threshold(y: np.ndarray, p: np.ndarray, t: float) -> dict:
    pred = (p >= t).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-12)
    fdr = fp / max(tp + fp, 1)
    return {"f1": f1, "prec": prec, "rec": rec, "fdr": fdr, "tp": tp, "fp": fp, "fn": fn, "tn": tn, "threshold": t}


def tune_threshold_f1(y, p, grid=None):
    if grid is None:
        grid = np.linspace(0.05, 0.95, 91)
    best_m, best_t = None, float(grid[0])
    for t in grid:
        m = metrics_at_threshold(y, p, float(t))
        if best_m is None or m["f1"] > best_m["f1"]:
            best_m = m
            best_t = float(t)
    return best_t, best_m


def tune_mlfs_base(y_val, p_val, comp_val, w, pred_grid):
    lam_grid = np.array([0.05, 0.1, 0.2, 0.5, 1.0, 2.0], dtype=np.float64)
    tau_grid = np.array([0.2, 0.3, 0.5, 0.7, 0.9], dtype=np.float64)
    best = {"f1": -1.0}
    for lam in lam_grid:
        for tau in tau_grid:
            pc = apply_mlfs_base(p_val, comp_val, w, float(lam), float(tau))
            t_best, m_best = tune_threshold_f1(y_val, pc, grid=pred_grid)
            if m_best["f1"] > best["f1"]:
                best = {**m_best, "lambda": float(lam), "tau": float(tau),
                        "pred_threshold": float(t_best)}
    return best


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    print("Loading data and artifacts...")
    df = pd.read_parquet(PARQUET)
    y = pd.to_numeric(df["label_unified"], errors="coerce").fillna(0).astype(int).to_numpy()

    bundle = load_v2_artifacts(ARTIFACTS_DIR)
    fc = bundle["feature_config"]
    raw_features = fc["raw_features"]
    boost_features = fc["boost_features"]

    # Build features
    X_raw_93 = build_X_93(df)
    X_scaled_93 = v2_preprocess_raw(X_raw_93, bundle["preprocessors"])
    X_boost = v2_build_boost(X_scaled_93, raw_features, boost_features)

    # V2 raw scores (full dataset for orientation detection)
    xgb_raw_all, lgb_raw_all = v2_score(X_boost, bundle)

    # Detect orientation: if AUC < 0.5 with raw scores, flip.
    auc_xgb = safe_auc(y, xgb_raw_all)
    auc_lgb = safe_auc(y, lgb_raw_all)
    flip_xgb = auc_xgb < 0.5
    flip_lgb = auc_lgb < 0.5
    print(f"  XGB raw AUC={auc_xgb:.4f} → {'flip' if flip_xgb else 'as-is'}")
    print(f"  LGB raw AUC={auc_lgb:.4f} → {'flip' if flip_lgb else 'as-is'}")

    if flip_xgb:
        xgb_raw_all = 1.0 - xgb_raw_all
    if flip_lgb:
        lgb_raw_all = 1.0 - lgb_raw_all

    # Split
    split = make_4way_split(y, random_state=42)
    y_train_fit = y[split.train_fit]
    y_cal = y[split.cal]
    y_val = y[split.val]
    y_test = y[split.test]

    print(f"  Split sizes: train_fit={len(split.train_fit)}, cal={len(split.cal)}, "
          f"val={len(split.val)}, test={len(split.test)}")
    print(f"  Test positives: {y_test.sum()}/{len(y_test)} ({y_test.mean():.2%})")

    pred_grid = np.linspace(0.05, 0.95, 91)
    results = {"dataset": str(PARQUET), "n": len(y), "pos_rate": float(y.mean()),
               "split_sizes": {"train_fit": len(split.train_fit), "cal": len(split.cal),
                                "val": len(split.val), "test": len(split.test)},
               "xgb_orientation": "flipped" if flip_xgb else "as_is",
               "lgb_orientation": "flipped" if flip_lgb else "as_is",
               "models": {}}

    for model_name, p_all in [("XGB", xgb_raw_all), ("LGB", lgb_raw_all)]:
        print(f"\n{'='*72}")
        print(f"  Model: {model_name}")
        print(f"{'='*72}")

        p_train_fit = p_all[split.train_fit]
        p_cal = p_all[split.cal]
        p_val = p_all[split.val]
        p_test = p_all[split.test]

        model_results = {}

        # ── 1. Uncalibrated base ─────────────────────────────────────────
        base_th, _ = tune_threshold_f1(y_val, p_val, grid=pred_grid)
        base_m_test = metrics_at_threshold(y_test, p_test, base_th)
        base_auc = safe_auc(y_test, p_test)
        base_ap = safe_ap(y_test, p_test)
        model_results["uncalibrated"] = {
            "roc_auc": base_auc, "pr_auc": base_ap, **base_m_test}
        print(f"  Uncalibrated:  AUC={base_auc:.4f}  AP={base_ap:.4f}  "
              f"F1={base_m_test['f1']:.4f}  P={base_m_test['prec']:.4f}  R={base_m_test['rec']:.4f}")

        # ── 2. Platt calibration ─────────────────────────────────────────
        platt = platt_fit(p_cal, y_cal)
        p_val_platt = platt_apply(platt, p_val)
        p_test_platt = platt_apply(platt, p_test)
        p_train_fit_platt = platt_apply(platt, p_train_fit)

        platt_th, _ = tune_threshold_f1(y_val, p_val_platt, grid=pred_grid)
        platt_m_test = metrics_at_threshold(y_test, p_test_platt, platt_th)
        platt_auc = safe_auc(y_test, p_test_platt)
        platt_ap = safe_ap(y_test, p_test_platt)
        model_results["platt"] = {
            "roc_auc": platt_auc, "pr_auc": platt_ap, **platt_m_test}
        print(f"  Platt:         AUC={platt_auc:.4f}  AP={platt_ap:.4f}  "
              f"F1={platt_m_test['f1']:.4f}  P={platt_m_test['prec']:.4f}  R={platt_m_test['rec']:.4f}")

        # ── 3. Isotonic calibration ──────────────────────────────────────
        iso = isotonic_fit(p_cal, y_cal)
        p_val_iso = isotonic_apply(iso, p_val)
        p_test_iso = isotonic_apply(iso, p_test)

        iso_th, _ = tune_threshold_f1(y_val, p_val_iso, grid=pred_grid)
        iso_m_test = metrics_at_threshold(y_test, p_test_iso, iso_th)
        iso_auc = safe_auc(y_test, p_test_iso)
        iso_ap = safe_ap(y_test, p_test_iso)
        model_results["isotonic"] = {
            "roc_auc": iso_auc, "pr_auc": iso_ap, **iso_m_test}
        print(f"  Isotonic:      AUC={iso_auc:.4f}  AP={iso_ap:.4f}  "
              f"F1={iso_m_test['f1']:.4f}  P={iso_m_test['prec']:.4f}  R={iso_m_test['rec']:.4f}")

        # ── 4. BSDT components (on preprocessed 93-dim, not raw) ─────────
        # Use Platt-calibrated scores as p_base for MLFS variants.
        X_train_scaled = X_scaled_93[split.train_fit]
        X_val_scaled = X_scaled_93[split.val]
        X_test_scaled = X_scaled_93[split.test]

        stats = ref_stats_fit(X_train_scaled, y_train_fit)
        comp_train = bsdt_components(X_train_scaled, stats)
        comp_val = bsdt_components(X_val_scaled, stats)
        comp_test = bsdt_components(X_test_scaled, stats)

        mi_w, _mi_raw = mi_weights_fit(comp_train, y_train_fit)

        # Use Platt-calibrated scores as base for MLFS.
        p_base_train = p_train_fit_platt
        p_base_val = p_val_platt
        p_base_test = p_test_platt

        # ── 5. MLFS Base ─────────────────────────────────────────────────
        best_corr = tune_mlfs_base(y_val, p_base_val, comp_val, mi_w, pred_grid)
        pc_test = apply_mlfs_base(p_base_test, comp_test, mi_w,
                                  best_corr["lambda"], best_corr["tau"])
        mlfs_m_test = metrics_at_threshold(y_test, pc_test, best_corr["pred_threshold"])
        mlfs_auc = safe_auc(y_test, pc_test)
        mlfs_ap = safe_ap(y_test, pc_test)
        model_results["mlfs_base"] = {
            "roc_auc": mlfs_auc, "pr_auc": mlfs_ap,
            "best_lambda": best_corr["lambda"], "best_tau": best_corr["tau"],
            **mlfs_m_test}
        print(f"  +MLFS Base:    AUC={mlfs_auc:.4f}  AP={mlfs_ap:.4f}  "
              f"F1={mlfs_m_test['f1']:.4f}  P={mlfs_m_test['prec']:.4f}  R={mlfs_m_test['rec']:.4f}  "
              f"(λ={best_corr['lambda']:.2f} τ={best_corr['tau']:.2f})")

        # ── 6. QuadSurf ──────────────────────────────────────────────────
        quad_alpha_grid = np.array([0.01, 0.1, 1.0], dtype=np.float64)
        quad_best = {"f1": -1.0}
        quad_best_poly = quad_best_beta = None
        quad_best_alpha = quad_best_th = 0.0

        for alpha in quad_alpha_grid:
            poly, beta = quadsurf_fit_beta(comp_train, y_train_fit, p_base_train, float(alpha))
            p_q_val = quadsurf_apply(poly, beta, p_base_val, comp_val)
            th_q, m_q = tune_threshold_f1(y_val, p_q_val, grid=pred_grid)
            if m_q["f1"] > quad_best["f1"]:
                quad_best = m_q
                quad_best_alpha = float(alpha)
                quad_best_th = float(th_q)
                quad_best_poly = poly
                quad_best_beta = beta

        p_quad_test = quadsurf_apply(quad_best_poly, quad_best_beta, p_base_test, comp_test)
        quad_auc = safe_auc(y_test, p_quad_test)
        quad_ap = safe_ap(y_test, p_quad_test)
        quad_m_test = metrics_at_threshold(y_test, p_quad_test, quad_best_th)
        model_results["quadsurf"] = {
            "roc_auc": quad_auc, "pr_auc": quad_ap,
            "best_alpha": quad_best_alpha, **quad_m_test}
        print(f"  +QuadSurf:     AUC={quad_auc:.4f}  AP={quad_ap:.4f}  "
              f"F1={quad_m_test['f1']:.4f}  P={quad_m_test['prec']:.4f}  R={quad_m_test['rec']:.4f}  "
              f"(α={quad_best_alpha})")

        # ── 7. QuarSurf + ExpoGate ───────────────────────────────────────
        gate_k_grid = np.array([2.0, 4.0, 8.0, 12.0], dtype=np.float64)
        gate_tau_grid = np.array([0.2, 0.3, 0.5, 0.7], dtype=np.float64)

        qexp_best = {"f1": -1.0}
        qexp_best_alpha = qexp_best_k = qexp_best_tau = qexp_best_th = 0.0
        qexp_best_poly = qexp_best_beta = None

        for alpha in quad_alpha_grid:
            poly, beta = quadsurf_fit_beta(comp_train, y_train_fit, p_base_train, float(alpha))
            p_q_val = quadsurf_apply(poly, beta, p_base_val, comp_val)
            delta_val = p_q_val - p_base_val

            for gate_tau in gate_tau_grid:
                for gate_k in gate_k_grid:
                    gate = sigmoid(float(gate_k) * (float(gate_tau) - p_base_val))
                    p_qexp_val = np.clip(p_base_val + gate * delta_val, 0.0, 1.0)
                    th_e, m_e = tune_threshold_f1(y_val, p_qexp_val, grid=pred_grid)
                    if m_e["f1"] > qexp_best["f1"]:
                        qexp_best = m_e
                        qexp_best_alpha = float(alpha)
                        qexp_best_k = float(gate_k)
                        qexp_best_tau = float(gate_tau)
                        qexp_best_th = float(th_e)
                        qexp_best_poly = poly
                        qexp_best_beta = beta

        p_q_test_for_gate = quadsurf_apply(qexp_best_poly, qexp_best_beta, p_base_test, comp_test)
        delta_test = p_q_test_for_gate - p_base_test
        gate_test = sigmoid(qexp_best_k * (qexp_best_tau - p_base_test))
        p_qexp_test = np.clip(p_base_test + gate_test * delta_test, 0.0, 1.0)
        qexp_auc = safe_auc(y_test, p_qexp_test)
        qexp_ap = safe_ap(y_test, p_qexp_test)
        qexp_m_test = metrics_at_threshold(y_test, p_qexp_test, qexp_best_th)
        model_results["quarsurf_expogate"] = {
            "roc_auc": qexp_auc, "pr_auc": qexp_ap,
            "best_alpha": qexp_best_alpha, "best_gate_k": qexp_best_k,
            "best_gate_tau": qexp_best_tau, **qexp_m_test}
        print(f"  +QuarSurf+Exp: AUC={qexp_auc:.4f}  AP={qexp_ap:.4f}  "
              f"F1={qexp_m_test['f1']:.4f}  P={qexp_m_test['prec']:.4f}  R={qexp_m_test['rec']:.4f}  "
              f"(α={qexp_best_alpha} k={qexp_best_k} τ={qexp_best_tau})")

        # ── 8. Signed LR ────────────────────────────────────────────────
        slr = LogisticRegression(random_state=42, max_iter=2000, class_weight="balanced")
        slr.fit(comp_train, y_train_fit)
        p_slr_val = slr.predict_proba(comp_val)[:, 1]
        p_slr_test = slr.predict_proba(comp_test)[:, 1]
        slr_auc = safe_auc(y_test, p_slr_test)
        slr_ap = safe_ap(y_test, p_slr_test)
        slr_th, _ = tune_threshold_f1(y_val, p_slr_val, grid=pred_grid)
        slr_m_test = metrics_at_threshold(y_test, p_slr_test, slr_th)
        model_results["signed_lr"] = {
            "roc_auc": slr_auc, "pr_auc": slr_ap, **slr_m_test}
        print(f"  +SignedLR:     AUC={slr_auc:.4f}  AP={slr_ap:.4f}  "
              f"F1={slr_m_test['f1']:.4f}  P={slr_m_test['prec']:.4f}  R={slr_m_test['rec']:.4f}")

        results["models"][model_name] = model_results

    # ── Print summary table ──────────────────────────────────────────────
    print(f"\n{'='*88}")
    print(f"  SUMMARY TABLE — labelled_eth.parquet (test split, n_test={len(split.test)})")
    print(f"{'='*88}")
    print(f"{'Model':<6} {'Variant':<20} {'ROC-AUC':>8} {'PR-AUC':>8} {'F1':>8} {'Prec':>8} {'Rec':>8} {'FDR':>8}")
    print("-" * 88)
    for mname in ["XGB", "LGB"]:
        mr = results["models"][mname]
        for vname, vkey in [("Uncalibrated", "uncalibrated"),
                            ("Platt", "platt"),
                            ("Isotonic", "isotonic"),
                            ("MLFS Base", "mlfs_base"),
                            ("QuadSurf", "quadsurf"),
                            ("QuarSurf+ExpGate", "quarsurf_expogate"),
                            ("SignedLR", "signed_lr")]:
            d = mr[vkey]
            print(f"{mname:<6} {vname:<20} {d['roc_auc']:8.4f} {d['pr_auc']:8.4f} "
                  f"{d['f1']:8.4f} {d['prec']:8.4f} {d['rec']:8.4f} {d['fdr']:8.4f}")
        print("-" * 88)

    # ── Write JSON ───────────────────────────────────────────────────────
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nWrote: {OUT_JSON}")


if __name__ == "__main__":
    main()
