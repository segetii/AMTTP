#!/usr/bin/env python3
"""
Geometry of System Collapse — Full Formula Arsenal × 5 Representations
=======================================================================
For each representation R ∈ {FullTensor, ReducedTensor, MDN, Coordinate, CoverageTensor}:

  Raw X → R.transform(X) → R_space → CollapseGeometry full decomposition:

    ── C* Ellipsoid (frozen geometry) ──
      Q(x) = Σ (x_b,j)² / a²_j         quadratic form
      τ_Q  = χ²_{0.99}(d)               boundary threshold
      λ_max(x) = 2·max(Q,1)/min(a²)     spectral radius
      Φ_eff(x) = γ(e^{-Q_conv/2} − λ·ln r)  effective potential

    ── Angular Geometry ──
      θ(x) = arccos(d̃(x)·d̄_ref)        angular departure
      AM(x) = √((d̃−d̄)ᵀ Σ_d⁻¹ (d̃−d̄))   angular Mahalanobis

    ── BSDT v3 Channels (energyv3 formulation) ──
      δ_C = √Q               collapse amplitude
      δ_G = ‖(I−P_A)X‖       off-manifold residual
      δ_A = max(‖∇Q‖−v₀,0)   excess gradient
      δ_T = Q/2 + log_const   density penalty
      E_BS = Σ δ²_k

    ── 7 Indicators (Fisher VR fusion) ──
      [Q_ex, θ_ex, −σ, dE, Q×θ, K×θ, AM] → w_fusion → sigmoid → S(x)

    ── Dissipation & Friction ──
      σ(x) = (c₀+γ*)‖∇E‖²   Lyapunov dissipation
      γ*(x) = α/(λ_max+ε)    adaptive friction
      S_f(t) = brake(S_f)·S   friction-damped score
      tipping = argmax ΔS_f

    ── Policy ──
      δ*(x) = −(Q−τ_Q)/‖∇Q‖² · ∇Q   min-norm correction to C*

  Then: compare which geometric objects separate attacks in each
  representation space.
"""
from __future__ import annotations
import sys, os, time, warnings
import numpy as np

warnings.filterwarnings("ignore")

ROOT = r"c:\amttp"
sys.path.insert(0, os.path.join(ROOT, "research", "udl"))
sys.path.insert(0, os.path.join(ROOT, "research", "udl", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from collapse_geometry import CollapseGeometry
from test_collapse_network_flow import generate_network_flow, downsample, MINS_PER_DAY

# UDL framework representations
from udl.system_mode import ReducedTensorDescriptor, UDLPostSimScorer
from udl.stack import RepresentationStack
from udl.tensor import AnomalyTensor
from udl.coordinates import CoefficientCoordinates

W = 100
BIN = 10


def cohen_d(a, b):
    """Cohen's d effect size."""
    pooled = np.sqrt((a.var() + b.var()) / 2 + 1e-12)
    return (a.mean() - b.mean()) / pooled


def main():
    np.set_printoptions(precision=4, suppress=True, linewidth=120)

    print("=" * W)
    print("  GEOMETRY OF SYSTEM COLLAPSE — FULL FORMULAS × 5 REPRESENTATIONS")
    print("  30-day network capture, 8 features, 7 attack phases")
    print("=" * W)

    # ═══════════════════════════════════════════════════════════
    # DATA
    # ═══════════════════════════════════════════════════════════
    X_raw, phases = generate_network_flow()
    X = downsample(X_raw, BIN)
    T, d = X.shape
    bpd = MINS_PER_DAY // BIN

    phase_bins = {}
    for name, (s, e) in phases.items():
        phase_bins[name] = (s // BIN, e // BIN)

    ref_s, ref_e = 144, 1584  # days 1–11
    X_ref = X[ref_s:ref_e]
    norm_sb, norm_eb = phase_bins['normal']

    attack_phases = ['reconnaissance', 'c2_beacon', 'lateral_movement',
                     'exfiltration', 'ddos']
    IND_NAMES = ['Q_ex', 'θ_ex', '−σ', 'dE', 'Q×θ', 'K×θ', 'AM']

    # ═══════════════════════════════════════════════════════════
    # STEP 1: Build 5 representation spaces
    # ═══════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  STEP 1: BUILD 5 REPRESENTATION SPACES")
    print("─" * W)

    reps = {}

    # 1. Full Tensor
    print("\n  [1] Full Tensor (RepresentationStack)...")
    from udl.spectra import (
        StatisticalSpectrum, ChaosSpectrum, SpectralSpectrum,
        ExponentialSpectrum, ReconstructionSpectrum, RankOrderSpectrum,
    )
    stack = RepresentationStack(operators=[
        ("stat", StatisticalSpectrum()),
        ("chaos", ChaosSpectrum()),
        ("freq", SpectralSpectrum()),
        ("exp", ExponentialSpectrum()),
        ("recon", ReconstructionSpectrum()),
        ("rank", RankOrderSpectrum()),
    ])
    stack.fit(X_ref)
    reps['FullTensor'] = {
        'ref': stack.transform(X_ref),
        'all': stack.transform(X),
        'D': stack.total_dim,
        'laws': stack.law_names_,
    }
    print(f"      D={reps['FullTensor']['D']}, laws={stack.law_names_}")

    # 2. Reduced Tensor
    print("  [2] Reduced Tensor (ReducedTensorDescriptor)...")
    rtd = ReducedTensorDescriptor(k_neighbors=min(15, len(X_ref) - 1))
    rtd.fit(X_ref)
    reps['ReducedTensor'] = {
        'ref': rtd.transform(X_ref),
        'all': rtd.transform(X),
        'D': rtd.transform(X_ref[:1]).shape[1],
        'features': rtd.feature_names(),
    }
    print(f"      D={reps['ReducedTensor']['D']}")

    # 3. MDN Vector
    print("  [3] MDN Vector (AnomalyTensor)...")
    R_full_ref = reps['FullTensor']['ref']
    R_full_all = reps['FullTensor']['all']
    mdn = AnomalyTensor()
    mdn.fit(R_full_ref)
    tr_ref = mdn.build(R_full_ref, stack.law_dims_)
    mdn.store_ref_law_stats(tr_ref)
    tr_all = mdn.build(R_full_all, stack.law_dims_)
    R_mdn_ref = np.column_stack([tr_ref.magnitude[:, None],
                                  tr_ref.novelty[:, None],
                                  tr_ref.law_magnitudes])
    R_mdn_all = np.column_stack([tr_all.magnitude[:, None],
                                  tr_all.novelty[:, None],
                                  tr_all.law_magnitudes])
    reps['MDN'] = {'ref': R_mdn_ref, 'all': R_mdn_all,
                   'D': R_mdn_ref.shape[1]}
    print(f"      D={reps['MDN']['D']}")

    # 4. Coordinate
    print("  [4] Coordinate (CoefficientCoordinates)...")
    coord = CoefficientCoordinates(views=['sorted', 'variance'])
    coord.fit(X_ref)
    R_coord_ref, coord_names = coord.transform(X_ref)
    R_coord_all, _ = coord.transform(X)
    reps['Coordinate'] = {'ref': R_coord_ref, 'all': R_coord_all,
                          'D': R_coord_ref.shape[1],
                          'axes': coord_names}
    print(f"      D={reps['Coordinate']['D']}")

    # 5. Coverage Tensor (Phase + Topo + KernelRKHS + Rank)
    print("  [5] Coverage Tensor (UDLPostSimScorer: Phase+Topo+Kernel+Rank)...")
    cov = UDLPostSimScorer(k=15, max_dim=12, n_components=10)
    cov.fit(X_ref)
    R_cov_ref = cov.transform(X_ref)
    R_cov_all = cov.transform(X)
    op_names = [n for n, _ in cov._operators] if cov._operators else []
    reps['CoverageTensor'] = {
        'ref': R_cov_ref, 'all': R_cov_all,
        'D': R_cov_ref.shape[1],
        'operators': op_names,
    }
    print(f"      D={reps['CoverageTensor']['D']}, ops={op_names}")

    # ═══════════════════════════════════════════════════════════
    # STEP 2: Full CollapseGeometry on each representation
    # ═══════════════════════════════════════════════════════════
    results = {}
    for rep_name, rep in reps.items():
        print("\n" + "═" * W)
        print(f"  {rep_name} (D={rep['D']}) → FULL COLLAPSE GEOMETRY")
        print("═" * W)

        R_ref = rep['ref']
        R_all = rep['all']

        cg = CollapseGeometry()
        cg.fit(R_ref)

        # ── Frozen geometry ──
        print(f"\n  ── Frozen C* Ellipsoid ──")
        print(f"  τ_Q = {cg._tau_Q:.4f}   θ_crit = {cg._theta_crit:.4f} rad")
        print(f"  Semi-axes a² = {cg._a2}")
        print(f"  Fisher VR w  = {cg._w_fusion}")
        print(f"  Calibration  = centre {cg._score_centre:.4f}, "
              f"scale {cg._score_scale:.4f}")

        # ── Full detect ──
        det = cg.detect(R_all)
        scores = cg.score(R_all)
        S_f = cg.score_with_friction(R_all)
        raw = cg._raw_indicators(R_all)  # (T, 7)

        # ────────────────────────────────────────────
        # A. Q(x) — Quadratic Form on C*
        # ────────────────────────────────────────────
        print(f"\n  ── A. Q(x): Quadratic Form ──")
        print(f"  {'Phase':<22s} {'mean Q':>10s} {'max Q':>10s} "
              f"{'%>τ_Q':>7s}")
        for pn, (sb, eb) in phase_bins.items():
            Qs = det.Q[sb:eb]
            print(f"  {pn:<22s} {Qs.mean():10.2f} {Qs.max():10.2f} "
                  f"{(Qs > cg._tau_Q).mean():7.1%}")

        # ────────────────────────────────────────────
        # B. λ_max — Spectral Radius
        # ────────────────────────────────────────────
        print(f"\n  ── B. λ_max(x): Spectral Radius ──")
        print(f"  {'Phase':<22s} {'mean':>12s} {'max':>12s}")
        for pn, (sb, eb) in phase_bins.items():
            lm = det.lambda_max[sb:eb]
            print(f"  {pn:<22s} {lm.mean():12.2f} {lm.max():12.2f}")

        # ────────────────────────────────────────────
        # C. θ(x), AM(x) — Angular Geometry
        # ────────────────────────────────────────────
        print(f"\n  ── C. Angular: θ(x), AM(x) ──")
        print(f"  {'Phase':<22s} {'mean θ':>10s} {'%>θ_c':>7s} "
              f"{'mean AM':>10s}")
        for pn, (sb, eb) in phase_bins.items():
            th = det.theta[sb:eb]
            am = det.AM[sb:eb]
            print(f"  {pn:<22s} {th.mean():10.4f} "
                  f"{(th > cg._theta_crit).mean():7.1%} "
                  f"{am.mean():10.4f}")

        # ────────────────────────────────────────────
        # D. BSDT v3 Energy Channels
        # ────────────────────────────────────────────
        print(f"\n  ── D. BSDT v3 Channels: δ_C, δ_G, δ_A, δ_T ──")
        print(f"  {'Phase':<22s} {'δ_C':>8s} {'δ_G':>8s} {'δ_A':>8s} "
              f"{'δ_T':>8s} {'E_BS':>10s}")
        for pn, (sb, eb) in phase_bins.items():
            print(f"  {pn:<22s} "
                  f"{det.delta_C[sb:eb].mean():8.3f} "
                  f"{det.delta_G[sb:eb].mean():8.3f} "
                  f"{det.delta_A[sb:eb].mean():8.3f} "
                  f"{det.delta_T[sb:eb].mean():8.3f} "
                  f"{det.E_BS[sb:eb].mean():10.2f}")

        # ────────────────────────────────────────────
        # E. Φ_eff — Effective Potential
        # ────────────────────────────────────────────
        print(f"\n  ── E. Φ_eff(x): Effective Potential ──")
        print(f"  {'Phase':<22s} {'mean':>10s} {'min':>10s} {'max':>10s}")
        for pn, (sb, eb) in phase_bins.items():
            phi = det.phi_eff[sb:eb]
            print(f"  {pn:<22s} {phi.mean():10.4f} {phi.min():10.4f} "
                  f"{phi.max():10.4f}")

        # ────────────────────────────────────────────
        # F. Dissipation & Friction
        # ────────────────────────────────────────────
        print(f"\n  ── F. Dissipation σ(x), Friction γ*(x) ──")
        print(f"  {'Phase':<22s} {'σ mean':>10s} {'γ* mean':>10s} "
              f"{'%dE>0':>7s} {'%diss_f':>8s}")
        for pn, (sb, eb) in phase_bins.items():
            sig = det.sigma_dissipation[sb:eb].mean()
            gam = det.gamma_star[sb:eb].mean()
            de = (det.dE_sign[sb:eb] > 0).mean()
            df = det.dissipation_failure[sb:eb].mean()
            print(f"  {pn:<22s} {sig:10.4f} {gam:10.4f} "
                  f"{de:7.1%} {df:8.1%}")

        # ────────────────────────────────────────────
        # G. Seven Indicators — Fisher VR Decomposition
        # ────────────────────────────────────────────
        print(f"\n  ── G. 7 Indicators (raw means) ──")
        print(f"  Fisher w = {cg._w_fusion}")
        hdr = f"  {'Phase':<22s}"
        for n in IND_NAMES:
            hdr += f" {n:>10s}"
        print(hdr)
        for pn, (sb, eb) in phase_bins.items():
            row = f"  {pn:<22s}"
            for j in range(7):
                row += f" {raw[sb:eb, j].mean():10.4f}"
            print(row)

        # Weighted contribution
        print(f"\n  Weighted contribution (% of fusion signal):")
        z = (raw - cg._fusion_mu) / (cg._fusion_std + 1e-12)
        z_pos = np.maximum(z, 0)
        wz = z_pos * cg._w_fusion
        hdr = f"  {'Phase':<22s}"
        for n in IND_NAMES:
            hdr += f" {n:>8s}"
        print(hdr)
        for pn, (sb, eb) in phase_bins.items():
            wm = wz[sb:eb].mean(axis=0)
            total = wm.sum() + 1e-12
            row = f"  {pn:<22s}"
            for j in range(7):
                row += f" {wm[j]/total*100:7.1f}%"
            print(row)

        # ────────────────────────────────────────────
        # H. Score + Friction + Tipping
        # ────────────────────────────────────────────
        print(f"\n  ── H. Score S(x), Friction S_f(t), Tipping ──")
        print(f"  {'Phase':<22s} {'S mean':>8s} {'S peak':>8s} "
              f"{'S_f mean':>8s} {'AUC':>6s}")
        for pn, (sb, eb) in phase_bins.items():
            print(f"  {pn:<22s} "
                  f"{scores[sb:eb].mean():8.4f} "
                  f"{scores[sb:eb].max():8.4f} "
                  f"{S_f[sb:eb].mean():8.4f} "
                  f"{(scores[sb:eb] > 0.5).mean():6.1%}")

        # Tipping points
        dS = np.diff(S_f)
        print(f"\n  Tipping (max ΔS_f near onset):")
        for ap in attack_phases:
            sb, eb = phase_bins[ap]
            search_s = max(0, sb - bpd)
            search_e = min(T - 1, eb)
            if search_e > search_s:
                local = dS[search_s:search_e]
                tip_off = int(np.argmax(local))
                tip_bin = search_s + tip_off
                tip_day = tip_bin * BIN / MINS_PER_DAY
                lead_h = (sb - tip_bin) * BIN / 60
                print(f"    {ap:<22s}: day {tip_day:.1f}, "
                      f"ΔS_f={local[tip_off]:+.4f}, lead={lead_h:+.0f}h")

        # ────────────────────────────────────────────
        # I. Lead Time
        # ────────────────────────────────────────────
        print(f"\n  ── I. Lead Time (steps to C*) ──")
        print(f"  {'Phase':<22s} {'mean LT':>10s} {'%LT=0':>7s}")
        for pn, (sb, eb) in phase_bins.items():
            lt = det.lead_time[sb:eb]
            m = lt[lt > 0].mean() if (lt > 0).any() else 0
            print(f"  {pn:<22s} {m:10.2f} "
                  f"{(lt == 0).mean():7.1%}")

        # ────────────────────────────────────────────
        # J. Policy δ* — correction per attack phase
        # ────────────────────────────────────────────
        print(f"\n  ── J. Policy δ* (min-norm correction) ──")
        for ap in attack_phases:
            sb, eb = phase_bins[ap]
            n_s = min(100, eb - sb)
            idx = np.linspace(sb, eb - 1, n_s, dtype=int)
            pt = cg.policy_test(R_all[idx])
            md = pt['min_delta']
            md_norm = pt['min_delta_norm']
            n_out = (~pt['inside_before']).sum()
            mean_norm = md_norm[md_norm > 0].mean() if (md_norm > 0).any() else 0
            # Dominant dimensions
            mean_abs = np.abs(md).mean(axis=0)
            total = mean_abs.sum() + 1e-12
            pcts = mean_abs / total * 100
            top3 = np.argsort(pcts)[::-1][:3]
            top_str = ", ".join(f"dim{i}({pcts[i]:.0f}%)" for i in top3)
            print(f"    {ap:<22s}: outside={n_out}/{n_s}, "
                  f"‖δ*‖={mean_norm:.4f}, dom=[{top_str}]")

        # ────────────────────────────────────────────
        # K. Effect sizes vs normal for all geometric objects
        # ────────────────────────────────────────────
        tensors = [
            ("Q", det.Q), ("λ_max", det.lambda_max),
            ("θ", det.theta), ("AM", det.AM),
            ("δ_C", det.delta_C), ("δ_G", det.delta_G),
            ("δ_A", det.delta_A), ("δ_T", det.delta_T),
            ("E_BS", det.E_BS), ("σ_diss", det.sigma_dissipation),
            ("Φ_eff", det.phi_eff), ("S(x)", det.collapse_score),
        ]
        print(f"\n  ── K. Effect Size (Cohen's d vs normal) ──")
        hdr = f"  {'Tensor':<12s}"
        for ap in attack_phases:
            hdr += f" {ap[:10]:>12s}"
        print(hdr)
        for tname, arr in tensors:
            norm_v = arr[norm_sb:norm_eb]
            row = f"  {tname:<12s}"
            for ap in attack_phases:
                sb, eb = phase_bins[ap]
                d = cohen_d(arr[sb:eb], norm_v)
                row += f" {d:+12.2f}"
            print(row)

        # Store for cross-rep comparison
        results[rep_name] = {
            'cg': cg, 'det': det, 'scores': scores,
            'S_f': S_f, 'raw': raw,
        }

    # ═══════════════════════════════════════════════════════════
    # STEP 3: CROSS-REPRESENTATION COMPARISON
    # ═══════════════════════════════════════════════════════════
    print("\n" + "═" * W)
    print("  CROSS-REPRESENTATION COMPARISON")
    print("═" * W)

    # A. Best score AUC per representation × attack
    print(f"\n  ── CollapseGeometry Score AUC (fraction > 0.5) ──")
    print(f"  {'Representation':<18s}", end="")
    for ap in attack_phases:
        print(f" {ap[:10]:>12s}", end="")
    print()
    for rn, res in results.items():
        row = f"  {rn:<18s}"
        for ap in attack_phases:
            sb, eb = phase_bins[ap]
            auc = (res['scores'][sb:eb] > 0.5).mean()
            row += f" {auc:12.1%}"
        print(row)

    # B. Which geometric object is most discriminative per rep
    tensors_names = ["Q", "λ_max", "θ", "AM", "δ_C", "δ_G",
                     "δ_A", "δ_T", "E_BS", "σ_diss", "Φ_eff", "S(x)"]
    tensors_idx = {
        "Q": "Q", "λ_max": "lambda_max", "θ": "theta", "AM": "AM",
        "δ_C": "delta_C", "δ_G": "delta_G", "δ_A": "delta_A",
        "δ_T": "delta_T", "E_BS": "E_BS", "σ_diss": "sigma_dissipation",
        "Φ_eff": "phi_eff", "S(x)": "collapse_score",
    }

    print(f"\n  ── Most Discriminative Geometric Object per rep × attack ──")
    print(f"  {'Rep × Phase':<30s} {'Best Tensor':>14s} {'d':>8s}")
    for rn, res in results.items():
        det = res['det']
        for ap in attack_phases:
            sb, eb = phase_bins[ap]
            best_name = None
            best_d = 0
            for tname in tensors_names:
                attr = tensors_idx[tname]
                arr = getattr(det, attr)
                d_val = cohen_d(arr[sb:eb], arr[norm_sb:norm_eb])
                if abs(d_val) > abs(best_d):
                    best_d = d_val
                    best_name = tname
            label = f"{rn[:14]}×{ap[:12]}"
            print(f"  {label:<30s} {best_name:>14s} {best_d:+8.2f}")

    # C. Fisher VR weights comparison
    print(f"\n  ── Fisher VR Weights (which indicator matters in each space) ──")
    print(f"  {'Representation':<18s}", end="")
    for n in IND_NAMES:
        print(f" {n:>8s}", end="")
    print()
    for rn, res in results.items():
        w = res['cg']._w_fusion
        row = f"  {rn:<18s}"
        for j in range(7):
            row += f" {w[j]:8.4f}"
        print(row)

    # D. C2 Beacon — the hard target
    print(f"\n  ── C2 BEACON: Can any rep × formula detect it? ──")
    c2_sb, c2_eb = phase_bins['c2_beacon']
    print(f"  {'Rep':<18s} {'S mean':>8s} {'AUC':>6s} "
          f"{'Best tensor':>14s} {'d':>8s}")
    for rn, res in results.items():
        sc = res['scores']
        sm = sc[c2_sb:c2_eb].mean()
        auc = (sc[c2_sb:c2_eb] > 0.5).mean()
        det = res['det']
        best_name = None
        best_d = 0
        for tname in tensors_names:
            attr = tensors_idx[tname]
            arr = getattr(det, attr)
            d_val = cohen_d(arr[c2_sb:c2_eb], arr[norm_sb:norm_eb])
            if abs(d_val) > abs(best_d):
                best_d = d_val
                best_name = tname
        print(f"  {rn:<18s} {sm:8.4f} {auc:6.1%} "
              f"{best_name:>14s} {best_d:+8.2f}")

    # E. Tipping points
    print(f"\n  ── Lateral Movement: Early Warning (lead time) ──")
    lat_sb = phase_bins['lateral_movement'][0]
    for rn, res in results.items():
        dS = np.diff(res['S_f'])
        search_s = max(0, lat_sb - bpd)
        local = dS[search_s:lat_sb]
        if len(local) > 0:
            tip = search_s + int(np.argmax(local))
            lead_h = (lat_sb - tip) * BIN / 60
            print(f"  {rn:<18s}: tipping at bin {tip} = "
                  f"{lead_h:+.0f}h before onset")
        else:
            print(f"  {rn:<18s}: no pre-onset data")

    # ═══════════════════════════════════════════════════════════
    # ASSERTIONS
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * W)
    print("  ASSERTIONS")
    print("=" * W)

    n_pass = 0
    n_total = 0

    def check(cond, msg):
        nonlocal n_pass, n_total
        n_total += 1
        n_pass += cond
        print(f"  {'✓' if cond else '✗'} {msg}")

    # All 5 reps fit successfully
    check(len(results) == 5, f"All 5 representations fitted ({len(results)}/5)")

    # Major attacks detected on all reps
    for ap in ['lateral_movement', 'exfiltration', 'ddos']:
        for rn, res in results.items():
            sb, eb = phase_bins[ap]
            auc = (res['scores'][sb:eb] > 0.5).mean()
            check(auc > 0.5, f"{rn}×{ap}: AUC={auc:.1%}")

    # MDN detects C2 beacon (established in prior test)
    if 'MDN' in results:
        c2_auc = (results['MDN']['scores'][c2_sb:c2_eb] > 0.5).mean()
        check(c2_auc > 0.5, f"MDN×C2_beacon: AUC={c2_auc:.1%}")

    # Fisher weights differ across representations
    w_full = results['FullTensor']['cg']._w_fusion
    w_red = results['ReducedTensor']['cg']._w_fusion
    divergence = np.sum(np.abs(w_full - w_red))
    check(divergence > 0.1,
          f"Fisher weights diverge across reps (L1={divergence:.3f})")

    # Recovery returns to baseline on all reps
    rec_sb, rec_eb = phase_bins['recovery']
    for rn, res in results.items():
        rec_mean = res['scores'][rec_sb:rec_eb].mean()
        check(rec_mean < 0.4, f"{rn} recovery: S={rec_mean:.3f} (<0.4)")

    # Q separates attacks from normal on all reps
    for rn, res in results.items():
        q_norm = res['det'].Q[norm_sb:norm_eb].mean()
        q_lat = res['det'].Q[phase_bins['lateral_movement'][0]:
                              phase_bins['lateral_movement'][1]].mean()
        check(q_lat > q_norm * 2,
              f"{rn}: Q_lateral={q_lat:.1f} > 2×Q_normal={q_norm:.1f}")

    print(f"\n  {n_pass}/{n_total} checks passed")
    print("=" * W)

    assert n_pass >= n_total - 3, f"Too many failures: {n_pass}/{n_total}"


if __name__ == "__main__":
    main()
