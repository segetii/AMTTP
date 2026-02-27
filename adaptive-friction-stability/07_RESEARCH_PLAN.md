# 07 — Research Plan: Timeline, Papers, and Milestones

## North Star (Personal Ambition)

This is a long-horizon programme aimed at a **foundational** contribution: a general mathematical theory of stability and adaptive stabilisation in networked financial systems — applicable to macroeconomic dynamics, banking contagion, asset markets, and monetary policy, and compelling to economists, central banks, and financial regulators.

"Nobel laureate level" here is not a claim about prizes; it is a commitment to the *type* of output that has lasting impact:

- **General**: not tied to one protocol or sector — applies wherever high-dimensional feedback dynamics arise.
- **Mechanistic**: explains cascade dynamics (self-reinforcing deviations, reflexivity, contagion), not only detection.
- **Predictive**: makes falsifiable, out-of-sample predictions on real instability windows.
- **Actionable**: yields implementable stabilisation primitives (adaptive friction, circuit breakers, dynamic buffers) with direct policy interpretation.
- **Credible audience**: economists, central banks (Fed, ECB, BIS, Bank of England), financial regulators (FSB, IMF), and systemic-risk researchers — not primarily DeFi practitioners.

---

## Is AMTTP Integration Required?

**No.** AMTTP is a separate engineering/compliance product and is not a prerequisite for the scientific research programme. The core outputs — a mathematical theory of energy-based adaptive stabilisation, empirical validation on macro-financial data, and policy-facing results — stand entirely independently.

AMTTP is an *optional parallel track*: if later you want to demonstrate an on-chain enforcement layer, it can be positioned as a one-paragraph application example in Paper 3. But dropping or delaying AMTTP has zero effect on Papers 1 or 2, and those are the papers that matter to the target audience.

---

## Core Thesis

**Adaptive Stabilisation of Networked Financial Systems via Data-Induced Damping.**

Networked financial systems — interbank exposure networks, macro-variable feedback loops, asset correlation structures — can be modelled as controlled dynamical systems in which endogenous feedback may amplify perturbations. Rather than imposing exogenous control parameters or training a regulator, we construct a scalar instability functional directly from observable system trajectories and show that gradient-proportional adaptive damping provably suppresses amplification.

The programme targets four deliverables:

1. **Characterise fragility** (when and why low-/zero-damping regimes become unstable — stated as theorems with explicit conditions).
2. **Derive stability thresholds** (minimal damping magnitudes and their dependence on network topology and volatility).
3. **Identify early-warning signals** (when does $E(X(t))$ rise detectably before observed instability?).
4. **Validate on real macro-financial data** (2022 rate-shock / liquidity cascade as flagship; 2008 credit cascade as robustness case).

---

## Flagship Use Case: 2022 Global Rate-Shock / Liquidity Cascade

The May–June 2022 global event combines: reflexive feedback (rate expectations → credit spreads → collateral values), liquidity spirals (fund redemptions → forced selling → spread widening), discrete shocks (Fed rate decisions, CPI prints), and cross-market contagion (equities, credit, EM currencies, and commodity markets moving together).

This event is ideal as a flagship because:
- All data is publicly available (FRED, BIS, Bloomberg / WRDS proxies).
- It is macro-financial, not crypto-specific — directly relevant to central banks and regulators.
- It has clear instability onset, peak, and recovery phases suitable for out-of-sample evaluation.

The goal is not "reproduce history." The goal is:

- **Pre-onset calibration** → **instability-window prediction** using only pre-event data;
- counterfactual: "if adaptive damping $\gamma^*(t)$ had been applied at time $t_0$, what does the energy trajectory $E(X(t))$ show?"

The keystone output is a falsifiable prediction of instability onset and a stability envelope estimate — both evaluated on held-out data windows.

**Secondary use case**: 2008 credit cascade (GFC). Used as a robustness / out-of-sample check after calibration on 2022 data. Different shock type (credit vs. rate); tests generality of the energy functional.

**Removed**: crypto / DeFi events are no longer used as primary evidence. If mentioned, they appear only as a brief appendix example, framed neutrally.

---

## New Paper Blueprint (Stabilisation Framework)

This paper is **not** UDL Part II. It is a new mathematical paper in nonlinear dynamical systems / optimization / control. It may reuse structural ideas (data-induced energy, sensitivity), but it does not depend on anomaly-detection framing.

### Working title

*"Energy-Dependent Damping in High-Dimensional Feedback Systems: A Data-Induced Variational Stabilisation Framework"*

Short version: *"Energy-Based Adaptive Damping for High-Dimensional Networked Systems"*

**Positioning guardrails**:

- No anomaly detection language.
- No AUC / classification metrics.
- No econophysics framing.
- No “gravity” branding in the title (Terra/Luna is a use case, not the title).

### Abstract (journal-ready, 150–180 words)

We study adaptive stabilisation in high-dimensional feedback systems whose endogenous dynamics may amplify perturbations. Rather than introducing exogenous control coefficients or trained regulators, we construct a scalar instability functional directly from observed system trajectories and define an energy-dependent damping mechanism proportional to its gradient. The resulting controlled dynamics take the form

$$\dot{X} = F(X) - \gamma(E(X)) \nabla E(X),$$

where $E$ is a data-induced functional and $\gamma$ is a non-negative activation rule increasing with instability energy. We prove sufficient conditions under which the damping term guarantees monotone decrease of instability energy, bounded amplification of deviations, and preservation of equilibrium states. For discrete implementations, we establish conditional monotone descent under backtracking line search. Synthetic cascade systems and macroeconomic network data illustrate that adaptive damping suppresses self-reinforcing deviations while leaving low-energy regimes unaffected. The framework is parameter-light, fully auditable, and grounded entirely in variational analysis and nonlinear dynamical systems.

### Mathematical framework (formal model + assumptions)

#### State space and dynamics

Let $X(t) \in \mathbb{R}^d$ represent system state (e.g., exposures, prices, liquidity measures).

Uncontrolled dynamics:

$$\dot{X} = F(X).$$

Assume:

- (A1) Local Lipschitz continuity: $F \in C^1(\mathbb{R}^d)$.
- (A2) Possible amplification: the Jacobian $DF(X)$ may have eigenvalues with positive real part in some region.

#### Data-induced energy functional

Construct $E : \mathbb{R}^d \to \mathbb{R}$ from empirical deviation geometry.

General form:

$$E(X) = \underbrace{\sum_i \psi(\delta_i(X))}_{\text{local deviation}} + \underbrace{\sum_{i<j} \phi(\|X_i - X_j\|)}_{\text{interaction structure}},$$

Assume:

- (E1) $E \in C^1$.
- (E2) $E$ bounded below.
- (E3) $\nabla E$ locally Lipschitz.

#### Adaptive damping law

Controlled dynamics:

$$\dot{X} = F(X) - \gamma(E(X))\nabla E(X),$$

where $\gamma : \mathbb{R}_{\ge 0} \to \mathbb{R}_{\ge 0}$ satisfies:

- $\gamma(0)=0$,
- $\gamma$ increasing,
- bounded on compact sets.

Example (parameter-light):

$$\gamma(E) = \frac{E}{E + \theta},$$

where $\theta$ is derived from empirical dispersion (no trainable parameters).

### Core theorems (paper spine)

- **Theorem 1 — Energy dissipation condition.** If $\nabla E(X)\cdot F(X) \le C\|\nabla E(X)\|^2$ and $\gamma(E(X)) > C$, then $\frac{d}{dt}E(X(t)) \le 0$.
- **Theorem 2 — Bounded amplification.** If $\|F(X)\| \le L\|X\|$ and $\gamma(E) \ge \gamma_{\min} > L$, then $\|X(t)\| \le e^{-(\gamma_{\min}-L)t}\|X(0)\|$.
- **Theorem 3 — Equilibrium preservation.** If $F(X^\star)=0$ and $\nabla E(X^\star)=0$, then $X^\star$ remains equilibrium under damping.
- **Theorem 4 — Discrete descent.** For Armijo backtracking in $X^{t+1} = X^t - \eta_t\,\gamma(E^t)\nabla E^t$, we obtain $E^{t+1} \le E^t$ under standard descent conditions.

### Synthetic cascade model (minimal but publishable)

Use:

$$\dot{X} = AX + \alpha\,\sigma(X),$$

where $A$ has at least one eigenvalue with positive real part and $\sigma$ is a reinforcement nonlinearity (cubic or sigmoidal). 1D illustrative case:

$$\dot{x} = \lambda x + \alpha x^3.$$

Demonstrate:

- energy growth uncontrolled,
- energy decay with adaptive damping,
- state norm bounded,
- plots: $\|X(t)\|$, $E(t)$, phase portrait.

### Empirical data sources (macro-financial; no crypto)

- **FRED** macro time series: credit spreads (ICE BofA OAS), M2, GDP growth, yield curve slope (10Y–2Y), VIX, and NFCI.
- **BIS** cross-border banking exposure data (quarterly; publicly available on BIS website).
- **Rolling equity correlation networks**: time-varying correlation matrices from daily S&P 500 returns (CRSP or Yahoo Finance).
- **WRDS / Bloomberg proxy**: investment-grade and high-yield spread indices, 2005–2024 (or FRED equivalents where available).
- **IMF Financial Soundness Indicators**: capital adequacy, asset quality, liquidity ratios across banking sectors.
- Instability windows used: May–June 2022 (primary), Sep–Dec 2008 (robustness check).

### Experimental protocol (no classification metrics)

For each dataset:

- compute state vector $X(t)$,
- construct $E(X)$,
- simulate / compare: no damping vs constant damping vs adaptive damping,
- measure: max amplitude, energy trajectory, time to stabilisation.

### Structure summary (18–22 pages)

- Introduction
- Mathematical setting
- Adaptive damping theory
- Construction of energy functional
- Discrete implementation
- Synthetic cascade experiments
- Empirical network applications
- Discussion & limitations
- Appendix (proofs)

### Submission strategy

Targets:

- SIAM Journal on Control and Optimization
- Discrete & Continuous Dynamical Systems – B
- IEEE Transactions on Automatic Control
- Journal of Optimization Theory and Applications

Preprint:

- arXiv: math.DS, math.OC

---

## Final Architectural Decision (must be explicit)

Before drafting the full paper, decide this precisely:

**Is instability energy defined on individual states $X \in \mathbb{R}^d$ (single-state stabilisation), or on a joint configuration of multiple interacting agents $X \in \mathbb{R}^{N\times d}$ (multi-agent / network stabilisation)?**

This determines whether we formalise the model as single-system stabilisation or multi-agent network stabilisation (and how interaction terms enter $E$ and $F$).

## Paper Decomposition

Three papers, each targeting a different audience and venue:

### Paper 1: Energy-Based Adaptive Damping (Pure Theory)
**Working title**: *"Energy-Dependent Damping in High-Dimensional Feedback Systems"*

**Content**:
- Canonical model class: $\dot{X}=F(X)$ with possible amplification; controlled dynamics $\dot{X}=F(X)-\gamma(E(X))\nabla E(X)$
- Construction of a data-induced energy $E$ (deviation + interaction structure)
- Core theory: energy dissipation, bounded amplification, equilibrium preservation
- Discrete implementation: Armijo backtracking monotone descent
- Synthetic cascade experiments (ODE) + neutral empirical network/time-series illustrations
- Clear limitations: conditions are explicit; no “prevents all collapses” language

**Target venues** (ranked):
1. SIAM Journal on Control and Optimization / IEEE Transactions on Automatic Control
2. Discrete & Continuous Dynamical Systems – B
3. Journal of Optimization Theory and Applications

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
| Define stabilisation claims as conditional statements | Claim inventory | Not started |
| Define strict evaluation discipline (fit/freeze rules) | Protocol checklist | Not started |
| Define robustness sweep suite (noise, scaling drift, rotations, subsampling) | Robustness plan | Not started |

### Phase 1: Formalisation (Weeks 1–2)

| Task | Deliverable | Status |
|------|------------|--------|
| Write canonical dynamical system definition ($\dot{X}=F(X)$) | LaTeX section | Not started |
| Define data-induced energy $E(X)$ and regularity assumptions (E1–E3) | LaTeX section | Not started |
| Prove energy dissipation condition $\frac{d}{dt}E \le 0$ under explicit inequality | Formal proof | Not started |
| Verify $\dot{X}=F(X)-\gamma(E(X))\nabla E(X)$ and $\frac{d}{dt}E$ expression against code-level update rule | Cross-check | Not started |
| Identify gaps between code dynamics and theory | Gap analysis | Not started |

### Phase 2: Instability Proof (Weeks 2–3)

| Task | Deliverable | Status |
|------|------------|--------|
| Prove bounded amplification result (Theorem 2) under explicit growth bounds on $F$ | Formal proof | Not started |
| Prove equilibrium preservation (Theorem 3) | Formal proof | Not started |
| Prove discrete monotone descent with Armijo backtracking (Theorem 4) | Formal proof | Not started |
| Computational validation: synthetic cascade without damping shows amplification/blow-up | Python experiment | Not started |
| Computational validation: adaptive damping suppresses amplification and yields $E(t)$ descent | Python experiment | Not started |
| Write stability threshold discussion ($\gamma^*$ as sufficient condition; label what is not necessary) | LaTeX section | Not started |

### Phase 3: Macro-Financial Data + Empirical Validation (Weeks 3–5)

| Task | Deliverable | Status |
|------|------------|--------|
| Download FRED macro bundle (credit spreads, M2, VIX, yield slope, NFCI) via `fredapi` | Parquet file | Not started |
| Download BIS cross-border banking exposure data (BIS website, quarterly) | Parquet file | Not started |
| Build rolling 60-day equity correlation network from daily S&P 500 returns (Yahoo Finance / CRSP) | Parquet file | Not started |
| Download IMF Financial Soundness Indicators (FSI) dataset | Parquet file | Not started |
| Construct state vector $X(t)$ from each dataset; define deviation terms $\delta_i$ | Data pipeline | Not started |
| Compute $E(X(t))$ over full history; plot energy trajectory with instability event markers | Analysis figure | Not started |
| Identify instability windows (2022 primary, 2008 robustness); split strictly: pre-onset train / post-onset test | Split protocol | Not started |
| Calibrate $\theta$ on train window only; freeze before evaluation | Calibration script | Not started |
| Simulate no-damping, constant damping, adaptive damping on held-out test window | Simulation + figures | Not started |
| Counterfactual: apply $\gamma^*(t)$ from $t_0$ (onset); quantify change in energy peak and recovery time | Counterfactual report | Not started |
| Robustness sweep: vary $\theta$, window length, data frequency; report sensitivity table | Robustness table | Not started |

### Phase 4: Theoretical Completion + Policy Translation (Weeks 5–8)

| Task | Deliverable | Status |
|------|------------|--------|
| Draft full proofs of Theorems 1–4 (energy descent, bounded amplification, equilibrium preservation, discrete descent) | LaTeX appendix | Not started |
| Write related-work section contrasting with CLF, ISS, energy shaping, barrier certificates | LaTeX section | Not started |
| Compute $\gamma^*(t)$ estimates from empirical data; compare to realised instability thresholds | Analysis figure | Not started |
| Build policy interpretation table: theory concept → macro-prudential instrument analogue | Policy table | Not started |
| Draft Paper 1 theory sections (model, theorems, synthetic experiments) | Partial draft | Not started |
| Draft Paper 2 empirical sections (data, energy construction, counterfactual results) | Partial draft | Not started |
| Draft Paper 3 policy sections (instruments, implementability, governance) | Policy draft | Not started |
| Internal review: check all claims are conditional; remove any absolute stability language | Review log | Not started |

### Phase 5: Paper 1 Draft (Weeks 8–9)

| Task | Deliverable | Status |
|------|------------|--------|
| Write introduction (systemic risk / macro-financial motivation + research gap vs. CLF / ISS) | LaTeX section | Not started |
| Write model section (canonical model, energy construction, damping law, assumptions A1–A2, E1–E3) | LaTeX section | From Phase 1 |
| Write main results section (Theorems 1–4 with proofs in appendix) | LaTeX section | From Phase 2 |
| Write synthetic experiments section ($\dot{x}=\lambda x + \alpha x^3$; controlled vs. uncontrolled) | LaTeX section | From Phase 2 |
| Write discussion (stability conditions, limitations, open problems) | LaTeX section | Not started |
| Compile figures ($E(t)$, $\|X(t)\|$, phase portrait, $\gamma^*$ vs. instability) | LaTeX figures | From Phase 2–3 |
| Internal review: verify all claims are conditional, no absolute stability language | Clean draft | Not started |

### Phase 6: Paper 2 + Paper 3 Draft (Weeks 10–12)

| Task | Deliverable | Status |
|------|------------|--------|
| Write Paper 2 introduction (macro-prudential motivation, research gap) | LaTeX section | Not started |
| Write Paper 2 data + energy construction section | LaTeX section | From Phase 3 |
| Write Paper 2 counterfactual experiment results + robustness | LaTeX section | From Phase 3–4 |
| Compile Paper 2 figures (energy trajectory, norm trajectory, robustness table) | LaTeX figures | From Phase 3 |
| Write Paper 3 policy translation section (theory → instruments) | Policy section | From Phase 4 |
| Get informal review from one economist / central bank contact before submission | Feedback | Not started |
| Internal review and revision of all three papers | Clean drafts | Not started |

### Phase 7: Submission + Dissemination (Week 13)

| Task | Deliverable | Status |
|------|------------|--------|
| Post Paper 1 to arXiv (math.DS, math.OC) | arXiv preprint | Not started |
| Submit Paper 1 to SIAM SICON or IEEE TAC | Submission confirmation | Not started |
| Post Paper 2 to SSRN and arXiv (q-fin.RM) | SSRN preprint | Not started |
| Submit Paper 2 to Journal of Financial Stability or Review of Financial Studies | Submission confirmation | Not started |
| Submit Paper 3 to BIS Working Papers or Fed FEDS series | Submission confirmation | Not started |

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

### Priority 2 (Needed for Phase 3 — data pipeline)

```python
# Minimal empirical data pipeline sketch
import fredapi, yfinance, pandas as pd

# FRED macro bundle
fred = fredapi.Fred(api_key="...")
series = {
    "credit_spread": "BAMLH0A0HYM2",  # ICE BofA HY OAS
    "yield_slope":   "T10Y2Y",
    "vix":           "VIXCLS",
    "m2":            "M2SL",
    "nfci":          "NFCI",
}
macro_df = pd.concat({k: fred.get_series(v) for k, v in series.items()}, axis=1)

# Rolling equity correlation network (60-day window)
prices = yfinance.download(sp500_tickers, period="20y", interval="1d")["Adj Close"]
returns = prices.pct_change().dropna()
corr_t = returns.rolling(60).corr()  # MultiIndex: (date, ticker) x ticker

# State vector X(t): standardise, impute, drop obs with >20% missing
from sklearn.preprocessing import StandardScaler
X = StandardScaler().fit_transform(macro_df.ffill().dropna())
```

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Theory-to-code mismatch: GravityEngine uses multiplicative damping, paper proves gradient form | High | High | **P0**: resolve before writing proofs — either change code to $-\gamma\nabla E$ or prove theorems for the implemented form |
| Theorem 2 gap: bounded $\gamma(E)=E/(E+\theta)<1$ may not satisfy $\gamma_{\min}>L$ | High | High | **P0**: patch theorem statement with explicit condition on $L$ vs. $\gamma$ range; or change example $\gamma$ |
| Reviewer "what's new vs. ISS / CLF / energy shaping" objection | High | High | **P1**: write related-work differentiation block before submitting; novelty = data-inducedness + parameter-free $\gamma$ |
| Macro data signal is weak: $E(X(t))$ doesn't rise before 2022 onset | Medium | High | Evaluate this in Phase 3 before committing to Paper 2; if weak, reframe as theoretical paper with synthetic-only illustrations |
| Terra/Luna data reconstruction gaps | Low | Low | No longer flagship use case; removed from primary evidence |
| Overclaim ("guarantees prevention") | Medium | High | Use conditional theorems + robustness envelopes; publish explicit failure cases |
| Architectural decision unresolved (single-state vs. N-agent) | High | Medium | **P0**: resolve in Phase 1 Week 1; determines whether proofs change |
| Someone publishes similar work first | Low | High | Paper 1 is theory-only; post to arXiv immediately after proofs are clean |
| No access to WRDS / Bloomberg | Low | Low | All primary data (FRED, BIS, Yahoo Finance) is free and already identified |

---

## Dependencies / Prerequisites

### Software
- Python 3.11+ (existing)
- GravityEngine (`udl/gravity.py`) — committed
- `fredapi` (pip install fredapi)
- `yfinance` (pip install yfinance)
- `pandas`, `numpy`, `scipy`, `scikit-learn` (existing)
- `matplotlib` / `seaborn` for figures
- LaTeX (Overleaf or local TeX Live)

### Data Access
- `fredapi` Python package + FRED API key (free, register at fred.stlouisfed.org)
- BIS statistics portal (bis.org/statistics — all downloads free, no key required)
- Yahoo Finance via `yfinance` Python package (free, no key required)
- WRDS access (optional; most equivalents available via FRED / Yahoo Finance if not available)
- IMF Data API at imf.org/en/Data (free)

### Compute
- CPU: sufficient for all ODE simulations and macro data pipelines (already verified)
- Storage: <5 GB total for all macro datasets (FRED, BIS, equity returns)

---

## Success Criteria

### Minimum Viable (Phase 1–3 complete)
- [ ] Theorems 1–4 proved with explicit conditions (no informal claims)
- [ ] Code update rule verified to match theoretical model
- [ ] $E(X(t))$ constructed and validated on FRED macro data
- [ ] Instability window detection demonstrated on 2022 held-out test
- [ ] Paper 1 draft ready for arXiv posting

### Full Success (Scientific — all phases complete)
- [ ] All three papers submitted to target venues
- [ ] $\gamma^*(t)$ estimates validated against 2022 and 2008 held-out windows
- [ ] Policy interpretation table published and reviewed by at least one economist or central bank researcher
- [ ] arXiv preprints for Papers 1 and 2 posted and cited

### Stretch (Tier 1 direction)
- [ ] Joint work or formal engagement with BIS, Fed, ECB, or Bank of England research division
- [ ] Policy brief for FSB or IMF citing the framework
- [ ] Extension to stochastic systems (Itô dynamics + stochastic energy functional)
- [ ] Generalisation of stability threshold $\gamma^*$ to time-varying network topology (AMTTP and CBDC applicability as a downstream consequence, not a prerequisite)

---

## Guardrails (Scientific Credibility)

- Separate (i) proved statements (conditional theorems), (ii) empirical findings, (iii) engineering claims.
- Prefer “certified under stated assumptions” over “guaranteed in general.”
- Always include robustness sweeps (noise, scaling drift, subsampling; and only claim invariances you test).
- Avoid leakage: any parameter/threshold/controller selection is tuned on train/val only and reported on held-out test windows.
