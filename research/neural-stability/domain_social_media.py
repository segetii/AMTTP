"""
domain_social_media.py
======================
Domain XII — Social Media: Polarisation & Misinformation Virality
Canonical Engine Phase-Portrait Analysis
[STATUS] SYNTHETIC DATA — NOT USED IN PRODUCTION RESULTS.
This script generates synthetic engagement signals with numpy.random and is excluded
from the canonical / BSDT validation pipeline per user requirement (real data only).
Code preserved for archival; running it exits early.

System  : 8 social media clusters (ideological communities)
Features: Post volume, sentiment polarity, cross-pollination ratio, new user influx
Crisis  : Viral outrage event / echo-chamber formation lock-in at step T_viral

Key result: As communities polarise, state vectors align in phase space — a
dramatic collapse into a low-dimensional "outrage manifold". The δ_C camouflage
channel is the dominant precursor: misinformation hides inside normal traffic
patterns before virality detonates.

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
OUT_PNG = os.path.join(OUTDIR, "domain_social_media.png")

RNG = np.random.default_rng(88)

# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN PARAMETERS
# ─────────────────────────────────────────────────────────────────────────────
N_CLUSTERS = 8      # Social communities
N_FEATURES = 4      # Post volume, Sentiment polarity, Cross-pollination, New users
T_TOTAL    = 500    # Hours
T_VIRAL    = 350    # Viral outrage event onset
T_SEED     = 200    # When misinformation seed is planted (covert phase)
THETA_BSDT = 0.35

CLUSTER_NAMES = [
    "Mainstream-L", "Mainstream-R", "Fringe-L", "Fringe-R",
    "Moderate-L",  "Moderate-R",  "Bot-Network", "Amplifier"
]


# ─────────────────────────────────────────────────────────────────────────────
# SURROGATE SOCIAL MEDIA DYNAMICS
# ─────────────────────────────────────────────────────────────────────────────

def generate_social_surrogate(N: int, T: int, T_seed: int, T_viral: int) -> np.ndarray:
    """
    Generate social media cluster trajectories with misinformation virality.
    Returns (T, N, d=4) standardised array.

    Phase 1 (0–T_seed)     : Normal organic activity
    Phase 2 (T_seed–T_viral): Covert seeding — low visibility, bot-injected
    Phase 3 (T_viral–T)    : Viral cascade — cross-pollination explosion,
                             echo chamber lock-in
    """
    d = 4
    X = np.zeros((T, N, d))
    t_vec = np.arange(T)

    for n in range(N):
        # Feature 0: Post volume (baseline + circadian rhythm)
        vol_baseline = RNG.uniform(0.5, 2.0)
        X[:, n, 0] = vol_baseline + 0.3 * np.sin(2 * np.pi * t_vec / 24 + RNG.uniform(0, 2*np.pi))
        X[:, n, 0] += RNG.standard_normal(T) * 0.1

        # Feature 1: Sentiment polarity ([-1,1], baseline near 0)
        pol_rng = RNG.uniform(-0.3, 0.3)
        X[:, n, 1] = pol_rng + RNG.standard_normal(T) * 0.1

        # Feature 2: Cross-pollination ratio (0.05 baseline)
        X[:, n, 2] = 0.05 + RNG.standard_normal(T) * 0.01

        # Feature 3: New user influx (slow background)
        X[:, n, 3] = 0.02 + RNG.standard_normal(T) * 0.005

    # ── Covert seeding phase (T_seed to T_viral) ──
    # Bot network and amplifier cluster see covert volume injection
    # that camouflages as normal activity
    bot_idx = CLUSTER_NAMES.index("Bot-Network") % N
    amp_idx = CLUSTER_NAMES.index("Amplifier")   % N

    for n in [bot_idx, amp_idx]:
        seed_ramp = np.zeros(T)
        seed_ramp[T_seed:T_viral] = np.linspace(0, 0.4, T_viral - T_seed)
        X[:, n, 2] += seed_ramp   # stealth cross-pollination
        X[:, n, 0] += seed_ramp * 0.3   # slightly elevated volume

    # ── Viral cascade (T_viral to T) ──
    for n in range(N):
        viral_amp = RNG.uniform(1.5, 4.0)
        viral  = np.zeros(T)
        viral[T_viral:] = viral_amp * np.sqrt(np.linspace(0, 1.0, T - T_viral))
        X[:, n, 0] += viral            # volume explosion

        # Sentiment polarisation (clusters diverge in ±1 direction)
        pol_dir = 1.0 if n % 2 == 0 else -1.0
        pol_spike = np.zeros(T)
        pol_spike[T_viral:] = pol_dir * np.linspace(0, 0.9, T - T_viral)
        X[:, n, 1] += pol_spike

        # Cross-pollination increases dramatically
        xp = np.zeros(T)
        xp[T_viral:] = np.linspace(0, 0.8, T - T_viral) ** 1.5
        X[:, n, 2] += xp

        # New user influx from viral spread
        nu = np.zeros(T)
        nu[T_viral:] = 0.2 * np.sqrt(np.linspace(0, 1.0, T - T_viral))
        X[:, n, 3] += nu

    # Z-score
    mu  = X.mean(axis=0, keepdims=True)
    sig = X.std(axis=0,  keepdims=True) + 1e-8
    return (X - mu) / sig


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

        alpha = 0.08
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


def plot_results(X: np.ndarray, res: dict, T_seed: int, T_viral: int,
                 out_path: str) -> None:
    T    = X.shape[0]
    tvec = np.arange(T)

    Xmean = X.mean(axis=1)
    cov   = np.cov(Xmean.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    idx  = np.argsort(eigvals)[::-1]
    pc   = Xmean @ eigvecs[:, idx[:3]]

    fig = plt.figure(figsize=(18, 11), facecolor="white")
    fig.suptitle(
        "Domain XII — Social Media: Polarisation & Misinformation Virality\n"
        "Canonical BSDT Phase-Portrait  ·  N=8 clusters  ·  d=4 features  ·  "
        f"Covert seed t={T_seed}  ·  Viral onset t={T_viral}",
        fontsize=13, weight="bold", color=NAVY, y=0.98)

    gs = GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.35,
                  top=0.90, bottom=0.06, left=0.07, right=0.97)

    ax1 = fig.add_subplot(gs[0, 0])
    sc  = ax1.scatter(pc[:, 0], pc[:, 1], c=res["gamma"],
                      cmap="plasma", s=5, alpha=0.7)
    ax1.scatter(pc[T_seed, 0],  pc[T_seed, 1],  c="orange",
                s=70, marker="^", zorder=5, label=f"Seed t={T_seed}")
    ax1.scatter(pc[T_viral, 0], pc[T_viral, 1], c="red",
                s=80, marker="*", zorder=5, label=f"Viral t={T_viral}")
    fig.colorbar(sc, ax=ax1, shrink=0.8, label="γ")
    ax1.set_xlabel("PC1"); ax1.set_ylabel("PC2")
    ax1.set_title("Phase Portrait (PC1 × PC2)", fontsize=9, weight="bold")
    ax1.legend(fontsize=7)

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(tvec, res["energy"], color=NAVY, lw=1.2)
    ax2.axvline(T_seed,  color=GOLD, ls=":",  lw=1.5, label="Covert seeding")
    ax2.axvline(T_viral, color=RUST, ls="--", lw=1.5, label="Viral cascade")
    ax2.set_xlabel("Hours"); ax2.set_ylabel("E(t)")
    ax2.set_title("Lyapunov Energy E(t)", fontsize=9, weight="bold")
    ax2.legend(fontsize=7)

    ax3 = fig.add_subplot(gs[0, 2], projection="3d")
    ax3.scatter(pc[:, 0], pc[:, 1], pc[:, 2],
                c=np.log10(res["energy"] + 1), cmap="viridis", s=4, alpha=0.6)
    ax3.scatter([pc[T_viral, 0]], [pc[T_viral, 1]], [pc[T_viral, 2]],
                c="red", s=60, marker="*")
    ax3.set_xlabel("PC1", fontsize=7); ax3.set_ylabel("PC2", fontsize=7)
    ax3.set_zlabel("PC3", fontsize=7)
    ax3.set_title("3D Energy Surface", fontsize=9, weight="bold")

    ax4 = fig.add_subplot(gs[1, :2])
    for i, (key, lbl) in enumerate([
            ("delta_C", "δ_C Camouflage"),
            ("delta_A", "δ_A Activity"),
            ("delta_T", "δ_T Temporal"),
            ("delta_G", "δ_G Feature Gap")]):
        arr = res[key]
        norm_arr = (arr - arr.min()) / (arr.max() - arr.min() + 1e-8)
        ax4.plot(tvec, norm_arr, color=BSDT_CLR[i], lw=1.2, label=lbl, alpha=0.85)
    ax4.axvline(T_seed,  color=GOLD, ls=":",  lw=1.5, label="Covert seeding")
    ax4.axvline(T_viral, color=RUST, ls="--", lw=1.5, label="Viral cascade")
    ax4.set_xlabel("Hours"); ax4.set_ylabel("Normalised channel")
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
        res["delta_C"][T_viral:].mean(),
        res["delta_A"][T_viral:].mean(),
        res["delta_T"][T_viral:].mean(),
        res["delta_G"][T_viral:].mean(),
    ]
    total   = sum(post_means) + 1e-8
    weights = [v / total for v in post_means]
    bars    = ax6.bar(channels, weights, color=BSDT_CLR, width=0.5, alpha=0.85)
    ax6.set_ylabel("Fisher-VR weight"); ax6.set_xlabel("BSDT Channel")
    ax6.set_title("Post-Viral Channel Dominance", fontsize=9, weight="bold")
    for bar, w in zip(bars, weights):
        ax6.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.003,
                 f"{w:.3f}", ha="center", fontsize=8)

    ax7 = fig.add_subplot(gs[2, 2])
    ax7.axis("off")

    mu_pre  = res["energy"][:T_viral].mean()
    sd_pre  = res["energy"][:T_viral].std() + 1e-8
    z       = (res["energy"] - mu_pre) / sd_pre
    hits    = np.where(z[:T_viral] > 2.0)[0]
    first_a = hits[0] if len(hits) > 0 else T_viral
    lead    = T_viral - first_a
    dom_ch  = channels[int(np.argmax(weights))]

    summary = (
        f"Domain XII — Social Media Polarisation\n"
        f"{'─'*34}\n"
        f"Clusters (N):   8\n"
        f"Features (d):   4 (vol, polarity, x-poll, users)\n"
        f"Timesteps (T):  {T_TOTAL} hours\n"
        f"Covert seed:    t={T_seed}\n"
        f"Viral onset:    t={T_viral}\n\n"
        f"First alarm:    t={first_a}\n"
        f"Lead time:      +{lead} hours\n\n"
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
    print("Domain XII — Social Media: Polarisation and Misinformation Virality")
    print("  Generating surrogate social media dynamics...")
    X = generate_social_surrogate(N_CLUSTERS, T_TOTAL, T_SEED, T_VIRAL)
    print(f"  X shape: {X.shape}  min={X.min():.3f}  max={X.max():.3f}")

    print("  Running Canonical BSDT Engine...")
    res = run_canonical_engine(X)

    mu_pre  = res["energy"][:T_VIRAL].mean()
    sd_pre  = res["energy"][:T_VIRAL].std() + 1e-8
    z       = (res["energy"] - mu_pre) / sd_pre
    hits    = np.where(z[:T_VIRAL] > 2.0)[0]
    first_a = hits[0] if len(hits) > 0 else T_VIRAL
    lead    = T_VIRAL - first_a

    print(f"  Peak energy:   {res['energy'].max():.2f}")
    print(f"  Peak gamma:    {res['gamma'].max():.4f}")
    print(f"  Covert seed:   t={T_SEED}")
    print(f"  First alarm:   t={first_a}")
    print(f"  Lead time:     +{lead} hours before viral cascade")

    print("  Plotting...")
    plot_results(X, res, T_SEED, T_VIRAL, OUT_PNG)
    print("Done.")


if __name__ == "__main__":
    import sys as _sys
    print("[SKIPPED] domain_social_media.py uses synthetic engagement data (np.random)"
          " and is excluded from production canonical/BSDT results per user requirement.",
          file=_sys.stderr)
    _sys.exit(0)
    # Original main retained below for archival purposes.
    main()
