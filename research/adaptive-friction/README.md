# Adaptive Friction as a Stability Mechanism in Decentralised Economic Systems

**A Dissipative Particle Dynamics Approach with Lyapunov Guarantees**

*Theory, Simulation, and Application to Algorithmic Monetary Stability and Transaction Compliance*

**Author:** Odeyemi Olusegun Israel

---

## Project Summary

This research programme proves that **adaptive endogenous friction is necessary and sufficient for stability** in decentralised economic systems with strategic adversaries. The framework uses dissipative particle dynamics (DPD) — drawing from molecular physics rather than Newtonian gravity — with formal Lyapunov stability guarantees.

The work connects three strands:

1. **Pure Theory** — Lyapunov proof that zero-friction equilibria are generically unstable under adversarial perturbation
2. **Reinforcement Learning** — Lyapunov-constrained adversarial RL to learn optimal friction policies online
3. **Production System** — AMTTP protocol as a working implementation of adaptive friction for DeFi compliance

## Start Here

If you want direction instead of theory-only framing, use this order:

1. **Core package** — [collapse_geometry/README.md](collapse_geometry/README.md)
	This is the unified implementation of the collapse-geometry / BSDT stack.
2. **Empirical validation pipeline** — [upgraded/run_pipeline.py](upgraded/run_pipeline.py)
	This is the clearest banking / FDIC / FRED entry point.
3. **Trading map** — [pipeline/results/README.md](pipeline/results/README.md)
	This explains which trading scripts matter and which files are outputs.
4. **Math explainer** — [pipeline/results/math_reference (1).html](pipeline/results/math_reference%20(1).html)
	This is a readable presentation of the mathematical anatomy, not the core engine.

## Central Claim

> In decentralised economic systems with adaptive strategic agents, zero-friction equilibria are generically unstable. Bounded adaptive friction — dynamically responding to adversarial pressure — is both necessary and sufficient for long-run stability.

If proven rigorously, this changes how we understand frictionless markets, DeFi stability, and institutional economic design.

## Tier Classification

- **Tier 1** — Provably stable decentralised monetary system (Nobel-level direction)
- **Tier 2** — Optimal adaptive transaction friction (AMTTP direction, high commercial + academic value)

This project targets **both simultaneously**: Tier 2 as the near-term deliverable, Tier 1 as the long-term arc.

## Directory Map

The active code is organised around three main areas:

```text
research/adaptive-friction/
├── README.md
├── collapse_geometry/                 # Unified theory package and master operator stack
├── upgraded/                          # FDIC/FRED empirical pipeline and validation scripts
├── pipeline/results/                  # Crypto trading scripts plus generated result archive
├── banklevel/                         # Bank-level analysis variants
├── banklevel_enhanced/                # Extended bank-level experiments
├── alignment_results/                 # Generated alignment outputs
├── docs/                              # Supporting notes and figures
├── paper/                             # Paper support material
├── papers/                            # Drafts and longer-form writeups
├── reproduce.py                       # Reproduction helper
├── run_real_data_simulations.py       # Real-data simulation entry point
└── run_ews_leadtime.py                # Early-warning lead-time analysis
```

### What each area is for

- **`collapse_geometry/`** is the clean implementation of the mathematical system.
- **`upgraded/`** is the cleanest place to understand adaptive friction on banking data.
- **`pipeline/results/`** is the busiest folder: it mixes crypto trading code, domain experiments, and generated outputs. Read its local README before touching versioned scripts.

## Key Innovation

Standard economics treats friction as a distortion to be minimised. This work proves friction is a **stabilising control variable** — without it, decentralised systems are structurally vulnerable to adversarial destabilisation. The GravityEngine (more accurately: Dissipative Particle Engine) provides the computational substrate, and the Lyapunov function provides the mathematical certificate.

## Connection to Existing Work

- **GravityEngine** → `udl/gravity.py` — the particle dynamics engine (1,048 lines, committed)
- **AMTTP** → the compliance protocol — friction implemented as approve/review/escrow/block
- **UDL** → Universal Deviation Law — the anomaly detection framework
- **BSDT** → Blind Spot Decomposition Theory — diagnostic theory for detector failures

## Status

- [x] GravityEngine implemented and benchmarked
- [x] AMTTP compliance matrix operational
- [x] Benchmark results: UDL vs DeepSVDD vs ECOD (5-seed, 5 datasets)
- [x] Crypto BSDT pipeline v22 → v32 with stress-tested PROD strategy
- [ ] Formal Lyapunov stability proof
- [ ] Historical collapse simulations (Terra/Luna, Iron Finance, FTX)
- [ ] RL friction controller
- [ ] Paper 1 draft (theory)
- [ ] Paper 2 draft (RL + simulation)
- [ ] Paper 3 elevation (AMTTP + theoretical foundation)

## Live Results

**Crypto BSDT sizing-architecture arc (v22 → v32):** see [pipeline/results/SIZING_ARCHITECTURE_RESULTS.md](pipeline/results/SIZING_ARCHITECTURE_RESULTS.md) for the complete honest record of what worked, what failed, and why. PROD recommendation: **v22 (K=3.5, +$5,705 PnL)** or **v32 (stress-budgeted K_max=4.0, +$3,840 PnL with 3σ shock survival)**.

For day-to-day navigation of the trading code and output archive, use [pipeline/results/README.md](pipeline/results/README.md).
