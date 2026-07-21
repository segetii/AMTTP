"""
run_nn_gradient_sim.py — Domain IV: Neural Network Gradient Stability
======================================================================
Runs all 13 optimisers on the BlowUpNet and validates the critical
manifold thesis:
  - Vanilla SGD & RMSProp blow up at epoch 1
  - SGD+Clip survives but converges poorly (constant friction)
  - All 8 BSDT variants survive 300 epochs with superior convergence
  - Adaptive friction self-regulates: peak 700×+ → final ~1×

This is the neural-network analogue of the financial/supply-chain
result: constant parameters (gradient clipping) fail above C*,
only adaptive γ* = α/λ_max succeeds.

Author: Odeyemi Olusegun Israel
"""

from __future__ import annotations
import sys, os, json, time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nn_engine import (
    BlowUpNet, make_spiral_data, get_all_optimisers,
    train, EpochLog, grad_norm, per_layer_grad_norms,
    spectral_radius_approx, GradientBSDT,
)


# ═════════════════════════════════════════════════════════════
#  CANONICAL ADAPTIVE FRICTION — DIRECT IMPLEMENTATION
# ═════════════════════════════════════════════════════════════
#
# These classes implement the canonical formula directly in this
# script, independent of the BSDT optimiser family, so the math
# is fully auditable here without tracing into nn_engine.py.
#
# The stability condition for gradient descent is:
#
#   ‖θ_{t+1} − θ*‖ ≤ ‖θ_t − θ*‖  iff  lr_eff ≤ 2 / λ_max(∇²L)
#
# Setting a safety margin α (0 < α ≤ 2):
#
#   lr / (1 + γ*) = α / λ_max  →  γ* = lr · λ_max / α
#
# Level 1 (spectral):   γ_spec  = lr · λ_eff(W) / α
#   where λ_eff = geometric mean of layer spectral norms
#         = exp((1/L) Σ log σ_max(W_l))  ≈ typical per-layer σ
#   (Full product Π σ_l ≈ 5.6^20 ≈ 10^15 is too loose for deep nets)
# Level 2 (structural): γ_struct = E_BS / (E_BS + θ)
# Combined:             γ*       = max(γ_spec, γ_struct)
# ─────────────────────────────────────────────────────────────

class CanonicalSpectralOptimiser:
    """ʜ Level-1 only: pure spectral canonical adaptive friction.

    γ*(t) = lr · λ_eff(W, t) / α

    λ_eff is the GEOMETRIC MEAN of per-layer weight spectral norms:
        λ_eff = exp((1/L) Σ log σ_max(W_l))

    The full Jacobian product Π σ_l grows as σ^L ≈ 5.6^20 ≈ 10^15
    for a 20-layer init, making γ_spec astronomically large and
    freezing the network.  The geometric mean gives the typical
    per-layer spectral norm ≈ 5.6, keeping γ_spec in [0, 10].

    When λ_eff is small (flat landscape):  γ* ≈ 0 → full lr.
    When λ_eff is large (near blow-up):    γ* ≫ 1 → near-zero step.

    Spectral computation is cached once per epoch (not per batch) to
    avoid redundant power iterations inside the mini-batch loop.
    """
    name = "CanSpectral"

    def __init__(self, alpha: float = 0.1):
        self.alpha = alpha
        self._cached_epoch  = -1
        self._cached_lam    = 1.0

    def reset(self):
        self._cached_epoch = -1
        self._cached_lam   = 1.0

    def step(self, net, dW_list, db_list, epoch, lr):
        # Recompute spectral bound only once per epoch
        if epoch != self._cached_epoch:
            self._cached_lam   = spectral_radius_approx(net.W, seed=epoch)
            self._cached_epoch = epoch
        lam_max    = self._cached_lam
        gamma_star = lr * lam_max / self.alpha
        effective_lr = lr / (1.0 + gamma_star)

        for i in range(net.n_layers):
            net.W[i] -= effective_lr * dW_list[i]
            net.b[i] -= effective_lr * db_list[i]

        return {
            "friction":    1.0 + gamma_star,
            "gamma_star":  gamma_star,
            "lambda_max":  lam_max,
            "E_bs":        0.0,
            "channels":    None,
        }


class CanonicalFullOptimiser:
    """Two-level canonical adaptive friction (spectral + structural).

    Level 1 — spectral:   γ_spec   = lr · λ_max(W) / α
    Level 2 — structural: γ_struct  = E_BS / (E_BS + θ)
    Combined:             γ*        = max(γ_spec, γ_struct)

    This is the complete canonical formula from the grand-unification
    paper, implemented here as a standalone reference optimiser so the
    derivation is directly auditable in the runner script.

    Spectral computation is cached once per epoch (not per batch) to
    avoid redundant power iterations inside the mini-batch loop.
    """
    name = "CanFull"

    def __init__(self, alpha: float = 0.1, theta: float = 1.0):
        self.alpha = alpha
        self.bsdt  = GradientBSDT(theta=theta)
        self.calibrated    = False
        self._cached_epoch = -1
        self._cached_lam   = 1.0

    def reset(self):
        self.bsdt.reset()
        self.calibrated    = False
        self._cached_epoch = -1
        self._cached_lam   = 1.0

    def step(self, net, dW_list, db_list, epoch, lr):
        # ── Level 1: spectral (cached per epoch) ──────────────
        if epoch != self._cached_epoch:
            self._cached_lam   = spectral_radius_approx(net.W, seed=epoch)
            self._cached_epoch = epoch
        lam_max    = self._cached_lam
        gamma_spec = lr * lam_max / self.alpha

        # ── Level 2: structural (BSDT energy) ───────────────
        channels   = self.bsdt.compute_channels(net.W, dW_list)
        E_bs       = self.bsdt.energy(channels)
        gamma_struct = E_bs / (E_bs + self.bsdt.theta)

        # Calibrate on first epoch
        if not self.calibrated and epoch == 0:
            g_norms = per_layer_grad_norms(dW_list)
            if all(np.isfinite(g) for g in g_norms):
                self.bsdt.calibrate(g_norms)
                self.calibrated = True

        # ── Combined: canonical formula ──────────────────────
        gamma_star  = max(gamma_spec, gamma_struct)
        effective_lr = lr / (1.0 + gamma_star)

        for i in range(net.n_layers):
            net.W[i] -= effective_lr * dW_list[i]
            net.b[i] -= effective_lr * db_list[i]

        return {
            "friction":    1.0 + gamma_star,
            "gamma_star":  gamma_star,
            "gamma_spec":  gamma_spec,
            "gamma_struct": gamma_struct,
            "lambda_max":  lam_max,
            "E_bs":        E_bs,
            "channels":    channels,
        }


def get_canonical_optimisers() -> dict:
    """Return the two canonical reference optimisers."""
    return {
        "CanSpectral": CanonicalSpectralOptimiser(alpha=0.1),
        "CanFull":     CanonicalFullOptimiser(alpha=0.1, theta=1.0),
    }


# ═════════════════════════════════════════════════════════════
#  MAIN EXPERIMENT
# ═════════════════════════════════════════════════════════════

def run_experiment(n_epochs: int = 300, lr: float = 0.01,
                   seed: int = 42, verbose: bool = True,
                   hidden_dim: int = 64, n_layers: int = 10
                   ) -> dict:
    """Run all 15 optimisers on the BlowUpNet.

    hidden_dim / n_layers control network width and depth.
    defaults are 64 / 10 for practical runtimes on CPU;
    set 512 / 20 to reproduce the full pathological experiment.
    """

    # Generate data
    X, y = make_spiral_data(n_samples=2000, noise=0.3, seed=seed)
    split = int(0.8 * len(X))
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    if verbose:
        print(f"Data: {len(X_train)} train, {len(X_test)} test, {X.shape[1]}D")
        print(f"BlowUpNet: {n_layers} layers, d={hidden_dim}, init_scale=2.0 (pathological)")
        print(f"Training: lr={lr}, epochs={n_epochs}, batch=256")
        print()

    optimisers = {**get_all_optimisers(), **get_canonical_optimisers()}
    results = {}

    for opt_name, opt in optimisers.items():
        # Fresh network for each optimiser (same init)
        net = BlowUpNet(hidden_dim=hidden_dim, n_layers=n_layers)
        net.init_weights(seed=seed)
        opt.reset()

        if verbose:
            n_params = net.total_params()
            print(f"  [{opt_name:12s}] ({n_params:,d} params) ", end="", flush=True)

        t0 = time.time()
        logs = train(net, opt, X_train, y_train, X_test, y_test,
                     lr=lr, n_epochs=n_epochs, seed=seed, verbose=False)
        elapsed = time.time() - t0

        # Extract summary
        blew_up = any(log.blew_up for log in logs)
        blow_up_epoch = -1
        if blew_up:
            blow_up_epoch = next(i for i, log in enumerate(logs) if log.blew_up)

        # Last valid epoch
        valid_logs = [log for log in logs if not log.blew_up]
        if valid_logs:
            final_loss = valid_logs[-1].train_loss
            final_acc  = valid_logs[-1].test_acc
            best_acc   = max(log.test_acc for log in valid_logs)
            peak_friction = max(log.friction for log in valid_logs)
            final_friction = valid_logs[-1].friction
            peak_gnorm = max(log.grad_norm for log in valid_logs
                             if np.isfinite(log.grad_norm))
        else:
            final_loss = float('inf')
            final_acc = 0.5
            best_acc = 0.5
            peak_friction = 0.0
            final_friction = 0.0
            peak_gnorm = float('inf')

        # Three-phase dynamics (for BSDT variants)
        friction_history = [log.friction for log in logs if not log.blew_up]
        phases = classify_phases(friction_history) if len(friction_history) > 20 else {}

        result = {
            "name": opt_name,
            "blew_up": blew_up,
            "blow_up_epoch": blow_up_epoch,
            "epochs_survived": len(valid_logs),
            "final_train_loss": final_loss,
            "final_test_acc": final_acc,
            "best_test_acc": best_acc,
            "peak_grad_norm": peak_gnorm,
            "peak_friction": peak_friction,
            "final_friction": final_friction,
            "elapsed_s": elapsed,
            "phases": phases,
            "logs": logs,
        }
        results[opt_name] = result

        if verbose:
            if blew_up:
                print(f"BLOW-UP at epoch {blow_up_epoch:3d}  "
                      f"gnorm={peak_gnorm:.1e}  ({elapsed:.1f}s)")
            else:
                print(f"loss={final_loss:.4f}  acc={best_acc:.3f}  "
                      f"γ_peak={peak_friction:.1f}×  "
                      f"γ_final={final_friction:.2f}×  ({elapsed:.1f}s)")

    return results


def classify_phases(friction_history: list, n_epochs: int = 300) -> dict:
    """Detect three-phase dynamics in friction history.

    Phase 1 (Emergency braking):  friction >> 1, epochs ~0-20
    Phase 2 (Controlled descent): friction moderate, epochs ~20-200
    Phase 3 (Equilibrium):        friction ≈ 1, epochs ~200-300
    """
    if len(friction_history) < 20:
        return {}

    f = np.array(friction_history)
    n = len(f)

    # Phase 1 end: first epoch where friction drops below 50% of peak
    peak = np.max(f[:min(30, n)])
    phase1_end = 0
    for i in range(min(30, n)):
        if i > 5 and f[i] < 0.5 * peak:
            phase1_end = i
            break
    if phase1_end == 0:
        phase1_end = min(20, n)

    # Phase 3 start: last epoch where friction is within 20% of final
    final_friction = f[-1] if n > 0 else 1.0
    phase3_start = n
    for i in range(n - 1, max(n // 2, 0), -1):
        if abs(f[i] - final_friction) > 0.2 * max(final_friction, 1.0):
            phase3_start = i + 1
            break
    if phase3_start >= n:
        phase3_start = max(n * 2 // 3, phase1_end + 1)

    return {
        "phase1_end": phase1_end,
        "phase2_range": (phase1_end, phase3_start),
        "phase3_start": phase3_start,
        "peak_friction_phase1": float(np.max(f[:phase1_end + 1])) if phase1_end > 0 else float(f[0]),
        "mean_friction_phase2": float(np.mean(f[phase1_end:phase3_start])) if phase3_start > phase1_end else 0.0,
        "mean_friction_phase3": float(np.mean(f[phase3_start:])) if phase3_start < n else float(f[-1]),
    }


# ═════════════════════════════════════════════════════════════
#  SUMMARY TABLE
# ═════════════════════════════════════════════════════════════

def print_summary_table(results: dict) -> str:
    """Generate paper-ready summary table."""
    lines = []
    lines.append("")
    lines.append("=" * 105)
    lines.append("  NEURAL NETWORK GRADIENT STABILITY — BSDT UNIVERSALITY RESULTS")
    lines.append("=" * 105)
    lines.append(f"  {'Optimiser':<14s} {'Type':<8s} {'Survived':>8s} {'BU Epoch':>9s} "
                 f"{'Loss':>10s} {'Best Acc':>9s} {'Peak γ':>9s} "
                 f"{'Final γ':>9s} {'Peak ∥∇∥':>10s}")
    lines.append("-" * 105)

    standard = ["SGD", "SGD+Clip", "Adam", "AdamW", "RMSProp"]
    bsdt_names = ["BSDT", "MFLS", "Molecular", "Gravity", "Hybrid",
                  "QuadSurf", "QuadExpo", "SignedLR"]
    canonical_names = ["CanSpectral", "CanFull"]

    def format_row(name, r):
        survived = f"{r['epochs_survived']}/{300}"
        bu = f"{r['blow_up_epoch']}" if r['blew_up'] else "—"
        loss = f"{r['final_train_loss']:.4f}" if np.isfinite(r['final_train_loss']) else "∞"
        acc = f"{r['best_test_acc']:.3f}" if r['best_test_acc'] > 0.5 else "—"
        pk = f"{r['peak_friction']:.1f}×" if r['peak_friction'] > 0 else "—"
        fn = f"{r['final_friction']:.2f}×" if r['final_friction'] > 0 else "—"
        gn = f"{r['peak_grad_norm']:.1e}" if np.isfinite(r['peak_grad_norm']) else "∞"
        typ = "std" if name in standard else ("canon" if name in canonical_names else "BSDT")
        return f"  {name:<14s} {typ:<8s} {survived:>8s} {bu:>9s} {loss:>10s} {acc:>9s} {pk:>9s} {fn:>9s} {gn:>10s}"

    for name in standard:
        if name in results:
            lines.append(format_row(name, results[name]))
    lines.append("-" * 105)
    for name in bsdt_names:
        if name in results:
            lines.append(format_row(name, results[name]))
    lines.append("-" * 105)
    lines.append("  ── Canonical Adaptive Friction (direct implementations) ──")
    for name in canonical_names:
        if name in results:
            lines.append(format_row(name, results[name]))

    lines.append("=" * 105)
    lines.append("")

    # Key statistics
    bsdt_survived = sum(1 for n in bsdt_names if n in results and not results[n]["blew_up"])
    std_blew_up = sum(1 for n in standard if n in results and results[n]["blew_up"])
    canon_survived = sum(1 for n in canonical_names if n in results and not results[n]["blew_up"])

    bsdt_losses = [results[n]["final_train_loss"] for n in bsdt_names
                   if n in results and np.isfinite(results[n]["final_train_loss"])]
    bsdt_accs = [results[n]["best_test_acc"] for n in bsdt_names
                 if n in results and results[n]["best_test_acc"] > 0.5]

    lines.append(f"  Standard optimisers that BLEW UP: {std_blew_up}/{len(standard)}")
    lines.append(f"  BSDT variants surviving 300 epochs: {bsdt_survived}/{len(bsdt_names)}")
    lines.append(f"  Canonical variants surviving 300 epochs: {canon_survived}/{len(canonical_names)}")
    if bsdt_losses:
        lines.append(f"  Best BSDT train loss: {min(bsdt_losses):.4f}")
    if bsdt_accs:
        lines.append(f"  Best BSDT test accuracy: {max(bsdt_accs):.3f}")

    # Friction dynamics
    peak_frictions = [results[n]["peak_friction"] for n in bsdt_names
                      if n in results and results[n]["peak_friction"] > 0]
    final_frictions = [results[n]["final_friction"] for n in bsdt_names
                       if n in results and results[n]["final_friction"] > 0]
    if peak_frictions and final_frictions:
        lines.append(f"  Friction range: peak {max(peak_frictions):.0f}× → "
                     f"final {np.mean(final_frictions):.1f}×")

    # SGD+Clip comparison
    if "SGD+Clip" in results and not results["SGD+Clip"]["blew_up"]:
        clip_loss = results["SGD+Clip"]["final_train_loss"]
        lines.append(f"  SGD+Clip (constant friction) loss: {clip_loss:.4f}")

    lines.append("")
    table = "\n".join(lines)
    print(table)
    return table


# ═════════════════════════════════════════════════════════════
#  FIGURES
# ═════════════════════════════════════════════════════════════

def generate_figures(results: dict, figdir: str = None):
    """Generate publication-quality comparison figures."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  [WARN] matplotlib not available — skipping figures")
        return

    if figdir is None:
        figdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
    os.makedirs(figdir, exist_ok=True)

    # Colour scheme
    std_colors = {
        "SGD": "#e74c3c", "SGD+Clip": "#f39c12", "Adam": "#3498db",
        "AdamW": "#2980b9", "RMSProp": "#e67e22"
    }
    bsdt_colors = {
        "BSDT": "#2ecc71", "MFLS": "#27ae60", "Molecular": "#1abc9c",
        "Gravity": "#16a085", "Hybrid": "#2ecc71", "QuadSurf": "#1dd1a1",
        "QuadExpo": "#10ac84", "SignedLR": "#0a8f6c"
    }
    # Canonical optimisers: purple family — distinct from both standard and BSDT
    canonical_colors = {
        "CanSpectral": "#9b59b6",   # violet — Level 1 only
        "CanFull":     "#6c3483",   # deep purple — both levels
    }
    all_colors = {**std_colors, **bsdt_colors, **canonical_colors}

    # ── Figure 1: Training Loss Comparison ──────────────────
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    ax = axes[0]
    for name, r in results.items():
        logs = r["logs"]
        epochs = [log.epoch for log in logs]
        losses = [log.train_loss if np.isfinite(log.train_loss) else None for log in logs]
        # Truncate at blow-up
        valid = [(e, l) for e, l in zip(epochs, losses) if l is not None and l < 100]
        if valid:
            e, l = zip(*valid)
            ls = '-' if name not in std_colors else ('--' if name == "SGD+Clip" else '-')
            lw = 2.0 if name in bsdt_colors else 1.5
            ax.plot(e, l, label=name, color=all_colors.get(name, '#999'),
                    linewidth=lw, linestyle=ls, alpha=0.85)

    ax.set_yscale('log')
    ax.set_xlabel('Epoch', fontsize=11)
    ax.set_ylabel('Training Loss (log scale)', fontsize=11)
    ax.set_title('(a) Training Loss: Standard vs BSDT Optimisers', fontsize=12, fontweight='bold')
    ax.legend(fontsize=7, ncol=2, loc='upper right', framealpha=0.9)
    ax.grid(True, alpha=0.15)
    ax.set_xlim(0, 300)

    # ── Figure 1b: Gradient Norm ────────────────────────────
    ax = axes[1]
    for name, r in results.items():
        logs = r["logs"]
        epochs = [log.epoch for log in logs if np.isfinite(log.grad_norm)]
        gnorms = [log.grad_norm for log in logs if np.isfinite(log.grad_norm)]
        if gnorms and max(gnorms) > 0:
            valid = [(e, g) for e, g in zip(epochs, gnorms) if g < 1e12]
            if valid:
                e, g = zip(*valid)
                ax.plot(e, g, label=name, color=all_colors.get(name, '#999'),
                        linewidth=1.5, alpha=0.85)

    ax.set_yscale('log')
    ax.set_xlabel('Epoch', fontsize=11)
    ax.set_ylabel('Gradient Norm $\\|\\nabla L\\|$ (log scale)', fontsize=11)
    ax.set_title('(b) Gradient Norm: Explosion vs Stabilisation', fontsize=12, fontweight='bold')
    ax.axhline(y=1e10, color='red', linestyle=':', linewidth=1, alpha=0.5, label='Blow-up threshold')
    ax.legend(fontsize=7, ncol=2, loc='upper right', framealpha=0.9)
    ax.grid(True, alpha=0.15)

    plt.tight_layout()
    for ext in ['png', 'pdf']:
        path = os.path.join(figdir, f'nn_loss_gradient.{ext}')
        plt.savefig(path, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"  Saved: {path}")
    plt.close(fig)

    # ── Figure 2: Friction Dynamics (BSDT + Canonical) ──────
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    ax = axes[0]
    bsdt_names = ["BSDT", "MFLS", "Molecular", "Gravity", "Hybrid",
                  "QuadSurf", "QuadExpo", "SignedLR"]
    canonical_names_fig = ["CanSpectral", "CanFull"]
    all_canonical = bsdt_names + canonical_names_fig
    for name in all_canonical:
        if name in results and not results[name]["blew_up"]:
            logs = results[name]["logs"]
            epochs = [log.epoch for log in logs if not log.blew_up]
            frictions = [log.friction for log in logs if not log.blew_up]
            lw = 2.5 if name in canonical_names_fig else 1.8
            ax.plot(epochs, frictions, label=name,
                    color=all_colors.get(name, '#999'), linewidth=lw, alpha=0.9)

    ax.set_xlabel('Epoch', fontsize=11)
    ax.set_ylabel('Friction Multiplier $1 + \\gamma^*$', fontsize=11)
    ax.set_title('(a) Self-Regulating Adaptive Friction', fontsize=12, fontweight='bold')
    ax.legend(fontsize=8, loc='upper right', framealpha=0.9)
    ax.grid(True, alpha=0.15)

    # Annotate three phases
    ax.axvspan(0, 20, alpha=0.05, color='red', label='Phase 1: Emergency braking')
    ax.axvspan(20, 200, alpha=0.03, color='orange')
    ax.axvspan(200, 300, alpha=0.03, color='green')
    ax.text(10, ax.get_ylim()[1] * 0.9, 'Phase 1\nBraking', fontsize=8,
            ha='center', color='#c0392b', fontweight='bold', alpha=0.7)
    ax.text(110, ax.get_ylim()[1] * 0.9, 'Phase 2\nDescent', fontsize=8,
            ha='center', color='#e67e22', fontweight='bold', alpha=0.7)
    ax.text(250, ax.get_ylim()[1] * 0.9, 'Phase 3\nEquilibrium', fontsize=8,
            ha='center', color='#27ae60', fontweight='bold', alpha=0.7)

    # ── Figure 2b: Test Accuracy ────────────────────────────
    ax = axes[1]
    for name, r in results.items():
        if r["blew_up"]:
            continue
        logs = r["logs"]
        epochs = [log.epoch for log in logs if not log.blew_up]
        accs = [log.test_acc for log in logs if not log.blew_up]
        if accs:
            ls = '-' if name not in std_colors else '--'
            ax.plot(epochs, accs, label=name, color=all_colors.get(name, '#999'),
                    linewidth=1.5, linestyle=ls, alpha=0.85)

    ax.set_xlabel('Epoch', fontsize=11)
    ax.set_ylabel('Test Accuracy', fontsize=11)
    ax.set_title('(b) Test Accuracy Comparison', fontsize=12, fontweight='bold')
    ax.legend(fontsize=7, ncol=2, loc='lower right', framealpha=0.9)
    ax.grid(True, alpha=0.15)
    ax.set_ylim(0.45, 1.0)

    plt.tight_layout()
    for ext in ['png', 'pdf']:
        path = os.path.join(figdir, f'nn_friction_accuracy.{ext}')
        plt.savefig(path, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"  Saved: {path}")
    plt.close(fig)

    # ── Figure 3: Channel Decomposition at Peak Stress ──────
    fig, ax = plt.subplots(figsize=(12, 6))

    channel_names = ["camouflage", "feature_gap", "activity", "temporal_novelty"]
    channel_labels = ["$\\delta_C$ (Camouflage)", "$\\delta_G$ (Feature Gap)",
                      "$\\delta_A$ (Activity)", "$\\delta_T$ (Temporal)"]

    bar_data = {}
    for name in bsdt_names:
        if name in results and not results[name]["blew_up"]:
            logs = results[name]["logs"]
            # Find epoch with peak friction
            valid = [log for log in logs if log.channels is not None]
            if valid:
                peak_log = max(valid, key=lambda l: l.friction)
                bar_data[name] = peak_log.channels

    # Include canonical optimisers in channel chart
    for name in canonical_names_fig:
        if name in results and not results[name]["blew_up"]:
            logs = results[name]["logs"]
            valid = [log for log in logs if log.channels is not None]
            if valid:
                peak_log = max(valid, key=lambda l: l.friction)
                bar_data[name] = peak_log.channels

    if bar_data:
        x = np.arange(len(bar_data))
        width = 0.18
        for j, (ch_name, ch_label) in enumerate(zip(channel_names, channel_labels)):
            vals = [bar_data[n].get(ch_name, 0.0) for n in bar_data]
            ax.bar(x + j * width, vals, width, label=ch_label, alpha=0.8)

        # Highlight canonical bars with a border
        for xi, name in enumerate(bar_data):
            if name in canonical_names_fig:
                for j in range(len(channel_names)):
                    ax.patches[xi + j * len(bar_data)].set_edgecolor("#6c3483")
                    ax.patches[xi + j * len(bar_data)].set_linewidth(1.5)

        ax.set_xticks(x + 1.5 * width)
        ax.set_xticklabels(list(bar_data.keys()), rotation=30, ha='right')
        ax.set_ylabel('Channel Value at Peak Stress', fontsize=11)
        ax.set_title('BSDT Channel Decomposition at Peak Friction', fontsize=12, fontweight='bold')
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.15, axis='y')

    plt.tight_layout()
    for ext in ['png', 'pdf']:
        path = os.path.join(figdir, f'nn_channel_decomposition.{ext}')
        plt.savefig(path, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"  Saved: {path}")
    plt.close(fig)

    # ── Figure 4: Bar chart summary ────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    all_names = list(results.keys())
    survived = [results[n]["epochs_survived"] for n in all_names]
    losses = [min(results[n]["final_train_loss"], 10.0) for n in all_names]
    accs = [results[n]["best_test_acc"] for n in all_names]
    bar_colors = [all_colors.get(n, '#999') for n in all_names]

    # Survived epochs
    ax = axes[0]
    bars = ax.barh(range(len(all_names)), survived, color=bar_colors, alpha=0.8)
    ax.set_yticks(range(len(all_names)))
    ax.set_yticklabels(all_names, fontsize=8)
    ax.set_xlabel('Epochs Survived (out of 300)')
    ax.set_title('Epochs Survived', fontsize=11, fontweight='bold')
    ax.axvline(x=300, color='green', linestyle=':', linewidth=1, alpha=0.5)

    # Final loss
    ax = axes[1]
    ax.barh(range(len(all_names)), losses, color=bar_colors, alpha=0.8)
    ax.set_yticks(range(len(all_names)))
    ax.set_yticklabels(all_names, fontsize=8)
    ax.set_xlabel('Final Train Loss (capped at 10)')
    ax.set_title('Final Training Loss', fontsize=11, fontweight='bold')
    ax.set_xscale('log')

    # Best accuracy
    ax = axes[2]
    ax.barh(range(len(all_names)), accs, color=bar_colors, alpha=0.8)
    ax.set_yticks(range(len(all_names)))
    ax.set_yticklabels(all_names, fontsize=8)
    ax.set_xlabel('Best Test Accuracy')
    ax.set_title('Best Test Accuracy', fontsize=11, fontweight='bold')
    ax.axvline(x=0.5, color='red', linestyle=':', linewidth=1, alpha=0.5, label='Chance')

    plt.tight_layout()
    for ext in ['png', 'pdf']:
        path = os.path.join(figdir, f'nn_summary_bars.{ext}')
        plt.savefig(path, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"  Saved: {path}")
    plt.close(fig)


# ═════════════════════════════════════════════════════════════
#  SAVE RESULTS
# ═════════════════════════════════════════════════════════════

def save_results(results: dict, outdir: str = None):
    """Save results JSON (without raw log objects)."""
    if outdir is None:
        outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(outdir, exist_ok=True)

    json_results = {}
    for name, r in results.items():
        json_results[name] = {
            "name": r["name"],
            "blew_up": r["blew_up"],
            "blow_up_epoch": r["blow_up_epoch"],
            "epochs_survived": r["epochs_survived"],
            "final_train_loss": r["final_train_loss"] if np.isfinite(r["final_train_loss"]) else "Inf",
            "final_test_acc": r["final_test_acc"],
            "best_test_acc": r["best_test_acc"],
            "peak_grad_norm": r["peak_grad_norm"] if np.isfinite(r["peak_grad_norm"]) else "Inf",
            "peak_friction": r["peak_friction"],
            "final_friction": r["final_friction"],
            "elapsed_s": r["elapsed_s"],
            "phases": r["phases"],
        }

    outfile = os.path.join(outdir, "nn_gradient_results.json")
    with open(outfile, "w") as f:
        json.dump(json_results, f, indent=2, default=str)
    print(f"  Results saved to: {outfile}")

    # Also save the summary table
    table = print_summary_table(results)
    with open(os.path.join(outdir, "nn_summary_table.txt"), "w", encoding="utf-8") as f:
        f.write(table)


# ═════════════════════════════════════════════════════════════
#  MAIN
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("  Domain IV: Neural Network Gradient Stability")
    print("  BlowUpNet × 15 Optimisers  (13 standard/BSDT + 2 Canonical)")
    print("=" * 70)
    print()

    # hidden_dim=64, n_layers=10: retains blow-up pathology (init_scale=2.0)
    # while keeping per-optimiser runtime to ~5-15 s on CPU.
    # For the full 512/20 experiment (research quality) set:
    #   hidden_dim=512, n_layers=20  (~40 min total on CPU)
    results = run_experiment(
        n_epochs=300, lr=0.01, seed=42, verbose=True,
        hidden_dim=64, n_layers=10,
    )

    print()
    table = print_summary_table(results)

    print("\nGenerating figures...")
    generate_figures(results)

    print("\nSaving results...")
    save_results(results)

    print("\nDone.")
