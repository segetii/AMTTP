# AMTTP Practical Implementation Guide (Research → Proof → Production)

Audience: junior ML / crypto researcher.

Rules:
- Do the steps in order.
- Do not change code unless a step says so.
- Every phase produces **files**. If a file is missing, stop and fix that phase.

---

## What you are building (one sentence)
A reproducible pipeline that:
1) trains and freezes a **teacher** fraud model,
2) trains a **student** stack on fresh data,
3) logs **PAC‑Bayes + adversarial** proof artifacts from real runs,
4) wires the production **risk engine** (ML + graph + patterns) without mixing teacher/student time periods,
5) keeps ZK compliance proofs **separate** from ML.

---

# PHASE 0 — Environment Setup (Week 0)

## 0.1 Create a Python venv (Windows PowerShell)
From repo root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

## 0.2 Install Python packages (minimum to run the proof notebook)
Install the repo’s pinned ML requirements first:

```powershell
pip install -r ml/Automation/requirements.txt
```

Then install the proof‑notebook stack (this notebook uses these directly):

```powershell
pip install torch numpy pandas scipy polars pyarrow scikit-learn joblib xgboost lightgbm matplotlib shap captum
pip install torch-geometric
```

If `torch-geometric` install fails on Windows, stop and switch to running the notebook on a Linux box / WSL / Colab GPU.

## 0.3 Install Node tooling for ZK + contracts
You need Node >= 18.

From repo root:

```powershell
npm install
```

For Circom + snarkjs circuit builds (local option):

```powershell
cd contracts/zknaf
npm install
npm run install:circom
```

---

# PHASE 1 — Teacher Model (Old Labeled Data)

Goal: produce a **frozen** teacher model + calibrated probabilities. This teacher is the reference point for student distillation and for “prior” artifacts.

## 1.1 Pick the teacher dataset (DO NOT MIX TIME PERIODS)
You need 1 labeled dataset file with:
- tabular features
- label column (fraud vs non‑fraud)

Required columns for the proof notebook path:
- feature columns (default list is in the notebook)
- `fraud` (or your label name)
- `from_idx`, `to_idx` (graph edges)

Place the file under:
- `processed/` (recommended)

## 1.2 Verify you already have a production teacher model
Check these files exist (they do in a healthy repo checkout):
- `ml/Automation/ml_pipeline/models/trained/xgb.json`
- `ml/Automation/ml_pipeline/models/trained/xgb_calibrator.joblib` (optional but preferred)
- `ml/Automation/ml_pipeline/models/feature_schema.json`

If they exist and you are not retraining this week, stop here and move to PHASE 2.

## 1.3 (Optional weekly) Retrain teacher and update the production model directory
This repo’s “production teacher” is the XGBoost model loaded by the CPU predictor.

Action:
- Train XGBoost on your old labeled dataset.
- Save:
	- model → `xgb.json`
	- calibrator → `xgb_calibrator.joblib`
	- updated feature list → `feature_schema.json`

Where to put them:
- `ml/Automation/ml_pipeline/models/trained/xgb.json`
- `ml/Automation/ml_pipeline/models/trained/xgb_calibrator.joblib`
- `ml/Automation/ml_pipeline/models/feature_schema.json`

Why this matters for AMTTP proofs:
- This is your fixed baseline for distillation and for “teacher prior” logging.

---

# PHASE 2 — Fresh Blockchain Data (Unlabeled Student Training)

Goal: pull **fresh** on‑chain data from a later time window and store it locally.

## 2.1 Choose one data source (do not do multiple today)
Pick exactly one:
- BigQuery bulk (recommended for scale)
- Etherscan (targeted)
- Synthetic (for plumbing tests)

## 2.2 BigQuery fetch (bulk)
Prereqs:
- A billing‑enabled GCP project ID
- Auth configured (service account JSON or `gcloud auth application-default login`)

Set env var once:

```powershell
$env:GCP_PROJECT_ID = "<your-billing-project-id>"
```

Run the fetcher by importing it in a short Python snippet (keep it simple):
- Use `automation/bigquery_fetcher.py`.
- Save raw JSON/CSV/Parquet into `automation/data/` or `processed/`.

## 2.3 Etherscan fetch (targeted)
Set:

```powershell
$env:ETHERSCAN_API_KEY = "<your-key>"
```

Use `automation/eth_data_fetcher.py` to download per‑address history.

## 2.4 Ingest into Memgraph (graph features)
Start Memgraph (Docker compose in this repo already includes it).

Then ingest transactions:
- Use `automation/memgraph_ingest.py`.

Why this matters for AMTTP proofs:
- Graph features are part of the multi‑signal engine and the proof notebook’s GNN steps.

---

# PHASE 3 — Teacher → Student Distillation (Practical version in this repo)

Goal: train the student stack on fresh data, using teacher outputs where available.

Reality check for this repo:
- The proof notebook already trains a student‑style stack (β‑VAE + VGAE + GATv2 + GraphSAGE + boosted models + meta‑ensemble).
- “Distillation” is currently operationalised as **using teacher‑quality supervised models and graph models together**, not as a single explicit KL distillation training script.

Action today:
- Run the proof notebook end‑to‑end on the *fresh* dataset.

---

# PHASE 4 — PAC‑Bayes Proof Metrics (Automated)

Goal: compute and persist PAC‑Bayes metrics from a real training run.

## 4.1 Run the proof notebook with explicit inputs
Notebook:
- `notebooks/pac_bayes_security_proofs.ipynb`

Set environment variables so you don’t edit notebook code:

```powershell
$env:AMTTP_TABULAR_PATH = "C:\\amttp\\processed\\<your_dataset>.parquet"
$env:AMTTP_LABEL_COL = "fraud"
$env:AMTTP_NODE_FEATURES = "sender_total_transactions,sender_total_sent,sender_total_received,sender_sophisticated_score,sender_hybrid_score"
$env:AMTTP_NOTEBOOK_OUT = "C:\\amttp\\reports\\publishing\\notebook_outputs\\run_$(Get-Date -Format yyyyMMdd_HHmmss)"
```

Then open the notebook in VS Code and **Run All**.

## 4.2 Confirm proof artifacts exist (must-have)
In your `AMTTP_NOTEBOOK_OUT` folder, confirm:
- `theorem1_pac_bayes_bounds.json`
- `theorem2_minimax_game.json`
- `theorem3_unified_adversarial_bound.json`

Why this matters for AMTTP proofs:
- These JSON files are the “math‑to‑execution bridge”: they are the numeric proof artifacts you cite.

---

# PHASE 5 — Adversarial Robustness Testing (Already in notebook)

Goal: generate adversarial patterns and measure stability.

Do not write new generators today.

Action:
- In the notebook, execute Theorem 3 (it sweeps attack strengths and logs the unified bound vs observed adversarial risk).

Output to verify:
- `theorem3_unified_adversarial_bound.json`

---

# PHASE 6 — Uncertainty Quantification (Already in notebook)

Goal: compute uncertainty for active learning.

Action:
- In the notebook, run the MC Dropout section (30 forward passes).
- Store the resulting uncertainty arrays in your run output directory (if you need them for daily ops).

Why this matters for AMTTP proofs:
- Uncertainty is used to justify the active learning loop and stability checks.

---

# PHASE 7 — Risk Fusion Engine (Production)

Goal: run the actual AMTTP multi‑signal scoring API.

## 7.1 Start the hybrid risk API
The hybrid API combines:
- ML score (reads from models directory)
- graph boosts (Memgraph)
- pattern boosts (CSV patterns)

Entry point:
- `ml/Automation/ml_pipeline/inference/hybrid_api.py`

Preferred: start via the CLI:
- `automation/automation_cli.py`

Example:

```powershell
python automation/automation_cli.py serve --mode hybrid --port 8000
```

## 7.2 Confirm the models directory is discoverable
The hybrid API searches for trained models and will disable ML scoring if not found.

You want these files present:
- `ml/Automation/ml_pipeline/models/trained/xgb.json`
- `ml/Automation/ml_pipeline/models/feature_schema.json`

Why this matters for AMTTP proofs:
- This is the production instantiation of “multi‑signal” detection used in the system claims.

---

# PHASE 8 — ZK Layer (Separate from ML)

Rule: ZK proofs do NOT touch ML inference. They only prove compliance predicates.

## 8.1 Build circuits + verifiers (existing circuits)
Circuits:
- `contracts/zknaf/circuits/sanctions_non_membership.circom`
- `contracts/zknaf/circuits/risk_range_proof.circom`
- `contracts/zknaf/circuits/kyc_credential.circom`

Build:

```powershell
cd contracts/zknaf
npm run download:ptau
node scripts/build-production.js
```

## 8.2 Deploy verifier contracts
You already have a router contract:
- `contracts/zknaf/ZkNAFVerifierRouter.sol`

Deploy using Hardhat flows in this repo.

---

# PHASE 9 — Active Learning Loop

Goal: feed only high‑uncertainty cases back into labeling.

Daily action:
1) run student pipeline (PHASE 4)
2) extract highest‑uncertainty items
3) send to manual review / rule oracle / graph oracle
4) append confirmed labels to the **teacher** dataset (old labeled bucket)

Do NOT add fresh‑window labels back into the teacher’s original time window.

---

# PHASE 10 — Mathematical Proof Data Collection (Non‑Negotiable Logging)

Must log per run (store under your `AMTTP_NOTEBOOK_OUT`):
- PAC‑Bayes: KL proxy, empirical risk proxy (Brier), bound value → already logged by Theorem 1 JSON
- Game theory: equilibrium strategies, adversarial success rate → logged by Theorem 2 JSON
- Unified adversarial bound: clean risk, worst‑case attack, bound terms → logged by Theorem 3 JSON

---

# PHASE 11 — Dataset Split Rule (DO NOT VIOLATE)

Teacher:
- old labeled dataset window

Student:
- fresh unlabeled (or sparsely labeled) dataset window

Never mix windows.

---

# PHASE 12 — What to Run Daily (literally the daily loop)

Daily (in order):
1) Fetch fresh data (PHASE 2)
2) Run notebook proofs on that dataset (PHASE 4)
3) Verify the three theorem JSON outputs exist
4) Run hybrid API scoring (PHASE 7) to confirm production path still works

Weekly:
- retrain teacher (PHASE 1.3) and re‑run a full proof notebook run

---

# PHASE 13 — When It’s Research‑Grade

Stop calling it research‑grade until:
- the three theorem JSON artifacts exist for multiple non‑overlapping fresh datasets
- adversarial sweep does not collapse detection (Theorem 3 stays non‑vacuous)
- production hybrid API loads the updated teacher artifacts without schema mismatch
- ZK circuits build and verifier router deploys (independent of ML)