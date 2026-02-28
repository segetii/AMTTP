# MFLS SDK

**Multi-Factor Lyapunov Systemic-risk engine.**

Real-time blind-spot detection, early-warning signals, and macro-prudential
calibration for financial networks.

## Quick Start

```python
from mfls import MFLSEngine

engine = MFLSEngine()

# Load real FDIC/World Bank data
panel = engine.load_gsib_panel(start="2005-01-01", end="2023-12-31")

# Fit on normal period and score
result = engine.fit_and_score(panel)

print(f"Current MFLS score: {result.signal[-1]:.4f}")
print(f"AUROC: {result.auroc:.3f}")
print(f"GFC lead: {result.gfc_lead_quarters}Q")
print(f"CCyB recommendation: {result.ccyb_bps:.0f} bps")
```

## Installation

```bash
pip install -e ".[all]"
```

## REST API

```bash
mfls-api                     # starts on http://localhost:8000
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/signal/gsib
curl http://localhost:8000/api/v1/audit/bsdt?format=json
```

## Python Library

### Core Components

| Module | Purpose |
|--------|---------|
| `mfls.core.bsdt` | 4-channel BSDT operators (Camouflage, Feature Gap, Activity, Temporal) |
| `mfls.core.scoring` | MFLS scoring variants (Baseline, Full BSDT, QuadSurf, SignedLR, ExpoGate) |
| `mfls.core.network` | Ledoit-Wolf correlation network + spectral radius |
| `mfls.core.energy` | GravityEngine potential, forces, phase-transition detection |
| `mfls.data` | FDIC, World Bank GFDD, ECB MIR data loaders |
| `mfls.signals` | High-level MFLS pipeline, CCyB calibration, herding monitor |
| `mfls.evaluation` | Backtest, block-bootstrap CI, Granger causality suite |
| `mfls.api` | FastAPI REST endpoints |

### Products

1. **Systemic Risk Signal** — `engine.fit_and_score()` → real-time MFLS score
2. **Blind-Spot Audit** — `engine.bsdt_audit()` → 4-channel decomposition per institution
3. **CCyB Calibration** — `engine.ccyb()` → Basel III buffer in basis points
4. **Herding Monitor** — `engine.herding_score()` → convergent herding signal

## License

Proprietary. All rights reserved.
