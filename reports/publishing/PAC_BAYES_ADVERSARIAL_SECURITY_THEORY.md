# Unified Adversarial Learning and PAC-Bayes Security Theory (Theoretical Background)

**Date:** February 7, 2026

## Scope / disclaimer (read first)

This document is **theoretical background**.

- It is **not** a claim that AMTTP’s repository implementation proves or satisfies these theorems.
- It is provided as publishable mathematical context (PAC-Bayes generalisation + adversarial game framing) that can be cited *as theory*, separately from the repository’s implementation-backed evidence under `reports/publishing/`.

---

## Definitions

### Definition 1 — Data distribution

Let $\mathcal{D}$ be the true (unknown) distribution over samples $(x,y) \in \mathcal{X} \times \mathcal{Y}$.

---

### Definition 2 — Hypothesis space

Let $\mathcal{H}$ be a measurable hypothesis class where each hypothesis satisfies
$$
 h: \mathcal{X} \rightarrow [0,1].
$$

---

### Definition 3 — Loss function

Assume a bounded loss
$$
\ell(h(x), y) \in [0,1].
$$

---

### Definition 4 — Prior and posterior

Let:

- **Prior:** $P$ over $\mathcal{H}$
- **Posterior:** $Q$ over $\mathcal{H}$

---

### Definition 5 — Risks

**True risk**
$$
R(Q) = \mathbb{E}_{h \sim Q}\, \mathbb{E}_{(x,y) \sim \mathcal{D}}\big[\ell(h(x), y)\big].
$$

**Empirical risk** (for a sample $S = \{(x_i,y_i)\}_{i=1}^n$)
$$
\widehat{R}_S(Q) = \mathbb{E}_{h \sim Q}\, \frac{1}{n} \sum_{i=1}^{n} \ell(h(x_i), y_i).
$$

---

# Part I — Deep PAC-Bayes security bound

## Theorem 1 — PAC-Bayes generalisation bound (deep form)

Let:

- $S \sim \mathcal{D}^n$ be an i.i.d. sample of size $n$
- $P$ be a prior over $\mathcal{H}$
- $Q$ be a posterior over $\mathcal{H}$

Then with probability at least $1-\delta$ over the draw of $S$,
$$
R(Q) \le \widehat{R}_S(Q) + \sqrt{\frac{\mathrm{KL}(Q\,\|\|\,P) + \ln\!\left(\frac{2\sqrt{n}}{\delta}\right)}{2n}}.
$$

---

### Lemma 1 — Change of measure inequality

For any measurable function $f$,
$$
\mathbb{E}_{h \sim Q}[f(h)] \le \mathrm{KL}(Q\,\|\|\,P) + \ln \mathbb{E}_{h \sim P}[e^{f(h)}].
$$

#### Proof

From the Gibbs variational principle,
$$
\mathrm{KL}(Q\,\|\|\,P)=
\sup_f\left(\mathbb{E}_{h \sim Q}[f(h)]-\ln\mathbb{E}_{h \sim P}[e^{f(h)}]\right).
$$
Rearranging yields the result. $\square$

---

### Lemma 2 — Empirical concentration (schematic)

Under standard bounded-loss concentration assumptions (e.g., Hoeffding-style), one can bound the exponential moment of the deviation between true and empirical risk. A typical schematic form is:
$$
\mathbb{E}\left[\exp\big(\lambda\,(R-\widehat{R})\big)\right] \le \exp\left(\frac{\lambda^2}{2n}\right),
$$
with appropriate conditioning and measurability assumptions.

---

### Proof of Theorem 1 (outline)

1. Apply Lemma 1 (change of measure).
2. Apply an exponential concentration inequality (e.g., Lemma 2).
3. Optimise over $\lambda$.
4. Apply a union bound over $\delta$.

The bound follows. $\square$

---

### Corollary 1 — Security interpretation (informal)

A smaller complexity term $\mathrm{KL}(Q\,\|\|\,P)$ suggests:

- more “stable” posterior behaviour relative to the prior,
- reduced capacity for overfitting to the sample,
- improved generalisation of the learned detector under distributional stability assumptions.

---

# Part II — Adversarial optimality (fraudster vs detector game)

### Definition 6 — Adversarial game

Players:

- detector strategy $D$
- fraudster strategy $F$

Payoff:
$$
V(D,F) = \mathbb{E}_{x \sim F}[\Pr(\text{detected} \mid D, x)].
$$

Zero-sum structure:

- detector maximises $V$
- fraudster minimises $V$

---

## Theorem 2 — Adversarial optimality (minimax)

If:

- strategy spaces are convex,
- the payoff is continuous and bilinear (in mixed strategies),

then
$$
\max_D\, \min_F\, V(D,F) = \min_F\, \max_D\, V(D,F),
$$
and a (mixed-strategy) equilibrium exists.

---

### Lemma 3 — Best response contraction (informal)

Under convexity assumptions, best-response updates are non-expansive in the mixed-strategy simplex.

#### Proof sketch

Follows from convexity of expected payoff under mixed strategies and standard properties of projection in simplices. $\square$

---

### Proof of Theorem 2

Apply the von Neumann minimax theorem. $\square$

---

### Corollary 2 — Security interpretation (informal)

At equilibrium:

- the detector cannot unilaterally improve detection probability against the equilibrium adversary,
- the adversary cannot unilaterally reduce detection probability against the equilibrium detector,

yielding a notion of adversarial stability.

---

# Part III — Unified security learning theorem

## Theorem 3 — Unified PAC-Bayes adversarial security bound (template)

At adversarial equilibrium with posterior $Q^*$,
$$
R_{\mathrm{adv}}(Q^*) \le \widehat{R}_S(Q^*) + \sqrt{\frac{\mathrm{KL}(Q^*\,\|\|\,P) + \ln(1/\delta)}{2n}}.
$$

---

### Lemma 4 — Adversarial risk decomposition (template)

$$
R_{\mathrm{adv}} = R_{\mathrm{clean}} + \Delta_{\mathrm{attack}}.
$$

---

### Lemma 5 — Attack amplification bound (template)

If an attacker divergence is bounded (relative to a baseline $F_0$), a typical template bound is
$$
\Delta_{\mathrm{attack}} \le \sqrt{\frac{\mathrm{KL}(F\,\|\|\,F_0)}{n}}.
$$

---

### Proof of Theorem 3 (outline)

Combine:

- a PAC-Bayes generalisation bound,
- an adversarial-risk decomposition,
- a constraint on adversary divergence.

$\square$

---

# Part IV — Consequences (informal)

### Corollary 3 — Security scaling law (informal)

$$
\text{Security strength} \propto \frac{1}{\sqrt{n}}.
$$

---

### Corollary 4 — Information-theoretic security limit (template)

$$
R_{\min} \ge e^{-I(X;Y)}.
$$

---

### Corollary 5 — ML security design rule (informal)

To improve robustness, seek to simultaneously control:

- empirical risk,
- complexity via $\mathrm{KL}(Q\,\|\|\,P)$,
- adversarial divergence (e.g., $\mathrm{KL}(F\,\|\|\,F_0)$).

---

# Part V — Research extensions (frontier directions)

### Extension 1 — Differential privacy link (conceptual)

PAC-Bayes complexity terms can be related to stability notions, and in some settings to privacy leakage measures.

---

### Extension 2 — Zero-knowledge security link (conceptual)

Posterior indistinguishability can be analogised to simulation/indistinguishability notions used in modern cryptography.

---

### Extension 3 — Optimal detector geometry (conceptual)

Decision boundary geometry (e.g., curvature and margins) influences adversarial susceptibility.

---

# Final unified statement (informal template)

## Grand unified security learning theorem (informal)

For a learning-based detector under a rational adversary,
$$
R_{\mathrm{real}} \le R_{\mathrm{emp}} + \text{Model complexity} + \text{Adversarial complexity} + \text{Finite-sample term},
$$
where the “complexity” terms are quantified via KL divergence and/or information-theoretic measures.

---

## Practical interpretation (informal)

If you:

- train to achieve low empirical error,
- control posterior complexity (stay close to the prior),
- limit adversary divergence/information gain, and
- use sufficient data,

then (under the relevant assumptions) adversarial failure probability can be bounded.
