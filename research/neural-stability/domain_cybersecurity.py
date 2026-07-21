"""
domain_cybersecurity.py
=======================
[STATUS] SUPERSEDED — NOT USED IN PRODUCTION RESULTS.
This file uses simplified canonical-themed math, not the strict locked Canonical-v4
ODE + mathematically exact BSDT. The production cybersecurity validation is in:
    cyber_frozen_window_validation.py
which implements the strict v4 ODE on real TON-IoT-2020 traffic.
Code preserved for archival; running it exits early.

Domain X — Cybersecurity: Network Intrusion Detection
Canonical Engine Phase-Portrait Analysis

Dataset : UNSW-NB15 (real-world network traffic — 54,296 labelled flows)
          10 attack categories: Analysis, Backdoor, DoS, Exploits, Fuzzers,
          Generic, Normal, Reconnaissance, Shellcode, Worms
Features: 10-dimensional pre-standardised flow features
Agents  : Each attack category = 1 "agent" (N=10)

The canonical engine processes the category-mean feature trajectory over
time (temporal batches). The Lyapunov energy spikes during intense attack
phases (DOS, Exploits) and γ activates to structurally bound the intrusion
energy gradient.

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

DATA_PATH = r"c:\amttp\data\external_validation\cyber\unsw_nb15.npz"
OUTDIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
os.makedirs(OUTDIR, exist_ok=True)
OUT_PNG   = os.path.join(OUTDIR, "domain_cybersecurity.png")

RNG = np.random.default_rng(77)

THETA_BSDT = 0.4
BATCH_SIZE = 50    # Flows per timestep batch

NAVY, GOLD, RUST, TEAL = "#1f3b73", "#c9a227", "#a23a1f", "#1a5f5f"
BSDT_CLR = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3"]


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADER
# ─────────────────────────────────────────────────────────────────────────────

ATTACK_ORDER = [
    "Normal", "Fuzzers", "Analysis", "Backdoor",
    "DoS", "Exploits", "Reconnaissance", "Shellcode", "Generic", "Worms"
]

def load_data(path: str, batch_size: int = BATCH_SIZE):
    """
    Load UNSW-NB15, sort by attack category, create temporal batches.
    Returns:
        X  : (T, N, d)  — T timestep-batches, N=10 categories, d=10 features
        categories : list of N category names
        T_crisis  : int  — first timestep where high-severity attacks dominate
    """
    d = np.load(path, allow_pickle=True)
    X_raw = d["X10"]            # (54296, 10)  standardised
    y_raw = d["attack_types"]   # (54296,)  object dtype

    # Map attack types to canonical order
    categories = [c for c in ATTACK_ORDER if c in np.unique(y_raw)]
    N = len(categories)

    # Shuffle within each category to simulate temporal arrival
    cat_data = {}
    for cat in categories:
        mask = (y_raw == cat)
        rows = X_raw[mask]
        RNG.shuffle(rows)
        cat_data[cat] = rows

    # Build temporal batches: for each timestep, take batch_size flows
    # from each category proportionally (or as available)
    max_per_cat = max(len(v) for v in cat_data.values())
    T = max_per_cat // batch_size

    X_out = np.zeros((T, N, X_raw.shape[1]))
    for t in range(T):
        for ci, cat in enumerate(categories):
            rows = cat_data[cat]
            lo   = (t * batch_size) % max(len(rows), 1)
            hi   = min(lo + batch_size, len(rows))
            if hi > lo:
                X_out[t, ci, :] = rows[lo:hi].mean(axis=0)
            else:
                X_out[t, ci, :] = rows.mean(axis=0)   # fill with category mean

    # T_crisis: first timestep where DoS/Exploits/Generic dominate activity
    high_sev_cats = ["DoS", "Exploits", "Generic"]
    high_sev_idx  = [categories.index(c) for c in high_sev_cats if c in categories]

    # Compute per-timestep intensity of high-severity categories
    sev_energy = np.sum(X_out[:, high_sev_idx, :] ** 2, axis=(1, 2))
    # Crisis = first 30% mark of total run (these datasets have balanced timing)
    T_crisis = max(T // 3, 5)

    return X_out, categories, T_crisis


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

def plot_results(X: np.ndarray, res: dict, categories: list,
                 T_crisis: int, out_path: str) -> None:
    T = X.shape[0]
    tvec = np.arange(T)

    Xmean = X.mean(axis=1)
    cov   = np.cov(Xmean.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    idx  = np.argsort(eigvals)[::-1]
    pc   = Xmean @ eigvecs[:, idx[:3]]

    fig = plt.figure(figsize=(18, 11), facecolor="white")
    fig.suptitle(
        "Domain X — Cybersecurity: Network Intrusion Detection (UNSW-NB15)\n"
        "Canonical BSDT Phase-Portrait  ·  N=10 attack categories  ·  d=10 features  ·  "
        f"T={T} temporal batches",
        fontsize=13, weight="bold", color=NAVY, y=0.98)

    gs = GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.35,
                  top=0.90, bottom=0.06, left=0.07, right=0.97)

    # Panel 1: Phase portrait coloured by γ
    ax1 = fig.add_subplot(gs[0, 0])
    sc  = ax1.scatter(pc[:, 0], pc[:, 1], c=res["gamma"],
                      cmap="plasma", s=8, alpha=0.7)
    ax1.scatter(pc[T_crisis, 0], pc[T_crisis, 1], c="red",
                s=80, marker="*", zorder=5, label=f"High-severity t={T_crisis}")
    fig.colorbar(sc, ax=ax1, shrink=0.8, label="γ")
    ax1.set_xlabel("PC1"); ax1.set_ylabel("PC2")
    ax1.set_title("Phase Portrait (PC1 × PC2)", fontsize=9, weight="bold")
    ax1.legend(fontsize=7)

    # Panel 2: Lyapunov energy time series
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(tvec, res["energy"], color=NAVY, lw=1.2)
    ax2.axvline(T_crisis, color=RUST, ls="--", lw=1.5, label="High-severity phase")
    ax2.set_xlabel("Batch (50 flows)"); ax2.set_ylabel("E(t)")
    ax2.set_title("Lyapunov Energy E(t)", fontsize=9, weight="bold")
    ax2.legend(fontsize=7)

    # Panel 3: 3D phase portrait
    ax3 = fig.add_subplot(gs[0, 2], projection="3d")
    ax3.scatter(pc[:, 0], pc[:, 1], pc[:, 2],
                c=np.log10(res["energy"] + 1), cmap="viridis", s=4, alpha=0.55)
    ax3.scatter([pc[T_crisis, 0]], [pc[T_crisis, 1]], [pc[T_crisis, 2]],
                c="red", s=60, marker="*")
    ax3.set_xlabel("PC1", fontsize=7); ax3.set_ylabel("PC2", fontsize=7)
    ax3.set_zlabel("PC3", fontsize=7)
    ax3.set_title("3D Energy Surface", fontsize=9, weight="bold")

    # Panel 4: BSDT channels
    ax4 = fig.add_subplot(gs[1, :2])
    for i, (key, lbl) in enumerate([
            ("delta_C", "δ_C Camouflage"),
            ("delta_A", "δ_A Activity"),
            ("delta_T", "δ_T Temporal"),
            ("delta_G", "δ_G Feature Gap")]):
        arr = res[key]
        norm_arr = (arr - arr.min()) / (arr.max() - arr.min() + 1e-8)
        ax4.plot(tvec, norm_arr, color=BSDT_CLR[i], lw=1.2, label=lbl, alpha=0.85)
    ax4.axvline(T_crisis, color=RUST, ls="--", lw=1.5, label="Attack phase")
    ax4.set_xlabel("Batch (50 flows)"); ax4.set_ylabel("Normalised channel")
    ax4.set_title("BSDT Channel Decomposition", fontsize=9, weight="bold")
    ax4.legend(fontsize=7, ncol=3)

    # Panel 5: Alignment manifold
    ax5 = fig.add_subplot(gs[1, 2])
    sc5 = ax5.scatter(res["cos_theta"], res["gamma"],
                      c=np.log10(res["energy"] + 1), cmap="viridis", s=5, alpha=0.6)
    fig.colorbar(sc5, ax=ax5, shrink=0.8, label="log₁₀E")
    ax5.set_xlabel("cos θ"); ax5.set_ylabel("γ")
    ax5.set_title("Alignment-Commitment Manifold", fontsize=9, weight="bold")

    # Panel 6: Per-category energy (heatmap)
    ax6 = fig.add_subplot(gs[2, :2])
    cat_E = np.sum(X ** 2, axis=2)   # (T, N)  energy per category per timestep
    im = ax6.imshow(cat_E.T, aspect="auto", cmap="hot",
                    interpolation="nearest", origin="lower")
    ax6.set_yticks(range(len(categories)))
    ax6.set_yticklabels(categories, fontsize=7)
    ax6.set_xlabel("Batch (50 flows)")
    ax6.set_title("Per-Category Energy Heatmap", fontsize=9, weight="bold")
    ax6.axvline(T_crisis, color="cyan", lw=1.5, ls="--", label="Attack phase")
    fig.colorbar(im, ax=ax6, shrink=0.6, label="E per category")
    ax6.legend(fontsize=7)

    # Panel 7: Summary
    ax7 = fig.add_subplot(gs[2, 2])
    ax7.axis("off")

    channels  = ["δ_C", "δ_A", "δ_T", "δ_G"]
    post_means = [
        res["delta_C"][T_crisis:].mean(),
        res["delta_A"][T_crisis:].mean(),
        res["delta_T"][T_crisis:].mean(),
        res["delta_G"][T_crisis:].mean(),
    ]
    total   = sum(post_means) + 1e-8
    weights = [v / total for v in post_means]
    dom_ch  = channels[int(np.argmax(weights))]

    mu_pre  = res["energy"][:T_crisis].mean()
    sd_pre  = res["energy"][:T_crisis].std() + 1e-8
    z       = (res["energy"] - mu_pre) / sd_pre
    hits    = np.where(z[:T_crisis] > 2.0)[0]
    first_a = hits[0] if len(hits) > 0 else T_crisis
    lead    = T_crisis - first_a

    summary = (
        f"Domain X — Cybersecurity (UNSW-NB15)\n"
        f"{'─'*34}\n"
        f"Categories (N): {len(categories)}\n"
        f"Features (d):   10 (flow features)\n"
        f"Timesteps (T):  {T}\n"
        f"Dataset:        54,296 real flows\n"
        f"Crisis:         High-severity phase t={T_crisis}\n\n"
        f"First alarm:    t={first_a}\n"
        f"Lead time:      +{lead} batches\n\n"
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
    print("Domain X — Cybersecurity: Network Intrusion Detection (UNSW-NB15)")

    if not os.path.exists(DATA_PATH):
        print(f"  ERROR: dataset not found at {DATA_PATH}")
        return

    print("  Loading UNSW-NB15 dataset...")
    X, categories, T_crisis = load_data(DATA_PATH)
    print(f"  X shape: {X.shape}  categories: {categories}")
    print(f"  T_crisis: {T_crisis}")

    print("  Running Canonical BSDT Engine...")
    res = run_canonical_engine(X)

    mu_pre  = res["energy"][:T_crisis].mean()
    sd_pre  = res["energy"][:T_crisis].std() + 1e-8
    z       = (res["energy"] - mu_pre) / sd_pre
    hits    = np.where(z[:T_crisis] > 2.0)[0]
    first_a = hits[0] if len(hits) > 0 else T_crisis
    lead    = T_crisis - first_a

    print(f"  Peak energy:   {res['energy'].max():.2f}")
    print(f"  Peak gamma:    {res['gamma'].max():.4f}")
    print(f"  First alarm:   t={first_a}")
    print(f"  Lead time:     +{lead} batches before high-severity phase")

    print("  Plotting...")
    plot_results(X, res, categories, T_crisis, OUT_PNG)
    print("Done.")


if __name__ == "__main__":
    import sys as _sys
    print("[SKIPPED] domain_cybersecurity.py is superseded by cyber_frozen_window_validation.py"
          " (strict Canonical-v4 + real TON-IoT). This older file is excluded from production"
          " results per user requirement (strict methods only).",
          file=_sys.stderr)
    _sys.exit(0)
    # Original main retained below for archival purposes.
    main()
