# Adaptive Friction Control — GUI

Interactive dashboard for the Adaptive Friction Stability Framework.

## Quick Start

```bash
# 1. Install Python dependencies
pip install fastapi uvicorn pandas numpy scipy

# 2. Start the API server
cd adaptive-friction-gui/backend
python server.py

# 3. Open the dashboard
# Open adaptive-friction-gui/frontend/index.html in a browser
# Or visit http://localhost:8050 (if serving via the API)
```

## Features

- **Real-time KPI display**: MFLS score, γ*(t) coupling, λ_max spectral radius, phase state, CCyB recommendation
- **Historical trajectory charts**: MFLS + energy, spectral phase diagram, adaptive coupling, gradient alignment, CCyB bars
- **Interactive simulation**: Sweep GravityEngine parameters (α, γ, σ, λ_rep, η) and run from any crisis onset
- **Crisis analysis tables**: Lead-lag analysis, Granger causality, welfare consumption-equivalent loss
- **Crisis window overlays**: GFC 2008, COVID 2020, Rate Shock 2022 highlighted on all charts

## Architecture

```
adaptive-friction-gui/
├── backend/
│   └── server.py          # FastAPI server (port 8050)
├── frontend/
│   └── index.html         # Single-page dashboard (Chart.js)
└── README.md
```

The backend loads pipeline results from `research/adaptive-friction/pipeline/results/`
and exposes REST endpoints. The frontend is a standalone HTML file with no build step.
