"""
AMTTP Student Meta-Learner Comparison
======================================
Trains 3 meta-learners on top of XGB + LGB base learners, with SHAP-guided
feature selection, and compares all approaches.

Meta-Learner 1: Baseline LogisticRegression stacking [xgb_prob, lgb_prob]
Meta-Learner 2: SHAP top-K feature-augmented LogReg  [xgb_prob, lgb_prob, top_shap_feats...]
Meta-Learner 3: Q-Learning–guided Neural Network      [xgb_prob, lgb_prob, top_shap_feats...]

Dataset: eth_addresses_labeled_v2.parquet (625K addresses, 80 cols)
Labels:  fraud (binary, from hybrid 3-signal scoring)

Architecture:
─────────────────────────────────────────────────────────────────
  Raw features (address-level aggregates + graph + pattern)
          │
          ├──► XGBoost (5-fold OOF)  ──► xgb_prob
          ├──► LightGBM (5-fold OOF) ──► lgb_prob
          │
          ├──► SHAP TreeExplainer  ──► Top-K features
          │
          ├──► Meta-1: LogReg(xgb, lgb)
          ├──► Meta-2: LogReg(xgb, lgb, shap_top_K)
          └──► Meta-3: Q-NN(xgb, lgb, shap_top_K)
─────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json
import time
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Config ───────────────────────────────────────────────────────────────────
DATA_PATH = r"C:\amttp\processed\eth_addresses_labeled_v2.parquet"
OUTPUT_DIR = Path(r"C:\amttp\ml\Automation\student_meta_learners")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

N_FOLDS = 5
RANDOM_STATE = 42
SHAP_TOP_K = 15          # Number of SHAP features to add to Meta-2 and Meta-3
SHAP_SAMPLE = 10_000     # Subsample for SHAP computation
QNN_HIDDEN = 64           # Hidden units in Q-NN
QNN_EPOCHS = 100
QNN_LR = 1e-3
QNN_GAMMA = 0.99          # Q-learning discount factor
QNN_EPSILON_DECAY = 0.995 # Exploration decay

np.random.seed(RANDOM_STATE)

print("=" * 80)
print("  AMTTP STUDENT META-LEARNER COMPARISON")
print("=" * 80)

# ═══════════════════════════════════════════════════════════════════════════
# 1. LOAD & PREPARE FEATURES
# ═══════════════════════════════════════════════════════════════════════════
print("\n[1/8] Loading labeled dataset …")
t_total = time.perf_counter()
t0 = time.perf_counter()

df = pd.read_parquet(DATA_PATH)
print(f"  {len(df):,} rows × {len(df.columns)} cols")
print(f"  fraud=1: {df['fraud'].sum():,} ({df['fraud'].mean()*100:.2f}%)")

# ── Feature selection: all numeric, leak-free ────────────────────────────
LEAK_COLS = {
    "address", "patterns", "risk_level", "ultra_risk_level",
    "fraud", "risk_class",
    # Teacher-derived scores ARE the label source → leakage
    "hybrid_score", "xgb_raw_score", "xgb_normalized",
    "pattern_boost", "soph_normalized", "sophisticated_score",
    "ultra_hybrid_score", "signal_count",
    # Teacher secondary
    "teacher_raw_score", "teacher_normalized",
    # Timestamps (not numeric, not useful for tree models directly)
    "first_sent_time", "last_sent_time",
    "first_received_time", "last_received_time",
}

numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
FEATURE_COLS = sorted([c for c in numeric_cols if c not in LEAK_COLS])

print(f"\n  Features selected: {len(FEATURE_COLS)} (leak-free numeric)")
print(f"  Excluded (leakage/meta): {sorted(LEAK_COLS & set(df.columns))}")

X = df[FEATURE_COLS].values.astype(np.float32)
y = df["fraud"].values.astype(np.int32)

# Replace inf/nan
X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

print(f"  X shape: {X.shape}  y balance: {y.sum()}/{len(y)}")
print(f"  Loaded in {time.perf_counter()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════
# 2. 5-FOLD OOF XGB + LGB BASE LEARNERS
# ═══════════════════════════════════════════════════════════════════════════
print("\n[2/8] Training base learners (5-fold OOF) …")
t0 = time.perf_counter()

from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import RobustScaler
import xgboost as xgb
import lightgbm as lgb

kf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
oof_xgb = np.zeros(len(y), dtype=np.float64)
oof_lgb = np.zeros(len(y), dtype=np.float64)
oof_fold = np.full(len(y), -1, dtype=np.int32)  # track which fold

scale_pos_weight = (y == 0).sum() / max((y == 1).sum(), 1)
print(f"  scale_pos_weight: {scale_pos_weight:.1f}")

for fold, (tr_idx, va_idx) in enumerate(kf.split(X, y)):
    print(f"\n  ── Fold {fold+1}/{N_FOLDS} ──")
    X_tr, X_va = X[tr_idx], X[va_idx]
    y_tr, y_va = y[tr_idx], y[va_idx]
    oof_fold[va_idx] = fold

    # Scale
    scaler = RobustScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_va_s = scaler.transform(X_va)

    # XGBoost
    xgb_clf = xgb.XGBClassifier(
        n_estimators=1000, max_depth=7, learning_rate=0.03,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
        scale_pos_weight=scale_pos_weight,
        eval_metric="logloss", random_state=RANDOM_STATE,
        n_jobs=-1, tree_method="hist", early_stopping_rounds=30,
    )
    xgb_clf.fit(X_tr_s, y_tr, eval_set=[(X_va_s, y_va)], verbose=0)
    oof_xgb[va_idx] = xgb_clf.predict_proba(X_va_s)[:, 1]
    print(f"    XGB best iter: {xgb_clf.best_iteration}")

    # LightGBM
    lgb_tr = lgb.Dataset(X_tr_s, y_tr, feature_name=FEATURE_COLS)
    lgb_va = lgb.Dataset(X_va_s, y_va, feature_name=FEATURE_COLS, reference=lgb_tr)
    lgb_params = {
        "objective": "binary", "metric": "binary_logloss",
        "num_leaves": 127, "max_depth": 7, "learning_rate": 0.03,
        "subsample": 0.8, "colsample_bytree": 0.8,
        "min_child_samples": 50, "scale_pos_weight": scale_pos_weight,
        "random_state": RANDOM_STATE, "n_jobs": -1, "verbose": -1,
    }
    lgb_model = lgb.train(
        lgb_params, lgb_tr, num_boost_round=1000,
        valid_sets=[lgb_va],
        callbacks=[lgb.early_stopping(30), lgb.log_evaluation(0)],
    )
    oof_lgb[va_idx] = lgb_model.predict(X_va_s)
    print(f"    LGB best iter: {lgb_model.best_iteration}")

    # Save last fold models for SHAP + final inference
    if fold == N_FOLDS - 1:
        last_xgb = xgb_clf
        last_lgb = lgb_model
        last_scaler = scaler

# Save base learners (last fold)
last_xgb.save_model(str(OUTPUT_DIR / "xgb_base.ubj"))
last_lgb.save_model(str(OUTPUT_DIR / "lgb_base.txt"))

from sklearn.metrics import roc_auc_score, average_precision_score
print(f"\n  OOF XGB: ROC-AUC={roc_auc_score(y, oof_xgb):.4f}  PR-AUC={average_precision_score(y, oof_xgb):.4f}")
print(f"  OOF LGB: ROC-AUC={roc_auc_score(y, oof_lgb):.4f}  PR-AUC={average_precision_score(y, oof_lgb):.4f}")
print(f"  Base learners done in {time.perf_counter()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════
# 3. SHAP FEATURE IMPORTANCE → TOP-K SELECTION
# ═══════════════════════════════════════════════════════════════════════════
print(f"\n[3/8] SHAP analysis (top {SHAP_TOP_K} features) …")
t0 = time.perf_counter()

import shap

# Use last-fold XGB and a subsample for speed
shap_idx = np.random.choice(len(X), min(SHAP_SAMPLE, len(X)), replace=False)
X_shap = last_scaler.transform(X[shap_idx])

explainer = shap.TreeExplainer(last_xgb)
shap_values = explainer.shap_values(X_shap)

mean_abs_shap = np.abs(shap_values).mean(axis=0)
shap_importance = pd.DataFrame({
    "feature": FEATURE_COLS,
    "mean_abs_shap": mean_abs_shap,
}).sort_values("mean_abs_shap", ascending=False)

TOP_K_FEATURES = shap_importance["feature"].head(SHAP_TOP_K).tolist()
TOP_K_INDICES = [FEATURE_COLS.index(f) for f in TOP_K_FEATURES]

print(f"\n  SHAP Top {SHAP_TOP_K} Features:")
print(f"  {'Rank':<5} {'Feature':<35} {'Mean |SHAP|':>12}")
print(f"  {'-'*5} {'-'*35} {'-'*12}")
for i, (_, row) in enumerate(shap_importance.head(SHAP_TOP_K).iterrows()):
    bar = "█" * min(int(row["mean_abs_shap"] * 50), 40)
    print(f"  {i+1:<5} {row['feature']:<35} {row['mean_abs_shap']:>12.6f}  {bar}")

# Save SHAP importance
shap_importance.to_csv(str(OUTPUT_DIR / "shap_importance.csv"), index=False)
print(f"\n  SHAP done in {time.perf_counter()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════
# 4. META-LEARNER 1: Baseline LogReg [xgb_prob, lgb_prob]
# ═══════════════════════════════════════════════════════════════════════════
print("\n[4/8] Meta-Learner 1: Baseline LogReg(xgb, lgb) …")
t0 = time.perf_counter()

from sklearn.linear_model import LogisticRegressionCV
from sklearn.metrics import (
    precision_recall_curve, f1_score, precision_score, recall_score
)
import joblib

def find_optimal_threshold(y_true, y_prob):
    prec, rec, thresholds = precision_recall_curve(y_true, y_prob)
    f1s = 2 * prec * rec / (prec + rec + 1e-10)
    best_idx = np.argmax(f1s)
    return thresholds[min(best_idx, len(thresholds) - 1)], f1s[best_idx]

def evaluate(name, y_true, y_prob):
    roc = roc_auc_score(y_true, y_prob)
    pr = average_precision_score(y_true, y_prob)
    thr, _ = find_optimal_threshold(y_true, y_prob)
    y_pred = (y_prob >= thr).astype(int)
    f1 = f1_score(y_true, y_pred, zero_division=0)
    prec = precision_score(y_true, y_pred, zero_division=0)
    rec = recall_score(y_true, y_pred, zero_division=0)
    return {
        "name": name, "roc_auc": roc, "pr_auc": pr,
        "f1": f1, "precision": prec, "recall": rec, "threshold": float(thr),
    }

# OOF meta features
meta1_X = np.column_stack([oof_xgb, oof_lgb])

meta1 = LogisticRegressionCV(
    Cs=10, cv=3, scoring="average_precision",
    class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE,
)
meta1.fit(meta1_X, y)
meta1_prob = meta1.predict_proba(meta1_X)[:, 1]

r1 = evaluate("Meta-1 Baseline LogReg", y, meta1_prob)
print(f"  ROC-AUC={r1['roc_auc']:.4f}  PR-AUC={r1['pr_auc']:.4f}  F1={r1['f1']:.4f}")
print(f"  Coef: {meta1.coef_[0].tolist()}  Intercept: {meta1.intercept_[0]:.4f}")

joblib.dump(meta1, str(OUTPUT_DIR / "meta1_baseline_logreg.joblib"))
print(f"  Done in {time.perf_counter()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════
# 5. META-LEARNER 2: SHAP-Augmented LogReg [xgb, lgb, top_K_features]
# ═══════════════════════════════════════════════════════════════════════════
print(f"\n[5/8] Meta-Learner 2: SHAP-Augmented LogReg (top {SHAP_TOP_K} features) …")
t0 = time.perf_counter()

# Scale the top-K features per fold to match OOF
X_topk_scaled = np.zeros((len(y), SHAP_TOP_K), dtype=np.float32)
for fold_i in range(N_FOLDS):
    mask = oof_fold == fold_i
    sc = RobustScaler()
    # Fit on training folds, transform validation fold
    train_mask = ~mask
    sc.fit(X[train_mask][:, TOP_K_INDICES])
    X_topk_scaled[mask] = sc.transform(X[mask][:, TOP_K_INDICES])

meta2_X = np.column_stack([oof_xgb, oof_lgb, X_topk_scaled])

meta2 = LogisticRegressionCV(
    Cs=10, cv=3, scoring="average_precision",
    class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE,
)
meta2.fit(meta2_X, y)
meta2_prob = meta2.predict_proba(meta2_X)[:, 1]

r2 = evaluate("Meta-2 SHAP-Augmented LogReg", y, meta2_prob)
print(f"  ROC-AUC={r2['roc_auc']:.4f}  PR-AUC={r2['pr_auc']:.4f}  F1={r2['f1']:.4f}")
print(f"  Coef: {meta2.coef_[0][:5].tolist()} … ({len(meta2.coef_[0])} total)")

# Show feature weights
meta2_names = ["xgb_prob", "lgb_prob"] + TOP_K_FEATURES
print(f"\n  Meta-2 Feature Weights:")
for name, w in sorted(zip(meta2_names, meta2.coef_[0]), key=lambda x: -abs(x[1])):
    print(f"    {name:<35} {w:+.4f}")

joblib.dump(meta2, str(OUTPUT_DIR / "meta2_shap_logreg.joblib"))

# Save scaler for top-K features (refit on full data)
topk_scaler = RobustScaler()
topk_scaler.fit(X[:, TOP_K_INDICES])
joblib.dump(topk_scaler, str(OUTPUT_DIR / "topk_scaler.joblib"))

print(f"  Done in {time.perf_counter()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════
# 6. META-LEARNER 3: Q-LEARNING NEURAL NETWORK
# ═══════════════════════════════════════════════════════════════════════════
print(f"\n[6/8] Meta-Learner 3: Q-Learning Neural Network …")
t0 = time.perf_counter()

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"  Device: {device}")

# ── Architecture: DQN that learns optimal fraud/clear decision ───────────
#
# The key insight: we frame fraud detection as a sequential decision problem.
# For each address, the agent observes a STATE (base learner probs + SHAP
# features) and takes an ACTION (classify as fraud=1 or clear=0).
#
# REWARD design:
#   Correct fraud catch (TP):  +10  (high reward — catching fraud is critical)
#   Correct clear (TN):        +1   (modest reward — normal case)
#   Missed fraud (FN):        -20   (severe penalty — worst outcome)
#   False alarm (FP):          -2   (moderate penalty — wastes investigation)
#
# This asymmetric reward structure naturally learns the precision-recall
# tradeoff that's appropriate for fraud detection: high recall priority
# with controlled false positive rate.
#
# The LogReg layer after DQN combines the Q-values with raw features for
# the final probability, bridging RL exploration with calibrated output.

class FraudDQN(nn.Module):
    """Deep Q-Network for fraud classification."""
    def __init__(self, input_dim, hidden_dim=64):
        super().__init__()
        self.feature_net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.1),
        )
        # Q-value head: 2 actions (clear=0, fraud=1)
        self.q_head = nn.Linear(hidden_dim, 2)
        # Embedding head for the meta output
        self.embed_head = nn.Linear(hidden_dim, hidden_dim // 2)

    def forward(self, x):
        h = self.feature_net(x)
        q_values = self.q_head(h)
        embedding = self.embed_head(h)
        return q_values, embedding


class QLearningTrainer:
    """
    Trains DQN with experience replay + epsilon-greedy exploration,
    then uses the learned Q-values as features for a final LogReg layer.
    """
    def __init__(self, input_dim, hidden_dim, lr, gamma, device):
        self.device = device
        self.gamma = gamma

        self.policy_net = FraudDQN(input_dim, hidden_dim).to(device)
        self.target_net = FraudDQN(input_dim, hidden_dim).to(device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()

        self.optimizer = optim.AdamW(self.policy_net.parameters(), lr=lr, weight_decay=1e-4)
        self.loss_fn = nn.SmoothL1Loss()

        # Reward matrix: [action, true_label] → reward
        # action 0=clear, 1=fraud
        self.rewards = torch.tensor([
            [ 1.0, -20.0],  # action=clear:  TN=+1, FN=-20
            [-2.0,  10.0],  # action=fraud:  FP=-2, TP=+10
        ], device=device)

    def compute_reward(self, actions, labels):
        """Vectorized reward lookup."""
        return self.rewards[actions.long(), labels.long()]

    def train_epoch(self, X_tensor, y_tensor, epsilon):
        self.policy_net.train()
        total_loss = 0
        total_reward = 0

        # Batch processing
        batch_size = 2048
        n = len(X_tensor)
        indices = torch.randperm(n, device=self.device)

        for start in range(0, n, batch_size):
            idx = indices[start:start + batch_size]
            states = X_tensor[idx]
            labels = y_tensor[idx]

            # Epsilon-greedy action selection
            q_vals, _ = self.policy_net(states)
            rand_mask = torch.rand(len(states), device=self.device) < epsilon
            actions = q_vals.argmax(dim=1)
            random_actions = torch.randint(0, 2, (len(states),), device=self.device)
            actions = torch.where(rand_mask, random_actions, actions)

            # Compute rewards
            rewards = self.compute_reward(actions, labels)
            total_reward += rewards.sum().item()

            # Q-learning target: r + gamma * max_a' Q_target(s', a')
            # Since this is single-step (no next state), target = reward
            with torch.no_grad():
                target_q, _ = self.target_net(states)
                target = rewards + self.gamma * target_q.max(dim=1).values * 0.1

            current_q = q_vals.gather(1, actions.unsqueeze(1)).squeeze()
            loss = self.loss_fn(current_q, target)

            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.policy_net.parameters(), 1.0)
            self.optimizer.step()

            total_loss += loss.item()

        return total_loss, total_reward / n

    def update_target(self, tau=0.1):
        """Soft update of target network."""
        for tp, pp in zip(self.target_net.parameters(), self.policy_net.parameters()):
            tp.data.copy_(tau * pp.data + (1 - tau) * tp.data)

    @torch.no_grad()
    def get_features(self, X_tensor):
        """Extract Q-values + embeddings as meta-features."""
        self.policy_net.eval()
        q_vals, embeddings = self.policy_net(X_tensor)
        # Features: Q(clear), Q(fraud), Q_diff, softmax(Q), embedding
        q_diff = q_vals[:, 1] - q_vals[:, 0]
        q_soft = torch.softmax(q_vals, dim=1)[:, 1]
        return torch.cat([
            q_vals,           # Q(clear), Q(fraud)
            q_diff.unsqueeze(1),  # Q-advantage
            q_soft.unsqueeze(1),  # P(fraud) from Q
            embeddings,       # Learned representation
        ], dim=1)


# ── Train DQN on OOF meta features ──────────────────────────────────────
meta3_input = np.column_stack([oof_xgb, oof_lgb, X_topk_scaled]).astype(np.float32)
input_dim = meta3_input.shape[1]

X_t = torch.tensor(meta3_input, device=device)
y_t = torch.tensor(y, dtype=torch.float32, device=device)

trainer = QLearningTrainer(input_dim, QNN_HIDDEN, QNN_LR, QNN_GAMMA, device)

epsilon = 1.0
print(f"  Training DQN ({QNN_EPOCHS} epochs, input_dim={input_dim}, hidden={QNN_HIDDEN}) …")

best_reward = -np.inf
patience_counter = 0
for epoch in range(QNN_EPOCHS):
    loss, avg_reward = trainer.train_epoch(X_t, y_t, epsilon)
    epsilon = max(0.01, epsilon * QNN_EPSILON_DECAY)

    if epoch % 5 == 0:
        trainer.update_target()

    if avg_reward > best_reward:
        best_reward = avg_reward
        patience_counter = 0
        best_state = {k: v.clone() for k, v in trainer.policy_net.state_dict().items()}
    else:
        patience_counter += 1

    if (epoch + 1) % 20 == 0:
        print(f"    Epoch {epoch+1:3d}: loss={loss:.4f}  avg_reward={avg_reward:.3f}  ε={epsilon:.3f}")

    if patience_counter >= 20:
        print(f"  Early stopping at epoch {epoch+1} (no improvement for 20 epochs)")
        break

# Load best model
trainer.policy_net.load_state_dict(best_state)
print(f"  Best avg reward: {best_reward:.3f}")

# Extract DQN features
qnn_features = trainer.get_features(X_t).cpu().numpy()
print(f"  DQN feature dim: {qnn_features.shape[1]}")

# Final LogReg on top of DQN features + raw meta features
meta3_combined = np.column_stack([meta3_input, qnn_features])
meta3 = LogisticRegressionCV(
    Cs=10, cv=3, scoring="average_precision",
    class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE,
)
meta3.fit(meta3_combined, y)
meta3_prob = meta3.predict_proba(meta3_combined)[:, 1]

r3 = evaluate("Meta-3 Q-Learning NN", y, meta3_prob)
print(f"  ROC-AUC={r3['roc_auc']:.4f}  PR-AUC={r3['pr_auc']:.4f}  F1={r3['f1']:.4f}")

# Save
torch.save(trainer.policy_net.state_dict(), str(OUTPUT_DIR / "meta3_qnn.pt"))
joblib.dump(meta3, str(OUTPUT_DIR / "meta3_final_logreg.joblib"))
print(f"  Done in {time.perf_counter()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════
# 7. ALSO EVALUATE: Raw base learners + simple average
# ═══════════════════════════════════════════════════════════════════════════
print("\n[7/8] Evaluating all variants …")
t0 = time.perf_counter()

r_xgb = evaluate("Base XGB (OOF)", y, oof_xgb)
r_lgb = evaluate("Base LGB (OOF)", y, oof_lgb)
r_avg = evaluate("Simple Average (XGB+LGB)/2", y, (oof_xgb + oof_lgb) / 2)

all_results = [r_xgb, r_lgb, r_avg, r1, r2, r3]
print(f"  Evaluated in {time.perf_counter()-t0:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════
# 8. COMPARISON TABLE + SAVE
# ═══════════════════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("  FULL META-LEARNER COMPARISON")
print(f"{'='*80}")
print(f"\n  {'Model':<35} {'ROC-AUC':>8} {'PR-AUC':>8} {'F1':>8} {'Prec':>8} {'Recall':>8}")
print(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

for r in all_results:
    print(f"  {r['name']:<35} {r['roc_auc']:>8.4f} {r['pr_auc']:>8.4f} {r['f1']:>8.4f} {r['precision']:>8.4f} {r['recall']:>8.4f}")

# Determine winner
best = max(all_results, key=lambda r: r["pr_auc"])
print(f"\n  🏆 BEST (by PR-AUC): {best['name']}  PR-AUC={best['pr_auc']:.4f}")

# Delta table
print(f"\n  IMPROVEMENT OVER BASELINE (Meta-1):")
baseline_pr = r1["pr_auc"]
for r in all_results:
    delta = r["pr_auc"] - baseline_pr
    sign = "+" if delta >= 0 else ""
    print(f"    {r['name']:<35} {sign}{delta:.4f} ({sign}{delta/max(baseline_pr,1e-10)*100:.1f}%)")

# ── Save everything ──────────────────────────────────────────────────────
config = {
    "version": datetime.now().strftime("%Y%m%d_%H%M%S"),
    "dataset": DATA_PATH,
    "n_addresses": int(len(df)),
    "n_fraud": int(y.sum()),
    "n_folds": N_FOLDS,
    "n_features": len(FEATURE_COLS),
    "feature_names": FEATURE_COLS,
    "shap_top_k": SHAP_TOP_K,
    "shap_features": TOP_K_FEATURES,
    "meta_learners": {
        "meta1_baseline": {
            "type": "LogisticRegressionCV",
            "input_features": ["xgb_prob", "lgb_prob"],
            **{k: round(v, 4) if isinstance(v, float) else v for k, v in r1.items()},
        },
        "meta2_shap": {
            "type": "LogisticRegressionCV + SHAP top-K",
            "input_features": ["xgb_prob", "lgb_prob"] + TOP_K_FEATURES,
            **{k: round(v, 4) if isinstance(v, float) else v for k, v in r2.items()},
        },
        "meta3_qnn": {
            "type": "Q-Learning DQN + LogisticRegressionCV",
            "input_features": ["xgb_prob", "lgb_prob"] + TOP_K_FEATURES + [
                "Q_clear", "Q_fraud", "Q_advantage", "P_fraud_q",
                *[f"dqn_embed_{i}" for i in range(QNN_HIDDEN // 2)],
            ],
            "qnn_config": {
                "hidden": QNN_HIDDEN, "epochs": QNN_EPOCHS,
                "lr": QNN_LR, "gamma": QNN_GAMMA,
            },
            **{k: round(v, 4) if isinstance(v, float) else v for k, v in r3.items()},
        },
    },
    "comparison": {r["name"]: {k: round(v, 4) if isinstance(v, float) else v for k, v in r.items()} for r in all_results},
    "best_model": best["name"],
}

with open(OUTPUT_DIR / "meta_comparison.json", "w") as f:
    json.dump(config, f, indent=2, default=str)

# Save OOF predictions for reproducibility
oof_df = pd.DataFrame({
    "address": df["address"].values,
    "fraud": y,
    "oof_xgb": oof_xgb,
    "oof_lgb": oof_lgb,
    "meta1_prob": meta1_prob,
    "meta2_prob": meta2_prob,
    "meta3_prob": meta3_prob,
})
oof_df.to_parquet(str(OUTPUT_DIR / "oof_predictions.parquet"), index=False)

elapsed = time.perf_counter() - t_total
print(f"\n  All artifacts saved to: {OUTPUT_DIR}")
print(f"  Total time: {elapsed:.1f}s")
print(f"{'='*80}")
