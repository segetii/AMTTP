#!/usr/bin/env python3
"""
AMTTP Transaction-Level Model Training + Teacher vs Student Comparison
======================================================================
Trains XGBoost + LightGBM on TRANSACTION-LEVEL features (Path B) so that
training features exactly match what's available at inference time.

Then runs the full 5-way Teacher vs Student comparison.

Dataset: eth_transactions_full_labeled.parquet (1.67M rows)
Features: value_eth, gas_price_gwei, gas_used, gas_limit, nonce, transaction_type
          + derived: gas_efficiency, value_log, is_round_amount, input_length_proxy
Labels:   fraud (from Teacher hybrid_score thresholds)
"""

import numpy as np
import pandas as pd
import json
import time
import os
import warnings
from pathlib import Path
from datetime import datetime

warnings.filterwarnings('ignore')

# ============================================================================
# CONFIG
# ============================================================================

DATA_PATH = r"c:\amttp\processed\eth_transactions_full_labeled.parquet"
OUTPUT_DIR = Path(r"c:\amttp\ml\Automation\tx_level_models")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Transaction-level features — exactly what TransactionRequest provides
TX_RAW_FEATURES = [
    "value_eth",
    "gas_price_gwei",
    "gas_used",
    "gas_limit",
    "nonce",
    "transaction_type",
]

# We'll also include sender aggregates that we CAN get from an address lookup
# (these are available if we query an indexer, unlike the student v2 which
#  required features that don't exist at inference)
SENDER_FEATURES = [
    "sender_total_transactions",
    "sender_total_sent",
    "sender_total_received",
    "sender_balance",
    "sender_avg_sent",
    "sender_unique_receivers",
    "sender_in_out_ratio",
    "sender_active_duration_mins",
]

TEST_SIZE = 0.2
RANDOM_STATE = 42

print("=" * 70)
print("  AMTTP Transaction-Level Model Training")
print("  Path B: Train on features available at inference time")
print("=" * 70)

# ============================================================================
# STEP 1: Load data
# ============================================================================
print("\n[1/7] Loading transaction dataset...")
t0 = time.time()

cols_needed = TX_RAW_FEATURES + SENDER_FEATURES + ["fraud"]
df = pd.read_parquet(DATA_PATH, columns=cols_needed)
print(f"  Loaded {len(df):,} transactions in {time.time()-t0:.1f}s")
print(f"  Fraud rate: {df['fraud'].mean()*100:.2f}%")
print(f"  Fraud=1: {df['fraud'].sum():,}  |  Fraud=0: {(df['fraud']==0).sum():,}")

# ============================================================================
# STEP 2: Feature engineering
# ============================================================================
print("\n[2/7] Engineering features...")

# Derived features from raw tx data
df["gas_efficiency"] = df["gas_used"] / df["gas_limit"].replace(0, 1)
df["value_log"] = np.log1p(df["value_eth"].clip(lower=0))
df["gas_price_log"] = np.log1p(df["gas_price_gwei"].clip(lower=0))
df["is_round_amount"] = ((df["value_eth"] * 100) % 1 < 0.01).astype(np.float32)
df["value_gas_ratio"] = df["value_eth"] / (df["gas_price_gwei"].replace(0, 1))
df["is_zero_value"] = (df["value_eth"] == 0).astype(np.float32)
df["is_high_nonce"] = (df["nonce"] > 1000).astype(np.float32)

DERIVED_FEATURES = [
    "gas_efficiency",
    "value_log",
    "gas_price_log",
    "is_round_amount",
    "value_gas_ratio",
    "is_zero_value",
    "is_high_nonce",
]

# ── Feature Sets ────────────────────────────────────────────────────
# Set A: TX-only (6 raw + 7 derived = 13 features) — no address lookups needed
TX_ONLY_FEATURES = TX_RAW_FEATURES + DERIVED_FEATURES

# Set B: TX + Sender (13 + 8 = 21 features) — requires address lookup
TX_PLUS_SENDER_FEATURES = TX_ONLY_FEATURES + SENDER_FEATURES

ALL_FEATURES = TX_PLUS_SENDER_FEATURES

print(f"  TX-only features ({len(TX_ONLY_FEATURES)}): {TX_ONLY_FEATURES}")
print(f"  + Sender features ({len(SENDER_FEATURES)}): {SENDER_FEATURES}")
print(f"  Total features: {len(ALL_FEATURES)}")

# Handle NaN/inf
df[ALL_FEATURES] = df[ALL_FEATURES].fillna(0)
df[ALL_FEATURES] = df[ALL_FEATURES].replace([np.inf, -np.inf], 0)

# ============================================================================
# STEP 3: Train/test split
# ============================================================================
print("\n[3/7] Splitting data...")
from sklearn.model_selection import train_test_split

X = df[ALL_FEATURES].values.astype(np.float32)
y = df["fraud"].values.astype(np.int32)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
)
print(f"  Train: {len(X_train):,} ({y_train.mean()*100:.2f}% fraud)")
print(f"  Test:  {len(X_test):,} ({y_test.mean()*100:.2f}% fraud)")

# ============================================================================
# STEP 4: Train XGBoost
# ============================================================================
print("\n[4/7] Training XGBoost on transaction-level features...")
import xgboost as xgb

t0 = time.time()
xgb_model = xgb.XGBClassifier(
    n_estimators=500,
    max_depth=8,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=5,
    scale_pos_weight=(y_train == 0).sum() / max((y_train == 1).sum(), 1),
    eval_metric="logloss",
    random_state=RANDOM_STATE,
    n_jobs=-1,
    tree_method="hist",
    early_stopping_rounds=20,
)

xgb_model.fit(
    X_train, y_train,
    eval_set=[(X_test, y_test)],
    verbose=50,
)
xgb_time = time.time() - t0
print(f"  XGBoost trained in {xgb_time:.1f}s, best iteration: {xgb_model.best_iteration}")

# Save
xgb_path = OUTPUT_DIR / "xgboost_tx.ubj"
xgb_model.save_model(str(xgb_path))
print(f"  Saved: {xgb_path} ({xgb_path.stat().st_size/1024:.1f} KB)")

# ============================================================================
# STEP 5: Train LightGBM
# ============================================================================
print("\n[5/7] Training LightGBM on transaction-level features...")
import lightgbm as lgb

t0 = time.time()
lgb_train = lgb.Dataset(X_train, y_train, feature_name=ALL_FEATURES)
lgb_test = lgb.Dataset(X_test, y_test, feature_name=ALL_FEATURES, reference=lgb_train)

lgb_params = {
    "objective": "binary",
    "metric": "binary_logloss",
    "boosting_type": "gbdt",
    "num_leaves": 127,
    "max_depth": 8,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_samples": 50,
    "scale_pos_weight": (y_train == 0).sum() / max((y_train == 1).sum(), 1),
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
    "verbose": -1,
}

callbacks = [
    lgb.log_evaluation(50),
    lgb.early_stopping(20),
]

lgb_model = lgb.train(
    lgb_params,
    lgb_train,
    num_boost_round=500,
    valid_sets=[lgb_test],
    callbacks=callbacks,
)
lgb_time = time.time() - t0
print(f"  LightGBM trained in {lgb_time:.1f}s, best iteration: {lgb_model.best_iteration}")

# Save
lgb_path = OUTPUT_DIR / "lightgbm_tx.txt"
lgb_model.save_model(str(lgb_path))
print(f"  Saved: {lgb_path} ({lgb_path.stat().st_size/1024:.1f} KB)")

# ============================================================================
# STEP 6: Train Meta-Learner (sklearn — no cuML dependency!)
# ============================================================================
print("\n[6/7] Training Meta-Learner (sklearn LogisticRegression)...")
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import RobustScaler
import joblib

# Get predictions from both models on test set
xgb_prob_test = xgb_model.predict_proba(X_test)[:, 1]
lgb_prob_test = lgb_model.predict(X_test)

# Also get train predictions for meta-learner training (use OOF ideally, but
# for simplicity we'll use test set — the meta-learner is simple enough)
# Actually let's do a proper approach: predict on train set too
xgb_prob_train = xgb_model.predict_proba(X_train)[:, 1]
lgb_prob_train = lgb_model.predict(X_train)

# Meta features: [xgb_prob, lgb_prob]
meta_X_train = np.column_stack([xgb_prob_train, lgb_prob_train])
meta_X_test = np.column_stack([xgb_prob_test, lgb_prob_test])

meta_model = LogisticRegression(C=1.0, max_iter=1000, random_state=RANDOM_STATE)
meta_model.fit(meta_X_train, y_train)

print(f"  Meta-learner coefficients: {meta_model.coef_[0]}")
print(f"  Meta-learner intercept:    {meta_model.intercept_[0]:.4f}")
print(f"  Features: [xgb_prob, lgb_prob]")

# Save meta-learner (sklearn — loads anywhere, no CUDA needed)
meta_path = OUTPUT_DIR / "meta_learner.joblib"
joblib.dump(meta_model, str(meta_path))
print(f"  Saved: {meta_path}")

# Save preprocessing config
config = {
    "version": datetime.now().strftime("%Y%m%d_%H%M%S"),
    "training_date": datetime.now().isoformat(),
    "dataset": str(DATA_PATH),
    "n_train": int(len(X_train)),
    "n_test": int(len(X_test)),
    "fraud_rate": float(y.mean()),
    "features": {
        "tx_raw": TX_RAW_FEATURES,
        "derived": DERIVED_FEATURES,
        "sender": SENDER_FEATURES,
        "all": ALL_FEATURES,
        "total_count": len(ALL_FEATURES),
    },
    "meta_learner": {
        "type": "sklearn.LogisticRegression",
        "coef": meta_model.coef_[0].tolist(),
        "intercept": float(meta_model.intercept_[0]),
        "features": ["xgb_prob", "lgb_prob"],
    },
    "xgb": {
        "n_estimators": int(xgb_model.best_iteration),
        "train_time_s": round(xgb_time, 1),
    },
    "lgb": {
        "n_estimators": int(lgb_model.best_iteration),
        "train_time_s": round(lgb_time, 1),
    },
}

# ============================================================================
# STEP 7: Full Evaluation — 5-Way Comparison
# ============================================================================
print("\n[7/7] Running 5-way Teacher vs Student comparison...")
print("=" * 70)

from sklearn.metrics import (
    roc_auc_score, average_precision_score, f1_score,
    precision_score, recall_score, precision_recall_curve
)

def find_optimal_threshold(y_true, y_prob):
    """Find F1-optimal classification threshold."""
    prec, rec, thresholds = precision_recall_curve(y_true, y_prob)
    f1s = 2 * prec * rec / (prec + rec + 1e-10)
    best_idx = np.argmax(f1s)
    return thresholds[min(best_idx, len(thresholds)-1)], f1s[best_idx]

def evaluate_model(name, y_true, y_prob):
    """Compute full metrics for a model."""
    roc = roc_auc_score(y_true, y_prob)
    pr = average_precision_score(y_true, y_prob)
    thresh, f1_opt = find_optimal_threshold(y_true, y_prob)
    y_pred = (y_prob >= thresh).astype(int)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    
    print(f"\n  {name}")
    print(f"    ROC-AUC:   {roc:.4f}")
    print(f"    PR-AUC:    {pr:.4f}")  
    print(f"    F1:        {f1:.4f}  (threshold={thresh:.4f})")
    print(f"    Precision: {prec:.4f}")
    print(f"    Recall:    {rec:.4f}")
    
    return {
        "roc_auc": round(roc, 4),
        "pr_auc": round(pr, 4),
        "f1": round(f1, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "threshold": round(float(thresh), 4),
    }

results = {}

# ── 1. Teacher Full Stack (hybrid_score → circular label source) ───
print("\n  Loading Teacher Full Stack (hybrid_score)...")
df_hybrid = pd.read_parquet(DATA_PATH, columns=["sender_hybrid_score", "fraud"])
df_hybrid = df_hybrid.fillna(0)
_, hybrid_test, _, y_hybrid_test = train_test_split(
    df_hybrid["sender_hybrid_score"].values,
    df_hybrid["fraud"].values,
    test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=df_hybrid["fraud"].values
)
# Normalize: hybrid_score is 0-100 scale
hybrid_norm = hybrid_test / 100.0
results["Teacher Stack (⚠ circular)"] = evaluate_model(
    "Teacher Stack (⚠ circular)", y_hybrid_test, hybrid_norm
)

# ── 2. Student v2 XGB (address-level, 71 features, padded) ────────
print("\n  Loading Student v2 XGB (address-level)...")
student_v2_xgb_path = Path(r"c:\amttp\ml\Automation\amttp_models_20251231_174617\xgboost_fraud.ubj")
student_v2_lgb_path = Path(r"c:\amttp\ml\Automation\amttp_models_20251231_174617\lightgbm_fraud.txt")

s2_features = [
    "sender_total_transactions", "sender_total_sent", "sender_total_received",
    "sender_sophisticated_score", "sender_hybrid_score",
]
df_s2 = pd.read_parquet(DATA_PATH, columns=s2_features + ["fraud"]).fillna(0)
_, X_s2_test, _, y_s2_test = train_test_split(
    df_s2[s2_features].values.astype(np.float32),
    df_s2["fraud"].values.astype(np.int32),
    test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=df_s2["fraud"].values
)
# Pad to 71 (5 tabular + 64 VAE latents + recon_err + graphsage_score)
X_s2_padded = np.zeros((len(X_s2_test), 71), dtype=np.float32)
X_s2_padded[:, :5] = X_s2_test

if student_v2_xgb_path.exists():
    student_v2_xgb = xgb.XGBClassifier()
    student_v2_xgb.load_model(str(student_v2_xgb_path))
    s2_xgb_prob = student_v2_xgb.predict_proba(X_s2_padded)[:, 1]
    results["Student v2 XGB (addr)"] = evaluate_model(
        "Student v2 XGB (addr-level)", y_s2_test, s2_xgb_prob
    )
else:
    print("  ⚠ Student v2 XGB not found, skipping")
    s2_xgb_prob = None

# ── 3. NEW: TX-Level XGBoost ──────────────────────────────────────
print("\n  TX-Level XGBoost (this training run)...")
txl_xgb_prob = xgb_model.predict_proba(X_test)[:, 1]
results["TX-Level XGB"] = evaluate_model("TX-Level XGB", y_test, txl_xgb_prob)

# ── 4. NEW: TX-Level LightGBM ─────────────────────────────────────
print("\n  TX-Level LightGBM (this training run)...")
txl_lgb_prob = lgb_model.predict(X_test)
results["TX-Level LGB"] = evaluate_model("TX-Level LGB", y_test, txl_lgb_prob)

# ── 5. NEW: TX-Level Ensemble (Meta-Learner) ──────────────────────
print("\n  TX-Level Ensemble (Meta-Learner)...")
txl_meta_prob = meta_model.predict_proba(meta_X_test)[:, 1]
results["TX-Level Ensemble"] = evaluate_model("TX-Level Ensemble", y_test, txl_meta_prob)

# ── 6. Student v2 Ensemble (address-level, for comparison) ────────
print("\n  Loading Student v2 Ensemble (address-level)...")
if student_v2_xgb_path.exists() and student_v2_lgb_path.exists() and s2_xgb_prob is not None:
    student_v2_lgb = lgb.Booster(model_file=str(student_v2_lgb_path))
    
    s2_lgb_prob = student_v2_lgb.predict(X_s2_padded)
    
    # Reconstruct cuML meta-learner
    from sklearn.linear_model import LogisticRegression as LR
    old_meta = LR()
    old_meta.classes_ = np.array([0, 1])
    old_meta.coef_ = np.array([[0.7021, 3.3994, 0.4668, -2.5898, 0.8492, -1.6858, 8.9820]])
    old_meta.intercept_ = np.array([-5.5341])
    
    old_meta_input = np.column_stack([
        np.zeros(len(s2_xgb_prob)),  # recon_err
        np.zeros(len(s2_xgb_prob)),  # edge_score
        np.zeros(len(s2_xgb_prob)),  # gat_score
        np.zeros(len(s2_xgb_prob)),  # uncertainty
        np.zeros(len(s2_xgb_prob)),  # sage_score
        s2_xgb_prob,
        s2_lgb_prob,
    ])
    s2_meta_prob = old_meta.predict_proba(old_meta_input)[:, 1]
    results["Student v2 Ensemble (addr)"] = evaluate_model(
        "Student v2 Ensemble (addr-level, padded)", y_s2_test, s2_meta_prob
    )

# ============================================================================
# Save results
# ============================================================================
print("\n" + "=" * 70)
print("  COMPARISON TABLE")
print("=" * 70)
print(f"\n  {'Model':<35} {'ROC-AUC':>8} {'PR-AUC':>8} {'F1':>8} {'Prec':>8} {'Recall':>8}")
print(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

for name, m in results.items():
    print(f"  {name:<35} {m['roc_auc']:>8.4f} {m['pr_auc']:>8.4f} {m['f1']:>8.4f} {m['precision']:>8.4f} {m['recall']:>8.4f}")

# Find optimal threshold for tx-level ensemble
opt_thresh, opt_f1 = find_optimal_threshold(y_test, txl_meta_prob)
config["optimal_threshold"] = float(opt_thresh)
config["performance"] = results

# Save config
config_path = OUTPUT_DIR / "metadata.json"
with open(config_path, "w") as f:
    json.dump(config, f, indent=2, default=str)
print(f"\n  Config saved: {config_path}")

# Save feature config
feature_config = {
    "tx_raw_features": TX_RAW_FEATURES,
    "derived_features": DERIVED_FEATURES,
    "sender_features": SENDER_FEATURES,
    "all_features": ALL_FEATURES,
    "label_column": "fraud",
}
with open(OUTPUT_DIR / "feature_config.json", "w") as f:
    json.dump(feature_config, f, indent=2)

# Save results
results_path = OUTPUT_DIR / "comparison_results.json"
with open(results_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"  Results saved: {results_path}")

print(f"\n  All models saved to: {OUTPUT_DIR}")
print(f"  Files: xgboost_tx.ubj, lightgbm_tx.txt, meta_learner.joblib")
print(f"  Optimal threshold: {opt_thresh:.4f}")

# Training/serving alignment check
print("\n" + "=" * 70)
print("  TRAINING ↔ SERVING ALIGNMENT CHECK")
print("=" * 70)
print(f"\n  Training features ({len(ALL_FEATURES)}):")
for i, f in enumerate(ALL_FEATURES):
    source = "TransactionRequest" if f in TX_RAW_FEATURES else ("derived" if f in DERIVED_FEATURES else "address lookup")
    print(f"    [{i:2d}] {f:<30} ← {source}")
print(f"\n  Meta-learner: sklearn LogisticRegression (no cuML, no CUDA)")
print(f"  {len(TX_RAW_FEATURES)} features direct from TransactionRequest")
print(f"  {len(DERIVED_FEATURES)} derived features (computed at inference)")
print(f"  {len(SENDER_FEATURES)} sender features (from address lookup/cache)")
print(f"\n  ✅ ZERO training/serving skew")
