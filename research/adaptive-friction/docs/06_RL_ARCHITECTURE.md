# 06 — Reinforcement Learning Architecture

## Why RL Is Needed

The Lyapunov proof (Theorems 1–4) establishes:
- **Existence**: a stabilising friction γ(t) ≥ γ* exists
- **Lower bound**: γ* = B/||Ẋ|| + δ guarantees ISS

But in practice:
- **B is unknown** (you don't know the adversary's budget)
- **||Ẋ|| is noisy** (real-time velocity estimation from market data has observation noise)
- **Φ is partially unknown** (hidden credit linkages — the FTX/3AC lesson)
- **The objective is multi-dimensional**: minimise fraud loss + minimise user friction + maintain stability

RL solves the **online adaptive optimisation** problem: learn the best γ(t) from experience while never violating the stability constraint.

---

## The Friction Control Problem as an MDP

### State Space s_t ∈ ℝ^k

```
s_t = [
    Δp(t),           # price deviation from peg / target (scalar)
    V_trade(t),       # trading volume (proxy for ||Ẋ||)
    W_rate(t),        # withdrawal / redemption rate
    TVL(t),           # total value locked (proxy for well depth)
    HHI(t),           # Herfindahl index of capital concentration
    σ_vol(t),         # realised volatility (recent)
    Δp_oracle(t),     # oracle price vs market price deviation
    G_metrics(t),     # graph topology metrics (degree, clustering coeff)
    n_alerts(t),      # AMTTP alert count (from ML risk engine)
    V̇_est(t),        # estimated Lyapunov derivative (from energy tracking)
]
```

Dimensionality: k ≈ 10–20 features.

### Action Space a_t

**Continuous**: γ(t) ∈ [γ_min, γ_max]

This maps to the AMTTP compliance matrix:

| γ Range | AMTTP Action | Economic Effect |
|---------|-------------|-----------------|
| γ ∈ [0, 0.2) | APPROVE (fast-track) | Near-zero friction, maximum throughput |
| γ ∈ [0.2, 0.5) | APPROVE (standard) | Normal friction, standard checks |
| γ ∈ [0.5, 0.8) | REVIEW | Elevated friction, human review queue |
| γ ∈ [0.8, 1.2) | ESCROW | High friction, funds held pending review |
| γ ∈ [1.2, ∞) | BLOCK | Maximum friction, transaction rejected |

The continuous γ can also be discretised to 5 levels for discrete RL (DQN) as a baseline comparison.

### Reward Function r_t

```
r_t = −w₁ · FraudLoss(t)           # penalise undetected fraud
      − w₂ · UserFriction(t)        # penalise legitimate user delays
      − w₃ · ||V̇_positive(t)||     # penalise energy increase (instability)
      + w₄ · Throughput(t)           # reward transaction throughput
```

where:
- **FraudLoss** = total value of transactions that were approved but later identified as fraudulent
- **UserFriction** = average delay imposed on legitimate transactions (sum of review/escrow times)
- **V̇_positive** = max(V̇, 0) — only penalise when energy is increasing (system destabilising)
- **Throughput** = number of transactions processed per unit time

Weight defaults: w₁ = 10.0, w₂ = 1.0, w₃ = 5.0, w₄ = 0.5

---

## RL Architecture

### Policy Algorithm: Soft Actor-Critic (SAC)

**Why SAC**:
- Continuous action space (γ is real-valued)
- Maximum entropy framework → natural exploration
- Sample-efficient (important: historical collapse data is limited)
- Off-policy (can learn from replay buffer of historical data)

**Architecture**:
```
State s_t (k dims)
    │
    ├──→ Actor Network π(a|s) ──→ γ(t) ∈ [γ_min, γ_max]
    │     (2 hidden layers, 256 units, ReLU)
    │     (output: tanh scaled to action range)
    │
    └──→ Twin Q-Networks Q₁(s,a), Q₂(s,a)
          (2 hidden layers, 256 units, ReLU)
          (output: scalar expected return)
```

### Safety Layer: Lyapunov Constraint

**Key innovation**: The RL policy is **constrained** to only output actions satisfying V̇ ≤ 0.

This uses the **Lyapunov-based safe RL** framework (Chow et al. 2018, Berkenkamp et al. 2017):

```
π_safe(s_t) = project(π_unconstrained(s_t), C_safe(s_t))
```

where:

```
C_safe(s_t) = {γ : V̇(s_t, γ) ≤ 0}
            = {γ : γ ≥ B_est / ||Ẋ_est||}
```

**Implementation**: After the actor network outputs γ_proposed, apply:

```python
def safety_projection(gamma_proposed, state):
    """Project proposed friction onto safe set."""
    V_dot_est = state['V_dot_estimate']
    X_dot_norm = state['velocity_norm']
    B_est = state['adversary_budget_estimate']
    
    # Minimum safe friction
    gamma_min_safe = B_est / (X_dot_norm + eps) + delta
    
    # Project: take the maximum of proposed and minimum safe
    gamma_safe = max(gamma_proposed, gamma_min_safe)
    
    return gamma_safe
```

The actor learns that the safety projection clips bad actions → it naturally learns to propose safe γ values → the projection fires less over time.

### Adversary: Robust Adversarial RL (RARL)

A second RL agent learns the **worst-case attack strategy** ξ(t):

```
State s_t (same as controller)
    │
    └──→ Adversary Network ξ(s) ──→ ξ(t), ||ξ|| ≤ B
          (2 hidden layers, 256 units)
          (reward: −r_t, i.e., maximise damage)
```

**Training loop**:
```
For each episode:
    1. Controller π selects γ(t) to minimise fraud + friction
    2. Adversary ν selects ξ(t) to maximise fraud + instability
    3. System evolves: MẌ = −∇Φ − γẊ + ξ
    4. Both agents update from experience
```

This finds the **Nash equilibrium** of the friction game:

```
(π*, ν*) = arg min_π max_ν E[Σ_t r_t | π, ν]
```

If the controller can stabilise under the worst-case adversary, it can stabilise under any real adversary.

---

## Training Curriculum

### Stage 1: Synthetic Environments (Episodes 1–10K)

```python
envs = [
    SyntheticEconomy(N=200, B=0.5, phi_depth=10),   # easy
    SyntheticEconomy(N=500, B=1.0, phi_depth=5),     # medium
    SyntheticEconomy(N=500, B=2.0, phi_depth=3),     # hard
    SyntheticEconomy(N=1000, B=5.0, phi_depth=2),    # extreme
]
```

### Stage 2: Historical Collapse Replay (Episodes 10K–20K)

Replay the six historical case studies as RL environments:

```python
envs = [
    TerraLunaReplay(data='terra_luna_may2022.parquet'),
    IronFinanceReplay(data='iron_titan_jun2021.parquet'),
    ChainlinkOracleReplay(data='chainlink_sep2020.parquet'),
    FTXContagionReplay(data='ftx_nov2022.parquet'),
    ThreeACReplay(data='3ac_celsius_jun2022.parquet'),
    CurveExploitReplay(data='curve_jul2023.parquet'),
]
```

Each environment calibrates the DPD parameters to match observed dynamics, then asks the RL controller to find friction that would have prevented the collapse.

### Stage 3: Live Data (Episodes 20K+)

Connect to Ethereum mempool / AMTTP transaction stream. Real-time friction control.

---

## Evaluation Metrics

### Stability Metrics

| Metric | Definition | Target |
|--------|-----------|--------|
| **Escape rate** | Fraction of episodes where ||X|| → ∞ | 0% under controller |
| **V̇ violation rate** | Fraction of timesteps where V̇ > 0 | 0% (safety constraint) |
| **Mean γ** | Average friction applied | As low as possible (efficiency) |
| **Max γ** | Peak friction (worst-case stress) | < γ_max (not market seizure) |
| **Recovery time** | Steps to return within r_stable after perturbation | < 50 steps |

### Economic Metrics

| Metric | Definition | Target |
|--------|-----------|--------|
| **Fraud loss** | Total undetected fraud value | Minimise |
| **User friction cost** | Average legitimate transaction delay | < 10 seconds |
| **Throughput** | Transactions per second during normal operation | > 100 TPS |
| **False block rate** | Legitimate transactions incorrectly blocked | < 1% |
| **Peg deviation** (stablecoins) | Max |price − 1.0| during attack | < 2% |

### Adversarial Metrics

| Metric | Definition | Target |
|--------|-----------|--------|
| **Adversary success rate** | Fraction of attacks that cause divergence | 0% under controller |
| **Nash gap** | ||π − BR(ν)|| + ||ν − BR(π)|| | < ε (convergence to equilibrium) |
| **Worst-case regret** | max_ν [V(π*) − V(π)] | Bounded by theory |

---

## Implementation Stack

```
Framework:    Stable-Baselines3 (SAC) + custom safety layer
Environment:  Gymnasium-compatible wrapper around GravityEngine
Compute:      CPU for GravityEngine dynamics, GPU for RL networks
Logging:      Weights & Biases (wandb) for experiment tracking
Hyperparams:  Optuna for automated tuning
Baselines:    
  - Fixed γ (static friction — current AMTTP)
  - PID controller (classical control baseline)
  - Threshold rule (γ = f(V̇_sign))
  - Unconstrained SAC (no Lyapunov safety)
  - Constrained SAC (with Lyapunov — our method)
```

---

## Connection to AMTTP Decision Matrix

The RL controller's output γ(t) maps directly to AMTTP's existing infrastructure:

```
AMTTP Compliance Orchestrator
    │
    ├── ML Risk Engine → risk_score
    ├── Graph API → graph_metrics
    ├── Sanctions Service → sanctions_flag
    ├── Geo-risk Service → geo_risk
    │
    └── RL Friction Controller (NEW)
         │
         Input:  state = (risk_score, graph_metrics, V̇, ||Ẋ||, ...)
         Output: γ(t) → maps to APPROVE/REVIEW/ESCROW/BLOCK
         Safety: Lyapunov constraint ensures V̇ ≤ 0
```

This integrates as a new module in AMTTP Layer II without modifying the existing architecture.

---

## Key References

1. Chow, Y. et al. (2018). "A Lyapunov-based Approach to Safe Reinforcement Learning." NeurIPS.
2. Berkenkamp, F. et al. (2017). "Safe Model-based Reinforcement Learning with Stability Guarantees." NeurIPS.
3. Pinto, L. et al. (2017). "Robust Adversarial Reinforcement Learning." ICML.
4. Haarnoja, T. et al. (2018). "Soft Actor-Critic: Off-Policy Maximum Entropy Deep RL." ICML.
5. Achiam, J. et al. (2017). "Constrained Policy Optimization." ICML.
