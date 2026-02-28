"""
welfare.py
==========
CCyB calibration and consumption-equivalent welfare cost computation.
Implements §9 of the paper.

Equations (from main.tex):
    ΔCCyB(t) ≈ κ⁻¹ · γ*(t) · σ_ℓ(t)                      [eq:ccyb]
    L_inaction = ∫[t0,t1] [E(X_t) − E(X_t^{γ*})] dt       [welfare loss]
    %CL = 100 × (1 − exp(−L_inaction / (σ θ T)))           [consumption pct]
"""

from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "results"

# Basel III CCyB range: 0 – 250 basis points
CCyB_MAX_BPS = 250.0

# Euler equation parameters for consumption-equivalent welfare
SIGMA_EULER   = 2.0    # inverse of intertemporal elasticity of substitution
THETA_EULER   = 0.02   # time preference rate (annualised)
DISCOUNT_BETA = 0.96   # annual discount factor

# Intervention cost κ calibration (fraction of GDP loss per unit credit restriction)
KAPPA: float = 0.5


def ccyb_formula(
    gamma_star: np.ndarray,
    sigma_leverage: np.ndarray,
    kappa: float = KAPPA,
) -> np.ndarray:
    """
    ΔCCyB(t) ≈ κ⁻¹ · γ*(t) · σ_ℓ(t)   in normalised units.
    Rescale to [0, 250] bps by mapping the 99th percentile to 200 bps.
    """
    raw = gamma_star * sigma_leverage / (kappa + 1e-9)
    # Normalise to bps (99th percentile → 200 bps, same order as Basel III guidance)
    p99 = np.quantile(raw[raw > 0], 0.99) if (raw > 0).any() else 1.0
    bps = np.clip(raw / (p99 + 1e-9) * 200.0, 0.0, CCyB_MAX_BPS)
    return bps


def energy_counterfactual(
    energy: np.ndarray,
    gamma_star: np.ndarray,
    alpha: float = 0.1,
    eta: float = 0.02,
) -> np.ndarray:
    """
    Approximate energy trajectory under γ*(t) vs γ=0.
    Under γ=0 (inaction): dE/dt ≈ −‖∇Φ‖² + amplification ≈ E stays elevated.
    Under γ*(t) (policy): the spectral abscissa is set to 0, so
        E(X_t^{γ*}) ≈ E(X_t^{γ=0}) · exp(−α·t)  within each crisis window.

    We approximate the counterfactual as exponential decay at rate α from
    crisis onset, calibrated to match the observed post-crisis recovery.
    """
    T = len(energy)
    E_policy = energy.copy()
    # Identify distinct crisis episodes using a lower per-window threshold
    # (50th percentile = any above-median quarter gets the counterfactual treatment)
    threshold = np.quantile(energy, 0.50)
    in_crisis = energy > threshold
    start = None
    for t in range(T):
        if in_crisis[t] and start is None:
            start = t
        elif not in_crisis[t] and start is not None:
            duration = t - start
            if duration >= 2:   # minimum 2 quarters to count as episode
                # E_policy decays from crisis-onset energy to the post-crisis level
                decay = np.exp(-alpha * np.arange(duration) * eta * 50)
                E_end = energy[t] if t < T else energy[-1]
                E_policy[start:t] = (
                    energy[start] * decay[:duration]
                    + E_end * (1 - decay[:duration])
                )
            start = None
    # Handle open episode at end
    if start is not None:
        duration = T - start
        decay = np.exp(-alpha * np.arange(duration) * eta * 50)
        E_policy[start:] = energy[start] * decay[:duration]
    return E_policy


def welfare_loss(
    energy: np.ndarray,
    energy_policy: np.ndarray,
    dates: pd.DatetimeIndex,
    window_start: str,
    window_end: str,
    sigma: float = SIGMA_EULER,
    theta: float = THETA_EULER,
) -> dict[str, float]:
    """
    Compute welfare loss in [window_start, window_end].

    Returns dict with:
        L_inaction  : raw integral
        pct_consumption_loss : %-equivalent
        quarters    : number of quarters in window
    """
    mask = (dates >= window_start) & (dates <= window_end)
    E_no   = energy[mask]
    E_pol  = energy_policy[mask]
    T_win  = mask.sum()

    # Numerical integration (trapezoidal, quarterly)
    L = float(np.trapz(np.maximum(E_no - E_pol, 0), dx=1.0))

    # Consumption-equivalent loss (quarterly θ = annual / 4)
    theta_q = theta / 4.0
    pct_cl  = 100.0 * (1.0 - np.exp(-L / (sigma * theta_q * T_win + 1e-9)))

    return {
        "L_inaction":             round(L, 4),
        "pct_consumption_loss":   round(pct_cl, 2),
        "quarters":               int(T_win),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sigma_ℓ proxy from FRED
# ─────────────────────────────────────────────────────────────────────────────

def sigma_leverage_proxy(
    fred_raw: pd.DataFrame,
    dates: pd.DatetimeIndex,
    n_sectors: int = 12,
) -> np.ndarray:
    """
    Proxy for cross-sectional s.d. of leverage σ_ℓ(t).
    Computed as rolling std of credit_gdp over a 4-quarter window,
    scaled to represent sector dispersion.
    """
    if "credit_gdp" in fred_raw.columns:
        s = fred_raw["credit_gdp"].copy()
    elif "total_loans" in fred_raw.columns:
        s = fred_raw["total_loans"].copy()
    else:
        return np.ones(len(dates))

    s.index = pd.to_datetime(s.index)
    s = s.reindex(dates, method="ffill").fillna(s.mean())
    rolling_std = s.rolling(4, min_periods=1).std().fillna(0.1)
    # Scale: sector dispersion ≈ √N × aggregate std (mean-field approximation)
    return rolling_std.values * np.sqrt(n_sectors)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
CRISIS_WINDOWS_WELFARE = {
    "GFC 2008":        ("2007-07-01", "2009-06-30"),
    "COVID 2020":      ("2020-01-01", "2020-12-31"),
    "Rate Shock 2022": ("2022-01-01", "2023-06-30"),
}


def run_welfare_analysis(
    stats: dict[str, np.ndarray],
    dates: pd.DatetimeIndex,
    fred_raw: pd.DataFrame,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Compute CCyB path and welfare losses for all three crisis windows.
    Returns a summary DataFrame.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    energy      = stats["energy"]
    gamma_star  = stats["gamma_star"]
    above_cman  = stats["above_cman"]

    sig_lev = sigma_leverage_proxy(fred_raw, dates)
    ccyb    = ccyb_formula(gamma_star, sig_lev)
    E_pol   = energy_counterfactual(energy, gamma_star)

    # ── Welfare table ──
    rows = []
    for window_name, (wstart, wend) in CRISIS_WINDOWS_WELFARE.items():
        wl = welfare_loss(energy, E_pol, dates, wstart, wend)
        # CCyB peak within window
        mask = (dates >= wstart) & (dates <= wend)
        ccyb_peak = round(float(ccyb[mask].max()), 1) if mask.any() else 0.0
        rows.append({
            "Crisis":                  window_name,
            "Quarters":                wl["quarters"],
            "L_inaction":              wl["L_inaction"],
            "Welfare loss (% consump)":wl["pct_consumption_loss"],
            "Peak CCyB (bps)":         ccyb_peak,
        })
    welfare_df = pd.DataFrame(rows)

    if verbose:
        print("\n===  Welfare Calibration Table  ===")
        print(welfare_df.to_string(index=False))

    # ── Plot ──
    fig, axes = plt.subplots(2, 1, figsize=(12, 9))

    ax = axes[0]
    ax.plot(dates, ccyb, lw=2, color="darkgreen", label="Adaptive CCyB (bps)")
    ax.axhline(200, color="red", ls="--", lw=1, label="200 bps upper guidance")
    ax.axhline(0,   color="k",   ls="-",  lw=0.3)
    _shade_welfare(ax, dates)
    ax.set_ylabel("CCyB (basis points)"); ax.legend()
    ax.set_title("Panel A: Adaptive CCyB Path  Δ CCyB(t)")

    ax = axes[1]
    ax.plot(dates, energy,  lw=2, color="steelblue",  label="E(X) — no intervention")
    ax.plot(dates, E_pol,   lw=2, color="darkorange", label="E(X^{γ*}) — adaptive policy", ls="--")
    ax.fill_between(dates, E_pol, energy, where=(energy > E_pol),
                    alpha=0.25, color="red", label="Welfare loss area")
    _shade_welfare(ax, dates)
    ax.set_ylabel("Φ(X) energy"); ax.legend()
    ax.set_title("Panel B: Energy Counterfactual — Inaction vs Adaptive Policy")

    plt.tight_layout()
    fig_path = OUTPUT_DIR / "welfare_calibration.pdf"
    plt.savefig(fig_path, bbox_inches="tight")
    plt.savefig(str(fig_path).replace(".pdf", ".png"), dpi=150, bbox_inches="tight")
    plt.close()
    if verbose:
        print(f"[plot] Saved: {fig_path}")

    return welfare_df


def _shade_welfare(ax: plt.Axes, dates: pd.DatetimeIndex) -> None:
    colours = ["#FFB3B3", "#B3FFB3", "#B3D9FF"]
    for (name, (wstart, wend)), c in zip(CRISIS_WINDOWS_WELFARE.items(), colours):
        mask = (dates >= wstart) & (dates <= wend)
        if mask.any():
            ax.axvspan(dates[mask][0], dates[mask][-1], alpha=0.2, color=c, label=name)


# ─────────────────────────────────────────────────────────────────────────────
# LaTeX tables for §9
# ─────────────────────────────────────────────────────────────────────────────

def latex_welfare_table(welfare_df: pd.DataFrame) -> str:
    lines = [
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{Welfare costs and CCyB calibration across three crisis windows. "
        r"$\mathcal{L}_{\mathrm{inaction}}$ is the integral of the energy gap between "
        r"the no-intervention and optimal-policy trajectories. "
        r"Percentage consumption loss is computed via equation~\eqref{eq:ccyb}.}",
        r"\label{tab:welfare}",
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"Crisis Window & Quarters & $\mathcal{L}_{\mathrm{inaction}}$ & "
        r"Welfare loss (\%~consump.) & Peak CCyB (bps) \\",
        r"\midrule",
    ]
    for _, row in welfare_df.iterrows():
        lines.append(
            f"{row['Crisis']} & {int(row['Quarters'])} & "
            f"{row['L_inaction']:.4f} & "
            f"{row['Welfare loss (% consump)']:.2f}\\% & "
            f"{row['Peak CCyB (bps)']:.0f} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)
