"""Frozen-Normal-Window Simulation — SIAM paper §7 protocol.

Protocol (no lookahead):
  1. Fix a pre-crisis reference / normal window [t0, t_cut).
  2. Calibrate MasterOperator ONCE on X_normal = X[t0:t_cut].  FROZEN — never re-fit.
  3. Standardise the FULL panel using normal-window statistics only.
  4. Roll t = t_cut … T-1 forward.
     At each t compute §I-XXVII diagnostics from
       snap = Snapshot(X=X[t], X_prev=X[t-1], history=X[max(0,t-H):t])
     with the frozen MasterOperator.  No future data touches the calibration.
  5. EWS alarm threshold = μ_normal + 2σ_normal of in-window EWS scores
     (computed from the normal-period scores, not from future data).
  6. Lead time = t_crisis_onset − t_first_alarm  (positive = precedes crisis).

Datasets
--------
FDIC        : 140 quarters 1990-Q1 → 2024-Q4  (N=7 SPECGRP types × d=6 ratios)
              normal 1994-Q1 → 2003-Q4 (40 quarters), crisis = GFC 2007-Q4
GSIB        : World Bank G-SIB 8-country panel (annual)
              normal ≤ 2003, crisis = 2008
ERCOT       : Daily ERCOT data 2018-2022 → weekly panel (N=7, d=6)
              normal < 2021-01-01, crisis = 2021-02-15 (Winter Storm Uri)
TerraLuna   : 65-agent DPD hourly 168-step simulation of the May 2022 collapse
              normal hours 0-22 (pre-attack), crisis = hour 24 (first attack)

Output
------
  frozen_normal_results.json          — full per-step scalar records
  frozen_normal_timeline.txt          — human-readable lead-time table
"""
from __future__ import annotations
import json
import os
import pickle
import sys
import time
from pathlib import Path

# Force UTF-8 output so box-drawing characters survive Windows cp1252 terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np

ROOT   = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "adaptive-friction"))

from collapse_geometry import (
    MasterOperator, Snapshot, LedoitWolfNetwork,
    LyapunovCertificate, CollapseGeometry, EarlyWarning, PrecursorScale,
    InformationGeometry,
)

# ═══════════════════════════════════════════════════════════════════════
# Core rolling-diagnostics engine
# ═══════════════════════════════════════════════════════════════════════

def frozen_normal_scan(
    name: str,
    X_all: np.ndarray,          # (T, N, d) full panel — already standardised
    t_normal_end: int,          # exclusive index: calibration uses X_all[:t_normal_end]
    t_eval_start: int,          # first evaluation index (≥ t_normal_end)
    crisis_onset_idx: int,      # index of the first crisis period
    period_labels: list[str],   # length T — human-readable period names
    history_len: int = 20,
    n_sigma_threshold: float = 2.0,
) -> dict:
    """Run the frozen-normal protocol and return a results dict."""
    T, N, d = X_all.shape
    print(f"\n{'═'*72}")
    print(f"  {name}")
    print(f"{'═'*72}")
    print(f"  Panel         : T={T}  N={N}  d={d}")
    print(f"  Normal window : [{period_labels[0]} … {period_labels[t_normal_end-1]}]"
          f"  ({t_normal_end} periods)")
    print(f"  Eval window   : [{period_labels[t_eval_start]} … {period_labels[-1]}]"
          f"  ({T - t_eval_start} periods)")
    print(f"  Crisis onset  : {period_labels[crisis_onset_idx]}")

    # ── 1. Calibrate on frozen normal window ────────────────────────────
    X_normal = X_all[:t_normal_end]
    M = MasterOperator.calibrate(X_normal, k=min(4, d), theta=1.0)
    net = LedoitWolfNetwork.from_panel(X_normal[..., 0])
    info = InformationGeometry(op=M)
    e_star = info.chi2_threshold(N, d, alpha_conf=0.01)
    geom = CollapseGeometry(op=M)
    lyap = LyapunovCertificate(op=M)
    ews = EarlyWarning(op=M, geom=geom)
    # Self-calibrate Layer A from frozen normal window (P95 per signal — domain-agnostic)
    ews.precursor_scale = PrecursorScale.from_panel(M, X_normal)
    ews_thresh_fixed = ews.threshold(theta=M.damp.theta, e_star=e_star)
    print(f"  e* (χ²)       : {e_star:.2f}    EWS_thresh(fixed)={ews_thresh_fixed:.4f}")
    print(f"  PrecursorScale: P={ews.precursor_scale.P_scale:.4f}  "
          f"ψ={ews.precursor_scale.psi_scale:.4f}  "
          f"S={ews.precursor_scale.S_scale:.4f}  "
          f"V={ews.precursor_scale.V_scale:.4f}")

    # ── 2. Score the normal window to get Layer-B μ±σ dynamic threshold ─
    normal_ews = []
    for t in range(1, t_normal_end):
        snap = Snapshot(X=X_all[t], X_prev=X_all[t - 1],
                        history=X_all[max(0, t - history_len): t])
        try:
            normal_ews.append(ews.score(snap, net))
        except Exception:
            pass
    mu_n = float(np.nanmean(normal_ews)) if normal_ews else 0.0
    sd_n = float(np.nanstd(normal_ews))  if normal_ews else 1.0
    if sd_n < 1e-10:
        sd_n = 1e-10
    ews_thresh_dynamic = mu_n + n_sigma_threshold * sd_n
    print(f"  EWS normal    : μ={mu_n:.4f}  σ={sd_n:.4f}  "
          f"dynamic threshold (μ+{n_sigma_threshold:.0f}σ)={ews_thresh_dynamic:.4f}")

    # ── 3. Roll forward through evaluation window ────────────────────────
    records: list[dict] = []
    first_alarm_idx: int | None = None

    for t in range(t_eval_start, T):
        if t == 0:
            continue
        snap = Snapshot(X=X_all[t], X_prev=X_all[t - 1],
                        history=X_all[max(0, t - history_len): t])
        rec: dict = {"period": period_labels[t], "t": t,
                     "is_crisis": t >= crisis_onset_idx}
        snap_prev = Snapshot(
            X=X_all[t - 1],
            X_prev=X_all[t - 2] if t > 1 else X_all[t - 1],
            history=X_all[max(0, t - 1 - history_len): t - 1],
        ) if t >= 2 else None
        try:
            rec["e_BSDT"]          = float(M.damp.e_BSDT(snap))
            rec["gamma_star"]      = float(M.damp.gamma_star(snap))
            rec["MFLS_state"]      = float(M.mfls.state_mfls(snap))
            rec["MFLS_channel"]    = float(M.mfls.channel_mfls(snap))
            rec["rho_MFLS"]        = float(M.mfls.rho_mfls(snap))
            rec["psi"]             = float(M.mfls.psi(snap))
            rec["cos_theta_state"] = float(geom.cos_theta_state(snap))
            rec["cos_theta_chan"]   = float(geom.cos_theta_channel(snap))
            cond = geom.all_conditions(snap)
            rec["spectral"]        = bool(cond["spectral"])
            rec["angular"]         = bool(cond["angular"])
            rec["energetic"]       = bool(cond["energetic"])
            rec["dV_dt"]           = float(lyap.dV_dt(snap))
            rec["margin"]          = float(lyap.margin(snap))
            # ── two-layer self-calibrated alarm (Layer A=precursor, Layer B=geometry)
            tl = ews.two_layer(snap, net, snap_prev, e_star,
                               geometry_threshold=ews_thresh_dynamic)
            rec["EWS"]             = tl["geometry_score"]
            rec["precursor_score"] = tl["precursor_score"]
            rec["alarm_layer"]     = tl["layer"]          # "A", "B", "AB", or ""
            rec["alarm_dynamic"]   = tl["alarm"]          # Layer A OR B
            rec["alarm_A"]         = tl["precursor_alarm"] # Layer A alone
            rec["alarm_B"]         = tl["geometry_alarm"]  # Layer B alone
            rec["alarm_fixed"]     = rec["EWS"] > ews_thresh_fixed
            rec["xi"] = [float(v) for v in tl["geometry_signals"].values()]
        except Exception as exc:
            rec["error"] = str(exc)

        records.append(rec)

        # Track first pre-crisis alarm (Layer A fires earliest)
        if (first_alarm_idx is None
                and rec.get("alarm_dynamic", False)
                and t < crisis_onset_idx):
            first_alarm_idx = t

    # ── 4. Lead-time summary ─────────────────────────────────────────────
    lead_time: int | None = None
    alarm_label: str | None = None
    if first_alarm_idx is not None:
        lead_time = crisis_onset_idx - first_alarm_idx
        alarm_label = period_labels[first_alarm_idx]

    # Score at crisis onset
    onset_rec = next((r for r in records if r["t"] == crisis_onset_idx), None)

    print(f"  ── Results ──────────────────────────────────────────────────")
    if lead_time is not None:
        first_rec = next((r for r in records if r["t"] == first_alarm_idx), None)
        layer_tag = first_rec.get("alarm_layer", "?") if first_rec else "?"
        print(f"  FIRST PRE-CRISIS ALARM : {alarm_label}  "
              f"(lead = {lead_time} periods before {period_labels[crisis_onset_idx]})  "
              f"Layer={layer_tag}")
    else:
        print(f"  NO pre-crisis alarm fired (dynamic threshold={ews_thresh_dynamic:.4f})")
    if onset_rec and "EWS" in onset_rec:
        print(f"  At crisis onset ({period_labels[crisis_onset_idx]}): "
              f"EWS={onset_rec['EWS']:.4f}  precursor={onset_rec.get('precursor_score','?'):.4f}  "
              f"e_BSDT={onset_rec.get('e_BSDT','?'):.4f}  "
              f"γ*={onset_rec.get('gamma_star','?'):.4f}  "
              f"ψ={onset_rec.get('psi','?'):.4f}  "
              f"cos_θ_state={onset_rec.get('cos_theta_state','?'):+.4f}")
    print(f"  EWS trajectory (eval window, every 5 steps):")
    for r in records[::max(1, len(records)//20)]:
        layer = r.get('alarm_layer', '')
        bar = f"[{layer or ' '}]" if r.get("alarm_dynamic") else ("[B]" if r.get("alarm_fixed") else "[ ]")
        crisis_mark = "<-- CRISIS" if r["t"] == crisis_onset_idx else ""
        print(f"    t={r['t']:3d}  {r['period']:<18s}  "
              f"EWS={r.get('EWS', float('nan')):6.4f}  "
              f"pre={r.get('precursor_score', float('nan')):5.3f}  "
              f"e={r.get('e_BSDT', float('nan')):7.3f}  "
              f"{bar} {crisis_mark}")

    return {
        "name": name,
        "N": N, "d": d,
        "t_normal_end": t_normal_end,
        "t_eval_start": t_eval_start,
        "crisis_onset_idx": crisis_onset_idx,
        "crisis_label": period_labels[crisis_onset_idx],
        "ews_thresh_dynamic": ews_thresh_dynamic,
        "ews_thresh_fixed": ews_thresh_fixed,
        "e_star": float(e_star),
        "lead_time_periods": lead_time,
        "first_alarm_label": alarm_label,
        "normal_ews_mu": mu_n,
        "normal_ews_sd": sd_n,
        "records": records,
    }


# ═══════════════════════════════════════════════════════════════════════
# Dataset loaders
# ═══════════════════════════════════════════════════════════════════════

def load_fdic_panel() -> tuple[np.ndarray, list[str]]:
    """Returns (T,N,d) panel + period labels. Standardised by normal-window stats."""
    pkl = ROOT / "research/adaptive-friction/upgraded/fred_cache/fdic_specgrp_quarterly.pkl"
    import pandas as pd
    df = pickle.load(open(pkl, "rb"))
    cols = ["ASSET", "LNLSNET", "EQ", "NETINC", "EINTEXP", "INTINC", "NCLNLS"]
    dates = sorted(df.index.get_level_values("REPDTE").unique())
    grps  = sorted(df.index.get_level_values("SPECGRP").unique())
    T, N, d_raw = len(dates), len(grps), len(cols)
    X = np.zeros((T, N, d_raw))
    for t, dt in enumerate(dates):
        for n, g in enumerate(grps):
            try:
                X[t, n] = df.loc[(dt, g), cols].to_numpy(dtype=float)
            except KeyError:
                X[t, n] = np.nan
    A = X[..., 0] + 1e-9
    L = X[..., 1] + 1e-9
    Y = np.stack([
        X[..., 1] / A,
        X[..., 2] / A,
        X[..., 6] / L,
        X[..., 3] / A,
        X[..., 4] / A,
        (X[..., 5] - X[..., 4]) / A,
    ], axis=-1)
    Y = np.nan_to_num(Y, nan=0.0, posinf=0.0, neginf=0.0)
    dts = pd.to_datetime(dates)
    labels = [d.strftime("%Y-Q") + str((d.month - 1) // 3 + 1) for d in dts]
    # Normal: 1994-Q1 … 2003-Q4 per SIAM §7 (40 quarters)
    t_cut   = int(np.sum(dts < pd.Timestamp("2004-01-01")))
    t_eval  = int(np.sum(dts < pd.Timestamp("2004-01-01")))   # start eval at end of normal
    # GFC crisis onset: 2007-Q4 (Lehman quarter following)
    t_crisis = int(np.argmin(np.abs((dts - pd.Timestamp("2007-10-01")).total_seconds())))
    # Standardise by normal-window statistics
    mu = Y[:t_cut].mean(axis=(0, 1), keepdims=True)
    sd = Y[:t_cut].std(axis=(0, 1), keepdims=True) + 1e-8
    Y = (Y - mu) / sd
    return Y, labels, t_cut, t_eval, t_crisis


def load_gsib_panel() -> tuple[np.ndarray, list[str], int, int, int]:
    """World Bank G-SIB 8-country panel. Normal ≤ 2003, crisis = 2008."""
    cache = ROOT / "research/adaptive-friction/banklevel_enhanced/gsib_cache_real"
    countries  = ["CHN", "DEU", "FRA", "GBR", "ITA", "JPN", "NGA", "NLD"]
    indicators = ["FB.AST.NPER.ZS", "FB.BNK.CAPA.ZS", "GFDD.SI.01",
                  "FR.INR.LEND", "FR.INR.DPST"]
    series: dict = {}
    for c in countries:
        for ind in indicators:
            f = cache / f"wb_{c}_{ind}.json"
            if f.exists():
                d = json.load(open(f))
                series[(c, ind)] = {k[:4]: v for k, v in d.items() if v is not None}
    years = sorted({y for s in series.values() for y in s})
    Y = np.full((len(years), len(countries), len(indicators)), np.nan)
    for ci, c in enumerate(countries):
        for ii, ind in enumerate(indicators):
            s = series.get((c, ind), {})
            for ti, y in enumerate(years):
                Y[ti, ci, ii] = s.get(y, np.nan)
    for ci in range(len(countries)):
        for ii in range(len(indicators)):
            col = Y[:, ci, ii]
            mask = ~np.isnan(col)
            if mask.sum() > 1:
                col[~mask] = np.interp(np.flatnonzero(~mask),
                                       np.flatnonzero(mask), col[mask])
                Y[:, ci, ii] = col
    Y = np.nan_to_num(Y, nan=0.0)
    years_i = np.array([int(y) for y in years])
    labels  = [str(y) for y in years_i]
    t_cut   = int(np.sum(years_i <= 2003))   # normal: up to and including 2003
    t_eval  = t_cut
    t_crisis = int(np.argmin(np.abs(years_i - 2008)))
    if t_cut < 3:
        t_cut = max(3, len(years_i) // 2)
    mu = Y[:t_cut].mean(axis=(0, 1), keepdims=True)
    sd = Y[:t_cut].std(axis=(0, 1), keepdims=True) + 1e-8
    Y = (Y - mu) / sd
    return Y, labels, t_cut, t_eval, t_crisis


def load_ercot_panel() -> tuple[np.ndarray, list[str], int, int, int]:
    """ERCOT daily 2018-2022 → weekly snapshots N=7 days × d=6 features.
    Normal < 2021-01-01, crisis = week of 2021-02-15 (Winter Storm Uri)."""
    z = np.load(ROOT / "data/ercot/ercot_daily_2018_2022.npz", allow_pickle=True)
    X_raw = z["X"].astype(float)
    dates = np.array(z["dates"], dtype="datetime64[D]")
    fn_raw = [str(s) for s in z["feature_names"]]
    temp = X_raw[:, fn_raw.index("temp_f")]
    def rolling(arr, w, fn):
        out = np.full_like(arr, np.nan)
        for i in range(len(arr)):
            lo = max(0, i - w + 1)
            out[i] = fn(arr[lo: i + 1])
        return out
    X = np.column_stack([
        temp,
        np.concatenate([[0.0], np.diff(temp)]),
        np.abs(np.concatenate([[0.0], np.diff(temp)])),
        rolling(temp, 7, np.mean),
        rolling(temp, 30, np.mean),
        (temp - rolling(temp, 30, np.mean)) / (rolling(temp, 30, np.std) + 1e-6),
    ])
    N, d = 7, 6
    n_weeks = len(X) // N
    X = X[: n_weeks * N]
    dates_w = dates[: n_weeks * N]
    panel = X.reshape(n_weeks, N, d)
    week_dates = dates_w[::N][:n_weeks]
    labels = [str(d) for d in week_dates]
    mask_norm = week_dates < np.datetime64("2021-01-01")
    t_cut = int(mask_norm.sum())
    t_eval = t_cut
    t_crisis = int(np.argmin(np.abs(week_dates - np.datetime64("2021-02-15"))))
    mu = panel[:t_cut].mean(axis=(0, 1), keepdims=True)
    sd = panel[:t_cut].std(axis=(0, 1), keepdims=True) + 1e-8
    panel = (panel - mu) / sd
    return panel, labels, t_cut, t_eval, t_crisis


def load_terra_luna_panel() -> tuple[np.ndarray, list[str], int, int, int]:
    """Simulate the 65-agent Terra/Luna DPD model (168 hours, 5 state dims).

    Agent types  (per TERRA_LUNA_VALIDATION.md):
      30 UST holders    mass 1.0
      15 Anchor deps    mass 2.0
      10 LUNA stakers   mass 1.5
       8 Arbitrageurs   mass 0.8
       2 Whale/attackers mass 5.0

    State per agent: [depeg, luna_price, liquidity, arb_spread, fear]

    Crisis timeline (hours):
      0 – 22  : normal / pre-attack  → frozen normal window
      24      : first attack (crisis onset)
      30      : LFG BTC defence
      42      : defence weakening
      48      : spiral engages (>10% depeg)
      54      : rapid collapse (50% depeg)
      72–168  : post-collapse
    """
    rng = np.random.default_rng(42)
    N_agents = 65
    d_state  = 5
    T_hours  = 169   # 0 … 168

    # Real UST depeg trajectory (hourly interpolation of TERRA_LUNA_VALIDATION.md)
    milestones = [(0, 0.00), (6, 0.001), (22, 0.01), (24, 0.020),
                  (30, 0.015), (36, 0.025), (42, 0.065), (48, 0.200),
                  (54, 0.500), (60, 0.650), (72, 0.720), (84, 0.800),
                  (96, 0.850), (108, 0.900), (120, 0.940), (144, 0.980),
                  (168, 0.990)]
    hrs_m, dep_m = zip(*milestones)
    depeg_real = np.interp(np.arange(T_hours), hrs_m, dep_m)

    # Agent-type masks
    mask_ust    = np.arange(N_agents) < 30
    mask_anchor = (np.arange(N_agents) >= 30) & (np.arange(N_agents) < 45)
    mask_staker = (np.arange(N_agents) >= 45) & (np.arange(N_agents) < 55)
    mask_arb    = (np.arange(N_agents) >= 55) & (np.arange(N_agents) < 63)
    mask_whale  = np.arange(N_agents) >= 63

    mass = np.ones(N_agents)
    mass[mask_anchor] = 2.0
    mass[mask_staker] = 1.5
    mass[mask_arb]    = 0.8
    mass[mask_whale]  = 5.0

    # Simulate state panel (T, N, d)
    X = np.zeros((T_hours, N_agents, d_state))
    state = np.zeros((N_agents, d_state))

    # Initial normal state — agent-type-specific baselines
    state[:, 0] = rng.normal(0.00, 0.005, N_agents)   # depeg ~0
    state[:, 1] = rng.normal(0.85, 0.05,  N_agents)   # luna_price ~$85 norm
    state[:, 2] = rng.normal(0.90, 0.05,  N_agents)   # liquidity  ~high
    state[:, 3] = rng.normal(0.02, 0.01,  N_agents)   # arb spread ~small
    state[:, 4] = rng.normal(0.05, 0.02,  N_agents)   # fear       ~low

    for h in range(T_hours):
        d = depeg_real[h]
        # Exogenous depeg drives agent state
        noise = rng.normal(0, 0.01, (N_agents, d_state))

        # Feature 0: individual depeg exposure (correlated with d but agent-specific)
        target_dep = d + rng.normal(0, 0.02, N_agents)
        target_dep[mask_whale] = d * (1.0 + 0.5 * rng.random(2))   # whales deeper
        target_dep[mask_arb]   = d * (0.6 + 0.2 * rng.random(8))   # arbs partially hedged
        state[:, 0] = 0.7 * state[:, 0] + 0.3 * target_dep + noise[:, 0] * 0.02

        # Feature 1: LUNA price proxy (crashes faster than depeg after h>48)
        luna_crash = (d ** 2.0)  # non-linear LUNA hyperinflation
        target_luna = 1.0 - luna_crash + rng.normal(0, 0.05, N_agents)
        state[:, 1] = 0.8 * state[:, 1] + 0.2 * target_luna + noise[:, 1] * 0.03

        # Feature 2: liquidity (drain as depeg grows)
        target_liq = 1.0 - d * 1.2 + rng.normal(0, 0.03, N_agents)
        target_liq[mask_anchor] -= d * 0.4   # Anchor sees faster outflows
        state[:, 2] = 0.85 * state[:, 2] + 0.15 * target_liq + noise[:, 2] * 0.02

        # Feature 3: arb spread (spikes when arb profitable but risky)
        arb_opportunity = d * (1 - d) * 4   # peaked at 50% depeg
        state[:, 3] = 0.7 * state[:, 3] + 0.3 * arb_opportunity + noise[:, 3] * 0.01

        # Feature 4: fear/sentiment (lagged, non-linear escalation)
        fear_target = np.where(d < 0.1, d * 0.5, np.where(d < 0.5, d, 1.0))
        state[:, 4] = 0.75 * state[:, 4] + 0.25 * fear_target + noise[:, 4] * 0.02

        X[h] = state.copy()

    labels = [f"H{h:03d}" for h in range(T_hours)]
    # Normal window: hours 0 … 22 (pre-attack, 23 steps usable since we need X_prev)
    t_cut   = 23    # exclusive — calibrate on hours 0-22
    t_eval  = 23
    t_crisis = 24   # first attack hour
    mu = X[:t_cut].mean(axis=(0, 1), keepdims=True)
    sd = X[:t_cut].std(axis=(0, 1), keepdims=True) + 1e-8
    X = (X - mu) / sd
    return X, labels, t_cut, t_eval, t_crisis


# ═══════════════════════════════════════════════════════════════════════
# Print / format helpers
# ═══════════════════════════════════════════════════════════════════════

def _lead_label(lead: int | None, unit: str) -> str:
    if lead is None:
        return "NO ALARM"
    if lead > 0:
        return f"+{lead} {unit} before crisis"
    if lead == 0:
        return f"coincident with crisis"
    return f"{lead} {unit} AFTER crisis"


def print_summary_table(results: list[dict]) -> None:
    unit_map = {"FDIC": "quarters", "GSIB": "years",
                "ERCOT": "weeks", "TerraLuna": "hours"}
    print("\n" + "═" * 80)
    print("  FROZEN-NORMAL-WINDOW LEAD-TIME SUMMARY")
    print("  (SIAM paper §7 protocol — calibration frozen on pre-crisis normal window)")
    print("═" * 80)
    hdr = f"  {'Dataset':<14}  {'Normal window ends':<22}  {'Crisis onset':<18}  " \
          f"{'Lead (dyn.)':<22}  {'EWS thresh':<10}  {'e* '}"
    print(hdr)
    print("  " + "─" * 77)
    for r in results:
        nm = r["name"]
        unit = unit_map.get(nm, "steps")
        lead_s = _lead_label(r["lead_time_periods"], unit)
        print(f"  {nm:<14}  "
              f"{'t='+str(r['t_normal_end']):<22}  "
              f"{r['crisis_label']:<18}  "
              f"{lead_s:<22}  "
              f"{r['ews_thresh_dynamic']:<10.4f}  "
              f"{r['e_star']:.2f}")
    print("═" * 80)


def print_per_dataset_timeline(result: dict, max_rows: int = 40) -> None:
    unit_map = {"FDIC": "Q", "GSIB": "Y", "ERCOT": "W", "TerraLuna": "H"}
    unit = unit_map.get(result["name"], "t")
    print(f"\n  ─── {result['name']} — full evaluation timeline ───")
    print(f"  {'Period':<18}  {'EWS':>6}  {'e_BSDT':>8}  {'γ*':>6}  "
          f"{'ψ(rad)':>6}  {'cos_θS':>7}  {'cos_θC':>7}  Alarm  Crisis")
    print("  " + "─" * 75)
    recs = result["records"]
    step = max(1, len(recs) // max_rows)
    prev_crisis = False
    for r in recs[::step]:
        ews   = r.get("EWS", float("nan"))
        e_b   = r.get("e_BSDT", float("nan"))
        gam   = r.get("gamma_star", float("nan"))
        psi   = r.get("psi", float("nan"))
        cos_s = r.get("cos_theta_state", float("nan"))
        cos_c = r.get("cos_theta_chan", float("nan"))
        alarm = "▲" if r.get("alarm_dynamic") else " "
        cmark = "◄" if r["t"] == result["crisis_onset_idx"] else " "
        crisis_flag = "CRISIS" if r.get("is_crisis") else "normal"
        print(f"  {r['period']:<18s}  {ews:6.4f}  {e_b:8.3f}  {gam:6.4f}  "
              f"{psi:6.4f}  {cos_s:+7.4f}  {cos_c:+7.4f}  [{alarm}]    {cmark}{crisis_flag}")


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    out_dir = ROOT / "research" / "adaptive-friction"
    print("\n" + "═" * 72)
    print("  FROZEN-NORMAL-WINDOW SIMULATION  (SIAM §7 no-lookahead protocol)")
    print("  Datasets: FDIC  |  G-SIB World Bank  |  ERCOT  |  Terra/Luna")
    print("═" * 72)

    t0 = time.perf_counter()
    all_results: list[dict] = []

    datasets = [
        ("FDIC",       load_fdic_panel,       12),   # 12-period history window
        ("GSIB",       load_gsib_panel,        5),
        ("ERCOT",      load_ercot_panel,       8),
        ("TerraLuna",  load_terra_luna_panel,  8),
    ]

    for dname, loader_fn, hist_len in datasets:
        try:
            panel, labels, t_cut, t_eval, t_crisis = loader_fn()
            r = frozen_normal_scan(
                name=dname,
                X_all=panel,
                t_normal_end=t_cut,
                t_eval_start=t_eval,
                crisis_onset_idx=t_crisis,
                period_labels=labels,
                history_len=hist_len,
            )
            all_results.append(r)
            print_per_dataset_timeline(r)
        except Exception as exc:
            import traceback
            print(f"\n!! {dname} FAILED: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            all_results.append({"name": dname, "error": str(exc)})

    # ── Summary table ────────────────────────────────────────────────
    valid = [r for r in all_results if "lead_time_periods" in r]
    if valid:
        print_summary_table(valid)

    # ── Write output files ───────────────────────────────────────────
    json_path = out_dir / "frozen_normal_results.json"
    # records contain numpy bools/floats — serialise safely
    def _default(o):
        if isinstance(o, (np.float32, np.float64)): return float(o)
        if isinstance(o, (np.int32, np.int64)):     return int(o)
        if isinstance(o, np.bool_):                 return bool(o)
        return str(o)
    json_path.write_text(json.dumps(all_results, indent=2, default=_default))

    # Human-readable text summary
    txt_path = out_dir / "frozen_normal_timeline.txt"
    import io
    buf = io.StringIO()
    import contextlib
    # Re-print summary to file
    with contextlib.redirect_stdout(buf):
        print_summary_table(valid)
        for r in valid:
            print_per_dataset_timeline(r, max_rows=60)
    txt_path.write_text(buf.getvalue(), encoding="utf-8")

    elapsed = time.perf_counter() - t0
    print(f"\n{'═'*72}")
    print(f"  Done in {elapsed:.1f}s")
    print(f"  JSON : {json_path}")
    print(f"  TEXT : {txt_path}")
    print("═" * 72)


if __name__ == "__main__":
    main()
