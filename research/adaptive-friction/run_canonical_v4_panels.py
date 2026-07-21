"""Apply canonical_system_v4 directly to the three real-data panels.

Each panel is wired as a literal §8.1 TradingDomain instantiation of
``CanonicalSystem``:

    S(X)     = X − μ_normal              (residual relative to normal regime)
    J(X)     = I_n
    G        = Σ_normal^{-1}             (Mahalanobis metric)
    F_base   = −κ (X − μ_normal)         (mean reversion to normal)
    E(X)     = (X−μ)ᵀ Σ^{-1} (X−μ)       (Theorem 6.6 energy — single defn)
    g_X(X)   = 2 Σ^{-1} (X−μ)            (§4.3, single gradient)

Risk signal at time t = canonical energy E(X_t).  This is the *canonical*
quantity the v4 paper certifies: §6 monotone decay, §7 exponential rate,
§D §E §F bounds, §10 checklist.

Panels:
    1. ERCOT   — daily, n=6   (real EIA load + Open-Meteo temp 2018–2022)
    2. FDIC    — quarterly, 30 banks × 5 features 1994–2022 (cross-bank mean)
    3. GSIB    — quarterly, 20 G-SIBs × 5 features 2005–2023 (cross-bank mean)

For each panel we report:
    a) §10 verification checklist on a representative crisis state
    b) §H.1.2 gradient FD check
    c) AUROC of canonical energy E_t against ground-truth crisis labels
    d) §7.1 exponential-decay relaxation: integrate canonical ODE from a
       crisis state X_t and measure the empirical decay rate ρ̂
"""
from __future__ import annotations
import os, sys, time, warnings
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['CUDA_VISIBLE_DEVICES'] = ''
warnings.filterwarnings('ignore')
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import roc_auc_score

from collapse_geometry.canonical import (
    CanonicalSystem, verification_checklist, verify_gradient_fd,
)

ROOT = Path(r"C:\amttp")
RES  = ROOT / "results" / "canonical_v4_panels"
RES.mkdir(parents=True, exist_ok=True)


# =======================================================================
#  Canonical wiring — §8.1 TradingDomain template, single source of truth
# =======================================================================
def build_canonical(mu: np.ndarray, Sigma: np.ndarray, kappa: float = 1.0,
                    theta: float = 1.0, ridge: float = 1e-6) -> CanonicalSystem:
    """Wire a panel into CanonicalSystem (§8.1 TradingDomain form, A=I, b=μ)."""
    n = mu.size
    S_eff = 0.5 * (Sigma + Sigma.T) + ridge * np.eye(n)
    L = np.linalg.cholesky(S_eff)
    G = np.linalg.solve(L.T, np.linalg.solve(L, np.eye(n)))   # Σ^{-1}
    I = np.eye(n)
    S      = lambda X: X - mu
    J      = lambda X: I
    F_base = lambda X: -kappa * (X - mu)
    K_zero = lambda X: np.zeros((n, n, n))    # S affine ⇒ K ≡ 0
    return CanonicalSystem(S=S, J=J, G=G, F_base=F_base,
                           theta=theta, epsilon=0.0, K=K_zero)


def fit_normal(X_normal: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (μ, Σ) on a normal-regime block with Ledoit–Wolf-light shrinkage."""
    mu = X_normal.mean(axis=0)
    Xc = X_normal - mu
    n  = X_normal.shape[1]
    S  = (Xc.T @ Xc) / max(X_normal.shape[0] - 1, 1)
    # light shrinkage to the diagonal for stability
    tau   = float(np.trace(S)) / n
    alpha = 0.10
    S = (1 - alpha) * S + alpha * tau * np.eye(n)
    return mu, S


# =======================================================================
#  Reporting helpers
# =======================================================================
def report_canonical(name: str,
                     sys_can: CanonicalSystem,
                     X_series: np.ndarray,
                     y: np.ndarray,
                     X_repr: np.ndarray,
                     X_panel3d: np.ndarray | None = None) -> dict:
    """Run the full canonical v4 audit + AUROC on a panel time series.

    If ``X_panel3d`` (T, N, d) is supplied, also reports the per-entity-max
    canonical energy E_t = max_i E(X_{t,i}) — the proper systemic-risk
    aggregator under §6 (energy non-decreasing with worst-case entity).
    """
    print(f"\n{'='*72}\n  {name}\n{'='*72}")

    # --- §10 verification checklist on a crisis state -------------------
    cl = verification_checklist(sys_can, X_repr)
    print(cl.summary())
    print(f"  all_passed = {cl.all_passed}")

    # --- §H.1.2 gradient FD check --------------------------------------
    g_chk = verify_gradient_fd(sys_can, X_repr, h=1e-6)
    print(f"  gradient FD: max_abs_err = {g_chk['max_abs_error']:.3e}  "
          f"passed = {g_chk['passed']}")

    # --- canonical energy time series  (Thm 6.6 / Lemma 6.7) -----------
    E = np.array([sys_can.energy(x) for x in X_series])
    if len(np.unique(y)) >= 2:
        auroc = float(roc_auc_score(y, E))
    else:
        auroc = float('nan')
    print(f"  E range: [{E.min():.3f}, {E.max():.3f}]   "
          f"E_normal mean = {E[y==0].mean():.3f}   "
          f"E_crisis mean = {E[y==1].mean():.3f}")
    print(f"  AUROC (canonical energy, cross-mean state): {auroc:.4f}")

    # --- per-entity-max aggregator (§6 worst-case systemic energy) -----
    auroc_max = float('nan')
    auroc_p90 = float('nan')
    if X_panel3d is not None and len(np.unique(y)) >= 2:
        T_, N_, d_ = X_panel3d.shape
        # E_{t,i} = (X_{t,i} - mu)^T G (X_{t,i} - mu)  vectorised
        mu_full = sys_can.S(np.zeros_like(X_panel3d[0,0])) * 0  # noop, mu absorbed
        # easier: just call sys_can.energy on each
        E_panel = np.zeros((T_, N_))
        for t in range(T_):
            for i in range(N_):
                xi = X_panel3d[t, i]
                if not np.all(np.isfinite(xi)):
                    E_panel[t, i] = np.nan
                else:
                    E_panel[t, i] = sys_can.energy(xi)
        E_max = np.nanmax(E_panel, axis=1)
        E_p90 = np.nanpercentile(E_panel, 90, axis=1)
        auroc_max = float(roc_auc_score(y, E_max))
        auroc_p90 = float(roc_auc_score(y, E_p90))
        print(f"  AUROC (canonical energy, per-entity MAX):  {auroc_max:.4f}")
        print(f"  AUROC (canonical energy, per-entity P90):  {auroc_p90:.4f}")

    # --- §7.1 exponential-decay relaxation from worst crisis state -----
    rho = float('nan')
    t_half = float('nan')
    if y.sum() > 0:
        i_worst = int(np.argmax(E * y))
        X0 = X_series[i_worst].astype(float).copy()
        E0 = sys_can.energy(X0)
        # Use the canonical §H.1.4 adaptive integrator (locked in core.py)
        res = sys_can.integrate(X0, h=1e-2, max_steps=20000,
                                adaptive=True,
                                eps_E=1e-12, eps_g=1e-10,
                                K_op_norm=0.0, record=True)
        E_hist = np.asarray(res.energy)
        # virtual time axis = step index * h₀ (adaptive scaling absorbed)
        t_hist = np.arange(len(E_hist)) * 1e-2
        # ρ from log-linear fit on the active decay regime
        mask = (E_hist > 1e-3 * E0) & (E_hist < E0) & np.isfinite(E_hist)
        if mask.sum() >= 5:
            slope = np.polyfit(t_hist[mask], np.log(E_hist[mask]), 1)[0]
            rho = float(-slope)
            t_half = float(np.log(2.0) / rho) if rho > 0 else float('nan')
        print(f"  §7.1 relaxation from worst crisis state "
              f"(E0={E0:.3f}): ρ̂={rho:.4f}  t_half={t_half:.4f}  "
              f"reached E={E_hist[-1]:.3e} after {res.n_steps} steps  "
              f"converged={res.converged}")

    return {
        "name": name,
        "n_state": int(X_repr.size),
        "T": int(len(X_series)),
        "n_crisis": int(y.sum()),
        "checklist_all_passed": bool(cl.all_passed),
        "gradient_fd_max_abs_err": float(g_chk['max_abs_error']),
        "gradient_fd_passed": bool(g_chk['passed']),
        "E_min": float(E.min()), "E_max": float(E.max()),
        "E_normal_mean": float(E[y==0].mean()) if (y==0).any() else float('nan'),
        "E_crisis_mean": float(E[y==1].mean()) if (y==1).any() else float('nan'),
        "auroc_canonical_energy": auroc,
        "auroc_per_entity_max": auroc_max,
        "auroc_per_entity_p90": auroc_p90,
        "rho_hat_relaxation": rho,
        "t_half": t_half,
    }


# =======================================================================
#  Panel 1 — ERCOT  (daily, n=6)
# =======================================================================
def run_ercot() -> dict:
    npz = np.load(ROOT / "data/ercot/ercot_daily_2018_2022.npz", allow_pickle=True)
    X = npz['X'].astype(np.float64)        # (1826, 6)
    y = npz['y'].astype(int)
    dates_str = np.array([str(d)[:10] for d in npz['dates']])
    # impute remaining NaNs with column mean
    for j in range(X.shape[1]):
        col = X[:, j]
        m = np.nanmean(col)
        col[np.isnan(col)] = m

    # normal regime: 2018-01-01 .. 2019-12-31, label==0
    norm_mask = (dates_str < '2020-01-01') & (y == 0)
    mu, Sigma = fit_normal(X[norm_mask])
    sys_can   = build_canonical(mu, Sigma, kappa=1.0)

    # representative crisis state: Winter Storm Uri peak day
    uri = np.where(np.array([d.startswith('2021-02-15') for d in dates_str]))[0]
    X_repr = X[uri[0]] if len(uri) else X[int(np.argmax(y))]

    return report_canonical("ERCOT (n=6, daily 2018–2022)",
                            sys_can, X, y, X_repr)


# =======================================================================
#  Panel 2 — FDIC bank-level  (quarterly, 30 banks × 5 features)
# =======================================================================
def run_fdic() -> dict:
    sys.path.insert(0, str(ROOT / "research/adaptive-friction/banklevel_enhanced"))
    from bank_level_loader import build_bank_panel
    panel = build_bank_panel(n_banks=30, force_refresh=False)
    X3 = panel['X']                    # (T, N, d)
    dates = panel['dates']
    T, N, d = X3.shape

    # Aggregate to (T, d) by cross-bank mean — keeps canonical state n=d small
    X = np.nanmean(X3, axis=1)         # (T, d)
    # forward-fill any column NaNs
    for j in range(d):
        col = X[:, j]
        last = np.nanmean(col)
        for i in range(T):
            if np.isnan(col[i]): col[i] = last
            else: last = col[i]

    # crisis labels: GFC ’07–’09, COVID ’20, Rate Shock ’22
    y = np.zeros(T, dtype=int)
    for t, dt in enumerate(dates):
        if pd.Timestamp('2007-01-01') <= dt <= pd.Timestamp('2009-12-31'): y[t] = 1
        elif pd.Timestamp('2020-01-01') <= dt <= pd.Timestamp('2020-12-31'): y[t] = 1
        elif pd.Timestamp('2022-01-01') <= dt <= pd.Timestamp('2022-12-31'): y[t] = 1

    # normal regime: 1994–2003, pre-GFC stable era, fit on per-bank-quarter rows
    norm_t = (dates < pd.Timestamp('2004-01-01')) & (y == 0)
    X_norm_rows = X3[norm_t].reshape(-1, d)
    X_norm_rows = X_norm_rows[np.all(np.isfinite(X_norm_rows), axis=1)]
    mu, Sigma = fit_normal(X_norm_rows)
    sys_can   = build_canonical(mu, Sigma, kappa=1.0)

    # representative crisis state: 2008-Q4 (Lehman quarter) or worst E
    delta = (pd.DatetimeIndex(dates) - pd.Timestamp('2008-12-31')).total_seconds().to_numpy()
    lehman_idx = int(np.argmin(np.abs(delta)))
    X_repr = X[lehman_idx]
    return report_canonical("FDIC banks (n=5, 30-bank panel, 1994–2022)",
                            sys_can, X, y, X_repr, X_panel3d=X3)


# =======================================================================
#  Panel 3 — GSIB real-data  (quarterly, 20 G-SIBs × 5 features)
# =======================================================================
def run_gsib() -> dict:
    sys.path.insert(0,
        str(ROOT / "github-repos/bsdt-systemic-risk/banklevel"))
    from gsib_loader_real import build_gsib_panel_real
    panel = build_gsib_panel_real(
        quarters_start="2005-01-01", quarters_end="2023-12-31",
        force_refresh=False, min_coverage=0.50, verbose=False,
    )
    X3 = panel['X']                                        # (T, N, d)
    dates = panel['dates']
    T, N, d = X3.shape
    X = np.nanmean(X3, axis=1)                             # (T, d)
    for j in range(d):
        col = X[:, j]; last = np.nanmean(col)
        for i in range(T):
            if np.isnan(col[i]): col[i] = last
            else: last = col[i]

    # crisis labels: GFC ’07–’09, EU sovereign ’11–’12, COVID ’20, Rate Shock ’22
    y = np.zeros(T, dtype=int)
    windows = [
        ('2007-07-01', '2009-12-31'),
        ('2011-07-01', '2012-12-31'),
        ('2020-01-01', '2020-12-31'),
        ('2022-01-01', '2023-06-30'),
    ]
    for t, dt in enumerate(dates):
        for a, b in windows:
            if pd.Timestamp(a) <= dt <= pd.Timestamp(b):
                y[t] = 1; break

    # normal regime: 2005-Q1 to 2006-Q4 (pre-GFC), per-bank-quarter rows
    norm_t = (dates < pd.Timestamp('2007-01-01')) & (y == 0)
    X_norm_rows = X3[norm_t].reshape(-1, d)
    X_norm_rows = X_norm_rows[np.all(np.isfinite(X_norm_rows), axis=1)]
    mu, Sigma = fit_normal(X_norm_rows)
    sys_can   = build_canonical(mu, Sigma, kappa=1.0)

    # representative crisis state: Lehman quarter 2008-Q4
    delta = (pd.DatetimeIndex(dates) - pd.Timestamp('2008-12-31')).total_seconds().to_numpy()
    lehman_idx = int(np.argmin(np.abs(delta)))
    X_repr = X[lehman_idx]
    return report_canonical("G-SIBs (n=5, 20-bank panel, 2005–2023)",
                            sys_can, X, y, X_repr, X_panel3d=X3)


# =======================================================================
#  Main
# =======================================================================
if __name__ == "__main__":
    t0 = time.time()
    print("=" * 72)
    print("  Canonical Dynamical Geometry System v4 — applied to real panels")
    print("  Paper: research/adaptive-friction/docs/canonical_system_v4.tex")
    print("  Wiring: §8.1 TradingDomain (S=X−μ, J=I, G=Σ⁻¹, F_base=−κ(X−μ))")
    print("=" * 72)

    out = {}
    for name, fn in [("ercot", run_ercot), ("fdic", run_fdic), ("gsib", run_gsib)]:
        try:
            out[name] = fn()
        except Exception as e:
            import traceback
            print(f"\n[{name}] FAILED: {e}")
            traceback.print_exc()
            out[name] = {"error": str(e)}

    # Summary
    print("\n" + "=" * 72)
    print("  CANONICAL v4 — SUMMARY")
    print("=" * 72)
    print(f"  {'Panel':<10}{'n':>4}{'T':>6}{'crisis':>8}{'gradFD':>10}"
          f"{'§10':>6}{'AUROCmean':>11}{'AUROCmax':>10}{'AUROCp90':>10}{'ρ̂':>8}{'t_½':>8}")
    print("  " + "-" * 90)
    for nm in ("ercot", "fdic", "gsib"):
        r = out.get(nm, {})
        if "error" in r:
            print(f"  {nm:<10}  ERROR: {r['error']}")
            continue
        print(f"  {nm:<10}{r['n_state']:>4}{r['T']:>6}{r['n_crisis']:>8}"
              f"{r['gradient_fd_max_abs_err']:>10.2e}"
              f"{'OK' if r['checklist_all_passed'] else 'X':>6}"
              f"{r['auroc_canonical_energy']:>11.4f}"
              f"{r['auroc_per_entity_max']:>10.4f}"
              f"{r['auroc_per_entity_p90']:>10.4f}"
              f"{r['rho_hat_relaxation']:>8.3f}"
              f"{r['t_half']:>8.3f}")
    print("  " + "-" * 90)

    import json
    with open(RES / "canonical_v4_panels_results.json", "w") as f:
        json.dump(out, f, indent=2,
                  default=lambda o: float(o) if hasattr(o, '__float__') else str(o))
    print(f"\n  Saved -> {RES / 'canonical_v4_panels_results.json'}")
    print(f"  Runtime: {time.time()-t0:.1f}s")
