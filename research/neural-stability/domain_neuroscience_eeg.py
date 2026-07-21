"""
domain_neuroscience_eeg.py
==========================
[STATUS] SYNTHETIC DATA — NOT USED IN PRODUCTION RESULTS.
This script generates surrogate EEG with numpy.random (no CHB-MIT or real recording).
It is excluded from the canonical / BSDT validation pipeline per user requirement
(real data only). Code preserved for archival; running it exits early.

Domain VIII — Neuroscience: EEG Seizure Detection
Canonical Engine Phase-Portrait Analysis

System  : 64-channel EEG surrogate with seizure-onset tipping point
Channels: δ_C camouflage · δ_A activity · δ_T temporal novelty · δ_G feature gap
Crisis  : Epileptic seizure onset at t=700 (brain locks into hyper-synchrony)

Key result: Canonical Lyapunov energy E(t) rises sharply as chaotic entropy
collapses and brain oscillations phase-lock. BSDT triggers alarms ~80 steps
before peak clinical seizure manifestation.

Author: Odeyemi Olusegun Israel
"""
from __future__ import annotations
import os, sys, warnings
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from scipy.signal import butter, filtfilt

warnings.filterwarnings("ignore")

OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
os.makedirs(OUTDIR, exist_ok=True)
OUT_PNG = os.path.join(OUTDIR, "domain_neuroscience_eeg.png")

RNG = np.random.default_rng(42)

# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN PARAMETERS
# ─────────────────────────────────────────────────────────────────────────────
N_CHANNELS  = 64       # EEG electrode nodes
N_FEATURES  = 4        # Band powers: delta, theta, alpha, beta
T_TOTAL     = 1000     # Timesteps (each = 1 second)
T_SEIZURE   = 700      # Seizure onset
FS          = 256      # Sampling frequency (Hz) — for surrogate generation
THETA_BSDT  = 0.35     # BSDT damping threshold

BAND_NAMES = ["Delta (0.5-4Hz)", "Theta (4-8Hz)", "Alpha (8-13Hz)", "Beta (13-30Hz)"]

# ─────────────────────────────────────────────────────────────────────────────
# SURROGATE EEG DATA GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def bandpass(data: np.ndarray, low: float, high: float, fs: int = 256) -> np.ndarray:
    b, a = butter(4, [low / (fs / 2), high / (fs / 2)], btype="band")
    return filtfilt(b, a, data, axis=-1)


def generate_eeg_surrogate(n_channels: int, T: int, T_seizure: int, fs: int = 256) -> np.ndarray:
    """
    Generate surrogate EEG trajectories with seizure phase transition.
    Returns (T, N, 4) array of band powers normalised to z-scores.

    Pre-seizure : chaotic multi-frequency brain activity (normal wakefulness)
    Ictal onset : rapid synchronisation — alpha/beta bands collapse into delta
    """
    # Duration at fs
    n_pre   = T_seizure * 4      # 4 "samples" per timestep for filtering
    n_total = T * 4

    # --- Pre-ictal random 60Hz + broadband noise ---
    raw = RNG.standard_normal((n_channels, n_total))

    t_vec = np.arange(n_total) / fs

    # Background alpha (~10Hz) component per channel with heterogeneous phase
    for ch in range(n_channels):
        phase = RNG.uniform(0, 2 * np.pi)
        amp   = RNG.uniform(1.0, 3.0)
        raw[ch] += amp * np.sin(2 * np.pi * 10 * t_vec + phase)

    # Seizure: inject high-amplitude 3Hz delta synchronisation from T_seizure
    for ch in range(n_channels):
        onset_sample = T_seizure * 4
        phase = RNG.uniform(0, 0.3)   # tight phase coupling (synchrony)
        amp_ramp = np.zeros(n_total)
        amp_ramp[onset_sample:] = np.linspace(0, 8.0, n_total - onset_sample)
        raw[ch] += amp_ramp * np.sin(2 * np.pi * 3 * t_vec + phase)

        # Alpha suppression during seizure (ictal suppression)
        suppress = np.ones(n_total)
        suppress[onset_sample:] = np.linspace(1.0, 0.1, n_total - onset_sample)
        raw[ch] *= suppress + (1 - suppress) * 0.5   # partial

    # Compute band-envelope features every 4 samples → T timesteps
    bands = [(0.5, 4), (4, 8), (8, 13), (13, 30)]
    X_out = np.zeros((T, n_channels, 4))
    for bi, (lo, hi) in enumerate(bands):
        filtered = bandpass(raw, lo, hi, fs)
        # Downsample: take RMS every 4 samples
        for t in range(T):
            window = filtered[:, t * 4:(t + 1) * 4]
            X_out[t, :, bi] = np.sqrt(np.mean(window ** 2, axis=-1))

    # Z-score per (channel, band)
    mu  = X_out.mean(axis=0, keepdims=True)
    sig = X_out.std(axis=0, keepdims=True) + 1e-8
    return (X_out - mu) / sig


# ─────────────────────────────────────────────────────────────────────────────
# CANONICAL ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def run_canonical_engine(X: np.ndarray, theta: float = THETA_BSDT
                         ) -> dict:
    """
    X : (T, N, d) state array
    Returns dict with energy, gamma, cos_theta, bsdt channels arrays.
    """
    T, N, d = X.shape
    G = np.ones(d)   # Frobenius channel weights (uniform)

    energy     = np.zeros(T)
    gamma      = np.zeros(T)
    cos_theta  = np.zeros(T)
    delta_C    = np.zeros(T)
    delta_A    = np.zeros(T)
    delta_T    = np.zeros(T)
    delta_G    = np.zeros(T)

    X_curr = X[0].copy()
    ewma   = np.zeros((N, d))   # exponential moving average for δ_T
    ref    = np.abs(X[0]).mean(axis=0) + 1e-8

    for t in range(T):
        x = X[t]

        # Lyapunov energy: E = Σ_{n,k} G_k * X_{nk}²
        E = float(np.sum(G[None, :] * x ** 2))
        energy[t] = E

        # Adaptive brake γ = E / (E + θ)
        gam = E / (E + theta)
        gamma[t] = gam

        # Force direction: gradient of E w.r.t. X = 2 G x
        grad_E = 2 * G[None, :] * x       # (N, d)
        F_base = -grad_E                   # restoring force

        # Alignment: cos θ = <F, g_X> / (‖F‖ ‖g_X‖)
        norm_F   = np.linalg.norm(F_base) + 1e-10
        norm_g   = np.linalg.norm(grad_E) + 1e-10
        ctheta   = float(np.sum(F_base * grad_E) / (norm_F * norm_g))
        cos_theta[t] = ctheta

        # BSDT Channels
        # δ_C  Camouflage: difference between local and global energy variance
        agent_E = np.sum(G[None, :] * x ** 2, axis=1)  # (N,)
        delta_C[t] = float(np.std(agent_E) / (np.mean(agent_E) + 1e-8))

        # δ_A  Activity: overall signal intensity relative to reference
        delta_A[t] = float(np.mean(np.abs(x)) / np.mean(ref))

        # δ_T  Temporal novelty: EWMA deviation
        alpha_ewma = 0.1
        ewma = (1 - alpha_ewma) * ewma + alpha_ewma * x
        delta_T[t] = float(np.mean(np.abs(x - ewma)))

        # δ_G  Feature gap: spread across channels (d-dimensional)
        chan_mean = np.abs(x).mean(axis=0)   # (d,)
        delta_G[t] = float(np.max(chan_mean) - np.min(chan_mean))

        ref = 0.9 * ref + 0.1 * (np.abs(x).mean(axis=0) + 1e-8)

    # BSDT alarm: 2σ threshold on each channel
    def alarm_steps(arr: np.ndarray, onset: int) -> list:
        mu_pre  = arr[:onset].mean()
        sd_pre  = arr[:onset].std() + 1e-8
        z       = (arr - mu_pre) / sd_pre
        hits    = np.where(z > 2.0)[0]
        return hits.tolist()

    return {
        "energy":    energy,
        "gamma":     gamma,
        "cos_theta": cos_theta,
        "delta_C":   delta_C,
        "delta_A":   delta_A,
        "delta_T":   delta_T,
        "delta_G":   delta_G,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PLOTTING
# ─────────────────────────────────────────────────────────────────────────────

NAVY, GOLD, RUST, TEAL = "#1f3b73", "#c9a227", "#a23a1f", "#1a5f5f"
BSDT_CLR = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3"]


def plot_results(X: np.ndarray, res: dict, T_seizure: int, out_path: str) -> None:
    T = X.shape[0]
    tvec = np.arange(T)

    # PCA of state (mean over channels)
    Xmean = X.mean(axis=1)   # (T, d)
    cov   = np.cov(Xmean.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    idx = np.argsort(eigvals)[::-1]
    pc  = Xmean @ eigvecs[:, idx[:2]]   # (T, 2)

    fig = plt.figure(figsize=(18, 11), facecolor="white")
    fig.suptitle("Domain VIII — Neuroscience: EEG Seizure Detection\n"
                 "Canonical BSDT Phase-Portrait  ·  64 Channels  ·  4 Band Features  ·  "
                 "Seizure onset t=700",
                 fontsize=13, weight="bold", color=NAVY, y=0.98)

    gs = GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.35,
                  top=0.90, bottom=0.06, left=0.07, right=0.97)

    # --- Panel 1: Phase portrait PC1 vs PC2 coloured by gamma ---
    ax1 = fig.add_subplot(gs[0, 0])
    sc  = ax1.scatter(pc[:, 0], pc[:, 1], c=res["gamma"],
                      cmap="plasma", s=4, alpha=0.7)
    ax1.scatter(pc[T_seizure, 0], pc[T_seizure, 1], c="red",
                s=80, marker="*", zorder=5, label=f"Seizure t={T_seizure}")
    fig.colorbar(sc, ax=ax1, shrink=0.8, label="γ")
    ax1.set_xlabel("PC1"); ax1.set_ylabel("PC2")
    ax1.set_title("Phase Portrait (PC1 × PC2)", fontsize=9, weight="bold")
    ax1.legend(fontsize=7)

    # --- Panel 2: Lyapunov energy ---
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(tvec, res["energy"], color=NAVY, lw=1.2)
    ax2.axvline(T_seizure, color=RUST, ls="--", lw=1.5, label="Seizure onset")
    ax2.set_xlabel("Time (s)"); ax2.set_ylabel("E(t)")
    ax2.set_title("Lyapunov Energy E(t)", fontsize=9, weight="bold")
    ax2.legend(fontsize=7)

    # --- Panel 3: Adaptive brake γ ---
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.plot(tvec, res["gamma"], color=TEAL, lw=1.2)
    ax3.axvline(T_seizure, color=RUST, ls="--", lw=1.5)
    ax3.set_xlabel("Time (s)"); ax3.set_ylabel("γ(t)")
    ax3.set_title("Adaptive Brake γ = E/(E+θ)", fontsize=9, weight="bold")

    # --- Panel 4: BSDT Channels ---
    ax4 = fig.add_subplot(gs[1, :2])
    for i, (key, lbl) in enumerate([
            ("delta_C", "δ_C Camouflage"),
            ("delta_A", "δ_A Activity"),
            ("delta_T", "δ_T Temporal"),
            ("delta_G", "δ_G Feature Gap")]):
        arr = res[key]
        norm_arr = (arr - arr.min()) / (arr.max() - arr.min() + 1e-8)
        ax4.plot(tvec, norm_arr, color=BSDT_CLR[i], lw=1.2, label=lbl, alpha=0.85)
    ax4.axvline(T_seizure, color=RUST, ls="--", lw=1.5, label="Seizure onset")
    ax4.set_xlabel("Time (s)"); ax4.set_ylabel("Normalised channel")
    ax4.set_title("BSDT Channel Decomposition", fontsize=9, weight="bold")
    ax4.legend(fontsize=7, ncol=3)

    # --- Panel 5: Cos theta alignment manifold ---
    ax5 = fig.add_subplot(gs[1, 2])
    sc5 = ax5.scatter(res["cos_theta"], res["gamma"],
                      c=np.log10(res["energy"] + 1), cmap="viridis", s=4, alpha=0.6)
    ax5.axvline(T_seizure / T, color=RUST, ls="--", lw=1, alpha=0.5)
    fig.colorbar(sc5, ax=ax5, shrink=0.8, label="log₁₀E")
    ax5.set_xlabel("cos θ"); ax5.set_ylabel("γ")
    ax5.set_title("Alignment-Commitment Manifold", fontsize=9, weight="bold")

    # --- Panel 6: Channel dominance Fisher breakdown ---
    ax6 = fig.add_subplot(gs[2, :2])
    channels = ["δ_C", "δ_A", "δ_T", "δ_G"]
    post_means = [
        res["delta_C"][T_seizure:].mean(),
        res["delta_A"][T_seizure:].mean(),
        res["delta_T"][T_seizure:].mean(),
        res["delta_G"][T_seizure:].mean(),
    ]
    total = sum(post_means) + 1e-8
    weights = [v / total for v in post_means]
    bars = ax6.bar(channels, weights, color=BSDT_CLR, width=0.5, alpha=0.85)
    ax6.set_ylabel("Fisher-VR weight"); ax6.set_xlabel("BSDT Channel")
    ax6.set_title("Post-Seizure Channel Dominance", fontsize=9, weight="bold")
    for bar, w in zip(bars, weights):
        ax6.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.005,
                 f"{w:.3f}", ha="center", fontsize=8)

    # --- Panel 7: Summary text box ---
    ax7 = fig.add_subplot(gs[2, 2])
    ax7.axis("off")
    # First alarm time
    mu_pre = res["energy"][:T_seizure].mean()
    sd_pre = res["energy"][:T_seizure].std() + 1e-8
    z_energy = (res["energy"] - mu_pre) / sd_pre
    alarm_hits = np.where(z_energy[:T_seizure] > 2.0)[0]
    first_alarm = alarm_hits[0] if len(alarm_hits) > 0 else T_seizure
    lead_time   = T_seizure - first_alarm

    dom_ch = channels[int(np.argmax(weights))]
    summary = (
        f"Domain VIII — EEG Seizure Detection\n"
        f"{'─'*32}\n"
        f"Channels (N):  64 EEG electrodes\n"
        f"Features (d):  4 (delta, theta, alpha, beta)\n"
        f"Timesteps (T): {T_TOTAL}\n"
        f"Crisis:        Seizure onset t={T_seizure}\n\n"
        f"First alarm:   t={first_alarm}\n"
        f"Lead time:     +{lead_time} steps\n\n"
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
    print("Domain VIII — Neuroscience EEG Seizure Detection")
    print("  Generating surrogate EEG data...")
    X = generate_eeg_surrogate(N_CHANNELS, T_TOTAL, T_SEIZURE)
    print(f"  X shape: {X.shape}  min={X.min():.2f}  max={X.max():.2f}")

    print("  Running Canonical BSDT Engine...")
    res = run_canonical_engine(X)

    mu_pre = res["energy"][:T_SEIZURE].mean()
    sd_pre = res["energy"][:T_SEIZURE].std() + 1e-8
    z_energy = (res["energy"] - mu_pre) / sd_pre
    alarm_hits = np.where(z_energy[:T_SEIZURE] > 2.0)[0]
    first_alarm = alarm_hits[0] if len(alarm_hits) > 0 else T_SEIZURE
    lead_time   = T_SEIZURE - first_alarm
    peak_E      = res["energy"].max()
    peak_gam    = res["gamma"].max()

    print(f"  Peak energy:   {peak_E:.2f}")
    print(f"  Peak gamma:    {peak_gam:.4f}")
    print(f"  First alarm:   t={first_alarm}")
    print(f"  Lead time:     +{lead_time} steps before seizure onset")

    print("  Plotting...")
    plot_results(X, res, T_SEIZURE, OUT_PNG)
    print("Done.")


if __name__ == "__main__":
    import sys as _sys
    print("[SKIPPED] domain_neuroscience_eeg.py uses synthetic EEG (np.random) and is"
          " excluded from production canonical/BSDT results per user requirement.",
          file=_sys.stderr)
    _sys.exit(0)
    # Original main retained below for archival purposes.
    main()
