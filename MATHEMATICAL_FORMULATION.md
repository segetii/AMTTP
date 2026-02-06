# AMTTP: Mathematical Formulation & Cryptographic Primitives

## 1. Variational Autoencoder (VAE) for Latent Anomaly Detection

To detect non-linear anomalies in the transaction feature space $\mathcal{X}$, we employ a $\beta$-VAE. This model learns a compressed latent representation $z$ of legitimate transactions, where anomalies are identified by high reconstruction error.

### 1.1 Objective Function (ELBO)
The training objective maximizes the Evidence Lower Bound (ELBO) with a weight $\beta$ on the KL divergence term (i.e., a $\beta$-VAE).

$$
\mathcal{L}_{\beta\text{-VAE}}(\theta, \phi; x) = \mathbb{E}_{q_\phi(z|x)}[\log p_\theta(x|z)] - \beta D_{KL}(q_\phi(z|x) || p(z))
$$

Where:
*   $x$ is the input transaction feature vector.
*   $q_\phi(z|x)$ is the probabilistic encoder (approximate posterior).
*   $p_\theta(x|z)$ is the decoder likelihood term in the ELBO; in this workspace it is instantiated via an MSE reconstruction surrogate.
*   In the implementation, the reconstruction term is computed as **mean squared error** (MSE):
	$$ \mathcal{L}_{recon} = ||x - \hat{x}(z)||^2 $$
	This is equivalent (up to additive/scale constants) to a Gaussian decoder with fixed variance.
*   $p(z) = \mathcal{N}(0, I)$ is the prior distribution.
*   $\beta = 4.0$ (as implemented in `vae_gnn_pipeline.ipynb`).

The reconstruction loss (first term) measures how well the transaction matches the patterns learned from the training data.

### 1.2 The Reparameterization Trick & Analytical KL
To facilitate backpropagation through the stochastic sampling processes of the latent variable $z$, we employ the reparameterization trick. Instead of sampling $z$ directly from the distribution, we sample an auxiliary noise variable $\epsilon$ and transform it:

$$
z = \mu_\phi(x) + \sigma_\phi(x) \odot \epsilon, \quad \text{where } \epsilon \sim \mathcal{N}(0, \mathbf{I})
$$

This renders the sampling operation differentiable with respect to $\phi$. Furthermore, since we enforce a Gaussian prior $p(z) = \mathcal{N}(0, I)$, the Kullback-Leibler divergence term has a closed-form analytical solution, avoiding high-variance Monte Carlo estimation:

$$
D_{KL}(q_\phi(z|x) || p(z)) = -\frac{1}{2} \sum_{j=1}^{J} \left( 1 + \log(\sigma_j^2) - \mu_j^2 - \sigma_j^2 \right)
$$

### 1.3 Anomaly Score (Reconstruction Probability)
In the implementation, anomaly is scored directly by the per-sample reconstruction error (mean squared error), computed after training the VAE on normal-only data:

$$
s_{vae}(x_i) = \mathrm{MSE}(x_i, \hat{x}_i) = \frac{1}{d}\sum_{j=1}^{d} (x_{ij} - \hat{x}_{ij})^2
$$

If one assumes a Gaussian decoder with fixed variance, the negative log-likelihood is proportional to this MSE up to an additive/scale constant; therefore ranking by $s_{vae}$ matches ranking by the (fixed-variance) NLL.

---

## 2. Graph Learning (VGAE + GATv2)

The implemented graph stack in `vae_gnn_pipeline.ipynb` consists of:

1. **VGAE (Variational Graph Autoencoder)** to learn unsupervised structural embeddings.
2. **GATv2** to perform supervised fraud classification, with **MC Dropout** used to estimate epistemic uncertainty.

### 2.1 VGAE (Unsupervised Graph Structure)
Let $G=(V,E)$ be the transaction graph with node features $X$ (augmented with the VAE reconstruction error) and edge index $E$. The VGAE encoder parameterizes a node-wise Gaussian latent variable using GCN layers:

$$
q_\phi(z_v|X,E) = \mathcal{N}(\mu_v, \mathrm{diag}(\sigma_v^2))
$$

The VGAE training objective used is the standard reconstruction + KL regularization:

$$
\mathcal{L}_{VGAE} = \mathcal{L}_{recon}(Z,E) + \lambda\, D_{KL}(q_\phi(Z|X,E)\,||\,p(Z))
$$

In the notebook, the reconstruction term is implemented as `vgae.recon_loss(z, edge_index)` with a small KL weight (e.g., $\lambda=10^{-4}$).

After training, an edge reconstruction matrix is decoded for all node pairs, and a per-node structural anomaly score is computed as the mean reconstructed connectivity:

$$
s_{edge}(v) = \frac{1}{|V|}\sum_{u \in V} \hat{A}_{vu}
$$

The VGAE node embedding used downstream is the concatenation of latent structure and this edge score:

$$
h_{v}^{VGAE} = [z_v \;||\; s_{edge}(v)]
$$

### 2.2 GATv2 (Supervised Fraud Classification)
The supervised GNN is a multi-layer GATv2 network. For each node $v$, attention coefficients over neighbors are computed via a learned scoring function and normalized using a neighborhood softmax:

$$
\alpha_{vu} = \frac{\exp(e_{vu})}{\sum_{k \in \mathcal{N}(v)} \exp(e_{vk})}
$$

The model outputs a logit $\ell_v$ and a probability

$$
p_{GAT}(v) = \sigma(\ell_v)
$$

### 2.3 Uncertainty via MC Dropout
To quantify prediction uncertainty, inference is repeated with dropout enabled (Monte Carlo Dropout). With $T$ stochastic passes, the calibrated point estimate and uncertainty are:

$$
\hat{p}(v) = \frac{1}{T}\sum_{t=1}^{T} p^{(t)}(v), \qquad u(v)=\sqrt{\mathrm{Var}_{t}(p^{(t)}(v))}
$$

---

## 3. Gradient Boosting Learners (XGBoost + LightGBM)

The implemented pipeline uses tree-based Gradient Boosting Machines (XGBoost/LightGBM) alongside neural components, and combines their outputs via ensembling/stacking in the notebook and script paths described below.

### 3.1 XGBoost Objective (Regularized)
XGBoost minimizes a regularized objective function, combining convex loss $l$ and a penalty $\Omega$ for model complexity (number of leaves $T$ and leaf weights $w$).

$$
\mathcal{L}^{(t)} = \sum_{i=1}^n l(y_i, \hat{y}_i^{(t-1)} + f_t(x_i)) + \Omega(f_t)
$$

$$
\Omega(f) = \gamma T + \frac{1}{2}\lambda ||w||^2
$$

By using the second-order Taylor expansion, we optimize the tree structure $q$ based on gradients $g_i$ and Hessians $h_i$:

$$
\mathcal{L}^{(t)} \approx \sum_{i=1}^n [l(y_i, \hat{y}^{(t-1)}) + g_i f_t(x_i) + \frac{1}{2}h_i f_t^2(x_i)] + \Omega(f_t)
$$

### 3.2 LightGBM (GOSS & EFB)
LightGBM contributes speed and accuracy via **Gradient-based One-Side Sampling (GOSS)**, which prioritizes training instances with large gradients (high error), and **Exclusive Feature Bundling (EFB)**, which reduces sparsity.

---

## 4. Risk Scoring: Implemented Fusion Paths

There are three concrete scoring paths implemented in the workspace:

1. **Full meta-ensemble stacking (research notebook)** in `vae_gnn_pipeline.ipynb`.
2. **Recalibrated XGBoost inference (scripted production fallback)** in `scripts/recalibrated_inference.py`.
3. **Hybrid multi-signal inference API (production-style)** in `ml/Automation/ml_pipeline/inference/hybrid_api.py`.

### 4.1 Full Meta-Ensemble (Logistic Regression Stacking)
In the notebook, the final risk probability is produced by a logistic regression meta-learner trained on the stacked model outputs/features:

$$
m(x) = \big[\; s_{vae}(x),\; s_{edge}(x),\; p_{GAT}(x),\; u(x),\; p_{XGB}(x),\; p_{LGB}(x) \;\big]^\top
$$

$$
R_{meta}(x) = \sigma\left(b + w^\top m(x)\right)
$$

The meta-learner is implemented as `LogisticRegressionCV` (or a cuML logistic regression when available) trained with log-loss (`scoring='neg_log_loss'`).

#### Implemented details (learner notebook)
In `notebooks/vae_gnn_pipeline.ipynb`, the stacked feature vector is explicitly:
$$
m(x)=\big[\; r_{vae}(x),\; s_{vgae}(x),\; p_{gat}(x),\; u_{gat}(x),\; p_{xgb}(x),\; p_{lgb}(x)\;\big]^\top,
$$
where:

- $r_{vae}(x)$ is the **β-VAE reconstruction error** (implemented as MSE).
- $s_{vgae}(x)$ is the **VGAE decoded adjacency mean per node** (i.e., `edge_recon.mean(dim=1)` in the notebook).
- $p_{gat}(x)$ is the GATv2 fraud probability and $u_{gat}(x)$ is the MC-dropout standard deviation.

The notebook also performs **threshold optimization** for the meta-ensemble by maximizing test-set $F_1$ over the precision–recall curve thresholds:
$$
F_1(t)=\frac{2\,\mathrm{Prec}(t)\,\mathrm{Rec}(t)}{\mathrm{Prec}(t)+\mathrm{Rec}(t)+\varepsilon},\qquad
t^*=\arg\max_t F_1(t).
$$

### 4.2 Recalibrated XGBoost (Percentile Rank + Pattern Boost)
In `scripts/recalibrated_inference.py`, inference starts from an XGBoost raw model score $s_{raw}(x)$ and converts it into a dataset-relative percentile rank (ECDF) on a $[0,100]$ scale:

$$
R_{rank}(x) = 100\cdot \hat{F}_n(s_{raw}(x)) = 100\cdot \frac{1}{n} \sum_{i=1}^n \mathbb{I}[s_{raw}(x_i) < s_{raw}(x)]
$$

Behavioral pattern detectors (e.g., SMURFING, STRUCTURING, PEELING) contribute an additive boost $B(x)$ capped at 50, producing the final script score:

$$
R_{final}(x) = \mathrm{clip}(R_{rank}(x) + B(x),\; 0,\; 100)
$$

Risk levels are assigned by computing percentile thresholds over $R_{final}$ itself (e.g., CRITICAL = P99, HIGH = P95, MEDIUM = P85, LOW = P70).

### 4.3 Hybrid Multi-Signal API (ML + Graph + Behavioral Patterns)
In `ml/Automation/ml_pipeline/inference/hybrid_api.py`, the final score is a **weighted fusion** of three signals:

- **ML**: an ML risk score $m \in [0,1]$ (loaded from `processed/cross_validated_results.csv` as `ml_max_score`).
- **Graph**: a Memgraph-derived risk score $g \ge 0$ (queried from an `Address` node property `graph_score`).
- **Patterns**: a set of detected behavioral patterns $\mathcal{P}$ loaded from `processed/sophisticated_fraud_patterns.csv`.

The API defines boolean “signals” as:
$$
\mathbb{1}_{ML} = \mathbb{I}[m \ge 0.55],\quad
\mathbb{1}_{G} = \mathbb{I}[g > 0],\quad
\mathbb{1}_{P} = \mathbb{I}[|\mathcal{P}| > 0],\quad
c = \mathbb{1}_{ML} + \mathbb{1}_{G} + \mathbb{1}_{P}.
$$

Each signal is normalized to a $[0,100]$ scale using constants implemented in the API:
$$
\widetilde{m} = 100\cdot \min\left(\frac{m}{0.85}, 1\right),\qquad
\widetilde{g} = 100\cdot \min\left(\frac{g}{305}, 1\right).
$$

For the pattern component, the API assigns additive boosts per pattern keyword $p$ with configured weights $b_p$:
$$
s_{pat} = 100\cdot \sum_{p}\mathbb{I}[p \in \mathcal{P}]\,b_p,\qquad
\widetilde{p} = 100\cdot \min\left(\frac{s_{pat}}{100}, 1\right)=\min(s_{pat},100).
$$

The base hybrid score is:
$$
H_0 = 0.30\,\widetilde{m} + 0.35\,\widetilde{g} + 0.35\,\widetilde{p}.
$$

Then a multi-signal multiplier is applied:
$$
H = \begin{cases}
1.20\,H_0 & c=2\\
1.50\,H_0 & c=3\\
H_0 & \text{otherwise}
\end{cases}
$$

Finally, the API maps $H$ to risk levels (CRITICAL/HIGH/MEDIUM/LOW) by fixed thresholds (80/50/25).

**Action gating (implemented)**: when `require_multi_signal = True`, high-severity actions (ESCROW/FLAG) require both a high ML score and corroboration ($c\ge 2$); otherwise the API can downgrade to REVIEW/MONITOR/APPROVE.

### 4.3.1 Implemented Probability Calibration (Teacher Notebook Artifacts)
In `notebooks/Hope_machine (4).ipynb`, probability calibration is implemented as a **1D logistic regression calibrator** (named “Platt scaling” in the notebook code): a logistic regression is fit on uncalibrated probabilities $p\in[0,1]$ reshaped to a single-feature input.

Let $p$ be an uncalibrated model probability. The calibrator fits parameters $(a,b)$ such that the calibrated probability is a monotone sigmoid remapping:
$$
\hat p = \sigma(a\,p + b).
$$

The calibrator is persisted as `{model}_calibrator.joblib` under the artifacts model directory, and downstream inference code loads these calibrators when present.

### 4.3.2 Implemented Class-Imbalance Weighting (scale\_pos\_weight)
Both notebooks and scripts use the standard XGBoost imbalance correction:
$$
\mathrm{scale\_pos\_weight}=\frac{N_-}{\max(N_+,1)},
$$
where $N_+$ and $N_-$ are the counts of positive and negative labels in the training split.

### 4.4 Teacher → Learner Training via Pseudo-Labeling (Self-Training)
In this project, the “teacher” refers to an earlier model trained on a **public labeled dataset** (e.g., the `notebooks/Hope_machine (4).ipynb` notebook trains on a downloaded labeled parquet configured as `cfg.data_path` with label column `label_unified`). The broader workspace corroborates this staged pipeline (e.g., `scripts/investigate_8percent_final.py` describes “Kaggle labeled data → XGBv1 (initial training) → BigQuery 20‑day data → pseudo‑labeling”).

In the executable Python pipeline that constructs the pseudo-labels used downstream, the teacher model artifact that is actually loaded is an XGBoost Booster at:

`c:\amttp\ml\Automation\ml_pipeline\models\trained\xgb.json`

The teacher notebook `notebooks/Hope_machine (4).ipynb` is implemented to **write** the XGBoost model as `artifacts/models/xgb.json` (it sets `cfg.xgb_model_path` accordingly and calls `bst.save_model(...)`). The same notebook also includes a “Download All Artifacts” cell that zips `cfg.artifact_root` into `all_artifacts.zip` for manual download from Colab.

Operationally, the deployment/inference scripts in this repo expect the notebook-produced artifact to be **manually copied/imported** into the workspace path above (`ml_pipeline/models/trained/xgb.json`). This matches the current implementation: scripts load `c:\amttp\ml\Automation\ml_pipeline\models\trained\xgb.json`, and no automated “pull artifacts from Colab” step is present in-repo.

with its feature schema from `ml/Automation/ml_pipeline/models/feature_schema.json` (see `scripts/sophisticated_fraud_detection_ultra.py`).

Separately, graph technology (Memgraph) and rule/pattern detectors contribute additional signals that can be used as labeling heuristics and features.

One explicit implemented pseudo-label construction step is `scripts/generate_labeled_dataset.py`, which generates training labels from **multi-signal high-confidence flags**.

Let $a$ be an address and suppose we have an address-level fraud results table (from `processed/sophisticated_xgb_combined.csv`) that includes `risk_level(a)` and `pattern_count(a)` (and potentially teacher model scores such as `xgb_normalized(a)`). The script’s positive address set is constructed as:
$$
\mathcal{A}_+ = \{a:\; risk\_level(a)\in\{\text{CRITICAL},\text{HIGH}\}\;\wedge\; pattern\_count(a)\ge 2\}.
$$

Then transaction-level pseudo-labels are defined by whether either endpoint is in $\mathcal{A}_+$:
$$
\widetilde{y}_{tx} = \mathbb{I}[from\_address \in \mathcal{A}_+\;\vee\; to\_address \in \mathcal{A}_+].
$$

This is a **teacher–learner supervision loop** in the sense of self-training / weak supervision (hard pseudo-labels). It is different from classical “knowledge distillation” as a loss term (soft targets with temperature and KL divergence) unless such a loss is implemented elsewhere.

#### Implemented Teacher-Score Calibration + Hybrid Label Signal
In `scripts/sophisticated_fraud_detection_ultra.py`, the teacher produces raw XGBoost scores $s_{raw}(a)$ for each address $a$ (via `model.predict`). These are then **sigmoid-calibrated** around the empirical 75th percentile with scaling factor $k=30$:
$$
τ = P_{75}(\{s_{raw}(a)\}),\qquad
s_{cal}(a) = \sigma\big(k\,(s_{raw}(a)-τ)\big),\qquad
s_{xgb}(a)=100\,s_{cal}(a).
$$

The script then forms a hybrid label signal from:

- $s_{xgb}(a)$: calibrated teacher score (0–100)
- $B(a)$: pattern boost computed from detected rule/pattern types (capped)
- $s_{soph}(a)$: a “sophisticated” rule-based score, normalized to $s_{soph,n}(a)\in[0,100]$

with the implemented linear fusion:
$$
H(a)=0.4\,s_{xgb}(a) + 0.3\,B(a) + 0.3\,s_{soph,n}(a).
$$

Finally, the script derives risk thresholds by optimizing on a proxy target (implemented as `pattern_count >= 3` used as pseudo ground truth) and writes the resulting labeled table to `processed/sophisticated_xgb_combined.csv`. This file is then consumed by the dataset builders that create the learner training parquet.

---

## 4A. Implemented Model Training Mathematics (Notebook-Specific)

This section captures additional *training-time* mathematics that is implemented in the notebooks and affects the learned risk engine behavior.

### 4A.1 Implemented β-VAE Loss (MSE Reconstruction + KL)
In `notebooks/vae_gnn_pipeline.ipynb`, the decoder likelihood is not explicitly parameterized as a Gaussian with learned variance; instead reconstruction is implemented via **mean squared error** (MSE). The loss is:
$$
\mathcal{L}_{\beta\text{-VAE}}(x)=\underbrace{\mathrm{MSE}(x,\hat x)}_{\text{reconstruction}}+\beta\,\underbrace{\Big(-\tfrac12\,\mathbb{E}[1+\log\sigma^2-\mu^2-\sigma^2]\Big)}_{D_{KL}(q_\phi(z\mid x)\,\|\,\mathcal{N}(0,I))},\qquad \beta=4.
$$

### 4A.2 Implemented VGAE Objective (Recon + Weighted KL)
In `notebooks/vae_gnn_pipeline.ipynb`, VGAE is trained with:
$$
\mathcal{L}_{\mathrm{VGAE}} = \mathcal{L}_{\mathrm{recon}} + \lambda\,\mathcal{L}_{\mathrm{KL}},\qquad \lambda=10^{-4},
$$
where `torch_geometric.nn.VGAE` supplies `recon_loss(z, edge_index)` and `kl_loss()`.

### 4A.3 Implemented GATv2 Supervised Objective (Focal Loss + Smoothing)
In `notebooks/vae_gnn_pipeline.ipynb`, node classification uses a focal-weighted BCE with label smoothing:

Smoothed targets:
$$
y' = y\,(1-s) + 0.5\,s,\qquad s=0.05.
$$

Per-sample BCE:
$$
\mathrm{BCE}(\ell,y') = -\big[y'\log\sigma(\ell) + (1-y')\log(1-\sigma(\ell))\big].
$$

Focal term and class-weighting (implemented with $\alpha=0.75$, $\gamma=2$):
$$
pt = \exp(-\mathrm{BCE}(\ell,y')),\qquad
w_{\mathrm{focal}}=(1-pt)^{\gamma},\qquad
w_{\alpha}=\begin{cases}\alpha & y\ge 0.5\\ 1-\alpha & y<0.5\end{cases}
$$

Final loss:
$$
\mathcal{L}_{\mathrm{GAT}} = \mathbb{E}\big[w_{\alpha}\,w_{\mathrm{focal}}\,\mathrm{BCE}(\ell,y')\big].
$$

### 4A.4 Implemented Uncertainty (MC Dropout)
The same notebook implements Monte Carlo dropout by forcing `model.train()` at inference and sampling $T=30$ stochastic forward passes:
$$
\hat p = \frac{1}{T}\sum_{t=1}^T \sigma(\ell^{(t)}),\qquad
u = \mathrm{StdDev}_t\big(\sigma(\ell^{(t)})\big).
$$

### 4A.5 Implemented Optimization & Regularization (OneCycleLR + EMA)
GATv2 training uses `AdamW` with gradient clipping and a **OneCycleLR** schedule.

In `notebooks/vae_gnn_pipeline.ipynb`, OneCycleLR is instantiated more than once (i.e., the notebook contains multiple schedulers). The GATv2 scheduler uses `pct_start=0.1`, `div_factor=25`, `final_div_factor=1000`, and another scheduler earlier in the notebook uses `pct_start=0.3` with the same `div_factor` / `final_div_factor`.

In addition, the notebook maintains an **exponential moving average** (EMA) of weights:
$$
θ_{ema}^{(t)} = \rho\,θ_{ema}^{(t-1)} + (1-\rho)\,θ^{(t)},\qquad \rho=0.999.
$$

### 4A.8 Implemented Evaluation Metrics (Brier Score, Log-Loss, Calibration Curve)
In `notebooks/vae_gnn_pipeline.ipynb`, evaluation prints ROC-AUC, PR-AUC, and explicitly computes **Brier score** and **log-loss** on the test set.

Brier score (implemented via `sklearn.metrics.brier_score_loss`):
$$
\mathrm{Brier}(y,\hat p)=\frac{1}{n}\sum_{i=1}^n (y_i-\hat p_i)^2.
$$

Log-loss (implemented via `sklearn.metrics.log_loss` with probability clipping):
$$
\mathrm{LogLoss}(y,\hat p)= -\frac{1}{n}\sum_{i=1}^n \Big(y_i\log\hat p_i + (1-y_i)\log(1-\hat p_i)\Big).
$$

Reliability curves are computed with `sklearn.calibration.calibration_curve` using `n_bins=10` and `strategy='uniform'`.

### 4A.6 Implemented K-Fold Ensembling (XGBoost / LightGBM)
In `notebooks/vae_gnn_pipeline.ipynb`, the tabular learners are trained as $K=5$ fold ensembles producing out-of-fold (OOF) estimates:
$$
\hat p_{\mathrm{OOF}}(x_i) = \hat p^{(k(i))}(x_i),\qquad
\hat p_{\mathrm{test}}(x) = \frac{1}{K}\sum_{k=1}^K \hat p^{(k)}(x),
$$
where $k(i)$ denotes the held-out fold containing sample $i$.

### 4A.7 Teacher Notebook Stacking Uses LightGBM (Not Logistic)
Separately, `notebooks/Hope_machine (4).ipynb` implements a stacking meta-learner using **LightGBM** as the meta-model (with early stopping), and then optionally applies Platt calibration to the meta predictions. This is a distinct implemented stacking path from the logistic stacking used in `vae_gnn_pipeline.ipynb`.

In addition, the workspace contains an end-to-end dataset assembly path that produces the exact file consumed by the learner notebook:

- `scripts/create_complete_labeled_dataset.py` builds an address-level labeled table by joining transaction-derived features with hybrid scoring outputs (`processed/sophisticated_xgb_combined.csv`), and sets the binary label as:
	$$
	y_{addr}=\mathbb{I}[\texttt{risk\_level}\in\{\text{CRITICAL},\text{HIGH}\}].
	$$
	It exports `processed/eth_addresses_labeled.parquet`.

- `scripts/create_gat_transaction_dataset.py` then joins these address labels/scores onto transactions and constructs the transaction label as:
	$$
	y_{tx}=\mathbb{I}[y_{from}=1\;\vee\;y_{to}=1],
	$$
	exporting `processed/eth_transactions_full_labeled.parquet` (plus graph arrays). This is the `TABULAR_PATH` used in `vae_gnn_pipeline.ipynb`.

### 4.5 “Rules + Graph Baked In” (As Training Features and Labels)
The learner notebook `vae_gnn_pipeline.ipynb` trains on a labeled transaction parquet at `TABULAR_PATH = '/content/eth_transactions_full_labeled.parquet'` with `LABEL_COL = 'fraud'` and node features including:
$$
X_{node} = [\;\texttt{sender\_total\_transactions},\;\texttt{sender\_total\_sent},\;\texttt{sender\_total\_received},\;\texttt{sender\_sophisticated\_score},\;\texttt{sender\_hybrid\_score}\;].
$$

Here `sender_sophisticated_score` and `sender_hybrid_score` are composite signals produced by rule/pattern and hybrid scoring pipelines elsewhere in the workspace (e.g., `scripts/hybrid_scoring_model.py` and the multi-signal API). As a result, even if the final learner model is a neural/GBM ensemble, it is trained on inputs and labels that already encode rule- and graph-derived evidence—i.e., those signals are “baked in” to the learned decision surface.
Here `sender_sophisticated_score` and `sender_hybrid_score` are composite signals produced by rule/pattern and hybrid scoring pipelines elsewhere in the workspace (e.g., `scripts/hybrid_scoring_model.py` and the multi-signal API). As a result, even if the final learner model is a neural/GBM ensemble, it is trained using features (and upstream label construction) that incorporate rule/pattern and hybrid evidence.

---

## 5. Zero-Knowledge Proofs (ZK-SNARKs)
The computation allows the prover to construct a valid proof if and only if they possess the private witness inputs (address, Merkle path). This logic is first flattened into a Rank-1 Constraint System (R1CS):

$$
A\mathbf{s} \circ B\mathbf{s} - C\mathbf{s} = \mathbf{0}
$$

Where $\circ$ denotes the Hadamard product. This vector equation is then transformed into the polynomial domain (Quadratic Arithmetic Program - QAP) using Lagrange Interpolation. The prover must effectively compute a polynomial $H(x)$ such that:

$$
A(x) \cdot B(x) - C(x) = H(x) \cdot Z(x)
$$

Where $Z(x) = \prod_{i=0}^{n-1} (x - \omega^i)$ is the vanishing polynomial over the scalar field $\mathbb{F}_r$, ensuring the constraints hold at all roots of unity.

### 5.1 Verification (On-Chain)
The Ethereum smart contract `AMTTPzkNAF.sol` verifies the proof $\pi = (A, B, C)$ using pairings. The verification equation checks:

$$
e(A, B) = e(\alpha, \beta) \cdot e(\sum_{i=0}^{l} a_i [IC]_i, \gamma) \cdot e(C, \delta)
$$

Where:
*   $e: \mathbb{G}_1 \times \mathbb{G}_2 \to \mathbb{G}_T$ is the bilinear pairing operation.
*   $\alpha, \beta, \gamma, \delta$ are the toxic waste parameters from the Trusted Setup.
*   $[IC]_i$ are the public input commitments (including the Sanctions Merkle Root).

Compliance is mathematically strictly proven if and only if this equality holds.

---

## 6. Optimization Dynamics (Implemented Schedules)

In `notebooks/vae_gnn_pipeline.ipynb`, neural components are trained with PyTorch’s `torch.optim.lr_scheduler.OneCycleLR` (with parameters such as `pct_start`, `div_factor`, and `final_div_factor` explicitly set in the notebook).

Where the scheduler uses cosine annealing (PyTorch `OneCycleLR` supports `anneal_strategy='cos'`), the LR can be viewed as a 1-cycle warmup + cosine-decay policy between $\eta_{max}/\mathrm{div\_factor}$ and $\eta_{max}/\mathrm{final\_div\_factor}$.

