# -*- coding: utf-8 -*-
"""
test_full_engine_benchmark.py
=============================
Dynamical-systems validation of the canonical collapse-geometry stack.

This is NOT a machine-learning benchmark.  CEK-v4 / CGS-v1 is a deterministic
Lyapunov flow, not a fitted classifier, so AUROC / hit-rate are the wrong
instruments.  Instead we test the framework's *structural* claims directly:

  C1  Lyapunov descent      E should dissipate (Edot < 0) during quiescence.
  C2  Energy precursor       Edot should rise (turn positive) approaching onset.
  C3  Three-phase precursor   P(t)=[Edot>0 & Rdot>0 & theta_ddot>0] should
                              CONCENTRATE in the pre-onset window, not fire
                              uniformly (Trigonometry-of-Collapse Thm 46.1).
  C4  Geometry reorganises    cos(theta), gamma, rho_eff should DRIFT across the
                              transition with theory-predicted signs:
                                 cos(theta)  +  (enters 'collapse' regime, >0)
                                 gamma       +  (brake saturates as E rises)
                                 rho_eff     -  (safety ratio collapses)
  C5  Betti time-locking      Morse-index flips (beta_1 events) should cluster
                              pre-onset, not sit at the ~25% second-difference
                              noise floor.
  C6  Kramers crossing        For the stochastic tier, the barrier-crossing
                              hazard h(t) (escape probability over horizon tau)
                              should rise pre-onset.  This is a TIME-TO-EVENT
                              quantity — the only question the Ito/Kramers
                              machinery can actually answer (it is rank-inert
                              for classification by construction).

Significance for every event-locked quantity is established by an EVENT-SHUFFLE
null: the same signal is scored against randomly-placed pseudo-onsets (n=2000),
and the empirical p-value is the fraction of nulls at least as extreme as the
observed pre-onset statistic.  This controls for the signal's base rate and
autocorrelation, which a single ROC point cannot.

Engines compared (identical deterministic flow, differing observables):
  v4          FrozenCanonicalV4         (locked affine CEK-v4)
  cgs1        CGS-v1 batch flow         (E, Edot, g_norm, gamma directly)
  cgs1_morse  cgs1 + Morse/Betti        (adds C5)
  cgs1_stoch  cgs1 + Ito/Kramers        (adds C6)

Domains:
  banks    G-SIB real panel    onsets = entries into GFC/Euro/COVID/SVB windows
  protein  RCSB PDB B-factors  onsets = entries into disordered (high-B) segments
  eeg      UCI EEG eye-state   onsets = eye open->closed transitions

Outputs: benchmark_dynamical_results.json (repo root) + printed report.

Author: Copilot — June 2026
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings

import numpy as np

warnings.filterwarnings("ignore")
np.random.seed(20260601)

ROOT = r"C:\amttp"
NS = os.path.join(ROOT, "research", "neural-stability")
BANK = os.path.join(ROOT, "research", "adaptive-friction", "banklevel_enhanced")
sys.path.insert(0, NS)
sys.path.insert(0, BANK)

from canonical_v4_engine import FrozenCanonicalV4          # noqa: E402
from cgs_v1_engine import evaluate_cgs_v1_batch            # noqa: E402
import trading_stack_brakes as TSB                         # noqa: E402

EPS = 1e-12
N_SHUFFLE = 2000
TIERS = ["v4", "cgs1", "cgs1_morse", "cgs1_stoch"]
G7_KAPPA_MAX = 10.0   # G7 regularisation cap on cond(Sigma_0); None disables

# theory-predicted sign of the pre-onset drift for each geometry diagnostic
PREDICTED_SIGN = {"cos_theta": +1.0, "gamma": +1.0, "rho_eff": -1.0, "Edot": +1.0}


# ════════════════════════════════════════════════════════════════════════════
#  CGS-v1 function builders from a fitted FrozenCanonicalV4
# ════════════════════════════════════════════════════════════════════════════

def _alpha_of(engine: FrozenCanonicalV4) -> float:
    return float(getattr(engine, "alpha_base_", getattr(engine, "alpha_base", 0.05)))


def build_cgs_fns(engine: FrozenCanonicalV4):
    """Derive (S_fn, J_fn, G, Fbase_fn, theta) from a fitted V4 engine."""
    mu, sigma, G = engine.mu_, engine.sigma_, engine.G_
    alpha, theta = _alpha_of(engine), float(engine.theta_)
    # Euclidean chart (canonical Rule 2): J = dS/dX is taken as the IDENTITY,
    # exactly as FrozenCanonicalV4._observables does (gX = 2 G S).  The metric
    # Jacobian J = diag(1/sigma) amplifies low-variance dimensions without
    # bound and produced the dEdot ~ 1e6 blow-ups on banks/protein; G7 cannot
    # fix that because it regularises Sigma_0, not the chart Jacobian.  Using
    # J = I makes every tier numerically identical to v4 in the chart and
    # comparable across stiff domains.
    n_dim = len(sigma)
    J_const = np.eye(n_dim)

    def S_fn(X):
        return (np.asarray(X, dtype=float) - mu) / sigma

    def J_fn(X):
        return J_const

    def Fbase_fn(X):
        return -alpha * S_fn(X)

    return S_fn, J_fn, G, Fbase_fn, theta


def compute_cos_theta_series(X_series: np.ndarray, engine: FrozenCanonicalV4) -> np.ndarray:
    """Per-step alignment cos(theta) = <gX, Fbase> / (||gX|| ||Fbase||)."""
    mu, sigma, G = engine.mu_, engine.sigma_, engine.G_
    alpha = _alpha_of(engine)
    Z = (np.asarray(X_series, dtype=float) - mu[None, :]) / sigma[None, :]
    gX = 2.0 * (Z @ G)
    Fbase = -alpha * Z
    dot = np.einsum("ij,ij->i", gX, Fbase)
    gn = np.linalg.norm(gX, axis=1) + EPS
    fn = np.linalg.norm(Fbase, axis=1) + EPS
    return np.clip(dot / (gn * fn), -1.0, 1.0)


def engine_series(tier: str, engine: FrozenCanonicalV4, X: np.ndarray) -> dict:
    """Return the dynamical state series the instruments operate on.

    All tiers expose: E, Edot, g_norm (R), cos_theta, gamma, rho_eff.
    """
    if tier == "v4":
        r = engine.evaluate(X)
        E, Edot, g_norm = r.E, r.Edot, r.g_norm
        cos_theta, gamma = r.cos_theta, r.gamma
    else:
        S_fn, J_fn, G, Fbase_fn, theta = build_cgs_fns(engine)
        b = evaluate_cgs_v1_batch(X, S_fn, J_fn, G, Fbase_fn, theta)
        E, Edot, g_norm, gamma = b["E"], b["Edot"], b["g_norm"], b["gamma"]
        cos_theta = compute_cos_theta_series(X, engine)
    rho_eff = -Edot / (np.abs(E) + EPS)   # safety ratio (sign per CHB-MIT diag)
    return dict(E=E, Edot=Edot, g_norm=g_norm, cos_theta=cos_theta,
                gamma=gamma, rho_eff=rho_eff)


# ════════════════════════════════════════════════════════════════════════════
#  Dynamical instruments
# ════════════════════════════════════════════════════════════════════════════

def onset_events(crisis_mask: np.ndarray) -> np.ndarray:
    """Indices where the trajectory ENTERS a crisis/disordered segment."""
    c = np.asarray(crisis_mask, dtype=int)
    if c.size == 0:
        return np.array([], dtype=int)
    rising = np.where(np.diff(c) > 0)[0] + 1
    if c[0] == 1:                       # series starts already in crisis
        rising = np.concatenate([[0], rising])
    return rising


def _pre_onset_mask(onsets: np.ndarray, W: int, T: int) -> np.ndarray:
    m = np.zeros(T, dtype=bool)
    for o in onsets:
        lo = max(0, o - W)
        if lo < o:
            m[lo:o] = True
    return m


def lyapunov_descent(Edot: np.ndarray, crisis_mask: np.ndarray) -> dict:
    """C1: does E dissipate during quiescence?"""
    q = ~np.asarray(crisis_mask, dtype=bool)
    if q.sum() == 0:
        return dict(desc_frac=float("nan"), Edot_quiescent=float("nan"))
    eq = Edot[q]
    return dict(desc_frac=float((eq < 0).mean()),
                Edot_quiescent=float(np.mean(eq)))


def _drift_stat(signal: np.ndarray, onsets: np.ndarray, W: int) -> float:
    """Pre-onset mean minus global mean (the event-locked drift)."""
    T = len(signal)
    pre = _pre_onset_mask(onsets, W, T)
    if pre.sum() == 0:
        return float("nan")
    return float(np.mean(signal[pre]) - np.mean(signal))


def _rate_ratio(boolean: np.ndarray, onsets: np.ndarray, W: int) -> float:
    """Pre-onset event rate / global event rate (>1 = concentrates pre-onset)."""
    T = len(boolean)
    pre = _pre_onset_mask(onsets, W, T)
    base = float(np.mean(boolean)) + EPS
    if pre.sum() == 0:
        return float("nan")
    return float(np.mean(boolean[pre]) / base)


def precursor_lead(boolean: np.ndarray, onsets: np.ndarray, W: int) -> float:
    """Mean lead (in steps) of the FIRST precursor firing inside each pre-onset
    window, averaged over onsets that have at least one firing.  Larger = the
    precursor fires earlier before onset.  NaN if no onset window contains a
    firing."""
    T = len(boolean)
    leads = []
    for o in onsets:
        lo = max(0, o - W)
        if lo >= o:
            continue
        seg = np.where(boolean[lo:o])[0]
        if seg.size:
            first = lo + int(seg[0])
            leads.append(o - first)
    return float(np.mean(leads)) if leads else float("nan")


def per_onset_drift(signal: np.ndarray, onsets: np.ndarray, W: int) -> dict:
    """Per-onset version of the drift statistic: for each onset, mean(signal in
    its own pre-onset window) - global mean.  Reports the distribution across
    events so a pooled mean can't be carried by a single outlier onset.

    Returns: n_events, frac_pos (fraction of onsets with positive drift),
             mean, std, and the raw per-onset values.
    """
    g = float(np.mean(signal))
    vals = []
    T = len(signal)
    for o in onsets:
        lo = max(0, o - W)
        if lo >= o:
            continue
        vals.append(float(np.mean(signal[lo:o]) - g))
    if not vals:
        return dict(n_events=0, frac_pos=float("nan"),
                    mean=float("nan"), std=float("nan"), values=[])
    arr = np.asarray(vals)
    return dict(n_events=len(vals), frac_pos=float((arr > 0).mean()),
                mean=float(arr.mean()), std=float(arr.std()), values=vals)


def event_shuffle_p(signal: np.ndarray, onsets: np.ndarray, W: int,
                    stat_fn, observed: float, n: int = N_SHUFFLE,
                    two_sided: bool = True) -> float:
    """Empirical p-value: place len(onsets) pseudo-onsets at random and recompute
    the statistic.  Controls for the signal's base rate / autocorrelation."""
    T = len(signal)
    k = len(onsets)
    if k == 0 or not np.isfinite(observed):
        return float("nan")
    null = np.empty(n)
    lo, hi = W, T
    for i in range(n):
        fake = np.random.randint(lo, hi, size=k) if hi > lo else onsets
        null[i] = stat_fn(signal, fake, W)
    null = null[np.isfinite(null)]
    if null.size == 0:
        return float("nan")
    if two_sided:
        centre = np.median(null)
        return float((np.abs(null - centre) >= abs(observed - centre)).mean())
    return float((null >= observed).mean())


def kramers_hazard(E: np.ndarray, Edot: np.ndarray, e_star: float,
                   sigma_n: float, tau: float) -> np.ndarray:
    """C6: per-step Kramers barrier-crossing probability over horizon tau.

        tau_K = 2*pi / sqrt(|mu'(e_t)|*|mu'(e*)|) * exp(2(e* - e_t)/sigma_n^2)
        h(t)  = 1 - exp(-tau / tau_K)                       (escape probability)

    mu(e) = drift of energy = Edot;  mu'(e) estimated as the local slope of
    Edot along the energy axis.  sigma_n is the natural diffusion scale of the
    energy increments, so the barrier is finite and surmountable.
    """
    T = len(E)
    h = np.zeros(T)
    order = np.argsort(E)
    Es, Eds = E[order], Edot[order]
    if np.ptp(Es) < EPS:
        return h
    slope_sorted = np.gradient(Eds, Es + np.linspace(0, EPS, T))
    dmu = np.empty(T)
    dmu[order] = slope_sorted
    mu_star_slope = float(np.interp(e_star, Es, slope_sorted))
    s2 = max(sigma_n ** 2, 1e-12)
    for t in range(T):
        e_t = E[t]
        if e_star <= e_t:
            h[t] = 1.0
            continue
        denom = np.sqrt(abs(dmu[t]) * abs(mu_star_slope)) + 1e-12
        log_barrier = min(2.0 * (e_star - e_t) / s2, 700.0)
        tau_K = (2.0 * np.pi / denom) * np.exp(log_barrier)
        h[t] = 1.0 - np.exp(-tau / max(tau_K, 1e-12))
    return h


# ════════════════════════════════════════════════════════════════════════════
#  Per-engine evaluation
# ════════════════════════════════════════════════════════════════════════════

def run_one_engine(tier: str, engine: FrozenCanonicalV4, X: np.ndarray,
                   crisis_mask: np.ndarray, label: str, W: int) -> dict:
    X = np.asarray(X, dtype=float)
    crisis_mask = np.asarray(crisis_mask, dtype=bool)
    T = X.shape[0]
    s = engine_series(tier, engine, X)
    onsets = onset_events(crisis_mask)
    n_on = len(onsets)

    row = {"domain": label, "engine": tier, "n_onsets": int(n_on),
           "T": int(T), "W": int(W)}

    # C1 — Lyapunov descent during quiescence
    row.update(lyapunov_descent(s["Edot"], crisis_mask))

    # C2 + C4 — energy + geometry drift across onset, with predicted signs
    geom_keys = ["Edot", "cos_theta", "gamma", "rho_eff"]
    n_tests = len(geom_keys)   # Bonferroni family size
    for key in geom_keys:
        d = _drift_stat(s[key], onsets, W)
        p = event_shuffle_p(s[key], onsets, W, _drift_stat, d)
        p_bonf = min(1.0, p * n_tests) if np.isfinite(p) else float("nan")
        row[f"drift_{key}"] = d
        row[f"p_{key}"] = p
        row[f"pbonf_{key}"] = p_bonf
        pod = per_onset_drift(s[key], onsets, W)
        row[f"poFrac_{key}"] = pod["frac_pos"]   # event-consistency of sign
        pred = PREDICTED_SIGN[key]
        # significant under Bonferroni AND correctly signed = confirmed
        row[f"match_{key}"] = bool(np.isfinite(d) and np.sign(d) == pred
                                   and np.isfinite(p_bonf) and p_bonf < 0.05)

    # C3 — three-phase precursor concentration (all tiers share the geometry)
    topo = TSB.morse_curvature_signals(
        s["E"], s["g_norm"], s["cos_theta"], engine.G_, alpha_base=_alpha_of(engine))
    p3 = topo["three_phase_mask"].astype(float)
    r3 = _rate_ratio(p3, onsets, W)
    row["p3_conc_ratio"] = r3
    row["p_p3"] = event_shuffle_p(p3, onsets, W, _rate_ratio, r3)
    row["p3_global_rate"] = float(p3.mean())
    row["p3_lead"] = precursor_lead(topo["three_phase_mask"], onsets, W)

    # C3b — DISJUNCTION precursor: the EEG result showed Edot and cos_theta
    # carry signal individually but the AND-conjunction (three-phase) loses it.
    # Test P_disj = [Edot rising] OR [cos_theta rising] instead.
    Edot_rise = np.concatenate([[False], np.diff(s["Edot"]) > 0]) if T > 1 else np.zeros(T, bool)
    cos_rise = np.concatenate([[False], np.diff(s["cos_theta"]) > 0]) if T > 1 else np.zeros(T, bool)
    p_disj = (Edot_rise | cos_rise).astype(float)
    rd = _rate_ratio(p_disj, onsets, W)
    row["disj_conc_ratio"] = rd
    row["p_disj"] = event_shuffle_p(p_disj, onsets, W, _rate_ratio, rd)
    row["disj_global_rate"] = float(p_disj.mean())
    row["disj_lead"] = precursor_lead((Edot_rise | cos_rise), onsets, W)

    # C5 — Betti / Morse-index flip time-locking (cgs1_morse, cgs1_stoch report it)
    if tier in ("cgs1_morse", "cgs1_stoch"):
        bt = topo["betti_transitions"].astype(float)
        rb = _rate_ratio(bt, onsets, W)
        row["betti_conc_ratio"] = rb
        row["p_betti"] = event_shuffle_p(bt, onsets, W, _rate_ratio, rb)
        row["betti_global_rate"] = float(bt.mean())
        row["betti_peak"] = int(topo["betti_cumulative"][-1]) if T else 0

    # C6 — Kramers barrier-crossing hazard (cgs1_stoch only)
    if tier == "cgs1_stoch":
        E = s["E"]
        q = ~crisis_mask
        e_star = float(np.mean(E[q]) + 2.0 * np.std(E[q])) if q.sum() else float(np.mean(E))
        sigma_n = float(np.std(np.diff(E))) + EPS          # natural diffusion scale
        tau = float(max(1.0, W))
        h = kramers_hazard(E, s["Edot"], e_star, sigma_n, tau)
        dh = _drift_stat(h, onsets, W)
        row["kramers_drift"] = dh
        row["p_kramers"] = event_shuffle_p(h, onsets, W, _drift_stat, dh)
        row["kramers_global_mean"] = float(np.mean(h))
        row["e_star"] = e_star
        row["sigma_n_eff"] = sigma_n

    return _clean(row)


def _clean(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, (np.floating, np.integer)):
            v = v.item()
        elif isinstance(v, np.bool_):
            v = bool(v)
        out[k] = v
    return out


def run_all_tiers(X_ref, X, crisis_mask, label, W) -> list[dict]:
    rows = []
    for tier in TIERS:
        engine = FrozenCanonicalV4(alpha_base=0.05)
        engine.fit(X_ref)
        # G7: cap cond(Sigma_0) so near-singular references don't blow up
        # gradients (banks/protein had kappa ~ 1e10 -> dEdot ~ 1e7 artefacts).
        lam_g7 = TSB.apply_g7_to_engine(engine, G7_KAPPA_MAX)
        r = run_one_engine(tier, engine, X, crisis_mask, label, W)
        r["g7_lambda"] = float(lam_g7)
        rows.append(r)
    return rows


# ════════════════════════════════════════════════════════════════════════════
#  Domains
# ════════════════════════════════════════════════════════════════════════════

def domain_banks() -> list[dict]:
    import pandas as pd
    cache = os.path.join(BANK, "gsib_cache_real", "gsib_real_panel.npz")
    if not os.path.exists(cache):
        print(f"[banks] cache not found: {cache} — skipping")
        return []
    npz = np.load(cache)
    X_3d = npz["X"]
    T = X_3d.shape[0]
    dates = pd.date_range("2005-01-01", "2023-12-31", freq="QE")[:T]
    Xagg = np.nan_to_num(np.nanmean(X_3d, axis=1), nan=0.0, posinf=0.0, neginf=0.0)
    windows = [("2008-09-30", "2009-03-31"), ("2011-09-30", "2012-03-31"),
               ("2020-03-31", "2020-06-30"), ("2023-03-31", "2023-06-30")]
    crisis = np.zeros(T, dtype=bool)
    for lo, hi in windows:
        crisis |= np.asarray((dates >= pd.Timestamp(lo)) & (dates <= pd.Timestamp(hi)))
    X_ref = Xagg[np.asarray(dates < pd.Timestamp("2008-01-01"))]
    print(f"[banks] T={T} d={Xagg.shape[1]} ref={len(X_ref)} onsets={len(onset_events(crisis))}")
    return run_all_tiers(X_ref, Xagg, crisis, "banks", W=4)   # 4 quarters = 1 yr


def domain_protein() -> list[dict]:
    try:
        from domain_v2_protein import (
            PDB_IDS, fetch_pdb_bfactors, bfactors_to_state_matrix,
            CRISIS_B_ZSCORE, REF_B_FRACTION)
    except Exception as exc:
        print(f"[protein] import failed: {exc} — skipping")
        return []
    rows = []
    for pdb_id in PDB_IDS:
        print(f"[protein] {pdb_id} fetching ...")
        try:
            data = fetch_pdb_bfactors(pdb_id)
        except Exception as exc:
            print(f"[protein] {pdb_id} fetch error: {exc} — skipping")
            continue
        if not data:
            continue
        bf = np.asarray(data["bfactors"], dtype=float)
        X = bfactors_to_state_matrix(bf)
        crisis = bf > (bf.mean() + CRISIS_B_ZSCORE * bf.std())
        X_ref = X[bf <= np.percentile(bf, REF_B_FRACTION * 100)]
        print(f"[protein] {pdb_id} n={len(bf)} ref={len(X_ref)} onsets={len(onset_events(crisis))}")
        rows += run_all_tiers(X_ref, X, crisis, f"protein:{pdb_id}", W=5)
    return rows


def domain_eeg() -> list[dict]:
    try:
        from domain_real_eeg import load_arff, DATA
    except Exception as exc:
        print(f"[eeg] import failed: {exc} — skipping")
        return []
    if not os.path.exists(DATA):
        print(f"[eeg] data not found: {DATA} — skipping")
        return []
    X_eeg, y = load_arff(DATA)
    open_idx = np.where(y == 0)[0]
    if len(open_idx) < 100:
        return []
    X_ref = X_eeg[open_idx[:1500]]
    crisis = (y == 1)
    print(f"[eeg] n={len(y)} ref={len(X_ref)} onsets={len(onset_events(crisis))}")
    return run_all_tiers(X_ref, X_eeg, crisis, "eeg", W=64)   # ~0.5 s at 128 Hz


# ════════════════════════════════════════════════════════════════════════════
#  Reporting
# ════════════════════════════════════════════════════════════════════════════

def _sig(val, p, fmt="{:+.3f}"):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "   -   "
    star = "*" if (isinstance(p, float) and np.isfinite(p) and p < 0.05) else " "
    return fmt.format(val) + star


def print_report(rows: list[dict]) -> None:
    print("\n" + "=" * 134)
    print("DYNAMICAL VALIDATION  ( * = event-shuffle p < 0.05 AFTER Bonferroni×4 ;  drift = pre-onset mean - global mean )")
    print("=" * 134)
    hdr = (f"{'domain':<14}{'engine':<11}{'n_on':>4}{'descF':>7}"
           f"{'dEdot':>9}{'dCos':>9}{'dgam':>9}{'drho':>9}"
           f"{'C4ok':>5}{'P3conc':>8}{'Disj':>8}{'Dlead':>7}{'Betti':>8}{'Kram':>11}")
    print(hdr)
    print("-" * 134)
    last = None
    for r in rows:
        if last is not None and r["domain"] != last:
            print("-" * 134)
        last = r["domain"]
        c4ok = sum(int(bool(r.get(f"match_{k}")))
                   for k in ("Edot", "cos_theta", "gamma", "rho_eff"))
        print(
            f"{r['domain']:<14}{r['engine']:<11}{r['n_onsets']:>4}"
            f"{_sig(r.get('desc_frac'), None, '{:.3f}'):>7}"
            f"{_sig(r.get('drift_Edot'), r.get('pbonf_Edot')):>9}"
            f"{_sig(r.get('drift_cos_theta'), r.get('pbonf_cos_theta')):>9}"
            f"{_sig(r.get('drift_gamma'), r.get('pbonf_gamma')):>9}"
            f"{_sig(r.get('drift_rho_eff'), r.get('pbonf_rho_eff')):>9}"
            f"{c4ok:>5}"
            f"{_sig(r.get('p3_conc_ratio'), r.get('p_p3'), '{:.2f}'):>8}"
            f"{_sig(r.get('disj_conc_ratio'), r.get('p_disj'), '{:.2f}'):>8}"
            f"{_sig(r.get('disj_lead'), None, '{:.1f}'):>7}"
            f"{_sig(r.get('betti_conc_ratio'), r.get('p_betti'), '{:.2f}'):>8}"
            f"{_sig(r.get('kramers_drift'), r.get('p_kramers'), '{:+.2e}'):>11}"
        )
    print("=" * 134)
    print("descF : fraction of quiescent steps with Edot<0   (C1, want > 0.5; =1.0 is tautological)")
    print("dEdot : energy-rate drift pre-onset                (C2, predict +)")
    print("dCos/dgam/drho : geometry drift pre-onset          (C4, predict + / + / -)")
    print("C4ok  : # of {Edot,cos,gamma,rho} both correctly signed AND Bonferroni-significant")
    print("P3conc: three-phase AND-precursor rate-ratio       (C3, want > 1)")
    print("Disj  : OR-precursor [Edot rise | cos rise] ratio  (C3b, want > 1)")
    print("Dlead : mean lead (steps) of OR-precursor pre-onset (larger = earlier)")
    print("Betti : Morse-index flip rate-ratio pre-onset      (C5, want > 1)")
    print("Kram  : Kramers crossing-hazard drift pre-onset    (C6, want > 0)")
    print("=" * 134)
    # Confirmation summary: which (domain, engine) survive Bonferroni on >=1 C4 sign
    print("\nCONFIRMED PRECURSORS (Bonferroni-significant, theory-signed C4 diagnostics):")
    any_conf = False
    for r in rows:
        hits = [k for k in ("Edot", "cos_theta", "gamma", "rho_eff") if r.get(f"match_{k}")]
        if hits:
            any_conf = True
            parts = []
            for k in hits:
                drift_k = r["drift_" + k]
                frac_k = r.get("poFrac_" + k, float("nan"))
                parts.append(f"{k}={drift_k:+.3f}(frac+={frac_k:.2f})")
            detail = ", ".join(parts)
            print(f"  {r['domain']:<14} {r['engine']:<11} n_on={r['n_onsets']:<3} -> {detail}")
    if not any_conf:
        print("  (none)")
    print("=" * 134 + "\n")


def main() -> None:
    t0 = time.time()
    print("=" * 100)
    print("DYNAMICAL ENGINE VALIDATION — v4 / cgs1 / cgs1_morse / cgs1_stoch  ×  banks / protein / eeg")
    print("=" * 100)
    rows: list[dict] = []
    rows += domain_banks()
    rows += domain_eeg()
    rows += domain_protein()
    if not rows:
        print("No domains produced results.")
        return
    print_report(rows)
    out_path = os.path.join(ROOT, "benchmark_dynamical_results.json")
    payload = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "engine_tiers": TIERS,
        "n_shuffle": N_SHUFFLE,
        "g7_kappa_max": G7_KAPPA_MAX,
        "predicted_signs": PREDICTED_SIGN,
        "claims": {
            "C1": "Lyapunov descent: Edot<0 during quiescence",
            "C2": "Energy precursor: Edot drifts + pre-onset",
            "C3": "Three-phase AND-precursor concentrates pre-onset",
            "C3b": "Disjunction OR-precursor concentrates pre-onset",
            "C4": "Geometry drift cos+/gamma+/rho- pre-onset",
            "C5": "Betti/Morse flips time-lock pre-onset",
            "C6": "Kramers crossing-hazard rises pre-onset",
        },
        "results": rows,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Saved {len(rows)} rows -> {out_path}")
    print(f"Elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
