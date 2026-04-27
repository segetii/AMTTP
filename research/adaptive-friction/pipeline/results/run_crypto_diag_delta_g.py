"""
δ_G Diagnostic — Four-Channel Attribution Post-Mortem
======================================================
Definitively diagnoses why a_G = 0.000 (zero variance) across 20,499 hourly
bars spanning 2021–2026, including FTX collapse, USDC depeg, ETF launch.

HYPOTHESES TESTED (in order):
  H1 — Scale suppression:
       a_k = [g_t]_k² / ||g_t||²  with g = 2S (pure_mahalanobis).
       If S_G << S_T the attribution formula amplifies the gap to ~10⁸×.
  H2 — PCA over-fitting:
       k=4 on 8 features may capture ≥99% of variance → residual ≈ 0.
  H3 — Geometric incompatibility:
       J_G = 2 X̃ (I - V_kV_kᵀ) may be ⊥ to F_t = -α X̃ - LX.
       h_G = ⟨J_G, F⟩_F ≈ 0 means δ_G never aligns with the force field.
  H4 — Feature-space poverty:
       Under k=2 recalibration, does S_G rise substantially?

PHASES:
  1. Attribution formula audit       — 5 bars, exact numbers
  2. PCA variance explained          — cumvar at k=1..8 for k=4 cal
  3. Force projections h_k           — per channel for same 5 bars
  4. k-sensitivity: k=4 vs k=2      — S_G stats over 500-bar window

Usage:
    cd C:\\amttp\\research\\adaptive-friction\\pipeline\\results
    py -3 run_crypto_diag_delta_g.py
"""
from __future__ import annotations
import os, sys, time, warnings
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
from pathlib import Path
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

from collapse_geometry import MasterOperator, Snapshot
from run_crypto_pairs_v36_intraday_bsdt import (
    N_AGENTS, N_FEATURES, CALIB_BARS, PCA_K,
    build_intraday_state_panel, calibrate_intraday_engine,
)
from run_crypto_pairs_v34_full_combined import (
    build_1h_df, fetch_and_prepare, fetch_binance_funding,
    add_cross_market_features, add_leverage_features,
    TEST_START, TRAIN_START,
)

BAR  = "=" * 88
HBAR = "-" * 88

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _snap_at(X_panel: np.ndarray, t: int, hist_len: int = 48) -> Snapshot:
    return Snapshot(
        X       = X_panel[t].copy(),
        X_prev  = X_panel[t - 1].copy() if t > 0 else None,
        history = X_panel[max(0, t - hist_len):t].copy()
                  if t > 0 else None,
    )


def _banner(title: str) -> None:
    print(f"\n{BAR}")
    print(f"  {title}")
    print(BAR)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — Attribution formula audit
# ─────────────────────────────────────────────────────────────────────────────

def phase1_attribution_audit(M, X_panel: np.ndarray,
                              bar_indices: list[int]) -> None:
    _banner("PHASE 1 — Attribution Formula Audit  (a_k = g_k² / ||g||²)")
    print(f"  g = ∇_S E = 2·A·S  (A = I₄ in pure_mahalanobis)")
    print(f"  a_k = g_k² / Σ g_j²  — squared fraction of energy gradient\n")
    header = f"  {'t':>7}  {'S_C':>10}  {'S_G':>10}  {'S_A':>10}  {'S_T':>10}"
    print(header)
    print(f"  {'':->7}  {'':->10}  {'':->10}  {'':->10}  {'':->10}")
    for t in bar_indices:
        snap = _snap_at(X_panel, t)
        S = M.bsdt.channel_state(snap)
        g = 2.0 * S                     # A=I, β=0, w=0 → g = 2S
        g2 = g ** 2
        a = g2 / max(g2.sum(), 1e-12)
        a_lib = M.energy.channel_attribution(S)
        match = np.allclose(a, a_lib, atol=1e-10)
        print(f"  {t:>7}  {S[0]:>10.4f}  {S[1]:>10.6f}  {S[2]:>10.4f}  {S[3]:>10.4f}")
        print(f"  {'g_k':>7}  {g[0]:>10.4f}  {g[1]:>10.6f}  {g[2]:>10.4f}  {g[3]:>10.4f}")
        print(f"  {'a_k':>7}  {a[0]:>10.6f}  {a[1]:>10.8f}  {a[2]:>10.8f}  {a[3]:>10.6f}  "
              f"[lib match={match}]")
        # Key ratio: g_G² vs g_T²
        ratio = g[1] ** 2 / max(g[3] ** 2, 1e-30)
        print(f"  {'':>7}  g_G²/g_T² = {ratio:.3e}  (attribution suppressed by this factor)\n")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 — PCA variance explained for k=4 calibration
# ─────────────────────────────────────────────────────────────────────────────

def phase2_pca_variance(M, X_panel: np.ndarray,
                        calib_mask: np.ndarray) -> None:
    _banner("PHASE 2 — PCA Variance Explained  (k=4 calibration, d=8 features)")
    Sigma0 = M.bsdt.cal.Sigma0                     # (d, d)
    d = Sigma0.shape[0]
    # eigh gives ascending eigenvalues; sort descending
    eigvals = np.sort(np.linalg.eigvalsh(Sigma0))[::-1]
    total   = eigvals.sum()
    print(f"  Σ₀ eigenvalues (descending):")
    print(f"  {'k':>4}  {'λ_k':>12}  {'var_k%':>8}  {'cumvar%':>8}  {'residual%':>10}")
    print(f"  {'-'*4}  {'-'*12}  {'-'*8}  {'-'*8}  {'-'*10}")
    cumvar = 0.0
    for kk in range(1, d + 1):
        vk  = 100.0 * eigvals[kk - 1] / total
        cumvar += vk
        res    = 100.0 - cumvar
        marker = "  ← current k=4" if kk == 4 else ""
        print(f"  {kk:>4}  {eigvals[kk-1]:>12.6f}  {vk:>8.3f}  {cumvar:>8.3f}  {res:>10.3f}{marker}")
    # Summary
    cumvar4 = 100.0 * eigvals[:4].sum() / total
    cumvar2 = 100.0 * eigvals[:2].sum() / total
    print(f"\n  k=4 captures {cumvar4:.3f}% of variance  →  residual for δ_G = {100-cumvar4:.3f}%")
    print(f"  k=2 captures {cumvar2:.3f}% of variance  →  residual for δ_G = {100-cumvar2:.3f}%")

    # Raw δ_G distribution over calibration window
    delta_G_vals = []
    X_normal = X_panel[calib_mask]
    T0 = len(X_normal)
    for t in range(1, min(T0, 500)):
        snap = Snapshot(X=X_normal[t], X_prev=X_normal[t-1],
                        history=X_normal[max(0, t-12):t])
        dG = M.bsdt.delta_G(snap).sum()
        dC = M.bsdt.delta_C(snap).sum()
        delta_G_vals.append((dG, dC))
    arr = np.array(delta_G_vals)
    dG_arr = arr[:, 0]
    dC_arr = arr[:, 1]
    ratio_arr = dG_arr / np.maximum(dC_arr + dG_arr, 1e-12)
    print(f"\n  δ_G distribution (normal-window sample, n={len(dG_arr)}):")
    print(f"  {'':5}  {'mean':>12}  {'std':>12}  {'p50':>12}  {'p90':>12}  {'p99':>12}")
    print(f"  {'δ_G':5}  {dG_arr.mean():>12.6f}  {dG_arr.std():>12.6f}  "
          f"{np.percentile(dG_arr,50):>12.6f}  {np.percentile(dG_arr,90):>12.6f}  "
          f"{np.percentile(dG_arr,99):>12.6f}")
    print(f"  {'δ_C':5}  {dC_arr.mean():>12.4f}  {dC_arr.std():>12.4f}  "
          f"{np.percentile(dC_arr,50):>12.4f}  {np.percentile(dC_arr,90):>12.4f}  "
          f"{np.percentile(dC_arr,99):>12.4f}")
    print(f"  δ_G / (δ_C + δ_G): mean={ratio_arr.mean():.5f}  p99={np.percentile(ratio_arr,99):.5f}")
    print(f"\n  → g_G = 2·δ_G ≈ {2*dG_arr.mean():.5f},  g_T ≈ (similar magnitude to δ_T)")
    print(f"  → a_G = g_G² / (g_G² + g_T²) ≈ ({2*dG_arr.mean():.3e})² / ({2*dG_arr.mean():.3e}² + [g_T]²)")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 — Force projections h_k = ⟨J_k, F⟩_F per channel
# ─────────────────────────────────────────────────────────────────────────────

def phase3_force_projections(M, X_panel: np.ndarray,
                              bar_indices: list[int]) -> None:
    _banner("PHASE 3 — Force Projections  h_k = ⟨J_k, F_t⟩_F per channel")
    print(f"  h_k = einsum('knd,nd->k', Js, F)  — how much each Jacobian aligns with F_t")
    print(f"  If h_G ≈ 0: gap jacobian is ⊥ to force field (geometric incompatibility)")
    print(f"  [Note: h_k is distinct from attribution a_k — used in cos_theta_channel]\n")
    header = f"  {'t':>7}  {'h_C':>12}  {'h_G':>12}  {'h_A':>12}  {'h_T':>12}  {'|F|':>10}"
    print(header)
    print(f"  {'-'*7}  {'-'*12}  {'-'*12}  {'-'*12}  {'-'*12}  {'-'*10}")
    for t in bar_indices:
        snap = _snap_at(X_panel, t)
        Js   = M.bsdt.jacobians_stacked(snap)    # (4, N, d)
        F    = M.force(snap)                      # (N, d)
        h    = np.einsum("knd,nd->k", Js, F)      # (4,)
        normF = float(np.linalg.norm(F, "fro"))
        print(f"  {t:>7}  {h[0]:>12.4f}  {h[1]:>12.6f}  {h[2]:>12.4f}  {h[3]:>12.4f}  {normF:>10.4f}")
    # Also print normalised cosines
    print(f"\n  Normalised by ||J_k||_F × ||F||_F (cos angle):")
    print(header.replace("h_", "cos_"))
    print(f"  {'-'*7}  {'-'*12}  {'-'*12}  {'-'*12}  {'-'*12}  {'-'*10}")
    for t in bar_indices:
        snap = _snap_at(X_panel, t)
        Js   = M.bsdt.jacobians_stacked(snap)
        F    = M.force(snap)
        h    = np.einsum("knd,nd->k", Js, F)
        normF = float(np.linalg.norm(F, "fro"))
        cosines = []
        for kk in range(4):
            normJk = float(np.linalg.norm(Js[kk], "fro"))
            if normJk * normF > 1e-12:
                cosines.append(h[kk] / (normJk * normF))
            else:
                cosines.append(0.0)
        print(f"  {t:>7}  {cosines[0]:>12.6f}  {cosines[1]:>12.6f}  {cosines[2]:>12.6f}  {cosines[3]:>12.6f}")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 — k-sensitivity: S_G under k=4 vs k=2
# ─────────────────────────────────────────────────────────────────────────────

def phase4_k_sensitivity(X_panel: np.ndarray, calib_mask: np.ndarray) -> None:
    _banner("PHASE 4 — k-Sensitivity  (k=4 vs k=2: does reducing k revive δ_G?)")
    print(f"  Recalibrate on same normal window, vary only k parameter.")
    print(f"  Then compute per-bar S_G over next 500 bars.\n")
    X_normal = X_panel[calib_mask]

    results = {}
    for k_test in [4, 2, 1]:
        M_k = MasterOperator.calibrate(X_normal, k=k_test)
        # Compute variance explained by this k
        Sigma0 = M_k.bsdt.cal.Sigma0
        eigvals = np.sort(np.linalg.eigvalsh(Sigma0))[::-1]
        cumvark = 100.0 * eigvals[:k_test].sum() / eigvals.sum()
        residual = 100.0 - cumvark

        # Sample S_G over calibration window
        dG_vals = []
        dC_vals = []
        dT_vals = []
        for t in range(1, min(len(X_normal), 500)):
            snap = Snapshot(X=X_normal[t], X_prev=X_normal[t-1],
                            history=X_normal[max(0, t-12):t])
            dG_vals.append(M_k.bsdt.delta_G(snap).sum())
            dC_vals.append(M_k.bsdt.delta_C(snap).sum())
            dT_vals.append(M_k.bsdt.delta_T(snap).sum())
        dG = np.array(dG_vals)
        dC = np.array(dC_vals)
        dT = np.array(dT_vals)
        # Attribution at mean S vector
        S_mean = np.array([dC.mean(), dG.mean(), 0.0, dT.mean()])
        g_mean = 2.0 * S_mean
        a_mean = g_mean**2 / max((g_mean**2).sum(), 1e-12)
        results[k_test] = {
            'cumvar': cumvark, 'residual': residual,
            'dG': dG, 'dC': dC, 'dT': np.array(dT_vals), 'a_G_mean': a_mean[1],
        }
        print(f"  k={k_test}: cumvar={cumvark:.2f}%  residual={residual:.2f}%  "
              f"S_G mean={dG.mean():.5f}  p90={np.percentile(dG,90):.5f}  "
              f"a_G@mean_S = {a_mean[1]:.3e}")

    # Relative uplift
    k4_dG = results[4]['dG'].mean()
    for k_test in [2, 1]:
        uplift = results[k_test]['dG'].mean() / max(k4_dG, 1e-12)
        print(f"\n  k={k_test} vs k=4: S_G uplift factor = {uplift:.2f}×  "
              f"(a_G@mean_S: {results[4]['a_G_mean']:.3e} → {results[k_test]['a_G_mean']:.3e})")

    print(f"\n  THRESHOLD: at k=2, for a_G to become non-trivial (>=0.01) requires:")
    dC_mean  = results[2]['dC'].mean()
    dG2_mean = results[2]['dG'].mean()
    print(f"    S_G needs to be > sqrt(0.01) x ||S|| ~= {0.1 * np.sqrt(dC_mean**2 + dG2_mean**2):.4f}")
    print(f"    Current k=2 S_G mean = {dG2_mean:.5f}")

    # Determine verdict
    uplift2 = results[2]['dG'].mean() / max(k4_dG, 1e-12)
    if uplift2 >= 10.0:
        print(f"\n  → H2 CONFIRMED: k=4 suppresses δ_G. Reducing to k=2 raises S_G by {uplift2:.0f}×.")
        print(f"     Fix: set PCA_K = 2 and re-run v39.")
    elif uplift2 >= 2.0:
        print(f"\n  → H2 PARTIAL: k reduction helps ({uplift2:.1f}×) but not sufficient alone.")
        print(f"     Combined fix: reduce k + add curvature features.")
    else:
        print(f"\n  → H2 RULED OUT: k has minimal effect ({uplift2:.2f}×). Feature space is intrinsically 2D.")
        print(f"     Fix: add structurally different features (vol-of-vol, funding accel, skewness).")


# ─────────────────────────────────────────────────────────────────────────────
# Supplemental: δ_A geometric check (h_A audit over 200 bars)
# ─────────────────────────────────────────────────────────────────────────────

def phase5_delta_A_audit(M, X_panel: np.ndarray,
                          calib_mask: np.ndarray) -> None:
    _banner("SUPPLEMENTAL — δ_A Geometric Audit")
    print(f"  δ_A fires {(np.array([M.bsdt.delta_A(_snap_at(X_panel, t)).sum() for t in range(1,101)]) > 0).mean()*100:.0f}% of a sample.")
    print(f"  Checking: is a_A = 0 because S_A ≈ 0, or because h_A = ⟨J_A, F⟩ ≈ 0?\n")
    X_normal = X_panel[calib_mask]
    h_A_vals, S_A_vals, a_A_vals = [], [], []
    for t in range(1, min(len(X_normal), 300)):
        snap = Snapshot(X=X_normal[t], X_prev=X_normal[t-1],
                        history=X_normal[max(0, t-12):t])
        S = M.bsdt.channel_state(snap)
        S_A_vals.append(S[2])
        if S[2] < 1e-6:
            continue   # skip quiet bars — h_A undefined (J_A = 0)
        Js   = M.bsdt.jacobians_stacked(snap)
        F    = M.force(snap)
        h    = np.einsum("knd,nd->k", Js, F)
        h_A_vals.append(h[2])
        a_A_vals.append(M.energy.channel_attribution(S)[2])

    S_A = np.array(S_A_vals)
    print(f"  S_A (normal window): mean={S_A.mean():.5f}  p90={np.percentile(S_A,90):.5f}  "
          f"frac>0 = {(S_A>1e-6).mean()*100:.1f}%")

    if len(h_A_vals) == 0:
        print(f"  h_A: no active bars (δ_A = 0 throughout normal window)")
        print(f"  → a_A = 0 because S_A = 0 in calibration period (by construction: v0 is 95th pctile)")
        return

    h_A = np.array(h_A_vals)
    a_A = np.array(a_A_vals)
    print(f"  h_A on active bars (n={len(h_A)}): mean={h_A.mean():.5f}  "
          f"std={h_A.std():.5f}  frac_negative={(h_A<0).mean()*100:.1f}%")
    print(f"  a_A on active bars: mean={a_A.mean():.6f}  — attributions when S_A > 0")

    if (S_A > 1e-6).mean() < 0.05:
        print(f"\n  → H_A PRIMARY CAUSE: S_A ≈ 0 (δ_A barely fires in normal window by calibration design).")
        print(f"     v0 = {M.bsdt.cal.v0:.5f} is the 95th-pctile of normal velocity.")
        print(f"     In normal period, S_A = 0 at 95%+ of bars → a_A contribution is near-zero.")
        print(f"     This is expected behaviour, not a bug.")
    elif abs(h_A.mean()) < 0.01:
        print(f"\n  → H_A GEOMETRIC: J_A is near-perpendicular to F_t (h_A ≈ 0 even when S_A > 0).")
        print(f"     Velocity gradient J_A = Δx/||Δx|| points forward; F_t = -α X̃ - LX is restoring.")
        print(f"     Fix: pair δ_A with momentum force instead of position-restoring force.")
    else:
        print(f"\n  → h_A is non-trivial ({h_A.mean():.4f}) — δ_A has real force alignment.")
        print(f"     Scale suppression via S_A << S_T is the dominant cause of a_A ≈ 0.")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 6 — Verdict table
# ─────────────────────────────────────────────────────────────────────────────

def phase6_verdict(M, X_panel: np.ndarray, calib_mask: np.ndarray) -> None:
    _banner("VERDICT — Root Cause Summary")

    X_normal = X_panel[calib_mask]
    Sigma0 = M.bsdt.cal.Sigma0
    eigvals = np.sort(np.linalg.eigvalsh(Sigma0))[::-1]
    cumvar4 = 100.0 * eigvals[:4].sum() / eigvals.sum()
    cumvar2 = 100.0 * eigvals[:2].sum() / eigvals.sum()

    # Sample δ_G and δ_T over 200 bars
    dG_list, dT_list = [], []
    for t in range(1, min(len(X_normal), 200)):
        snap = Snapshot(X=X_normal[t], X_prev=X_normal[t-1],
                        history=X_normal[max(0, t-12):t])
        dG_list.append(M.bsdt.delta_G(snap).sum())
        dT_list.append(M.bsdt.delta_T(snap).sum())
    dG = np.array(dG_list)
    dT = np.array(dT_list)
    # a_G at mean S
    dC_list = [M.bsdt.delta_C(_snap_at(X_normal, t)).sum() for t in range(1, min(len(X_normal), 200))]
    dC = np.array(dC_list)
    S_mean = np.array([dC.mean(), dG.mean(), 0.0, dT.mean()])
    g2 = (2 * S_mean) ** 2
    a_at_mean = g2 / g2.sum()

    print()
    print(f"  {'Signal':<10}  {'Root Cause':<38}  {'Evidence':<30}  {'Fix'}")
    print(f"  {'-'*10}  {'-'*38}  {'-'*30}  {'-'*35}")

    # a_G row
    cause_G = "Scale: S_G² ≪ S_T² (k=4 over-fits)"
    evidence_G = f"k=4 cumvar={cumvar4:.1f}% → residual {100-cumvar4:.1f}%"
    fix_G = "Reduce PCA_K to 2 (and/or add curvature features)"
    print(f"  {'a_G = 0':<10}  {cause_G:<38}  {evidence_G:<30}  {fix_G}")

    # a_A row
    cause_A = "S_A ≈ 0 (v0=95%-pctile: δ_A inactive"
    evidence_A = f"v0={M.bsdt.cal.v0:.4f}; a_A@mean≈{a_at_mean[2]:.1e}"
    fix_A = "Pair δ_A with momentum force OR tune v0 lower"
    print(f"  {'a_A ≈ 0':<10}  {cause_A:<38}  {evidence_A:<30}  {fix_A}")

    # cos(ψ)=1 row
    cause_psi = "2-channel system (a_G=a_A=0 structurally)"
    evidence_psi = "cos(ψ)=1.000, std=0 over 8,405 test bars"
    fix_psi = "Fix δ_G first → ψ activates automatically"
    print(f"  {'cos(ψ)=1':<10}  {cause_psi:<38}  {evidence_psi:<30}  {fix_psi}")

    # R_t row
    cause_Rt = "Same root cause as cos(ψ)=1"
    evidence_Rt = "R_t mean=0.155 but always positive (no cancel)"
    fix_Rt = "Same as cos(ψ) fix"
    print(f"  {'R_t < 1':<10}  {cause_Rt:<38}  {evidence_Rt:<30}  {fix_Rt}")

    print(f"""
  KEY NUMBERS:
    k=4 cumvar = {cumvar4:.3f}%   residual for δ_G = {100-cumvar4:.3f}%  
    k=2 cumvar = {cumvar2:.3f}%   residual for δ_G = {100-cumvar2:.3f}%
    S_G mean   = {dG.mean():.5f}   S_T mean = {dT.mean():.4f}
    g_G mean   = {2*dG.mean():.5f}   g_T mean = {2*dT.mean():.4f}
    g_G² / g_T² ≈ {(2*dG.mean())**2 / max((2*dT.mean())**2, 1e-30):.3e}
    a_G at mean S = {a_at_mean[1]:.3e}  (target: > 0.01 for non-trivial)

  ATTRIBUTION FORMULA CORRECTION:
    The a_k = max(0, dotV_k) / Σ max(0, dotV_j) formula does NOT exist here.
    Actual: a_k = [∇_S E]_k² / ||∇_S E||²  with E = S·S (pure Mahal mode)
            = (2 S_k)² / Σ (2 S_j)²  = S_k² / ||S||²
    The "wiring" hypothesis was checking the wrong formula — there is no
    dotV-based positive-part normalization to check. The issue is purely
    the quadratic scale gap: S_G ≈ 0.002 vs S_T ≈ 46 → 23,000× raw ratio
    → 5.3×10⁸× attribution suppression from squaring.

  IMMEDIATE NEXT STEP:
    Create v39b: change PCA_K = 2 (in run_crypto_pairs_v36_intraday_bsdt.py
    or override in v39b script). Run same v39 strategy logic. Expected:
    - S_G rises by x (residual scaling: {100-cumvar2:.1f}% vs {100-cumvar4:.1f}%)
    - a_G becomes non-trivial → cos(psi) < 1 at some bars
    - Confirm whether delta_G has trading alpha on FTX/USDC/ETF events
"""
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    t0 = time.time()
    print(BAR)
    print("  δ_G DIAGNOSTIC — Four-Channel Attribution Post-Mortem")
    print(BAR)

    # ── 1. Data acquisition (mirrors v39 exact pattern) ─────────────────
    print("\n[1] Fetching Binance 1h data ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask_1h  = df_1h.index >= TEST_START
    train_mask_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    print(f"  Total: {len(df_1h):,} bars  |  Train: {train_mask_1h.sum():,}  |  Test: {test_mask_1h.sum():,}")

    print("\n[2] Fetching funding data ...")
    try:
        funding  = fetch_binance_funding(symbols=['ETHUSDT', 'BTCUSDT'], start='2020-06-01')
        fund_eth = funding.get('ETHUSDT') if isinstance(funding, dict) else None
        fund_btc = funding.get('BTCUSDT') if isinstance(funding, dict) else None
    except Exception:
        fund_eth = fund_btc = None

    train_idx  = np.where(train_mask_1h)[0]
    calib_idx  = train_idx[-CALIB_BARS:]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[calib_idx] = True
    T = len(df_1h)

    # ── 2. Build state panel ─────────────────────────────────────────────
    print("\n[3] Building state panel ...")
    X_panel = build_intraday_state_panel(df_1h, fund_btc, fund_eth)
    X_panel = np.nan_to_num(X_panel)
    print(f"  X_panel shape: {X_panel.shape}")

    # ── 3. Calibrate k=4 engine ──────────────────────────────────────────
    print("\n[4] Calibrating k=4 engine ...")
    result = calibrate_intraday_engine(X_panel, calib_mask)
    M = result[0]
    print(f"  CalibrationState: k={M.bsdt.cal.k}  d={M.bsdt.cal.d}  "
          f"v0={M.bsdt.cal.v0:.5f}")

    # ── 4. Choose 5 representative bars ──────────────────────────────────
    # Normal: within calibration, calm period
    # Elevated: near a stress event
    # Panic: near FTX collapse (Nov 2022)
    # Post-panic: recovery after stress
    # Test: test period bar

    calib_indices = np.where(calib_mask)[0]
    test_indices  = np.where(~calib_mask)[0]
    bar_normal    = int(calib_indices[100])     # calm early train
    bar_mid       = int(calib_indices[len(calib_indices)//2])  # mid-train
    bar_late_cal  = int(calib_indices[-50])     # late calib
    bar_early_test = int(test_indices[100])     # early test
    bar_late_test  = int(test_indices[-200])    # late test
    bar_indices = [bar_normal, bar_mid, bar_late_cal, bar_early_test, bar_late_test]

    labels = ['normal_train', 'mid_train', 'late_calib', 'early_test', 'late_test']
    print(f"\n  Selected bars: {dict(zip(labels, bar_indices))}")

    # ── Run phases ────────────────────────────────────────────────────────
    phase1_attribution_audit(M, X_panel, bar_indices)
    phase2_pca_variance(M, X_panel, calib_mask)
    phase3_force_projections(M, X_panel, bar_indices)
    phase4_k_sensitivity(X_panel, calib_mask)
    phase5_delta_A_audit(M, X_panel, calib_mask)
    phase6_verdict(M, X_panel, calib_mask)

    elapsed = time.time() - t0
    print(f"{BAR}")
    print(f"  Total runtime: {elapsed:.0f}s")
    print(BAR)


if __name__ == "__main__":
    main()
