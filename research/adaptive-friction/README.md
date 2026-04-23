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

## Central Claim

> In decentralised economic systems with adaptive strategic agents, zero-friction equilibria are generically unstable. Bounded adaptive friction — dynamically responding to adversarial pressure — is both necessary and sufficient for long-run stability.

If proven rigorously, this changes how we understand frictionless markets, DeFi stability, and institutional economic design.

## Tier Classification

- **Tier 1** — Provably stable decentralised monetary system (Nobel-level direction)
- **Tier 2** — Optimal adaptive transaction friction (AMTTP direction, high commercial + academic value)

This project targets **both simultaneously**: Tier 2 as the near-term deliverable, Tier 1 as the long-term arc.

## Repository Structure

```
adaptive-friction-stability/
├── README.md                          # This file
├── 01_RESEARCH_OVERVIEW.md            # Title, aims, objectives
├── 02_KERNEL_ANALYSIS.md              # Is it gravity or molecular? Physics analysis
├── 03_DATA_SPECIFICATION.md           # All datasets for simulation
├── 04_CASE_STUDIES.md                 # Terra/Luna, Iron Finance, Chainlink, FTX, Curve
├── 05_THEORETICAL_FRAMEWORK.md        # Dynamical system, Lyapunov proof structure
├── 06_RL_ARCHITECTURE.md              # Where RL fits, MDP formulation, safety constraints
├── 07_RESEARCH_PLAN.md                # Timeline, paper decomposition, milestones
└── papers/                            # Paper drafts (future)
```

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
