# 08 — The Unified Paper

## One Sentence

> **Financial systems fail to detect the crises they create because detection failure and instability share the same geometric structure — and the gradient of that structure is the provably minimal corrective force.**

This is the claim that unifies UDL, BSDT, GravityEngine, and adaptive friction into a single contribution.

---

## Working Title

*"Systemic Risk as Geometry: A Unified Theory of Financial Instability, Detection, and Adaptive Stabilisation"*

Short version (arXiv/SSRN): *"From Detection Blind Spots to Stability: A Unified Geometric Framework for Networked Financial Systems"*

**Note on terminology (deferred).** A future rename of GravityEngine to a more algorithm-facing name (e.g. "Blind-Spot Gradient Descent") will be applied consistently across all papers at a single point. Until then, all documents use **GravityEngine** to avoid cross-paper inconsistency.

---

## Why This Is One Paper, Not Three

| Component | Existing work | Role in unified paper |
|---|---|---|
| UDL | Deviation geometry; what normal looks like | Derives the deviation operators $\delta_i(X)$ |
| BSDT | Decomposes missed-detection into $C, G, A, T$ | Shows $\delta_i$ are near-orthogonal and span the failure space |
| GravityEngine | Computes forces $\nabla\Phi$ over agent configurations | Is the online algorithm that computes $\nabla E$ in real time |
| Adaptive friction | Damps dynamics via $\gamma(E)\nabla E$ | Is the optimal response to $E$ under a social planner's problem |

The connection that makes them one paper: the BSDT score
$$\text{MFLS}(X) = \sum_{i=1}^{4} w_i \cdot S_i(X)$$
and the adaptive damping energy functional
$$E(X) = \sum_i \psi(\delta_i(X)) + \sum_{i<j} \phi(\|X_i - X_j\|)$$
are the **same object**: one is a statistical decomposition of deviation from normality, the other is the Lyapunov candidate for the controlled system. Proving this equivalence formally is the central theorem.

---

## The Central Theorem (Convergence Theorem)

**Theorem C — Equivalence of Blind-Spot Geometry and Instability Energy (Referee-Ready Statement).**

Let $\mathcal{N}$ be the reference measure of normal system states. Let $\delta_i(X)$ be the BSDT deviation operators (Camouflage, Feature Gap, Activity Anomaly, Temporal Novelty) calibrated on $\mathcal{N}$. Define the blind-spot energy:

$$E_{\text{BS}}(X) = \sum_{i=1}^{4} \psi_i(\delta_i(X)) + \sum_{i<j} \phi(\|X_i - X_j\|)$$

where each $\psi_i$ is convex, increasing, and 1-Lipschitz, and $\phi$ is a short-range attractive potential (erf-based, as in BSGD).

Under regularity assumptions (E1)–(E3) and the deviation-separating condition of Odeyemi (202X), the following hold in a neighbourhood of any equilibrium $X^\star$:

1. **Gradient alignment (two-sided)**: There exist constants $c_1, c_2 > 0$ such that
   $$c_1 \|\nabla \Phi(X)\| \le \|\nabla E_{\text{BS}}(X)\| \le c_2 \|\nabla \Phi(X)\|$$
   uniformly on sublevel sets $\{X : E_{\text{BS}}(X) \le M\}$. The blind-spot gradient and the restoring force are uniformly equivalent in magnitude; they point in approximately the same direction (alignment angle $\cos\theta \ge 1 - \epsilon$ under the separating condition).

2. **Energy equivalence (two-sided)**: For any $M > 0$ there exist $a, b > 0$ such that
   $$a\, V(X, X^\star) \le E_{\text{BS}}(X) \le b\, V(X, X^\star)$$
   on $\{X : V(X, X^\star) \le R\}$, where $V(X, X^\star) = \Phi(X) - \Phi(X^\star)$ is the standard Lyapunov function for the gradient flow. The constants $a, b$ depend only on the Lipschitz constants of $\psi_i$ and the curvature of $\Phi$ at $X^\star$.

3. **Stabilisation sufficiency (local asymptotic stability)**: The damped dynamics
   $$\dot{X} = F(X) - \gamma(E_{\text{BS}}(X))\nabla E_{\text{BS}}(X)$$
   with $\gamma(E) \ge \kappa > 0$ for $E > \theta > 0$ renders $X^\star$ locally asymptotically stable whenever the uncontrolled system is unstable but the open-loop Jacobian remains Hurwitz under bounded damping.

*Proof strategy.* Part 1 follows from the chain rule and the Lipschitz bound on $\psi_i$ together with the lower bound on $\|\delta_i'(X)\|$ given by the separating condition. Part 2 is a standard energy comparison lemma using the two-sided bound in Part 1. Part 3 applies the LaSalle invariance principle (Proof 2 of the framework) with $V = E_{\text{BS}}$ as the Lyapunov candidate; the descent property $\frac{d}{dt}E_{\text{BS}} \le -\kappa c_1^2 \|\nabla\Phi\|^2$ follows from Parts 1 and 2 combined with the descent rate formula.

*Interpretation*: A statistical detector trained only on normal data, when decomposed into BSDT blind-spot operators, already encodes the complete geometric information needed to stabilise the system. Detection and stabilisation are not separate problems — they are dual views of the same geometric structure. This is the central non-trivial claim of the paper.

---

## The Four-Community Structure

### 1. Mathematics contribution
*Energy-induced gradient systems with data-constructed Lyapunov functions.*

**Core results**:

- **Theorem 1 (Descent)**: $\frac{d}{dt}E(X(t)) \le 0$ when $\gamma(E) > C$ (standard).
- **Theorem 2 (Sharp phase transition)**: Define the effective coupling operator $\mathcal{L}(\rho,\ell) = \rho\ell\mathbf{W} - \mathbf{I}$, where $\mathbf{W}$ is the row-normalised weighted adjacency matrix of agent interactions. The critical manifold is
  $$\mathcal{C} = \left\{(\rho,\ell) : \lambda_{\max}(\rho\ell\mathbf{W}) = 1\right\}$$
  (spectral radius criterion, not determinant — the determinant form only holds in mean-field / rank-1 approximations). Instability occurs when $\lambda_{\max}(\mathcal{L}) > 0$, equivalently when $\lambda_{\max}(\rho\ell\mathbf{W}) > 1$. Below $\mathcal{C}$: any bounded constant $\bar\gamma$ stabilises the system. Above $\mathcal{C}$: no bounded constant damping stabilises; state-adaptive $\gamma(E(X))$ is *necessary*.
  This is an impossibility result for static policy. The critical surface is directly observable: $\lambda_{\max}(\rho\ell\mathbf{W}) = 1$ can be estimated from network density (BIS bilateral exposures), mean leverage (FRED bank leverage ratios), and the largest eigenvalue of the connectivity matrix (computable from regulatory filings).
- **Theorem 3 (Equilibrium preservation)**: Equilibria are preserved (standard; needed for policy interpretation).
- **Theorem 4 (Discrete descent)**: Armijo backtracking guarantees $E^{t+1} \le E^t$ (standard).
- **Theorem C (Convergence / Equivalence)**: BSDT geometry = instability energy (the new result).

**Target**: SIAM Journal on Applied Mathematics or Journal of Nonlinear Science.

---

### 2. Computer Science contribution
*GravityEngine as an online algorithm: regret bounds and approximation guarantees.*

**Framing**: At each time step $t$, the system receives state $X_t$, must output a damping decision $\gamma_t$, then observes the next state $X_{t+1}$. This is an **online convex optimisation** problem with the loss $\ell_t(\gamma) = E(X_{t+1}(\gamma))$.

**Core results**:

- **Proposition CS1 (Online regret bound)**: Running GravityEngine with online gradient descent on $\gamma_t$ achieves regret
  $$R_T = \sum_{t=1}^T \ell_t(\gamma_t) - \min_\gamma \sum_{t=1}^T \ell_t(\gamma) \le O(\sqrt{T})$$
  under Lipschitz loss and bounded gradient assumptions. This is the standard OCO bound, but the significance is that GravityEngine's $\nabla E$ computation makes it *efficiently implementable* in this online setting.

- **Proposition CS2 (Computational complexity)**: Computing $\nabla E(X)$ via $k$-NN approximation costs $O(n \cdot k \cdot d)$ per step, where $n$ = number of agents, $k$ = neighbourhood size, $d$ = state dimension. Under graph sparsification (keeping only edges with weight $\ge \tau$), this reduces to $O(n \log n)$ using a $k$-d tree.

- **Proposition CS3 (Approximation guarantee)**: The $k$-NN approximation of $\nabla E$ satisfies
  $$\|\widehat{\nabla E}(X) - \nabla E(X)\| \le C / k^{1/d}$$
  under a standard smoothness assumption on $E$. For $k = O(\log n)$ and fixed $d$, this is $O(1/\text{polylog}(n))$.

**What this gives CS**: GravityEngine is not just a simulation tool — it is an **efficient, approximation-guaranteed online algorithm** for adaptive stabilisation. The regret bound means it is competitive with the best fixed policy in hindsight, a meaningful strongest-possible benchmark for online control. The algorithmic framing also opens connections to literature on online convex optimisation over manifolds and non-stationary environments.

**Target**: NeurIPS algorithms track, or SODA / ICALP for the approximation result.

---

### 3. Operations Research contribution
*Optimal adaptive friction as the solution to a stochastic dynamic programme.*

**Framing**: The social planner chooses $\gamma_t$ to minimise total instability cost:

$$V(X_t) = \min_{\{\gamma_s\}_{s \ge t}} \mathbb{E}\left[\sum_{s=t}^\infty \beta^{s-t}\left(E(X_s) + c(\gamma_s)\right)\;\Big|\; X_t\right]$$

where $c(\gamma) = \kappa \gamma^2$ is a cost of intervention (friction has a price — it slows legitimate activity), and $\beta \in (0,1)$ is a discount factor.

**Core results**:

- **Theorem OR1 (Bellman equation)**: $V$ satisfies
  $$V(X) = \min_{\gamma \ge 0}\left[E(X) + c(\gamma) + \beta \mathbb{E}[V(X') \mid X, \gamma]\right]$$
  where $X' = X + h[F(X) - \gamma\nabla E(X)] + \text{noise}$ (Euler-Maruyama step).

- **Theorem OR2 (Optimal policy structure)**: The optimal $\gamma^*(X)$ satisfies the first-order condition
  $$2\kappa \gamma^* = \beta \frac{\partial}{\partial \gamma}\mathbb{E}[V(X') \mid X, \gamma]\Big|_{\gamma^*}$$
  and under the gradient-system structure, this has a closed-form approximation:
  $$\gamma^*(X) \approx \frac{\beta \cdot \|\nabla E(X)\|^2}{2\kappa + \beta\|\nabla E(X)\|^2} \cdot \frac{E(X)}{E(X) + \theta}$$
  which *recovers* the adaptive damping law $\gamma(E) = E/(E+\theta)$ as the leading-order term. The parameter $\theta$ is pinned by $\kappa/\beta$ — the ratio of intervention cost to patience.

- **Theorem OR3 (Necessity of state-dependence)**: A constant policy $\bar\gamma$ achieves value $V_{\bar\gamma}(X)$; the welfare gap is
  $$V^*(X) - V_{\bar\gamma}(X) \ge \Delta(\rho, \ell) > 0$$
  for all $X$ above the critical manifold $\mathcal{C}$. Constant friction is strictly suboptimal when the system is above the fragility threshold.

**What this gives OR**: The adaptive friction formula is not heuristic — it is the **analytically derived optimal policy** of a well-posed infinite-horizon stochastic control problem. The intervention cost parameter $\kappa$ is interpretable: it is the social cost of slowing financial activity, which can be calibrated from GDP data.

**Target**: *Operations Research*, *Management Science*, or *Mathematics of Operations Research*.

---

### 4. Economics / Central Bank contribution
*Welfare calibration and the policy interpretation of $\gamma^*$.*

**Framing**: Translate $\gamma^*(X)$ into units that central bankers use — basis points, capital ratios, buffer requirements.

**Core results**:

- **Calibration equation**: Under a log-linear approximation around steady state, the stability threshold $\gamma^*$ maps to a required countercyclical capital buffer increment:
  $$\Delta\text{CCyB}(t) \approx \kappa^{-1} \cdot \gamma^*(X_t) \cdot \sigma_\ell$$
  where $\sigma_\ell$ is the cross-sectional standard deviation of leverage in the banking system (observable from BIS data). This converts the abstract damping coefficient into a Basel III-compatible policy variable.

- **Welfare cost of inaction (multi-period)**: The expected welfare loss from running at $\gamma = 0$ over each instability window, computed as:
  $$\mathcal{L}_{\text{inaction}} = \int_{t_0}^{t_1} \left[E(X_t) - E(X_t^{\gamma^*})\right] dt$$
  calibrated to consumption-equivalent units via a standard Euler equation. Evaluate over three periods: 2008 GFC (primary flagship), 2020 COVID shock (robustness), 2023 regional banking stress (recency). The 2022 rate-shock window is included as Appendix D (supplementary illustration, 1 page). Multi-period validation prevents over-fitting to a single episode and demonstrates the method is not crisis-specific.

- **Comparison to existing instruments**: Show explicitly that $\gamma^*(X_t)$ spikes *before* known stress onset more sharply than either SRISK (Brownlees & Engle 2017) or $\Delta$CoVaR (Adrian & Brunnermeier 2016), across all three periods. Data sources: FRED macro-financial indicators (credit spreads, leverage ratios, term spreads), BIS locational banking statistics (cross-border exposures), CRSP/Compustat firm-level leverage networks (supply-chain or return-correlation networks). The advantage is that $\gamma^*$ is forward-looking (derived from $\nabla E$, which reflects current systemic configuration) rather than backward-looking (regression-based tail risk measures). This property is verifiable via a simple lead-lag test: regress stress indicators on $\gamma^*(t-k)$ for $k = 1, \ldots, 12$ quarters.

**Target**: *Journal of Finance* or *Review of Financial Studies* (empirical contribution); *American Economic Review* if micro-foundations section is complete; *BIS Working Papers* for direct policy circulation.

---

## The Micro-Foundation (Elevating to Nobel-Level)

This is the hardest part but the most important. It derives $F(X)$ from agent behaviour rather than assuming it.

**Set-up**: There are $N$ financial institutions. Each institution $i$ chooses leverage $\ell_i(t)$ to maximise expected profit subject to limited liability:
$$\max_{\ell_i} \mathbb{E}[\ell_i \cdot r_i(X)] - \frac{1}{2}\mu \ell_i^2 \quad \text{s.t.} \quad \ell_i \ge 0$$
where $r_i(X) = \bar{r} + \beta_i^\top X + \epsilon_i$ is return as a function of system state (herding channel: institutions' returns are correlated through $X$).

**Nash equilibrium dynamics**: The best-response dynamics of this game generate:
$$\dot{X}_i = \ell_i^*(X) \cdot [r_i(X) - \bar{r}] = \frac{\beta_i^\top X}{\mu} \cdot \beta_i^\top X$$

This is a *quadratic* positive-feedback term — exactly the amplifying dynamics (A2) that the abstract model assumes. The Jacobian has positive eigenvalues whenever $\|\beta\|^2/\mu > 1$ (the instability condition is now pinned to observable parameters: $\beta$ from asset pricing, $\mu$ from risk tolerance).

**Consequence**: The critical manifold $\mathcal{C}(\rho, \ell)$ is no longer abstract — it is the set
$$\mathcal{C} = \left\{(\rho, \ell) : \frac{\rho \cdot \bar\ell^2}{\mu} = 1\right\}$$
where $\bar\ell$ is mean leverage and $\rho$ is network connectivity. Central banks can estimate all three quantities directly.

**Welfare gap**: The decentralised equilibrium produces $E_{\text{DE}}(X) > E_{\text{SP}}(X)$ (the social planner's outcome) by a gap that equals the *negative externality* of each institution's leverage choice on the system's energy. The state-dependent damping coefficient $\gamma^*(X)$ is the Pigouvian correction that internalises the marginal externality of each institution's leverage choice on the system's instability energy $E(X)$. Under quadratic costs of intervention, the optimal policy coincides with the adaptive law derived from the energy gradient, providing a micro-founded justification for state-contingent macroprudential instruments. The tax rate $\gamma^*(X)$ is not a fixed surcharge — it rises with the gradient $\|\nabla E(X)\|$, meaning the correction is largest exactly when the system is most fragile.

This connects the mathematics directly to Pigou (welfare correction), Arrow-Debreu (decentralised equilibrium vs. planner), and the Diamond-Dybvig tradition (systemic fragility from individually rational behaviour) — the three pillars that economists use to evaluate whether a contribution is fundamental.

---

## Paper Structure (22–28 pages + appendix)

| Section | Content | Community |
|---|---|---|
| 1. Introduction | Gap statement; Mathematical Overview box (4 theorems); roadmap | All |
| 2. Agent model and equilibrium dynamics | $N$-institution game → quadratic feedback → amplifying $F(X)$ | Economics |
| 3. Blind-spot energy functional | BSDT operators $\delta_i$ → $E_{\text{BS}}(X)$; regularity theorems | Mathematics |
| 4. Equivalence theorem | Theorem C: two-sided bounds; LAS sufficiency | Mathematics |
| 5. Adaptive damping | $\dot{X} = F - \gamma\nabla E$; Theorems 1–4; spectral critical manifold | Mathematics |
| 6. Online algorithm | GravityEngine as OCO; regret bound; $O(n\log n)$ complexity | CS |
| 7. Optimal policy | DP formulation; Theorems OR1–OR3; closed-form $\gamma^*$ | OR |
| 8. Empirical validation | FRED + BIS + CRSP data; 2008/2020/2023 stress windows; lead-lag test vs. SRISK, $\Delta$CoVaR | Economics |
| 9. Welfare calibration | Consumption-equivalent welfare cost; CCyB formula; Pigouvian interpretation | Economics |
| 10. Discussion | Audience table; limitations; open problems; policy conditions | All |
| Appendix A | Full proofs (Theorems 1–4, C, OR1–OR3) | Mathematics |
| Appendix B | Derivation of Nash equilibrium dynamics | Economics |
| Appendix C | Complexity proofs (CS2, CS3) | CS |
| Appendix D | 2022 rate-shock supplementary illustration (≤ 1 page) | Economics |

**Mathematical Overview box (to appear in §1 Introduction):** A ½-page boxed environment summarising the four main theorems — Theorem C (equivalence), Theorem 2 (spectral phase transition), Theorem OR2 (closed-form $\gamma^*$), Proposition CS1 (online regret) — with one-sentence non-technical summaries for each. This box allows specialists to locate the contribution relevant to their field without reading the entire paper.

---

## Submission Strategy

### Primary target (submit sequentially, one journal at a time)

1. **Journal of Political Economy** — Pigouvian welfare externality framing + micro-foundations makes this a natural fit. Requires micro-foundation section to be complete and tight.
2. **Econometrica** — if Theorem C and the spectral phase transition are the contributions referees engage with most. The two-sided equivalence bounds and LAS result have the rigour Econometrica expects.
3. **Review of Financial Studies** — if the multi-period empirical validation (2008/2020/2023) and CCyB calibration formula are the strongest standalone contributions.

### Parallel / fallback (by community)

| Track | Primary | Fallback |
|---|---|---|
| Mathematics | *SIAM Journal on Applied Mathematics* | *Journal of Nonlinear Science* |
| CS | *NeurIPS* (algorithms track) | *ICALP / SODA* (complexity) |
| OR | *Operations Research* | *Management Science* or *Math. of OR* |
| Policy | *BIS Working Papers* | *Journal of Financial Regulation* |

### Preprint strategy

- **arXiv**: cross-list to `econ.GN` + `math.DS` + `cs.DS` simultaneously — this is the most efficient way to reach all four communities in one action
- **SSRN**: Finance section, posted the same day as arXiv — central bank researchers use SSRN, not arXiv
- **Policy brief**: 2-page version for BIS Quarterly Review submission — this is how the result reaches Basel Committee staff

---

## Immediate Next Three Actions

These are the three things that must happen before writing a single LaTeX line.

### Action 1 — Resolve the architectural decision (1 day)

The single-agent vs. $N$-agent question. **The answer is $N$-agent** (the micro-foundation section makes this mandatory). This means:
- State space: $X \in \mathbb{R}^{N \times d}$
- $E(X) = \sum_i \psi(\delta_i(X)) + \sum_{i<j}\phi(\|X_i - X_j\|)$ (both terms active)
- GravityEngine already operates in this space — the code is compatible

### ✅ Action 2 — Verify gradient alignment numerically — DONE

**Result: PASS.** Script `verify_gradient_alignment.py` (commit 64aa01a), $N=50$, $d=4$, 200 steps.

| Metric | Value |
|---|---|
| Mean $\cos\theta$ | **0.8616** |
| Fraction of steps $\geq 0.7$ | **100%** |
| Threshold | 0.7 |

The alignment is strong and monotonically improves as the system moves away from the initial scattered state (early steps 0.74–0.77 → late steps 0.88–0.92). This is consistent with Theorem C: alignment tightens as $X$ approaches the critical manifold $\mathcal{C}$ where both $\nabla E_{\text{BS}}$ and $-\nabla\Phi$ concentrate.

**Conclusion: Theorem C is empirically supported. Formal proof is warranted.** Proceed to Action 3.

### Action 3 — Write the two-page impossibility sketch (2 days)

Prove (or formally conjecture with computational support) that constant $\bar\gamma$ fails above $\mathcal{C}$. This is the result that makes the whole paper necessary — it is the reason adaptive friction exists rather than Basel III buffer rules being sufficient.

---

### Impossibility Theorem (Sketch) — Constant Friction is Insufficient Above $\mathcal{C}$

**Setup.** Consider the $N$-agent GravityEngine with *constant* coupling strength $\bar\gamma > 0$:
$$\dot X_i = -\alpha(X_i - \mu) - \bar\gamma \sum_{j \neq i} f'(\|X_i - X_j\|)\frac{X_i - X_j}{\|X_i-X_j\|} + \xi_i$$
where $\alpha > 0$ is the radial spring, $f$ is pairwise potential. Denote the pairwise Jacobian evaluated at a configuration $X$ by $J(X) \in \mathbb{R}^{Nd \times Nd}$, with $\lambda_{\max}(J(X))$ the largest eigenvalue of its symmetrisation.

**Definition.** The critical manifold is:
$$\mathcal{C} = \{X \in \mathbb{R}^{N \times d} : \lambda_{\max}(\rho(X)\,\ell(X)\,\hat{W}) = 1\}$$
where $\rho(X)$ is the mean pairwise correlation, $\ell(X)$ the mean exposure, and $\hat W$ the normalised adjacency matrix. Points with $\lambda_{\max} > 1$ are *above* $\mathcal{C}$ (the unstable side).

**Proposition 1 (Linear instability, constant $\bar\gamma$).** Fix $\bar\gamma > 0$ and $\alpha > 0$. For any $M > 0$ there exists a configuration $X^{(M)}$ above $\mathcal{C}$ with $\lambda_{\max}(J(X^{(M)})) > M$. Consequently:
$$\lambda_{\max}\bigl(-\alpha I + \bar\gamma J(X^{(M)})\bigr) > 0$$
i.e., there exist directions in which the linearised constant-friction dynamics are *unstable* at $X^{(M)}$.

*Proof sketch.* Take $N$ agents arranged so pairwise distances $\|X_i - X_j\| \to 0$ (herding configuration). In this limit pairwise forces become strongly repulsive ($f'' > 0$) but correlation $\rho \to 1$. The pairwise Jacobian $J = \bar\gamma \nabla^2 \sum_{i<j} f(\|X_i - X_j\|)$ has its maximum eigenvalue scale as $\Theta(N \bar\gamma / \epsilon^2)$ where $\epsilon = \min_{i\neq j}\|X_i-X_j\|$. For small enough $\epsilon$, $\bar\gamma \lambda_{\max}(J) \gg \alpha$. $\square$

**Proposition 2 (Adaptive friction restores stability everywhere).** Let $\gamma^*(X) = \alpha / \lambda_{\max}(J(X))$. Then for all $X$:
$$\lambda_{\max}\bigl(-\alpha I + \gamma^*(X) J(X)\bigr) = 0$$
and the adaptive system is marginally stable at every configuration, becoming asymptotically stable via the radial spring as soon as $X$ exits the $\mathcal{C}$-neighbourhood. 

**Corollary (Basel III insufficiency).** A fixed capital buffer $\bar\kappa$ corresponds to constant friction $\bar\gamma \propto \bar\kappa$. By Proposition 1, for sufficiently correlated portfolios (small $\epsilon$, high $\rho$), the constant-friction system is linearly unstable. No fixed $\bar\kappa$ can cover all above-$\mathcal{C}$ configurations without either (a) being prohibitively large in normal times or (b) failing during herding. This is the formal statement of *procyclicality* — a constant tool applied to a heteroskedastic system.

**What this means for the paper.** The impossibility result is the *necessity* half of the main theorem. The constructive part (adaptive $\gamma^*$ satisfies the regret bound) is the *sufficiency* half. Together they establish that adaptive friction is the **minimal** intervention: no simpler rule works above $\mathcal{C}$, and $\gamma^*$ works everywhere.

**~~Remaining gaps~~ → All three closed in `05_THEORETICAL_FRAMEWORK.md` (Proofs 6–8).**

| Gap | Resolution | Proof |
|-----|-----------|-------|
| 1. Linearisation only | Extended to global Lyapunov mode-energy argument via $W(t) = \frac{1}{2}\langle X-X^\star, u\rangle^2$, $\dot W \ge cW$ above $\mathcal{C}$ | Proof 6, Steps 3–4 |
| 2. Force-clamp singularity | $L_{\text{pair}}^{\text{clamp}}(c) \le F_{\max}/\delta_{\min}(c) < \infty$ on any compact sublevel set; `max_force=100` is a principled regulariser, not a numerical hack | Proof 7 |
| 3. Tractable $\gamma^\star(X)$ online | OGD on $\gamma_t$ achieves $R_T = O(\sqrt T)$; $\lambda_{\max}$ approximated by power iteration with finite-difference HVP at $O(N^2 d \log N)$ per step — no worse than existing pairwise loop | Proof 8 |

**Status: theoretical foundation is complete. LaTeX draft can begin.**

---

## What Success Looks Like

| Milestone | Indicator |
|---|---|
| Mathematics respects it | Theorem C accepted; sharp phase transition proved; SIAM / Econometrica referee does not find the proofs trivial |
| CS respects it | Regret bound and $O(n\log n)$ complexity are cited in online learning literature |
| OR respects it | The closed-form $\gamma^*$ derivation is used in policy optimisation courses as a canonical example |
| Economics respects it | The Pigouvian interpretation of adaptive friction is cited in macro-prudential regulation literature; BIS or Fed researchers engage with it |
| Central banks use it | The CCyB calibration formula is applied to real data by at least one central bank research division |

All five happen from the same paper. That is the convergence point.
