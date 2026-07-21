# -*- coding: utf-8 -*-
"""
canonical_early_warning_all_domains.py
======================================
Apply the locked Canonical Dynamical Geometry System v4 as an early-warning
alarm engine across five fields:

  1. G-SIB / World Bank + FDIC bank panel
  2. FDIC sector panel
  3. Protein B-factor profiles
  4. Supply-chain disruption simulations
  5. ERCOT demand + supply concatenated hourly panel

This is not the prior trading-brake sweep.  It uses the canonical objects
from canonical_system_v4.tex directly:

  S(X) = z-scored state residual against a reference/normal window
  G    = regularised inverse covariance of S in the reference window
  E    = S^T G S
  g_X  = 2 G S                         (J = I in standardised coordinates)
  gamma = E/(E + theta)
  F    = F_base - g_X, F_base=-alpha*S
  Xdot = F - gamma * <F,g_X>/||g_X||^2 * g_X

The alarm protocol follows the gap-closure G5 idea: report event-wise first
alarm inside a finite pre-crisis window, lead time, hit-rate, false-positive
rate, and false alarms per 1,000 non-crisis steps.

Outputs:
  results/canonical_early_warning_all_domains/summary.json
  results/canonical_early_warning_all_domains/domain_results.csv
  figures/canonical_early_warning_all_domains.png
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

THIS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(THIS, "..", ".."))
sys.path.insert(0, THIS)
sys.path.insert(0, os.path.abspath(os.path.join(THIS, "..", "adaptive-friction", "banklevel_enhanced")))
sys.path.insert(0, os.path.abspath(os.path.join(THIS, "..", "adaptive-friction", "upgraded")))
sys.path.insert(0, os.path.abspath(os.path.join(THIS, "..", "supply-chain")))

OUTDIR = os.path.join(THIS, "results", "canonical_early_warning_all_domains")
FIGDIR = os.path.join(THIS, "figures")
os.makedirs(OUTDIR, exist_ok=True)
os.makedirs(FIGDIR, exist_ok=True)

EPS = 1e-10
ALPHA_BASE = 0.05
K_SIGMA = 2.0
KAPPA_MAX = 10.0


@dataclass
class DomainPanel:
    name: str
    X: np.ndarray                  # (T, d)
    labels: list[str]              # time/residue labels
    step_unit: str                 # q, h, d, step, residue
    ref_mask: np.ndarray           # normal/calibration mask
    events: dict[str, int]         # event onset index
    crisis_windows: dict[str, tuple[int, int]]  # inclusive start, exclusive end
    max_pre: int
    feature_names: list[str]
    note: str = ""


class CanonicalAlarm:
    """Transparent canonical-v4 alarm in standardised coordinates (J=I)."""

    def __init__(self, alpha_base: float = ALPHA_BASE, k_sigma: float = K_SIGMA,
                 kappa_max: float = KAPPA_MAX):
        self.alpha_base = float(alpha_base)
        self.k_sigma = float(k_sigma)
        self.kappa_max = float(kappa_max)

    def fit(self, X_ref: np.ndarray) -> "CanonicalAlarm":
        X_ref = np.asarray(X_ref, dtype=float)
        self.mu_ = np.nanmean(X_ref, axis=0)
        self.sd_ = np.nanstd(X_ref, axis=0) + EPS
        Z = np.nan_to_num((X_ref - self.mu_[None, :]) / self.sd_[None, :])
        cov = np.cov(Z, rowvar=False)
        cov = np.atleast_2d(cov)
        if cov.shape == (1, 1):
            cov = cov + 1e-6
        eig = np.linalg.eigvalsh(cov + 1e-12 * np.eye(cov.shape[0]))
        lam_min = float(max(eig.min(), 1e-12))
        lam_max = float(max(eig.max(), lam_min))
        kappa_raw = lam_max / lam_min
        # Gap G7 regularisation: target covariance conditioning <= kappa_max.
        if kappa_raw > self.kappa_max:
            ridge = (lam_max - self.kappa_max * lam_min) / (self.kappa_max - 1.0)
        else:
            ridge = 0.0
        ridge = max(float(ridge), 1e-8)
        cov_reg = cov + ridge * np.eye(cov.shape[0])
        self.G_ = np.linalg.pinv(cov_reg)
        self.kappa_raw_ = kappa_raw
        self.kappa_reg_ = float(np.linalg.cond(cov_reg))
        self.ridge_ = ridge
        E_ref = self._energy(Z)
        self.theta_ = float(np.percentile(E_ref, 75) + EPS)
        self.threshold_ = float(np.mean(E_ref) + self.k_sigma * (np.std(E_ref) + EPS))
        self.ref_mean_ = float(np.mean(E_ref))
        self.ref_std_ = float(np.std(E_ref) + EPS)
        return self

    def _Z(self, X: np.ndarray) -> np.ndarray:
        return np.nan_to_num((np.asarray(X, dtype=float) - self.mu_[None, :]) / self.sd_[None, :])

    def _energy(self, Z: np.ndarray) -> np.ndarray:
        return np.einsum("ij,ij->i", Z, Z @ self.G_)

    def evaluate(self, X: np.ndarray) -> dict[str, np.ndarray | float]:
        Z = self._Z(X)
        E = self._energy(Z)
        GS = Z @ self.G_
        gx = 2.0 * GS
        Fbase = -self.alpha_base * Z
        F = Fbase - gx
        g_norm = np.linalg.norm(gx, axis=1) + EPS
        F_norm = np.linalg.norm(F, axis=1) + EPS
        dot_fg = np.einsum("ij,ij->i", F, gx)
        gamma = E / (E + self.theta_)
        coeff = dot_fg / (g_norm ** 2 + EPS)
        Xdot = F - (gamma * coeff)[:, None] * gx
        Edot_model = np.einsum("ij,ij->i", gx, Xdot)
        dZ = np.vstack([np.zeros((1, Z.shape[1])), np.diff(Z, axis=0)])
        Edot_obs = np.einsum("ij,ij->i", gx, dZ)
        cos_theta = np.clip(dot_fg / (F_norm * g_norm), -1, 1)
        delta_C = np.abs(gamma * coeff) * g_norm
        delta_A = g_norm
        delta_T = np.abs(Edot_obs)
        delta_G = np.max(Z * Z, axis=1)
        alarms = E > self.threshold_
        return dict(E=E, gamma=gamma, g_norm=g_norm, F_norm=F_norm,
                    Edot_model=Edot_model, Edot_obs=Edot_obs,
                    cos_theta=cos_theta, delta_C=delta_C, delta_A=delta_A,
                    delta_T=delta_T, delta_G=delta_G, threshold=self.threshold_,
                    alarms=alarms)


def _fill_nan(X: np.ndarray) -> np.ndarray:
    X = np.asarray(X, dtype=float).copy()
    for j in range(X.shape[1]):
        col = X[:, j]
        if np.isnan(col).any():
            med = float(np.nanmedian(col)) if np.isfinite(np.nanmedian(col)) else 0.0
            col[np.isnan(col)] = med
            X[:, j] = col
    return X


def _mask_windows(T: int, windows: dict[str, tuple[int, int]], pad_pre: int = 0) -> np.ndarray:
    mask = np.zeros(T, dtype=bool)
    for s, e in windows.values():
        mask[max(0, s - pad_pre):min(T, e)] = True
    return mask


def _event_metrics(panel: DomainPanel, out: dict[str, Any]) -> list[dict[str, Any]]:
    E = np.asarray(out["E"])
    alarms = np.asarray(out["alarms"], dtype=bool)
    T = len(E)
    all_crisis = _mask_windows(T, panel.crisis_windows, pad_pre=0)
    # Exclude all crisis windows and all pre-warning windows from FP denominator.
    excluded = _mask_windows(T, panel.crisis_windows, pad_pre=panel.max_pre)
    normal_den = ~excluded
    far_global = float(alarms[normal_den].mean()) if normal_den.any() else float("nan")
    fp_per_1000 = float(1000.0 * alarms[normal_den].sum() / max(1, normal_den.sum()))
    rows = []
    for ev, onset in panel.events.items():
        win = panel.crisis_windows[ev]
        s, e = win
        lo = max(0, onset - panel.max_pre)
        pre = np.where(alarms[lo:onset])[0]
        inside = np.where(alarms[onset:e])[0]
        if len(pre):
            alarm_idx = int(lo + pre[0])
            lead = int(onset - alarm_idx)
            timing = "before"
        elif len(inside):
            alarm_idx = int(onset + inside[0])
            lead = -int(alarm_idx - onset)
            timing = "inside"
        else:
            alarm_idx = None
            lead = None
            timing = "miss"
        event_mask = np.zeros(T, dtype=bool)
        event_mask[s:e] = True
        hr = float(alarms[event_mask].mean()) if event_mask.any() else float("nan")
        peak_lo = max(0, onset - panel.max_pre)
        peak_hi = min(T, e + panel.max_pre // 2)
        peak_idx = int(peak_lo + np.argmax(E[peak_lo:peak_hi])) if peak_hi > peak_lo else onset
        rows.append(dict(
            domain=panel.name, event=ev, onset_idx=int(onset), onset_label=panel.labels[onset],
            alarm_idx=alarm_idx, alarm_label=(panel.labels[alarm_idx] if alarm_idx is not None else None),
            lead=lead, step_unit=panel.step_unit, timing=timing,
            hit_rate=hr, far=far_global, fp_per_1000=fp_per_1000,
            peak_idx=peak_idx, peak_label=panel.labels[peak_idx], peak_E=float(E[peak_idx]),
            threshold=float(out["threshold"]), crisis_start=s, crisis_end=e,
        ))
    return rows


# ---------------------------------------------------------------------------
# Domain loaders
# ---------------------------------------------------------------------------
def load_gsib() -> DomainPanel:
    from gsib_loader_real import build_gsib_panel_real, FEATURE_NAMES
    panel = build_gsib_panel_real(verbose=False)
    X = _fill_nan(np.nanmean(panel["X"], axis=1))
    dates = pd.DatetimeIndex(panel["dates"])
    events_dt = {
        "GFC": pd.Timestamp("2008-09-30"),
        "Euro": pd.Timestamp("2011-09-30"),
        "COVID": pd.Timestamp("2020-03-31"),
        "SVB": pd.Timestamp("2023-03-31"),
    }
    windows_dt = {
        "GFC": (pd.Timestamp("2008-09-30"), pd.Timestamp("2009-06-30")),
        "Euro": (pd.Timestamp("2011-09-30"), pd.Timestamp("2012-06-30")),
        "COVID": (pd.Timestamp("2020-03-31"), pd.Timestamp("2020-09-30")),
        "SVB": (pd.Timestamp("2023-03-31"), pd.Timestamp("2023-09-30")),
    }
    events = {k: int(np.searchsorted(dates, v)) for k, v in events_dt.items()}
    windows = {k: (int(np.searchsorted(dates, a)), min(len(dates), int(np.searchsorted(dates, b)) + 1)) for k, (a, b) in windows_dt.items()}
    ref = np.asarray(dates < pd.Timestamp("2008-01-01"))
    return DomainPanel("gsib", X, [str(d.date()) for d in dates], "q", ref, events, windows, 8, list(FEATURE_NAMES),
                       "G-SIB cross-sectional mean; reference pre-2008")


def load_fdic() -> DomainPanel:
    from fdic_loader import fetch_fdic_specgrp, compute_sector_features, build_panel, FEATURE_NAMES
    from fred_loader import fetch_all as fetch_fred_all
    fred = fetch_fred_all(use_cache=True, verbose=False)["slope_10y2y"]
    fdic = fetch_fdic_specgrp(start="1990-01-01", end="2024-12-31", use_cache=True, verbose=False)
    sector_features = compute_sector_features(fdic, fred)
    X3, dates, sectors = build_panel(sector_features)
    dates = pd.DatetimeIndex(dates)
    X = _fill_nan(np.nanmean(X3, axis=1))
    events_dt = {
        "GFC": pd.Timestamp("2008-09-30"),
        "Euro": pd.Timestamp("2011-09-30"),
        "COVID": pd.Timestamp("2020-03-31"),
        "SVB": pd.Timestamp("2023-03-31"),
    }
    windows_dt = {
        "GFC": (pd.Timestamp("2008-09-30"), pd.Timestamp("2009-06-30")),
        "Euro": (pd.Timestamp("2011-09-30"), pd.Timestamp("2012-06-30")),
        "COVID": (pd.Timestamp("2020-03-31"), pd.Timestamp("2020-09-30")),
        "SVB": (pd.Timestamp("2023-03-31"), pd.Timestamp("2023-09-30")),
    }
    events = {k: int(np.searchsorted(dates, v)) for k, v in events_dt.items()}
    windows = {k: (int(np.searchsorted(dates, a)), min(len(dates), int(np.searchsorted(dates, b)) + 1)) for k, (a, b) in windows_dt.items()}
    ref = np.asarray(dates < pd.Timestamp("2008-01-01"))
    return DomainPanel("fdic", X, [str(d.date()) for d in dates], "q", ref, events, windows, 8, list(FEATURE_NAMES),
                       "FDIC SPECGRP sector mean + FRED slope; reference pre-2008")


def load_protein_all() -> list[DomainPanel]:
    from domain_v2_protein import PDB_IDS, fetch_pdb_bfactors, bfactors_to_state_matrix, CRISIS_B_ZSCORE, REF_B_FRACTION
    panels = []
    prior_path = os.path.join(THIS, "results", "domain_v2_protein.json")
    prior = {}
    if os.path.exists(prior_path):
        with open(prior_path) as f:
            raw = json.load(f)
        prior = {r["pdb_id"]: np.asarray(r["bfactors"], dtype=float) for r in raw.get("proteins", []) if "bfactors" in r}
    for pdb in PDB_IDS:
        data = fetch_pdb_bfactors(pdb)
        if data is not None:
            bf = np.asarray(data["bfactors"], dtype=float)
        elif pdb in prior:
            bf = prior[pdb]
        else:
            print(f"  [WARN] no protein data for {pdb}; skipped")
            continue
        X = _fill_nan(bfactors_to_state_matrix(bf))
        ref_cut = np.percentile(bf, REF_B_FRACTION * 100)
        ref = bf <= ref_cut
        crisis = bf > (bf.mean() + CRISIS_B_ZSCORE * bf.std())
        idxs = np.where(crisis)[0]
        if len(idxs) == 0:
            continue
        # contiguous hot-residue runs as events
        runs = []
        start = prev = int(idxs[0])
        for ix in map(int, idxs[1:]):
            if ix == prev + 1:
                prev = ix
            else:
                runs.append((start, prev + 1)); start = prev = ix
        runs.append((start, prev + 1))
        events = {f"hot_region_{i+1}": s for i, (s, e) in enumerate(runs)}
        windows = {f"hot_region_{i+1}": (s, e) for i, (s, e) in enumerate(runs)}
        panels.append(DomainPanel(f"protein_{pdb}", X, [f"res_{i+1}" for i in range(len(bf))], "residue", ref, events, windows, 20,
                                  ["B_raw", "B_z", "B_roll_mean", "B_roll_std", "B_gradient"],
                                  "Protein labels are B-factor hot residues; useful as structural proxy, not independent biology."))
    return panels


def load_supply_chain_all() -> list[DomainPanel]:
    from scenarios import ALL_SCENARIOS
    from supply_chain_engine import run_simulation
    panels = []
    for name, fn in ALL_SCENARIOS.items():
        network, disruptions, meta = fn()
        result = run_simulation(network, disruptions, n_steps=200, eta=0.02, mode="none",
                                buffer_level=0.2, cascade_rate=0.15, seed=42, verbose=False)
        mean_health = np.mean(result["node_health"], axis=1)
        X = np.column_stack([
            result["energy"], result["mfls"], result["lambda_max"], result["gamma_star"],
            result["cascade_depth"], mean_health,
            result["channels"]["camouflage"], result["channels"]["feature_gap"],
            result["channels"]["activity"], result["channels"]["temporal_novelty"],
        ])
        X = _fill_nan(X)
        first_onset = min(d.onset_step for d in disruptions)
        ref = np.arange(len(X)) < max(20, first_onset - 12)
        events = {d.name: int(d.onset_step) for d in disruptions}
        windows = {d.name: (int(d.onset_step), min(len(X), int(d.onset_step + d.duration))) for d in disruptions}
        panels.append(DomainPanel(f"supply_{name}", X, [str(i) for i in range(len(X))], "step", ref, events, windows, 30,
                                  ["energy", "mfls", "lambda_max", "gamma_star", "cascade_depth", "mean_health", "delta_C", "delta_G", "delta_A", "delta_T"],
                                  f"{meta['name']} — simulated no-intervention field dynamics"))
    return panels


def load_ercot_combined() -> DomainPanel:
    data_dir = r"C:\amttp\data\ercot"
    # Prefer explicit demand+supply concatenation so the requested construction is exact.
    dem = np.load(os.path.join(data_dir, "ercot_demand_hourly.npz"), allow_pickle=True)
    sup = np.load(os.path.join(data_dir, "ercot_supply_hourly.npz"), allow_pickle=True)
    dates_d = pd.to_datetime(dem["dates"])
    dates_s = pd.to_datetime(sup["dates"])
    if len(dates_d) != len(dates_s) or not np.all(dates_d == dates_s):
        common = pd.Index(dates_d).intersection(pd.Index(dates_s))
        id_d = pd.Index(dates_d).get_indexer(common)
        id_s = pd.Index(dates_s).get_indexer(common)
        X = np.column_stack([dem["X"][id_d], sup["X"][id_s]])
        dates = pd.DatetimeIndex(common)
        y = np.maximum(dem["y"][id_d], sup["y"][id_s])
    else:
        X = np.column_stack([dem["X"], sup["X"]])
        dates = pd.DatetimeIndex(dates_d)
        y = np.maximum(dem["y"], sup["y"])
    X = _fill_nan(X)
    feature_names = ["demand_" + str(x) for x in dem["feature_names"]] + ["supply_" + str(x) for x in sup["feature_names"]]
    ev_raw = json.loads(str(dem["event_onsets"])) if "event_onsets" in dem.files else {}
    events = {k: int(np.searchsorted(dates, pd.Timestamp(v))) for k, v in ev_raw.items()}
    windows = {}
    for k, s in events.items():
        windows[k] = (s, min(len(X), s + 240))  # 10 days after onset
    # Normal = 2019 outside labelled crisis hours, consistent with existing ERCOT scripts.
    ref = np.asarray((dates.year == 2019) & (np.asarray(y) == 0))
    return DomainPanel("ercot_demand_supply_hourly", X, [str(d)[:16] for d in dates], "h", ref, events, windows, 720,
                       list(feature_names), "ERCOT demand and supply hourly features concatenated; normal window = non-crisis 2019")


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------
def analyse_panel(panel: DomainPanel) -> dict[str, Any]:
    if panel.ref_mask.sum() < max(5, panel.X.shape[1] + 1):
        # fallback: earliest 25% if an explicit reference is too short
        ref = np.zeros(len(panel.X), dtype=bool)
        ref[:max(10, len(panel.X) // 4)] = True
        panel.ref_mask = ref
    engine = CanonicalAlarm().fit(panel.X[panel.ref_mask])
    out = engine.evaluate(panel.X)
    metrics = _event_metrics(panel, out)
    all_crisis = _mask_windows(len(panel.X), panel.crisis_windows, pad_pre=0)
    channels = {
        "delta_C": float(np.mean(np.asarray(out["delta_C"])[all_crisis])) if all_crisis.any() else 0.0,
        "delta_A": float(np.mean(np.asarray(out["delta_A"])[all_crisis])) if all_crisis.any() else 0.0,
        "delta_T": float(np.mean(np.asarray(out["delta_T"])[all_crisis])) if all_crisis.any() else 0.0,
        "delta_G": float(np.mean(np.asarray(out["delta_G"])[all_crisis])) if all_crisis.any() else 0.0,
    }
    s = sum(channels.values()) + EPS
    ch_dom = {k: v / s for k, v in channels.items()}
    summary = dict(
        domain=panel.name, T=int(panel.X.shape[0]), d=int(panel.X.shape[1]),
        ref_n=int(panel.ref_mask.sum()), step_unit=panel.step_unit,
        threshold=float(out["threshold"]), ref_E_mean=engine.ref_mean_, ref_E_std=engine.ref_std_,
        kappa_cov_raw=engine.kappa_raw_, kappa_cov_reg=engine.kappa_reg_, ridge=engine.ridge_,
        n_alarms=int(np.asarray(out["alarms"]).sum()), alarm_rate=float(np.asarray(out["alarms"]).mean()),
        channel_dominance=ch_dom, events=metrics, note=panel.note,
    )
    return dict(panel=panel, out=out, summary=summary, event_rows=metrics)


def main() -> None:
    t0 = time.time()
    print("=" * 100)
    print("  Canonical v4 early-warning across GSIB, FDIC, protein, supply chain, ERCOT")
    print("=" * 100)

    panels: list[DomainPanel] = []
    for loader in [load_gsib, load_fdic, load_ercot_combined]:
        try:
            p = loader()
            panels.append(p)
            print(f"  loaded {p.name}: T={p.X.shape[0]}, d={p.X.shape[1]}, events={len(p.events)}")
        except Exception as e:
            print(f"  [WARN] failed loader {loader.__name__}: {e}")
    try:
        ps = load_protein_all(); panels.extend(ps)
        for p in ps:
            print(f"  loaded {p.name}: T={p.X.shape[0]}, d={p.X.shape[1]}, events={len(p.events)}")
    except Exception as e:
        print(f"  [WARN] failed protein loader: {e}")
    try:
        ss = load_supply_chain_all(); panels.extend(ss)
        for p in ss:
            print(f"  loaded {p.name}: T={p.X.shape[0]}, d={p.X.shape[1]}, events={len(p.events)}")
    except Exception as e:
        print(f"  [WARN] failed supply-chain loader: {e}")

    results = []
    rows = []
    for panel in panels:
        print(f"\n[analyse] {panel.name}")
        r = analyse_panel(panel)
        results.append(r)
        rows.extend(r["event_rows"])
        summ = r["summary"]
        print(f"  alarms={summ['n_alarms']}/{summ['T']} ({summ['alarm_rate']:.3f}), "
              f"kappa raw/reg={summ['kappa_cov_raw']:.1f}/{summ['kappa_cov_reg']:.1f}")
        for ev in summ["events"]:
            lead_s = "miss" if ev["lead"] is None else f"{ev['lead']:+d}{ev['step_unit']}"
            print(f"    {ev['event']:<28} alarm={ev['alarm_label']} lead={lead_s} "
                  f"HR={ev['hit_rate']:.2f} FAR={ev['far']:.3f} FP/1000={ev['fp_per_1000']:.1f}")

    # JSON + CSV
    json_summary = {r["summary"]["domain"]: r["summary"] for r in results}
    with open(os.path.join(OUTDIR, "summary.json"), "w") as f:
        json.dump(json_summary, f, indent=2, default=str)
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUTDIR, "domain_results.csv"), index=False)
    print(f"\n  -> {os.path.join(OUTDIR, 'summary.json')}")
    print(f"  -> {os.path.join(OUTDIR, 'domain_results.csv')}")

    # Figure: one row per domain group, plot E with alarms and crisis shading.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = len(results)
    fig, axes = plt.subplots(n, 1, figsize=(14, max(3.0 * n, 8)), squeeze=False)
    axes = axes[:, 0]
    for ax, r in zip(axes, results):
        p = r["panel"]; out = r["out"]
        E = np.asarray(out["E"]); alarms = np.asarray(out["alarms"], dtype=bool)
        x = np.arange(len(E))
        ax.plot(x, E, color="navy", lw=1.0, label="canonical E")
        ax.axhline(float(out["threshold"]), color="gray", ls="--", lw=0.8, label="μ+2σ threshold")
        for ev, (s, e) in p.crisis_windows.items():
            ax.axvspan(s, e, color="red", alpha=0.15)
            ax.axvline(p.events[ev], color="red", alpha=0.4, lw=0.7)
        idx = np.where(alarms)[0]
        if len(idx):
            ax.scatter(idx, E[idx], color="orange", s=10, zorder=3, label="alarm")
        ax.set_title(f"{p.name}  |  T={len(E)} d={p.X.shape[1]}  ref={p.ref_mask.sum()}  unit={p.step_unit}", fontsize=9)
        ax.set_ylabel("E")
        ax.grid(True, alpha=0.25)
    axes[-1].set_xlabel("index")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", fontsize=8)
    fig.tight_layout(rect=[0, 0, 0.96, 1])
    png = os.path.join(FIGDIR, "canonical_early_warning_all_domains.png")
    fig.savefig(png, dpi=120)
    plt.close(fig)
    print(f"  -> {png}")
    print(f"\nDone in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
