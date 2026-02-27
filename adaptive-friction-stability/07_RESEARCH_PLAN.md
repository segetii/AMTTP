# 07 — Research Plan: Timeline, Papers, and Milestones

## North Star (Personal Ambition)

This is a long-horizon programme aimed at a **foundational** contribution: a general theory of stability and crisis prevention in programmable financial systems (DeFi first, then broader digital and traditional markets).

“Nobel laureate level” here is not a claim about prizes; it is a commitment to the *type* of output that has lasting impact:

- **General**: not tied to one protocol, chain, or crisis.
- **Mechanistic**: explains collapse dynamics (feedback loops, reflexivity, delay, leverage), not only detection.
- **Predictive**: makes falsifiable, out-of-sample predictions on real crisis timelines.
- **Actionable**: yields implementable control primitives (adaptive friction) with governance hooks.
- **Transferable**: bridges DeFi to systemic-risk phenomena in broader finance as a limit case.

---

## Core Thesis

**Programmable Market Stability via Adaptive Friction.**

Programmable markets can be modeled as controlled dynamical systems with endogenous feedback loops. In this framing, “friction” is an explicit **control input** (not merely a fee) that modifies state transitions: throttling, delay/queuing, dynamic haircuts/margins, circuit breakers/cooldowns, and oracle-confidence gating.

The programme targets four deliverables:

1. **Characterise fragility** (when and why low-/zero-friction regimes become unstable).
2. **Derive stability thresholds** (critical friction levels and robust stability margins).
3. **Construct certified controllers** (policies that enforce stability under uncertainty/adversaries).
4. **Validate on crisis replays** (Terra/Luna as flagship, plus a portfolio of collapse modes).

---

## Flagship Use Case: Terra/Luna Collapse

Terra/Luna is used as the decisive stress event because it combines: reflexive feedback (mint/burn), liquidity spirals, discrete events (liquidations/oracle updates), and correlated/adversarial behavior.

The goal is not “reproduce history.” The goal is:

- **Pre-crash calibration** → **crash-window prediction**;
- counterfactual evaluation: “if adaptive friction had been applied at time $t_0$, what stability envelope changes?”

The keystone output is a falsifiable prediction of a stability threshold (e.g., $\gamma^*(t)$) and its relationship to observed collapse dynamics.

## Paper Decomposition

Three papers, each targeting a different audience and venue:

### Paper 1: Pure Theory
**Working title**: *"Programmable Market Stability: Adaptive Friction as a Robust Control Primitive"*

**Content**:
- Canonical model class: controlled dynamical system (control-affine or stochastic hybrid system) with endogenous feedback
- Fragility / impossibility result: static or insufficient friction fails for a defined shock/adversary class
- Robust stabilisability: ISS / small-gain / passivity-style conditions for stability under bounded disturbances
- Critical threshold analysis: derive $\gamma^*$ as a *necessary and sufficient* bound under explicit assumptions (or clearly label what is only sufficient)
- Robustness to model perturbations (oracle attacks / parameter drift) stated as explicit uncertainty sets
- Interpretation for policy/governance: friction as stability control, not “market distortion” rhetoric

**Target venues** (ranked):
1. Automatica / IEEE Transactions on Automatic Control (if control-theoretic contribution is primary)
2. Management Science / Operations Research (if the model is tied tightly to market design and measurable outcomes)
3. Journal of Economic Theory / Games and Economic Behavior (if the economic primitives are the centre)

**Length**: ~25 pages + appendix

### Paper 2: RL + Simulation
**Working title**: *"Certified Friction Policies for Adversarial DeFi: Safe Control with Stability Certificates"*

**Content**:
- Crisis replay simulator calibrated to historical collapse traces (Terra/Luna as flagship)
- Evaluation is framed as **out-of-sample** prediction and counterfactual stabilisation within a declared shock class
- Controller families:
    - robust MPC / robust control baselines;
    - shielded RL or policy + safety filter (certificate-first, learning-second);
    - adversarial evaluation (RARL-style) explicitly bounded
- Stability metrics and failure envelopes (not “always prevents collapse”): quantify safe region, breakdown modes, and robustness sweeps
- Ablations: certificate vs no-certificate; static vs adaptive friction; oracle-attack vs non-adversarial

**Target venues** (ranked):
1. NeurIPS / ICML (if the certified-control method is the main novelty)
2. Financial Cryptography and Data Security (FC) / ICAIF (if the domain + evaluation is the novelty)
3. AAAI (if positioned as safe decision-making under adversarial market dynamics)

**Length**: ~10 pages (conference format)

### Paper 3: System Paper (AMTTP Elevation)
**Working title**: *"AMTTP as a Stability Layer: Programmable Compliance and Adaptive Friction for Market Integrity"*

**Content**:
- Existing AMTTP architecture paper, elevated with:
    - Theoretical foundation (friction = stability control primitive)
    - GravityEngine / DPE as stability monitoring + scenario simulator
    - Certified controller as adaptive friction decision engine (with governance constraints)
    - UDL/BSDT as risk signal inputs (separate from stability control layer)
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

### Phase 0: Scientific Guardrails (Week 0)

| Task | Deliverable | Status |
|------|------------|--------|
| Define anomaly/stability claims as conditional statements | Claim inventory | Not started |
| Define strict evaluation discipline (fit/freeze rules) | Protocol checklist | Not started |
| Define robustness sweep suite (noise, scaling drift, rotations, subsampling) | Robustness plan | Not started |

### Phase 1: Formalisation (Weeks 1–2)

| Task | Deliverable | Status |
|------|------------|--------|
| Write canonical dynamical system definition (control-affine or hybrid) | LaTeX section | Not started |
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
| Predict γ* for each case; evaluate on held-out crash window | Analysis | Not started |
| Counterfactual: apply friction at time t0; quantify stability envelope change | Counterfactual report | Not started |

### Phase 4: RL Controller (Weeks 5–8)

| Task | Deliverable | Status |
|------|------------|--------|
| Build Gymnasium environment wrapping GravityEngine | `envs/dpd_economy.py` | Not started |
| Implement robust MPC baseline | Baseline controller | Not started |
| Implement SAC baseline (Stable-Baselines3) | Training script | Not started |
| Add safety filter / certificate layer (shield) | `safety/` module | Not started |
| Implement adversary agent (RARL) | `agents/adversary.py` | Not started |
| Train on synthetic environments (Stage 1) | Trained models | Not started |
| Train on historical replays (Stage 2) | Trained models | Not started |
| Ablation study: certificate vs no-certificate vs PID vs static friction | Results table | Not started |
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
    # NOTE: friction should damp velocity / displacement updates, not rescale the force directly.
    # The code-level choice must match the theoretical model you prove.
    # Recommended: apply damping to the update term (e.g., dX or velocity state).
    dX *= (1.0 / (1.0 + gamma_t))
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
| Overclaim ("universal", "prevents all collapses") | Medium | High | Use conditional theorems + robustness envelopes; publish explicit failure cases |
| Historical data insufficient for calibration | Medium | Medium | Supplement with synthetic data; qualitative matching is sufficient for first paper |
| RL doesn't converge on real data | Medium | Medium | Start with synthetic; demonstrate on simpler environments first |
| Reviewer rejects "gravity" framing | High | Low | Already planned: use "DPD" terminology, footnote explains naming |
| Someone publishes similar work first | Low | High | Focus on speed for Paper 1 (theory); the working code + AMTTP integration is hard to replicate |
| Foundational track takes >5 years | Certain | None | Expected; publish intermediate results as coherent steps toward the thesis |

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
- [ ] Terra/Luna: pre-crash calibration → crash-window prediction report
- [ ] Paper 1 draft ready for submission (venue depends on emphasis)

### Full Success (All phases complete)
- [ ] All three papers submitted
- [ ] Certified controller demonstrates bounded-loss / bounded-deviation under declared shock classes
- [ ] AMTTP integration demonstrated on live transactions
- [ ] γ* prediction validated against real peg deviation data

### Stretch (Tier 1 direction)
- [ ] Generalisation beyond crypto to TradFi (bank runs, currency attacks)
- [ ] Central bank or regulator engagement
- [ ] Policy paper on friction design for CBDCs

---

## Guardrails (Scientific Credibility)

- Separate (i) proved statements (conditional theorems), (ii) empirical findings, (iii) engineering claims.
- Prefer “certified under stated assumptions” over “guaranteed in general.”
- Always include robustness sweeps (noise, scaling drift, subsampling; and only claim invariances you test).
- Avoid leakage: any parameter/threshold/controller selection is tuned on train/val only and reported on held-out test windows.
