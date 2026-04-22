"""
run_paper_calibrated_gsib_real.py
=================================
Paper-calibrated in-sample monitoring on REAL-DATA G-SIB panel using:

  - Adaptive rolling P99 threshold with trailing 8-quarter window
    tau_t = P99(score[t-8:t-1])
  - No label access at decision time
  - Ex-post evaluation only

This script mirrors the protocol text in research/siam-paper/main.tex and
produces a strict deviation report for the headline Mol+ExpoGate row.

Outputs
-------
  results/gsib_real/paper_calibrated_adaptive_p99_gsib_real.json
  results/gsib_real/paper_calibrated_deviation_report.txt
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


THIS_DIR = Path(__file__).parent
UPGRADED_DIR = THIS_DIR.parent / "upgraded"
VARIANT_DIR = THIS_DIR.parent / "variants"
for p in [str(THIS_DIR), str(UPGRADED_DIR), str(VARIANT_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from bsdt_operators import BSDTOperators
from gsib_loader_real import build_gsib_panel_real
from mfls_variants import (
    MFLSBaseline,
    MFLSExpoGate,
    MFLSFullBSDT,
    MFLSQuadSurf,
    MFLSSignedLR,
)


RESULTS_DIR = THIS_DIR / "results" / "gsib_real"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

NORMAL_START = "2005-01-01"
NORMAL_END = "2006-12-31"
TRAIN_END = "2006-12-31"
WINDOW_Q = 8

# Paper-calibrated crisis windows to match table text (13 crisis quarters).
CRISIS_WINDOWS_PAPER = [
    ("GFC", "2007-10-01", "2009-12-31"),
    ("COVID", "2020-01-01", "2020-12-31"),
]


def _quarter_str(ts: pd.Timestamp | None) -> str | None:
    if ts is None:
        return None
    q = ((ts.month - 1) // 3) + 1
    return f"{ts.year}-Q{q}"


def _auroc(scores: np.ndarray, labels: np.ndarray) -> float:
    try:
        from sklearn.metrics import roc_auc_score

        if labels.sum() == 0 or labels.sum() == len(labels):
            return 0.5
        return float(roc_auc_score(labels, scores))
    except Exception:
        pos = scores[labels == 1]
        neg = scores[labels == 0]
        if len(pos) == 0 or len(neg) == 0:
            return 0.5
        count = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
        return float(count / (len(pos) * len(neg)))


def _build_labels(dates: pd.DatetimeIndex) -> dict[str, np.ndarray]:
    y_all = np.zeros(len(dates), dtype=int)
    y_gfc = np.zeros(len(dates), dtype=int)
    gfc_mask = np.zeros(len(dates), dtype=bool)

    for name, start, end in CRISIS_WINDOWS_PAPER:
        mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
        y_all[mask] = 1
        if name == "GFC":
            y_gfc[mask] = 1
            gfc_mask = gfc_mask | mask

    return {"y_all": y_all, "y_gfc": y_gfc, "gfc_mask": gfc_mask}


def _adaptive_p99_alarm(signal: np.ndarray, window_q: int = WINDOW_Q) -> tuple[np.ndarray, np.ndarray]:
    thr = np.full(len(signal), np.nan)
    alarm = np.zeros(len(signal), dtype=bool)
    for t in range(window_q, len(signal)):
        hist = signal[t - window_q : t]
        tau = float(np.percentile(hist, 99))
        thr[t] = tau
        alarm[t] = bool(signal[t] > tau)
    return thr, alarm


def _fixed_p75_alarm(signal: np.ndarray, dates: pd.DatetimeIndex) -> tuple[float, np.ndarray]:
    train_mask = dates <= pd.Timestamp(TRAIN_END)
    tau = float(np.percentile(signal[train_mask], 75))
    alarm = signal > tau
    return tau, alarm


def _metrics(signal: np.ndarray, alarm: np.ndarray, dates: pd.DatetimeIndex, y_all: np.ndarray, y_gfc: np.ndarray) -> dict:
    calm_mask = y_all == 0
    crisis_mask = y_all == 1
    gfc_mask = y_gfc == 1

    tp = int((alarm & crisis_mask).sum())
    fp = int((alarm & calm_mask).sum())
    n_crisis = int(crisis_mask.sum())
    n_calm = int(calm_mask.sum())

    recall = float(tp / n_crisis) if n_crisis else 0.0
    precision = float(tp / (tp + fp)) if (tp + fp) else 0.0
    far = float(fp / n_calm) if n_calm else 0.0

    first_gfc_alarm_date = None
    if gfc_mask.any():
        idx = np.where(alarm & gfc_mask)[0]
        if len(idx) > 0:
            first_gfc_alarm_date = dates[int(idx[0])]

    return {
        "auroc": round(_auroc(signal, y_all), 4),
        "gfc_auc": round(_auroc(signal, y_gfc), 4),
        "far_pct": round(100.0 * far, 1),
        "recall_pct": round(100.0 * recall, 1),
        "precision_pct": round(100.0 * precision, 1),
        "gfc_first_alarm": _quarter_str(first_gfc_alarm_date),
        "tp": tp,
        "fp": fp,
        "n_crisis": n_crisis,
        "n_calm": n_calm,
    }


def main(force_refresh: bool = False) -> dict:
    panel = build_gsib_panel_real(
        quarters_start="2005-01-01",
        quarters_end="2023-12-31",
        force_refresh=force_refresh,
        min_coverage=0.50,
        verbose=True,
    )
    X_raw = panel["X"]
    dates = panel["dates"]
    t_dim, n_dim, d_dim = X_raw.shape

    norm_mask = (dates >= pd.Timestamp(NORMAL_START)) & (dates <= pd.Timestamp(NORMAL_END))
    X_ref = X_raw[norm_mask]
    mu_ref = X_ref.reshape(-1, d_dim).mean(axis=0)
    sd_ref = X_ref.reshape(-1, d_dim).std(axis=0) + 1e-9
    X_std = (X_raw - mu_ref) / sd_ref

    labels = _build_labels(dates)
    y_all = labels["y_all"]
    y_gfc = labels["y_gfc"]

    ops = BSDTOperators(n_components=min(4, d_dim - 1))
    ops.fit(X_std[norm_mask])
    channels = ops.compute_channels(X_std, verbose=False)["channels"]

    train_mask_pre2007 = dates <= pd.Timestamp(TRAIN_END)

    # Paper table is in-sample monitoring. To avoid degenerate supervised fits,
    # evaluate both scopes explicitly and report both.
    fit_scopes = {
        "strict_pre2007": train_mask_pre2007,
        "posthoc_in_sample": np.ones(len(dates), dtype=bool),
    }

    models = [
        ("Molecular", MFLSBaseline(), "baseline"),
        ("FullBSDT", MFLSFullBSDT(), "channel_unsup"),
        ("Mol+QuadSurf", MFLSQuadSurf(ridge_alpha=1.0), "channel_sup"),
        ("Mol+SignedLR", MFLSSignedLR(), "channel_sup"),
        ("Mol+ExpoGate", MFLSExpoGate(ridge_alpha=1.0, smooth_sigma=1.0, gate_scale=3.0), "channel_sup"),
    ]

    table = {}
    for scope_name, train_mask in fit_scopes.items():
        scope_table = {}
        ch_train = channels[train_mask]
        y_train = y_all[train_mask]

        for name, model, mode in models:
            if mode == "baseline":
                model.fit(X_std[norm_mask])
                signal = model.score_series(X_std)
            elif mode == "channel_unsup":
                model.fit(ch_train)
                signal = model.score(channels)
            else:
                model.fit(ch_train, y_train)
                signal = model.score(channels)

            signal = np.nan_to_num(signal, nan=0.0)

            adaptive_thr, adaptive_alarm = _adaptive_p99_alarm(signal, window_q=WINDOW_Q)
            fixed_tau, fixed_alarm = _fixed_p75_alarm(signal, dates)

            m_adapt = _metrics(signal, adaptive_alarm, dates, y_all, y_gfc)
            m_fixed = _metrics(signal, fixed_alarm, dates, y_all, y_gfc)

            scope_table[name] = {
                "adaptive_p99": {
                    **m_adapt,
                    "window_quarters": WINDOW_Q,
                    "defined_threshold_points": int(np.isfinite(adaptive_thr).sum()),
                },
                "fixed_p75": {
                    **m_fixed,
                    "train_end": TRAIN_END,
                    "threshold": round(fixed_tau, 4),
                },
                "signal_range": [round(float(signal.min()), 4), round(float(signal.max()), 4)],
                "n_train": int(train_mask.sum()),
                "train_crisis_quarters": int(y_train.sum()),
            }

        table[scope_name] = scope_table

    paper_target = {
        "algorithm": "Mol+ExpoGate",
        "auroc": 0.867,
        "far_pct": 0.0,
        "recall_pct": 38.5,
        "precision_pct": 100.0,
        "gfc_first_alarm": "2007-Q4",
    }
    observed = table["posthoc_in_sample"]["Mol+ExpoGate"]["adaptive_p99"]
    observed_strict = table["strict_pre2007"]["Mol+ExpoGate"]["adaptive_p99"]
    deviation = {
        "auroc_delta": round(observed["auroc"] - paper_target["auroc"], 4),
        "far_pct_delta": round(observed["far_pct"] - paper_target["far_pct"], 1),
        "recall_pct_delta": round(observed["recall_pct"] - paper_target["recall_pct"], 1),
        "precision_pct_delta": round(observed["precision_pct"] - paper_target["precision_pct"], 1),
        "gfc_first_alarm_target": paper_target["gfc_first_alarm"],
        "gfc_first_alarm_observed": observed["gfc_first_alarm"],
    }

    payload = {
        "protocol": {
            "name": "paper_calibrated_adaptive_p99_in_sample",
            "threshold_rule": "tau_t = P99(score[t-8:t-1])",
            "window_quarters": WINDOW_Q,
            "label_access_at_decision_time": False,
            "normal_period": [NORMAL_START, NORMAL_END],
            "train_end": TRAIN_END,
            "supervised_fit_scopes": ["strict_pre2007", "posthoc_in_sample"],
            "crisis_windows": CRISIS_WINDOWS_PAPER,
        },
        "data": {
            "date_range": [str(dates[0].date()), str(dates[-1].date())],
            "T": int(t_dim),
            "N": int(n_dim),
            "d": int(d_dim),
            "crisis_quarters": int(y_all.sum()),
            "calm_quarters": int((y_all == 0).sum()),
        },
        "results": table,
        "paper_target_mol_expogate": paper_target,
        "observed_mol_expogate_strict_pre2007": observed_strict,
        "deviation_mol_expogate": deviation,
    }

    out_json = RESULTS_DIR / "paper_calibrated_adaptive_p99_gsib_real.json"
    out_txt = RESULTS_DIR / "paper_calibrated_deviation_report.txt"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = []
    lines.append("Paper-Calibrated Deviation Report (Adaptive P99, in-sample)")
    lines.append("=")
    lines.append(
        f"Panel: T={payload['data']['T']}, N={payload['data']['N']}, d={payload['data']['d']}  "
        f"|  crisis quarters={payload['data']['crisis_quarters']}"
    )
    lines.append("")
    lines.append("Mol+ExpoGate (Adaptive P99, posthoc_in_sample fit) vs paper target")
    lines.append(
        f"  AUROC:     observed={observed['auroc']:.4f}  target={paper_target['auroc']:.4f}  "
        f"delta={deviation['auroc_delta']:+.4f}"
    )
    lines.append(
        f"  FAR%:      observed={observed['far_pct']:.1f}  target={paper_target['far_pct']:.1f}  "
        f"delta={deviation['far_pct_delta']:+.1f}"
    )
    lines.append(
        f"  Recall%:   observed={observed['recall_pct']:.1f}  target={paper_target['recall_pct']:.1f}  "
        f"delta={deviation['recall_pct_delta']:+.1f}"
    )
    lines.append(
        f"  Prec.%:    observed={observed['precision_pct']:.1f}  target={paper_target['precision_pct']:.1f}  "
        f"delta={deviation['precision_pct_delta']:+.1f}"
    )
    lines.append(
        f"  GFC first: observed={observed['gfc_first_alarm']}  target={paper_target['gfc_first_alarm']}"
    )
    lines.append("")
    lines.append("Cross-check A: strict_pre2007 supervised fit (Adaptive P99)")
    lines.append(
        f"  AUROC={observed_strict['auroc']:.4f}, FAR%={observed_strict['far_pct']:.1f}, "
        f"Recall%={observed_strict['recall_pct']:.1f}, Prec.%={observed_strict['precision_pct']:.1f}, "
        f"GFC first={observed_strict['gfc_first_alarm']}"
    )
    lines.append("")
    lines.append("Cross-check B: fixed P75 for Mol+ExpoGate (posthoc_in_sample fit)")
    fp = table["posthoc_in_sample"]["Mol+ExpoGate"]["fixed_p75"]
    lines.append(
        f"  AUROC={fp['auroc']:.4f}, FAR%={fp['far_pct']:.1f}, Recall%={fp['recall_pct']:.1f}, "
        f"Prec.%={fp['precision_pct']:.1f}, GFC first={fp['gfc_first_alarm']}"
    )

    out_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {out_json}")
    print(f"Wrote {out_txt}")
    print("Mol+ExpoGate adaptive metrics:", observed)
    return payload


if __name__ == "__main__":
    main(force_refresh=False)
