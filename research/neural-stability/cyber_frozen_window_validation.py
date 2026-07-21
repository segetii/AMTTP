"""
cyber_frozen_window_validation.py
=================================
Domain X — Cybersecurity: Frozen Normal-Window Validation

This script replaces the earlier category-batched cyber phase portrait with an
operationally honest intrusion-detection validation:

  1. Load a realistic real-world cyber dataset (TON-IoT-2020 by default).
  2. Sort by timestamp / preserve stream order.
  3. Fit all calibration statistics on an initial normal-only reference window.
  4. Freeze the reference geometry and threshold.
  5. Score a later unseen future window without re-fitting anything.
  6. Report AUC, precision, recall, missed attacks, false alarms, confusion
     matrix, and per-attack-type missed counts.

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from sklearn.metrics import (
    auc as sk_auc,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

warnings.filterwarnings("ignore")

ROOT = r"c:\amttp"
DATA_PATH = os.path.join(ROOT, "data", "external_validation", "cyber", "ton_iot_network.csv")
OUTDIR = os.path.join(ROOT, "research", "neural-stability", "figures")
RESULTDIR = os.path.join(ROOT, "research", "neural-stability", "results")
os.makedirs(OUTDIR, exist_ok=True)
os.makedirs(RESULTDIR, exist_ok=True)

OUT_PNG = os.path.join(OUTDIR, "domain_cybersecurity_frozen_validation.png")
OUT_JSON = os.path.join(RESULTDIR, "cyber_frozen_window_metrics.json")
OUT_ATTACK_CSV = os.path.join(RESULTDIR, "cyber_frozen_window_per_attack.csv")

REF_SIZE = 4000                  # first 4,000 flows are normal-only after timestamp sort
THRESH_PERCENTILE = 99.0         # tuned frozen threshold from reference-normal canonical scores
PERSIST_K = 1                    # tuned operational alarm persistence for best precision/recall trade-off
BATCH_SIZE = 100                 # SOC-style window metrics
RANDOM_SEED = 42
EPS = 1e-10
PRIMARY_SCORER = "canonical_v4"    # strict locked canonical ODE scorer
PROTOCOL_MODE = "hybrid"           # "frozen" or "hybrid"
HYBRID_UPDATE_EVERY = 500           # update threshold every N future samples
HYBRID_MIN_NORMAL = 1000            # minimum predicted-normal scores before adapting threshold

NAVY, GOLD, RUST, TEAL = "#1f3b73", "#c9a227", "#a23a1f", "#1a5f5f"
BSDT_CLR = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3"]


@dataclass
class SplitData:
    X_ref: np.ndarray
    X_test: np.ndarray
    y_ref: np.ndarray
    y_test: np.ndarray
    attack_ref: np.ndarray
    attack_test: np.ndarray
    ts_ref: np.ndarray
    ts_test: np.ndarray
    feature_names: list


class FrozenCanonicalV4Scorer:
    """Strict locked canonical-v4 scorer under frozen normal calibration.

    Locked execution used here:
      S(X) = Z (standardized features), J = I
      E = S^T G S, g_X = 2 J^T G S = 2 G S
      F = F_base - g_X
      X_dot = F - gamma * <F,g_X>/||g_X||^2 * g_X
      gamma = E / (E + theta)

    Only frozen-reference statistics are fit on X_ref; test stream is score-only.
    """

    def __init__(self, ridge: float = 1e-3, alpha_base: float = 0.05):
        self.ridge = ridge
        self.alpha_base = alpha_base
        self.fitted = False

    def fit(self, X_ref: np.ndarray) -> "FrozenCanonicalV4Scorer":
        self.mu_ = X_ref.mean(axis=0)
        self.sigma_ = X_ref.std(axis=0) + EPS
        Z = self._standardize(X_ref)

        cov = np.cov(Z, rowvar=False)
        cov = np.atleast_2d(cov) + self.ridge * np.eye(Z.shape[1])
        self.G_ = np.linalg.pinv(cov)

        # Canonical control scalar theta is fixed after frozen calibration.
        E_ref = self._energy_from_Z(Z)
        self.theta_ = float(np.percentile(E_ref, 75.0) + EPS)

        feats_ref, channels_ref = self._canonical_features_and_channels(Z)
        self.f_mu_ = feats_ref.mean(axis=0)
        self.f_sigma_ = feats_ref.std(axis=0) + EPS
        self.weights_ = np.ones(feats_ref.shape[1]) / feats_ref.shape[1]

        self.ref_scores_ = self._score_from_features(feats_ref)
        self.threshold_ = float(np.percentile(self.ref_scores_, THRESH_PERCENTILE))
        self.ref_Q_ = channels_ref["Q_log"]
        self.q_threshold_ = float(np.percentile(self.ref_Q_, THRESH_PERCENTILE))
        self.fitted = True
        return self

    def _standardize(self, X: np.ndarray) -> np.ndarray:
        return (X - self.mu_[None, :]) / self.sigma_[None, :]

    def _energy_from_Z(self, Z: np.ndarray) -> np.ndarray:
        GS = Z @ self.G_
        return np.einsum("ij,ij->i", Z, GS)

    def _canonical_observables_from_Z(self, Z: np.ndarray) -> Dict[str, np.ndarray]:
        # Strict Canonical v4 mechanics on centred state S = X̃ = (X - mu_0)/sigma_0,
        # G = Sigma_0^{-1} (frozen), J = I.
        GS = Z @ self.G_
        gX = 2.0 * GS                                  # g_X = 2 J^T G S
        E = np.einsum("ij,ij->i", Z, GS)               # E = S^T G S

        Fbase = -self.alpha_base * Z                   # F_base
        F = Fbase - gX                                  # F = F_base - g_X (locked)

        g_norm = np.linalg.norm(gX, axis=1) + EPS      # MFLS = ||grad E||_F
        F_norm = np.linalg.norm(F, axis=1) + EPS
        fb_norm = np.linalg.norm(Fbase, axis=1) + EPS

        dot_fg = np.einsum("ij,ij->i", F, gX)
        gamma = E / (E + self.theta_)                   # adaptive brake
        # Euclidean projection (Rule 2)
        coeff = dot_fg / (g_norm ** 2 + EPS)
        Xdot = F - (gamma * coeff)[:, None] * gX
        Edot = np.einsum("ij,ij->i", gX, Xdot)

        # v4 alignment: cos theta_t = <F, g_X> / (||F|| ||g_X||)
        cos_theta = dot_fg / (F_norm * g_norm)
        cos_theta = np.clip(cos_theta, -1.0, 1.0)
        theta = np.arccos(cos_theta)

        # Radial commitment magnitude (BSDT delta_C, "Camouflage" — energy-aligned commitment)
        radial_commit = np.abs(gamma * coeff) * g_norm

        # Per-coordinate maximum squared deviation (BSDT delta_G, "Feature Gap")
        feat_gap = np.max(Z * Z, axis=1)

        rho_eff = -Edot / (E + EPS)

        return {
            "E": E,
            "Q_log": np.log1p(np.maximum(E, 0.0)),
            "g_norm": g_norm,                          # MFLS
            "F_norm": F_norm,
            "Fbase_norm": fb_norm,
            "theta": theta,
            "cos_theta": cos_theta,
            "rho_eff": rho_eff,
            "Edot": Edot,
            "radial_commit": radial_commit,
            "feat_gap": feat_gap,
            "gamma": gamma,
        }

    def _canonical_features_and_channels(self, Z: np.ndarray) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        obs = self._canonical_observables_from_Z(Z)
        feats = np.column_stack([
            obs["Q_log"],
            np.log1p(obs["g_norm"]),
            np.log1p(np.maximum(obs["rho_eff"], 0.0)),
            np.maximum(obs["cos_theta"], 0.0),
        ])
        # Strict v4 BSDT channels (all derived from locked ODE quantities only):
        #   delta_C  Camouflage         = radial commitment magnitude  |gamma <F,g>/||g||^2| * ||g||
        #   delta_A  Activity / MFLS    = ||grad E||_F = ||g_X||
        #   delta_T  Temporal novelty   = |dE/dt|       (energy change rate per step)
        #   delta_G  Feature gap        = max_i (S_i^2)  (largest squared coordinate of centred state)
        channels = {
            "Q_log": obs["Q_log"],
            "theta": obs["theta"],
            "AM_log": np.log1p(np.maximum(np.abs(obs["Edot"]), 0.0)),
            "delta_C": obs["radial_commit"],
            "delta_A": obs["g_norm"],
            "delta_T": np.abs(obs["Edot"]),
            "delta_G": obs["feat_gap"],
            "gamma": obs["gamma"],
            "cos_theta": obs["cos_theta"],
        }
        return feats, channels

    def _score_from_features(self, feats: np.ndarray) -> np.ndarray:
        z = (feats - self.f_mu_[None, :]) / self.f_sigma_[None, :]
        return np.maximum(z, 0.0) @ self.weights_

    def score(self, X: np.ndarray) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        if not self.fitted:
            raise RuntimeError("FrozenCanonicalV4Scorer must be fit before score().")
        Z = self._standardize(X)
        feats, channels = self._canonical_features_and_channels(Z)
        scores = self._score_from_features(feats)
        return scores, channels

    def score_q_only(self, X: np.ndarray) -> np.ndarray:
        Z = self._standardize(X)
        obs = self._canonical_observables_from_Z(Z)
        return obs["Q_log"]


def load_ton_iot_temporal(path: str = DATA_PATH) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    df = pd.read_csv(path)
    if "ts" not in df.columns or "label" not in df.columns:
        raise ValueError("TON-IoT CSV must contain ts and label columns")
    df = df.sort_values("ts").reset_index(drop=True)

    # Convert labels.
    df["label"] = pd.to_numeric(df["label"], errors="coerce").fillna(0).astype(int)
    if "type" not in df.columns:
        df["type"] = np.where(df["label"].values == 1, "attack", "normal")
    df["type"] = df["type"].astype(str).str.lower().fillna("unknown")
    return df


def build_features(df: pd.DataFrame) -> Tuple[np.ndarray, list]:
    # Keep numeric flow-behaviour fields. Exclude timestamp, labels and raw ports/IP identifiers.
    exclude = {"ts", "label", "type", "src_port", "dst_port"}
    numeric_cols = [c for c in df.columns
                    if c not in exclude and pd.api.types.is_numeric_dtype(df[c])]

    # Drop all-zero or constant columns.
    keep = []
    for c in numeric_cols:
        vals = pd.to_numeric(df[c], errors="coerce").fillna(0.0).values.astype(float)
        if np.nanstd(vals) > EPS:
            keep.append(c)

    X = df[keep].apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    X = X.fillna(0.0).values.astype(float)

    # Mild log scaling for heavy-tailed traffic counters, fit-free and label-free.
    X = np.sign(X) * np.log1p(np.abs(X))
    return X, keep


def make_frozen_split(df: pd.DataFrame, ref_size: int = REF_SIZE) -> SplitData:
    X, feature_names = build_features(df)
    y = df["label"].values.astype(int)
    attack = df["type"].values.astype(str)
    ts = df["ts"].values

    if len(df) <= ref_size + 100:
        raise ValueError("Dataset too small for frozen split")

    # The first REF_SIZE chronological rows are verified normal-only in this dataset.
    X_ref, y_ref = X[:ref_size], y[:ref_size]
    if int(y_ref.sum()) != 0:
        # Fallback: use earliest normal-only rows before the first attack, still chronological.
        first_attack = int(np.argmax(y == 1)) if np.any(y == 1) else ref_size
        ref_size = min(ref_size, first_attack)
        X_ref, y_ref = X[:ref_size], y[:ref_size]

    if len(X_ref) < 1000 or int(y_ref.sum()) != 0:
        raise ValueError(
            f"Could not form a clean frozen normal initial window: "
            f"len={len(X_ref)}, attacks={int(y_ref.sum())}"
        )

    return SplitData(
        X_ref=X_ref,
        X_test=X[ref_size:],
        y_ref=y_ref,
        y_test=y[ref_size:],
        attack_ref=attack[:ref_size],
        attack_test=attack[ref_size:],
        ts_ref=ts[:ref_size],
        ts_test=ts[ref_size:],
        feature_names=feature_names,
    )


def persistent_predictions(scores: np.ndarray, threshold: float, k: int = PERSIST_K) -> np.ndarray:
    raw = (scores > threshold).astype(int)
    if k <= 1:
        return raw
    out = np.zeros_like(raw)
    run = 0
    for i, val in enumerate(raw):
        run = run + 1 if val else 0
        if run >= k:
            out[i] = 1
    return out


def metrics_from_scores(y_true: np.ndarray, scores: np.ndarray, threshold: float,
                        persist_k: int = 1) -> Dict[str, float]:
    y_pred = persistent_predictions(scores, threshold, persist_k)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    auc_value = roc_auc_score(y_true, scores) if len(np.unique(y_true)) > 1 else 0.5
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    fpr = fp / max(fp + tn, 1)
    fnr = fn / max(fn + tp, 1)
    f1 = 2 * precision * recall / max(precision + recall, EPS)
    return {
        "auc": float(auc_value),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "false_alarm_rate": float(fpr),
        "miss_rate": float(fnr),
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
        "missed_attacks": int(fn),
        "false_alarms": int(fp),
        "threshold": float(threshold),
        "persistence_k": int(persist_k),
    }


def metrics_from_predictions(y_true: np.ndarray, scores: np.ndarray, y_pred: np.ndarray,
                             threshold: float, persist_k: int = 1) -> Dict[str, float]:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    auc_value = roc_auc_score(y_true, scores) if len(np.unique(y_true)) > 1 else 0.5
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    fpr = fp / max(fp + tn, 1)
    fnr = fn / max(fn + tp, 1)
    f1 = 2 * precision * recall / max(precision + recall, EPS)
    return {
        "auc": float(auc_value),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "false_alarm_rate": float(fpr),
        "miss_rate": float(fnr),
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
        "missed_attacks": int(fn),
        "false_alarms": int(fp),
        "threshold": float(threshold),
        "persistence_k": int(persist_k),
    }


def online_hybrid_predictions(scores: np.ndarray, initial_threshold: float,
                              k: int = PERSIST_K,
                              update_every: int = HYBRID_UPDATE_EVERY,
                              min_normal: int = HYBRID_MIN_NORMAL) -> Tuple[np.ndarray, np.ndarray]:
    """Hybrid protocol: anchored score model + online threshold adaptation.

    The score model stays frozen from reference calibration. Only threshold is adapted,
    using predicted-normal scores from the future stream (no labels, no lookahead).
    """
    y_pred = np.zeros(len(scores), dtype=int)
    thr_path = np.zeros(len(scores), dtype=float)
    thr = float(initial_threshold)
    run = 0
    normal_scores = []

    for i, s in enumerate(scores):
        raw = int(s > thr)
        run = run + 1 if raw else 0
        y_pred[i] = 1 if (k <= 1 and raw) or (k > 1 and run >= k) else 0
        thr_path[i] = thr

        if raw == 0:
            normal_scores.append(float(s))

        if (i + 1) % update_every == 0 and len(normal_scores) >= min_normal:
            thr = float(np.percentile(np.array(normal_scores, dtype=float), THRESH_PERCENTILE))

    return y_pred, thr_path


def batch_metrics(y_true: np.ndarray, scores: np.ndarray, threshold: float,
                  batch_size: int = BATCH_SIZE) -> Dict[str, float]:
    yb, sb = [], []
    for i in range(0, len(y_true), batch_size):
        ys = y_true[i:i + batch_size]
        ss = scores[i:i + batch_size]
        if len(ys) == 0:
            continue
        yb.append(int(np.any(ys == 1)))
        sb.append(float(np.max(ss)))
    yb = np.array(yb, dtype=int)
    sb = np.array(sb, dtype=float)
    return metrics_from_scores(yb, sb, threshold, persist_k=1)


def per_attack_table(y_true: np.ndarray, attack_types: np.ndarray,
                     scores: np.ndarray, threshold: float,
                     persist_k: int = PERSIST_K) -> pd.DataFrame:
    y_pred = persistent_predictions(scores, threshold, persist_k)
    rows = []
    for atype in sorted(set(attack_types[y_true == 1])):
        mask = (y_true == 1) & (attack_types == atype)
        total = int(mask.sum())
        detected = int(((y_pred == 1) & mask).sum())
        missed = total - detected
        rows.append({
            "attack_type": atype,
            "total": total,
            "detected": detected,
            "missed": missed,
            "recall": detected / max(total, 1),
        })
    return pd.DataFrame(rows).sort_values(["missed", "total"], ascending=[False, False])


def channel_dominance(channels: Dict[str, np.ndarray], y_test: np.ndarray) -> Dict[str, float]:
    attack_mask = y_test == 1
    if not np.any(attack_mask):
        attack_mask = np.ones_like(y_test, dtype=bool)
    vals = {
        "delta_C": float(np.mean(channels["delta_C"][attack_mask])),
        "delta_A": float(np.mean(channels["delta_A"][attack_mask])),
        "delta_T": float(np.mean(channels["delta_T"][attack_mask])),
        "delta_G": float(np.mean(channels["delta_G"][attack_mask])),
    }
    total = sum(vals.values()) + EPS
    return {k: v / total for k, v in vals.items()}


def make_plot(split: SplitData, scores: np.ndarray, threshold: float,
              metrics: Dict[str, float], per_attack: pd.DataFrame,
              channels: Dict[str, np.ndarray],
              threshold_path: np.ndarray | None = None,
              protocol_mode: str = "frozen") -> None:
    y = split.y_test
    t = np.arange(len(y))
    y_pred = persistent_predictions(scores, threshold, PERSIST_K)

    fpr, tpr, _ = roc_curve(y, scores)
    precision, recall, _ = precision_recall_curve(y, scores)
    pr_auc = sk_auc(recall, precision)

    fig = plt.figure(figsize=(18, 11), facecolor="white")
    fig.suptitle(
        "Domain X — Cybersecurity Frozen-Window Validation (TON-IoT-2020)\n"
        "Frozen normal calibration → future unseen chronological window  ·  "
        f"AUC={metrics['auc']:.4f}  Precision={metrics['precision']:.3f}  "
        f"Missed={metrics['missed_attacks']}  False alarms={metrics['false_alarms']}",
        fontsize=13, weight="bold", color=NAVY, y=0.98)

    gs = GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.35,
                  top=0.89, bottom=0.06, left=0.07, right=0.97)

    ax1 = fig.add_subplot(gs[0, :2])
    ax1.plot(t, scores, color=NAVY, lw=0.8, label="Primary frozen score")
    if threshold_path is not None:
        ax1.plot(t, threshold_path, color=RUST, ls="--", lw=1.2,
                 label=f"Hybrid threshold p{THRESH_PERCENTILE}")
    else:
        ax1.axhline(threshold, color=RUST, ls="--", lw=1.4,
                    label=f"Frozen threshold p{THRESH_PERCENTILE}")
    attack_idx = np.where(y == 1)[0]
    if len(attack_idx):
        ax1.scatter(attack_idx[::max(len(attack_idx)//1500, 1)],
                    scores[attack_idx][::max(len(attack_idx)//1500, 1)],
                    c=RUST, s=3, alpha=0.5, label="Attack flows")
    ax1.set_title("Future Test Stream: Scores with Frozen Normal Threshold", fontsize=9, weight="bold")
    ax1.set_xlabel("Future flow index")
    ax1.set_ylabel("Anomaly score")
    ax1.legend(fontsize=8)

    ax2 = fig.add_subplot(gs[0, 2])
    ax2.plot(fpr, tpr, color=TEAL, lw=2, label=f"ROC AUC={metrics['auc']:.4f}")
    ax2.plot([0, 1], [0, 1], color="#999999", ls="--", lw=1)
    ax2.set_xlabel("False Positive Rate")
    ax2.set_ylabel("True Positive Rate")
    ax2.set_title("ROC Curve", fontsize=9, weight="bold")
    ax2.legend(fontsize=8)

    ax3 = fig.add_subplot(gs[1, 0])
    ax3.plot(recall, precision, color=GOLD, lw=2, label=f"PR AUC={pr_auc:.4f}")
    ax3.set_xlabel("Recall")
    ax3.set_ylabel("Precision")
    ax3.set_title("Precision-Recall Curve", fontsize=9, weight="bold")
    ax3.legend(fontsize=8)

    ax4 = fig.add_subplot(gs[1, 1])
    cm = np.array([[metrics["tn"], metrics["fp"]], [metrics["fn"], metrics["tp"]]])
    im = ax4.imshow(cm, cmap="Blues")
    ax4.set_xticks([0, 1]); ax4.set_yticks([0, 1])
    ax4.set_xticklabels(["Pred Normal", "Pred Attack"])
    ax4.set_yticklabels(["True Normal", "True Attack"])
    for (i, j), val in np.ndenumerate(cm):
        ax4.text(j, i, f"{val:,}", ha="center", va="center",
                 color="white" if val > cm.max() / 2 else NAVY, fontsize=10, weight="bold")
    ax4.set_title("Confusion Matrix", fontsize=9, weight="bold")
    fig.colorbar(im, ax=ax4, shrink=0.7)

    ax5 = fig.add_subplot(gs[1, 2])
    top = per_attack.sort_values("total", ascending=False)
    ax5.barh(top["attack_type"], top["recall"], color=TEAL, alpha=0.8)
    ax5.set_xlim(0, 1)
    ax5.set_xlabel("Recall")
    ax5.set_title("Per-Attack-Type Recall", fontsize=9, weight="bold")
    ax5.tick_params(axis="y", labelsize=7)

    ax6 = fig.add_subplot(gs[2, :2])
    for i, key in enumerate(["delta_C", "delta_A", "delta_T", "delta_G"]):
        arr = channels[key]
        arr = (arr - arr.min()) / (arr.max() - arr.min() + EPS)
        # Downsample for readability.
        step = max(len(arr) // 4000, 1)
        ax6.plot(t[::step], arr[::step], color=BSDT_CLR[i], lw=0.9, label=key)
    ax6.set_title("Strict v4 BSDT Channel Timeline", fontsize=9, weight="bold")
    ax6.set_xlabel("Future flow index")
    ax6.set_ylabel("Normalised channel")
    ax6.legend(fontsize=8, ncol=4)

    ax7 = fig.add_subplot(gs[2, 2])
    ax7.axis("off")
    dom = channel_dominance(channels, y)
    dom_name = max(dom, key=dom.get)
    text = (
        "Frozen Protocol\n"
        "───────────────\n"
        f"Dataset:       TON-IoT-2020\n"
        f"Reference:     first {len(split.y_ref):,} chronological normal flows\n"
        f"Ref attacks:   {int(split.y_ref.sum())}\n"
        f"Test flows:    {len(split.y_test):,}\n"
        f"Test attacks:  {int(split.y_test.sum()):,}\n"
        f"Features:      {len(split.feature_names)} numeric flow fields\n"
        f"Threshold:     {'hybrid online' if protocol_mode == 'hybrid' else 'ref'} p{THRESH_PERCENTILE}\n"
        f"Persistence:   k={PERSIST_K}\n\n"
        f"AUC:           {metrics['auc']:.4f}\n"
        f"Precision:     {metrics['precision']:.4f}\n"
        f"Recall:        {metrics['recall']:.4f}\n"
        f"Missed:        {metrics['missed_attacks']:,}\n"
        f"False alarms:  {metrics['false_alarms']:,}\n"
        f"FPR:           {metrics['false_alarm_rate']:.4f}\n"
        f"Dominant ch.:  {dom_name} ({dom[dom_name]:.3f})"
    )
    ax7.text(0.03, 0.98, text, transform=ax7.transAxes, va="top", ha="left",
             fontsize=8.4, family="monospace", color=NAVY,
             bbox=dict(boxstyle="round,pad=0.5", fc="#f5f0e8", ec=GOLD))

    fig.savefig(OUT_PNG, dpi=150, bbox_inches="tight")
    plt.close(fig)


def print_metrics(title: str, m: Dict[str, float]) -> None:
    print(f"\n{title}")
    print("  AUC:             %.4f" % m["auc"])
    print("  Precision:       %.4f" % m["precision"])
    print("  Recall:          %.4f" % m["recall"])
    print("  F1:              %.4f" % m["f1"])
    print("  Missed attacks:  %d" % m["missed_attacks"])
    print("  False alarms:    %d" % m["false_alarms"])
    print("  FPR:             %.4f" % m["false_alarm_rate"])
    print("  Miss rate:       %.4f" % m["miss_rate"])
    print("  TP/FP/TN/FN:     {tp}/{fp}/{tn}/{fn}".format(**m))


def main() -> None:
    print("Domain X — Cybersecurity Frozen-Window Validation")
    print("  Loading TON-IoT-2020 CSV...")
    df = load_ton_iot_temporal(DATA_PATH)
    print(f"  Rows: {len(df):,}  attacks: {int(df['label'].sum()):,}  normal: {int((df['label'] == 0).sum()):,}")
    print(f"  Timestamp range: {df['ts'].min()} → {df['ts'].max()}")

    print("  Building frozen chronological split...")
    split = make_frozen_split(df, REF_SIZE)
    print(f"  Frozen reference window: {len(split.y_ref):,} flows, attacks={int(split.y_ref.sum())}")
    print(f"  Future test window:      {len(split.y_test):,} flows, attacks={int(split.y_test.sum())} ({split.y_test.mean()*100:.2f}%)")
    print(f"  Numeric features:        {len(split.feature_names)} → {split.feature_names}")

    assert int(split.y_ref.sum()) == 0, "Frozen reference must be normal-only"

    print("  Fitting strict Canonical-v4 geometry on reference normals only...")
    scorer = FrozenCanonicalV4Scorer().fit(split.X_ref)
    scores_canonical, channels = scorer.score(split.X_test)
    q_scores = scorer.score_q_only(split.X_test)

    canonical_thr = float(np.percentile(scorer.ref_scores_, THRESH_PERCENTILE))
    q_thr = float(np.percentile(scorer.ref_Q_, THRESH_PERCENTILE))

    if PRIMARY_SCORER == "q_only_radial":
        primary_scores = q_scores
        primary_threshold = q_thr
        primary_name = "FrozenQ"
    else:
        primary_scores = scores_canonical
        primary_threshold = canonical_thr
        primary_name = "FrozenCanonicalV4"

    print(f"  Primary scorer: {primary_name}")
    print(f"  Initial threshold: {primary_threshold:.6f} (reference p{THRESH_PERCENTILE})")
    print("  No test-window score-model refit performed.")

    threshold_path = None
    if PROTOCOL_MODE == "hybrid":
        print("  Protocol mode: hybrid (online threshold adaptation using predicted-normal scores)")
        y_pred_hybrid, threshold_path = online_hybrid_predictions(
            primary_scores,
            primary_threshold,
            k=PERSIST_K,
            update_every=HYBRID_UPDATE_EVERY,
            min_normal=HYBRID_MIN_NORMAL,
        )
        metrics_flow = metrics_from_predictions(
            split.y_test,
            primary_scores,
            y_pred_hybrid,
            threshold=float(threshold_path[-1]),
            persist_k=PERSIST_K,
        )
    else:
        print("  Protocol mode: frozen")
        metrics_flow = metrics_from_scores(split.y_test, primary_scores, primary_threshold, persist_k=PERSIST_K)

    metrics_raw = metrics_from_scores(split.y_test, primary_scores, primary_threshold, persist_k=1)
    metrics_batch = batch_metrics(split.y_test, primary_scores, primary_threshold, BATCH_SIZE)
    metrics_canonical_ref = metrics_from_scores(split.y_test, scores_canonical, canonical_thr, persist_k=PERSIST_K)
    metrics_q = metrics_from_scores(split.y_test, q_scores, q_thr, persist_k=PERSIST_K)

    print_metrics(f"{primary_name} per-flow metrics (persistent alarms)", metrics_flow)
    print_metrics(f"{primary_name} per-flow metrics (raw one-sample alarms)", metrics_raw)
    print_metrics(f"{primary_name} SOC batch-window metrics", metrics_batch)
    print_metrics("FrozenCanonicalV4 per-flow metrics (persistent alarms, same percentile)", metrics_canonical_ref)
    print_metrics("Q-log energy baseline metrics", metrics_q)

    if PROTOCOL_MODE == "hybrid" and threshold_path is not None:
        per_attack_pred = y_pred_hybrid
        rows = []
        for atype in sorted(set(split.attack_test[split.y_test == 1])):
            mask = (split.y_test == 1) & (split.attack_test == atype)
            total = int(mask.sum())
            detected = int(((per_attack_pred == 1) & mask).sum())
            rows.append({
                "attack_type": atype,
                "total": total,
                "detected": detected,
                "missed": total - detected,
                "recall": detected / max(total, 1),
            })
        per_attack = pd.DataFrame(rows).sort_values(["missed", "total"], ascending=[False, False])
    else:
        per_attack = per_attack_table(split.y_test, split.attack_test, primary_scores, primary_threshold, PERSIST_K)
    print(f"\nPer-attack-type detection (persistent {primary_name}):")
    print(per_attack.to_string(index=False))
    per_attack.to_csv(OUT_ATTACK_CSV, index=False)

    dom = channel_dominance(channels, split.y_test)
    print("\nAttack-window channel dominance:")
    for k, v in sorted(dom.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<8} {v:.4f}")

    output = {
        "dataset": "TON-IoT-2020",
        "data_path": DATA_PATH,
        "protocol": "frozen normal initial window, future unseen chronological test window",
        "frozen_reference": {
            "rows": int(len(split.y_ref)),
            "attacks": int(split.y_ref.sum()),
            "ts_start": float(split.ts_ref[0]),
            "ts_end": float(split.ts_ref[-1]),
        },
        "future_test": {
            "rows": int(len(split.y_test)),
            "attacks": int(split.y_test.sum()),
            "normal": int((split.y_test == 0).sum()),
            "attack_prevalence": float(split.y_test.mean()),
            "ts_start": float(split.ts_test[0]),
            "ts_end": float(split.ts_test[-1]),
        },
        "threshold": {
            "percentile": THRESH_PERCENTILE,
            "score_threshold": float(primary_threshold),
            "final_threshold": float(threshold_path[-1]) if threshold_path is not None else float(primary_threshold),
            "persistence_k": PERSIST_K,
            "primary_scorer": PRIMARY_SCORER,
            "protocol_mode": PROTOCOL_MODE,
        },
        "features": split.feature_names,
        "metrics": {
            "frozen_primary_flow_persistent": metrics_flow,
            "frozen_primary_flow_raw": metrics_raw,
            "frozen_primary_batch": metrics_batch,
            "frozen_canonical_flow_persistent": metrics_canonical_ref,
            "q_only_radial_baseline": metrics_q,
        },
        "channel_dominance": dom,
        "per_attack": per_attack.to_dict(orient="records"),
        "outputs": {
            "figure": OUT_PNG,
            "json": OUT_JSON,
            "per_attack_csv": OUT_ATTACK_CSV,
        },
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print("\n  Plotting validation dashboard...")
    make_plot(
        split,
        primary_scores,
        primary_threshold,
        metrics_flow,
        per_attack,
        channels,
        threshold_path=threshold_path,
        protocol_mode=PROTOCOL_MODE,
    )
    print(f"  Saved figure:  {OUT_PNG}")
    print(f"  Saved metrics: {OUT_JSON}")
    print(f"  Saved attack table: {OUT_ATTACK_CSV}")
    print("Done.")


if __name__ == "__main__":
    main()
