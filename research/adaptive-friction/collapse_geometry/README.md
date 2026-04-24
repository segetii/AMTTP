# Collapse Geometry — Full §I–XXVII Implementation

A single, coherent Python package that implements **every closed-form expression**
from the *Mathematical Anatomy of System Collapse* spec (sections I through XXVII).

Replaces the prior **shadow** code (`mfls-sdk/`, `variants/`, `pipeline/`,
`udl/energyv3/`) — which implemented BSDT channels, MFLS scoring variants, and
the GravityEngine in scattered form — with a unified package that adds:

- the **corrected pullback gradient** G̃_t = Σ_k g_k ∂δ_k/∂X (§XXIV.1)
- **two distinct collapse directions** (channel u and state u) (§XXIV.2)
- the **ψ_t misalignment angle** — the sixth diagnostic signal (§XXVI)
- **per-channel Lyapunov contributions** V̇_k with η_k efficiency (§XXV)
- the **MolecularEngine** (Langevin/velocity-Verlet) and **HybridEngine** (gravity + LJ + control)
- the **stochastic extension** (Itô, Fokker-Planck stationary, Kramers escape)
- **inverse-problem identification** + **agent sensitivity** + **hysteresis recovery**

## Module map

| File | Spec sections |
|------|---------------|
| `state.py` | §I  state matrix + calibration |
| `network.py` | §II Ledoit-Wolf shrinkage network |
| `potential.py` | §III + §V  Φ + Hessian Gershgorin bound |
| `forces.py` | §IV  Laplacian-form force field |
| `bsdt.py` | §VI + §XXIV.1  4 channels + Jacobians |
| `unified_energy.py` | §XII  Quadsurf + Expogate + SignedLR |
| `mfls.py` | §XXIV.4 + §XXVI  channel/state MFLS, ρ, ψ |
| `damping.py` | §VIII  γ*(X) = e/(e+θ) |
| `control.py` | §XV  **MasterOperator** Ẋ = F − γ*⟨F,u⟩u |
| `lyapunov.py` | §XVI + §XXIV.5 + §XXV  V, dV/dt, M_t, γ*_min, V̇_k |
| `geometry.py` | §XIV  tan θ, three equivalent collapse conditions |
| `ews.py` | §XVII + §XXVI.3  6-signal EWS |
| `escape.py` | §XVIII  τ_lin, τ_quad, τ_safe |
| `stochastic.py` | §XIX  Itô, Fokker-Planck, Kramers |
| `inverse.py` | §XX  parameter identification, attribution |
| `sensitivity.py` | §XXI  ∂λ_max/∂x_i agent importance |
| `recovery.py` | §XXII  hysteresis, γ_crit, reverse operator |
| `info_theory.py` | §XXIII  KL divergence, χ² threshold, Fisher |
| `engines/gravity.py` | first-order overdamped GravityEngine |
| `engines/molecular.py` | second-order Langevin (velocity-Verlet) |
| `engines/hybrid.py` | gravity + Lennard-Jones + master control |

## Quick start

```python
import numpy as np
from collapse_geometry import MasterOperator, Snapshot, Hybrid

X_normal = np.load("normal_period.npy")            # (T0, N, d)
M = MasterOperator.calibrate(X_normal, k=4, theta=1.0)

snap = Snapshot(X=X_now, X_prev=X_prev, history=X_normal[-20:])

# Single-step controlled velocity (§XV master operator):
dXdt = M.step(snap)

# Run with the production Hybrid engine (gravity + molecular + control):
engine = Hybrid(op=M, dt=1e-2, zeta=0.1, kT=1e-4)
trajectory, _ = engine.trajectory(snap, T=500)
```

## Demo

```powershell
cd c:\amttp\research\adaptive-friction\collapse_geometry
py -3 demo_full_system.py
```

Prints every diagnostic from §VI–§XXVII on a synthetic 8-institution stress event,
and runs all three engines (Gravity, Molecular, Hybrid) for 50 steps.

## Scope of "shadow → full" upgrade

| Capability | Shadow (pre-existing) | Full (this package) |
|---|---|---|
| BSDT 4 channels | ✅ scattered | ✅ unified + Jacobians |
| MFLS scoring | ✅ 5 variants | ✅ + dual (channel/state) + ρ_MFLS |
| GravityEngine | ✅ | ✅ + controlled mode |
| Master Operator | ❌ (only γ* ad-hoc) | ✅ §XV explicit Ẋ = F − γ*⟨F,u⟩u |
| Pullback gradient G̃ | ❌ | ✅ §XXIV.1 |
| ψ_t misalignment | ❌ | ✅ §XXVI |
| Per-channel V̇_k + η_k | ❌ | ✅ §XXV |
| Stability margin M_t | ❌ | ✅ §XXIV.5 (corrected) |
| Three eq. collapse conditions | ❌ | ✅ §XIV |
| 6-signal EWS | ⚠️ 5-only | ✅ +ξ_6 = cos²ψ |
| Escape time τ_lin/τ_quad/τ_safe | ❌ | ✅ §XVIII |
| Itô + Fokker-Planck + Kramers | ❌ | ✅ §XIX |
| Inverse problem | ❌ | ✅ §XX |
| Agent sensitivity | ❌ | ✅ §XXI |
| Recovery / hysteresis | ❌ | ✅ §XXII |
| KL / χ² / Fisher | ❌ | ✅ §XXIII |
| MolecularEngine | ❌ | ✅ Langevin velocity-Verlet |
| HybridEngine | ❌ | ✅ gravity + LJ + control |
