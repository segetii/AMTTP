"""
domain_real_eeg.py
==================
Domain VIII (REAL DATA) — Neuroscience EEG: UCI EEG Eye State.
14-channel real Emotiv EEG, ~117 s continuous, binary label = eye open/closed.

Source: https://archive.ics.uci.edu/ml/datasets/EEG+Eye+State

Detection engine: STRICT LOCKED CANONICAL-v4 ODE  (canonical_v4_engine.py)
Presentation style: Odeyemi 2026 BSDT paper
  Fisher-VR weights (eq. 2.4) over the v4 BSDT channels,
  composite E_paper = sum_k w_k z_k(delta_k),
  split-conformal p-values (eq. 6.9) on the v4 anomaly score,
  adaptive rolling P99 threshold (sec. 7.12).
Reference (frozen): first 1,500 samples of eye-open (label==0) baseline.
Crisis epoch: first eye-state transition (open -> closed).
"""
from __future__ import annotations
import json, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from canonical_v4_engine import FrozenCanonicalV4
from canonical_v4_paper_style import (
    evaluate_paper_style, channel_dominance_weighted, first_alarm_lead,
)

DATA = r"C:\amttp\data\external_validation\eeg\uci_eeg_eye_state.arff"
OUTDIR = r"c:\amttp\research\neural-stability\figures"
RESULTDIR = r"c:\amttp\research\neural-stability\results"
os.makedirs(OUTDIR, exist_ok=True); os.makedirs(RESULTDIR, exist_ok=True)
OUT_PNG = os.path.join(OUTDIR, "domain_real_eeg.png")
OUT_JSON = os.path.join(RESULTDIR, "domain_real_eeg.json")

NAVY, GOLD, RUST, TEAL = "#1f3b73", "#c9a227", "#a23a1f", "#1a5f5f"
BSDT_CLR = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3"]
CHANNELS = ["AF3","F7","F3","FC5","T7","P7","O1","O2","P8","T8","FC6","F4","F8","AF4"]


def load_arff(path: str = DATA):
    rows = []
    with open(path, "r") as f:
        in_data = False
        for line in f:
            line = line.strip()
            if not line or line.startswith("%"):
                continue
            if line.upper().startswith("@DATA"):
                in_data = True; continue
            if in_data:
                vals = line.split(",")
                if len(vals) == 15:
                    rows.append(vals)
    arr = np.array(rows, dtype=float)
    X = arr[:, :14]; y = arr[:, 14].astype(int)
    return X, y


def main() -> None:
    X, y = load_arff()
    print(f"  EEG samples: {X.shape[0]}  channels: {X.shape[1]}  open(0): {(y==0).sum()}  closed(1): {(y==1).sum()}")

    # Drop a handful of well-known sensor artefact spikes (>4 sigma per channel)
    med = np.median(X, axis=0); mad = np.median(np.abs(X - med), axis=0) + 1e-6
    keep = np.all(np.abs(X - med) < 8.0 * mad, axis=1)
    X = X[keep]; y = y[keep]
    print(f"  After artefact rejection: {X.shape[0]} samples (kept {keep.mean()*100:.1f}%)")

    # Reference: first 1,500 samples that are eye-open (label==0)
    REF = 1500
    ref_idx = np.where(y == 0)[0][:REF]
    if len(ref_idx) < REF:
        ref_idx = np.where(y == 0)[0]
    crisis_idx = int(np.argmax(y == 1))
    print(f"  Reference: {len(ref_idx)} eye-open samples  crisis (first eye-close): index {crisis_idx}")

    eng = FrozenCanonicalV4(thresh_percentile=99.0).fit(X[ref_idx])
    res = evaluate_paper_style(eng, X, X[ref_idx], alpha_alarm=0.01,
                               rolling_window=200)
    cv4 = res.canonical
    closed_mask = (y == 1)
    open_mask = (y == 0)
    dom = channel_dominance_weighted(res, mask=closed_mask)
    lead = first_alarm_lead(res.alarms_paper, crisis_idx)
    fa = int(np.argmax(res.alarms_paper)) if np.any(res.alarms_paper) else -1
    rate_closed = float(res.alarms_paper[closed_mask].mean())
    rate_open   = float(res.alarms_paper[open_mask].mean())
    print(f"  First alarm: index {fa}  lead = {lead} samples vs first eye-close")
    print(f"  Alarm rate eye-closed: {rate_closed:.4f}   eye-open: {rate_open:.4f}")
    print(f"  Fisher-VR weights  C={res.weights[0]:.3f}  G={res.weights[1]:.3f}  A={res.weights[2]:.3f}  T={res.weights[3]:.3f}")
    print("  BSDT dominance (eye-closed, weighted z):")
    for k, v in sorted(dom.items(), key=lambda kv: -kv[1]):
        print(f"    {k:<8} {v:.4f}")

    # ---- plot ----
    t = np.arange(len(X))
    fig = plt.figure(figsize=(16, 10), facecolor="white")
    fig.suptitle("Domain VIII (REAL) — UCI EEG Eye State (14-ch Emotiv)  ·  Canonical v4 ODE (paper-style presentation)",
                 fontsize=13, weight="bold", color=NAVY, y=0.98)
    gs = GridSpec(3, 3, figure=fig, hspace=0.42, wspace=0.32, top=0.91, bottom=0.07, left=0.07, right=0.97)

    ax = fig.add_subplot(gs[0, :])
    sub = max(len(t)//6000, 1)
    for i in range(min(6, X.shape[1])):
        ax.plot(t[::sub], X[::sub, i], lw=0.4, alpha=0.8, label=CHANNELS[i])
    ax.fill_between(t, X.min(), X.max(), where=(y==1), color=RUST, alpha=0.08, step="mid", label="eye closed")
    ax.set_title("Raw EEG (subset of channels)", fontsize=10, weight="bold")
    ax.legend(fontsize=7, ncol=7)

    ax = fig.add_subplot(gs[1, 0])
    ax.plot(t[::sub], cv4.score[::sub], color=NAVY, lw=0.5, label="v4 score")
    ax.plot(t[::sub], res.E_paper[::sub], color=GOLD, lw=0.4, ls="--", label="E_paper")
    ax.axvline(crisis_idx, color=RUST, ls="--")
    ax.set_title("v4 score vs paper-style composite", fontsize=10, weight="bold"); ax.legend(fontsize=7)

    ax = fig.add_subplot(gs[1, 1])
    ax.semilogy(t[::sub], np.clip(res.pvalue[::sub], 1e-4, 1.0), color=GOLD, lw=0.5)
    ax.axhline(res.info["alpha_alarm_effective"], color=RUST, ls="--",
               label=f"α_eff = {res.info['alpha_alarm_effective']:.3f}")
    ax.axvline(crisis_idx, color=RUST, ls="--")
    ax.set_title("Split-conformal p-value (on v4 score)", fontsize=10, weight="bold"); ax.legend(fontsize=7)

    ax = fig.add_subplot(gs[1, 2])
    ax.plot(t[::sub], cv4.score[::sub], color=NAVY, lw=0.5, label="v4 score")
    ax.plot(t[::sub], res.threshold_adaptive[::sub], color=RUST, ls="--", lw=0.5, label="adaptive P99")
    ax.axhline(cv4.threshold, color=GOLD, ls=":", lw=0.6, label=f"frozen p99={cv4.threshold:.3f}")
    ax.set_title("v4 score vs adaptive + frozen thresholds", fontsize=10, weight="bold"); ax.legend(fontsize=7)

    ax = fig.add_subplot(gs[2, :2])
    for i, key in enumerate(["delta_C","delta_G","delta_A","delta_T"]):
        v = getattr(cv4, key); v = (v - v.min())/(v.max()-v.min()+1e-12)
        ax.plot(t[::sub], v[::sub], color=BSDT_CLR[i], lw=0.6,
                label=f"{key} (w={res.weights[i]:.2f})")
    ax.fill_between(t, 0, 1, where=(y==1), color=RUST, alpha=0.06, step="mid")
    ax.set_title("Canonical-v4 BSDT channels (min-max normalised) with Fisher-VR weights", fontsize=10, weight="bold")
    ax.legend(fontsize=8, ncol=4)

    ax = fig.add_subplot(gs[2, 2]); ax.axis("off")
    txt = ("Canonical v4 ODE (math)  ·  Paper-style presentation\n"
           "Source: UCI EEG Eye State (Emotiv 14-ch)\n"
           f"Samples: {X.shape[0]}  Channels: 14\n"
           f"Reference: {len(ref_idx)} eye-open (frozen)\n"
           f"Frozen v4 p99: {cv4.threshold:.4f}\n"
           f"Fisher-VR weights (over v4 channels):\n"
           f"  δ_C={res.weights[0]:.3f}  δ_G={res.weights[1]:.3f}\n"
           f"  δ_A={res.weights[2]:.3f}  δ_T={res.weights[3]:.3f}\n"
           f"Crisis: first eye-close (idx {crisis_idx})\n\n"
           f"Conformal alarm α_eff: {res.info['alpha_alarm_effective']:.3f}\n"
           f"First alarm idx: {fa}  lead = {lead}\n"
           f"Alarm rate eye-closed: {rate_closed:.4f}\n"
           f"Alarm rate eye-open:   {rate_open:.4f}\n\n"
           "BSDT dominance (closed, weighted z):\n"
           + "\n".join(f"  {k:<8} {v:.3f}" for k,v in sorted(dom.items(), key=lambda kv:-kv[1])))
    ax.text(0.0, 1.0, txt, va="top", ha="left", fontsize=8.0, family="monospace",
            color=NAVY, bbox=dict(boxstyle="round,pad=0.5", fc="#f5f0e8", ec=GOLD))

    fig.savefig(OUT_PNG, dpi=150, bbox_inches="tight"); plt.close(fig)
    out = {
        "dataset": "UCI EEG Eye State (Emotiv 14-ch)",
        "source_url": "https://archive.ics.uci.edu/ml/datasets/EEG+Eye+State",
        "engine": "FrozenCanonicalV4 (canonical-v4 ODE)",
        "presentation": "Odeyemi 2026 paper-style",
        "samples": int(X.shape[0]),
        "channels": CHANNELS,
        "reference_size": int(len(ref_idx)),
        "crisis_index": int(crisis_idx),
        "fisher_vr_weights": {"C": float(res.weights[0]), "G": float(res.weights[1]),
                              "A": float(res.weights[2]), "T": float(res.weights[3])},
        "frozen_v4_threshold_p99": float(cv4.threshold),
        "alpha_alarm_effective": float(res.info["alpha_alarm_effective"]),
        "first_alarm_index": int(fa),
        "lead_samples": int(lead),
        "alarm_rate_eye_closed": rate_closed,
        "alarm_rate_eye_open":   rate_open,
        "bsdt_dominance_eye_closed": dom,
        "engine_info": res.info,
        "outputs": {"figure": OUT_PNG, "json": OUT_JSON},
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"  Saved {OUT_PNG}\n  Saved {OUT_JSON}")


if __name__ == "__main__":
    main()
