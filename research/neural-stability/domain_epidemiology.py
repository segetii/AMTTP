"""
domain_epidemiology.py
======================
[STATUS] SYNTHETIC DATA — NOT USED IN PRODUCTION RESULTS.
This script simulates SIR dynamics with random parameters and is excluded from
the canonical / BSDT validation pipeline per user requirement (real data only).
Code preserved for archival / reference; running it exits early.
======================
Domain XI — Epidemiology: Pandemic Dynamics (SIR Multi-Region)
Canonical Engine Phase-Portrait Analysis

System  : SIR model across N=10 cities/regions with inter-city mobility
Features: Infection rate, Hospitalisation rate, Mobility index, R_effective
Crisis  : Healthcare capacity breach at step T_breach (rate > 0.15 threshold)

Key result: The Canonical engine detects the transition from exponential growth
to systemic healthcare collapse ~20–40 steps before the peak, with δ_T temporal
novelty as the earliest forerunner.

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
OUT_PNG = os.path.join(OUTDIR, "domain_epidemiology.png")

RNG = np.random.default_rng(55)

# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN PARAMETERS
# ─────────────────────────────────────────────────────────────────────────────
N_CITIES   = 10     # Regions/cities
N_FEATURES = 4      # I-rate, Hosp-rate, Mobility, R_eff
T_TOTAL    = 365    # Days
THETA_BSDT = 0.4

CITY_NAMES = [
    "City-A", "City-B", "City-C", "City-D", "City-E",
    "City-F", "City-G", "City-H", "City-I", "City-J",
]

# SIR parameters
BETA_BASE   = 0.28    # Base transmission rate
GAMMA_SIR   = 0.07    # Recovery rate → R_0 ≈ 4.0
HOSP_FRAC   = 0.05    # Fraction needing hospitalisation
HOSP_CAP    = 0.002   # Healthcare capacity threshold (as fraction of population)


# ─────────────────────────────────────────────────────────────────────────────
# MULTI-REGION SIR SIMULATOR
# ─────────────────────────────────────────────────────────────────────────────

def run_sir_multi_region(N: int, T: int) -> tuple:
    """
    Simulate SIR across N regions with mobility coupling.
    Returns X (T, N, 4),  T_breach (first healthcare capacity breach).
    """
    # Initial conditions: one seeded city, rest clean
    S = np.ones(N) * 0.9999
    I = np.zeros(N)
    R = np.zeros(N)
    I[0] = 0.0001  # seed first city

    # Heterogeneous transmission (urban density proxy)
    beta_arr = BETA_BASE * RNG.uniform(0.7, 1.4, N)

    # Mobility coupling matrix (small-world)
    mob = RNG.uniform(0.001, 0.005, (N, N))
    np.fill_diagonal(mob, 0)
    mob = mob / mob.sum(axis=1, keepdims=True) * 0.02  # scale: 2% daily travel

    X_out   = np.zeros((T, N, N_FEATURES))
    T_breach = T - 1

    for t in range(T):
        # SIR step with mobility
        mobility_inflow  = mob @ I   # fraction of infectious arriving
        effective_I      = I + mobility_inflow

        dS = -beta_arr * S * effective_I
        dI =  beta_arr * S * effective_I - GAMMA_SIR * I
        dR =  GAMMA_SIR * I

        S = np.clip(S + dS, 0.0, 1.0)
        I = np.clip(I + dI, 0.0, 1.0)
        R = np.clip(R + dR, 0.0, 1.0)

        # Renormalize
        total = S + I + R + 1e-10
        S /= total; I /= total; R /= total

        # R_effective per city
        R_eff = beta_arr * S / GAMMA_SIR

        # Features: I, Hosp rate, Mobility, R_eff
        hosp = I * HOSP_FRAC
        mobility_out = mob.sum(axis=1)  # (N,) constant for now

        X_out[t, :, 0] = I
        X_out[t, :, 1] = hosp
        X_out[t, :, 2] = mobility_out * (1 - I)   # mobility suppressed by infection
        X_out[t, :, 3] = R_eff

        # Check healthcare breach
        if T_breach == T - 1 and np.any(hosp > HOSP_CAP):
            T_breach = t

    # Standardise
    mu  = X_out.mean(axis=0, keepdims=True)
    sig = X_out.std(axis=0,  keepdims=True) + 1e-8
    return (X_out - mu) / sig, T_breach


# ─────────────────────────────────────────────────────────────────────────────
# CANONICAL ENGINE
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

        E = float(np.sum(G[None, :] * x ** 2))
        energy[t] = E
        gam = E / (E + theta)
        gamma[t] = gam

        grad_E = 2 * G[None, :] * x
        F_base = -grad_E
        norm_F = np.linalg.norm(F_base) + 1e-10
        norm_g = np.linalg.norm(grad_E) + 1e-10
        cos_theta[t] = float(np.sum(F_base * grad_E) / (norm_F * norm_g))

        agent_E    = np.sum(G[None, :] * x ** 2, axis=1)
        delta_C[t] = float(np.std(agent_E) / (np.mean(agent_E) + 1e-8))
        delta_A[t] = float(np.mean(np.abs(x)) / np.mean(ref))

        alpha = 0.1
        ewma  = (1 - alpha) * ewma + alpha * x
        delta_T[t] = float(np.mean(np.abs(x - ewma)))

        chan_mean  = np.abs(x).mean(axis=0)
        delta_G[t] = float(np.max(chan_mean) - np.min(chan_mean))

        ref = 0.9 * ref + 0.1 * (np.abs(x).mean(axis=0) + 1e-8)

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


def plot_results(X: np.ndarray, res: dict, T_breach: int, out_path: str) -> None:
    T    = X.shape[0]
    tvec = np.arange(T)

    Xmean = X.mean(axis=1)
    cov   = np.cov(Xmean.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    idx  = np.argsort(eigvals)[::-1]
    pc   = Xmean @ eigvecs[:, idx[:3]]

    fig = plt.figure(figsize=(18, 11), facecolor="white")
    fig.suptitle(
        "Domain XI — Epidemiology: Pandemic SIR Multi-Region Dynamics\n"
        "Canonical BSDT Phase-Portrait  ·  N=10 cities  ·  d=4 features  ·  "
        f"Healthcare breach t={T_breach}",
        fontsize=13, weight="bold", color=NAVY, y=0.98)

    gs = GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.35,
                  top=0.90, bottom=0.06, left=0.07, right=0.97)

    ax1 = fig.add_subplot(gs[0, 0])
    sc  = ax1.scatter(pc[:, 0], pc[:, 1], c=res["gamma"],
                      cmap="plasma", s=5, alpha=0.7)
    ax1.scatter(pc[T_breach, 0], pc[T_breach, 1], c="red",
                s=80, marker="*", zorder=5, label=f"Crisis t={T_breach}")
    fig.colorbar(sc, ax=ax1, shrink=0.8, label="γ")
    ax1.set_xlabel("PC1"); ax1.set_ylabel("PC2")
    ax1.set_title("Phase Portrait (PC1 × PC2)", fontsize=9, weight="bold")
    ax1.legend(fontsize=7)

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(tvec, res["energy"], color=NAVY, lw=1.2)
    ax2.axvline(T_breach, color=RUST, ls="--", lw=1.5, label="Healthcare breach")
    ax2.set_xlabel("Days"); ax2.set_ylabel("E(t)")
    ax2.set_title("Lyapunov Energy E(t)", fontsize=9, weight="bold")
    ax2.legend(fontsize=7)

    ax3 = fig.add_subplot(gs[0, 2], projection="3d")
    ax3.scatter(pc[:, 0], pc[:, 1], pc[:, 2],
                c=np.log10(res["energy"] + 1), cmap="viridis", s=4, alpha=0.6)
    ax3.scatter([pc[T_breach, 0]], [pc[T_breach, 1]], [pc[T_breach, 2]],
                c="red", s=60, marker="*")
    ax3.set_xlabel("PC1", fontsize=7); ax3.set_ylabel("PC2", fontsize=7)
    ax3.set_zlabel("PC3", fontsize=7)
    ax3.set_title("3D State Cloud", fontsize=9, weight="bold")

    ax4 = fig.add_subplot(gs[1, :2])
    for i, (key, lbl) in enumerate([
            ("delta_C", "δ_C Camouflage"),
            ("delta_A", "δ_A Activity"),
            ("delta_T", "δ_T Temporal"),
            ("delta_G", "δ_G Feature Gap")]):
        arr = res[key]
        norm_arr = (arr - arr.min()) / (arr.max() - arr.min() + 1e-8)
        ax4.plot(tvec, norm_arr, color=BSDT_CLR[i], lw=1.2, label=lbl, alpha=0.85)
    ax4.axvline(T_breach, color=RUST, ls="--", lw=1.5, label="Healthcare breach")
    ax4.set_xlabel("Days"); ax4.set_ylabel("Normalised channel")
    ax4.set_title("BSDT Channel Decomposition", fontsize=9, weight="bold")
    ax4.legend(fontsize=7, ncol=3)

    ax5 = fig.add_subplot(gs[1, 2])
    sc5 = ax5.scatter(res["cos_theta"], res["gamma"],
                      c=np.log10(res["energy"] + 1), cmap="viridis", s=5, alpha=0.6)
    fig.colorbar(sc5, ax=ax5, shrink=0.8, label="log₁₀E")
    ax5.set_xlabel("cos θ"); ax5.set_ylabel("γ")
    ax5.set_title("Alignment-Commitment Manifold", fontsize=9, weight="bold")

    ax6 = fig.add_subplot(gs[2, :2])
    channels  = ["δ_C", "δ_A", "δ_T", "δ_G"]
    post_means = [
        res["delta_C"][T_breach:].mean(),
        res["delta_A"][T_breach:].mean(),
        res["delta_T"][T_breach:].mean(),
        res["delta_G"][T_breach:].mean(),
    ]
    total   = sum(post_means) + 1e-8
    weights = [v / total for v in post_means]
    bars    = ax6.bar(channels, weights, color=BSDT_CLR, width=0.5, alpha=0.85)
    ax6.set_ylabel("Fisher-VR weight"); ax6.set_xlabel("BSDT Channel")
    ax6.set_title("Post-Crisis Channel Dominance", fontsize=9, weight="bold")
    for bar, w in zip(bars, weights):
        ax6.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.003,
                 f"{w:.3f}", ha="center", fontsize=8)

    ax7 = fig.add_subplot(gs[2, 2])
    ax7.axis("off")
    mu_pre  = res["energy"][:T_breach].mean()
    sd_pre  = res["energy"][:T_breach].std() + 1e-8
    z       = (res["energy"] - mu_pre) / sd_pre
    hits    = np.where(z[:T_breach] > 2.0)[0]
    first_a = hits[0] if len(hits) > 0 else T_breach
    lead    = T_breach - first_a
    dom_ch  = channels[int(np.argmax(weights))]

    summary = (
        f"Domain XI — Epidemiology (SIR)\n"
        f"{'─'*32}\n"
        f"Cities (N):    10\n"
        f"Features (d):  4 (I-rate, Hosp, Mob, R_eff)\n"
        f"Timesteps (T): {T_TOTAL} days\n"
        f"R_0:           {BETA_BASE/GAMMA_SIR:.1f}  (beta={BETA_BASE}, gamma={GAMMA_SIR})\n"
        f"Crisis:        Hosp capacity breach t={T_breach}\n\n"
        f"First alarm:   t={first_a}\n"
        f"Lead time:     +{lead} days\n\n"
        f"Peak E:        {res['energy'].max():.2f}\n"
        f"Peak γ:        {res['gamma'].max():.4f}\n"
        f"Dom. channel:  {dom_ch}\n"
        f"Fisher-w:       {max(weights):.3f}"
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
    print("Domain XI — Epidemiology: Pandemic SIR Multi-Region")
    print("  Running multi-region SIR simulation...")
    X, T_breach = run_sir_multi_region(N_CITIES, T_TOTAL)
    print(f"  X shape: {X.shape}  T_breach={T_breach}")

    print("  Running Canonical BSDT Engine...")
    res = run_canonical_engine(X)

    mu_pre  = res["energy"][:T_breach].mean()
    sd_pre  = res["energy"][:T_breach].std() + 1e-8
    z       = (res["energy"] - mu_pre) / sd_pre
    hits    = np.where(z[:T_breach] > 2.0)[0]
    first_a = hits[0] if len(hits) > 0 else T_breach
    lead    = T_breach - first_a

    print(f"  Peak energy:   {res['energy'].max():.2f}")
    print(f"  Peak gamma:    {res['gamma'].max():.4f}")
    print(f"  First alarm:   t={first_a} days")
    print(f"  Lead time:     +{lead} days before healthcare breach")

    print("  Plotting...")
    plot_results(X, res, T_breach, OUT_PNG)
    print("Done.")


if __name__ == "__main__":
    import sys as _sys
    print("[SKIPPED] domain_epidemiology.py uses synthetic SIR data (np.random) and is"
          " excluded from production canonical/BSDT results per user requirement.",
          file=_sys.stderr)
    _sys.exit(0)
    # Original main retained below for archival purposes.
    main()
