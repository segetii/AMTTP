# Navier–Stokes Adaptive Viscosity Framework

## What this is

A research-grade 3D incompressible Navier–Stokes pseudo-spectral solver on
the periodic torus T³, equipped with a **state-dependent viscosity** mechanism
derived from the MFLS/BSDT financial stability framework.

The modified equation solved here is:

$$\partial_t \mathbf{u} + (\mathbf{u}\cdot\nabla)\mathbf{u} = -\nabla p + \nu(E_{\mathrm{BS}})\,\Delta\mathbf{u}, \qquad \nabla\cdot\mathbf{u}=0$$

where $\nu(E) = \nu_0\bigl(1 + E/(E+\theta)\bigr)$ and $E_{\mathrm{BS}}$ is a
composite diagnostic functional measuring enstrophy anomaly, spectral
deviation, vorticity–strain alignment, and temporal novelty.

## What this is NOT

- **This does not solve the Clay Millennium Navier–Stokes problem.**
- The analytical statements in the paper and code apply to a *modified*
  equation (state-dependent viscosity), not to the standard constant-viscosity
  3D Navier–Stokes equations.
- All computational results are finite-resolution numerical evidence (specific
  grid sizes, time steps, Reynolds numbers, and initial conditions). They
  should not be interpreted as a continuum proof of global regularity or
  blow-up.
- The "proof scaffolding" module contains heuristic/conjectural checks, not
  rigorous proofs.

## Key numerical observation

In the tested runs (Taylor–Green vortex, Re ∈ [314, 6283], N = 32):

| Re   | P/D (constant ν) | P/D (adaptive ν) | Ratio |
|------|-------------------|-------------------|-------|
| 314  | 1.214             | 0.548             | 0.451 |
| 628  | 2.561             | 1.222             | 0.477 |
| 1257 | 5.256             | 2.576             | 0.490 |
| 3142 | 11.751            | 5.849             | 0.498 |
| 6283 | 16.306            | 8.158             | 0.500 |

The production-to-dissipation proxy is reduced by ≈ 50 % under the adaptive
mechanism across these Reynolds numbers, consistent with the heuristic
prediction from the viscosity doubling ($\gamma^* \to 1$).

## Repository structure

| File | Description |
|------|-------------|
| `solver.py` | Core pseudo-spectral solver, BSDT channels, adaptive viscosity |
| `proof_scaffolding.py` | Conjectural/heuristic regularity checks |
| `run_exp1.py` / `run_fast.py` | Experiment 1 (constant vs adaptive) |
| `reynolds_sweep.py` / `fast_sweep.py` | Reynolds-number sweep experiments |
| `high_re.py` / `re6283.py` | High-Re targeted runs |
| `paper/main.tex` | LaTeX paper (conditional claims + numerical evidence) |
| `paper/main.pdf` | Compiled paper |

## Running

```bash
cd navier-stokes
python run_fast.py          # Quick Experiment 1 (~3 min)
python re6283.py            # Re = 6283 comparison (~10 min)
```

Requires only **NumPy** (tested with Python 3.10+).

## Author

Segun Odeyemi — London, United Kingdom
