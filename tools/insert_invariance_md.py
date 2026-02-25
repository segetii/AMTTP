"""Insert invariance analysis section into the .md paper."""
import re

path = 'papers/blind_spot_decomposition_theory.md'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# Check if already present
if 'Invariance Analysis' in text:
    print('Invariance Analysis section already present - skipping')
    exit(0)

INVARIANCE_SECTION = r"""
---

## 8. Invariance Analysis

We characterise the symmetry and equivariance properties of the four BSDT components and the five correction operators. Understanding which invariances hold (and which break) is important for two reasons: **(i)** it identifies the preprocessing assumptions under which BSDT is valid, and **(ii)** it reveals which operators can be applied safely without risk of degrading the base model.

### 8.1 Notation

Let $x \in \mathbb{R}^d$ be a feature vector, $S(x) = [C(x), G(x), A(x), T(x)]$ the component vector, and $\hat{p}(x)$ the base model's fraud probability. We write $\hat{p}^*(x)$ for the corrected probability under a given operator. We analyse eight properties: scale invariance, translation invariance, permutation invariance, monotone equivariance, affine equivariance, correction safety ($\hat{p}^* \geq \hat{p}$), label dependence, and dimensionality stability.

### 8.2 Component-Level Invariances

**Proposition 7 (Component invariance profile).** Under the BSDT component definitions:

1. **Scale.** None of $C, G, A, T$ is scale-invariant. $G$ is approximately invariant for $|\alpha| \gg \epsilon$ (threshold effect) but collapses to 1 as $\alpha \to 0$.
2. **Translation.** No component is translation-invariant. $C$ depends on $\|x - \mu_\text{legit}\|$; $G$ depends on the absolute zero threshold; $A$ and $T$ depend on reference statistics.
3. **Permutation.** $G$ is permutation-invariant (it counts near-zero features regardless of position). $C$, $A$, and $T$ are not ($C$ depends on per-feature $\mu_\text{legit}$; $A$ accesses specific column indices; $T$ uses per-feature reference moments).
4. **Dimensionality ($d \to \infty$).** $T$ converges to $\sigma(-0.5) \approx 0.378$ under the null by the law of large numbers on normalised squared deviations (empirically: $\text{std}(T) < 0.011$ at $d = 1000$). $G$ converges to $P(|X_j| < \epsilon)$. $A$ is dimension-independent (uses 2 columns). $C$ drifts toward 0 as $d$ grows because Euclidean distances concentrate; this is mitigated by the 99th-percentile normalisation but not eliminated.

*Proof.* (i)-(iii): Direct from the formulae. For (i), $C(\alpha x) = 1 - \|\alpha x - \mu\|_2 / d_{\max} \neq C(x)$ unless $\alpha = 1$. For (iii), $G(\Pi x) = |\{j : |x_{\pi(j)}| < \epsilon\}|/d = |\{j : |x_j| < \epsilon\}|/d = G(x)$. (iv): For $T$, the normalised mean $\bar{m}(x) = d^{-1} \sum_j (x_j - \bar{x}_j^{\text{ref}})^2 / \text{Var}_j^{\text{ref}}$ converges a.s. by the SLLN when feature deviations are i.i.d. with finite second moment. Empirical verification on synthetic Gaussian data ($d \in \{10, 50, 93, 200, 500, 1000\}$) confirms convergence of $T$ and drift of $C$ (Table 3). $\square$

**Table 3: Dimensionality sensitivity of BSDT components** (synthetic Gaussian, $n=1000$, 5% fraud rate).

| $d$ | $\bar{C} \pm \sigma$ | $\bar{G}$ | $\bar{T} \pm \sigma$ |
|-----|----------------------|------------|----------------------|
| 10 | $0.720 \pm 0.172$ | 0.000 | $0.416 \pm 0.083$ |
| 50 | $0.676 \pm 0.144$ | 0.000 | $0.413 \pm 0.034$ |
| 93 | $0.654 \pm 0.135$ | 0.000 | $0.417 \pm 0.026$ |
| 200 | $0.565 \pm 0.120$ | 0.000 | $0.421 \pm 0.019$ |
| 500 | $0.455 \pm 0.094$ | 0.000 | $0.419 \pm 0.014$ |
| 1000 | $0.325 \pm 0.064$ | 0.000 | $0.414 \pm 0.011$ |

### 8.3 Operator-Level Properties

**Proposition 8 (Correction operator properties).** The five correction operators satisfy:

1. **Monotone equivariance.** MFLS is monotone: if $S_i(x) \leq S_i(x')$ for all $i$, then $\text{MFLS}(x) \leq \text{MFLS}(x')$, because MI weights $w_i \geq 0$. SignedLR is *not* monotone: learned coefficients $\beta_i$ can be negative (empirically, $\beta_C < 0$ in 4/5 out-of-domain datasets).
2. **Correction safety.** MFLS and SignedLR (max formulation) guarantee $\hat{p}^*(x) \geq \hat{p}(x)$ by construction. QuadSurf and ExpGate do not: the polynomial residual can be negative (empirically, 73.2% of samples violate $\hat{p}^* \geq \hat{p}$ on synthetic data).
3. **Idempotency.** SignedLR (max formulation) is idempotent: $\max(\hat{p}, \max(\hat{p}, p_{\text{SLR}})) = \max(\hat{p}, p_{\text{SLR}})$. MFLS is not strictly idempotent (repeated application further uplifts sub-threshold samples), though the uplift converges to zero.
4. **Commutativity.** The operator chain is non-commutative. SignedLR targets classification; QuadSurf targets residual regression. Reversing their order changes the objective surface.

*Proof.* (i): $\text{MFLS}(x) = \sum_i w_i S_i(x)$ with $w_i \geq 0$; component-wise domination implies sum domination. For SignedLR, $\sigma(\cdot)$ is monotone increasing, but $\sum_i \beta_i S_i(x)$ with negative $\beta_i$ can decrease when a dominated component increases, breaking monotonicity. (ii): $\hat{p}^*_{\text{MFLS}} = \hat{p} + \lambda \cdot \text{MFLS} \cdot (1-\hat{p}) \cdot \mathbb{1}[\hat{p} < \tau]$ with $\lambda \geq 0$, $\text{MFLS} \in [0,1]$, $(1-\hat{p}) \geq 0$, so the additive term is non-negative. The max formulation $\max(\hat{p}, p_{\text{SLR}})$ is self-evidently safe. For QuadSurf, $\hat{p}_{\text{quad}} = \text{clip}(\hat{p} + \boldsymbol{\beta}^\top \phi_2(S), 0, 1)$ and $\boldsymbol{\beta}^\top \phi_2(S)$ is unconstrained in sign. (iii): $\max(a, \max(a, b)) = \max(a, b)$ for $a, b \in \mathbb{R}$. For MFLS, the second application applies the same formula to $\hat{p}^*$; since $\hat{p}^* \geq \hat{p}$, fewer samples fall below $\tau$ and those that do receive a smaller $(1 - \hat{p}^*)$ multiplier. The sequence $\hat{p}^{(k)}$ is monotonically increasing and bounded above by 1, hence convergent. $\square$

### 8.4 Affine Equivariance and the Re-Fitting Requirement

BSDT components are defined in the preprocessed feature space (sign-log + RobustScaler). Under an arbitrary affine transformation $x \mapsto Ax + b$ without re-fitting reference statistics, components change by a mean absolute deviation of up to 0.13 (Camouflage). When reference statistics are re-fit on the transformed data, the deviation drops substantially (to $<0.06$ for $C$, $<0.05$ for $A$, $<0.04$ for $T$; $G$ is exactly invariant).

**Corollary (Re-fitting requirement).** BSDT components are not affine-equivariant with fixed reference statistics. Domain adaptation requires re-fitting $\mu_\text{legit}$, $d_{\max}$, $\bar{x}^{\text{ref}}$, and $\text{Var}^{\text{ref}}$ on the target-domain train-fit split. Only $G$ is invariant without re-fitting.

### 8.5 Label Dependence

Three of four components require labelled data for reference statistics ($C$: legitimate centroid, $A$: fraud activity stats, $T$: fraud reference distribution). Only $G$ (Feature Gap) is label-free. Among weighting schemes, Fisher Variance-Ratio weights are unsupervised (using model-output splits only), enabling a fully label-free path: $G + \text{VR weights} \to \text{MFLS}$. All advanced operators (SignedLR, QuadSurf, ExpGate) require labelled calibration data, with SignedLR converging with as few as ~50 labelled samples.

### 8.6 Invariance Summary

**Table 4: Invariance and algebraic properties of BSDT components and correction operators.** Checkmark = holds; X = violated; ~ = approximately holds; --- = not applicable.

| Property | $C$ | $G$ | $A$ | $T$ | MFLS | SLR | QS | EG |
|----------|-----|-----|-----|-----|------|-----|----|----|
| Scale invariance | X | ~ | X | X | X | X | X | X |
| Translation invariance | X | X | X | X | X | X | X | X |
| Permutation invariance | X | Yes | X | X | X | X | X | X |
| Monotone equivariance | --- | --- | --- | --- | Yes | X | X | X |
| Safety (p* >= p) | --- | --- | --- | --- | Yes | Yes | X | X |
| Label-free | X | Yes | X | X | VR | X | X | X |
| Idempotent | --- | --- | --- | --- | X | Yes | --- | --- |
| Dim-stable (d -> inf) | X* | Yes | Yes | Yes | Yes | Yes | X** | X** |

*C drifts toward 0 due to distance concentration. **Polynomial feature count grows as O(d^2).

The key insight is that MFLS and SignedLR(max) are the only *safe* operators (guaranteed p* >= p), while QuadSurf and ExpGate trade safety for expressiveness -- the polynomial residual can decrease predictions for samples where the base model is already accurate. In practice, the safety violations in QuadSurf/ExpGate are beneficial: they suppress false alarms from the base model, reducing FDR from 46.9% (SignedLR) to 36.0% (QuadSurf).
"""

# Insert before "## 9. Discussion"
marker = '## 9. Discussion'
idx = text.find(marker)
if idx == -1:
    print('ERROR: Could not find ## 9. Discussion marker')
    exit(1)

# Find the preceding --- line
# Look backward for the "---" separator
pre = text[:idx]
last_hr = pre.rfind('---')
if last_hr == -1:
    print('ERROR: Could not find --- separator before Discussion')
    exit(1)

# Insert right before the --- that precedes Discussion
new_text = text[:last_hr] + INVARIANCE_SECTION.lstrip('\n') + '\n\n---\n\n' + text[idx:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_text)

# Verify
if 'Invariance Analysis' in new_text:
    print('SUCCESS: Invariance Analysis section inserted')
    # Count sections
    import re
    headers = re.findall(r'^## (\d+)\. (.+)', new_text, re.MULTILINE)
    for num, title in headers:
        print(f'  Section {num}: {title}')
else:
    print('FAILED: Section not in output')
