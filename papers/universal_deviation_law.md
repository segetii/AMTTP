# Universal Deviation Law: A Multi-Spectrum Tensor Framework for Anomaly Detection

## Formal Theory Document — Research & Development Reference

---

## 1. Motivation and Origin

This work originates from the **Blind Spot Decomposition Theory (BSDT)**, which decomposes model failure into four orthogonal components:

| Component | Symbol | Meaning |
|-----------|--------|---------|
| Camouflage | C | Fraud looks normal — hides in dense normal regions |
| Feature Gap | G | Insufficient signal — sparse or zero-valued features |
| Activity Anomaly | A | Unusual transaction volumes relative to known fraud |
| Temporal Novelty | T | New patterns not seen in training distribution |

BSDT demonstrated **cross-domain generalisation** across Credit Card Fraud, Shuttle, Mammography, Pendigits, Ethereum, and Elliptic datasets. A post-model correction formula (MFLS) consistently improved AUC — in some cases from ~0.2 to ~0.8 — **without retraining**, by amplifying latent residual structure in model outputs.

This success raised a deeper question:

> **Why does a domain-agnostic post-model transform consistently reveal hidden separability across unrelated domains?**

The answer leads to a **Universal Deviation Law** — the hypothesis that anomalies are structured disturbances across multiple fundamental law domains, and that detection requires multi-spectrum representation, not single-metric thresholding.

---

## 2. Foundational Concepts

### 2.1 Observation as Process Realisation

An observation row $\mathbf{x}_i \in \mathbb{R}^m$ is NOT a static feature vector.

It is a **realisation of an underlying generative process**. We treat it as a discrete signal:

$$f_i(t_j) = x_{ij}, \quad j = 1, \ldots, m$$

where $t_j$ is pseudo-time (column index or ordered feature dimension).

### 2.2 Multi-Law Deviation Domains

Any observable system can deviate from expected behaviour in multiple **fundamental law domains**:

| Law Domain | What It Captures | Mathematical Tool |
|------------|-----------------|-------------------|
| **Probabilistic** | Distribution shape mismatch | KL divergence, Hellinger distance, entropy |
| **Dynamical/Chaos** | Evolution instability, sensitivity to initial conditions | Lyapunov exponents, phase space divergence |
| **Spectral** | Hidden periodicity, frequency structure | Fourier/wavelet transforms, power spectrum |
| **Geometric** | Shape of deviation in feature manifold | Mahalanobis distance, geodesic distance |
| **Information-Theoretic** | Surprise, knowledge gap | Shannon entropy, mutual information |

### 2.3 Key Insight

> A mimic or subtle anomaly may appear normal in ANY SINGLE law domain, but cannot simultaneously appear normal across ALL law domains.

This is the **Universal Deviation Principle**.

---

## 3. The Three Approaches

### Approach 1: Wave → Laws → Surprise → Geometry (Original)

```
Raw Row → Waveform → Apply Each Law → Bits of Surprise → Anomaly Vector
```

- Convert row to signal $f_i(t)$
- Evaluate deviation under each law domain
- Convert to common surprise units (bits)
- Combine into anomaly vector $\vec{\mathcal{A}}_i$

### Approach 2: Multi-Spectrum Simultaneous Projection

```
Raw Row → Project into ALL spectrum spaces simultaneously → Unified Representation
```

- Define spectrum projection operators $\Phi_{\text{stat}}$, $\Phi_{\text{freq}}$, $\Phi_{\text{chaos}}$, $\Phi_{\text{geom}}$
- Apply all operators to raw observation
- Stack results into unified representation $\mathcal{R}(\mathbf{x}) = [\Phi_{\text{stat}}(\mathbf{x}), \Phi_{\text{freq}}(\mathbf{x}), \Phi_{\text{chaos}}(\mathbf{x}), \Phi_{\text{geom}}(\mathbf{x})]$

### Approach 3: Multi-Spectrum → Tensor → Hyperplane Projection

```
Raw Row → Representation Stack (including exponential) → Tensor → Hyperplane Projection → Class Separation
```

**This is the full framework:**

1. **Representation Stack**: Each row is represented across multiple spectra, with exponential amplification as one layer
2. **Tensor Construction**: Stack all representations into a unified tensor object
3. **Centroid Estimation**: Compute reference equilibrium in representation space
4. **Hyperplane Projection**: Project deviation tensors onto separation subspace
5. **Geometric Classification**: Anomaly classes become spatially separable

---

## 4. Mathematical Formulation

### 4.1 Representation Stack

Let raw observation be $\mathbf{x} \in \mathbb{R}^n$. Define **spectrum projection operators**:

$$\Phi_{\text{stat}}(\mathbf{x}) \in \mathbb{R}^{d_1}$$
$$\Phi_{\text{chaos}}(\mathbf{x}) \in \mathbb{R}^{d_2}$$
$$\Phi_{\text{freq}}(\mathbf{x}) \in \mathbb{R}^{d_3}$$
$$\Phi_{\text{geom}}(\mathbf{x}) \in \mathbb{R}^{d_4}$$
$$\Phi_{\text{exp}}(\mathbf{x}) = \exp(\alpha \cdot \mathbf{x}) \in \mathbb{R}^{d_5}$$

The **unified representation** is:

$$\mathcal{R}(\mathbf{x}) = \left[\Phi_{\text{stat}}(\mathbf{x}),\ \Phi_{\text{chaos}}(\mathbf{x}),\ \Phi_{\text{freq}}(\mathbf{x}),\ \Phi_{\text{geom}}(\mathbf{x}),\ \Phi_{\text{exp}}(\mathbf{x})\right]$$

### 4.2 Tensor Formulation

For $N$ observations, $K$ law domains, and optional dimensions (time $T$, context $D$):

$$\mathcal{T}_{i,k,t,d} = \text{Law-domain } k \text{ representation of observation } i \text{ at time } t \text{ in context } d$$

### 4.3 Reference Centroid (Equilibrium State)

The centroid is the **expected law-space equilibrium point** of normal behaviour:

$$\boldsymbol{\mu}_{\text{ref}} = \frac{1}{|\mathcal{N}|} \sum_{i \in \mathcal{N}} \mathcal{R}(\mathbf{x}_i)$$

Or in robust form (geometric median):

$$\boldsymbol{\mu}_{\text{ref}} = \arg\min_{\boldsymbol{\mu}} \sum_{i \in \mathcal{N}} \|\mathcal{R}(\mathbf{x}_i) - \boldsymbol{\mu}\|$$

### 4.4 Deviation Vector

$$\mathbf{D}_i = \mathcal{R}(\mathbf{x}_i) - \boldsymbol{\mu}_{\text{ref}}$$

### 4.5 Magnitude, Direction, and Novelty

**Magnitude** (how anomalous):
$$r_i = \|\mathbf{D}_i\| = \sqrt{\sum_k D_{ik}^2}$$

**Direction** (what type of anomaly):
$$\hat{\mathbf{D}}_i = \frac{\mathbf{D}_i}{r_i}$$

**Angular deviation from normal direction** (how novel):
$$\theta_i = \arccos\left(\frac{\mathbf{D}_i \cdot \boldsymbol{\mu}_{\text{normal}}}{|\mathbf{D}_i| \cdot |\boldsymbol{\mu}_{\text{normal}}|}\right)$$

### 4.6 Hyperplane Projection

Let $\mathbf{w}$ be the dominant separation direction (e.g., first principal component of labelled deviations, or Fisher discriminant direction):

$$\text{Score}_i = (\mathbf{D}_i) \cdot \mathbf{w}$$

Classes separate along $\mathbf{w}$ in the projected space.

### 4.7 Decomposition Theorem

Any deviation vector can be decomposed into expected and novel components:

$$\mathbf{D}_i = \underbrace{\text{proj}_{\boldsymbol{\mu}} \mathbf{D}_i}_{\text{expected deviation}} + \underbrace{\mathbf{D}_i - \text{proj}_{\boldsymbol{\mu}} \mathbf{D}_i}_{\text{novel deviation}}$$

The **perpendicular component** is the truly novel, unexpected part — this is what catches mimics that evade marginal detection.

---

## 5. Unified Action Functional

Define the **observation action integral**:

$$A_i = \sum_{j=1}^{m} \exp\left(\underbrace{-\sum_j p_i(j) \log p_i(j)}_{\text{Entropy}} + \underbrace{\lambda_i}_{\text{Chaos}} + \underbrace{E_{\text{freq}}}_{\text{Frequency}} + \underbrace{d_M}_{\text{Geometry}}\right)$$

**Interpretation**: Observations with high $A_i$ deviate strongly from reference across all mathematical domains.

### 5.1 Physics Analogy

| Physics | Observation Framework |
|---------|----------------------|
| Position / Momentum | Observation vector / Fourier coefficients |
| Energy / Potential | Entropy / Divergence / Spectral energy |
| Action | Integrated exponential divergence ($A_i$) |
| Phase space | Probability manifold |
| Chaotic sensitivity | Lyapunov exponent $\lambda_i$ |

---

## 6. Centroid Determination Methods

| Method | When to Use | Formula |
|--------|------------|---------|
| Simple Mean | Clean normal data, prototype stage | $\boldsymbol{\mu} = \frac{1}{N}\sum \mathcal{R}(\mathbf{x}_i)$ |
| Geometric Median | Noisy data, outlier-resistant | $\boldsymbol{\mu} = \arg\min \sum \|\mathcal{R}(\mathbf{x}_i) - \boldsymbol{\mu}\|$ |
| Law-Weighted | Theory-driven importance | $\boldsymbol{\mu} = \sum w_k \mathbb{E}[\mathcal{R}_k]$ |
| Energy Minimum | Physics-consistent equilibrium | $\boldsymbol{\mu}^* = \arg\min \sum \|\mathcal{R}(\mathbf{x}_i) - \boldsymbol{\mu}\|^2$ |
| Density Peak | Cyber environments | $\boldsymbol{\mu} = \arg\max P(\mathcal{R})$ |
| Multi-Regime | Complex systems with multiple normal states | $\boldsymbol{\mu}_1, \boldsymbol{\mu}_2, \ldots$ per regime |
| Manifold | Advanced / research level | Projection onto normal behaviour surface |

---

## 7. Conditions for Mathematical Rigor

To prove the axiom is valid (not just a wish):

1. **Well-defined spaces**: $\mathbb{R}^m$, Hilbert / manifold properly specified
2. **Normalized probability vectors**: $\sum_j p_i(j) = 1$
3. **Reference signal(s) defined**: Centroid or baseline established
4. **Action functional convergent and bounded**: All terms finite
5. **Interrelationships derivable**: Entropy ↔ Geometry ↔ Spectral ↔ Dynamics
6. **Limiting cases analyzed**: Identical → min action; Random → max action
7. **Numerical stability ensured**: ε-smoothing, log-sum-exp tricks
8. **Existence and uniqueness of $A_i$**: Provable for any valid observation
9. **Analytical derivations**: Show one law-domain reduces to another in limits
10. **Sufficient numerical data**: For empirical validation

---

## 8. Benchmark Datasets for Validation

### Time Series
- NAB (Numenta Anomaly Benchmark)
- Yahoo Webscope S5
- MIT-BIH ECG

### Network / Cybersecurity
- CICIDS 2017 / 2018
- UNSW-NB15
- NSL-KDD

### Industrial / Sensors
- NASA Bearing / Turbofan
- SECOM

### Chaotic Systems
- Lorenz Attractor
- Mackey-Glass Series

### Multivariate
- NASA SMAP / MSL
- UCR Time Series Archive

### Cross-Domain (Already Validated in BSDT)
- Credit Card Fraud
- Shuttle
- Mammography
- Pendigits
- Ethereum (Elliptic / XBlock)

---

## 9. Connection to BSDT

The Universal Deviation Law **extends** BSDT:

| BSDT | UDL |
|------|-----|
| 4 components (C, G, A, T) | K law-domain projection operators |
| Scalar MFLS correction score | Multi-dimensional anomaly vector/tensor |
| Post-model correction | Universal representation framework |
| Cross-domain validation (4 datasets) | Multi-spectrum + hyperplane separation |
| Near-orthogonal components | Full geometric decomposition (magnitude + direction + novelty) |

BSDT discovered that model failures are structured.
UDL formalizes **why** and provides the mathematical machinery to exploit that structure universally.

---

## 10. Research Roadmap

1. **Formalize representation operators**: Define $\Phi_k$ precisely for each law domain
2. **Implement Python library**: `udl` package with composable pipeline
3. **Validate centroid methods**: Compare on benchmark datasets
4. **Prove limiting cases**: Show action functional behaves correctly at boundaries
5. **Cross-domain benchmark suite**: Systematic evaluation table
6. **Tensor interaction analysis**: Which law-domain couplings matter most
7. **Publication**: Theory paper + benchmark results (IP-protected)
8. **Global Talent evidence**: Documented novelty, impact, and cross-domain results
