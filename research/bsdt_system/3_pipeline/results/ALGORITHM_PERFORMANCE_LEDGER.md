# Crypto BSDT / Canonical Trading Algorithm Performance Ledger

**Last updated:** 2026-05-15  
**Scope:** records tested crypto BSDT / canonical trading algorithms, core parameters, performance, and decision notes.  
**Current focus:** improve the true **$730K champion** algorithm, not proxy variants.

---

## Metric definitions

| Metric | Meaning |
|---|---|
| Final | Ending equity on the test period, starting from $10,000 unless noted otherwise |
| Profit | `Final - 10,000` |
| MaxDD | Maximum drawdown, peak-to-trough |
| Calmar | CAGR divided by `abs(MaxDD)` |
| Sharpe | Annualised return Sharpe from the simulation |
| CB | Circuit breaker halt/resume/window configuration |
| rhs filter | At CB release, if `rhs_norm` exceeds threshold, extend halt by N days |

---

## Locked target algorithm — the $730K champion

| Field | Value |
|---|---|
| Name | `d0p5_q0p65_w090_r04` |
| Source | `v35_top5_cb_transition/crypto_godmode_v35_top5_cb_transition.json` |
| Script family | `run_crypto_godmode_v35_top5_cb_transition.py` |
| `d` | `0.50` |
| `q` | `0.65` |
| CB halt | `8%` |
| CB resume | `4%` |
| CB window | `90d` |
| Baseline final | `$730,056` |
| Baseline MaxDD | `-34.84%` |
| Baseline Calmar | `17.46` |
| Baseline Sharpe | `0.668` |

**Decision:** all future drawdown-reduction experiments should start from this exact algorithm unless explicitly marked as a control.

---

## Algorithm performance table

| Version / Algorithm | Core config | Added mechanism | Final | Profit | MaxDD | Calmar | Sharpe | Status / Notes |
|---|---|---|---:|---:|---:|---:|---:|---|
| v35 true champion | `d=0.50`, `q=0.65`, CB `90d/4%` | none | `$730,056` | `$720,056` | `-34.84%` | `17.46` | `0.668` | **Target baseline. High return, high MaxDD.** |
| v53 champion best final | `d=0.50`, `q=0.65`, CB `90d/4%` | rhs release filter `thr=0.55`, `extend=30d` | `$949,196` | `$939,196` | `-29.45%` | `22.61` | `0.676` | **Best high-return result so far. Still MaxDD too high.** |
| v54 champion omega-soft best | `d=0.50`, `q=0.65`, CB `90d/4%` | rhs release filter `thr=0.55`, `extend=30d` + soft omega sizing `a=0.50` | `$953,748` | `$943,748` | `-28.97%` | `23.02` | n/a | **New best exact-champion result. Improves final, MaxDD, and Calmar over v53.** |
| v54 fractal/geoflow best DD high-return | fractional `alpha=0.60`, Ricci `eta=0.20`, `q=0.65`, CB `90d/4%` | rhs release filter `thr=0.55`, `extend=30d` + soft omega sizing `a=1.00` | `$860,072` | `$850,072` | `-28.88%` | `22.29` | n/a | Best high-return MaxDD from v54 sweep; lower final than champion-soft result. |
| v54 fractal/geoflow best >$900K | fractional `alpha=0.60`, Ricci `eta=0.10`, `q=0.65`, CB `90d/4%` | rhs release filter `thr=0.55`, `extend=30d` + soft omega sizing `a=0.50` | `$926,911` | `$916,911` | `-28.97%` | `22.80` | n/a | Best fractal/geoflow candidate above $900K. |
| v55 robust best Final | `d=0.50`, `q=0.65`, CB `90d/4%`, G7 `kappa_max=None or 20` | rhs filter `0.55/30d` + soft omega `a=0.50` + G2.4 `eta=3e-4 / lock=0` | `$1,410,244` | `$1,400,244` | `-31.56%` | `24.12` | `0.680` | **New equity record (+48% over v54).** MaxDD slightly worse. |
| v55 robust best Calmar | `d=0.50`, `q=0.65`, CB `90d/4%`, G7 `kappa_max=10` | rhs filter `0.55/30d` + soft omega `a=0.50` + curvature `b=0.25` + admiss `c=2.0` + G2.4 `eta=1e-4` | `$1,298,093` | `$1,288,093` | `-29.46%` | `25.13` | `0.559` | **New Calmar record.** Full mechanism stack works. |
| v55 robust best sub-25% MaxDD | `d=0.50`, `q=0.65`, CB `90d/4%`, G7 `kappa_max=10` | soft omega `a=0.50` + curvature `b=0.25` + G2.4 `eta=3e-4 / lock=500` (no rhs filter) | `$540,058` | `$530,058` | `-23.41%` | `23.40` | `0.639` | **First sub-25% MaxDD with Final>$500K.** Combines G7 + curvature + G2.4. |
| v53 champion low-DD | `d=0.50`, `q=0.65`, CB `180d/4%` | rhs release filter `thr=0.50`, `extend=10d` | `$157,431` | `$147,431` | `-15.27%` | `22.87` | `1.817` | Best low drawdown, but gives up too much upside. |
| v53 champion 180d base | `d=0.50`, `q=0.65`, CB `180d/4%` | none | `$163,395` | `$153,395` | `-17.49%` | `20.25` | `1.819` | Low drawdown control. Similar to v32/v33/v35 original regime. |
| v52 E proxy best final | `d=0.50`, `q=0.50`, CB `90d/4%` | rhs release filter `thr=0.55`, `extend=30d` | `$948,085` | `$938,085` | `-29.45%` | `22.60` | `0.676` | Proxy result; validated same mechanism before exact champion v53. |
| v52 E proxy low-DD | `d=0.50`, `q=0.50`, CB `180d/4%` | none | `$163,348` | `$153,348` | `-17.49%` | `20.24` | `1.819` | Proxy low-DD result. |
| A_v34_base | `d=0.25`, `q=0.50`, CB `90d/4%` | none | `$617,086` | `$607,086` | `-34.57%` | `16.60` | `0.660` | Control; not the target. |
| A_v34_base best MDD filter | `d=0.25`, `q=0.50`, CB `90d/4%` | rhs `thr=0.60`, `extend=20d` | `$29,800` | `$19,800` | `-28.22%` | `6.17` | `1.680` | Fails return objective. |
| v37 G2.4 champion | `d=0.25`, cb_original `180d/1%` | G2.4 CB override, `eta=3e-4` | `$288,433` | `$278,433` | `-17.4%` | `25.18` | n/a | Excellent Calmar; not enough final equity. |
| v38a tight-CB G2.4 | `d=0.25`, tight CB `90d/4%` | G2.4, `eta=3e-4`, `lock_min=1000` | `$997,444` | `$987,444` | `-35.4%` | `19.15` | n/a | Highest equity in doc table, but MaxDD still too high. |
| v38b G2.4 + G7 | `d=0.30`, tight CB `90d/4%` | G2.4 + G7 `kappa_max=10` | `$537,509` | `$527,509` | `-27.8%` | `19.71` | n/a | G7 reduced MaxDD but sacrificed equity. |
| v45 / original wide CB ref | approximately `d=0.25`, CB `180d/1%` | wide conservative CB | `$130,672` | `$120,672` | `-13.98%` | `23.25` | n/a | Low-DD reference; too low return. |

---

## v53 exact-champion sweep summary

Source: `v53_730k_champion/sweep_results.csv`

| Category | Config | Final | MaxDD | Calmar | Interpretation |
|---|---|---:|---:|---:|---|
| Baseline | `w=90d`, no rhs filter | `$730,056` | `-34.84%` | `17.46` | True target baseline. |
| Best final | `w=90d`, `rhs>=0.55`, `extend=30d` | `$949,196` | `-29.45%` | `22.61` | Works, but MaxDD still too high. |
| Best Calmar / MDD | `w=180d`, `rhs>=0.50`, `extend=10d` | `$157,431` | `-15.27%` | `22.87` | Too much upside lost. |
| Wide CB base | `w=180d`, no rhs filter | `$163,395` | `-17.49%` | `20.25` | Good DD, lower equity. |

---

## v54 fractal + geometric-flow sweep summary

Source: `v54_730k_fractal_geoflow/sweep_results.csv`

| Category | Config | Final | MaxDD | Calmar | Interpretation |
|---|---|---:|---:|---:|---|
| Best final / Calmar | champion `d=0.50`, soft omega `a=0.50`, rhs filter `0.55/30d` | `$953,748` | `-28.97%` | `23.02` | Best exact-champion improvement. Soft omega sizing helped slightly beyond v53. |
| Best high-return MaxDD | fractional `alpha=0.60`, Ricci `eta=0.20`, soft omega `a=1.00`, rhs filter `0.55/30d` | `$860,072` | `-28.88%` | `22.29` | Best MaxDD among candidates retaining more than $700K. |
| Best fractal/geoflow above $900K | fractional `alpha=0.60`, Ricci `eta=0.10`, soft omega `a=0.50`, rhs filter `0.55/30d` | `$926,911` | `-28.97%` | `22.80` | Fractal/geometric-flow candidate that keeps the high-return regime. |
| Best raw fractal/geoflow high final | fractional `alpha=1.20`, Ricci `eta=0.20`, no soft sizing, no rhs filter | `$905,449` | `-34.85%` | `18.80` | Geometry alone preserved high return but did not reduce MaxDD. |
| Best absolute MaxDD | fractional `alpha=1.20`, Ricci `eta=0.00`, soft omega `a=8.00`, rhs filter `0.55/30d` | `$16,543` | `-26.44%` | `4.92` | Drawdown improved but return failed; not viable. |

---

## Current diagnosis

1. The true $730K algorithm is **not** the earlier `d=0.25/q=0.50` proxy.
2. The true target is **`d=0.50/q=0.65/CB=90d resume=4%`**.
3. The `rhs_norm` release filter improves it to **$949K / -29.45% / Calmar 22.61**.
4. v54 soft omega sizing improves the exact champion again to **$954K / -28.97% / Calmar 23.02**.
5. Fractal/geometric-flow covariance helps create alternative high-return paths near **$861K-$927K** with MaxDD around **-28.9%**.
6. Geometry alone does not solve MaxDD; soft sizing plus release filtering is still required.
7. **v55 full robustness stack** (G7 + admissibility + curvature + soft omega + rhs filter + G2.4 stochastic CB override): equity ceiling jumps to **$1.41M** (Calmar 24.12) and **$1.30M** (Calmar 25.13), and the first sub-25% MaxDD high-equity cell appears at **$540K / -23.41% / Calmar 23.40**.
8. The remaining MaxDD on the moonshot path is structural to the permissive 90-day CB regime.
9. Wide CB (`180d`) solves drawdown but collapses the equity ceiling.

---

## v55 robust full-stack sweep summary

Source: `v55_730k_robust_full/sweep_results.csv` (724 rows, 522s).

Stack tested on top of the locked champion (`d=0.50`, `q=0.65`, CB `90d/4%`):

| Mechanism | Symbol | Grid |
|---|---|---|
| G7 covariance regularisation | `kappa_max` | `{None, 20, 10, 5}` |
| Soft omega sizing | `a_omega` | `{0, 0.25, 0.50}` |
| Curvature (rhs_norm) sizing | `b_curv` | `{0, 0.25, 0.50}` |
| Admissibility brake | `c_admiss` | `{0, 1.0, 2.0}` |
| rhs release filter | `thr/ext` | `{off, 0.55/30d}` |
| G2.4 stochastic CB override | `eta / lock_min` | `{off, 1e-4 / 0, 1e-4 / 500, 3e-4 / 0, 3e-4 / 500}` |

Best cells:

| Category | Config | Final | MaxDD | Calmar | Sharpe |
|---|---|---:|---:|---:|---:|
| Best Calmar | `kp=10, om=0.50, cv=0.25, ad=2.0, g24=η1e-4/l0, rel=0.55/30d` | `$1,298,093` | `-29.46%` | `25.13` | `0.559` |
| Best Final | `kp=None, om=0.50, cv=0, ad=0, g24=η3e-4/l0, rel=0.55/30d` | `$1,410,244` | `-31.56%` | `24.12` | `0.680` |
| Best sub-25% MaxDD with Final>$500K | `kp=10, om=0.50, cv=0.25, ad=0, g24=η3e-4/l500` | `$540,058` | `-23.41%` | `23.40` | `0.639` |
| Best Final at sub-25% MaxDD | none above $900K — closest sub-25% is $540K (above) |  |  |  |  |

Verification gate: the (kp=None, om=0.50, cv=0, ad=0, g24=off, rel=0.55/30d) baseline reproduces the v54 best at **$953,748 / -28.97% / Calmar 23.02 / Sharpe 0.676** exactly.

### v55 takeaways

1. Stacking G7 (`kappa_max=10`) + soft omega + curvature + admissibility + G2.4 keeps the full $1M+ moonshot path AND raises Calmar to a new record (`25.13`).
2. Sub-25% MaxDD is achievable **on the 90-day CB envelope** for the first time, but only at ~$540K final equity. The G7 + curvature + G2.4 (`η=3e-4 / lock=500`) trio is responsible.
3. G2.4 with `η=3e-4 / lock=0` reliably amplifies returns under the rhs filter (e.g., `$1.41M`), confirming it is the dominant mechanism for equity expansion.
4. Admissibility brake `c=2.0` only helps when paired with `omega=0.50` and `curvature=0.25` — alone it kills returns.
5. The "BIG WIN" cell (Final > $900K AND MaxDD > -25%) does not yet exist; the upside path and the brake path remain disjoint regions in the parameter space.

---

## v56 adaptive-Y fix attempt (negative result)

Source: `v56_adaptive_y_fix/sweep_results.csv` (108 rows, 307s).

Goal: fix the residual -29% to -32% MaxDD by sweeping the adaptive-Y throttle on top of the v55 winner stacks.

Grid:
- Y schedules: `(dd_soft, dd_stop, y_floor) ∈ {(0.05,0.20,0.25) default, floor_10, floor_00, mid, hard_12, hard_15, hard_18, aggressive_10, loose}`
- DD source: `{aty (all-time peak), cb (rolling 90d peak), max(both)}`
- Stacks: `{V55_Final, V55_Calmar, V55_LowDD, V54_Base}`

Result: **the v55 default schedule `(0.05, 0.20, 0.25, aty)` is locally optimal**. Every alternative degraded.

Failure modes:
1. `y_floor=0` (hard stop) → once `dd_aty ≥ dd_stop` the throttle goes to 0, equity flatlines, `peak_alltime` never recovers ⇒ permanent y=0 death spiral (final ≈ $1.2K).
2. `dd_source=cb` → over-throttles on minor pullbacks, kills the moonshot path (final ≈ $10K, MaxDD still -41%).
3. `dd_source=max ≡ aty` because `peak_alltime ≫ rolling_peak` once equity has grown.

Diagnosis: Y is reactive — by the time `dd_aty` registers a fast crash bar, the loss is already taken at full leverage. The schedule cannot be the lever for further DD reduction.

---

## v57 pre-trade vol cap attempt (negative result)

Source: `v57_vol_kcap/sweep_results.csv` (84 rows, 149s).

Goal: replace reactive Y with a **pre-trade** scaler `K_t ← K_normal · min(1, σ_target / σ_realised)`.

Grid:
- Vol windows: `{24, 72, 168, 336}` bars (1d, 3d, 1w, 2w)
- Per-bar σ targets: `{off, d_2.0, d_1.5, d_1.0, d_0.7, d_0.5}` (daily σ in %)
- Stacks: same four winners as v56

Result: **collapses equity to $1K–$10K even at `mean_kvol ≈ 0.9`** (only 10% average size reduction). The engine's edge lives in the same high-vol bars that produce the drawdown, so any pre-trade vol cap throws away the moonshot.

Best v57 cells:
- `V55_Calmar, vw=24, sig=d_0.7` → `$7,474 / -23.94% / Cal 3.41` (MDD improves but return destroyed)
- `V55_LowDD, vw=24, sig=d_2.0` → `$9,215 / -26.25% / Cal 3.56`

No TARGET cell (Final>$700K AND MaxDD>-25%) emerges.

---

## Combined diagnosis after v55/v56/v57

The -29% to -32% MaxDD on the high-equity path is **structural to the signal**, not a defect of position sizing. Concretely:

- The signal generates fat-tail returns that contribute both the moonshot (~$1.4M) and the drawdown (~-30%).
- Reactive throttles (Y) cannot react before the loss is taken.
- Pre-trade throttles (vol cap) cannot distinguish the winning high-vol bars from the losing high-vol bars.
- Multiplicative upstream brakes (omega / curvature / admissibility) are already active in the v55 winner stacks.

The sub-25% MaxDD frontier currently requires sacrificing equity (V55_LowDD at $540K). Reducing MaxDD on the $1M+ path requires changing the **edge geometry itself** — e.g., signal decomposition (separating tail-up vs tail-down components), regime-conditioned engine switching, or explicit short-tail hedging — not another sizing or throttle layer.

---

## Completed version — v54 fractal + geometric flow improvement

**Goal:** improve the true $730K champion, not proxies.

Target:

| Objective | Threshold |
|---|---:|
| Minimum acceptable final | `>$700K` |
| Preferred final | `>$900K` |
| Minimum acceptable MaxDD | better than `-29.45%` — achieved: `-28.97%` exact champion, `-28.88%` fractal/geoflow |
| Preferred MaxDD | better than `-25%` |
| Hard success target | `>$700K` and `MaxDD > -25%` |

### Planned mechanisms

| Mechanism | Formula / implementation idea | Why it may help |
|---|---|---|
| Fractal / fractional memory covariance | long-memory covariance or GL-FFD controlled by `d` / `alpha` | Better regime memory than a single covariance snapshot. |
| Geometric flow / Ricci shrink | log-Euclidean shrink of SPD covariance eigenvalues toward identity | Reduces covariance concentration and unstable metric directions. |
| Soft rhs sizing | `K_t = K0 / (1 + a * rhs_norm)` | Reduces risk during unstable ODE states without skipping the whole segment. |
| Soft omega sizing | `K_t = K0 / (1 + a * gamma * rhs_norm)` | Penalises only high-energy + high-motion states. |
| Preserve champion CB | keep `90d/4%` as primary | Keeps the high-return equity path. |

### v54 outcome

v54 succeeded on the minimum objective but did not reach the preferred `-25%` MaxDD target. The best exact-champion candidate is now:

| Field | Value |
|---|---|
| Geometry | champion `d=0.50` covariance |
| CB | `90d/4%` |
| rhs filter | `thr=0.55`, `extend=30d` |
| Soft sizing | `K_t = K0 / (1 + 0.50 * gamma * rhs_norm)` |
| Final | `$953,748` |
| Profit | `$943,748` |
| MaxDD | `-28.97%` |
| Calmar | `23.02` |

Next step should target **sub-25% MaxDD** with a more local drawdown brake or adaptive CB window that does not fully collapse the 90-day moonshot path.

### Do not prioritise yet

| Item | Reason |
|---|---|
| Full natural-gradient Langevin | Too complex for current drawdown fix. |
| Contact geometry | Not relevant to BTC/ETH/SOL trading state. |
| Thermodynamic entropy as live signal | Interpretive; not yet proven as a drawdown control. |
| Hard 180d CB only | Fixes MaxDD but destroys target return profile. |

---

## File index

| File | Purpose |
|---|---|
| `v53_730k_champion_filters.py` | Exact champion rhs/window sweep |
| `v53_730k_champion/sweep_results.csv` | v53 result table |
| `v53_730k_champion/v53_results.json` | v53 JSON archive |
| `v54_730k_fractal_geoflow.py` | Exact champion fractal/geometric-flow + soft sizing sweep |
| `v54_730k_fractal_geoflow/sweep_results.csv` | v54 result table |
| `v54_730k_fractal_geoflow/v54_results.json` | v54 JSON archive |
| `v55_730k_robust_full.py` | Champion + G7 + admissibility + curvature + soft omega + rhs filter + G2.4 stack |
| `v55_730k_robust_full/sweep_results.csv` | v55 result table |
| `v55_730k_robust_full/v55_results.json` | v55 JSON archive |
| `v56_adaptive_y_fix.py` | Y-throttle schedule + DD-source sweep on v55 winners |
| `v56_adaptive_y_fix/sweep_results.csv` | v56 result table |
| `v57_vol_kcap.py` | Pre-trade volatility cap on K_normal sweep |
| `v57_vol_kcap/sweep_results.csv` | v57 result table |
| `v52_cb_window_e050.py` | Earlier proxy window sweep |
| `v51_rhs_norm_cb_filter.py` | Earlier proxy rhs filter sweep |
| `run_crypto_godmode_v35_top5_cb_transition.py` | Source of true $730K champion config |
| `run_crypto_godmode_v30_fractional_ricci.py` | Existing fractional + Ricci/geometric-flow machinery |
| `run_crypto_godmode_v38_ito_tightcb.py` | Existing G2.4/G7 implementation |

---

## Running notes

Use PowerShell from:

`c:\amttp\research\adaptive-friction\pipeline\results`

Important commands:

```powershell
py -3 v53_730k_champion_filters.py 2>&1 | Tee-Object -FilePath v53_run_log.txt | Select-Object -Last 120
```

Latest v54 run:

```powershell
py -3 v54_730k_fractal_geoflow.py 2>&1 | Tee-Object -FilePath v54_run_log.txt | Select-Object -Last 120
```

Latest v55 run:

```powershell
$env:PYTHONIOENCODING='utf-8'; py -3 v55_730k_robust_full.py 2>&1 | Tee-Object -FilePath v55_run_log.txt | Select-Object -Last 300
```
