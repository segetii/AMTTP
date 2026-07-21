# BSDT System — Master Navigation Guide

Everything lives here. Each subfolder is a **directory junction** (a live link — edits
inside are edits to the real files; no copies, no sync issues).

```
bsdt_system/
├── README.md            ← you are here
├── 1_core/              → collapse_geometry/       Physics engine
├── 2_udl/               → research/udl/udl/        Signal scoring / anomaly detection
└── 3_pipeline/          → pipeline/                Runs, simulations, results
    ├── *.py                                         Engine-level scripts (gravity, GSIB…)
    └── results/                                     Trading pipeline
        ├── run_crypto_pairs_v36_intraday_bsdt.py   ← CURRENT CHAMPION
        ├── simulate_1000_production.py              ← $1k production simulation
        └── …
```

---

## 1 — Core Physics Engine (`1_core/`)

The mathematical foundation. All other layers import from here.

| File | What it does |
|---|---|
| `state.py` | `MasterOperator`, `Snapshot` — state matrix X_t, `pipeline()` |
| `bsdt.py` | **BSDT operator** — `delta_C/G/A/T`, `channel_state`, `jacobians` |
| `geometry.py` | `CollapseGeometry` — `cos_theta_channel` (4D, active), `cos_theta_state` (64D, degenerate) |
| `ews.py` | `EarlyWarning`, `PrecursorScale` — RSS precursor signals |
| `lyapunov.py` | `LyapunovCertificate` — exact ė_t = dV/dt (§XVI) |
| `forces.py` | Force field F_t, collapse direction G̃ |
| `potential.py` | Energy landscape V(X) |
| `damping.py` | Adaptive friction γ* = e_t/(e_t + θ) |
| `mfls.py` | MFLS state (mean-field landscape score ξ₅) |
| `network.py` | `LedoitWolfNetwork` — Ledoit-Wolf covariance shrinkage |
| `stochastic.py` | `StochasticExtension` — Kramers escape probability |
| `escape.py` | Escape rate ε = exp(−ΔV / σ²) |
| `info_theory.py` | `InformationGeometry` — χ² threshold e* |
| `control.py` | Controllability margin R_t |
| `sensitivity.py` | Perturbation / sensitivity analysis |
| `recovery.py` | Recovery trajectory estimation |
| `inverse.py` | Inverse problem solvers |
| `udl_transform.py` | Bridge: physics engine output → UDL input space |
| `unified_energy.py` | Unified energy field |
| `welfare.py` | Welfare operator |
| `__init__.py` | Package exports (import this) |
| `engines/gravity.py` | Gravity engine variant |
| `engines/molecular.py` | Molecular dynamics engine |
| `engines/hybrid.py` | Hybrid engine |
| `engines/diagnostics.py` | Engine diagnostics |

### Quick import

```python
import sys
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

from collapse_geometry import (
    MasterOperator, Snapshot, LedoitWolfNetwork,
    CollapseGeometry, LyapunovCertificate,
    EarlyWarning, PrecursorScale, InformationGeometry,
    StochasticExtension,
)
```

### Key concepts

- **X_t ∈ ℝ^{N×d}** — state matrix (N=8 instruments × d=8 features)
- **e_t** — blind-spot energy (Mahalanobis² distance from normal manifold)
- **e\*** — χ² critical threshold at 99% confidence
- **γ\*** = e_t/(e_t + θ) — position damping [0,1]
- **G̃_t** — collapse direction (N×d force tensor)
- **cos(θ)** — alignment of G̃ with F (power factor; use `cos_theta_channel` not `cos_theta_state`)
- **ψ_t** — false-alarm angle (entry valid when < π/4)
- **R_t** — controllability margin (block entry when ≤ 0)
- **τ_lin** — bars to critical manifold (exit when < 5)

---

## 2 — UDL Signal Scoring (`2_udl/`)

Anomaly detection and signal separation layer. Key files used by the trading pipeline:

| File | What it does |
|---|---|
| `subspace_scan.py` | **`SubspaceScanScorer`** — per-ξ tanh-stretch (fixes 5th-root variance compression) |
| `bsdt_bridge.py` | Direct BSDT → UDL bridge |
| `energy.py` | Energy-based anomaly scoring |
| `gravitational.py` / `gravity.py` | Gravity-field anomaly scores |
| `magnifier.py` | Signal magnification |
| `subspace_scan.py` | Key pattern: `score = sigmoid(STRETCH_GAMMA · z_i)` per ξ |
| `system_mode.py` | Mode classifier: EQUILIBRIUM / DEGENERACY / STRUCTURAL |
| `calibration.py` | Threshold calibration utilities |
| `ellipsoid_geometry.py` | Mahalanobis ellipsoid geometry |
| `pipeline.py` | Full UDL inference pipeline |
| `classifier.py` | Final classification layer |
| `fusion_strategies.py` | Score fusion (rank, meta, RL) |
| `deviation_layer.py` | Deviation scoring |
| `spectra.py` | Spectral decomposition |
| `hybrid_pipeline.py` | Hybrid UDL + physics pipeline |
| `benchmark_tanh_stretch.py` | Benchmark: tanh-stretch variants |

### The tanh-stretch pattern (from `subspace_scan.py`)

This is applied in `run_crypto_pairs_v36_intraday_bsdt.py` to break 5th-root
variance compression in RSS:

```python
# For each ξ signal with calibration σ ≥ MIN_XI_SIG:
z_i      = (xi_value - xi_mu_cal) / xi_sig_cal
stretched = sigmoid(STRETCH_GAMMA * z_i)   # STRETCH_GAMMA = 3.0

# Geometric mean of active (non-constant) stretched signals:
rss = product(stretched_i) ** (1 / K_active)
```

Result: RSS dynamic range 0.055 → 0.887 (16× wider); pre-collapse zone now reachable.

---

## 3 — Pipeline (`3_pipeline/`)

### Top-level engine scripts (`3_pipeline/*.py`)

| File | What it does |
|---|---|
| `gravity_engine.py` | Gravity engine (multi-engine benchmark runs) |
| `state_matrix.py` | State matrix builder |
| `run_pipeline.py` | Generic pipeline runner |
| `run_terra_luna_*.py` | Terra/Luna collapse case studies |
| `run_texas_grid_all_variants.py` | ERCOT power grid stress test |
| `run_navier_stokes_gsib.py` | Navier-Stokes G-SIB bank runs |
| `run_newtonian_gsib.py` | Newtonian G-SIB bank runs |
| `adversarial_stress_test.py` | Adversarial stress testing |
| `crisis_analysis.py` | Historical crisis analysis |

### Trading pipeline (`3_pipeline/results/`)

#### Core engine (the champion)

| File | What it does |
|---|---|
| **`run_crypto_pairs_v36_intraday_bsdt.py`** | **CHAMPION** — BSDT engine with per-ξ tanh-stretch RSS |
| `run_crypto_pairs_v63_clip_boost.py` | v63 clip+boost variant |
| `run_crypto_pairs_v64_cost_leverage.py` | Cost+leverage model |
| `run_crypto_pairs_v65_conviction_filter.py` | Conviction gate filter |
| `run_crypto_pairs_v66_v58_maker.py` | Maker fee model |
| `run_crypto_pairs_v67_pairs_fee.py` | Pairs-adjusted fee model |
| `run_crypto_pairs_v68_paper_signal.py` | Paper-correct signal (sign(M_t)) |
| `run_robustness_validation.py` | Walk-forward robustness validation |

#### Simulation layer

| File | What it does |
|---|---|
| **`simulate_1000_production.py`** | **$1k production sim** — 3 cost tiers (zero/realistic/pessimistic) |
| `simulate_master_strategy.py` | Core: position sizing, trailing stop, equity metrics |
| `simulate_v63_quadrant.py` | Circuit breaker + ZE7 gate logic |
| `simulate_dynamic_ze7_sweep.py` | ZE7 parameter sweep |
| `simulate_circuit_breaker.py` | Circuit breaker sweep |
| `simulate_cb_sweep.py` / `simulate_cb_resume_sweep.py` | CB parameter tuning |
| `simulate_impulse_sweep.py` | Impulse regime stress tests |
| `simulate_surge_sweep.py` | Surge regime stress tests |
| `simulate_fade_sweep.py` | Fade regime stress tests |
| `simulate_enterprise_v59_full.py` | Enterprise full simulation |
| `simulate_v59_best_combo_1000.py` | Best-combo 1000-run Monte Carlo |
| `simulate_hourly_2h_daily_risk_ohlc.py` | OHLC-aware hourly sim |
| `simulate_adaptive_y_drawdown_brake.py` | Adaptive-Y drawdown brake |
| `simulate_atr14_stops.py` | ATR-14 stop simulation |

#### Test / comparison scripts

| File | What it does |
|---|---|
| `test_v59_vs_v58_full.py` | v59 vs v58 full comparison |
| `test_v59_combined.py` | Combined signal comparison |
| `test_v59_direction.py` | Directional signal comparison |
| `test_v59_best_combo_search.py` | Best combo search |
| `test_psi_adaptive_y.py` | Adaptive ψ threshold test |

---

## Dependency Graph

```
  2_udl/subspace_scan.py
         │
         │  tanh-stretch pattern (STRETCH_GAMMA=3.0)
         ▼
  1_core/collapse_geometry/
    ┌─────────────────────────────────────────────┐
    │  state.py ──► forces.py ──► potential.py    │
    │  bsdt.py  ──► geometry.py                   │
    │  ews.py   ──► lyapunov.py ──► mfls.py       │
    │  network.py   stochastic.py   info_theory.py │
    └──────────────────────┬──────────────────────┘
                           │ imports
                           ▼
  3_pipeline/results/run_crypto_pairs_v36_intraday_bsdt.py
    │  calibrate_intraday_engine()
    │    → per-ξ calib (μ,σ) for ξ1(γ*) + ξ4(cos_theta)
    │    → RSS_stretch μ=0.459, σ=0.333
    │  compute_intraday_signals()
    │    → RSS dynamic range: [0.081, 0.968]
    │    → Regime: 57% Normal / 43% Elevated / 8% Pre-collapse
    │
    ▼
  3_pipeline/results/simulate_1000_production.py
    → Zero-cost:   $1k → $17,622  CAGR +54%  Calmar +3.24 (2021–2026)
    → Realistic:   $1k →  $3,723  CAGR +49%  Calmar +2.84 (OOS 2023–2026)
    → Pessimistic: $1k →  $3,429  CAGR +45%  Calmar +2.60 (OOS 2023–2026)
```

---

## RSS Signal Architecture (v36)

```
INPUTS from pipeline():
  ξ₁  γ*       = e_t / (e_t + θ)           position damping
  ξ₂  λ_f      = clip(λ_bound, 0, 1)        Gershgorin bound
  ξ₃  W̄_off    = mean off-diagonal weight   network coupling
  ξ₄  z_θ      = (cos_theta_channel − μ_cal) / σ_cal   AC-coupled power factor
  ξ₅  mfls_f   = MFLS / (1 + MFLS)         landscape score

CALIBRATION (normal window, 500 bars):
  Only ξ₁ (σ=0.014) and ξ₄ (σ=1.000) vary → K=2 active signals
  ξ₂, ξ₃, ξ₅ constant in calibration → skipped (no discriminative power)

STRETCH (UDL SubspaceScanScorer pattern):
  z_i       = (ξ_i − μ_i_cal) / σ_i_cal
  s_i       = sigmoid(3.0 · z_i)            maps z=0→0.50, z=+2→0.998
  RSS_raw   = (s₁ · s₄)^(1/2)              square root (K=2)
  RSS_t     = RSS_raw · cos²(ψ_t)

Z-SCORE (fixed calibration reference):
  z_rss     = (RSS_t − 0.459) / 0.333
  Normal       z < 0.5   → full size
  Elevated     z < 1.5   → 50% size
  Pre-collapse z < 2.5   → 0% size
  Critical     z ≥ 2.5   → flat / exit
```

---

## How to run

```powershell
cd C:\amttp\research\adaptive-friction\pipeline\results

# Full BSDT signal computation + strategy comparison
py -3 run_crypto_pairs_v36_intraday_bsdt.py

# $1,000 production simulation (3 cost tiers)
py -3 simulate_1000_production.py

# Robustness validation (walk-forward)
py -3 run_robustness_validation.py
```

---

## Key parameters (all in `run_crypto_pairs_v36_intraday_bsdt.py`)

| Constant | Value | Meaning |
|---|---|---|
| `CALIB_BARS` | 500 | Normal-window length for calibration |
| `STRETCH_GAMMA` | 3.0 | Tanh-stretch gain per ξ signal |
| `MIN_XI_SIG` | 0.01 | Min σ for a ξ signal to be active |
| `Z_RSS_NORMAL` | 0.5 | Below this → full position size |
| `Z_RSS_ELEVATED` | 1.5 | Above this → 50% position size |
| `Z_RSS_PRECOLLAPSE` | 2.5 | Above this → flat / exit |
| `AGC_SPAN_ATTACK` | 2160 bars (90d) | AGC slow-rise reference |
| `AGC_SPAN_DECAY` | 168 bars (7d) | AGC fast-fall reference |
| `TAU_TIGHT` | 5 bars | τ_lin exit threshold |
| `ALPHA_CONF` | 0.01 | χ² confidence level for e* |
| `PCA_K` | 4 | Leading eigenvectors for normal manifold |
