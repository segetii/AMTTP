# 05 — Theoretical Framework: Dynamical System and Lyapunov Proof Structure

## The Dynamical System

### Definition (Adversarial Decentralised Economy)

An **Adversarial Decentralised Economy** is a tuple E = (X, M, Φ, γ, ξ) where:

- **X(t) ∈ ℝ^{N×d}** — agent state matrix. Each row x_i(t) is agent i's position in d-dimensional economic state space (e.g., price, volume, holdings, risk metrics).

- **M = diag(m₁, ..., m_N) ∈ ℝ^{N×N}** — mass matrix. m_i represents agent i's capital/stake. Typically m_i follows a log-normal or Pareto distribution (power-law wealth distribution).

- **Φ: ℝ^{N×d} → ℝ** — interaction potential. Determines the force field governing agent interactions:

  ```
  Φ(X) = Σ_i (α/2)||x_i − μ||²                          [radial confinement]
        + Σ_{i<j} γ(σ√π/2) erf(||x_i−x_j||/σ)          [attraction]
        − Σ_{i<j} γλ log(||x_i−x_j|| + ε)               [repulsion]
  ```

- **γ(t) ≥ 0** — friction (damping) control. The adaptive compliance friction applied to the system. In AMTTP: γ maps to the decision matrix (approve/review/escrow/block).

- **ξ(t) ∈ ℝ^{N×d}** — adversarial perturbation. Bounded: ||ξ(t)|| ≤ B for adversary budget B.

### Equations of Motion

The system evolves according to damped Newtonian dynamics:

```
M Ẍ(t) = −∇Φ(X(t)) − γ(t) Ẋ(t) + ξ(t)
```

In first-order form (as implemented in GravityEngine with η as step size):

```
Ẋ = η · [−∇Φ(X) − γ Ẋ + ξ]
```

### Force Components (from udl/gravity.py)

The negative gradient of Φ decomposes as:

```
−∇_i Φ = F_radial + F_attract + F_repel + F_operator
```

where:

```
F_radial(x_i)  = −α(x_i − μ)                                    [spring toward centre]
F_attract(x_i) = −γ Σ_{j≠i} exp(−||x_i−x_j||²/σ²) · r̂_{ij}   [Gaussian clustering]
F_repel(x_i)   = +γλ Σ_{j≠i} 1/(||x_i−x_j||+ε) · r̂_{ij}      [prevent collapse]
F_operator(x_i)= −Σ_k β_k DΦ_k(x_i)ᵀ D_k(x_i)                 [external operators]
```

---

## Lyapunov Analysis

### The Lyapunov Candidate

Define the total mechanical energy:

```
V(X, Ẋ) = Φ(X) + (1/2) Ẋᵀ M Ẋ
```

This is the sum of:
- **Potential energy** Φ(X): interaction energy of the particle configuration
- **Kinetic energy** (1/2)||√M Ẋ||²: energy of agent movement

### Theorem 1: Energy Dissipation Under Friction

**Statement**: If γ(t) ≥ 0 and ξ(t) = 0 (no adversary), then:

```
V̇ ≤ −γ(t) ||Ẋ||²_M ≤ 0
```

**Proof sketch**:

```
V̇ = ∇Φ · Ẋ + Ẋᵀ M Ẍ
   = ∇Φ · Ẋ + Ẋᵀ (−∇Φ − γẊ + ξ)
   = ∇Φ · Ẋ − Ẋᵀ∇Φ − γ||Ẋ||²_M + Ẋᵀξ
   = −γ||Ẋ||²_M + Ẋᵀξ
```

When ξ = 0:

```
V̇ = −γ||Ẋ||²_M ≤ 0       ∀ γ ≥ 0
```

Energy is monotonically non-increasing. The system converges to a local minimum of Φ.

### Theorem 2: Instability Under Zero Friction

**Statement**: If γ = 0, then for any potential Φ with finite depth V_depth, there exists an adversarial strategy ξ* with ||ξ*|| ≤ B (for any B > 0) that drives ||X(t)|| → ∞ in finite time.

**Proof sketch**:

When γ = 0:
```
V̇ = Ẋᵀ ξ
```

The adversary chooses ξ* = B · Ẋ/||Ẋ|| (push in the direction of motion):

```
V̇ = B||Ẋ|| > 0
```

Energy increases monotonically. Once V > V_depth (the potential well rim), the confining potential loses effect and ||X(t)|| → ∞.

**Time to escape**:
```
T_escape ≤ V_depth / (B · ||Ẋ₀||)
```

where ||Ẋ₀|| is the initial velocity. Even from rest, thermal fluctuations provide initial velocity, and T_escape is finite.

**Key point**: This holds for **any** B > 0. No matter how small the adversary budget, zero friction always allows escape given enough time. This is the fundamental instability result.

### Theorem 3: Input-to-State Stability Under Adaptive Friction

**Statement**: If the adaptive friction satisfies:

```
γ(t) ≥ γ*(X, Ẋ, B) = B/||Ẋ|| + δ
```

for some δ > 0, then V satisfies:

```
V̇ ≤ −δ ||Ẋ||²_M
```

and the system is Input-to-State Stable (ISS) with respect to ξ.

**Proof**:

```
V̇ = −γ||Ẋ||²_M + Ẋᵀξ
   ≤ −γ||Ẋ||² + B||Ẋ||                    [Cauchy-Schwarz]
   = −(γ − B/||Ẋ||) · ||Ẋ||²
   ≤ −δ||Ẋ||²                              [by γ ≥ B/||Ẋ|| + δ]
```

Therefore V(t) → V_min as t → ∞. The trajectory is bounded. QED.

### The Critical Friction Threshold

The minimum friction for stability is:

```
γ*(t) = B / ||Ẋ(t)|| + δ
```

This has intuitive economic meaning:
- **B / ||Ẋ||**: friction must scale with the ratio of adversarial pressure to system velocity. If the adversary is strong and the market is slow → need heavy friction.
- **δ**: ensures strict dissipation even when adversarial pressure is zero.
- When ||Ẋ|| → 0 (market at rest), γ* → ∞: a stationary market is infinitely vulnerable to any adversary. This is the "dead market" vulnerability.
- When ||Ẋ|| is large (high trading volume), γ* → B/||Ẋ|| + δ ≈ δ: active markets need minimal friction because their kinetic energy self-stabilises.

### Theorem 4: Robustness to Potential Perturbation (Oracle Attacks)

**Statement**: If the potential is perturbed: Φ → Φ + δΦ with ||∇δΦ|| ≤ C, then ISS holds if:

```
γ(t) ≥ (B + C) / ||Ẋ|| + δ
```

**Proof**: Same structure as Theorem 3, with ξ_effective = ξ + ∇δΦ and ||ξ_effective|| ≤ B + C.

This covers the Chainlink oracle attack case: the oracle corruption modifies the potential by δΦ, requiring proportionally more friction.

---

## Stability Regions

### Phase Diagram

The system has three qualitative regimes:

```
γ
↑
│  OVERDAMPED              │
│  (Market seizure)        │
│  γ ≫ γ*                  │
│                          │
│──────── γ* ──────────────│ ← Critical threshold (function of B, ||Ẋ||)
│                          │
│  STABLE                  │
│  (Healthy market)        │   
│  γ* ≤ γ ≤ γ_max         │
│                          │
│──────── γ = 0 ───────────│
│  UNSTABLE                │
│  (Vulnerable to attack)  │
│                          │
└──────────────────── B →
    Adversary budget
```

### Well Depth and Escape Energy

The potential well depth V_depth determines the maximum perturbation the system can absorb without friction:

```
V_depth = Φ(X_rim) − Φ(X_eq)
```

where X_eq is the equilibrium configuration and X_rim is the rim of the potential well.

For the GravityEngine kernel:
- **α** (radial spring) → deeper well, harder to escape
- **σ** (attraction range) → wider well, but shallower per unit distance
- **λ** (repulsion) → prevents collapse but also limits well depth
- **N** (particle count) → more particles = deeper well (more interactions)

This maps economically to:
- **α** = mean-reversion strength (central bank credibility)
- **σ** = market depth (order book thickness)
- **λ** = competition / regulatory barriers
- **N** = number of market participants

---

## Connection to GravityEngine Implementation

The theory maps directly to the existing code:

| Theoretical Concept | Implementation in `udl/gravity.py` |
|--------------------|------------------------------------|
| Equation of motion: MẌ = −∇Φ − γẊ + ξ | `total_force()` → `fit_transform()` Euler integration |
| Potential energy Φ(X) | `compute_system_energy()` |
| Kinetic energy (1/2)ẊᵀMẊ | Displacement history: `displacement_history_` |
| Friction γ(t) | `damping = 0.9` + backtracking line-search |
| Convergence check V̇ ≤ 0 | Energy tracking: `energy_history_`, line-search acceptance |
| Escape detection | `if np.any(np.abs(X_work) > 1e6): break` |
| Well depth | Energy drop: `energy_drop` in `convergence_summary()` |
| Force clamping | `max_force = 100.0` in fit_transform |

### What Needs Modification

To support the full theoretical framework, the GravityEngine needs:

1. **Mass matrix M**: Currently all particles have unit mass. Need `m_i` parameter.
2. **Adversarial perturbation ξ(t)**: Need an `adversary` parameter that injects force at each step.
3. **Adaptive friction γ(t)**: Currently fixed. Need `gamma_fn(X, dX, t)` callback.
4. **Second-order dynamics**: Currently first-order Euler. Need velocity tracking for proper kinetic energy.
5. **ISS monitoring**: Track γ vs γ* at each step to verify stability condition.

---

## Mathematical Notation Summary

| Symbol | Meaning | Units/Domain |
|--------|---------|--------------|
| X(t) | Agent state matrix | ℝ^{N×d} |
| Ẋ(t) | Agent velocity (rate of change) | ℝ^{N×d} |
| M | Mass (capital) matrix | ℝ^{N×N}, diagonal, positive |
| Φ(X) | Interaction potential | ℝ |
| V(X,Ẋ) | Lyapunov function (total energy) | ℝ, V ≥ 0 |
| γ(t) | Adaptive friction | ℝ≥0 |
| γ*(t) | Critical friction threshold | ℝ>0 |
| ξ(t) | Adversarial perturbation | ℝ^{N×d}, ||ξ|| ≤ B |
| B | Adversary budget | ℝ>0 |
| α | Radial spring constant | ℝ>0 |
| σ | Interaction range | ℝ>0 |
| λ | Repulsion coefficient | ℝ>0 |
| η | Step size | ℝ>0 |
| δ | Strict dissipation margin | ℝ>0 |
| V_depth | Potential well depth | ℝ>0 |
| T_escape | Time to escape under zero friction | ℝ>0 |
