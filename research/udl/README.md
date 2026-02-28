# Universal Deviation Law (UDL) — Reproducibility Guide

## Overview

This directory contains the complete source code for the **Universal Deviation Law** framework, a multi-spectrum tensor approach for anomaly detection. The framework instantiates 14 composable spectrum operators across five mathematical families and provides multiple projection strategies for converting multi-law representations into anomaly scores.

**Papers:**
- IEEE version: `paper/universal_deviation_law.tex` (.pdf)
- NeurIPS version: `paper/universal_deviation_law_neurips.tex` (.pdf)

## Key Results

| Method | mAUC | mCov | minCov | Note |
|--------|------|------|--------|------|
| **UDL-Hybrid (4-op)** | **0.972** | **91%** | **65%** | Cross-validated strategy auto-selection |
| UDL-RankFusion (4-op) | 0.963 | 89% | 65% | Unsupervised, no labels required |
| UDL-QuadSurf (lean) | 0.919 | 86% | 69% | Best worst-case coverage |
| UDL-Fisher (4-op) | 0.950 | 80% | 53% | Collapses on Pendigits (Cov 13%) |

Results validated on 5 benchmarks: Synthetic (1050×10), Mimic (1050×10), Mammography (11183×6), Shuttle (10000×9), Pendigits (1797×64).

## Directory Structure

### Core Pipeline
| File | Description |
|------|-------------|
| `src/pipeline.py` | Main UDL pipeline — operator stacking, tensor construction, projection |
| `src/hybrid_pipeline.py` | Hybrid auto-selection — CV-competes Fisher/QDA/QDA-Magnified/RankFusion |
| `src/meta_fusion.py` | MetaFusionPipeline — per-sample rank-average across strategies |
| `src/rank_fusion.py` | RankFusion — non-parametric unsupervised strategy |
| `src/projection.py` | Fisher LDA and QDA projection implementations |
| `src/magnifier.py` | Boundary-Centred Dimension Magnifier (Eq. 8 in paper) |

### Spectrum Operators (14 total)
| File | Operators |
|------|-----------|
| `src/spectra.py` | Statistical, Geometric, Exponential, Reconstruction, RankOrder |
| `src/experimental_spectra.py` | Fourier, BSpline, Wavelet, Legendre, Phase-curve |
| `src/new_spectra.py` | Topological, Dependency, Kernel, Compression |

### Supporting Modules
| File | Description |
|------|-------------|
| `tensor.py` | Anomaly tensor and MDN decomposition (Magnitude-Direction-Novelty) |
| `centroid.py` | Normal centroid estimation |
| `stack.py` | Operator stack composition |
| `mfls_weighting.py` | QuadSurf polynomial calibration and weighting strategies |
| `datasets.py` | Benchmark dataset loading (Synthetic, Mimic, ODDS) |
| `coordinates.py` | Coordinate transforms |
| `energy.py` | GravityEngine energy functional |
| `gravity.py` / `gravitational.py` | GravityEngine N-body scoring |
| `law_matrix.py` | Cross-law coupling matrix |
| `functional.py` | Functional tests |
| `bsdt_bridge.py` | Bridge to BSDT framework |
| `backend.py` | Backend utilities |
| `fusion_strategies.py` | Strategy registry for meta-fusion |
| `rl_fusion.py` | Reinforcement learning fusion (experimental) |

### Validation & Results
| File | Description |
|------|-------------|
| `src/validate_phase2.py` | Validation orchestrator — spawns `worker_eval.py` per dataset |
| `src/worker_eval.py` | Per-dataset evaluation worker (9 methods × 5 datasets) |
| `src/correlation_audit.py` | 14×14 operator Spearman correlation analysis |
| `results/lean_results.txt` | Final validation results (all methods × all datasets) |
| `results/correlation_audit.json` | Full correlation matrix (JSON) |
| `results/corr_output.txt` | Correlation analysis output log |

### Figures
| File | Description |
|------|-------------|
| `paper/generate_figures.py` | Generates all 6 publication PDF figures |
| `paper/figures/` | Output directory (10 PDFs) |

## Reproducing Results

### Prerequisites

```
Python 3.10+
pip install numpy scipy scikit-learn pyod
```

### Step 1: Run Validation (All 5 Datasets × 9 Methods)

```bash
cd src
python validate_phase2.py
```

This spawns `worker_eval.py` as a subprocess for each dataset to avoid OOM. Results are printed to stdout and saved to `../results/lean_results.txt`.

### Step 2: Run Correlation Audit (14 Operators)

```bash
python correlation_audit.py
```

Computes 14×14 Spearman rank correlation matrix across all operator pairs, averaged over 5 datasets. Output: `../results/corr_output.txt` and `../results/correlation_audit.json`.

### Step 3: Generate Figures

```bash
cd ../paper
python generate_figures.py
```

Generates 6 publication-quality PDFs in `figures/`:
- `operator_solo_coverage.pdf` — Solo operator coverage bar chart
- `operator_correlation_heatmap.pdf` — 14×14 correlation heatmap
- `strategy_coverage_heatmap.pdf` — Strategy × dataset coverage
- `coverage_radar.pdf` — Coverage radar plot
- `auc_vs_coverage.pdf` — AUC vs coverage scatter
- `projection_scatter.pdf` — 2D law-space projection

### Step 4: Compile Papers

```bash
cd paper
pdflatex universal_deviation_law.tex          # IEEE version
pdflatex universal_deviation_law.tex          # run twice for refs

pdflatex universal_deviation_law_neurips.tex  # NeurIPS version
pdflatex universal_deviation_law_neurips.tex  # run twice for refs
```

### Datasets

Benchmark datasets are in `data/external_validation/odds/`:
- `mammography.mat`, `shuttle.mat`, `pendigits.mat` (ODDS format)
- Synthetic and Mimic datasets are generated programmatically by `datasets.py`

## Configuration

All experiments use a **single hyperparameter set** across all datasets:
- Exponential amplification: α = 1.0
- Score weights: (w_r, w_θ) = (0.7, 0.3)
- Magnifier steepness: γ = 5.0
- QDA regularisation: λ = 10⁻⁴
- Data split: 70/30 stratified, seed 42
- StandardScaler: fit on normal training data only

No per-dataset tuning is applied.
