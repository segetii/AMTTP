"""Restructure the invariance analysis section in the .md paper.

New hierarchy:
  8.1 Notation
  8.2 Component-Level Invariances (Proposition 7) — unchanged
  8.3 MFLS Monotonicity and Safety (elevated from operator section)
  8.4 Operating Conditions (affine, label dependence, dimensionality table)
  8.5 Deployment Operators (SignedLR, QuadSurf, ExpGate — demoted to remark)
  8.6 Summary Table (restructured: components + MFLS core, operators secondary)
"""

path = r'c:\amttp\papers\blind_spot_decomposition_theory.md'

with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# Find the invariance section boundaries
start_marker = '## 8. Invariance Analysis'
end_marker = '## 9. Discussion'

start_idx = text.find(start_marker)
end_idx = text.find(end_marker)

if start_idx == -1:
    print('ERROR: Cannot find ## 8. Invariance Analysis')
    exit(1)
if end_idx == -1:
    print('ERROR: Cannot find ## 9. Discussion')
    exit(1)

# Find the --- separator before Discussion
pre_discussion = text[start_idx:end_idx]
last_hr = pre_discussion.rfind('---')
if last_hr != -1:
    section_end = start_idx + last_hr
else:
    section_end = end_idx

NEW_SECTION = r"""## 8. Invariance Analysis

We characterise the symmetry and equivariance properties of the four BSDT components and the core MFLS correction operator. Understanding which invariances hold (and which break) serves two purposes: **(i)** it identifies the preprocessing assumptions under which BSDT is valid, and **(ii)** it establishes that MFLS correction is provably safe ($\hat{p}^* \geq \hat{p}$). The analysis distinguishes the *core theory* (components + MFLS) from the *deployment-layer operators* (SignedLR, QuadSurf, ExpGate), which are application choices rather than part of the decomposition itself.

### 8.1 Notation

Let $x \in \mathbb{R}^d$ be a feature vector, $S(x) = [C(x), G(x), A(x), T(x)]$ the component vector, and $\hat{p}(x)$ the base model's fraud probability. We write $\hat{p}^*(x)$ for the corrected probability under a given operator. We analyse six core properties at the component level (scale, translation, permutation, affine equivariance, label dependence, dimensionality stability) and two algebraic properties of the MFLS score (monotonicity and correction safety).

### 8.2 Component-Level Invariances

**Proposition 7 (Component invariance profile).** Under the BSDT component definitions:

1. **Scale.** None of $C, G, A, T$ is scale-invariant. $G$ is approximately invariant for $|\alpha| \gg \epsilon$ (threshold effect) but collapses to 1 as $\alpha \to 0$.
2. **Translation.** No component is translation-invariant. $C$ depends on $\|x - \mu_\text{legit}\|$; $G$ depends on the absolute zero threshold; $A$ and $T$ depend on reference statistics.
3. **Permutation.** $G$ is permutation-invariant (it counts near-zero features regardless of position). $C$, $A$, and $T$ are not: $C$ depends on per-feature $\mu_\text{legit}$; $A$ accesses specific column indices; $T$ uses per-feature reference moments. This is by design --- the decomposition deliberately tracks *which* features are anomalous, not merely *how many*.
4. **Dimensionality ($d \to \infty$).** $T$ converges to $\sigma(-0.5) \approx 0.378$ under the null by the law of large numbers on normalised squared deviations (empirically: $\text{std}(T) < 0.011$ at $d = 1000$). $G$ converges to $P(|X_j| < \epsilon)$. $A$ is dimension-independent (uses 2 columns). $C$ drifts toward 0 as $d$ grows because Euclidean distances concentrate; this is mitigated by the 99th-percentile normalisation but not eliminated.

*Proof.* (i)--(iii): Direct from the formulae. For (i), $C(\alpha x) = 1 - \|\alpha x - \mu\|_2 / d_{\max} \neq C(x)$ unless $\alpha = 1$. For (iii), $G(\Pi x) = |\{j : |x_{\pi(j)}| < \epsilon\}|/d = |\{j : |x_j| < \epsilon\}|/d = G(x)$. (iv): For $T$, the normalised mean $\bar{m}(x) = d^{-1} \sum_j (x_j - \bar{x}_j^{\text{ref}})^2 / \text{Var}_j^{\text{ref}}$ converges a.s. by the SLLN when feature deviations are i.i.d. with finite second moment. Empirical verification on synthetic Gaussian data ($d \in \{10, 50, 93, 200, 500, 1000\}$) confirms convergence of $T$ and drift of $C$ (Table 3). $\square$

### 8.3 MFLS Monotonicity and Correction Safety

The MFLS composite score $\text{MFLS}(x) = \sum_i w_i S_i(x)$ is the central object of the decomposition theory. Two algebraic properties make it suitable as a correction signal:

**Proposition 8 (MFLS core properties).**

1. **Monotonicity.** MFLS is monotone-equivariant: if $S_i(x) \leq S_i(x')$ for all $i$, then $\text{MFLS}(x) \leq \text{MFLS}(x')$. This follows directly from $w_i \geq 0$ (all weighting schemes --- MI, Fisher VR, Bayesian, gradient --- produce non-negative weights). Monotonicity ensures that higher blind-spot evidence always produces a higher composite score, making the score interpretable as a *severity measure*. Empirical verification: 45 comparable pairs tested, 0 monotonicity violations.

2. **Correction safety.** The MFLS correction formula $\hat{p}^*_{\text{MFLS}} = \hat{p} + \lambda \cdot \text{MFLS} \cdot (1-\hat{p}) \cdot \mathbb{1}[\hat{p} < \tau]$ guarantees $\hat{p}^*(x) \geq \hat{p}(x)$ for all $x$. Since $\lambda \geq 0$, $\text{MFLS} \in [0,1]$, and $(1-\hat{p}) \geq 0$, the additive correction term is non-negative. This is a theorem, not an empirical observation: **MFLS correction can never reduce the probability of flagging fraud**.

*Proof.* (i): $w_i \geq 0$ for all four weighting schemes by construction (MI $= I(S_i; Y) \geq 0$; Fisher VR $= \text{Var}_{\text{between}} / \text{Var}_{\text{within}} \geq 0$; Bayesian posteriors are non-negative; gradient updates maintain $w_i \geq 0$ via projection). Thus $\text{MFLS}(x) = \sum_i w_i S_i(x)$ is a non-negatively weighted sum, and component-wise domination implies sum domination. (ii): Each factor in the correction term is non-negative: $\lambda \geq 0$ (scaling constant), $\text{MFLS}(x) \in [0,1]$ (bounded components and convex weights), $(1-\hat{p}(x)) \geq 0$ (probability bound), and the indicator $\mathbb{1}[\hat{p} < \tau] \in \{0, 1\}$. Therefore $\hat{p}^* - \hat{p} = \lambda \cdot \text{MFLS} \cdot (1-\hat{p}) \cdot \mathbb{1}[\hat{p} < \tau] \geq 0$. $\square$

**Significance.** These two properties distinguish MFLS from generic post-hoc correction methods. Calibration (Platt scaling, isotonic regression) can both increase and decrease predictions. MFLS is constrained to only *boost* predictions for samples with blind-spot evidence, ensuring it functions as a safety net rather than a general recalibration tool.

### 8.4 Operating Conditions

**Affine equivariance and the re-fitting requirement.** BSDT components are defined in the preprocessed feature space (sign-log + RobustScaler). Under an arbitrary affine transformation $x \mapsto Ax + b$ without re-fitting reference statistics, components change by a mean absolute deviation of up to 0.13 (Camouflage). When reference statistics are re-fit on the transformed data, the deviation drops substantially (to $<0.06$ for $C$, $<0.05$ for $A$, $<0.04$ for $T$; $G$ is exactly invariant).

**Corollary (Re-fitting requirement).** BSDT components are not affine-equivariant with fixed reference statistics. Domain adaptation requires re-fitting $\mu_\text{legit}$, $d_{\max}$, $\bar{x}^{\text{ref}}$, and $\text{Var}^{\text{ref}}$ on the target-domain train-fit split. Only $G$ is invariant without re-fitting. This is the formal justification for the 4-way split protocol used in Section 6.1.

**Label dependence.** Three of four components require labelled data for reference statistics ($C$: legitimate centroid, $A$: fraud activity stats, $T$: fraud reference distribution). Only $G$ (Feature Gap) is label-free. Among weighting schemes, Fisher Variance-Ratio weights are unsupervised (using model-output splits only), enabling a fully label-free path: $G + \text{VR weights} \to \text{MFLS}$. This is not a design accident --- it falls out of the invariance analysis as the unique fully unsupervised combination.

**Dimensionality stability.** Table 3 summarises the convergence behaviour. The key result is that $T$ is provably stable under the LLN as $d \to \infty$ (std drops from 0.083 at $d=10$ to 0.011 at $d=1000$), while $C$ suffers from Euclidean distance concentration (mean drifts from 0.720 to 0.325). For high-dimensional feature spaces ($d > 500$, e.g., transformer embeddings), $C$ should be computed in a reduced subspace or replaced with a cosine-distance variant.

**Table 3: Dimensionality sensitivity of BSDT components** (synthetic Gaussian, $n=1000$, 5% fraud rate).

| $d$ | $\bar{C} \pm \sigma$ | $\bar{G}$ | $\bar{T} \pm \sigma$ |
|-----|----------------------|------------|----------------------|
| 10 | $0.720 \pm 0.172$ | 0.000 | $0.416 \pm 0.083$ |
| 50 | $0.676 \pm 0.144$ | 0.000 | $0.413 \pm 0.034$ |
| 93 | $0.654 \pm 0.135$ | 0.000 | $0.417 \pm 0.026$ |
| 200 | $0.565 \pm 0.120$ | 0.000 | $0.421 \pm 0.019$ |
| 500 | $0.455 \pm 0.094$ | 0.000 | $0.419 \pm 0.014$ |
| 1000 | $0.325 \pm 0.064$ | 0.000 | $0.414 \pm 0.011$ |

### 8.5 Deployment Operators: Algebraic Properties

The deployment-layer operators (SignedLR, QuadSurf, ExpGate) are *application choices* for how to convert the MFLS diagnostic into a corrected probability. They are not part of the core decomposition theory but have distinct algebraic properties that guide operator selection.

**SignedLR** uses a logistic regression on the four components with a $\max(\hat{p}, p_{\text{SLR}})$ formulation. It is correction-safe by construction and idempotent ($\max(a, \max(a, b)) = \max(a, b)$), but *not* monotone: learned coefficients $\beta_i$ can be negative (empirically, $\beta_C = -1.92$, $\beta_T = -7.41$). The negative $\beta_C$ is the most practically important finding --- it means camouflage *reverses direction* in cross-domain transfer (a transaction that looks "camouflaged" in the source domain is less likely fraud in the target domain). This explains why naive MFLS (which treats $C$ as always positive evidence) has high FDR, while SignedLR learns to correct for it.

**QuadSurf and ExpGate** fit polynomial or gated residual surfaces. They are *bidirectional* corrections: $\hat{p}_{\text{quad}} = \text{clip}(\hat{p} + \boldsymbol{\beta}^\top \phi_2(S), 0, 1)$, where the residual $\boldsymbol{\beta}^\top \phi_2(S)$ is unconstrained in sign. Empirically, 73.2% of samples receive a *lower* corrected probability than the base model. This is not a defect --- it is the mechanism by which QuadSurf/ExpGate suppress false alarms, reducing FDR from 46.9% (SignedLR) to 36.0% (QuadSurf). They trade the safety guarantee ($\hat{p}^* \geq \hat{p}$) for expressiveness (bidirectional probability adjustment).

**Operator composition.** The chain is non-commutative: SignedLR targets classification, QuadSurf targets residual regression, and reversing their order changes the objective surface.

### 8.6 Invariance Summary

**Table 4: Invariance and algebraic properties.** The table is divided into core theory (components + MFLS, left) and deployment operators (right). Checkmark = holds; X = violated; ~ = approximately holds; --- = not applicable.

| Property | $C$ | $G$ | $A$ | $T$ | **MFLS** | | SLR | QS | EG |
|----------|-----|-----|-----|-----|----------|---|-----|----|----|
| Scale invariance | X | ~ | X | X | X | | X | X | X |
| Translation invariance | X | X | X | X | X | | X | X | X |
| Permutation invariance | X | Yes | X | X | X | | X | X | X |
| **Monotone equivariance** | --- | --- | --- | --- | **Yes** | | X | X | X |
| **Safety** ($\hat{p}^* \geq \hat{p}$) | --- | --- | --- | --- | **Yes** | | Yes | X | X |
| Label-free | X | Yes | X | X | VR | | X | X | X |
| Idempotent | --- | --- | --- | --- | X | | Yes | --- | --- |
| Dim-stable ($d \to \infty$) | X* | Yes | Yes | Yes | Yes | | Yes | X** | X** |

*$C$ drifts toward 0 due to distance concentration. **Polynomial feature count grows as $O(d^2)$.

The central result is that MFLS --- the core contribution of this paper --- satisfies both monotonicity and correction safety, properties that no deployment-layer operator fully preserves. SignedLR preserves safety but sacrifices monotonicity to gain expressiveness. QuadSurf/ExpGate sacrifice both but gain bidirectional correction capability, which is empirically valuable for FDR reduction. The choice of deployment operator is thus a *safety--expressiveness trade-off* that is orthogonal to the validity of the underlying decomposition.

"""

new_text = text[:start_idx] + NEW_SECTION + '\n---\n\n' + text[end_idx:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_text)

# Verify
if 'MFLS Monotonicity and Correction Safety' in new_text and 'Deployment Operators' in new_text:
    print('SUCCESS: .md invariance section restructured')
    import re
    headers = re.findall(r'^(#{2,3})\s+(\d+[\.\d]*)\.\s+(.+)', new_text, re.MULTILINE)
    for level, num, title in headers:
        if num.startswith('8') or num.startswith('9'):
            prefix = '  ' if len(level)==3 else ''
            print(f'{prefix}{num}. {title}')
    print(f'Total lines: {len(new_text.splitlines())}')
else:
    print('FAILED')
