"""§XVII Early-Warning lead-time sweep — two-layer (Precursor + Geometry).

For each of FDIC, WORLD-BANK, ERCOT, PROTEIN we replay a lookback window
ending at the stress event and evaluate both EWS layers for every t:

  Layer A (Precursor):  p1=max(0,P_t), p2=1-cosψ, p3=std(S), p4=Σ|ΔS|
                        Normalised vs P95 of the normal period.  Alarm ≥ 1.0.
  Layer B (Geometry):   six ξ signals, geometric mean.
                        Alarm ≥ empirical μ+2σ of the normal period (min of
                        this and the §XVII.2 closed-form threshold).

Lead time = t_event − t_first_breach, in dataset-native units.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "adaptive-friction"))

from collapse_geometry import (
    MasterOperator, Snapshot, LedoitWolfNetwork,
    CollapseGeometry, EarlyWarning, PrecursorScale, InformationGeometry,
)

from run_real_data_simulations import (
    load_fdic, load_worldbank, load_ercot, load_protein,
)


def sweep_ews(name: str, panel: np.ndarray, X_normal: np.ndarray,
              t_event: int, lookback: int, unit: str,
              dates_or_idx) -> dict:
    """Two-layer EWS sweep: Layer A (precursor) + Layer B (geometry)."""
    print(f"\n{'='*72}\n  {name}\n{'='*72}")
    T0, N, d = X_normal.shape
    M = MasterOperator.calibrate(X_normal, k=min(4, d), theta=1.0)
    geom = CollapseGeometry(op=M)
    info = InformationGeometry(op=M)
    e_star = info.chi2_threshold(N, d, alpha_conf=0.01)
    ews = EarlyWarning(op=M, geom=geom)

    # ── Layer A: self-calibrate PrecursorScale from the normal period ──────
    print(f"  Calibrating PrecursorScale (T0={T0}, pct=95) ...")
    pre_scale = PrecursorScale.from_panel(M, X_normal, pct=95.0)
    ews.precursor_scale = pre_scale
    print(f"  P95 scales: P={pre_scale.P_scale:.4g}  ψ={pre_scale.psi_scale:.4g}"
          f"  S={pre_scale.S_scale:.4g}  V={pre_scale.V_scale:.4g}")

    # ── Layer B: empirical threshold μ+2σ over the normal period ──────────
    norm_scores = []
    for t in range(1, T0):
        snap_n = Snapshot(X=X_normal[t], X_prev=X_normal[t - 1],
                          history=X_normal[max(0, t - 5): t])
        feat0n = X_normal[max(0, t - T0): t, :, 0]
        net_n  = LedoitWolfNetwork.from_panel(feat0n) if feat0n.shape[0] >= 3 else None
        norm_scores.append(ews.score(snap_n, net_n))
    norm_scores = np.array(norm_scores)
    thresh_closed    = ews.threshold(theta=M.damp.theta, e_star=e_star)
    thresh_empirical = float(norm_scores.mean() + 2.0 * norm_scores.std())
    thresh_B         = min(thresh_closed, thresh_empirical)

    # ── Sweep lookback window ─────────────────────────────────────────────
    t_start = max(1, t_event - lookback)
    history: list = []
    breach_A_t = None   # Layer A first breach
    breach_B_t = None   # Layer B first breach
    snap_prev = None
    for t in range(t_start, t_event + 1):
        snap = Snapshot(X=panel[t], X_prev=panel[t - 1],
                        history=panel[max(0, t - 5): t])
        feat0 = panel[max(0, t - T0): t, :, 0]
        net   = LedoitWolfNetwork.from_panel(feat0) if feat0.shape[0] >= 3 else None

        result = ews.two_layer(snap, net, snap_prev, e_star,
                               geometry_threshold=thresh_B)
        g_alarm = result["geometry_alarm"]
        a_alarm = result["precursor_alarm"]

        history.append(dict(
            t=int(t),
            geometry_score=float(result["geometry_score"]),
            precursor_score=float(result["precursor_score"]),
            geometry_alarm=g_alarm,
            precursor_alarm=a_alarm,
            **{k: float(v) for k, v in result["geometry_signals"].items()},
            **{f"p_{k}": float(v) for k, v in result["precursor_signals"].items()},
        ))
        if breach_A_t is None and a_alarm:
            breach_A_t = t
        if breach_B_t is None and g_alarm:
            breach_B_t = t
        snap_prev = snap

    # ── Report ────────────────────────────────────────────────────────────
    print(f"  Layer B threshold : {thresh_B:.4f}  "
          f"(closed={thresh_closed:.4f}, empirical μ+2σ={thresh_empirical:.4f})")
    print(f"  Layer A threshold : 1.0  (P95-normalised precursor score)")
    print(f"  Lookback          : {lookback} {unit}  "
          f"(t={t_start} … {t_event}  |  event={dates_or_idx(t_event)})")
    for label, bt in (("A — Precursor", breach_A_t), ("B — Geometry", breach_B_t)):
        if bt is None:
            print(f"  Layer {label}: !! No breach in lookback window")
        else:
            lead = t_event - bt
            print(f"  Layer {label}: first breach t={bt} ({dates_or_idx(bt)})"
                  f"  →  lead = {lead} {unit}")

    print(f"  --- last 8 frames ---")
    for h in history[-8:]:
        gf = " G!" if h["geometry_alarm"] else "   "
        af = " A!" if h["precursor_alarm"] else "   "
        print(f"    t={h['t']:4d}  B={h['geometry_score']:.4f}"
              f"  A={h['precursor_score']:.4f}"
              f"  γ={h.get('xi1', 0):.3f}  cosθ={h.get('xi4', 0):.3f}"
              f"{gf}{af}")

    return dict(
        name=name,
        thresh_B=thresh_B, thresh_A=1.0,
        lookback=lookback, unit=unit,
        t_event=int(t_event),
        breach_A_t=None if breach_A_t is None else int(breach_A_t),
        breach_B_t=None if breach_B_t is None else int(breach_B_t),
        lead_A=None if breach_A_t is None else int(t_event - breach_A_t),
        lead_B=None if breach_B_t is None else int(t_event - breach_B_t),
        history=history,
    )


# ─────────────────────────────────── FDIC ───────────────────────────────────
def sweep_fdic():
    import pandas as pd
    cache = ROOT / "research/adaptive-friction/upgraded/fred_cache/fdic_specgrp_quarterly.pkl"
    df = pickle_load(cache).reset_index()                # REPDTE,SPECGRP -> cols
    df = df.rename(columns={"REPDTE": "DATE"})
    feats = ["leverage", "equity_ratio", "npl_ratio", "roa", "int_cost", "nim"]
    # Same construction as run_real_data_simulations.load_fdic
    df = df.sort_values(["DATE", "SPECGRP"]).reset_index(drop=True)
    df["leverage"]     = df["ASSET"] / (df["EQ"] + 1e-9)
    df["equity_ratio"] = df["EQ"] / (df["ASSET"] + 1e-9)
    df["npl_ratio"]    = df["NCLNLS"] / (df["LNLSNET"] + 1e-9)
    df["roa"]          = df["NETINC"] / (df["ASSET"] + 1e-9)
    df["int_cost"]     = df["EINTEXP"] / (df["ASSET"] + 1e-9)
    df["nim"]          = (df["INTINC"] - df["EINTEXP"]) / (df["ASSET"] + 1e-9)
    dates = pd.to_datetime(df["DATE"].unique())
    specgrps = sorted(df["SPECGRP"].unique())
    T = len(dates); N = len(specgrps); d = len(feats)
    panel = np.zeros((T, N, d))
    for ti, dt in enumerate(dates):
        for ni, sg in enumerate(specgrps):
            row = df[(df["DATE"] == dt) & (df["SPECGRP"] == sg)]
            if len(row) == 1:
                panel[ti, ni] = row[feats].values[0]
    panel = np.nan_to_num(panel, nan=0.0, posinf=0.0, neginf=0.0)
    # normalize per-feature
    mu = panel.mean(axis=(0, 1)); sd = panel.std(axis=(0, 1)) + 1e-8
    panel = (panel - mu) / sd
    mask_norm = dates < pd.Timestamp("2007-07-01")
    X_normal  = panel[mask_norm]
    t_event   = int(np.argmin(np.abs(dates - pd.Timestamp("2008-12-31"))))
    return sweep_ews("FDIC (GFC Q4-2008)", panel, X_normal,
                     t_event=t_event, lookback=20, unit="quarters",
                     dates_or_idx=lambda t: (
                         f"{dates[t].year}-Q{(dates[t].month - 1) // 3 + 1}"
                         if hasattr(dates[t], "month") else str(dates[t])
                     ))


def pickle_load(p):
    import pickle
    with open(p, "rb") as f:
        return pickle.load(f)


# ─────────────────────────────────── WB ─────────────────────────────────────
def sweep_wb():
    Y, years, countries, ind = load_worldbank()
    # standardise
    mu = Y.mean(axis=(0, 1)); sd = Y.std(axis=(0, 1)) + 1e-8
    Y = (Y - mu) / sd
    mask_norm = (years < 2007)
    X_normal = Y[mask_norm] if mask_norm.sum() >= 3 else Y[:max(3, len(years)//2)]
    t_event = int(np.argmin(np.abs(years - 2008)))
    return sweep_ews("WORLD BANK (2008 GFC)", Y, X_normal,
                     t_event=t_event, lookback=min(8, t_event), unit="years",
                     dates_or_idx=lambda t: str(int(years[t])))


# ─────────────────────────────────── ERCOT ──────────────────────────────────
def sweep_ercot():
    X, dates, fn = load_ercot()
    T, d = X.shape
    N = 7
    n_weeks = T // N
    X = X[: n_weeks * N]; dates = dates[: n_weeks * N]
    panel = X.reshape(n_weeks, N, d)
    week_dates = dates[::N][:n_weeks]
    # standardise
    mu = panel.mean(axis=(0, 1)); sd = panel.std(axis=(0, 1)) + 1e-8
    panel = (panel - mu) / sd
    mask_norm = week_dates < np.datetime64("2021-01-01")
    X_normal = panel[mask_norm]
    t_event = int(np.argmin(np.abs(week_dates - np.datetime64("2021-02-15"))))
    return sweep_ews("ERCOT (Winter Storm Uri 2021-02-15)", panel, X_normal,
                     t_event=t_event, lookback=12, unit="weeks",
                     dates_or_idx=lambda t: str(week_dates[t]))


# ─────────────────────────────────── PROTEIN ────────────────────────────────
def sweep_protein():
    folded, unfolded = load_protein()
    # combined trajectory: first 100 frames folded, then 100 frames unfolded
    panel = np.concatenate([folded, unfolded], axis=0)             # (T, N, d)
    # standardise
    mu = panel.mean(axis=(0, 1)); sd = panel.std(axis=(0, 1)) + 1e-8
    panel = (panel - mu) / sd
    X_normal = panel[:80]                                          # folded prefix
    t_event = int(panel.shape[0] - 1)                              # last unfolded frame
    return sweep_ews("PROTEIN β-hairpin (T_melt cross)", panel, X_normal,
                     t_event=t_event, lookback=80, unit="frames",
                     dates_or_idx=lambda t: f"frame {t}")


# ────────────────────────────────────────────────────────────────────────────
def main():
    out = {}
    for fn in (sweep_fdic, sweep_wb, sweep_ercot, sweep_protein):
        try:
            r = fn()
            out[r["name"]] = r
        except Exception as exc:
            import traceback
            print(f"!! {fn.__name__} FAILED: {exc}")
            traceback.print_exc()
    out_path = Path(__file__).parent / "ews_leadtime_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
