"""
IEEE-CIS Fraud Detection — BSDT Strict Transfer Evaluation.

Downloads from: kaggle.com/c/ieee-fraud-detection
Source: Vesta Corporation real-world e-commerce transactions.
Train: 590,540 transactions, 394 features, 3.5% fraud (isFraud=1).

This script:
1. Loads train_transaction.csv (we only use the labelled training set).
2. Maps numeric features to the 93-feature schema via PCA-based projection.
3. Runs the strict 4-way split BSDT evaluation pipeline.
4. Reports: Base F1, +MFLS, +SignedLR, +QuadSurf, +ExpGate.
5. Saves JSON results.

Usage:
    python ieee_cis_eval.py [--seeds 42,123]
"""

from __future__ import annotations
import json, time, warnings, argparse, sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.preprocessing import PolynomialFeatures, RobustScaler

try:
    import xgboost as xgb
except ImportError:
    xgb = None

warnings.filterwarnings("ignore")

ROOT = Path(r"c:\amttp")
DATA_DIR = ROOT / "data" / "external_validation" / "ieee_cis"
OUT_DIR = ROOT / "papers"

# 93-feature schema
FEATURES_93 = [
    "value_eth", "gas_price_gwei", "gas_used", "gas_limit",
    "transaction_type", "nonce", "transaction_index",
    "sender_sent_count", "sender_total_sent", "sender_avg_sent",
    "sender_max_sent", "sender_min_sent", "sender_std_sent",
    "sender_total_gas_sent", "sender_avg_gas_used", "sender_avg_gas_price",
    "sender_unique_receivers", "sender_received_count", "sender_total_received",
    "sender_avg_received", "sender_max_received", "sender_min_received",
    "sender_std_received", "sender_unique_senders", "sender_total_transactions",
    "sender_balance", "sender_in_out_ratio", "sender_unique_counterparties",
    "sender_avg_value", "sender_neighbors", "sender_count", "sender_income",
    "sender_active_duration_mins", "sender_in_degree", "sender_out_degree",
    "sender_degree", "sender_degree_centrality", "sender_betweenness_proxy",
    "sender_sent_to_mixer", "sender_recv_from_mixer", "sender_mixer_interaction",
    "sender_sent_to_sanctioned", "sender_recv_from_sanctioned",
    "sender_sanctioned_interaction", "sender_sent_to_exchange",
    "sender_recv_from_exchange", "sender_exchange_interaction",
    "sender_is_mixer", "sender_is_sanctioned", "sender_is_exchange",
    "receiver_sent_count", "receiver_total_sent", "receiver_avg_sent",
    "receiver_max_sent", "receiver_min_sent", "receiver_std_sent",
    "receiver_total_gas_sent", "receiver_avg_gas_used", "receiver_avg_gas_price",
    "receiver_unique_receivers", "receiver_received_count", "receiver_total_received",
    "receiver_avg_received", "receiver_max_received", "receiver_min_received",
    "receiver_std_received", "receiver_unique_senders", "receiver_total_transactions",
    "receiver_balance", "receiver_in_out_ratio", "receiver_unique_counterparties",
    "receiver_avg_value", "receiver_neighbors", "receiver_count", "receiver_income",
    "receiver_active_duration_mins", "receiver_in_degree", "receiver_out_degree",
    "receiver_degree", "receiver_degree_centrality", "receiver_betweenness_proxy",
    "receiver_sent_to_mixer", "receiver_recv_from_mixer",
    "receiver_mixer_interaction", "receiver_sent_to_sanctioned",
    "receiver_recv_from_sanctioned", "receiver_sanctioned_interaction",
    "receiver_sent_to_exchange", "receiver_recv_from_exchange",
    "receiver_exchange_interaction", "receiver_is_mixer",
    "receiver_is_sanctioned", "receiver_is_exchange",
]

# ─────── Mapping IEEE-CIS → 93-feature schema ───────

# Semantic mapping: IEEE-CIS features → closest AMTTP feature names
IEEE_CIS_MAP = [
    ("TransactionAmt", "value_eth"),            # transaction amount
    ("C1",  "sender_sent_count"),               # count feature
    ("C2",  "sender_total_sent"),               # count feature
    ("C4",  "sender_avg_sent"),                 # count feature
    ("C5",  "sender_max_sent"),                 # count feature
    ("C6",  "sender_min_sent"),                 # count feature
    ("C7",  "sender_std_sent"),                 # count feature
    ("C8",  "sender_total_gas_sent"),           # count feature
    ("C9",  "sender_avg_gas_used"),             # count feature
    ("C10", "sender_avg_gas_price"),            # count feature
    ("C11", "sender_unique_receivers"),         # count feature
    ("C12", "sender_received_count"),           # count feature
    ("C13", "sender_total_received"),           # count feature
    ("C14", "sender_avg_received"),             # count feature
    ("D1",  "sender_active_duration_mins"),     # time delta
    ("D2",  "sender_avg_value"),                # time delta
    ("D3",  "sender_in_degree"),                # time delta
    ("D4",  "sender_out_degree"),               # time delta
    ("D5",  "sender_degree"),                   # time delta
    ("D10", "sender_degree_centrality"),        # time delta
    ("D11", "sender_betweenness_proxy"),        # time delta
    ("D15", "sender_neighbors"),                # time delta
    ("card1", "gas_price_gwei"),                # card identifier → numeric proxy
    ("card2", "gas_used"),                      # card feature
    ("card3", "gas_limit"),                     # card feature
    ("card5", "nonce"),                         # card feature
    ("addr1", "transaction_type"),              # billing address
    ("addr2", "transaction_index"),             # billing country
    ("dist1", "sender_balance"),                # dist feature
    ("dist2", "sender_in_out_ratio"),           # dist feature
    ("TransactionDT", "sender_income"),         # timestamp proxy
]


def load_ieee_cis(max_rows: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Load IEEE-CIS train_transaction.csv, map to 93-feature schema."""
    path = DATA_DIR / "train_transaction.csv"
    # Columns we actually need
    needed = ["isFraud", "TransactionAmt", "TransactionDT",
              "card1", "card2", "card3", "card5", "addr1", "addr2",
              "dist1", "dist2"] + \
             [f"C{i}" for i in range(1, 15)] + \
             [f"D{i}" for i in range(1, 16)] + \
             [f"V{i}" for i in range(1, 340)]
    # Only read columns that exist
    all_cols = pd.read_csv(path, nrows=0).columns.tolist()
    use_cols = [c for c in needed if c in all_cols]

    print(f"  Loading {path.name} ({len(use_cols)} columns)...")
    df = pd.read_csv(path, usecols=use_cols, nrows=max_rows)
    print(f"  Loaded: {len(df):,} rows")

    y = df["isFraud"].astype(np.int32).to_numpy()

    idx = {f: i for i, f in enumerate(FEATURES_93)}
    n = len(df)
    X = np.zeros((n, len(FEATURES_93)), dtype=np.float32)

    # Apply semantic mapping
    for src_col, dst_feat in IEEE_CIS_MAP:
        if src_col in df.columns and dst_feat in idx:
            X[:, idx[dst_feat]] = pd.to_numeric(
                df[src_col], errors="coerce"
            ).fillna(0).to_numpy(dtype=np.float32)

    # Map V columns to remaining receiver features (PCA-style packing)
    v_cols = sorted([c for c in df.columns if c.startswith("V")],
                    key=lambda c: int(c[1:]))
    # Fill remaining zeros in the 93 features with V column values
    receiver_feats = [f for f in FEATURES_93 if f.startswith("receiver_") and f not in
                      [dst for _, dst in IEEE_CIS_MAP]]
    for i, rf in enumerate(receiver_feats):
        if i < len(v_cols):
            vals = pd.to_numeric(df[v_cols[i]], errors="coerce").fillna(0).to_numpy(dtype=np.float32)
            X[:, idx[rf]] = vals

    # Count how many features are non-zero
    nonzero = (np.abs(X) > 1e-8).any(axis=0).sum()
    print(f"  Features mapped: {nonzero}/93 non-zero")

    return X, y


# ─────── BSDT Components ───────

def camouflage(X, mu, dmax):
    d = np.linalg.norm(X - mu, axis=1)
    return np.clip(1.0 - d / max(dmax, 1e-12), 0, 1).astype(np.float64)

def feature_gap(X):
    return ((np.abs(X) < 1e-8).sum(axis=1) / max(X.shape[1], 1)).astype(np.float64)

def activity_anomaly(X, mu_c, sig_c):
    idx_sent = FEATURES_93.index("sender_sent_count")
    tx = np.abs(X[:, idx_sent]).astype(np.float64)
    z = (np.log1p(tx) - mu_c) / max(sig_c, 1e-12)
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60, 60)))

def temporal_novelty(X, rm, rv):
    rv_safe = np.where(rv < 1e-12, 1.0, rv)
    diff2 = ((X.astype(np.float64) - rm) ** 2) / rv_safe
    m_bar = diff2.mean(axis=1)
    return 1.0 / (1.0 + np.exp(-np.clip(0.5 * (m_bar - 2.0), -60, 60)))

def ref_stats_fit(X_train, y_train):
    legit = X_train[y_train == 0].astype(np.float64)
    fraud = X_train[y_train == 1].astype(np.float64)
    mu_legit = legit.mean(axis=0) if len(legit) > 0 else np.zeros(X_train.shape[1])
    dists = np.linalg.norm(legit - mu_legit, axis=1) if len(legit) > 0 else np.array([1.0])
    dmax = float(np.percentile(dists, 99))
    idx_sent = FEATURES_93.index("sender_sent_count")
    caught = fraud[:, idx_sent] if len(fraud) > 0 else np.array([0.0])
    mu_c = float(np.log1p(np.abs(caught)).mean())
    sig_c = float(np.log1p(np.abs(caught)).std()) if len(caught) > 1 else 1.0
    rm = fraud.mean(axis=0) if len(fraud) > 0 else np.zeros(X_train.shape[1])
    rv = fraud.var(axis=0) if len(fraud) > 1 else np.ones(X_train.shape[1])
    return mu_legit, dmax, rm, rv, mu_c, sig_c

def components(X, stats):
    mu_legit, dmax, rm, rv, mu_c, sig_c = stats
    C = camouflage(X, mu_legit, dmax)
    G = feature_gap(X)
    A = activity_anomaly(X, mu_c, sig_c)
    T = temporal_novelty(X, rm, rv)
    return np.column_stack([C, G, A, T])


# ─────── Weights ───────

def mi_weights_fit(comp_train, y_train, n_bins=20):
    from sklearn.metrics import mutual_info_score
    w = np.zeros(4, dtype=np.float64)
    for i in range(4):
        bins = np.linspace(comp_train[:, i].min(), comp_train[:, i].max() + 1e-12, n_bins + 1)
        digitised = np.digitize(comp_train[:, i], bins)
        w[i] = mutual_info_score(y_train, digitised)
    total = w.sum()
    if total > 0:
        w /= total
    else:
        w = np.ones(4) / 4
    return w, w.copy()

def vr_weights_fit(comp_train, p_train, th):
    pred = (p_train >= th).astype(int)
    correct = comp_train[pred == 1]
    missed = comp_train[pred == 0]
    w = np.zeros(4, dtype=np.float64)
    for i in range(4):
        vc = correct[:, i].var() if len(correct) > 1 else 1e-12
        vm = missed[:, i].var() if len(missed) > 1 else 1e-12
        w[i] = vm / max(vc, 1e-12)
    total = w.sum()
    if total > 0:
        w /= total
    else:
        w = np.ones(4) / 4
    return w, w.copy()


# ─────── Correction Operators ───────

def apply_original_correction(p, comp, w, lam, tau):
    mfls = (comp * w).sum(axis=1)
    corr = lam * mfls * (1.0 - p)
    mask = p < tau
    result = p.copy()
    result[mask] = np.clip(p[mask] + corr[mask], 0, 1)
    return result

def quadsurf_fit_beta(comp_train, y_train, p_train, alpha=1.0):
    poly = PolynomialFeatures(degree=2, include_bias=False)
    Z = poly.fit_transform(comp_train)
    residual = y_train.astype(np.float64) - p_train
    ridge = Ridge(alpha=alpha)
    ridge.fit(Z, residual)
    return poly, ridge.coef_

def quadsurf_apply(poly, beta, p_base, comp):
    Z = poly.transform(comp)
    corr = Z @ beta
    return np.clip(p_base + corr, 0, 1)

def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -60, 60)))


# ─────── Metrics ───────

def metrics_at_threshold(y, p, t):
    pred = (p >= t).astype(np.int32)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    prec = float(tp / max(tp + fp, 1))
    rec = float(tp / max(tp + fn, 1))
    f1 = float(2 * prec * rec / max(prec + rec, 1e-12))
    fa = float(fp / max(tp + fp, 1))
    return {"f1": f1, "rec": rec, "prec": prec, "tp": tp, "fp": fp, "fa": fa, "threshold": float(t)}

def tune_threshold_f1(y, p, grid=None):
    if grid is None:
        grid = np.linspace(0.05, 0.95, 91)
    best_m, best_t = None, float(grid[0])
    for t in grid:
        m = metrics_at_threshold(y, p, float(t))
        if best_m is None or m["f1"] > best_m["f1"]:
            best_m, best_t = m, float(t)
    return best_t, best_m

def safe_auc(y, p):
    try:
        return float(roc_auc_score(y, p))
    except:
        return 0.5


# ─────── Splitting ───────

def make_4way_split(X, y, random_state=42):
    from dataclasses import dataclass
    @dataclass(frozen=True)
    class SplitIdx:
        train_fit: np.ndarray
        cal: np.ndarray
        val: np.ndarray
        test: np.ndarray

    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.25, random_state=random_state)
    dev_idx, test_idx = next(sss.split(X, y))
    sss2 = StratifiedShuffleSplit(n_splits=1, test_size=1/3, random_state=random_state)
    train_cal_idx, val_idx = next(sss2.split(X[dev_idx], y[dev_idx]))
    sss3 = StratifiedShuffleSplit(n_splits=1, test_size=0.25, random_state=random_state)
    train_idx, cal_idx = next(sss3.split(X[dev_idx[train_cal_idx]], y[dev_idx[train_cal_idx]]))
    return SplitIdx(
        train_fit=dev_idx[train_cal_idx[train_idx]],
        cal=dev_idx[train_cal_idx[cal_idx]],
        val=dev_idx[val_idx],
        test=test_idx,
    )

def preprocess_fit_transform(X_train, X_other):
    Xt = np.log1p(np.abs(X_train)) * np.sign(X_train)
    Xt = np.nan_to_num(Xt, nan=0.0, posinf=0.0, neginf=0.0)
    scaler = RobustScaler()
    scaler.fit(Xt)
    Xt = np.clip(scaler.transform(Xt), -10, 10)
    Xo = np.log1p(np.abs(X_other)) * np.sign(X_other)
    Xo = np.nan_to_num(Xo, nan=0.0, posinf=0.0, neginf=0.0)
    Xo = np.clip(scaler.transform(Xo), -10, 10)
    return Xt, Xo, scaler

def platt_fit(p_cal, y_cal):
    lr = LogisticRegression(max_iter=2000, random_state=42)
    lr.fit(p_cal.reshape(-1, 1), y_cal)
    return lr

def platt_apply(lr, p):
    return lr.predict_proba(p.reshape(-1, 1))[:, 1]


# ─────── Models ───────

def fit_lr(X, y):
    return LogisticRegression(max_iter=2000, random_state=42, class_weight="balanced").fit(X, y)

def fit_xgb_model(X, y):
    if xgb is None:
        raise RuntimeError("xgboost not available")
    clf = xgb.XGBClassifier(
        n_estimators=120, max_depth=6, learning_rate=0.08,
        subsample=0.9, colsample_bytree=0.9, reg_lambda=1.0,
        min_child_weight=1.0, tree_method="hist", n_jobs=-1,
        random_state=42, eval_metric="logloss", verbosity=0,
    )
    clf.fit(X, y)
    return clf

def predict_proba(model, X):
    if hasattr(model, "predict_proba"):
        return model.predict_proba(X)[:, 1]
    return np.asarray(model.predict(X), dtype=np.float64).ravel()


# ─────── Main evaluation ───────

def evaluate_ieee_cis(X, y, seed=42):
    """Full BSDT strict evaluation — returns dict of results."""
    print(f"  4-way split (seed={seed})...")
    split = make_4way_split(X, y, random_state=seed)

    X_tf_raw = X[split.train_fit]
    y_tf = y[split.train_fit]
    X_cal_raw, y_cal = X[split.cal], y[split.cal]
    X_val_raw, y_val = X[split.val], y[split.val]
    X_test_raw, y_test = X[split.test], y[split.test]

    print(f"  Split sizes: train={len(y_tf):,} cal={len(y_cal):,} val={len(y_val):,} test={len(y_test):,}")
    print(f"  Test fraud: {y_test.sum():,}/{len(y_test):,} ({y_test.mean():.2%})")

    # Preprocess
    X_tf, X_val, scaler = preprocess_fit_transform(X_tf_raw, X_val_raw)
    X_cal_pp = scaler.transform(np.log1p(np.abs(X_cal_raw)) * np.sign(X_cal_raw))
    X_cal_pp = np.clip(np.nan_to_num(X_cal_pp, nan=0.0), -10, 10)
    X_test_pp = scaler.transform(np.log1p(np.abs(X_test_raw)) * np.sign(X_test_raw))
    X_test_pp = np.clip(np.nan_to_num(X_test_pp, nan=0.0), -10, 10)

    # BSDT fit on TRAIN only
    stats = ref_stats_fit(X_tf_raw, y_tf)
    comp_train = components(X_tf_raw, stats)
    comp_val = components(X_val_raw, stats)
    comp_test = components(X_test_raw, stats)

    # Weights
    mi_w, _ = mi_weights_fit(comp_train, y_tf)
    print(f"  MI weights: C={mi_w[0]:.3f} G={mi_w[1]:.3f} A={mi_w[2]:.3f} T={mi_w[3]:.3f}")

    pred_grid = np.arange(0.05, 0.95, 0.02)
    lam_grid = np.arange(0.1, 2.6, 0.2)
    tau_grid = np.array([0.1, 0.2, 0.3, 0.5, 0.7, 0.9])

    results = {}

    for mname, fit_fn in [("Transfer-XGB", lambda: fit_xgb_model(X_tf, y_tf))]:
        print(f"\n  Model: {mname}")
        model = fit_fn()

        p_raw_cal = predict_proba(model, X_cal_pp)
        p_raw_val = predict_proba(model, X_val)
        p_raw_test = predict_proba(model, X_test_pp)

        # Platt calibration
        platt = platt_fit(p_raw_cal, y_cal)
        p_val = platt_apply(platt, p_raw_val)
        p_test = platt_apply(platt, p_raw_test)

        # Base threshold
        base_th, _ = tune_threshold_f1(y_val, p_val, grid=pred_grid)
        base_m = metrics_at_threshold(y_test, p_test, base_th)
        base_auc = safe_auc(y_test, p_test)
        print(f"    Base: F1={base_m['f1']:.3f} Prec={base_m['prec']:.3f} Rec={base_m['rec']:.3f} AUC={base_auc:.3f}")

        # VR weights
        p_tf_raw = predict_proba(model, X_tf)
        p_tf = platt_apply(platt, p_tf_raw)
        vr_w, _ = vr_weights_fit(comp_train, p_tf, base_th)

        # MFLS correction (MI-weighted)
        best_corr = {"f1": -1.0}
        for lam in lam_grid:
            for tau in tau_grid:
                pc = apply_original_correction(p_val, comp_val, mi_w, float(lam), float(tau))
                t_best, m_best = tune_threshold_f1(y_val, pc, grid=pred_grid)
                if m_best["f1"] > best_corr["f1"]:
                    best_corr = {**m_best, "lambda": float(lam), "tau": float(tau), "pred_threshold": float(t_best)}
        pc_test = apply_original_correction(p_test, comp_test, mi_w, best_corr["lambda"], best_corr["tau"])
        mfls_m = metrics_at_threshold(y_test, pc_test, best_corr["pred_threshold"])
        print(f"    +MFLS: F1={mfls_m['f1']:.3f}")

        # SignedLR
        slr = LogisticRegression(random_state=42, max_iter=2000, class_weight="balanced")
        slr.fit(comp_train, y_tf)
        p_slr_val = slr.predict_proba(comp_val)[:, 1]
        p_slr_test = slr.predict_proba(comp_test)[:, 1]
        slr_auc = safe_auc(y_test, p_slr_test)
        slr_th, _ = tune_threshold_f1(y_val, p_slr_val, grid=pred_grid)
        slr_m = metrics_at_threshold(y_test, p_slr_test, slr_th)
        print(f"    +SLR:  F1={slr_m['f1']:.3f} AUC={slr_auc:.3f}")

        # QuadSurf
        quad_alpha_grid = np.array([0.01, 0.1, 1.0])
        quad_best = {"f1": -1.0}
        quad_best_poly = quad_best_beta = None
        quad_best_th = 0.5
        for alpha in quad_alpha_grid:
            poly, beta = quadsurf_fit_beta(comp_train, y_tf, p_tf, float(alpha))
            p_quad_val = quadsurf_apply(poly, beta, p_val, comp_val)
            th_q, m_q = tune_threshold_f1(y_val, p_quad_val, grid=pred_grid)
            if m_q["f1"] > quad_best["f1"]:
                quad_best = m_q
                quad_best_th = float(th_q)
                quad_best_poly, quad_best_beta = poly, beta
        p_quad_test = quadsurf_apply(quad_best_poly, quad_best_beta, p_test, comp_test)
        quad_auc = safe_auc(y_test, p_quad_test)
        quad_m = metrics_at_threshold(y_test, p_quad_test, quad_best_th)
        print(f"    +QS:   F1={quad_m['f1']:.3f} AUC={quad_auc:.3f}")

        # ExpGate
        gate_k_grid = np.array([2.0, 4.0, 8.0, 12.0])
        gate_tau_grid = np.array([0.2, 0.3, 0.5, 0.7])
        eg_best = {"f1": -1.0}
        eg_best_poly = eg_best_beta = None
        eg_best_k = eg_best_tau = eg_best_th = 0.5
        for alpha in quad_alpha_grid:
            poly, beta = quadsurf_fit_beta(comp_train, y_tf, p_tf, float(alpha))
            p_qv = quadsurf_apply(poly, beta, p_val, comp_val)
            delta = p_qv - p_val
            for gtau in gate_tau_grid:
                for gk in gate_k_grid:
                    gate = sigmoid(float(gk) * (float(gtau) - p_val))
                    p_eg = np.clip(p_val + gate * delta, 0, 1)
                    th_e, m_e = tune_threshold_f1(y_val, p_eg, grid=pred_grid)
                    if m_e["f1"] > eg_best["f1"]:
                        eg_best = m_e
                        eg_best_k, eg_best_tau, eg_best_th = float(gk), float(gtau), float(th_e)
                        eg_best_poly, eg_best_beta = poly, beta
        p_qt = quadsurf_apply(eg_best_poly, eg_best_beta, p_test, comp_test)
        delta_test = p_qt - p_test
        gate_test = sigmoid(eg_best_k * (eg_best_tau - p_test))
        p_eg_test = np.clip(p_test + gate_test * delta_test, 0, 1)
        eg_auc = safe_auc(y_test, p_eg_test)
        eg_m = metrics_at_threshold(y_test, p_eg_test, eg_best_th)
        print(f"    +EG:   F1={eg_m['f1']:.3f} AUC={eg_auc:.3f}")

        # MFLS AUC (missed-fraud prediction)
        missed_train = ((y_tf == 1) & (p_tf < base_th)).astype(np.int32)
        if missed_train.sum() >= 5:
            lr_missed = LogisticRegression(random_state=42, max_iter=2000)
            lr_missed.fit(comp_train, missed_train)
            missed_test = ((y_test == 1) & (p_test < base_th)).astype(np.int32)
            mfls_auc = safe_auc(missed_test, lr_missed.predict_proba(comp_test)[:, 1])
        else:
            mfls_auc = 0.5
        print(f"    MFLS AUC: {mfls_auc:.3f}")

        results[mname] = {
            "seed": seed,
            "n_test": int(len(y_test)),
            "n_fraud_test": int(y_test.sum()),
            "base_f1": base_m["f1"],
            "base_prec": base_m["prec"],
            "base_rec": base_m["rec"],
            "base_auc": base_auc,
            "base_fdr": base_m["fa"],
            "mfls_f1": mfls_m["f1"],
            "mfls_fdr": mfls_m["fa"],
            "slr_f1": slr_m["f1"],
            "slr_fdr": slr_m["fa"],
            "slr_auc": slr_auc,
            "quad_f1": quad_m["f1"],
            "quad_fdr": quad_m["fa"],
            "quad_auc": quad_auc,
            "eg_f1": eg_m["f1"],
            "eg_fdr": eg_m["fa"],
            "eg_auc": eg_auc,
            "mfls_auc": mfls_auc,
        }

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=str, default="42,123",
                        help="Comma-separated seeds")
    args = parser.parse_args()
    seeds = [int(s.strip()) for s in args.seeds.split(",")]

    t0 = time.time()
    print("=" * 60)
    print("IEEE-CIS Fraud Detection — BSDT Strict Evaluation")
    print("=" * 60)

    X, y = load_ieee_cis()

    all_results = {}
    for seed in seeds:
        print(f"\n{'='*40} Seed {seed} {'='*40}")
        res = evaluate_ieee_cis(X, y, seed=seed)
        all_results[f"seed_{seed}"] = res

    # Summary across seeds
    keys = list(all_results[f"seed_{seeds[0]}"].keys())
    summary = {}
    for mname in keys:
        for metric in ["base_f1", "mfls_f1", "slr_f1", "quad_f1", "eg_f1",
                        "base_fdr", "slr_fdr", "quad_fdr", "eg_fdr",
                        "slr_auc", "mfls_auc"]:
            vals = [all_results[f"seed_{s}"][mname][metric] for s in seeds]
            summary[f"{mname}_{metric}_mean"] = float(np.mean(vals))
            summary[f"{mname}_{metric}_std"] = float(np.std(vals))

    out_path = OUT_DIR / "ieee_cis_bsdt_results.json"
    with open(out_path, "w") as f:
        json.dump({
            "dataset": "IEEE-CIS Fraud Detection",
            "source": "Vesta Corporation via Kaggle",
            "n_total": int(len(y)),
            "n_fraud": int(y.sum()),
            "fraud_rate": float(y.mean()),
            "features_mapped": int((np.abs(X) > 1e-8).any(axis=0).sum()),
            "seeds": seeds,
            "results": all_results,
            "summary": summary,
        }, f, indent=2)
    print(f"\nResults saved to {out_path}")
    print(f"Done in {time.time() - t0:.1f}s")

    # Print paper-ready table row
    for mname in keys:
        bf = summary[f"{mname}_base_f1_mean"]
        mf = summary[f"{mname}_mfls_f1_mean"]
        sf = summary[f"{mname}_slr_f1_mean"]
        qf = summary[f"{mname}_quad_f1_mean"]
        ef = summary[f"{mname}_eg_f1_mean"]
        ed = summary[f"{mname}_eg_fdr_mean"]
        print(f"\n  Paper row ({mname}):")
        print(f"    Base F1={bf:.3f}, +MFLS={mf:.3f}, +SLR={sf:.3f}, +QS={qf:.3f}, +EG={ef:.3f}, EG FDR={ed:.1%}")


if __name__ == "__main__":
    main()
