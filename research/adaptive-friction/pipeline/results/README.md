# Pipeline Results Map

This folder is not just a results directory. It contains:

- versioned crypto trading scripts
- generated outputs for those scripts
- side experiments for ERCOT, market MFLS, directional frameworks, and alarm studies
- one-off diagnostic utilities

Treat it as a mixed research workspace, not a single clean package.

## Start Here

If your goal is to understand the code instead of browsing hundreds of files, use this order:

1. [../../collapse_geometry/README.md](../../collapse_geometry/README.md)
   Read this first if you want the formal package that defines MasterOperator, BSDT, MFLS, collapse geometry, Lyapunov terms, and the stochastic extensions.
2. [../../upgraded/run_pipeline.py](../../upgraded/run_pipeline.py)
   This is the clearest adaptive-friction entry point on FDIC/FRED data.
3. [run_crypto_pairs_v19.py](run_crypto_pairs_v19.py)
   This is the trading foundation: market data loading, funding features, BSDT state features, cross-market features, and base strategy plumbing.
4. [run_crypto_pairs_v22.py](run_crypto_pairs_v22.py)
   This adds the frozen engine, early-warning signals, rolling thresholds, and per-pair/global gating.
5. [run_crypto_pairs_v27.py](run_crypto_pairs_v27.py)
   This is the allocator fix where engine outputs become non-negative weights and strategy direction stays inside each strategy.
6. [run_crypto_pairs_v28.py](run_crypto_pairs_v28.py)
   This adds quality gating and volatility normalization on top of the engine-state allocator.

## Folder Roles

| Group | What it contains | How to treat it |
|---|---|---|
| `run_crypto_pairs_v*.py` | Versioned trading research scripts | Main trading code history |
| `crypto_bsdt_v*.json/png/txt/csv` | Saved outputs from those versions | Results archive, not source of truth for logic |
| `run_ercot_*`, `ercot_*` | ERCOT / power-grid experiments | Separate domain application |
| `run_directional_framework.py`, `run_two_phase_*.py`, `run_three_layer_model.py` | Side model branches | Read only if you are tracing a specific research branch |
| `market_mfls_*`, `omega_alarm_*` | Market-stress and alarm studies | Diagnostics and validation |
| `lead_table.tex`, `granger_table.tex`, `welfare_table.tex` | Paper outputs | Generated artifacts |
| `math_reference (1).html` | Mathematical narrative / presentation | Documentation, not runtime core |

## Important Naming Reality

There are multiple overlapping version lineages in this folder.

- The script names `run_crypto_pairs_v19.py` to `run_crypto_pairs_v58_stability_patch.py` are a research trail.
- The output files `crypto_bsdt_v*.json` and related images are generated artifacts from different branches and dates.
- [SIZING_ARCHITECTURE_RESULTS.md](SIZING_ARCHITECTURE_RESULTS.md) documents an older sizing arc centered on [run_crypto_pairs_v18.py](run_crypto_pairs_v18.py).

Do not assume the highest version number is automatically the canonical entry point.

## Recommended Map By Goal

### 1. Understand the adaptive-friction theory stack

- [../../collapse_geometry/README.md](../../collapse_geometry/README.md)
- [../../collapse_geometry/__init__.py](../../collapse_geometry/__init__.py)
- [../../upgraded/gravity_engine.py](../../upgraded/gravity_engine.py)

### 2. Understand the banking / empirical validation path

- [../../upgraded/run_pipeline.py](../../upgraded/run_pipeline.py)
- [../../upgraded/crisis_analysis.py](../../upgraded/crisis_analysis.py)
- [../../upgraded/welfare.py](../../upgraded/welfare.py)

### 3. Understand the trading application

- [run_crypto_pairs_v19.py](run_crypto_pairs_v19.py) for data and base signal construction
- [run_crypto_pairs_v22.py](run_crypto_pairs_v22.py) for frozen engine and signal emission
- [run_crypto_pairs_v27.py](run_crypto_pairs_v27.py) for unsigned state weighting
- [run_crypto_pairs_v28.py](run_crypto_pairs_v28.py) for quality-gated risk-normalized allocation
- [V58_PROFIT_ACCELERATION.md](V58_PROFIT_ACCELERATION.md) for an explanation of why the late-branch profit curve starts slower and then accelerates

### 4. Understand older documented production sizing work

- [run_crypto_pairs_v18.py](run_crypto_pairs_v18.py)
- [SIZING_ARCHITECTURE_RESULTS.md](SIZING_ARCHITECTURE_RESULTS.md)

This is a separate documented branch focused on leverage sizing and stress budgeting.

## What To Ignore On First Pass

If you are trying to understand logic, ignore these initially:

- all `.json`, `.png`, `.pdf`, `.csv`, `.tex`, and `.txt` files
- most `v3x` to `v5x` scripts unless you are tracing a specific experiment
- one-off diagnostics like [_diag_crypto.py](_diag_crypto.py) until the main path is clear

## Shortest Practical Reading Order

If you only want the shortest path to competence in this folder:

1. [run_crypto_pairs_v19.py](run_crypto_pairs_v19.py)
2. [run_crypto_pairs_v22.py](run_crypto_pairs_v22.py)
3. [run_crypto_pairs_v27.py](run_crypto_pairs_v27.py)
4. [run_crypto_pairs_v28.py](run_crypto_pairs_v28.py)
5. [math_reference (1).html](math_reference%20(1).html)

That path gives you the data plumbing, the engine signals, the allocator fix, the risk-quality overlay, and then the narrative math view.