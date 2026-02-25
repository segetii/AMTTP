# 07 — Research Plan: Timeline, Papers, and Milestones

## Paper Decomposition

Three papers, each targeting a different audience and venue:

### Paper 1: Pure Theory
**Title**: *"Friction Is Not a Distortion: Necessity of Adaptive Damping in Adversarial Decentralised Economies"*

**Content**:
- Formal definition of Adversarial Decentralised Economy as dissipative particle system
- Theorem: zero-friction equilibria are generically unstable (Lyapunov instability proof)
- Theorem: adaptive friction γ(t) ≥ γ* guarantees ISS
- Derivation of critical friction threshold γ*
- Extension to potential perturbation (oracle attacks) — ISS under model uncertainty
- Economic interpretation: friction as stabilising control, not market distortion

**Target venues** (ranked):
1. Econometrica (top economics — establishes the economic theory)
2. Journal of Economic Theory
3. Management Science
4. Operations Research
5. Games and Economic Behavior

**Length**: ~25 pages + appendix

### Paper 2: RL + Simulation
**Title**: *"Lyapunov-Constrained Adversarial Reinforcement Learning for Optimal Friction Control in Digital Asset Markets"*

**Content**:
- DPD model calibrated to historical crypto collapses
- Simulation reproducing Terra/Luna, Iron Finance, FTX contagion, Chainlink oracle attack
- Demonstration that γ* predicts collapse threshold
- Lyapunov-constrained SAC architecture
- Adversarial RL (RARL) for worst-case robustness
- Results: RL controller prevents all historical collapses in simulation
- Ablation: unconstrained RL vs constrained RL vs PID vs fixed friction

**Target venues** (ranked):
1. NeurIPS (top ML — novel safe RL application domain)
2. ICML
3. AAAI
4. Financial Cryptography and Data Security (FC)
5. IEEE Symposium on Security and Privacy (S&P)

**Length**: ~10 pages (conference format)

### Paper 3: System Paper (AMTTP Elevation)
**Title**: *"AMTTP: Adaptive Friction for Deterministic Compliance Enforcement in Institutional DeFi — Theory, Implementation, Evaluation"*

**Content**:
- Existing AMTTP architecture paper, elevated with:
  - Theoretical foundation (friction = stability mechanism, not just compliance tool)
  - GravityEngine / DPE integration as the stability monitoring component
  - RL friction controller as the adaptive compliance decision engine
  - UDL/BSDT anomaly detection providing risk signal inputs
- End-to-end demonstration: transaction → risk scoring → friction decision → on-chain enforcement

**Target venues** (ranked):
1. ACM CCS (Computer and Communications Security)
2. USENIX Security
3. IEEE S&P
4. Journal of Financial Technology (FinTech)
5. ACM Conference on AI in Finance (ICAIF)

**Length**: ~15 pages

---

## Timeline

### Phase 1: Formalisation (Weeks 1–2)

| Task | Deliverable | Status |
|------|------------|--------|
| Write dynamical system definition | LaTeX section | Not started |
| Specify Lyapunov candidate V = Φ + ½ẊᵀMẊ | LaTeX section | Drafted (05_THEORETICAL_FRAMEWORK.md) |
| Prove V̇ ≤ −γ||Ẋ||² (Theorem 1) | Formal proof | Sketch complete |
| Verify V̇ formula against GravityEngine code | Cross-check | Not started |
| Identify gaps between code dynamics and theory | Gap analysis | Not started |

### Phase 2: Instability Proof (Weeks 2–3)

| Task | Deliverable | Status |
|------|------------|--------|
| Prove Theorem 2 (zero-friction instability) | Formal proof | Sketch complete |
| Prove Theorem 3 (ISS under adaptive friction) | Formal proof | Sketch complete |
| Prove Theorem 4 (robustness to potential perturbation) | Formal proof | Sketch complete |
| Computational validation: run GravityEngine with γ=0, show divergence | Python experiment | Not started |
| Computational validation: run with γ ≥ γ*, show convergence | Python experiment | Not started |
| Write critical friction threshold analysis | LaTeX section | Not started |

### Phase 3: Historical Simulation (Weeks 3–5)

| Task | Deliverable | Status |
|------|------------|--------|
| Acquire Terra/Luna chain data (Flipside Crypto) | Parquet file | Not started |
| Acquire Iron Finance data (Polygon / DeFi Llama) | Parquet file | Not started |
| Acquire FTX/FTT token flow data (Etherscan + CoinGecko) | Parquet file | Not started |
| Acquire Chainlink oracle logs | Parquet file | Not started |
| Calibrate DPD parameters to Terra collapse dynamics | Calibration script | Not started |
| Reproduce Terra collapse in DPD model | Simulation + figures | Not started |
| Reproduce remaining 5 cases | Simulations | Not started |
| Predict γ* for each case; show it matches collapse point | Analysis | Not started |

### Phase 4: RL Controller (Weeks 5–8)

| Task | Deliverable | Status |
|------|------------|--------|
| Build Gymnasium environment wrapping GravityEngine | `envs/dpd_economy.py` | Not started |
| Implement SAC baseline (Stable-Baselines3) | Training script | Not started |
| Add Lyapunov safety projection layer | `safety/lyapunov_constraint.py` | Not started |
| Implement adversary agent (RARL) | `agents/adversary.py` | Not started |
| Train on synthetic environments (Stage 1) | Trained models | Not started |
| Train on historical replays (Stage 2) | Trained models | Not started |
| Ablation study: constrained vs unconstrained vs PID | Results table | Not started |
| Record training curves, stability metrics | Wandb dashboard | Not started |

### Phase 5: Paper 1 Draft (Weeks 8–9)

| Task | Deliverable | Status |
|------|------------|--------|
| Write introduction (economic motivation) | LaTeX section | Not started |
| Write model section (formal definitions) | LaTeX section | From Phase 1 |
| Write main results (Theorems 1–4) | LaTeX section | From Phase 2 |
| Write discussion (economic interpretation) | LaTeX section | Not started |
| Compile computational evidence (figures, tables) | LaTeX figures | From Phase 2–3 |
| Internal review and revision | Clean draft | Not started |

### Phase 6: Paper 2 Draft (Weeks 10–11)

| Task | Deliverable | Status |
|------|------------|--------|
| Write introduction (collapse prevention motivation) | LaTeX section | Not started |
| Write DPD model + calibration section | LaTeX section | From Phase 3 |
| Write RL architecture section | LaTeX section | From Phase 4 |
| Write experimental results | LaTeX section | From Phase 4 |
| Compile figures (collapse reproductions, training curves) | LaTeX figures | From Phase 3–4 |
| Internal review and revision | Clean draft | Not started |

### Phase 7: AMTTP Paper Elevation (Week 12)

| Task | Deliverable | Status |
|------|------------|--------|
| Add theoretical foundation section to existing AMTTP paper | LaTeX section | Not started |
| Connect GravityEngine to compliance matrix formally | Architecture update | Not started |
| Add RL controller as AMTTP Layer II module | System description | Not started |
| Update evaluation with stability metrics | Results tables | Not started |

---

## GravityEngine Code Modifications Required

### Priority 1 (Needed for Phase 2)

```python
# Add to GravityEngine.__init__:
self.masses = None           # (N,) mass vector (default: all ones)
self.adversary_fn = None     # callable(X, dX, t) → ξ ∈ ℝ^{N×d}
self.gamma_fn = None         # callable(X, dX, t) → γ ∈ ℝ≥0

# Add to fit_transform() loop:
if self.adversary_fn is not None:
    xi = self.adversary_fn(X_work, F, t)
    F += xi

if self.gamma_fn is not None:
    gamma_t = self.gamma_fn(X_work, F, t)
    F *= (1.0 / (1.0 + gamma_t))  # or damping = gamma_t
```

### Priority 2 (Needed for Phase 4)

```python
# Gymnasium environment wrapper
class DPDEconomyEnv(gymnasium.Env):
    def __init__(self, N=500, d=10, B_max=1.0):
        self.gravity = GravityEngine(...)
        self.action_space = spaces.Box(0, 5.0, shape=(1,))  # γ
        self.observation_space = spaces.Box(-inf, inf, shape=(k,))
    
    def step(self, action):
        gamma = action[0]
        self.gravity.gamma_fn = lambda X, dX, t: gamma
        # Run one step of dynamics
        # Return (obs, reward, done, truncated, info)
    
    def reset(self):
        # Initialise new random economy
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Lyapunov proof has a gap | Medium | High | Extensive computational validation first; if gap found, weaken theorem to local stability |
| Historical data insufficient for calibration | Medium | Medium | Supplement with synthetic data; qualitative matching is sufficient for first paper |
| RL doesn't converge on real data | Medium | Medium | Start with synthetic; demonstrate on simpler environments first |
| Reviewer rejects "gravity" framing | High | Low | Already planned: use "DPD" terminology, footnote explains naming |
| Someone publishes similar work first | Low | High | Focus on speed for Paper 1 (theory); the working code + AMTTP integration is hard to replicate |
| Tier 1 (Nobel direction) takes >5 years | Certain | None | Expected. Tier 2 papers provide near-term output. |

---

## Dependencies / Prerequisites

### Software
- Python 3.11+ (existing)
- GravityEngine (`udl/gravity.py`) — committed
- Stable-Baselines3 (pip install)
- Gymnasium (pip install)
- Weights & Biases (pip install wandb)
- LaTeX (Overleaf or local TeX Live)

### Data Access
- Flipside Crypto account (free)
- CoinGecko API key (free tier)
- Google Cloud BigQuery (free tier / academic credits)
- Etherscan API key (free tier)

### Compute
- CPU: sufficient for GravityEngine dynamics (already verified)
- GPU: Google Colab A100 for RL training (existing setup)
- Storage: <10 GB total for all datasets

---

## Success Criteria

### Minimum Viable (Phase 1–3 complete)
- [ ] Formal proof of zero-friction instability
- [ ] Formal proof of adaptive friction stability
- [ ] At least 2/6 historical collapses reproduced in simulation
- [ ] Paper 1 draft submitted to a top-3 venue

### Full Success (All phases complete)
- [ ] All three papers submitted
- [ ] RL controller prevents all 6 historical collapses
- [ ] AMTTP integration demonstrated on live transactions
- [ ] γ* prediction validated against real peg deviation data

### Stretch (Tier 1 direction)
- [ ] Generalisation beyond crypto to TradFi (bank runs, currency attacks)
- [ ] Central bank or regulator engagement
- [ ] Policy paper on friction design for CBDCs
