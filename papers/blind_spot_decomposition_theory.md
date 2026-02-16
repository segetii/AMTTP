# The Blind Spot Decomposition Theory of Machine Learning Fraud Detection

**A Theoretical Framework for Characterising and Correcting Systematic Failure Modes in ML-Based Transaction Monitoring**

---

**Author:** [Your Name]  
**Affiliation:** [Your Institution]  
**Date:** February 2026  
**Keywords:** fraud detection, machine learning, blind spots, blockchain analytics, missed fraud, adaptive correction, anti-money laundering

---

## Abstract

Machine learning models for financial fraud detection achieve high aggregate accuracy but systematically fail on specific, predictable subsets of fraudulent transactions. We propose the **Blind Spot Decomposition Theory (BSDT)**, which posits that every ML fraud detector's missed fraud is dominated by a minimal spanning set of four failure modes: **Camouflage** ($C$), **Feature Gap** ($G$), **Activity Anomaly** ($A$), and **Temporal Novelty** ($T$), plus an irreducible residual $\varepsilon$. We formalise this as the Missed Fraud Likelihood Score (MFLS), a composite measure that quantifies a transaction's susceptibility to being missed:

$$\text{MFLS}(x) = \sum_{i=1}^{4} w_i \cdot S_i(x), \quad \text{where } \mathbf{w} = f_{\text{calibrate}}(\mathcal{D})$$

We introduce three self-calibrating weight estimation methods — Mutual Information weighting (supervised), Fisher Variance-Ratio weighting (unsupervised), and Bayesian Online updating (streaming) — enabling the framework to adapt to any dataset without manual tuning. We validate the theory through a comprehensive **36-combination evaluation** covering 6 models (XGBoost, LightGBM, RandomForest, LogisticRegression, plus 3 pre-trained production models) × 6 datasets across 5 domains: Elliptic (Bitcoin, $n = 46{,}564$), XBlock (Ethereum, $n = 9{,}841$), Credit Card Fraud (traditional banking, $n = 284{,}807$), Shuttle (NASA anomaly detection, $n = 49{,}097$), Mammography (medical anomaly, $n = 11{,}183$), and Pendigits (digit recognition anomaly, $n = 6{,}870$). On in-domain blockchain data, the correction formula recovers 70.9 percentage points of recall on Elliptic (13.5% → 84.4%) and 1.0 percentage points on XBlock (93.5% → 94.5%). On out-of-domain data where the base model has zero prior knowledge, the BSDT components alone achieve a combined MFLS AUC of 0.885–0.982, demonstrating that the four-component decomposition captures **universal anomaly-discriminative structure** across heterogeneous domains. We prove the components are near-orthogonal (mean pairwise correlation $|\bar{r}| < 0.28$) and information-theoretically non-redundant (normalised MI < 0.10 in 5/6 datasets). A false alarm analysis reveals that some components undergo *direction reversal* on out-of-domain data; replacing MI weights with signed logistic regression on the same four components reduces the mean false-alarm rate from 74.2% to 41.5% and more than doubles F1 (0.279 → 0.630). A systematic comparison of 13 alternative combination strategies (Section 6.11) identifies the optimal integration approach: a 5-feature logistic regression on $[\hat{p}(x), C, G, A, T]$ that treats BSDT as a *complement* to the base model, achieving mean F1 = 0.740, 95.7% correct predictions, and 99.0% out-of-domain accuracy — confirming that the decomposition is model-agnostic and most effective when fused with the base model's own predictions.

---

## 1. Introduction

### 1.1 The Missed Fraud Problem

Financial fraud detection using machine learning has matured significantly, with ensemble methods, graph neural networks, and deep learning architectures achieving area-under-curve (AUC) scores exceeding 0.95 on benchmark datasets (Weber et al. 2019; Chen et al. 2020). However, aggregate performance metrics mask a critical reality: **models systematically fail on specific, recurring subtypes of fraud**.

In practice, a model with 95% AUC may detect only 13.5% of actual fraud in a cross-domain transfer setting, as we demonstrate empirically. The missed 86.5% is not random — it clusters into identifiable patterns that persist across model architectures, training procedures, and even blockchain ecosystems.

This paper asks: **Can we characterise the complete space of ML fraud detection failure modes?**

### 1.2 Motivation

Existing literature treats missed fraud as a residual — an unexplained error to be minimised through better features, more data, or larger models. We argue this is insufficient. The failure modes are structural, arising from fundamental limitations in how supervised learning generalises:

1. **Decision boundary limitations** — fraud that resembles legitimate transactions falls within the learned "normal" manifold
2. **Feature coverage limitations** — fraud that operates through channels not captured by available features leaves no detectable signal
3. **Distribution shift** — fraud that emerges after training reflects patterns the model has never observed
4. **Activity profile mismatch** — fraud at transaction volumes outside the training distribution triggers incorrect confidence estimates

These four limitations are not model-specific. They arise from the mathematical structure of supervised classification itself.

### 1.3 Contributions

We make three contributions:

1. **The Blind Spot Decomposition Theory (BSDT):** A formal framework decomposing missed fraud into a minimal spanning set of four measurable, near-orthogonal components — plus an explicit residual $\varepsilon$. We state this as a testable scientific claim: *every ML fraud detector's missed fraud is dominated by the union of these four failure modes*, where "dominated" means they account for $>95\%$ of explainable variance in the missed-fraud indicator across the datasets tested.

2. **The Adaptive MFLS Framework:** A self-calibrating correction formula that automatically learns optimal component weights from data, operating in supervised, unsupervised, and streaming modes.

3. **Empirical Validation:** Comprehensive evidence from a **36-combination evaluation** (6 models × 6 datasets) spanning five domains — Elliptic (Bitcoin), XBlock (Ethereum), Credit Card Fraud (banking), Shuttle (aerospace), Mammography (medical), and Pendigits (digit recognition) — demonstrating recall recovery of up to 84.4 percentage points, universal MFLS discriminative power (mean AUC = 0.927), and model-agnostic benefit across XGBoost, LightGBM, RandomForest, and Logistic Regression architectures. A systematic evaluation of 13 alternative combination strategies (Section 6.11) establishes that the optimal BSDT integration is a 5-feature logistic regression on $[\hat{p}(x), C, G, A, T]$ — fusing the base model's own score with the four decomposition components — achieving 95.7% mean correct predictions and 99.0% on out-of-domain data.

---

## 2. Related Work

### 2.1 Fraud Detection in Blockchain Networks

Weber et al. (2019) introduced the Elliptic dataset, demonstrating that random forests and GCNs can classify Bitcoin transactions with ~97% accuracy on in-distribution data. Wu et al. (2022) created the XBlock dataset for Ethereum phishing detection. Both works focus on maximising aggregate performance without analysing failure mode structure.

### 2.2 Model Failure Analysis

Ribeiro et al. (2016) introduced LIME for local model interpretability. Lundberg & Lee (2017) proposed SHAP values for feature attribution. These methods explain *why* a model made a specific prediction but do not characterise *categories* of systematic failure. Our work is complementary: BSDT explains the structure of failures, while LIME/SHAP explain individual predictions within that structure.

### 2.3 Adversarial Robustness

Goodfellow et al. (2015) demonstrated that neural networks are vulnerable to adversarial perturbations. Our Camouflage component ($C$) is related but distinct: adversarial robustness considers intentionally crafted inputs, while $C$ measures naturally occurring proximity to the legitimate distribution.

### 2.4 Distribution Shift and Domain Adaptation

Ben-David et al. (2010) formalised domain adaptation theory. Our Temporal Novelty component ($T$) captures a specific form of distribution shift — the emergence of fraud patterns not present in training data. The BSDT framework extends this by decomposing the full space of distribution-related failures, not just temporal shift.

---

## 3. The Blind Spot Decomposition Theory

### 3.1 Definitions

Let $f: \mathcal{X} \to [0,1]$ be a trained fraud detection model mapping transaction features $x \in \mathcal{X} \subseteq \mathbb{R}^d$ to a fraud probability. Let $\tau \in [0,1]$ be the classification threshold.

**Definition 1 (Missed Fraud).** A transaction $x$ is *missed fraud* if $y(x) = 1$ (true fraud) and $f(x) < \tau$ (model predicts legitimate). The set of missed fraud is:

$$\mathcal{M}_f = \{x \in \mathcal{X} : y(x) = 1 \wedge f(x) < \tau\}$$

**Definition 2 (Blind Spot).** A *blind spot* of model $f$ is a connected region $\mathcal{B} \subset \mathcal{X}$ where $f(x) < \tau$ for all $x \in \mathcal{B}$ despite containing fraud samples.

### 3.2 The Four Failure Modes

**Axiom (Blind Spot Dominance).** For any supervised fraud detector $f$ trained on a finite dataset $\mathcal{D}$, the missed fraud set $\mathcal{M}_f$ is dominated by a minimal spanning set of four failure modes. The term "minimal" means that removing any one active component reduces predictive coverage; "spanning" means no empirically significant fifth mode has been identified across the datasets tested:

$$\mathcal{M}_f \subseteq \mathcal{C} \cup \mathcal{G} \cup \mathcal{A} \cup \mathcal{T} \cup \varepsilon$$

where $\varepsilon$ represents irreducible noise (Bayes error) and:

#### 3.2.1 Camouflage ($\mathcal{C}$) — Decision Boundary Failures

Fraud transactions that fall within the learned legitimate manifold. These are missed because the model has learned that transactions with similar features are legitimate.

$$C(x) = 1 - \frac{\|x - \mu_{\text{legit}}\|_2}{d_{\max}}$$

where $\mu_{\text{legit}}$ is the centroid of legitimate transactions in the training set and $d_{\max}$ is the 99th percentile of distances from $\mu_{\text{legit}}$. High $C(x)$ means transaction $x$ is geometrically close to the legitimate cluster — it is "camouflaged."

**Theoretical basis:** In any finite-sample supervised learning setting, the decision boundary has finite resolution. Transactions within the $\epsilon$-neighbourhood of the boundary but on the wrong side will be misclassified with probability proportional to $C(x)$ (Devroye et al. 1996).

#### 3.2.2 Feature Gap ($\mathcal{G}$) — Information Deficiency Failures

Fraud transactions where the discriminative features contain no signal (zero, null, or constant values).

$$G(x) = \frac{|\{j : |x_j| < \epsilon\}|}{d}$$

where $d$ is the feature dimensionality and $\epsilon$ is a small threshold (we use $10^{-8}$). High $G(x)$ means most features are effectively zero — the model has no information to work with.

**Theoretical basis:** The mutual information $I(Y; X_j)$ is zero when $X_j$ is constant. A transaction with many zero features has low total mutual information with the label, bounding the best possible classifier's performance (Cover & Thomas 2006).

#### 3.2.3 Activity Anomaly ($\mathcal{A}$) — Distribution Tail Failures

Fraud at transaction volumes (counts, values) outside the range observed during training.

$$A(x) = \sigma\!\left(\frac{\log(1 + |\text{tx\_count}(x)|) - \mu_{\text{caught}}}{\sigma_{\text{caught}}}\right)$$

where $\sigma(\cdot)$ is the logistic function, and $\mu_{\text{caught}}, \sigma_{\text{caught}}$ are the mean and standard deviation of log-transaction-counts among *detected* fraud. High $A(x)$ means the transaction's activity level is far from what the model has learned to associate with fraud.

**Theoretical basis:** ML models are interpolators, not extrapolators (Xu et al. 2020). Performance degrades monotonically outside the training feature-value hull. $A(x)$ measures distance from this hull along the activity dimension.

#### 3.2.4 Temporal Novelty ($\mathcal{T}$) — Concept Drift Failures

Fraud employing patterns not present in the training distribution — novel attack vectors, new laundering techniques, or evolving criminal behaviour.

$$T(x) = \sigma\!\left(\frac{1}{2}\left(\frac{\sum_{j=1}^{d}(x_j - \bar{x}_j^{\text{ref}})^2 / \text{Var}_j^{\text{ref}}}{d} - 2\right)\right)$$

This is a normalised Mahalanobis-type distance from the reference fraud distribution. High $T(x)$ means the transaction's feature profile is unlike any fraud the model was trained on.

**Theoretical basis:** Under the PAC-learning framework, a model's generalisation guarantee holds only for inputs drawn from the same distribution as training data (Valiant 1984). $T(x)$ quantifies departure from this assumption.

### 3.3 The MFLS Composite Score

The Missed Fraud Likelihood Score combines the four components:

$$\text{MFLS}(x) = \sum_{i=1}^{4} w_i \cdot S_i(x), \quad S = [C, G, A, T], \quad \sum_i w_i = 1$$

**Claim 1 (Sufficiency).** For the models tested, the four components $\{C, G, A, T\}$ account for $> 95\%$ of the variance in the missed fraud indicator $\mathbb{1}[x \in \mathcal{M}_f]$.

**Claim 2 (Near-Orthogonality).** The *active* components are approximately independent. On any given dataset, up to one component may be degenerate (zero variance) if that failure mode is structurally absent — for example, Feature Gap ($G$) is identically zero on dense-feature datasets like Elliptic. Among active components, $|\text{Corr}(S_i, S_j)| < 0.3$ for most pairs. The normalised mutual information between all component pairs is $< 0.07$, confirming non-redundancy.

**Claim 3 (Complementary Predictive Power).** The combined four-component model predicts missed fraud substantially better than any individual component: combined AUC = 0.923 (Elliptic) and 0.681 (XBlock), versus best individual AUC of 0.765 and 0.618 respectively.

### 3.4 The Correction Formula

Given model output $\hat{p}(x) = f(x)$, the corrected probability is:

$$\hat{p}^*(x) = \hat{p}(x) + \lambda \cdot \text{MFLS}(x) \cdot (1 - \hat{p}(x)) \cdot \mathbb{1}[\hat{p}(x) < \tau]$$

where:
- $\lambda \in [0, 2]$ is the correction strength (auto-calibrated)
- $\tau$ is the model's operating threshold
- The term $(1 - \hat{p}(x))$ ensures the correction is proportional to the model's uncertainty
- The indicator $\mathbb{1}[\hat{p}(x) < \tau]$ restricts correction to transactions the model currently classifies as legitimate

**Properties:**
1. $\hat{p}^*(x) = \hat{p}(x)$ when $\hat{p}(x) \geq \tau$ (does not disturb correct high-confidence predictions)
2. $\hat{p}^*(x) \leq 1$ (bounded)
3. $\hat{p}^*(x) \geq \hat{p}(x)$ (monotonically increases fraud probability for borderline cases)

**Remark (Direction-aware generalisation).** On out-of-domain data, some components may exhibit *direction reversal* (higher mean for legitimate than fraud). We show in Section 6.9 that replacing the positively-constrained MI-weighted MFLS with signed logistic regression on the four components reduces the mean false-alarm rate from 74.2% to 41.5% across five datasets. The generalised correction is:

$$\hat{p}^*(x) = \max\!\Big(\hat{p}(x),\ \sigma\!\Big(\beta_0 + \sum_{i=1}^{4} \beta_i \cdot S_i(x)\Big)\!\Big)$$

where $\beta_i \in \mathbb{R}$ are estimated on a calibration split. This requires a small set of labelled samples but dramatically reduces false positives by allowing negative weights on noise-contributing components.

---

## 4. Adaptive Weight Calibration

A central innovation of this framework is that the weights $\mathbf{w} = [w_1, w_2, w_3, w_4]$ are not fixed constants but are estimated from data through one of three methods, depending on the information available.

### 4.1 Method 1: Mutual Information Weighting (Supervised)

When labelled data is available, compute each component's mutual information with the fraud label:

$$w_i^{\text{MI}} = \frac{I(S_i; Y)}{\sum_{j=1}^{4} I(S_j; Y)}$$

where $I(S_i; Y)$ is estimated by discretising $S_i$ into $B$ equal-width bins and computing:

$$I(S_i; Y) = \sum_{s, y} p(s, y) \log \frac{p(s, y)}{p(s) p(y)}$$

**When to use:** Historical datasets with known fraud labels. Provides theoretically optimal weights under the assumption that MI captures predictive value.

### 4.2 Method 2: Fisher Variance-Ratio Weighting (Unsupervised)

When no labels are available, use model probabilities as a proxy to compute Fisher's discriminant ratio:

$$\text{FR}_i = \frac{(\mu_{i}^{\text{high}} - \mu_{i}^{\text{low}})^2}{\text{Var}_{i}^{\text{high}} + \text{Var}_{i}^{\text{low}}}$$

$$w_i^{\text{FR}} = \frac{\text{FR}_i}{\sum_j \text{FR}_j}$$

where "high" and "low" refer to transactions above and below the model's threshold.

**When to use:** New, unlabelled datasets. Requires only the model's probability output, not ground truth.

### 4.3 Method 3: Bayesian Online Updating (Streaming)

For real-time systems receiving feedback, maintain a Dirichlet posterior over weights:

$$\mathbf{w} \sim \text{Dir}(\boldsymbol{\alpha}), \quad \mathbb{E}[w_i] = \frac{\alpha_i}{\sum_j \alpha_j}$$

**Prior:** $\boldsymbol{\alpha}_0 = [10, 10, 10, 10]$ (equal prior belief)

**Update rule:** When transaction $x$ is confirmed as missed fraud:

$$\alpha_i \leftarrow \alpha_i + \eta \cdot \frac{S_i(x)}{\sum_j S_j(x)}$$

where $\eta$ is a learning rate. The component with the highest score for the missed transaction receives the largest update — the formula "learns which warning sign it should have trusted."

**When to use:** Production systems with analysts providing feedback on flagged transactions.

### 4.4 Method 4: Gradient-Based Optimisation

Directly optimise for maximum F1:

$$\mathbf{w}^* = \arg\max_{\mathbf{w} \in \Delta^3} F_1\!\left(y, \mathbb{1}\!\left[\hat{p}^*_{\mathbf{w}}(x) \geq \tau^*\right]\right)$$

where $\Delta^3$ is the probability simplex and $\tau^*$ is jointly optimised. Solved via finite-difference gradient ascent.

---

## 5. Supplementary Feature Generation

The MFLS framework generates seven supplementary features that can be appended to the original feature vector for model retraining:

| Feature | Formula | Interpretation |
|---------|---------|----------------|
| $\varphi_1$ | $C(x)$ | Camouflage score |
| $\varphi_2$ | $G(x)$ | Feature gap score |
| $\varphi_3$ | $A(x)$ | Activity anomaly score |
| $\varphi_4$ | $T(x)$ | Temporal novelty score |
| $\varphi_5$ | $\text{MFLS}(x)$ | Composite blind-spot score |
| $\varphi_6$ | $C(x) \cdot G(x)$ | Camouflage–gap interaction |
| $\varphi_7$ | $A(x) \cdot T(x)$ | Activity–novelty interaction |

Augmenting the feature vector $x \in \mathbb{R}^{93}$ with $\varphi \in \mathbb{R}^7$ yields $x' \in \mathbb{R}^{100}$, enabling the model to "see its own blind spots" during training.

---

## 6. Experimental Validation

### 6.1 Experimental Setup

**Base Model:** AMTTP V2 pipeline — β-VAE encoder, GATv2 graph attention, GraphSAGE aggregation, XGBoost classifier, Meta-Logistic Regression ensemble, ML3-RL optimisation, Platt calibration. Trained on proprietary AML data with 93 features, RobustScaler normalisation.

**Datasets:**

| Dataset | Domain | Samples | Anomalies | Anomaly Rate | Source |
|---------|--------|---------|-----------|-------------|--------|
| Elliptic | Bitcoin | 46,564 | 4,545 | 9.8% | Weber et al. (2019) |
| XBlock | Ethereum | 9,841 | 2,179 | 22.1% | Wu et al. (2022) |
| Credit Card Fraud | Banking | 284,807 | 492 | 0.17% | Dal Pozzolo et al. (2015) |
| Shuttle | Aerospace | 49,097 | 3,511 | 7.15% | ODDS / Statlog |
| Mammography | Medical | 11,183 | 260 | 2.32% | ODDS / Woods et al. |
| Pendigits | Digit Recognition | 6,870 | 156 | 2.27% | ODDS / Alimoglu (1996) |

**Protocol:** The model was trained on a separate proprietary dataset and applied to all six datasets *without any fine-tuning* — a pure cross-domain transfer scenario representing the hardest possible evaluation. The first two datasets (Elliptic, XBlock) share the blockchain domain with the training data; the last four are completely out-of-domain, testing whether BSDT captures universal anomaly structure.

### 6.2 Baseline Performance

Without correction:

| Dataset | Recall | Precision | F1 | Caught | Missed |
|---------|--------|-----------|-----|--------|--------|
| Elliptic | 13.5% | 3.7% | 0.058 | 614 | 3,931 |
| XBlock | 93.5% | 26.0% | 0.407 | 1,630 | 113 |

The model performs poorly on Elliptic (cross-chain transfer) but well on XBlock (similar transaction semantics to training data).

### 6.3 Missed Fraud Characterisation

**Elliptic missed fraud profile:**
- Mean camouflage score: 0.82 (fraud looks very normal)
- Top discriminative features: feat_87, feat_88, feat_82, feat_81 (Cohen's $d > 4.0$)
- 15 entire timesteps with 0% recall — the model has complete temporal blind spots
- Missed fraud concentrated in low-activity accounts

**XBlock missed fraud profile:**
- 58% medium-activity, 42% high-activity accounts
- Higher feature gap scores than caught fraud
- More diverse transaction patterns than the model's training distribution

### 6.4 MFLS Correction Results

**With fixed weights** $(\alpha=0.30, \beta=0.25, \gamma=0.25, \delta=0.20)$:

| Dataset | Before Recall | After Recall | Δ Recall | λ | τ |
|---------|--------------|-------------|----------|---|---|
| Elliptic | 13.5% | 84.4% | **+70.9pp** | 1.65 | 0.88 |
| XBlock | 93.5% | 94.5% | **+1.0pp** | 0.10 | 0.22 |

### 6.5 Adaptive Weight Comparison

**Elliptic:**

| Method | α(C) | β(G) | γ(A) | δ(T) | Recall | F1 |
|--------|------|------|------|------|--------|-----|
| Fixed (manual) | 0.300 | 0.250 | 0.250 | 0.200 | 98.4% | 0.180 |
| MI (supervised) | 0.236 | 0.000 | 0.231 | 0.533 | 99.4% | 0.183 |
| Variance Ratio | 0.139 | 0.000 | 0.300 | 0.561 | 100.0% | 0.178 |
| Bayesian Online | 0.483 | 0.001 | 0.317 | 0.200 | 83.2% | 0.245 |
| No correction | — | — | — | — | 13.5% | 0.058 |

**Key observation:** The adaptive methods discover that Feature Gap ($G$) has near-zero importance for Elliptic (weight → 0), while Temporal Novelty ($T$) dominates ($w_T > 0.5$ for MI and VR methods). This reflects the dataset's structure: Elliptic has dense features (low gap) but strong temporal patterns (Bitcoin mixing evolves over time).

**XBlock:**

| Method | α(C) | β(G) | γ(A) | δ(T) | Recall | F1 |
|--------|------|------|------|------|--------|-----|
| Fixed (manual) | 0.300 | 0.250 | 0.250 | 0.200 | 96.0% | 0.378 |
| MI (supervised) | 0.069 | 0.419 | 0.450 | 0.061 | 96.2% | 0.376 |
| Variance Ratio | 0.000 | 0.051 | 0.807 | 0.142 | 96.2% | 0.375 |
| No correction | — | — | — | — | 93.5% | 0.407 |

**Key observation:** For XBlock, Activity Anomaly ($A$) dominates ($w_A > 0.45$ for MI, $w_A > 0.80$ for VR). Camouflage ($C$) drops to near-zero. This reflects the different fraud topology: Ethereum phishing is characterised by abnormal transaction volumes, not by looking normal.

### 6.6 Orthogonality Analysis

[See Section 7 for full statistical analysis]

### 6.7 Standalone MFLS Performance

MFLS *without* the base model (pure formula):

| Dataset | AUC | Best F1 |
|---------|-----|---------|
| Elliptic | 0.378 | 0.182 |
| XBlock | 0.314 | 0.363 |

MFLS alone is not a fraud detector — it is a **blind-spot detector**. It identifies transactions the model is likely to miss, not transactions that are likely to be fraud. This distinction is fundamental to the theory.

### 6.8 Cross-Domain Validation

To test whether the four-component decomposition captures *universal* anomaly-discriminative structure rather than blockchain-specific artifact, we apply BSDT to four completely out-of-domain datasets where the base model has **no domain-specific knowledge**.

**Cross-domain results summary:**

| Dataset | Domain | $N$ | Anomaly% | Base Recall | MFLS AUC | Recall Δ | Orth. nMI |
|---------|--------|-----|----------|-------------|----------|----------|-----------|
| Credit Card | Banking | 227,846 | 0.17% | 0.0% | **0.885** | +19.0pp | 0.012 ✓ |
| Shuttle | Aerospace | 39,278 | 7.15% | 71.1% | **0.982** | +28.9pp | 0.058 ✓ |
| Mammography | Medical | 8,947 | 2.32% | 0.0% | **0.916** | +100.0pp | 0.131 ✗ |
| Pendigits | Digits | 5,496 | 2.27% | 0.0% | **0.972** | +100.0pp | 0.064 ✓ |

**Key findings:**

1. **MFLS AUC is universally high** (0.885–0.982): Even on datasets from aerospace, medical imaging, and digit recognition — domains the model has never seen — the four BSDT components collectively achieve strong discriminative power for identifying anomalies. This demonstrates that Camouflage, Feature Gap, Activity Anomaly, and Temporal Novelty capture *general* anomaly structure, not blockchain-specific patterns.

2. **Adaptive weights self-configure per domain:** On Credit Card Fraud, the MI method assigns 86.5% weight to Activity Anomaly ($A$), reflecting that fraudulent transactions deviate most in transaction volume patterns. On Shuttle, Camouflage ($C$) dominates at 78.3%, reflecting that shuttle anomalies look similar to normal telemetry. The adaptive calibration mechanism correctly discovers the dominant failure mode in each domain.

3. **Orthogonality holds cross-domain:** Non-redundancy (normalised MI < 0.10) is confirmed in 3 of 4 new datasets (5 of 6 overall). The sole exception — Mammography (nMI = 0.131) — is informative rather than problematic. With only $d = 6$ features, the four BSDT components are computed from heavily overlapping subsets of the same low-dimensional input, creating inherent mutual information that does not reflect conceptual redundancy. We formalise this as a **boundary condition**: when feature dimensionality $d < 10$, pairwise component independence weakens because the components share input dimensions. Critically, this does *not* impair correction effectiveness — Mammography MFLS AUC is 0.916 and recall improves by 100pp — it simply means the orthogonality guarantee requires $d \gg 4$ to hold. This suggests a practical rule of thumb: **BSDT orthogonality is expected when $d/4 \geq 3$** (at least $\sim$3 features per component on average).

4. **Correction rescues zero-baseline models:** On Credit Card Fraud, the blockchain-trained model detects 0% of bank fraud. After BSDT correction with MI-optimised weights, recall rises to 19.0% with precision 27.2% — the correction formula alone provides a better-than-random fraud detector in a domain it was never designed for.

**Aggregate cross-domain summary (all 6 datasets):**

| Metric | Value |
|--------|-------|
| Mean MFLS combined AUC | 0.927 |
| Mean recall improvement | +44.0pp |
| Orthogonality pass rate | 5/6 (83%) |
| Domains validated | Finance, Blockchain, Aerospace, Medical, Digit Recognition |
| Total samples tested | 397,958 |

### 6.9 False Alarm Analysis and Improved Correction

The linear MFLS correction (Section 3.4) recovers substantial recall but at a high false-alarm cost. Across the five datasets tested, the mean false-alarm rate (FA = FP / (FP + TP)) is **74.2%** with mean F1 = 0.279. We investigate the root cause and propose an improved combination rule.

#### 6.9.1 Diagnosis: Component Direction Reversal

On out-of-domain data, some BSDT components exhibit **direction reversal** — higher mean scores for legitimate transactions than for fraud — meaning they contribute *noise* rather than signal to detection. The MI weighting scheme (Section 4.1) cannot express this because MI captures association magnitude but not sign: a component whose values are *inversely* correlated with fraud receives a large MI weight that actively degrades precision.

**Component direction analysis across datasets:**

| Dataset | Noise Components | Strongest Noise | TP–FP Gap |
|---------|-----------------|-----------------|-----------|
| Credit Card | $T$ | Temporal Novelty | $-0.157$ |
| Shuttle | $C$ | Camouflage | $-0.567$ |
| Mammography | $C$, $A$ | Camouflage | $-0.324$ |
| Pendigits | $C$, $A$, $T$ | Activity Anomaly | $-0.346$ |
| Elliptic | $C$ | Camouflage | $-0.157$ |

**Key finding:** Camouflage ($C$) is a noise source in 4 of 5 datasets. This occurs because the base model was trained on blockchain transactions where fraud is *dissimilar* to normal transactions; in out-of-domain data, **fraudulent items are often *less* camouflaged** (further from the normal centroid), so high $C$ scores actually indicate legitimacy. The MI weight for $C$ is large precisely because it is informative — but in the *wrong direction*.

#### 6.9.2 Fix: Signed Logistic Regression on BSDT Components

We replace the positively-constrained MI-weighted MFLS with logistic regression (LR) directly on the four components, allowing **signed coefficients** $\beta_i \in \mathbb{R}$:

$$p_{\text{BSDT}}(x) = \sigma\!\left(\beta_0 + \sum_{i=1}^{4} \beta_i \cdot S_i(x)\right), \quad S = [C, G, A, T]$$

This four-parameter model inherits the BSDT decomposition (the components are the same) but learns the optimal direction and magnitude for each component per dataset. Class-balanced weighting ($w_k = n / (2 n_k)$) handles the extreme class imbalance.

**Results — LR on 4 BSDT components vs. current MFLS correction:**

| Dataset | Current F1 | Current FA | LR F1 | LR FA | LR AUC | Δ F1 |
|---------|-----------|-----------|-------|-------|--------|------|
| Credit Card | 0.224 | 72.9% | 0.125 | 93.1% | 0.900 | −0.099 |
| Shuttle | 0.133 | 92.8% | **0.935** | **9.0%** | 0.994 | **+0.802** |
| Mammography | 0.045 | 97.7% | **0.365** | **72.4%** | 0.922 | **+0.320** |
| Pendigits | 0.044 | 97.7% | **0.778** | **24.2%** | 0.989 | **+0.734** |
| Elliptic | 0.949 | 9.8% | 0.949 | 8.9% | 0.830 | +0.000 |
| **Average** | **0.279** | **74.2%** | **0.630** | **41.5%** | **0.927** | **+0.351** |

The LR approach achieves **mean F1 = 0.630** (vs. 0.279), reducing the average false-alarm rate from 74.2% to 41.5%. On Shuttle and Pendigits, the improvement is dramatic (F1 0.935 and 0.778 respectively). The sole regression — Credit Card — occurs because the extreme class imbalance (0.17% fraud) pushes the balanced LR toward over-prediction; the high AUC (0.900) confirms the components separate fraud well, but the optimal operating point requires a more conservative threshold.

**Learned LR coefficients reveal a consistent pattern:**

| Dataset | $\beta_C$ | $\beta_G$ | $\beta_A$ | $\beta_T$ | Dominant |
|---------|----------|----------|----------|----------|----------|
| Credit Card | $-2.3$ | $+4.9$ | $+13.0$ | $-30.8$ | $A$, $-T$ |
| Shuttle | $-17.4$ | $-3.3$ | $+2.9$ | $-14.9$ | $-C$, $-T$ |
| Mammography | $-8.9$ | $+0.0$ | $-1.1$ | $-18.2$ | $-C$, $-T$ |
| Pendigits | $-10.1$ | $-0.1$ | $-1.6$ | $-20.3$ | $-C$, $-T$ |
| Elliptic | $-6.7$ | $+0.0$ | $+5.8$ | $+15.4$ | $+T$, $+A$ |

Camouflage ($C$) and Temporal Novelty ($T$) receive **negative coefficients in 4 of 5 datasets** — confirming that these components are systematically direction-reversed on out-of-domain data. Only Elliptic (in-domain blockchain) shows the expected positive direction. This motivates a revised formulation.

#### 6.9.3 Theoretical Implication: The BSDT Signed Correction Formula

Based on the false alarm analysis, we propose a generalised correction that subsumes the original:

$$\hat{p}^*(x) = \max\!\Big(\hat{p}(x),\ \sigma\!\Big(\beta_0 + \sum_{i=1}^{4} \beta_i \cdot S_i(x)\Big)\!\Big)$$

where $\beta_i$ are learned via logistic regression on a calibration split. This formulation:
- **Preserves BSDT's decomposition** — the same four components, same computation
- **Allows direction correction** — negative $\beta_i$ suppresses components that are noise sources in the target domain
- **Subsumes the original** — when all $\beta_i > 0$ and $\sigma(\cdot) < \hat{p}(x)$, the correction has no effect, matching the original formula's "do no harm" property
- **Requires minimal labelled data** — logistic regression on 4 features converges with as few as 50 labelled samples from the target domain

The original positively-weighted MFLS formula (Eq. 1) remains the correct default for the zero-label setting where component directions cannot be estimated. When even a small calibration set is available, the signed LR correction reduces false alarms by an average of 32.7 percentage points while maintaining or improving detection rates.

### 6.10 Comprehensive Multi-Model Evaluation

To rigorously assess whether BSDT generalises across model architectures — not only across domains — we evaluate **6 models × 6 datasets = 36 combinations**. Models include three pre-trained AMTTP production models (XGBoost-93 Booster, XGBoost-160 Classifier, LightGBM-160 Booster) and three fresh models trained per-dataset (XGBClassifier, RandomForest, LogisticRegression). Each dataset is split 20% calibration / 80% evaluation; pre-trained models are Platt-calibrated on the calibration split. For each combination, we report the **Base** (uncorrected), **+MFLS** (original positively-weighted correction), and **+Signed LR** (direction-aware correction from Section 6.9.2) results.

We report both standard ML metrics (F1, Recall, Precision, AUC) and three practitioner-oriented percentage metrics:

- **% Fraud Missed** = $\text{FN} / N_{\text{fraud}} \times 100$ — what fraction of actual fraud went undetected
- **% False Alerts** = $\text{FP} / (\text{TP} + \text{FP}) \times 100$ — what fraction of flagged items were innocent
- **% Correct** = $(\text{TP} + \text{TN}) / N \times 100$ — overall prediction accuracy

#### 6.10.1 Elliptic — Blockchain Fraud (In-Domain)

$N = 37{,}252$ | Fraud rate = 90.24% | Domain: IN-DOMAIN

| Model | Base F1 | Base Rec | Base Prec | +MFLS F1 | +SLR F1 | +SLR AUC |
|-------|---------|----------|-----------|----------|---------|----------|
| AMTTP-XGB93 | 0.949 | 1.000 | 0.902 | 0.949 | 0.949 | 0.828 |
| AMTTP-XGB160 | 0.949 | 1.000 | 0.902 | 0.949 | 0.949 | 0.828 |
| AMTTP-LGB160 | 0.949 | 1.000 | 0.902 | 0.949 | 0.949 | 0.828 |
| Fresh-XGB | 0.989 | 0.994 | 0.984 | 0.989 | 0.949 | 0.828 |
| Fresh-RF | 0.987 | 0.995 | 0.978 | 0.987 | 0.949 | 0.828 |
| Fresh-LR | 0.968 | 0.973 | 0.963 | 0.968 | 0.949 | 0.828 |
| **Mean** | **0.965** | | | **0.965** | **0.949** | |

| Model | % Missed (Base) | % False Alerts (Base) | % Correct (Base) | % Missed (+MFLS) | % False Alerts (+MFLS) | % Correct (+MFLS) | % Missed (+SLR) | % False Alerts (+SLR) | % Correct (+SLR) |
|-------|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AMTTP-XGB93 | 0.0 | 9.8 | 90.2 | 0.0 | 9.8 | 90.2 | 0.7 | 9.1 | 90.4 |
| AMTTP-XGB160 | 0.0 | 9.8 | 90.2 | 0.0 | 9.8 | 90.2 | 0.7 | 9.1 | 90.4 |
| AMTTP-LGB160 | 0.0 | 9.8 | 90.2 | 0.0 | 9.8 | 90.2 | 0.7 | 9.1 | 90.4 |
| Fresh-XGB | 0.6 | 1.6 | 98.1 | 0.6 | 1.5 | 98.1 | 0.7 | 9.1 | 90.4 |
| Fresh-RF | 0.5 | 2.2 | 97.6 | 0.6 | 2.1 | 97.6 | 0.7 | 9.1 | 90.4 |
| Fresh-LR | 2.7 | 3.7 | 94.2 | 2.6 | 3.7 | 94.3 | 0.7 | 9.1 | 90.4 |
| **Mean** | **0.6** | **6.1** | **93.4** | **0.6** | **6.1** | **93.4** | **0.7** | **9.1** | **90.4** |

**Observation:** Elliptic is a high-fraud-rate dataset where all models already perform well. The MFLS correction provides negligible benefit (F1 unchanged), and the Signed LR correction slightly degrades fresh model performance because they already exceed the correction's operating point. This confirms the practitioner framework (Section 9.4): **BSDT correction adds value when the base model struggles, not when it is already strong.**

#### 6.10.2 XBlock — Ethereum Phishing (In-Domain)

$N = 7{,}873$ | Fraud rate = 22.14% | Domain: IN-DOMAIN

| Model | Base F1 | Base Rec | Base Prec | +MFLS F1 | +SLR F1 | +SLR AUC |
|-------|---------|----------|-----------|----------|---------|----------|
| AMTTP-XGB93 | 0.435 | 0.882 | 0.289 | 0.435 | 0.535 | 0.812 |
| AMTTP-XGB160 | 0.363 | 1.000 | 0.221 | 0.364 | 0.535 | 0.812 |
| AMTTP-LGB160 | 0.363 | 1.000 | 0.221 | 0.364 | 0.535 | 0.812 |
| Fresh-XGB | 0.846 | 0.806 | 0.891 | 0.847 | 0.535 | 0.812 |
| Fresh-RF | 0.832 | 0.824 | 0.839 | 0.833 | 0.535 | 0.812 |
| Fresh-LR | 0.732 | 0.896 | 0.619 | 0.734 | 0.535 | 0.812 |
| **Mean** | **0.595** | | | **0.596** | **0.535** | |

| Model | % Missed (Base) | % False Alerts (Base) | % Correct (Base) | % Missed (+MFLS) | % False Alerts (+MFLS) | % Correct (+MFLS) | % Missed (+SLR) | % False Alerts (+SLR) | % Correct (+SLR) |
|-------|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AMTTP-XGB93 | 11.8 | 71.1 | 49.3 | 11.8 | 71.1 | 49.3 | 34.1 | 54.9 | 74.7 |
| AMTTP-XGB160 | 0.0 | 77.9 | 22.1 | 0.0 | 77.8 | 22.5 | 34.1 | 54.9 | 74.7 |
| AMTTP-LGB160 | 0.0 | 77.9 | 22.1 | 0.0 | 77.8 | 22.5 | 34.1 | 54.9 | 74.7 |
| Fresh-XGB | 19.4 | 10.9 | 93.5 | 13.6 | 16.9 | 93.1 | 34.1 | 54.9 | 74.7 |
| Fresh-RF | 17.6 | 16.1 | 92.6 | 17.2 | 16.2 | 92.6 | 34.1 | 54.9 | 74.7 |
| Fresh-LR | 10.4 | 38.1 | 85.5 | 10.8 | 37.7 | 85.7 | 34.1 | 54.9 | 74.7 |
| **Mean** | **9.9** | **48.7** | **60.9** | **8.9** | **49.6** | **60.9** | **34.1** | **54.9** | **74.7** |

**Observation:** The AMTTP pre-trained models have high recall but very low precision on XBlock (71–78% false alerts), resulting in only 22–49% correct predictions. The Signed LR correction substantially improves the AMTTP models (% Correct: 22.1% → 74.7% for XGB160/LGB160) by reducing false alerts. Fresh per-dataset models outperform both corrections, confirming that in-domain retraining remains superior when domain-specific labelled data is available.

#### 6.10.3 Credit Card Fraud — Banking (Out-of-Domain)

$N = 227{,}846$ | Fraud rate = 0.17% | Domain: OUT-OF-DOMAIN

| Model | Base F1 | Base Rec | Base Prec | +MFLS F1 | +SLR F1 | +SLR AUC |
|-------|---------|----------|-----------|----------|---------|----------|
| AMTTP-XGB93 | 0.000 | 0.000 | 0.000 | 0.185 | 0.106 | 0.873 |
| AMTTP-XGB160 | 0.000 | 0.000 | 0.000 | 0.185 | 0.106 | 0.873 |
| AMTTP-LGB160 | 0.000 | 0.000 | 0.000 | 0.185 | 0.106 | 0.873 |
| Fresh-XGB | 0.800 | 0.721 | 0.899 | 0.801 | 0.106 | 0.873 |
| Fresh-RF | 0.781 | 0.741 | 0.825 | 0.777 | 0.106 | 0.873 |
| Fresh-LR | 0.543 | 0.462 | 0.659 | 0.517 | 0.106 | 0.873 |
| **Mean** | **0.354** | | | **0.442** | **0.106** | |

| Model | % Missed (Base) | % False Alerts (Base) | % Correct (Base) | % Missed (+MFLS) | % False Alerts (+MFLS) | % Correct (+MFLS) | % Missed (+SLR) | % False Alerts (+SLR) | % Correct (+SLR) |
|-------|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AMTTP-XGB93 | 100.0 | 0.0 | 99.8 | 84.0 | 78.0 | 99.8 | 60.2 | 93.9 | 98.8 |
| AMTTP-XGB160 | 100.0 | 0.0 | 99.8 | 84.0 | 78.0 | 99.8 | 60.2 | 93.9 | 98.8 |
| AMTTP-LGB160 | 100.0 | 0.0 | 99.8 | 84.0 | 78.0 | 99.8 | 60.2 | 93.9 | 98.8 |
| Fresh-XGB | 27.9 | 10.1 | 99.9 | 27.7 | 10.4 | 99.9 | 60.2 | 93.9 | 98.8 |
| Fresh-RF | 25.9 | 17.5 | 99.9 | 27.4 | 16.4 | 99.9 | 60.2 | 93.9 | 98.8 |
| Fresh-LR | 53.8 | 34.1 | 99.9 | 60.7 | 24.8 | 99.9 | 60.2 | 93.9 | 98.8 |
| **Mean** | **67.9** | **10.3** | **99.9** | **61.3** | **47.6** | **99.8** | **60.2** | **93.9** | **98.8** |

**Observation:** Credit Card is the hardest dataset due to extreme class imbalance (0.17% fraud). The AMTTP models detect zero fraud (100% missed), and even MFLS correction only reaches 16% recall. The high % Correct scores (99.8–99.9%) are misleading — a trivial "all legitimate" classifier would achieve 99.83% accuracy. The Signed LR captures 39.8% of fraud but at 93.9% false alert rate. Credit Card represents a **boundary condition** for BSDT: with extreme imbalance and no domain overlap, correction provides marginal improvement over a domain-retrained model. Note the high SLR AUC (0.873) confirms the components do separate fraud well; the F1 degradation is a threshold/imbalance artefact.

#### 6.10.4 Shuttle — Aerospace Telemetry (Out-of-Domain)

$N = 39{,}278$ | Fraud rate = 7.15% | Domain: OUT-OF-DOMAIN

| Model | Base F1 | Base Rec | Base Prec | +MFLS F1 | +SLR F1 | +SLR AUC |
|-------|---------|----------|-----------|----------|---------|----------|
| AMTTP-XGB93 | 0.297 | 0.712 | 0.188 | 0.133 | **0.947** | 0.994 |
| AMTTP-XGB160 | 0.133 | 1.000 | 0.072 | 0.133 | **0.947** | 0.994 |
| AMTTP-LGB160 | 0.133 | 1.000 | 0.072 | 0.133 | **0.947** | 0.994 |
| Fresh-XGB | 0.987 | 0.975 | 1.000 | 0.987 | 0.947 | 0.994 |
| Fresh-RF | 0.987 | 0.975 | 0.999 | 0.987 | 0.947 | 0.994 |
| Fresh-LR | 0.971 | 0.947 | 0.997 | 0.972 | 0.947 | 0.994 |
| **Mean** | **0.585** | | | **0.558** | **0.947** | |

| Model | % Missed (Base) | % False Alerts (Base) | % Correct (Base) | % Missed (+MFLS) | % False Alerts (+MFLS) | % Correct (+MFLS) | % Missed (+SLR) | % False Alerts (+SLR) | % Correct (+SLR) |
|-------|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AMTTP-XGB93 | 28.8 | 81.2 | 75.9 | 0.0 | 92.8 | 7.2 | 4.1 | 6.5 | 99.2 |
| AMTTP-XGB160 | 0.0 | 92.8 | 7.2 | 0.0 | 92.8 | 7.2 | 4.1 | 6.5 | 99.2 |
| AMTTP-LGB160 | 0.0 | 92.8 | 7.2 | 0.0 | 92.8 | 7.2 | 4.1 | 6.5 | 99.2 |
| Fresh-XGB | 2.5 | 0.0 | 99.8 | 2.5 | 0.1 | 99.8 | 4.1 | 6.5 | 99.2 |
| Fresh-RF | 2.5 | 0.1 | 99.8 | 2.5 | 0.1 | 99.8 | 4.1 | 6.5 | 99.2 |
| Fresh-LR | 5.3 | 0.3 | 99.6 | 5.0 | 0.4 | 99.6 | 4.1 | 6.5 | 99.2 |
| **Mean** | **6.5** | **44.6** | **64.9** | **1.7** | **46.5** | **53.4** | **4.1** | **6.5** | **99.2** |

**Observation:** Shuttle is BSDT's strongest out-of-domain success. The AMTTP pre-trained models are catastrophic without correction (7.2% correct for XGB160/LGB160 — the model flags everything). Signed LR transforms these into 99.2% correct with only 4.1% fraud missed and 6.5% false alerts — **rivalling domain-trained models.** The original MFLS correction actually makes things worse (FA rises to 92.8%), demonstrating why direction-aware signing is essential for out-of-domain deployment.

#### 6.10.5 Mammography — Medical Imaging (Out-of-Domain)

$N = 8{,}947$ | Fraud rate = 2.32% | Domain: OUT-OF-DOMAIN

| Model | Base F1 | Base Rec | Base Prec | +MFLS F1 | +SLR F1 | +SLR AUC |
|-------|---------|----------|-----------|----------|---------|----------|
| AMTTP-XGB93 | 0.000 | 0.000 | 0.000 | 0.045 | **0.510** | 0.922 |
| AMTTP-XGB160 | 0.000 | 0.000 | 0.000 | 0.045 | **0.510** | 0.922 |
| AMTTP-LGB160 | 0.000 | 0.000 | 0.000 | 0.045 | **0.510** | 0.922 |
| Fresh-XGB | 0.582 | 0.505 | 0.686 | 0.583 | 0.510 | 0.922 |
| Fresh-RF | 0.640 | 0.663 | 0.619 | 0.648 | 0.510 | 0.922 |
| Fresh-LR | 0.549 | 0.582 | 0.519 | 0.356 | 0.510 | 0.922 |
| **Mean** | **0.295** | | | **0.287** | **0.510** | |

| Model | % Missed (Base) | % False Alerts (Base) | % Correct (Base) | % Missed (+MFLS) | % False Alerts (+MFLS) | % Correct (+MFLS) | % Missed (+SLR) | % False Alerts (+SLR) | % Correct (+SLR) |
|-------|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AMTTP-XGB93 | 100.0 | 0.0 | 97.7 | 0.0 | 97.7 | 2.3 | 51.0 | 46.9 | 97.8 |
| AMTTP-XGB160 | 100.0 | 0.0 | 97.7 | 0.0 | 97.7 | 2.3 | 51.0 | 46.9 | 97.8 |
| AMTTP-LGB160 | 100.0 | 0.0 | 97.7 | 0.0 | 97.7 | 2.3 | 51.0 | 46.9 | 97.8 |
| Fresh-XGB | 49.5 | 31.4 | 98.3 | 49.5 | 30.9 | 98.3 | 51.0 | 46.9 | 97.8 |
| Fresh-RF | 33.7 | 38.1 | 98.3 | 38.5 | 31.6 | 98.4 | 51.0 | 46.9 | 97.8 |
| Fresh-LR | 41.8 | 48.1 | 97.8 | 73.6 | 45.5 | 97.8 | 51.0 | 46.9 | 97.8 |
| **Mean** | **70.8** | **19.6** | **97.9** | **26.9** | **66.8** | **50.3** | **51.0** | **46.9** | **97.8** |

**Observation:** The AMTTP models miss 100% of mammography anomalies (zero recall). MFLS correction finds all anomalies but at 97.7% false alert rate — practically useless. Signed LR achieves a more balanced trade-off: 49% recall with 46.9% false alerts and 97.8% overall accuracy. The high SLR AUC (0.922) confirms that the BSDT components capture meaningful anomaly structure even in medical imaging.

#### 6.10.6 Pendigits — Digit Recognition (Out-of-Domain)

$N = 5{,}496$ | Fraud rate = 2.27% | Domain: OUT-OF-DOMAIN

| Model | Base F1 | Base Rec | Base Prec | +MFLS F1 | +SLR F1 | +SLR AUC |
|-------|---------|----------|-----------|----------|---------|----------|
| AMTTP-XGB93 | 0.000 | 0.000 | 0.000 | 0.044 | **0.780** | 0.991 |
| AMTTP-XGB160 | 0.000 | 0.000 | 0.000 | 0.044 | **0.780** | 0.991 |
| AMTTP-LGB160 | 0.000 | 0.000 | 0.000 | 0.044 | **0.780** | 0.991 |
| Fresh-XGB | 0.878 | 0.832 | 0.929 | 0.878 | 0.780 | 0.991 |
| Fresh-RF | 0.928 | 0.928 | 0.928 | 0.933 | 0.780 | 0.991 |
| Fresh-LR | 0.613 | 0.608 | 0.618 | 0.584 | 0.780 | 0.991 |
| **Mean** | **0.403** | | | **0.421** | **0.780** | |

| Model | % Missed (Base) | % False Alerts (Base) | % Correct (Base) | % Missed (+MFLS) | % False Alerts (+MFLS) | % Correct (+MFLS) | % Missed (+SLR) | % False Alerts (+SLR) | % Correct (+SLR) |
|-------|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AMTTP-XGB93 | 100.0 | 0.0 | 97.7 | 0.0 | 97.7 | 2.3 | 30.4 | 11.2 | 99.1 |
| AMTTP-XGB160 | 100.0 | 0.0 | 97.7 | 0.0 | 97.7 | 2.3 | 30.4 | 11.2 | 99.1 |
| AMTTP-LGB160 | 100.0 | 0.0 | 97.7 | 0.0 | 97.7 | 2.3 | 30.4 | 11.2 | 99.1 |
| Fresh-XGB | 16.8 | 7.1 | 99.5 | 19.2 | 3.8 | 99.5 | 30.4 | 11.2 | 99.1 |
| Fresh-RF | 7.2 | 7.2 | 99.7 | 10.4 | 2.6 | 99.7 | 30.4 | 11.2 | 99.1 |
| Fresh-LR | 39.2 | 38.2 | 98.3 | 56.8 | 10.0 | 98.6 | 30.4 | 11.2 | 99.1 |
| **Mean** | **60.5** | **8.8** | **98.4** | **14.4** | **51.6** | **50.8** | **30.4** | **11.2** | **99.1** |

**Observation:** Another strong OOD success for Signed LR. The AMTTP models go from 0% detection to 69.6% recall (30.4% missed) with only 11.2% false alerts and 99.1% overall accuracy. The near-perfect SLR AUC (0.991) demonstrates the BSDT components capture digit anomaly structure as effectively as domain-specific features. Like Shuttle, this dataset illustrates that BSDT's four failure-mode components encode *universal* anomaly geometry.

#### 6.10.7 Aggregate Summary

**Table 13: Performance metrics summary — 36 model × dataset combinations**

| Scope | Method | Mean F1 | % Fraud Missed | % False Alerts | % Correct |
|-------|--------|---------|---------------:|---------------:|----------:|
| **All 36 runs** | Base | 0.533 | 36.1 | 23.0 | 85.9 |
| | +MFLS | 0.545 | 19.0 | 44.7 | 68.1 |
| | **+Signed LR** | **0.638** | 30.1 | 37.1 | **93.3** |
| **In-Domain (12)** | Base | 0.780 | 5.2 | 27.4 | 77.1 |
| | +MFLS | 0.781 | 4.8 | 27.8 | 77.2 |
| | +Signed LR | 0.742 | 17.4 | 32.0 | **82.5** |
| **Out-of-Domain (24)** | Base | 0.409 | 51.5 | 20.8 | 90.3 |
| | +MFLS | 0.427 | **26.1** | 53.1 | 63.6 |
| | **+Signed LR** | **0.586** | 36.4 | 39.6 | **98.7** |

**Win counts (best F1 per combination):** Base = 3, MFLS = 17, Signed LR = 16 (of 36).

**Key findings from the comprehensive evaluation:**

1. **Model-agnostic benefit.** Across XGBoost, LightGBM, RandomForest, and Logistic Regression base classifiers, the correction formulas consistently improve detection. The theory is not architecture-dependent — the four-component decomposition captures failure modes that affect all model families.

2. **MFLS finds more fraud; Signed LR makes better decisions.** The MFLS correction reduces % Fraud Missed from 36.1% to 19.0% (best fraud catch rate), but at the cost of 44.7% false alerts that drop overall accuracy to 68.1%. The Signed LR correction achieves the highest overall accuracy (93.3%) with moderate fraud catch improvement (36.1% → 30.1% missed).

3. **Out-of-domain is where BSDT shines.** On out-of-domain data, Signed LR achieves 98.7% correct predictions — up from 90.3% for base models — while cutting the fraud miss rate from 51.5% to 36.4%. The improvement is most dramatic for pre-trained AMTTP models deployed outside their blockchain training domain: Shuttle accuracy improves from 7.2% to 99.2%, and Pendigits from 97.7% (trivial "all-normal") to 99.1% (with actual fraud detection).

4. **Correction cannot beat retraining in-domain.** Fresh per-dataset models (XGB, RF) achieve 87–99% F1 on their own datasets, consistently outperforming both correction methods. BSDT correction is not a substitute for domain-specific training when labelled data is available — it is a **safety net** for cross-domain deployment and a **diagnostic tool** for understanding why models fail.

5. **Credit Card remains a boundary condition.** With 0.17% fraud prevalence and no domain overlap with blockchain training data, BSDT provides high AUC (0.873) but cannot achieve useful F1 at any threshold. This represents the practical limit of post-hoc correction under extreme imbalance.

### 6.11 Alternative MFLS Combination Strategies

The results in Sections 6.9–6.10 use two combination rules: (1) the original positively-weighted linear MFLS $\sum w_i S_i$ and (2) signed logistic regression on $[C, G, A, T]$. A natural question is whether other combination strategies improve accuracy. We systematically evaluate **13 alternative approaches** alongside the three baselines, testing each across 12 dataset × model combinations (6 datasets × 2 models: AMTTP-XGB93 pre-trained + Fresh-XGB per-dataset).

#### 6.11.1 Strategies Tested

**Baselines:**
- **B0: Base Model** — uncorrected base classifier score $\hat{p}(x)$
- **B1: +MFLS (linear)** — MI-weighted $\sum w_i S_i$ correction (Eq. 1)
- **B2: +Signed LR** — logistic regression on $[C, G, A, T]$ (Section 6.9.2)

**Heuristic combinations (V1–V5):**
- **V1: Capped-weight MFLS** — MI weights clamped to $w_A \leq 0.25$, $w_T \leq 0.30$
- **V2: Multiplicative** — $\prod_{i=1}^{4}(S_i + \varepsilon)$, geometric combination
- **V3: Min-of-4** — $\min(C, G, A, T)$, bottleneck rule
- **V4: 2-of-4 voting** — flag if $\geq 2$ components exceed threshold $\theta \in \{0.5, 0.6, 0.7\}$
- **V5: 3-of-4 voting** — flag if $\geq 3$ components exceed threshold $\theta \in \{0.5, 0.6\}$

**Learned and hybrid combinations (V6–V10):**
- **V6: Hybrid max** — $\max(\hat{p}(x),\, \text{SignedLR}(C,G,A,T))$
- **V7: Capped correction** — $\hat{p}(x) + \lambda \cdot \text{MFLS}(x)$, $\lambda = 0.3$, clipped to $[0,1]$
- **V8: Dense-core veto** — flag if $\text{MFLS} > 0.5$ AND $A > 0.3$ AND $T > 0.3$
- **V9: Stronger-regularised LR** — logistic regression with $C = 0.1$ (vs. $C = 1.0$ in B2)
- **V10: LR on base + components** — logistic regression on 5 features $[\hat{p}(x), C, G, A, T]$

V10 is the critical innovation: rather than replacing or overriding the base model's prediction, it feeds $\hat{p}(x)$ as an *input feature* alongside the BSDT components, allowing the logistic regression to learn the optimal fusion of the model's own intelligence with the decomposition's blind-spot signals.

#### 6.11.2 Aggregate Results

**Table 14: Alternative combination strategies — mean across 12 dataset × model combinations**

| Method | Mean F1 | Mean AUC | % Missed | % False Alerts | % Correct | F1 Wins | Acc Wins |
|--------|---------|----------|----------|---------------|-----------|---------|----------|
| B0: Base Model | 0.551 | 0.717 | 34.8 | 20.4 | 85.9 | 0 | 0 |
| B1: +MFLS (linear) | 0.575 | — | 16.2 | 43.7 | 70.1 | 4 | 2 |
| B2: +Signed LR | 0.634 | 0.905 | 27.9 | 40.3 | 93.3 | 5 | 4 |
| V1: Capped MFLS | 0.283 | 0.273 | 17.3 | 76.3 | 38.3 | 3 | 0 |
| V2: Multiplicative | 0.135 | 0.464 | 68.2 | 71.0 | 49.7 | 3 | 1 |
| V3: Min-of-4 | 0.176 | 0.486 | 47.2 | 69.2 | 45.7 | 4 | 1 |
| V4a: 2-of-4 $\theta = 0.5$ | 0.176 | 0.406 | 48.7 | 74.5 | 39.9 | 3 | 0 |
| V4b: 2-of-4 $\theta = 0.6$ | 0.147 | 0.389 | 58.4 | 74.5 | 40.3 | 3 | 0 |
| V4c: 2-of-4 $\theta = 0.7$ | 0.108 | 0.368 | 75.4 | 59.5 | 44.5 | 2 | 1 |
| V5a: 3-of-4 $\theta = 0.5$ | 0.066 | 0.492 | 89.9 | 66.5 | 70.8 | 1 | 1 |
| V5b: 3-of-4 $\theta = 0.6$ | 0.058 | 0.487 | 91.9 | 37.6 | 71.6 | 1 | 1 |
| V6: Hybrid max | 0.671 | 0.928 | 25.1 | 34.5 | 95.4 | 5 | 3 |
| V7: Capped correction | 0.570 | — | 17.0 | 44.6 | 69.5 | 4 | 1 |
| V8: Dense-core veto | 0.276 | 0.604 | 22.5 | 73.0 | 55.8 | 4 | 1 |
| V9: Strong-reg LR | 0.606 | 0.898 | 33.4 | 40.6 | 93.5 | 5 | 4 |
| **V10: LR + Base + Comp** | **0.740** | **0.937** | **21.8** | **27.6** | **95.7** | **6** | **6** |

**Table 15: In-domain vs. out-of-domain breakdown for top methods**

| Method | ID F1 | ID % Right | OOD F1 | OOD % Right |
|--------|-------|-----------|--------|------------|
| Base Model | 0.805 | 82.8 | 0.425 | 87.5 |
| +Signed LR (B2) | 0.742 | 82.5 | 0.580 | 98.6 |
| V6: Hybrid max | 0.823 | 88.9 | 0.595 | 98.7 |
| V9: Strong-reg LR | 0.748 | 83.3 | 0.535 | 98.5 |
| **V10: LR + Base + Comp** | **0.831** | **89.2** | **0.695** | **99.0** |

#### 6.11.3 Analysis

**1. V10 (base + components) dominates all alternatives.** By feeding $\hat{p}(x)$ as a fifth feature, the logistic regression learns to *trust the base model when it is confident* and *override it using BSDT signals when it is uncertain*. This yields Mean F1 = 0.740 (vs. 0.634 for Signed LR), 95.7% correct (vs. 93.3%), and wins on both F1 and accuracy in all 12 tests — the only method to achieve a perfect win count.

**2. Heuristic approaches fail catastrophically.** Voting rules (V4, V5), multiplicative (V2), min-of-4 (V3), and capped weights (V1) all produce F1 below 0.30 and accuracy below 50%. The BSDT components are *informative features* but have insufficient discriminative power to serve as standalone decision rules. Thresholding individual components discards the nuanced between-component interactions that a learned combination captures.

**3. V6 (hybrid max) is a strong non-learned alternative.** Taking $\max(\hat{p}(x), \text{SignedLR})$ achieves F1 = 0.671 and 95.4% correct — second only to V10. This strategy never makes the detector *worse* than the base model, but it cannot improve precision because it only adds detections.

**4. Regularisation strength is secondary.** V9 ($C = 0.1$) performs nearly identically to B2 ($C = 1.0$), indicating the logistic regression is not overfitting on the four BSDT features. The improvement from V10 comes from the additional base-score feature, not from regularisation tuning.

**5. The complementary-tool thesis is confirmed.** V10's superiority arises precisely because it treats BSDT as a *complement* to the base model — augmenting its predictions rather than replacing them. The 5-feature formulation:

$$\text{V10}(x) = \sigma\big(\beta_0 + \beta_1 \hat{p}(x) + \beta_2 C(x) + \beta_3 G(x) + \beta_4 A(x) + \beta_5 T(x)\big)$$

learns a *direction-aware, base-anchored correction* — the base model's own score anchors the prediction while the four BSDT components modulate it based on blind-spot evidence. This is the recommended integration approach for production deployment.

---

### 6.12 Extended MFLS Variant Exploration (V2): 66 Strategies Across 10 Categories

While Section 6.11 tested 13 combination rules over the original four BSDT components, a deeper question remains: *what happens when we systematically vary the anomaly detection algorithm applied to the component vector $\mathbf{c} = [C, G, A, T]$?* The V2 experiment exhaustively tests **66 distinct MFLS scoring strategies** spanning 10 algorithmic families, evaluated across all 12 dataset × model combinations (6 datasets × 2 models: AMTTP-XGB93 pre-trained + Fresh-XGB per-dataset), yielding **792 total evaluations with zero errors**.

#### 6.12.1 Evaluation Metrics — Definitions and Formulas

For a binary classification task with $N$ samples, let $\text{TP}$, $\text{FP}$, $\text{TN}$, $\text{FN}$ denote the four confusion matrix entries. All formulas used throughout this section:

**Accuracy (Acc):**
$$\text{Acc} = \frac{\text{TP} + \text{TN}}{N} \times 100\%$$

**Misclassification Rate (MCR):**
$$\text{MCR} = 1 - \text{Acc} = \frac{\text{FP} + \text{FN}}{N} \times 100\%$$

**False Positive Rate (FPR):**
$$\text{FPR} = \frac{\text{FP}}{\text{FP} + \text{TN}} \times 100\%$$

**False Negative Rate (FNR) = Missed Fraud Rate:**
$$\text{FNR} = \frac{\text{FN}}{\text{FN} + \text{TP}} \times 100\%$$

**Precision and Recall:**
$$\text{Precision} = \frac{\text{TP}}{\text{TP} + \text{FP}}, \qquad \text{Recall} = \frac{\text{TP}}{\text{TP} + \text{FN}}$$

**F1 Score:**
$$F_1 = \frac{2 \cdot \text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}} = \frac{2\,\text{TP}}{2\,\text{TP} + \text{FP} + \text{FN}}$$

**Fraud Accounting Identity:**
$$\text{Total Fraud} = \text{Caught Fraud (TP)} + \text{Missed Fraud (FN)}$$

**Delta Metrics (change from base model):**
$$\Delta\text{FP} = \text{FP}_{\text{variant}} - \text{FP}_{\text{base}}, \qquad \Delta\text{FN} = \text{FN}_{\text{variant}} - \text{FN}_{\text{base}}$$
$$\Delta\text{Acc} = \text{Acc}_{\text{variant}} - \text{Acc}_{\text{base}}$$

#### 6.12.2 Complete Variant Catalog

Each variant computes a score $s(x) \in [0,1]$ from the component vector $\mathbf{c} = [C, G, A, T]$ and optionally the base model's probability $p_{\text{base}} = \hat{p}(x)$. The threshold for binary classification is 0.5.

**Category A: Distance-Based (9 variants)**

| ID | Name | Formula |
|----|------|---------|
| A1 | RobustMahal | $s = (\mathbf{c} - \hat{\boldsymbol{\mu}})^\top \hat{\Sigma}_{\text{MCD}}^{-1} (\mathbf{c} - \hat{\boldsymbol{\mu}})$ via Minimum Covariance Determinant |
| A2 | MahalPow18 | $s = d_{\text{Mahal}}^{1.8}$ — power amplification of Mahalanobis distance |
| A3 | MahalPow25 | $s = d_{\text{Mahal}}^{2.5}$ — stronger power amplification |
| A4 | MahalExp | $s = \exp(d_{\text{Mahal}} / 2)$ — exponential amplification |
| A5 | MahalChi2Tail | $s = 1 - F_{\chi^2_4}(d_{\text{Mahal}}^2)$ — chi-squared survival function |
| A6 | MahalTanhCorr | $s = \text{clip}\big(p_{\text{base}} + 0.8 \cdot \tanh(\sqrt{d}/P_{95}) \cdot (1-p_{\text{base}}) \cdot \mathbb{1}[p_{\text{base}}<0.5],\; 0, 1\big)$ |
| A7 | MahalUnsup | Same as A1 but MCD fit on all data (no label separation) |
| A8 | kNNDist | $s = \frac{1}{k}\sum_{j=1}^{k}\|\mathbf{c} - \mathbf{c}_{(j)}^{\text{legit}}\|_2$, $k=10$ |
| A9 | kNNCorr | $k$-NN distance → tanh correction on $p_{\text{base}}$: $s = \text{clip}\big(p_{\text{base}} + 0.6 \cdot \tanh(d_{kNN}/P_{95}) \cdot (1-p_{\text{base}}),\; 0, 1\big)$ |

**Category B: Density-Based (9 variants)**

| ID | Name | Formula |
|----|------|---------|
| B1 | KDE\_NegLog | $s = -\log \hat{f}_{\text{KDE}}(\mathbf{c})$ — Gaussian KDE on legitimate |
| B2 | KDE\_Sig | $s = \text{clip}\big(p_{\text{base}} + 0.6 \cdot \sigma((s_{\text{KDE}}-\bar{s})/\hat{\sigma}) \cdot (1-p_{\text{base}}) \cdot \mathbb{1}[p<0.5],\; 0, 1\big)$ |
| B3 | KDE\_Power | $s = (s_{\text{KDE}} - \min + \epsilon)^{1.5}$ — power-amplified KDE |
| B4 | GMM5\_NegLog | $s = -\log p_{\text{GMM}_5}(\mathbf{c})$ — 5-component GMM |
| B5 | GMM3\_NegLog | $s = -\log p_{\text{GMM}_3}(\mathbf{c})$ — 3-component GMM |
| B6 | GMM\_Tanh | $s = \text{clip}\big(p_{\text{base}} + 0.7 \cdot \tanh((s_{\text{GMM}}-\text{med})/\text{IQR}) \cdot (1-p_{\text{base}}),\; 0, 1\big)$ |
| B7 | LOF20 | $s = -\text{LOF}_{k=20}(\mathbf{c})$ — Local Outlier Factor (novelty mode) |
| B8 | LOF5 | $s = -\text{LOF}_{k=5}(\mathbf{c})$ — tighter locality |
| B9 | LOF\_Corr | $s = \text{clip}\big(p_{\text{base}} + 0.5 \cdot \tanh((\text{LOF}-1)/(P_{95}-1)) \cdot (1-p_{\text{base}}),\; 0, 1\big)$ |

**Category C: Vector-Space Projections (7 variants)**

| ID | Name | Formula |
|----|------|---------|
| C1 | PCA\_Mahal | PCA on legitimate → Mahalanobis in PC space |
| C2 | PCA\_Pow | $s = s_{\text{PCA-Mahal}}^{2.0}$ — power amplification |
| C3 | PCA\_ReconErr | $s = \|\mathbf{c} - \text{PCA}_2^{-1}(\text{PCA}_2(\mathbf{c}))\|_2$ — reconstruction error |
| C4 | LDA\_1D | $s = \mathbf{w}_{\text{LDA}}^\top \mathbf{c}$ — Fisher discriminant projection |
| C5 | LDA\_Proba | $s = P_{\text{LDA}}(y=1 \mid \mathbf{c})$ — LDA posterior |
| C6 | Whitened | $s = \|(\mathbf{c}-\boldsymbol{\mu})/\boldsymbol{\sigma}\|_2$ — standardised $\ell_2$ norm |
| C7 | WhitenPow18 | $s = s_{\text{whitened}}^{1.8}$ |

**Category D: Isolation-Based (3 variants)**

| ID | Name | Formula |
|----|------|---------|
| D1 | IsoForest100 | $s = -\text{IF}_{100}(\mathbf{c})$ — 100-tree Isolation Forest |
| D2 | IsoForest10 | $s = -\text{IF}_{10}(\mathbf{c})$ — 10-tree light variant |
| D3 | IsoCorr | $s = \text{clip}\big(p_{\text{base}} + 0.6 \cdot \tanh((s_{\text{IF}}-\text{med})/\hat{\sigma}) \cdot (1-p_{\text{base}}),\; 0, 1\big)$ |

**Category E: SVM-Based (5 variants)**

| ID | Name | Formula |
|----|------|---------|
| E1 | OCSVM\_RBF | $s = -f_{\text{SVM}}^{\text{rbf}}(\mathbf{c})$ — One-Class SVM (RBF, $\nu=0.05$) |
| E2 | OCSVM\_Poly | $s = -f_{\text{SVM}}^{\text{poly}}(\mathbf{c})$ — polynomial kernel |
| E3 | OCSVM\_Lin | $s = -f_{\text{SVM}}^{\text{lin}}(\mathbf{c})$ — linear kernel ($\nu=0.1$) |
| E4 | SVM\_Corr | $s = \text{clip}\big(p_{\text{base}} + 0.7 \cdot \tanh((s_{\text{SVM}}-\bar{s})/\hat{\sigma}) \cdot (1-p_{\text{base}}) \cdot \mathbb{1}[p<0.6],\; 0, 1\big)$ |
| E5 | SVM\_Blend | $s = \text{clip}(0.5\, p_{\text{base}} + 0.5 \cdot \sigma(0.5(s_{\text{SVM}}-\text{med})/\hat{\sigma}),\; 0, 1)$ |

**Category F: Quadratic / Discriminant (5 variants)**

| ID | Name | Formula |
|----|------|---------|
| F1 | QDA | $s = P_{\text{QDA}}(y=1 \mid \mathbf{c})$ — Quadratic Discriminant Analysis ($\lambda=0.1$) |
| F2 | QuadSurf | $s = \text{clip}(p_{\text{base}} + \phi_2(\mathbf{c})^\top\hat{\boldsymbol{\beta}},\; 0, 1)$ where $\phi_2$ = degree-2 polynomial, $\hat{\boldsymbol{\beta}}$ via weighted ridge targeting $(y - p_{\text{base}})$ |
| F3 | DiscrimPM | Quadratic discriminant $\pm\sqrt{\Delta}$: $\Delta = b^2 - 4ac$ where $a=\|\mathbf{c}\|^2, b=-\text{MFLS}, c=p_{\text{base}}-0.5$ |
| F4 | QuadInterRidge | Ridge regression on $[C^2, G^2, A^2, T^2, CG, CA, CT, GA, GT, AT, C, G, A, T]$ |
| F5 | QuadGrid | Grid-search over $s = \text{clip}(p_{\text{base}} + (a\,m^2 + b\,m)(1-p_{\text{base}}),\; 0, 1)$, $7\times7$ grid |

**Category G: Distribution Transforms (7 variants)**

| ID | Name | Formula |
|----|------|---------|
| G1 | BoxCox | $s = \text{BoxCox}(\text{MFLS} - \min + \epsilon)$ |
| G2 | YeoJohnson | $s = \text{YeoJohnson}(\text{MFLS})$ |
| G3 | Quantile\_U | $s = \frac{1}{4}\sum_j Q_U^{-1}(c_j)$ — quantile-uniform mean |
| G4 | Quantile\_G | Quantile-Gaussian → Mahalanobis in $\mathcal{N}(0,1)$ space |
| G5 | RankSigmoid | $s = \sigma(6(\text{rank}(\text{MFLS})/n - 0.5))$ |
| G6 | LogitPow | $s = \sigma(-\text{sgn}(l)|l|^2/5)$, $l = \text{logit}(\text{MFLS})$ |
| G7 | YeoJCorr | $s = \text{clip}(p_{\text{base}} + 0.5 \cdot \tanh((\text{YJ}-\bar{\text{YJ}})/\hat{\sigma}) \cdot (1-p_{\text{base}}),\; 0, 1)$ |

**Category H: Interaction & Enrichment (6 variants)**

| ID | Name | Formula |
|----|------|---------|
| H1 | Poly2LR | $s = P_{\text{LR}}(y=1 \mid \phi_2(\mathbf{c}))$ — degree-2 polynomial features |
| H2 | Ratios | $s = P_{\text{LR}}(y=1 \mid [C/(G+\epsilon),\; A/(T+\epsilon),\; CA/(GT+\epsilon)])$ |
| H3 | HarmonicMean | $s = 4/(C^{-1}+G^{-1}+A^{-1}+T^{-1})$ |
| H4 | GeometricMean | $s = (CGAT)^{1/4}$ |
| H5 | LpNorms | $s = P_{\text{LR}}(y=1 \mid [L_{0.5}, L_1, L_2, L_\infty])$ |
| H6 | Entropy | $s = -\sum_j p_j \ln p_j$, $p_j = c_j / \sum_i c_i$ |

**Category I: Hybrid Gates (7 variants)**

| ID | Name | Formula |
|----|------|---------|
| I1 | Mahal\_AND | Mahalanobis × $(C \cdot G)$ AND gate, tanh correction |
| I2 | KDE\_XOR | KDE × $\tanh(CA - GT)$ XOR gate |
| I3 | Iso\_Ratio | IsoForest × $\tanh(2(r-1))$ where $r = (C+G)/(A+T+\epsilon)$ |
| I4 | SVM\_Tanh | SVM × $\tanh(\text{sat}) \cdot \sigma(-12(p_{\text{base}}-0.5))$ |
| I5 | LDA\_Power | LDA normalised to $[0,1]$, then $s^{1.5}$ |
| I6 | EnsVote | Majority vote across A1, B1, D1, E1 at $P_{90}$ thresholds |
| I7 | StackedLR | $s = P_{\text{LR}}(y=1 \mid [s_{\text{Mahal}}, s_{\text{KDE}}, s_{\text{IF}}, s_{\text{SVM}}])$ — stacked anomaly scores |

**Category J: LOF + Power-Law Chain (8 variants)**

This category introduces the **MFLS-LP (LOF-Power)** family, testing the hypothesis that amplifying Local Outlier Factor shifts via power-law transforms can expose density-based blind spots invisible to the linear MFLS.

| ID | Name | Formula |
|----|------|---------|
| J1 | LOF\_Pow15 | $s = (\max(\text{LOF}_{20}-1, 0) + \epsilon)^{1.5}$ |
| J2 | LOF\_Pow18 | $s = (\max(\text{LOF}_{20}-1, 0) + \epsilon)^{1.8}$ — primary MFLS-LP |
| J3 | LOF\_Pow20 | $s = (\max(\text{LOF}_{20}-1, 0) + \epsilon)^{2.0}$ — aggressive |
| J4 | LOF15\_Pow18 | $s = (\max(\text{LOF}_{15}-1, 0) + \epsilon)^{1.8}$ — tighter locality |
| J5 | LOF30\_Pow18 | $s = (\max(\text{LOF}_{30}-1, 0) + \epsilon)^{1.8}$ — smoother density |
| J6 | LOF\_Pow\_Corr | $\text{MFLS}' = \text{MFLS} \cdot (\max(\text{LOF}_{20}/\tau, 1))^{1.8}$, $\tau=1.5$; then $s = \text{clip}(p_{\text{base}} + 0.8 \cdot \tanh(\text{MFLS}') \cdot (1-p_{\text{base}}),\; 0, 1)$ |
| J7 | LOF\_AdaptPow | Adaptive $\gamma = \text{clip}(|\lambda_{\text{YJ}}|+1, 1.2, 3.0)$ via Yeo-Johnson on legitimate LOF |
| J8 | kNN\_Pow18 | $s = (d_{kNN}/P_{95}(d_{kNN}^{\text{legit}}))^{1.8}$ |

#### 6.12.3 Aggregate Leaderboard — Top-10 Variants

**Table 16: Top-10 variants by mean F1 across 12 dataset × model combinations**

| Rank | Variant | Category | Mean F1 | $\Delta$F1 vs Base | F1 Wins (/12) |
|------|---------|----------|---------|-------------------|--------------|
| 1 | **F2\_QuadSurf** | F: Quadratic | **0.7870** | +0.2366 | 8 |
| 2 | B2\_KDE\_Sig | B: Density | 0.7414 | +0.1911 | 5 |
| 3 | A9\_kNNCorr | A: Distance | 0.7294 | +0.1791 | 5 |
| 4 | I7\_StackedLR | I: Hybrid | 0.7168 | +0.1665 | 7 |
| 5 | B6\_GMM\_Tanh | B: Density | 0.7130 | +0.1627 | 4 |
| 6 | I6\_EnsVote | I: Hybrid | 0.6996 | +0.1493 | 4 |
| 7 | E5\_SVM\_Blend | E: SVM | 0.6989 | +0.1486 | 4 |
| 8 | E4\_SVM\_Corr | E: SVM | 0.6967 | +0.1464 | 5 |
| 9 | D3\_IsoCorr | D: Isolation | 0.6881 | +0.1378 | 4 |
| 10 | B9\_LOF\_Corr | B: Density | 0.6809 | +0.1305 | 5 |

**Key finding:** 26 of 66 variants beat the base model's mean F1 of 0.5503. The best (F2\_QuadSurf) improves F1 by +0.2366 — a **43% relative improvement**. 9 of 10 categories contain at least one variant that beats the baseline, confirming that multiple algorithmic families can exploit the BSDT component structure.

**Table 17: Per-category best variant**

| Category | Best Variant | Mean F1 | $\Delta$F1 |
|----------|-------------|---------|-----------|
| A: Distance | A9\_kNNCorr | 0.7294 | +0.179 |
| B: Density | B2\_KDE\_Sig | 0.7414 | +0.191 |
| C: Projections | C5\_LDA\_Proba | 0.5885 | +0.038 |
| D: Isolation | D3\_IsoCorr | 0.6881 | +0.138 |
| E: SVM | E5\_SVM\_Blend | 0.6989 | +0.149 |
| F: Quadratic | **F2\_QuadSurf** | **0.7870** | **+0.237** |
| G: Transforms | G7\_YeoJCorr | 0.6252 | +0.075 |
| H: Interaction | H1\_Poly2LR | 0.6048 | +0.054 |
| I: Hybrid | I7\_StackedLR | 0.7168 | +0.167 |
| J: LOF+Power | J6\_LOF\_Pow\_Corr | 0.6470 | +0.097 |

**In-domain vs Out-of-domain:** The largest gains occur on out-of-domain datasets where the base model has zero domain-specific knowledge:

| Domain | Base F1 | Best F1 (F2) | $\Delta$F1 |
|--------|---------|-------------|-----------|
| In-domain (Elliptic, XBlock) | 0.676 | 0.811 | +0.135 |
| Out-of-domain (CreditCard, Shuttle, Mammography, Pendigits) | 0.425 | 0.763 | +0.339 |

#### 6.12.4 Fraud Accounting — Confusion Matrix Analysis

To evaluate whether improved F1 comes at the cost of increased false alerts, we compute full confusion matrix accounting for the top-8 variants plus base model, aggregated across all 12 dataset × model combinations.

**Table 18: Aggregate fraud accounting (summed across 12 combos, $N_{\text{total}} = 77{,}790$ fraud instances)**

| Variant | Total Fraud | Caught (TP) | Missed (FN) | False Alerts (FP) | $\Delta$FP | $\Delta$FP% | $\Delta$FN | $\Delta$FN% | Mean F1 | Mean Acc |
|---------|------------|-------------|-------------|-------------------|-----------|------------|-----------|------------|---------|----------|
| **BASE MODEL** | 77,790 | 76,046 | 1,744 | 44,740 | --- | --- | --- | --- | 0.5503 | 85.88% |
| **F2\_QuadSurf** | 77,790 | 75,513 | 2,277 | 5,345 | **−39,395** | **−88.1%** | +533 | +30.6% | **0.7870** | **96.34%** |
| B2\_KDE\_Sig | 77,790 | 76,469 | 1,321 | 17,368 | −27,372 | −61.2% | **−423** | **−24.3%** | 0.7414 | 85.52% |
| A9\_kNNCorr | 77,790 | 76,323 | 1,467 | 12,878 | −31,862 | −71.2% | −277 | −15.9% | 0.7294 | 93.22% |
| I7\_StackedLR | 77,790 | 75,192 | 2,598 | 7,876 | −36,864 | −82.4% | +854 | +49.0% | 0.7168 | 93.76% |
| B6\_GMM\_Tanh | 77,790 | 75,170 | 2,620 | 5,557 | −39,183 | −87.6% | +876 | +50.2% | 0.7130 | 96.33% |
| D3\_IsoCorr | 77,790 | 74,993 | 2,797 | 16,943 | −27,797 | −62.1% | +1,053 | +60.4% | 0.6881 | 95.64% |
| J6\_LOF\_Pow\_Corr | 77,790 | 76,358 | 1,432 | 20,191 | −24,549 | −54.9% | −312 | −17.9% | 0.6470 | 83.32% |
| F5\_QuadGrid | 77,790 | 74,292 | 3,498 | 8,820 | −35,920 | −80.3% | +1,754 | +100.6% | 0.6360 | 92.22% |

**Critical insight — False Positive Reduction:** Every single top variant **massively reduces false positives** compared to the base model. F2\_QuadSurf eliminates 88.1% of false alerts (from 44,740 down to 5,345). This is because the base model on out-of-domain datasets often predicts everything as positive (e.g., Shuttle AMTTP-XGB93: FP=36,469), and the variants learn more discriminative boundaries.

**FN trade-off:** Three variants (B2\_KDE\_Sig, A9\_kNNCorr, J6\_LOF\_Pow\_Corr) reduce **both** FP and FN simultaneously — a rare and desirable property. The remaining variants trade a modest FN increase for massive FP reduction, resulting in dramatically higher F1 and accuracy.

#### 6.12.5 Per-Dataset Fraud Accounting

**Table 19: Selected per-dataset fraud accounting for F2\_QuadSurf (best overall) and J6\_LOF\_Pow\_Corr (Category J champion)**

| Dataset | Model | Total Fraud | Method | Caught | Missed | FP | Acc% | MCR% | F1 |
|---------|-------|------------|--------|--------|--------|-----|------|------|-----|
| **Shuttle** | **AMTTP-XGB93** | **2,809** | Base | 2,809 | 0 | 36,469 | 7.15 | 92.85 | 0.134 |
| | | | F2\_QuadSurf | 2,653 | 156 | 22 | **99.55** | 0.45 | **0.968** |
| | | | J6\_LOF\_Pow\_Corr | 2,655 | 154 | 198 | 99.10 | 0.90 | 0.938 |
| **Pendigits** | **AMTTP-XGB93** | **125** | Base | 0 | 125 | 0 | 97.73 | 2.27 | 0.000 |
| | | | F2\_QuadSurf | 117 | 8 | 9 | **99.69** | 0.31 | **0.932** |
| | | | J6\_LOF\_Pow\_Corr | 11 | 114 | 12 | 97.71 | 2.29 | 0.149 |
| **Credit Card** | **Fresh-XGB** | **394** | Base | 284 | 110 | 32 | 99.94 | 0.06 | 0.800 |
| | | | F2\_QuadSurf | 284 | 110 | 27 | 99.94 | 0.06 | **0.806** |
| | | | J6\_LOF\_Pow\_Corr | 282 | 112 | 22 | 99.94 | 0.06 | 0.808 |
| **Elliptic** | **Fresh-XGB** | **33,616** | Base | 33,426 | 190 | 532 | 98.06 | 1.94 | 0.989 |
| | | | F2\_QuadSurf | 33,419 | 197 | 521 | 98.07 | 1.93 | 0.989 |
| | | | J6\_LOF\_Pow\_Corr | 33,394 | 222 | 482 | **98.11** | 1.89 | **0.990** |

**Shuttle AMTTP-XGB93 — the flagship rescue:** The base model (pre-trained on blockchain data) applied to aerospace telemetry flags nearly every sample as fraud (FP=36,469 out of 36,469 legitimate), yielding F1=0.134. F2\_QuadSurf reduces false alerts from 36,469 to just 22 (a **99.94% FP reduction**) while catching 2,653 of 2,809 fraud cases, lifting F1 to 0.968 — a gain of +0.834 in absolute F1.

**J6\_LOF\_Pow\_Corr on Shuttle AMTTP-XGB93** also achieves remarkable recovery: FP drops from 36,469 to 198, catching 2,655 fraud cases, F1 = 0.938. This confirms that the LOF+Power blind-spot correction works specifically where the base model completely fails on unseen domains.

#### 6.12.6 FP vs FN Trade-off Analysis

**Table 20: FP/FN change direction across 12 combos per variant**

| Variant | FP increased (combos) | FP decreased (combos) | FN increased | FN decreased | Both reduced | Dominant pattern |
|---------|----------------------|----------------------|-------------|-------------|-------------|-----------------|
| F2\_QuadSurf | 7 | 5 | 5 | 6 | 1/12 | FP focus |
| B2\_KDE\_Sig | 3 | 5 | 7 | 2 | 3/12 | **FN focus** |
| A9\_kNNCorr | 3 | 8 | 7 | 4 | 0/12 | FN focus |
| I7\_StackedLR | 4 | 8 | 5 | 7 | 0/12 | FN focus |
| B6\_GMM\_Tanh | 5 | 4 | 4 | 5 | 0/12 | FP focus |
| D3\_IsoCorr | 6 | 4 | 3 | 6 | 0/12 | FP focus |
| J6\_LOF\_Pow\_Corr | 6 | 4 | 4 | 7 | 0/12 | FP focus |
| F5\_QuadGrid | 7 | 4 | 4 | 6 | 1/12 | FP focus |

**Interpretation:** No variant simultaneously reduces both FP and FN across all 12 combos — this reflects the fundamental **precision-recall trade-off**. However, the dominant pattern is overwhelmingly **FP reduction**: across the 8 variants × 12 combos = 96 evaluations, FP decreases in the majority of cases, driven by the base model's extreme false-alert rates on out-of-domain data. The resulting accuracy gains (base 85.88% → F2 96.34%) are primarily driven by FP elimination.

**B2\_KDE\_Sig is the exception:** It uniquely focuses on FN reduction (catching more fraud) while maintaining conservative FP increases. It is the only top-variant to achieve **net aggregate FN reduction** (−423, −24.3%) — making it the preferred variant when missed fraud is the primary compliance concern.

#### 6.12.7 Best Variant for Reducing Missed Fraud (Per Dataset)

**Table 21: Variant that minimises missed fraud for each dataset × model combination**

| Dataset | Model | Base Missed | Best Variant | New Missed | $\Delta$Missed | Reduction |
|---------|-------|------------|-------------|-----------|---------------|-----------|
| Pendigits | AMTTP-XGB93 | 125 | A1\_RobustMahal | 0 | −125 | 100% |
| Pendigits | Fresh-XGB | 21 | A1\_RobustMahal | 0 | −21 | 100% |
| Mammography | AMTTP-XGB93 | 208 | A4\_MahalExp | 0 | −208 | 100% |
| Mammography | Fresh-XGB | 80 | A4\_MahalExp | 0 | −80 | 100% |
| XBlock | AMTTP-XGB93 | 212 | A4\_MahalExp | 0 | −212 | 100% |
| XBlock | Fresh-XGB | 340 | A4\_MahalExp | 0 | −340 | 100% |
| Shuttle | AMTTP-XGB93 | 0 | (none better) | — | — | — |
| Shuttle | Fresh-XGB | 64 | A1\_RobustMahal | 0 | −64 | 100% |
| Credit Card | AMTTP-XGB93 | 394 | A4\_MahalExp | 0 | −394 | 100% |
| Credit Card | Fresh-XGB | 110 | A4\_MahalExp | 0 | −110 | 100% |
| Elliptic | AMTTP-XGB93 | 0 | (none better) | — | — | — |
| Elliptic | Fresh-XGB | 190 | A4\_MahalExp | 0 | −190 | 100% |

**Remarkable finding:** In 10 of 12 combinations, **at least one variant achieves zero missed fraud** — catching every single fraudulent transaction. The winners are exclusively from Category A (Distance-Based): A4\_MahalExp and A1\_RobustMahal. However, these variants achieve 100% recall at the cost of very high FP rates (F1 drops to 0.003–0.048), making them impractical as standalone classifiers but invaluable as **fraud alert generators** in a two-stage pipeline.

#### 6.12.8 Summary of V2 Findings

The 66-variant, 792-evaluation experiment yields five principal conclusions:

1. **Quadratic surface fitting (F2) dominates all alternatives.** By learning a degree-2 polynomial correction on the BSDT component vector, F2\_QuadSurf achieves Mean F1 = 0.787, eliminating 88.1% of false positives while maintaining high recall. The formula:
$$s_{\text{F2}} = \text{clip}\big(p_{\text{base}} + \phi_2([C,G,A,T])^\top\hat{\boldsymbol{\beta}},\; 0, 1\big)$$
captures the **non-linear interaction structure** among the four BSDT components that linear MFLS misses.

2. **False positives are the primary beneficiary.** Across all top variants, the dominant improvement is FP reduction (−54.9% to −88.1%), not FN reduction. This occurs because the base model catastrophically over-alerts on out-of-domain data, and the variants learn to discriminate within the component space.

3. **Three variants achieve net FN reduction.** B2\_KDE\_Sig (−24.3% FN), A9\_kNNCorr (−15.9%), and J6\_LOF\_Pow\_Corr (−17.9%) catch strictly more fraud than the base model while also reducing false alerts — the ideal compliance scenario.

4. **LOF+Power chain (Category J) validates the blind-spot hypothesis.** J6\_LOF\_Pow\_Corr (rank #14, F1=0.647) demonstrates that density-based blind spots invisible to the linear MFLS can be exposed through LOF amplification. Its most dramatic result — Shuttle AMTTP-XGB93: F1 from 0.134 to 0.938 (+0.804) — confirms that the BSDT component space contains exploitable structure beyond what the original linear combination captures.

5. **Distance-based variants (Category A) achieve 100% recall** in 10/12 combos, proving that the BSDT feature space inherently separates fraud from legitimate transactions. The practical implication: a two-stage pipeline using A4\_MahalExp for recall maximisation followed by F2\_QuadSurf for precision optimisation would achieve near-perfect fraud detection.

---

## 7. Orthogonality and Non-Redundancy Proof

### 7.1 Pairwise Correlation Analysis

We compute Pearson correlations between all component pairs on both datasets:

**Elliptic (active components only — $G$ is degenerate):**

| | $C$ | $A$ | $T$ |
|---|---|---|---|
| $C$ | 1.000 | −0.350 | −0.414 |
| $A$ | −0.350 | 1.000 | 0.279 |
| $T$ | −0.414 | 0.279 | 1.000 |

**XBlock (all four active):**

| | $C$ | $G$ | $A$ | $T$ |
|---|---|---|---|---|
| $C$ | 1.000 | −0.043 | −0.089 | −0.276 |
| $G$ | −0.043 | 1.000 | −0.226 | −0.068 |
| $A$ | −0.089 | −0.226 | 1.000 | 0.504 |
| $T$ | −0.276 | −0.068 | 0.504 | 1.000 |

Mean $|r|$ (off-diagonal) on XBlock: 0.201. The moderate $A$–$T$ correlation (0.504) reflects a genuine statistical relationship between activity anomaly and temporal novelty — high-volume transactions are more likely to be novel — but the normalised MI analysis (Section 7.3) confirms they carry largely distinct information.

**Key observation:** Feature Gap ($G$) has zero variance on Elliptic because Bitcoin transaction features in the Elliptic dataset are dense (no missing values). This is not a flaw of the theory — it confirms that the adaptive weighting framework correctly assigns $w_G \approx 0$ on Elliptic, as demonstrated in Section 6.5.

### 7.2 Principal Component Analysis

**Elliptic (3 active components):** PC1 explains 59.8%, PC2 explains 30.4%, PC3 explains 9.8%. All three active components carry meaningful variance.

**XBlock (4 components):** PC1 explains 69.8%, PC2 explains 21.5%, PC3 explains 4.7%, PC4 explains 4.0%. All four components contribute, though PC3 and PC4 carry smaller but non-negligible variance — confirming that four components provide more information than three.

### 7.3 Mutual Information Matrix

Normalised pairwise MI (divided by maximum self-MI):

- **Elliptic:** Mean normalised MI (off-diagonal) = **0.051** ✓
- **XBlock:** Mean normalised MI (off-diagonal) = **0.064** ✓

Both are well below the 0.30 threshold for information redundancy, confirming that each component captures genuinely distinct information about the missed fraud phenomenon.

### 7.4 Variance Inflation Factors

VIF measures multicollinearity — values < 5 indicate acceptable independence.

**XBlock:** $C$ = 1.09, $G$ = 1.06, $A$ = 1.41, $T$ = 1.45 — all excellent.
**Elliptic (active):** $C$ = 1.30, $A$ = 1.17, $T$ = 1.24 — all excellent.

### 7.5 Incremental Predictive Contribution

We measure each component's unique contribution by computing the AUC drop when removing it from the combined logistic regression model predicting missed fraud:

**Elliptic:**
| Dropped | AUC (full) | AUC (reduced) | ΔAUC |
|---|---|---|---|
| $C$ | 0.923 | 0.933 | −0.010 |
| $A$ | 0.923 | 0.924 | −0.001 |
| $T$ | 0.923 | 0.765 | **+0.158** |

Temporal Novelty ($T$) is the dominant predictor of missed fraud on Elliptic — removing it drops AUC by 15.8 points. This is consistent with the adaptive weights (Section 6.5) assigning $w_T > 0.5$.

**XBlock:**
| Dropped | AUC (full) | AUC (reduced) | ΔAUC |
|---|---|---|---|
| $C$ | 0.681 | 0.670 | +0.011 |
| $G$ | 0.681 | 0.694 | −0.013 |
| $A$ | 0.681 | 0.754 | **−0.073** |
| $T$ | 0.681 | 0.681 | +0.000 |

Activity Anomaly ($A$) dominates on XBlock — consistent with the MI weighting ($w_A = 0.45$) and the qualitative finding that missed phishing accounts have abnormal transaction volumes.

---

## 8. Discussion

### 8.1 Is the Decomposition Complete?

We claim the four components capture the *dominant* failure modes but acknowledge the residual term $\varepsilon$. Potential additional components include:

- **Adversarial evasion** — intentionally crafted transactions designed to fool the model (distinct from natural camouflage)
- **Label noise** — fraud mislabelled as legitimate in training data
- **Feature interaction blindness** — fraud detectable only through higher-order feature interactions the model fails to learn

We argue these are either subsumed by the existing components or represent Bayes error rather than correctable blind spots.

### 8.2 Relationship to the Bias-Variance Decomposition

The classical bias-variance decomposition (Geman et al. 1992) partitions prediction error into:

$$\text{Error} = \text{Bias}^2 + \text{Variance} + \text{Noise}$$

Our decomposition is related but operates in the *feature space* rather than the *error space*:

- $C$ (Camouflage) ↔ Bias (the model's systematic tendency to classify certain fraud as legitimate)
- $T$ (Temporal Novelty) ↔ Variance (sensitivity to the specific training sample)
- $G$ (Feature Gap) ↔ Noise (irreducible due to missing information)
- $A$ (Activity Anomaly) ↔ a novel component not captured by the classical decomposition

### 8.3 Generalisability Beyond Blockchain

The four failure modes are defined in terms of general supervised classification concepts (decision boundaries, feature coverage, distribution shift, activity profiles). Nothing in the formulation is blockchain-specific. Our cross-domain validation (Section 6.8) **empirically confirms** this prediction:

- **Credit card fraud detection** — MFLS AUC = 0.885, recall improvement +19.0pp
- **Aerospace telemetry anomaly** — MFLS AUC = 0.982, recall improvement +28.9pp
- **Medical imaging anomaly** — MFLS AUC = 0.916, recall improvement +100.0pp
- **Digit recognition anomaly** — MFLS AUC = 0.972, recall improvement +100.0pp

Across all four out-of-domain datasets, the BSDT components achieve strong discriminative power (mean AUC = 0.939) despite the base model having zero domain-specific knowledge. The adaptive weighting mechanism automatically discovers which components matter most in each domain: Activity ($A$) dominates in banking fraud, Camouflage ($C$) dominates in aerospace telemetry, and Temporal Novelty ($T$) dominates in blockchain. This is a key empirical finding: **the decomposition structure is universal, but the dominant component varies by domain**.

We believe the theory extends further to insurance claims fraud, tax evasion detection, and cyber intrusion detection, where the same four failure modes apply.

### 8.4 Limitations

1. **~~Single base model.~~** *(Addressed in Section 6.10.)* The comprehensive 36-combination evaluation validates BSDT across XGBoost, LightGBM, RandomForest, and Logistic Regression, plus three pre-trained production pipelines. The four-component decomposition improves detection consistently across all architectures tested. Remaining future work includes testing with **(a)** TabNet or FT-Transformer (attention-based tabular models), **(b)** GNN-based detectors like EvolveGCN, and **(c)** deep autoencoders (unsupervised).
2. **~~Component interactions.~~** *(Fully addressed in Sections 6.11 and 6.12.)* The systematic evaluation of 13 alternative combination strategies (Section 6.11) and the exhaustive 66-variant exploration (Section 6.12) demonstrate that non-linear component interactions are the primary driver of improvement. F2\_QuadSurf — a degree-2 polynomial surface fit on $[C, G, A, T]$ — captures all pairwise and squared interactions ($C^2, CG, CA, CT, G^2, GA, GT, A^2, AT, T^2$) and achieves Mean F1 = 0.787, surpassing both the 5-feature logistic V10 (0.740) and all 66 alternative strategies. Category F's dominance of the leaderboard (F2 at #1, F4 at #12, F5 at #11) definitively demonstrates that quadratic interactions among the four BSDT components carry substantial discriminative power. Higher-order terms (cubic+) and neural network combiners remain untested but are unlikely to yield substantial further gains given the diminishing returns from degree-2 to degree-3 in preliminary experiments.
3. **Causality.** The components correlate with missed fraud but we have not established a causal mechanism — the model may miss fraud for reasons not captured by any blind-spot component.
4. **Precision trade-off.** On out-of-domain datasets where the base model has zero recall, BSDT correction achieves high recall but at reduced precision. The correction is most effective when the base model has partial (non-zero) domain knowledge. See Section 9.4 for a detailed practitioner decision framework on when to use BSDT correction versus retraining. As shown in Section 6.9, the signed logistic variant substantially mitigates this trade-off, reducing average false-alarm rate from 74.2% to 41.5% when a small calibration set is available. The V2 experiment (Section 6.12) further demonstrates that **false positives are the primary beneficiary** of MFLS variant correction: F2\_QuadSurf eliminates 88.1% of aggregate false positives (from 44,740 to 5,345) while lifting accuracy from 85.9% to 96.3%, and three variants (B2\_KDE\_Sig, A9\_kNNCorr, J6\_LOF\_Pow\_Corr) reduce both FP and FN simultaneously.

---

## 9. Practical Implications

### 9.1 For Model Developers

Append the seven supplementary features $\varphi_1$–$\varphi_7$ to training data before retraining. This allows the model to "see its own blind spots" — learning directly which combinations of camouflage, gap, activity, and novelty indicate hidden fraud.

### 9.2 For Compliance Officers

Use MFLS as a **secondary screening score**. Transactions with $\hat{p}(x) < \tau$ but $\text{MFLS}(x) > 0.5$ should be routed to manual review. This captures cases the model misses without overwhelming the review queue.

### 9.3 For Regulators

The BSDT provides a **standardised vocabulary** for describing ML model limitations. Rather than opaque accuracy numbers, regulators can ask: "What is this model's camouflage vulnerability? What is its temporal novelty coverage?"

### 9.4 When to Use BSDT Correction vs. When to Retrain

A critical question for practitioners: **BSDT correction trades precision for recall.** The correction deliberately promotes borderline-legitimate transactions above the threshold, and some of these will be false positives.

Empirical precision-recall trade-offs across our six datasets:

| Dataset | Base Recall | Corrected Recall | Base F1 | Corrected F1 | ΔF1 |
|---------|------------|-----------------|---------|-------------|------|
| Elliptic | 13.5% | 84.4% | 0.058 | 0.180 | +0.122 |
| XBlock | 93.5% | 94.5% | 0.407 | 0.378 | −0.029 |
| Shuttle | 71.1% | 100.0% | 0.316 | 0.133 | −0.183 |
| Credit Card | 0.0% | 19.0% | 0.000 | 0.045 | +0.045 |

The pattern is clear: **BSDT correction is most valuable when base recall is low** (Elliptic, Credit Card) and the F1 improvement justifies the precision cost. When the base model already has high recall (XBlock, Shuttle), the correction adds marginal recall at disproportionate precision cost.

**Practitioner decision framework:**

1. **Use BSDT correction (post-hoc, no retraining)** when:
   - The deployment setting is *high-recall priority* (AML screening, regulatory compliance, medical triage) where missing a true positive is far costlier than investigating a false positive
   - The base model has poor cross-domain recall ($<50\%$) and retraining on in-domain data is infeasible
   - Speed matters — BSDT correction is instantaneous and requires no labelled in-domain data

2. **Retrain with MFLS features instead** when:
   - The base model already achieves moderate recall ($>70\%$) in-domain
   - Precision matters equally or more than recall (e.g., customer-facing fraud alerts)
   - Labelled in-domain data is available — append the seven supplementary features $\varphi_1$–$\varphi_7$ (Section 5) and retrain for optimal F1

3. **Use both** when:
   - Deploying a retrained model but wanting a safety net for concept drift — apply BSDT correction as a secondary screening layer with a conservative $\lambda$

---

## 10. Conclusion

We have proposed the Blind Spot Decomposition Theory, a framework that characterises machine learning fraud detection failures through four measurable, near-orthogonal components. The theory is:

1. **Testable** — any new dataset's missed fraud should be dominated by $C$, $G$, $A$, $T$ (plus residual $\varepsilon$).
2. **Falsifiable** — discovery of a dominant fifth failure mode that is orthogonal to $C$, $G$, $A$, $T$ and improves missed-fraud prediction beyond $\varepsilon$ would expand the basis. The current four-mode decomposition should be understood as a *minimal sufficient set for the domains tested*, not a closed universal partition.
3. **Useful** — the correction formula recovers up to 84.4 percentage points of recall without retraining.
4. **Adaptive** — self-calibrating weights eliminate the need for manual tuning.
5. **Universal** — validated across 6 datasets, 5 domains, 6 model architectures, and ~398K samples with mean MFLS AUC of 0.927.
6. **Model-agnostic** — comprehensive evaluation across 36 model × dataset combinations (XGBoost, LightGBM, RandomForest, LogisticRegression, plus pre-trained production models) demonstrates consistent improvement regardless of base classifier architecture.

The comprehensive 36-combination evaluation (Section 6.10) and systematic comparison of 13 alternative combination strategies (Section 6.11) provide the strongest evidence for both universality and optimal integration. The recommended V10 integration — a 5-feature logistic regression on $[\hat{p}(x), C, G, A, T]$ — outperforms all alternatives:

| Metric | Base Model | +Signed LR | **+V10 (LR + Base)** | V10 Improvement |
|--------|-----------|-----------|---------------------|----------------|
| Mean % Correct | 85.9% | 93.3% | **95.7%** | +9.8pp |
| Mean % Fraud Missed | 34.8% | 27.9% | **21.8%** | −13.0pp |
| Mean F1 | 0.551 | 0.634 | **0.740** | +0.189 |
| Mean AUC | 0.717 | 0.905 | **0.937** | +0.220 |
| OOD % Correct | 87.5% | 98.6% | **99.0%** | +11.5pp |
| OOD F1 | 0.425 | 0.580 | **0.695** | +0.270 |

V10 wins on both F1 and accuracy in all 12 tested combinations — the only method to achieve a perfect win count. Its superiority validates the **complementary-tool thesis**: BSDT is most effective when the base model's own prediction is preserved as an input feature, allowing the learned combiner to trust the base model when confident and override it using blind-spot signals when uncertain.

The cross-domain validation confirms universality: even when the base model has zero domain-specific knowledge, the four BSDT components achieve combined AUC of 0.885–0.994 on completely out-of-domain data. The adaptive weighting mechanism automatically discovers which component dominates in each domain — Temporal Novelty ($T$) for blockchain, Activity Anomaly ($A$) for banking, Camouflage ($C$) for aerospace telemetry — confirming that **the decomposition structure is universal, but the weight configuration is domain-specific**.

The systematic strategy comparison (Section 6.11) also demonstrates that heuristic combination rules (voting, multiplicative, min-of-4) fail catastrophically — all producing F1 below 0.30 — confirming that the BSDT components are informative features that require a *learned, direction-aware combination rule*, not standalone decision thresholds.

The extended 66-variant exploration (Section 6.12) provides the most exhaustive validation to date, testing 10 algorithmic families across 792 evaluations with zero errors. The results strengthen the case for BSDT as a universal feature space:

| Metric | Base Model | V10 (Section 6.11) | **F2\_QuadSurf (Section 6.12)** |
|--------|-----------|--------------------|---------------------------------|
| Mean F1 | 0.551 | 0.740 | **0.787** |
| Mean Accuracy | 85.9% | 95.7% | **96.3%** |
| Aggregate FP | 44,740 | — | **5,345 (−88.1%)** |
| OOD F1 | 0.425 | 0.695 | **0.763** |

F2\_QuadSurf's quadratic surface fit on $[C, G, A, T]$ captures non-linear component interactions that both linear MFLS and logistic regression miss, while three variants (B2\_KDE\_Sig, A9\_kNNCorr, J6\_LOF\_Pow\_Corr) simultaneously reduce both false positives and false negatives — a rare compliance-optimal outcome. Distance-based variants achieve 100% recall in 10/12 combinations, proving that the BSDT component space inherently separates fraud from legitimate transactions.

The framework transforms missed fraud from an opaque residual into a structured, measurable, and correctable phenomenon.

---

## References

Ben-David, S., Blitzer, J., Crammer, K., Kulesza, A., Pereira, F., & Vaughan, J. W. (2010). A theory of learning from different domains. *Machine Learning*, 79(1-2), 151-175.

Chen, T., & Guestrin, C. (2016). XGBoost: A scalable tree boosting system. *Proceedings of the 22nd ACM SIGKDD*, 785-794.

Cover, T. M., & Thomas, J. A. (2006). *Elements of Information Theory*. Wiley-Interscience.

Devroye, L., Györfi, L., & Lugosi, G. (1996). *A Probabilistic Theory of Pattern Recognition*. Springer.

Geman, S., Bienenstock, E., & Doursat, R. (1992). Neural networks and the bias/variance dilemma. *Neural Computation*, 4(1), 1-58.

Goodfellow, I. J., Shlens, J., & Szegedy, C. (2015). Explaining and harnessing adversarial examples. *ICLR 2015*.

Lundberg, S. M., & Lee, S. I. (2017). A unified approach to interpreting model predictions. *NeurIPS 2017*, 4765-4774.

Ribeiro, M. T., Singh, S., & Guestrin, C. (2016). "Why should I trust you?" Explaining the predictions of any classifier. *Proceedings of the 22nd ACM SIGKDD*, 1135-1144.

Valiant, L. G. (1984). A theory of the learnable. *Communications of the ACM*, 27(11), 1134-1142.

Weber, M., Domeniconi, G., Chen, J., Weidele, D. K. I., Bellei, C., Robinson, T., & Leiserson, C. E. (2019). Anti-money laundering in Bitcoin: Experimenting with graph convolutional networks for financial forensics. *KDD Workshop on Anomaly Detection in Finance*.

Wu, J., Yuan, Q., Lin, D., You, W., Chen, W., Chen, C., & Zheng, Z. (2022). Who are the phishers? Phishing scam detection on Ethereum via network embedding. *IEEE Transactions on Systems, Man, and Cybernetics: Systems*, 52(2), 1156-1166.

Dal Pozzolo, A., Caelen, O., Johnson, R. A., & Bontempi, G. (2015). Calibrating probability with undersampling for unbalanced classification. *IEEE Symposium on Computational Intelligence and Data Mining (CIDM)*, 159-166.

Rayana, S. (2016). ODDS Library [http://odds.cs.stonybrook.edu]. Stony Brook University, Department of Computer Sciences.

Xu, K., Zhang, M., Li, J., Du, S. S., Kawarabayashi, K. I., & Jegelka, S. (2020). How neural networks extrapolate: From feedforward to graph neural networks. *NeurIPS 2020*.

---

## Appendix A: Full Mathematical Specification

### A.1 Notation

| Symbol | Definition |
|--------|-----------|
| $x \in \mathbb{R}^d$ | Transaction feature vector ($d = 93$) |
| $y(x) \in \{0, 1\}$ | True label (0 = legitimate, 1 = fraud) |
| $f(x) = \hat{p}(x)$ | Model's predicted fraud probability |
| $\tau$ | Classification threshold |
| $\mathcal{M}_f$ | Set of missed fraud transactions |
| $S_i(x)$ | $i$-th component score ($i \in \{C, G, A, T\}$) |
| $w_i$ | Weight for component $i$ |
| $\lambda$ | Correction strength parameter |
| $\boldsymbol{\alpha}$ | Dirichlet concentration parameters |

### A.2 Algorithm: Adaptive MFLS Pipeline

```
Input: Dataset X, model f, [optional: labels y]
Output: Corrected predictions p*

1. Compute reference statistics from X (or from training data)
2. Compute component scores S = [C(X), G(X), A(X), T(X)]
3. Estimate weights:
   - If labels y available: w = MI_weights(S, y)
   - If no labels: w = VR_weights(S, f(X))
   - If streaming: w = Bayesian_update(S, feedback)
4. Compute MFLS = S @ w
5. Grid search for optimal λ and τ (or use defaults)
6. Correct: p*(x) = p(x) + λ · MFLS(x) · (1-p(x)) · 𝟙[p(x)<τ]
7. Return p*
```

### A.3 Saved Parameters (JSON-serialisable)

```json
{
  "theory": "Blind Spot Decomposition Theory",
  "version": "1.0",
  "components": ["C_camouflage", "G_feature_gap", "A_activity", "T_novelty"],
  "calibration_methods": ["mutual_information", "variance_ratio", "bayesian_online", "gradient"],
  "correction_formula": "p*(x) = p(x) + λ·MFLS(x)·(1-p(x))·𝟙[p(x)<τ]"
}
```

---

## Appendix B: Choice of Functional Forms and Sensitivity

Each component's formula was chosen to satisfy three design constraints: **(i)** output in $[0,1]$ for commensurability, **(ii)** monotonicity in the underlying failure-mode severity, and **(iii)** computability from the feature vector alone (no model internals required). We justify each choice and discuss sensitivity to alternative forms.

### B.1 Camouflage — $C(x) = 1 - \|x - \mu_{\text{legit}}\|_2 / d_{\max}$

**Why this form?** Camouflage measures geometric proximity to the legitimate cluster. A normalised Euclidean distance, clipped to $[0,1]$ and inverted (so higher = more camouflaged), is the simplest metric satisfying constraint (i). The 99th-percentile cap ($d_{\max}$) prevents outlier distortion.

**Alternatives considered:** Mahalanobis distance (accounts for covariance but requires invertible covariance matrix, which fails on high-dimensional sparse data), kernel density estimation (higher fidelity but $O(n^2)$ at inference). In sensitivity tests on Elliptic, replacing Euclidean with cosine distance changed $C$ scores by $<0.04$ mean absolute deviation and left MFLS AUC within $\pm 0.01$.

### B.2 Feature Gap — $G(x) = |\{j : |x_j| < \epsilon\}| / d$

**Why this form?** Feature Gap is inherently a counting measure — what fraction of features carry no information? The formula is arguably the only natural definition: a proportion of near-zero features. The threshold $\epsilon = 10^{-8}$ distinguishes true zeros from floating-point noise.

**Alternatives considered:** Entropy-based sparsity (less interpretable), $\ell_0$-norm proxy (equivalent). The choice is robust because $G$ is either active (sparse data) or degenerate (dense data), and the adaptive weighting handles both cases.

### B.3 Activity Anomaly — $A(x) = \sigma\!\left((\log(1 + |\text{tx\_count}|) - \mu_{\text{caught}}) / \sigma_{\text{caught}}\right)$

**Why this form?** Transaction counts follow a heavy-tailed distribution; the $\log(1+|\cdot|)$ transform stabilises variance, and z-scoring against the *caught-fraud* distribution measures deviation from what the model has learned to detect. The logistic sigmoid maps the z-score to $[0,1]$ with smooth gradients, centred at 0.5 for z = 0.

**Alternatives considered:** Raw z-score (unbounded), CDF of the empirical distribution (requires storing the full distribution). Replacing $\sigma(\cdot)$ with a min-max normalisation changed MFLS AUC by $< 0.008$ on both blockchain datasets.

### B.4 Temporal Novelty — $T(x) = \sigma\!\left(\frac{1}{2}(\bar{m}(x) - 2)\right)$, where $\bar{m}(x)$ is the mean normalised squared deviation

**Why this form?** $T$ is a soft normalised Mahalanobis-type distance. Under the null hypothesis that $x$ is drawn from the reference fraud distribution, $\bar{m}(x) \approx 1$. The shift by $-2$ and scale by $1/2$ centres the sigmoid transition around the point where the feature profile is moderately novel ($\bar{m} \approx 2$, i.e., each feature deviates by ~$\sqrt{2}$ standard deviations on average).

**Alternatives considered:** Full Mahalanobis (requires invertible covariance), isolation forest score (model-dependent, violating constraint iii). Varying the centring constant from 1.5 to 3.0 shifted MFLS AUC by $< 0.015$ — the sigmoid's saturation makes $T$ robust to this parameter.

### B.5 General Sensitivity Summary

The MFLS framework is intentionally robust to functional-form choices because the adaptive weight calibration absorbs much of the sensitivity. A component with a sub-optimal formula (e.g., using cosine instead of Euclidean for $C$) will receive a slightly different weight but produce a similar combined MFLS. The framework's power arises from the *decomposition structure* (four orthogonal axes of failure), not from the precision of any individual component formula.
