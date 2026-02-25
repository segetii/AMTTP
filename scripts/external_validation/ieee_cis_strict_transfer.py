"""
IEEE-CIS — Strict Transfer BSDT Evaluation (Frozen Elliptic-Trained XGB).

Protocol matches the paper's strict transfer table:
1. Train XGB on Elliptic (93-feature schema) — this is the frozen transfer model.
2. Apply it frozen to IEEE-CIS (74/93 features mapped, 590K transactions).
3. The base model was never trained on e-commerce data.
4. BSDT correction operators (MFLS, SignedLR, QuadSurf, ExpGate) are fit
   per-dataset on the train-fit split using 4-way protocol.
5. Report test metrics.

This is the same protocol used for Credit Card, Shuttle, Mammography, Pendigits
in the paper — frozen blockchain model applied to a new domain.
"""

from __future__ import annotations
import json, time, warnings, sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import roc_auc_score, mutual_info_score
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.preprocessing import PolynomialFeatures, RobustScaler

try:
    import xgboost as xgb
except ImportError:
    xgb = None

warnings.filterwarnings("ignore")

ROOT = Path(r"c:\amttp")
DATA_DIR = ROOT / "data" / "external_validation"
OUT_DIR = ROOT / "papers"

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

# Semantic mapping
IEEE_CIS_MAP = [
    ("TransactionAmt", "value_eth"),
    ("C1",  "sender_sent_count"),
    ("C2",  "sender_total_sent"),
    ("C4",  "sender_avg_sent"),
    ("C5",  "sender_max_sent"),
    ("C6",  "sender_min_sent"),
    ("C7",  "sender_std_sent"),
    ("C8",  "sender_total_gas_sent"),
    ("C9",  "sender_avg_gas_used"),
    ("C10", "sender_avg_gas_price"),
    ("C11", "sender_unique_receivers"),
    ("C12", "sender_received_count"),
    ("C13", "sender_total_received"),
    ("C14", "sender_avg_received"),
    ("D1",  "sender_active_duration_mins"),
    ("D2",  "sender_avg_value"),
    ("D3",  "sender_in_degree"),
    ("D4",  "sender_out_degree"),
    ("D5",  "sender_degree"),
    ("D10", "sender_degree_centrality"),
    ("D11", "sender_betweenness_proxy"),
    ("D15", "sender_neighbors"),
    ("card1", "gas_price_gwei"),
    ("card2", "gas_used"),
    ("card3", "gas_limit"),
    ("card5", "nonce"),
    ("addr1", "transaction_type"),
    ("addr2", "transaction_index"),
    ("dist1", "sender_balance"),
    ("dist2", "sender_in_out_ratio"),
    ("TransactionDT", "sender_income"),
]

AMTTP_MAP = [
    "sender_total_sent", "sender_avg_sent", "sender_sent_count", "value_eth",
    "sender_total_transactions", "sender_balance", "receiver_total_received",
    "sender_in_out_ratio", "receiver_avg_received", "sender_unique_counterparties",
    "sender_degree", "sender_neighbors", "sender_in_degree", "sender_out_degree",
    "sender_unique_receivers", "receiver_unique_senders", "sender_max_sent",
    "sender_min_sent", "receiver_max_received", "receiver_min_received",
    "receiver_received_count", "sender_avg_time_between_txns",
    "sender_stddev_sent", "receiver_stddev_received", "sender_cluster_coeff",
    "sender_pagerank", "sender_betweenness", "sender_closeness",
]


def empty_X(n):
    return np.zeros((n, len(FEATURES_93)), dtype=np.float32)

def map_to_93(mapping):
    idx = {f: i for i, f in enumerate(FEATURES_93)}
    n = len(mapping[0][1])
    X = empty_X(n)
    for name, vals in mapping:
        if name in idx:
            X[:, idx[name]] = np.asarray(vals, dtype=np.float32)
    return X


def load_elliptic():
    feat_path = DATA_DIR / "elliptic" / "elliptic_txs_features.csv"
    cls_path = DATA_DIR / "elliptic" / "elliptic_txs_classes.csv"
    feat = pd.read_csv(feat_path, header=None)
    feat.columns = ["txId"] + [f"feat_{i}" for i in range(1, feat.shape[1])]
    cls = pd.read_csv(cls_path)
    cls.columns = ["txId", "class"]
    merged = feat.merge(cls, on="txId", how="inner")
    merged = merged[merged["class"].astype(str).isin(["1", "2"])].copy()
    y = (merged["class"].astype(str) == "1").astype(np.int32).to_numpy()
    avail = [c for c in merged.columns if c.startswith("feat_")]
    X_raw = merged[avail].to_numpy(dtype=np.float32)
    X = empty_X(len(X_raw))
    X[:, :min(X.shape[1], X_raw.shape[1])] = X_raw[:, :min(X.shape[1], X_raw.shape[1])]
    return X, y


def load_ieee_cis():
    path = DATA_DIR / "ieee_cis" / "train_transaction.csv"
    needed = ["isFraud", "TransactionAmt", "TransactionDT",
              "card1", "card2", "card3", "card5", "addr1", "addr2",
              "dist1", "dist2"] + \
             [f"C{i}" for i in range(1, 15)] + \
             [f"D{i}" for i in range(1, 16)] + \
             [f"V{i}" for i in range(1, 340)]
    all_cols = pd.read_csv(path, nrows=0).columns.tolist()
    use_cols = [c for c in needed if c in all_cols]
    print(f"  Loading {path.name} ({len(use_cols)} columns)...")
    df = pd.read_csv(path, usecols=use_cols)
    print(f"  Loaded: {len(df):,} rows")

    y = df["isFraud"].astype(np.int32).to_numpy()
    idx = {f: i for i, f in enumerate(FEATURES_93)}
    n = len(df)
    X = np.zeros((n, len(FEATURES_93)), dtype=np.float32)

    for src_col, dst_feat in IEEE_CIS_MAP:
        if src_col in df.columns and dst_feat in idx:
            X[:, idx[dst_feat]] = pd.to_numeric(
                df[src_col], errors="coerce"
            ).fillna(0).to_numpy(dtype=np.float32)

    # Map V columns to remaining receiver features
    v_cols = sorted([c for c in df.columns if c.startswith("V")],
                    key=lambda c: int(c[1:]))
    receiver_feats = [f for f in FEATURES_93 if f.startswith("receiver_") and f not in
                      [dst for _, dst in IEEE_CIS_MAP]]
    for i, rf in enumerate(receiver_feats):
        if i < len(v_cols):
            vals = pd.to_numeric(df[v_cols[i]], errors="coerce").fillna(0).to_numpy(dtype=np.float32)
            X[:, idx[rf]] = vals

    nonzero = int((np.abs(X) > 1e-8).any(axis=0).sum())
    print(f"  Features mapped: {nonzero}/93 non-zero")
    return X, y


# ─────── BSDT Components ───────

def camouflage(X, mu, dmax):
    d = np.linalg.norm(X - mu, axis=1)
    return np.clip(1.0 - d / max(dmax, 1e-12), 0, 1).astype(np.float64)

def feature_gap(X):
    return ((np.abs(X) < 1e-8).sum(axis=1) / max(X.shape[1], 1)).astype(np.float64)

def activity_anomaly(X, mu_c, sig_c):
    IDX = FEATURES_93.index("sender_sent_count")
    tx = np.abs(X[:, IDX]).astype(np.float64)
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
    IDX = FEATURES_93.index("sender_sent_count")
    caught = fraud[:, IDX] if len(fraud) > 0 else np.array([0.0])
    mu_c = float(np.log1p(np.abs(caught)).mean())
    sig_c = float(np.log1p(np.abs(caught)).std()) if len(caught) > 1 else 1.0
    rm = fraud.mean(axis=0) if len(fraud) > 0 else np.zeros(X_train.shape[1])
    rv = fraud.var(axis=0) if len(fraud) > 1 else np.ones(X_train.shape[1])
    return mu_legit, dmax, rm, rv, mu_c, sig_c

def bsdt_components(X, stats):
    mu_legit, dmax, rm, rv, mu_c, sig_c = stats
    C = camouflage(X, mu_legit, dmax)
    G = feature_gap(X)
    A = activity_anomaly(X, mu_c, sig_c)
    T = temporal_novelty(X, rm, rv)
    return np.column_stack([C, G, A, T])


# ─────── Corrections ───────

def mi_weights_fit(comp, y, n_bins=20):
    w = np.zeros(4, dtype=np.float64)
    for i in range(4):
        bins = np.linspace(comp[:, i].min(), comp[:, i].max() + 1e-12, n_bins + 1)
        digitised = np.digitize(comp[:, i], bins)
        w[i] = mutual_info_score(y, digitised)
    s = w.sum()
    return w / s if s > 0 else np.ones(4) / 4

def apply_mfls_correction(p, comp, w, lam, tau):
    mfls = (comp * w).sum(axis=1)
    corr = lam * mfls * (1.0 - p)
    mask = p < tau
    result = p.copy()
    result[mask] = np.clip(p[mask] + corr[mask], 0, 1)
    return result

def quadsurf_fit_beta(comp, y, p, alpha=1.0):
    poly = PolynomialFeatures(degree=2, include_bias=False)
    Z = poly.fit_transform(comp)
    residual = y.astype(np.float64) - p
    from sklearn.linear_model import Ridge
    ridge = Ridge(alpha=alpha)
    ridge.fit(Z, residual)
    return poly, ridge.coef_

def quadsurf_apply(poly, beta, p_base, comp):
    Z = poly.transform(comp)
    return np.clip(p_base + Z @ beta, 0, 1)

def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -60, 60)))

def metrics_at_threshold(y, p, t):
    pred = (p >= t).astype(np.int32)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    prec = float(tp / max(tp + fp, 1))
    rec = float(tp / max(tp + fn, 1))
    f1 = float(2 * prec * rec / max(prec + rec, 1e-12))
    fa = float(fp / max(tp + fp, 1))
    return {"f1": f1, "rec": rec, "prec": prec, "tp": tp, "fp": fp, "fa": fa}

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
    try: return float(roc_auc_score(y, p))
    except: return 0.5

def platt_fit(p_cal, y_cal):
    # Use log-odds for numerical stability with extreme probability clustering
    p_clipped = np.clip(p_cal, 1e-7, 1 - 1e-7)
    logits = np.log(p_clipped / (1 - p_clipped))
    lr = LogisticRegression(max_iter=2000, random_state=42)
    lr.fit(logits.reshape(-1, 1), y_cal)
    return lr

def platt_apply(lr, p):
    p_clipped = np.clip(p, 1e-7, 1 - 1e-7)
    logits = np.log(p_clipped / (1 - p_clipped))
    return lr.predict_proba(logits.reshape(-1, 1))[:, 1]

def preprocess(X, scaler=None):
    Xt = np.log1p(np.abs(X)) * np.sign(X)
    Xt = np.nan_to_num(Xt, nan=0.0, posinf=0.0, neginf=0.0)
    if scaler is None:
        scaler = RobustScaler()
        scaler.fit(Xt)
    Xt = np.clip(scaler.transform(Xt), -10, 10)
    return Xt, scaler

def fit_xgb(X, y):
    clf = xgb.XGBClassifier(
        n_estimators=120, max_depth=6, learning_rate=0.08,
        subsample=0.9, colsample_bytree=0.9, reg_lambda=1.0,
        min_child_weight=1.0, tree_method="hist", n_jobs=-1,
        random_state=42, eval_metric="logloss", verbosity=0,
    )
    clf.fit(X, y)
    return clf


# ─────── 4-way split ───────

def make_4way_split(X, y, rs=42):
    from dataclasses import dataclass
    @dataclass(frozen=True)
    class S:
        train_fit: np.ndarray
        cal: np.ndarray
        val: np.ndarray
        test: np.ndarray

    sss = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=rs)
    dev, test = next(sss.split(X, y))
    sss2 = StratifiedShuffleSplit(n_splits=1, test_size=0.25, random_state=rs)
    tc, val_r = next(sss2.split(X[dev], y[dev]))
    sss3 = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=rs)
    tr, cr = next(sss3.split(X[dev[tc]], y[dev[tc]]))
    return S(train_fit=dev[tc[tr]], cal=dev[tc[cr]], val=dev[val_r], test=test)


def run_strict_transfer(seed=42):
    """
    1. Train XGB on ALL of Elliptic (93 features) — this is the frozen transfer model.
    2. Apply frozen to IEEE-CIS 4-way split.
    3. Corrections fit on IEEE-CIS train-fit, tuned on val, reported on test.
    """
    print(f"\n{'='*60}")
    print(f"Step 1: Train frozen Transfer-XGB on Elliptic (seed={seed})")
    print(f"{'='*60}")

    X_ell, y_ell = load_elliptic()
    print(f"  Elliptic: {len(y_ell):,} samples, {y_ell.sum():,} fraud ({y_ell.mean():.2%})")

    # Preprocess Elliptic & train XGB
    X_ell_pp, ell_scaler = preprocess(X_ell)
    transfer_xgb = fit_xgb(X_ell_pp, y_ell)
    print(f"  Transfer-XGB trained. Features: {X_ell_pp.shape[1]}")

    print(f"\n{'='*60}")
    print(f"Step 2: Apply frozen Transfer-XGB to IEEE-CIS (seed={seed})")
    print(f"{'='*60}")

    X_ieee, y_ieee = load_ieee_cis()
    print(f"  IEEE-CIS: {len(y_ieee):,} samples, {y_ieee.sum():,} fraud ({y_ieee.mean():.2%})")

    # 4-way split on IEEE-CIS
    sp = make_4way_split(X_ieee, y_ieee, rs=seed)
    X_tf_raw = X_ieee[sp.train_fit]
    y_tf = y_ieee[sp.train_fit]
    X_cal_raw, y_cal = X_ieee[sp.cal], y_ieee[sp.cal]
    X_val_raw, y_val = X_ieee[sp.val], y_ieee[sp.val]
    X_test_raw, y_test = X_ieee[sp.test], y_ieee[sp.test]

    print(f"  Split: train={len(y_tf):,} cal={len(y_cal):,} val={len(y_val):,} test={len(y_test):,}")
    print(f"  Test fraud: {y_test.sum():,}/{len(y_test):,} ({y_test.mean():.2%})")

    # Preprocess IEEE-CIS using ELLIPTIC scaler (true transfer)
    X_tf_pp, _ = preprocess(X_tf_raw, scaler=ell_scaler)
    X_cal_pp, _ = preprocess(X_cal_raw, scaler=ell_scaler)
    X_val_pp, _ = preprocess(X_val_raw, scaler=ell_scaler)
    X_test_pp, _ = preprocess(X_test_raw, scaler=ell_scaler)

    # Frozen transfer: predict IEEE-CIS with Elliptic-trained model
    p_raw_cal = transfer_xgb.predict_proba(X_cal_pp)[:, 1]
    p_raw_val = transfer_xgb.predict_proba(X_val_pp)[:, 1]
    p_raw_test = transfer_xgb.predict_proba(X_test_pp)[:, 1]
    p_raw_tf = transfer_xgb.predict_proba(X_tf_pp)[:, 1]

    print(f"  Raw proba range: [{p_raw_test.min():.6f}, {p_raw_test.max():.6f}]")
    print(f"  Raw proba mean:  {p_raw_test.mean():.6f}")

    # Platt calibration on cal split
    platt = platt_fit(p_raw_cal, y_cal)
    p_tf = platt_apply(platt, p_raw_tf)
    p_val = platt_apply(platt, p_raw_val)
    p_test = platt_apply(platt, p_raw_test)

    print(f"  Calibrated range: [{p_test.min():.4f}, {p_test.max():.4f}]")

    # Base threshold
    pred_grid = np.arange(0.05, 0.95, 0.02)
    base_th, _ = tune_threshold_f1(y_val, p_val, grid=pred_grid)
    base_m = metrics_at_threshold(y_test, p_test, base_th)
    base_auc = safe_auc(y_test, p_test)
    print(f"\n  Base (Transfer-XGB): F1={base_m['f1']:.3f} Prec={base_m['prec']:.3f} "
          f"Rec={base_m['rec']:.3f} AUC={base_auc:.3f} FDR={base_m['fa']:.1%}")

    # ─── BSDT components (fit on IEEE-CIS train_fit only) ───
    stats = ref_stats_fit(X_tf_raw, y_tf)
    comp_tf = bsdt_components(X_tf_raw, stats)
    comp_val = bsdt_components(X_val_raw, stats)
    comp_test = bsdt_components(X_test_raw, stats)

    mi_w = mi_weights_fit(comp_tf, y_tf)
    print(f"  MI weights: C={mi_w[0]:.3f} G={mi_w[1]:.3f} A={mi_w[2]:.3f} T={mi_w[3]:.3f}")

    # ─── MFLS correction ───
    lam_grid = np.arange(0.1, 2.6, 0.2)
    tau_grid = np.array([0.1, 0.2, 0.3, 0.5, 0.7, 0.9])
    best_corr = {"f1": -1.0}
    for lam in lam_grid:
        for tau in tau_grid:
            pc = apply_mfls_correction(p_val, comp_val, mi_w, float(lam), float(tau))
            th, m = tune_threshold_f1(y_val, pc, grid=pred_grid)
            if m["f1"] > best_corr["f1"]:
                best_corr = {**m, "lam": float(lam), "tau": float(tau), "th": float(th)}
    pc_test = apply_mfls_correction(p_test, comp_test, mi_w, best_corr["lam"], best_corr["tau"])
    mfls_m = metrics_at_threshold(y_test, pc_test, best_corr["th"])
    print(f"  +MFLS:   F1={mfls_m['f1']:.3f} FDR={mfls_m['fa']:.1%}")

    # ─── SignedLR ───
    slr = LogisticRegression(random_state=42, max_iter=2000, class_weight="balanced")
    slr.fit(comp_tf, y_tf)
    p_slr_val = slr.predict_proba(comp_val)[:, 1]
    p_slr_test = slr.predict_proba(comp_test)[:, 1]
    slr_auc = safe_auc(y_test, p_slr_test)
    slr_th, _ = tune_threshold_f1(y_val, p_slr_val, grid=pred_grid)
    slr_m = metrics_at_threshold(y_test, p_slr_test, slr_th)
    print(f"  +SLR:    F1={slr_m['f1']:.3f} FDR={slr_m['fa']:.1%} AUC={slr_auc:.3f}")

    # ─── QuadSurf ───
    alpha_grid = np.array([0.01, 0.1, 1.0])
    qs_best = {"f1": -1.0}
    qs_poly = qs_beta = None
    qs_th = 0.5
    for alpha in alpha_grid:
        poly, beta = quadsurf_fit_beta(comp_tf, y_tf, p_tf, float(alpha))
        pq = quadsurf_apply(poly, beta, p_val, comp_val)
        th, m = tune_threshold_f1(y_val, pq, grid=pred_grid)
        if m["f1"] > qs_best["f1"]:
            qs_best, qs_th, qs_poly, qs_beta = m, float(th), poly, beta
    p_qs_test = quadsurf_apply(qs_poly, qs_beta, p_test, comp_test)
    qs_auc = safe_auc(y_test, p_qs_test)
    qs_m = metrics_at_threshold(y_test, p_qs_test, qs_th)
    print(f"  +QS:     F1={qs_m['f1']:.3f} FDR={qs_m['fa']:.1%} AUC={qs_auc:.3f}")

    # ─── ExpGate ───
    gk_grid = np.array([2.0, 4.0, 8.0, 12.0])
    gt_grid = np.array([0.2, 0.3, 0.5, 0.7])
    eg_best = {"f1": -1.0}
    eg_poly = eg_beta = None
    eg_k = eg_tau = eg_th = 0.5
    for alpha in alpha_grid:
        poly, beta = quadsurf_fit_beta(comp_tf, y_tf, p_tf, float(alpha))
        pq = quadsurf_apply(poly, beta, p_val, comp_val)
        delta = pq - p_val
        for gtau in gt_grid:
            for gk in gk_grid:
                gate = sigmoid(float(gk) * (float(gtau) - p_val))
                pe = np.clip(p_val + gate * delta, 0, 1)
                th, m = tune_threshold_f1(y_val, pe, grid=pred_grid)
                if m["f1"] > eg_best["f1"]:
                    eg_best, eg_k, eg_tau, eg_th = m, float(gk), float(gtau), float(th)
                    eg_poly, eg_beta = poly, beta
    pq_test = quadsurf_apply(eg_poly, eg_beta, p_test, comp_test)
    d_test = pq_test - p_test
    g_test = sigmoid(eg_k * (eg_tau - p_test))
    p_eg_test = np.clip(p_test + g_test * d_test, 0, 1)
    eg_auc = safe_auc(y_test, p_eg_test)
    eg_m = metrics_at_threshold(y_test, p_eg_test, eg_th)
    print(f"  +EG:     F1={eg_m['f1']:.3f} FDR={eg_m['fa']:.1%} AUC={eg_auc:.3f}")

    # ─── MFLS AUC ───
    missed_train = ((y_tf == 1) & (p_tf < base_th)).astype(np.int32)
    missed_test = ((y_test == 1) & (p_test < base_th)).astype(np.int32)
    if missed_train.sum() >= 5:
        lr_m = LogisticRegression(random_state=42, max_iter=2000)
        lr_m.fit(comp_tf, missed_train)
        mfls_auc = safe_auc(missed_test, lr_m.predict_proba(comp_test)[:, 1])
    else:
        mfls_auc = 0.5
    print(f"  MFLS AUC: {mfls_auc:.3f}")

    return {
        "seed": seed,
        "n_total": int(len(y_ieee)),
        "n_test": int(len(y_test)),
        "n_fraud_test": int(y_test.sum()),
        "features_mapped": int((np.abs(X_ieee) > 1e-8).any(axis=0).sum()),
        "base_f1": base_m["f1"], "base_fdr": base_m["fa"], "base_auc": base_auc,
        "mfls_f1": mfls_m["f1"], "mfls_fdr": mfls_m["fa"],
        "slr_f1": slr_m["f1"], "slr_fdr": slr_m["fa"], "slr_auc": slr_auc,
        "qs_f1": qs_m["f1"], "qs_fdr": qs_m["fa"], "qs_auc": qs_auc,
        "eg_f1": eg_m["f1"], "eg_fdr": eg_m["fa"], "eg_auc": eg_auc,
        "mfls_auc": mfls_auc,
    }


def main():
    t0 = time.time()
    seeds = [42, 123]
    all_res = []
    for s in seeds:
        all_res.append(run_strict_transfer(seed=s))

    # Average
    avg = {}
    for k in all_res[0]:
        if isinstance(all_res[0][k], (int, float)):
            vals = [r[k] for r in all_res]
            avg[k + "_mean"] = float(np.mean(vals))
            avg[k + "_std"] = float(np.std(vals))

    out = OUT_DIR / "ieee_cis_strict_transfer_results.json"
    with open(out, "w") as f:
        json.dump({
            "dataset": "IEEE-CIS Fraud Detection",
            "source": "Vesta Corp / Kaggle",
            "protocol": "Frozen Elliptic-trained XGB applied to IEEE-CIS; BSDT fit per-dataset",
            "seeds": seeds,
            "per_seed": all_res,
            "average": avg,
        }, f, indent=2)

    print(f"\n{'='*60}")
    print("SUMMARY (mean over seeds):")
    print(f"  Base F1:  {avg['base_f1_mean']:.3f} ± {avg['base_f1_std']:.3f}")
    print(f"  +MFLS:   {avg['mfls_f1_mean']:.3f} ± {avg['mfls_f1_std']:.3f}")
    print(f"  +SLR:    {avg['slr_f1_mean']:.3f} ± {avg['slr_f1_std']:.3f}")
    print(f"  +QS:     {avg['qs_f1_mean']:.3f} ± {avg['qs_f1_std']:.3f}")
    print(f"  +EG:     {avg['eg_f1_mean']:.3f} ± {avg['eg_f1_std']:.3f}")
    print(f"  EG FDR:  {avg['eg_fdr_mean']:.3f} ± {avg['eg_fdr_std']:.3f}")
    print(f"  MFLS AUC:{avg['mfls_auc_mean']:.3f} ± {avg['mfls_auc_std']:.3f}")
    print(f"  SLR AUC: {avg['slr_auc_mean']:.3f} ± {avg['slr_auc_std']:.3f}")
    print(f"\nSaved: {out}")
    print(f"Done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
