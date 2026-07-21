"""
domain_climate_tipping.py
=========================
[STATUS] SYNTHETIC DATA — NOT USED IN PRODUCTION RESULTS.
This script generates trajectories with numpy.random and is therefore excluded
from the canonical / BSDT validation pipeline per user requirement (real data only).
Code is preserved for archival / reference purposes only; running it exits early.

Domain IX — Earth Systems: Climate Tipping Points
Canonical Engine Phase-Portrait Analysis

System  : 4 global climate subsystems (Atmosphere, Oceans, Ice Sheets, Biosphere)
Features: Temperature anomaly, Salinity/CO2, Albedo, Carbon sink capacity
Crisis  : AMOC (Atlantic Meridional Overturning Circulation) collapse at year 780

Key result: Canonical engine shows the ocean subsystem as dominant energy carrier
(δ_G feature gap) before the atmospheric "cascade tip". The Lyapunov energy
transitions from a low-dimensional attractor to a high-energy runaway manifold.

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations
import os, warnings
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

warnings.filterwarnings("ignore")

OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
os.makedirs(OUTDIR, exist_ok=True)
OUT_PNG = os.path.join(OUTDIR, "domain_climate_tipping.png")

RNG = np.random.default_rng(123)

# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN PARAMETERS
# ─────────────────────────────────────────────────────────────────────────────
N_SUBSYSTEMS = 4     # Atmosphere, Oceans, Ice Sheets, Biosphere
N_FEATURES   = 4     # Temp anomaly, CO2/salinity, Albedo, Carbon sink
T_TOTAL      = 1000  # Timesteps (each = ~3 months / 0.25 year)
T_AMOC       = 780   # AMOC collapse onset
THETA_BSDT   = 0.4

SUBSYSTEM_NAMES = ["Atmosphere", "Oceans", "Ice Sheets", "Biosphere"]
FEATURE_NAMES   = ["T anomaly", "CO₂/Salinity", "Albedo", "C-sink"]

# ─────────────────────────────────────────────────────────────────────────────
# SURROGATE CLIMATE DATA GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def generate_climate_surrogate(N: int, T: int, T_amoc: int) -> np.ndarray:
    """
    Generate climate subsystem trajectories.
    Returns (T, N, d=4) array of standardised features.

    Pre-AMOC: slow drift with multi-decadal variability (ENSO-like ~60yr)
    AMOC collapse: ocean salinity drop → global heat redistribution cascade
    """
    d = 4
    X = np.zeros((T, N, d))
    t = np.arange(T)

    # Slow periodic variability (multi-decadal oscillations)
    osc_periods = [60, 11, 7, 23]  # quasi-cycles per 250-year span

    for n in range(N):
        for fd in range(d):
            base = RNG.standard_normal(T) * 0.15   # observational noise
            for period in osc_periods[:2]:
                amp   = RNG.uniform(0.3, 0.8)
                phase = RNG.uniform(0, 2 * np.pi)
                base += amp * np.sin(2 * np.pi * t / (period * 4) + phase)
            X[:, n, fd] = base

    # Linear warming trend in T anomaly (feature 0) for Atmosphere and Oceans
    warming = np.linspace(0, 2.5, T)
    X[:, 0, 0] += warming * 0.8   # Atmosphere
    X[:, 1, 0] += warming * 0.5   # Oceans (slower)
    X[:, 2, 0] += warming * 0.3   # Ice Sheets (lagged)

    # Albedo (feature 2): Ice loss → decreasing albedo (positive feedback)
    ice_loss = np.zeros(T)
    ice_loss[T_amoc:] = np.linspace(0, 3.0, T - T_amoc)  # abrupt
    X[:, 2, 2] -= ice_loss * 1.5   # albedo drops as ice melts

    # AMOC collapse signature (Ocean salinity drop at T_amoc)
    amoc_signal = np.zeros(T)
    amoc_signal[T_amoc:] = np.linspace(0, -4.0, T - T_amoc)
    X[:, 1, 1] += amoc_signal      # Ocean CO2/salinity feature

    # Biosphere carbon sink saturation
    csink = np.zeros(T)
    csink[T_amoc:] = -np.sqrt(np.linspace(0, 6.0, T - T_amoc))
    X[:, 3, 3] += csink            # C-sink weakening

    # Cascade: Atmosphere temp spikes AFTER ocean collapse (~30 step delay)
    if T_amoc + 30 < T:
        cascade = np.zeros(T)
        cascade[T_amoc + 30:] = np.linspace(0, 5.0, T - T_amoc - 30) ** 1.3
        X[:, 0, 0] += cascade

    # Z-score
    mu  = X.mean(axis=0, keepdims=True)
    sig = X.std(axis=0,  keepdims=True) + 1e-8
    return (X - mu) / sig


# ─────────────────────────────────────────────────────────────────────────────
# CANONICAL ENGINE  (same structure as neuroscience script)
# ─────────────────────────────────────────────────────────────────────────────

def run_canonical_engine(X: np.ndarray, theta: float = THETA_BSDT) -> dict:
    T, N, d = X.shape
    G = np.ones(d)

    energy    = np.zeros(T)
    gamma     = np.zeros(T)
    cos_theta = np.zeros(T)
    delta_C   = np.zeros(T)
    delta_A   = np.zeros(T)
    delta_T   = np.zeros(T)
    delta_G   = np.zeros(T)

    ewma = np.zeros((N, d))
    ref  = np.abs(X[0]).mean(axis=0) + 1e-8

    for t in range(T):
        x = X[t]

        E   = float(np.sum(G[None, :] * x ** 2))
        energy[t] = E

        gam = E / (E + theta)
        gamma[t] = gam

        grad_E   = 2 * G[None, :] * x
        F_base   = -grad_E
        norm_F   = np.linalg.norm(F_base) + 1e-10
        norm_g   = np.linalg.norm(grad_E) + 1e-10
        cos_theta[t] = float(np.sum(F_base * grad_E) / (norm_F * norm_g))

        agent_E  = np.sum(G[None, :] * x ** 2, axis=1)
        delta_C[t] = float(np.std(agent_E) / (np.mean(agent_E) + 1e-8))

        delta_A[t] = float(np.mean(np.abs(x)) / np.mean(ref))

        alpha_ewma = 0.05
        ewma = (1 - alpha_ewma) * ewma + alpha_ewma * x
        delta_T[t] = float(np.mean(np.abs(x - ewma)))

        chan_mean = np.abs(x).mean(axis=0)
        delta_G[t] = float(np.max(chan_mean) - np.min(chan_mean))

        ref = 0.92 * ref + 0.08 * (np.abs(x).mean(axis=0) + 1e-8)

    return {
        "energy": energy, "gamma": gamma, "cos_theta": cos_theta,
        "delta_C": delta_C, "delta_A": delta_A,
        "delta_T": delta_T, "delta_G": delta_G,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PLOTTING
# ─────────────────────────────────────────────────────────────────────────────

NAVY, GOLD, RUST, TEAL = "#1f3b73", "#c9a227", "#a23a1f", "#1a5f5f"
BSDT_CLR = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3"]


def plot_results(X: np.ndarray, res: dict, T_amoc: int, out_path: str) -> None:
    T = X.shape[0]
    tvec = np.arange(T)

    Xmean = X.mean(axis=1)
    cov   = np.cov(Xmean.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    idx  = np.argsort(eigvals)[::-1]
    pc   = Xmean @ eigvecs[:, idx[:3]]

    fig = plt.figure(figsize=(18, 11), facecolor="white")
    fig.suptitle(
        "Domain IX — Earth Systems: Climate Tipping Points\n"
        "Canonical BSDT Phase-Portrait  ·  N=4 subsystems  ·  d=4 features  ·  "
        "AMOC collapse t=780",
        fontsize=13, weight="bold", color=NAVY, y=0.98)

    gs = GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.35,
                  top=0.90, bottom=0.06, left=0.07, right=0.97)

    ax1 = fig.add_subplot(gs[0, 0])
    sc  = ax1.scatter(pc[:, 0], pc[:, 1], c=res["gamma"],
                      cmap="plasma", s=4, alpha=0.7)
    ax1.scatter(pc[T_amoc, 0], pc[T_amoc, 1], c="red",
                s=80, marker="*", zorder=5, label=f"AMOC t={T_amoc}")
    fig.colorbar(sc, ax=ax1, shrink=0.8, label="γ")
    ax1.set_xlabel("PC1"); ax1.set_ylabel("PC2")
    ax1.set_title("Phase Portrait (PC1 × PC2)", fontsize=9, weight="bold")
    ax1.legend(fontsize=7)

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(tvec, res["energy"], color=NAVY, lw=1.2)
    ax2.axvline(T_amoc, color=RUST, ls="--", lw=1.5, label="AMOC collapse")
    ax2.set_xlabel("Time (quarter-yr)"); ax2.set_ylabel("E(t)")
    ax2.set_title("Lyapunov Energy E(t)", fontsize=9, weight="bold")
    ax2.legend(fontsize=7)

    ax3 = fig.add_subplot(gs[0, 2], projection="3d")
    sc3 = ax3.scatter(pc[:, 0], pc[:, 1], pc[:, 2],
                      c=np.log10(res["energy"] + 1), cmap="viridis",
                      s=3, alpha=0.6)
    ax3.scatter([pc[T_amoc, 0]], [pc[T_amoc, 1]], [pc[T_amoc, 2]],
                c="red", s=60, marker="*")
    ax3.set_xlabel("PC1", fontsize=7); ax3.set_ylabel("PC2", fontsize=7)
    ax3.set_zlabel("PC3", fontsize=7)
    ax3.set_title("3D State Cloud (PC1·PC2·PC3)", fontsize=9, weight="bold")

    ax4 = fig.add_subplot(gs[1, :2])
    for i, (key, lbl) in enumerate([
            ("delta_C", "δ_C Camouflage"),
            ("delta_A", "δ_A Activity"),
            ("delta_T", "δ_T Temporal"),
            ("delta_G", "δ_G Feature Gap")]):
        arr  = res[key]
        norm_arr = (arr - arr.min()) / (arr.max() - arr.min() + 1e-8)
        ax4.plot(tvec, norm_arr, color=BSDT_CLR[i], lw=1.2, label=lbl, alpha=0.85)
    ax4.axvline(T_amoc, color=RUST, ls="--", lw=1.5, label="AMOC collapse")
    ax4.set_xlabel("Time (quarter-yr)"); ax4.set_ylabel("Normalised channel")
    ax4.set_title("BSDT Channel Decomposition", fontsize=9, weight="bold")
    ax4.legend(fontsize=7, ncol=3)

    ax5 = fig.add_subplot(gs[1, 2])
    sc5 = ax5.scatter(res["cos_theta"], res["gamma"],
                      c=np.log10(res["energy"] + 1), cmap="viridis", s=4, alpha=0.6)
    fig.colorbar(sc5, ax=ax5, shrink=0.8, label="log₁₀E")
    ax5.set_xlabel("cos θ"); ax5.set_ylabel("γ")
    ax5.set_title("Alignment-Commitment Manifold", fontsize=9, weight="bold")

    ax6 = fig.add_subplot(gs[2, :2])
    channels   = ["δ_C", "δ_A", "δ_T", "δ_G"]
    post_means = [
        res["delta_C"][T_amoc:].mean(),
        res["delta_A"][T_amoc:].mean(),
        res["delta_T"][T_amoc:].mean(),
        res["delta_G"][T_amoc:].mean(),
    ]
    total   = sum(post_means) + 1e-8
    weights = [v / total for v in post_means]
    bars    = ax6.bar(channels, weights, color=BSDT_CLR, width=0.5, alpha=0.85)
    ax6.set_ylabel("Fisher-VR weight"); ax6.set_xlabel("BSDT Channel")
    ax6.set_title("Post-AMOC Channel Dominance", fontsize=9, weight="bold")
    for bar, w in zip(bars, weights):
        ax6.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.003,
                 f"{w:.3f}", ha="center", fontsize=8)

    ax7 = fig.add_subplot(gs[2, 2])
    ax7.axis("off")
    mu_pre  = res["energy"][:T_amoc].mean()
    sd_pre  = res["energy"][:T_amoc].std() + 1e-8
    z       = (res["energy"] - mu_pre) / sd_pre
    hits    = np.where(z[:T_amoc] > 2.0)[0]
    first_a = hits[0] if len(hits) > 0 else T_amoc
    lead    = T_amoc - first_a
    dom_ch  = channels[int(np.argmax(weights))]

    summary = (
        f"Domain IX — Climate Tipping Points\n"
        f"{'─'*32}\n"
        f"Subsystems (N): 4\n"
        f"Features (d):   4 (T, CO₂, Albedo, C-sink)\n"
        f"Timesteps (T):  {T_TOTAL}\n"
        f"Crisis:         AMOC collapse t={T_amoc}\n\n"
        f"First alarm:    t={first_a}\n"
        f"Lead time:      +{lead} quarters\n\n"
        f"Peak E:         {res['energy'].max():.2f}\n"
        f"Peak γ:         {res['gamma'].max():.4f}\n"
        f"Dom. channel:   {dom_ch}\n"
        f"Fisher-w:        {max(weights):.3f}"
    )
    ax7.text(0.05, 0.97, summary, transform=ax7.transAxes,
             fontsize=8.5, va="top", ha="left", family="monospace",
             color=NAVY, bbox=dict(boxstyle="round,pad=0.5", fc="#f5f0e8", ec=GOLD))

    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Domain IX — Climate Tipping Points (AMOC Collapse)")
    print("  Generating surrogate climate data...")
    X = generate_climate_surrogate(N_SUBSYSTEMS, T_TOTAL, T_AMOC)
    print(f"  X shape: {X.shape}  min={X.min():.2f}  max={X.max():.2f}")

    print("  Running Canonical BSDT Engine...")
    res = run_canonical_engine(X)

    mu_pre = res["energy"][:T_AMOC].mean()
    sd_pre = res["energy"][:T_AMOC].std() + 1e-8
    z      = (res["energy"] - mu_pre) / sd_pre
    hits   = np.where(z[:T_AMOC] > 2.0)[0]
    first_a = hits[0] if len(hits) > 0 else T_AMOC
    lead    = T_AMOC - first_a

    print(f"  Peak energy:   {res['energy'].max():.2f}")
    print(f"  Peak gamma:    {res['gamma'].max():.4f}")
    print(f"  First alarm:   t={first_a}")
    print(f"  Lead time:     +{lead} quarters before AMOC onset")

    print("  Plotting...")
    plot_results(X, res, T_AMOC, OUT_PNG)
    print("Done.")


if __name__ == "__main__":
    import sys as _sys
    print("[SKIPPED] domain_climate_tipping.py uses synthetic data (np.random) and is"
          " excluded from production canonical/BSDT results per user requirement.",
          file=_sys.stderr)
    _sys.exit(0)
    # Original main retained below for archival purposes.
    main()
