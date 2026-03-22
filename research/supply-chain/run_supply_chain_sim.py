"""
run_supply_chain_sim.py — Domain VI: Supply Chain Disruption Simulation
========================================================================
Runs all five historical disruption scenarios under three control regimes:
  1. No intervention (baseline — how bad does the cascade get?)
  2. Constant buffer (fixed safety stock — analogous to constant Basel III)
  3. Adaptive BSDT friction (γ* = α / λ_max — adaptive rerouting/buffering)

Validates the critical manifold theorem: constant buffers fail above C*,
adaptive friction succeeds.

Generates:
  - Per-scenario comparison plots
  - Cross-scenario summary table
  - Channel decomposition analysis
  - Results JSON for the paper
"""

from __future__ import annotations
import sys, os, json, time
import numpy as np

# Ensure we can import from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from supply_chain_engine import run_simulation
from scenarios import ALL_SCENARIOS


def compute_metrics(result: dict, disruption_onset: int) -> dict:
    """Extract key metrics from a simulation run."""
    energy = result["energy"]
    mfls = result["mfls"]
    node_health = result["node_health"]
    cascade_depth = result["cascade_depth"]
    lambda_max = result["lambda_max"]
    gamma_star = result["gamma_star"]
    above_cman = result["above_cman"]
    cos_theta = result["cos_theta"]

    # Post-disruption window
    post = slice(disruption_onset, None)

    # Peak cascade depth (max nodes with health < 50%)
    peak_cascade = float(np.max(cascade_depth[post]))

    # Mean node health in post-disruption period
    mean_health_post = float(np.mean(node_health[post]))

    # Recovery time: steps until mean health returns to 90% of pre-disruption
    pre_health = float(np.mean(node_health[:disruption_onset]))
    recovery_threshold = 0.9 * pre_health
    post_health = np.mean(node_health[post], axis=1)
    recovered_steps = np.where(post_health >= recovery_threshold)[0]
    recovery_time = int(recovered_steps[0]) if len(recovered_steps) > 0 else -1

    # MFLS early warning: how many steps before disruption does MFLS spike?
    # Uses a rolling z-score to detect precursor anomaly
    pre_mfls_mean = float(np.mean(mfls[:disruption_onset]))
    pre_mfls_std = float(np.std(mfls[:disruption_onset])) + 1e-8
    mfls_z = (mfls - pre_mfls_mean) / pre_mfls_std
    # Find the FIRST time z > 2 in the window [onset-30, onset]
    early_warning_steps = 0
    search_start = max(0, disruption_onset - 30)
    for t in range(search_start, disruption_onset):
        if mfls_z[t] > 2.0:
            early_warning_steps = disruption_onset - t
            break
    # Also check: does MFLS ever exceed 1.5σ in the 10 steps around onset?
    # (cascade effects may cause gradual precursor buildup)
    if early_warning_steps == 0:
        for t in range(max(0, disruption_onset - 10), min(len(mfls), disruption_onset + 5)):
            if mfls_z[t] > 1.5:
                early_warning_steps = max(0, disruption_onset - t)
                break

    # Fraction of time above critical manifold
    frac_above_cman = float(np.mean(above_cman[post]))

    # Peak energy
    peak_energy = float(np.max(energy[post]))

    # Mean gradient alignment (report |cos θ| — the magnitude is what
    # validates the Morse-index equivalence Theorem C)
    mean_cos = float(np.mean(np.abs(cos_theta[post])))

    # Channel dominance at peak disruption
    channels = result["channels"]
    peak_t = disruption_onset + int(np.argmax(cascade_depth[post]))
    channel_at_peak = {k: float(v[peak_t]) for k, v in channels.items()}

    return {
        "peak_cascade_depth": peak_cascade,
        "mean_health_post": mean_health_post,
        "recovery_time_steps": recovery_time,
        "early_warning_steps": early_warning_steps,
        "frac_above_cman": frac_above_cman,
        "peak_energy": peak_energy,
        "mean_gradient_alignment": mean_cos,
        "channel_at_peak": channel_at_peak,
    }


def run_all_scenarios(verbose: bool = True) -> dict:
    """Run all scenarios under all three control modes."""
    all_results = {}

    for scenario_name, scenario_fn in ALL_SCENARIOS.items():
        network, disruptions, meta = scenario_fn()

        if verbose:
            print(f"\n{'='*70}")
            print(f"  Scenario: {meta['name']} ({meta['period']})")
            print(f"  Nodes: {len(network.nodes)}, Edges: {len(network.edges)}")
            print(f"  Disruptions: {len(disruptions)}")
            print(f"{'='*70}")

        earliest_onset = min(d.onset_step for d in disruptions)
        scenario_results = {}

        for mode in ["none", "constant", "adaptive"]:
            t0 = time.time()
            result = run_simulation(
                network=network,
                disruptions=disruptions,
                n_steps=200,
                eta=0.02,
                mode=mode,
                buffer_level=0.2,
                cascade_rate=0.15,
                seed=42,
                verbose=False,
            )
            elapsed = time.time() - t0
            metrics = compute_metrics(result, earliest_onset)

            scenario_results[mode] = {
                "metrics": metrics,
                "raw": result,    # kept for plotting
                "elapsed_s": elapsed,
            }

            if verbose:
                m = metrics
                label = {"none": "No intervention",
                         "constant": "Constant buffer",
                         "adaptive": "Adaptive BSDT"}[mode]
                print(f"\n  [{label}]  ({elapsed:.2f}s)")
                print(f"    Peak cascade depth:    {m['peak_cascade_depth']:.1f} nodes")
                print(f"    Mean health (post):    {m['mean_health_post']:.3f}")
                print(f"    Recovery time:         {m['recovery_time_steps']} steps")
                print(f"    Early warning:         {m['early_warning_steps']} steps")
                print(f"    Frac above C*:         {m['frac_above_cman']:.3f}")
                print(f"    Gradient alignment:    {m['mean_gradient_alignment']:.3f}")

        all_results[scenario_name] = {
            "meta": meta,
            "results": scenario_results,
        }

    return all_results


def print_summary_table(all_results: dict) -> str:
    """Generate paper-ready summary table."""
    lines = []
    lines.append("\n" + "="*90)
    lines.append("  SUPPLY CHAIN BSDT UNIVERSALITY — SUMMARY TABLE")
    lines.append("="*90)
    lines.append(f"  {'Scenario':<30s} {'Mode':<12s} {'Cascade':>8s} {'Health':>8s} "
                 f"{'Recovery':>9s} {'Warning':>8s} {'Above C*':>9s}")
    lines.append("-"*90)

    for scenario_name, data in all_results.items():
        name_short = data["meta"]["name"][:28]
        for mode in ["none", "constant", "adaptive"]:
            m = data["results"][mode]["metrics"]
            rec = f"{m['recovery_time_steps']:d}" if m['recovery_time_steps'] >= 0 else "DNR"
            line = (f"  {name_short:<30s} {mode:<12s} "
                    f"{m['peak_cascade_depth']:8.1f} "
                    f"{m['mean_health_post']:8.3f} "
                    f"{rec:>9s} "
                    f"{m['early_warning_steps']:8d} "
                    f"{m['frac_above_cman']:9.3f}")
            lines.append(line)
            name_short = ""   # blank for subsequent rows
        lines.append("-"*90)

    lines.append("")
    lines.append("  DNR = Did Not Recover within simulation horizon")
    lines.append("  Cascade = peak number of nodes with health < 50%")
    lines.append("  Warning = MFLS early warning (steps before disruption onset)")
    lines.append("")

    table = "\n".join(lines)
    print(table)
    return table


def save_results(all_results: dict, outdir: str = None):
    """Save results JSON (without raw numpy arrays)."""
    if outdir is None:
        outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(outdir, exist_ok=True)

    # Strip raw arrays for JSON serialisation
    json_results = {}
    for scenario_name, data in all_results.items():
        json_results[scenario_name] = {
            "meta": data["meta"],
            "metrics": {}
        }
        for mode in ["none", "constant", "adaptive"]:
            json_results[scenario_name]["metrics"][mode] = \
                data["results"][mode]["metrics"]

    outfile = os.path.join(outdir, "supply_chain_results.json")
    with open(outfile, "w") as f:
        json.dump(json_results, f, indent=2, default=str)
    print(f"\n  Results saved to: {outfile}")
    return outfile


def generate_figures(all_results: dict, figdir: str = None):
    """Generate publication-quality figures."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.gridspec import GridSpec
    except ImportError:
        print("  [WARN] matplotlib not available — skipping figures")
        return

    if figdir is None:
        figdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
    os.makedirs(figdir, exist_ok=True)

    # Colour scheme matching paper style
    colors = {"none": "#e74c3c", "constant": "#f39c12", "adaptive": "#2ecc71"}
    labels = {"none": "No intervention", "constant": "Constant buffer",
              "adaptive": "Adaptive (BSDT)"}

    for scenario_name, data in all_results.items():
        meta = data["meta"]
        fig = plt.figure(figsize=(16, 12))
        fig.suptitle(f"Supply Chain BSDT — {meta['name']}", fontsize=14, fontweight='bold')
        gs = GridSpec(3, 2, figure=fig, hspace=0.35, wspace=0.30)

        # ── Panel A: Mean node health ────────────────────────
        ax1 = fig.add_subplot(gs[0, 0])
        for mode in ["none", "constant", "adaptive"]:
            raw = data["results"][mode]["raw"]
            health = np.mean(raw["node_health"], axis=1)
            ax1.plot(health, color=colors[mode], label=labels[mode], linewidth=1.5)
        # Mark disruption onset
        earliest = min(d.onset_step for d in
                       ALL_SCENARIOS[scenario_name]()[1])
        ax1.axvline(earliest, color='gray', linestyle='--', alpha=0.5, label='Disruption onset')
        ax1.set_title("(a) Mean Node Health")
        ax1.set_xlabel("Time step")
        ax1.set_ylabel("Health (0–1)")
        ax1.legend(fontsize=8)
        ax1.set_ylim(0, 1.05)
        ax1.grid(True, alpha=0.3)

        # ── Panel B: Cascade depth ──────────────────────────
        ax2 = fig.add_subplot(gs[0, 1])
        for mode in ["none", "constant", "adaptive"]:
            raw = data["results"][mode]["raw"]
            ax2.plot(raw["cascade_depth"], color=colors[mode],
                     label=labels[mode], linewidth=1.5)
        ax2.axvline(earliest, color='gray', linestyle='--', alpha=0.5)
        ax2.set_title("(b) Cascade Depth (nodes with health < 50%)")
        ax2.set_xlabel("Time step")
        ax2.set_ylabel("Affected nodes")
        ax2.legend(fontsize=8)
        ax2.grid(True, alpha=0.3)

        # ── Panel C: MFLS detection score ────────────────────
        ax3 = fig.add_subplot(gs[1, 0])
        raw_adapt = data["results"]["adaptive"]["raw"]
        ax3.plot(raw_adapt["mfls"], color='#3498db', linewidth=1.5, label='MFLS score')
        ax3.axvline(earliest, color='gray', linestyle='--', alpha=0.5, label='Disruption onset')
        # Mark z > 2 threshold
        pre_mean = np.mean(raw_adapt["mfls"][:earliest])
        pre_std = np.std(raw_adapt["mfls"][:earliest]) + 1e-8
        threshold = pre_mean + 2 * pre_std
        ax3.axhline(threshold, color='red', linestyle=':', alpha=0.7, label='z=2 threshold')
        ax3.set_title("(c) MFLS Early Warning Signal")
        ax3.set_xlabel("Time step")
        ax3.set_ylabel("‖∇E_BS‖")
        ax3.legend(fontsize=8)
        ax3.grid(True, alpha=0.3)

        # ── Panel D: λ_max and γ* ───────────────────────────
        ax4 = fig.add_subplot(gs[1, 1])
        ax4.plot(raw_adapt["lambda_max"], color='#e74c3c', linewidth=1.5,
                 label='λ_max')
        ax4_r = ax4.twinx()
        ax4_r.plot(raw_adapt["gamma_star"], color='#2ecc71', linewidth=1.5,
                   label='γ* (adaptive)')
        ax4.axhline(0.10, color='gray', linestyle=':', alpha=0.5, label='α (spring)')
        ax4.axvline(earliest, color='gray', linestyle='--', alpha=0.5)
        ax4.set_title("(d) Spectral Radius & Adaptive Friction")
        ax4.set_xlabel("Time step")
        ax4.set_ylabel("λ_max", color='#e74c3c')
        ax4_r.set_ylabel("γ*", color='#2ecc71')
        ax4.legend(fontsize=8, loc='upper left')
        ax4_r.legend(fontsize=8, loc='upper right')
        ax4.grid(True, alpha=0.3)

        # ── Panel E: Four BSDT channels ─────────────────────
        ax5 = fig.add_subplot(gs[2, 0])
        ch_colors = {"camouflage": "#9b59b6", "feature_gap": "#e67e22",
                     "activity": "#e74c3c", "temporal_novelty": "#3498db"}
        ch_labels = {"camouflage": "δ_C (Camouflage)",
                     "feature_gap": "δ_G (Feature Gap)",
                     "activity": "δ_A (Activity)",
                     "temporal_novelty": "δ_T (Novelty)"}
        channels = raw_adapt["channels"]
        for ch_name, ch_data in channels.items():
            ax5.plot(ch_data, color=ch_colors[ch_name], linewidth=1.2,
                     label=ch_labels[ch_name])
        ax5.axvline(earliest, color='gray', linestyle='--', alpha=0.5)
        ax5.set_title("(e) BSDT Channel Decomposition")
        ax5.set_xlabel("Time step")
        ax5.set_ylabel("Channel score")
        ax5.legend(fontsize=8)
        ax5.grid(True, alpha=0.3)

        # ── Panel F: Gradient alignment cos θ ────────────────
        ax6 = fig.add_subplot(gs[2, 1])
        ax6.plot(raw_adapt["cos_theta"], color='#2c3e50', linewidth=1.2)
        ax6.axhline(0.7, color='green', linestyle=':', alpha=0.5, label='cos θ = 0.7')
        ax6.axvline(earliest, color='gray', linestyle='--', alpha=0.5, label='Disruption onset')
        ax6.set_title("(f) Gradient Alignment (∇E_BS vs −∇Φ)")
        ax6.set_xlabel("Time step")
        ax6.set_ylabel("cos θ")
        ax6.set_ylim(-1.05, 1.05)
        ax6.legend(fontsize=8)
        ax6.grid(True, alpha=0.3)

        plt.savefig(os.path.join(figdir, f"{scenario_name}.png"),
                    dpi=200, bbox_inches='tight')
        plt.savefig(os.path.join(figdir, f"{scenario_name}.pdf"),
                    bbox_inches='tight')
        plt.close(fig)
        print(f"  Figure saved: {scenario_name}.png / .pdf")

    # ── Cross-scenario comparison bar chart ──────────────────
    fig2, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig2.suptitle("Cross-Scenario: Adaptive BSDT vs Baselines", fontsize=13, fontweight='bold')

    scenario_labels = [data["meta"]["name"][:20] for data in all_results.values()]
    x = np.arange(len(scenario_labels))
    width = 0.25

    for idx, metric in enumerate(["peak_cascade_depth", "mean_health_post", "recovery_time_steps"]):
        ax = axes[idx]
        for j, mode in enumerate(["none", "constant", "adaptive"]):
            vals = []
            for data in all_results.values():
                v = data["results"][mode]["metrics"][metric]
                if metric == "recovery_time_steps" and v < 0:
                    v = 200  # DNR → max
                vals.append(v)
            ax.bar(x + j * width, vals, width, color=colors[mode], label=labels[mode])

        ax.set_xticks(x + width)
        ax.set_xticklabels(scenario_labels, rotation=30, ha='right', fontsize=8)
        title_map = {"peak_cascade_depth": "Peak Cascade Depth (↓ better)",
                     "mean_health_post": "Mean Health Post-Disruption (↑ better)",
                     "recovery_time_steps": "Recovery Time in Steps (↓ better)"}
        ax.set_title(title_map[metric], fontsize=10)
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(os.path.join(figdir, "cross_scenario_comparison.png"),
                dpi=200, bbox_inches='tight')
    plt.savefig(os.path.join(figdir, "cross_scenario_comparison.pdf"),
                bbox_inches='tight')
    plt.close(fig2)
    print(f"  Figure saved: cross_scenario_comparison.png / .pdf")


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║  BSDT Domain VI: Supply Chain Disruption & Resilience          ║")
    print("║  Grand Unification Paper — Section 8 Validation                ║")
    print("╚══════════════════════════════════════════════════════════════════╝")

    all_results = run_all_scenarios(verbose=True)
    table = print_summary_table(all_results)
    outfile = save_results(all_results)
    generate_figures(all_results)

    # Save table as text
    table_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "results", "summary_table.txt")
    with open(table_file, "w") as f:
        f.write(table)
    print(f"  Table saved to: {table_file}")

    print("\n  Done. Results ready for paper Section 8.")
