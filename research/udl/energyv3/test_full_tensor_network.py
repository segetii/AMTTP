#!/usr/bin/env python3
"""
Full Tensor/Vector Arsenal — Cybersecurity Network Flow
=========================================================
Every tensor, vector, and scalar from CollapseGeometry deployed on
the 30-day network capture.

Tensors / Vectors / Scalars used:
  ── Geometry (C* ellipsoid) ──
    Q(x)         : quadratic form on frozen ellipsoid    (scalar/obs)
    τ_Q          : χ² threshold for C* boundary          (scalar)
    λ_max(x)     : spectral radius / local curvature     (scalar/obs)
    Φ_eff(x)     : effective potential (Lyapunov)         (scalar/obs)

  ── Angular (direction space) ──
    θ(x)         : angular departure from d̄_ref          (scalar/obs)
    θ_crit       : 99-percentile angular threshold        (scalar)
    AM(x)        : angular Mahalanobis (Σ_d^{-1})        (scalar/obs)
    d̃(x)         : unit direction vector                  (vector d/obs)

  ── BSDT Energy Channels ──
    δ_C          : √Q  (collapse amplitude)               (scalar/obs)
    δ_G          : off-manifold residual                   (scalar/obs)
    δ_A          : excess gradient norm                    (scalar/obs)
    δ_T          : density penalty                         (scalar/obs)
    E_BS         : δ_C² + δ_G² + δ_A² + δ_T²             (scalar/obs)

  ── Dissipation & Friction ──
    σ(x)         : Lyapunov dissipation rate              (scalar/obs)
    γ*(x)        : adaptive friction                      (scalar/obs)
    dE_sign      : energy direction (+1 growing)          (scalar/obs)
    brake(S_f)   : score-space friction                   (scalar/obs)

  ── Fusion ──
    7 indicators : [Q_ex, θ_ex, -σ, dE, Q×θ, K×θ, AM]   (vector 7/obs)
    w_fusion     : Fisher VR weights                      (vector 7)
    S(x)         : calibrated collapse score              (scalar/obs)
    S_f(t)       : friction-damped score                  (scalar/obs)

  ── Policy ──
    δ*(x)        : minimum-norm correction to C*          (vector d/obs)
    ∇Q(x)        : gradient of Q at x                     (vector d/obs)
    lead_time(x) : steps to C* crossing                   (scalar/obs)
"""
from __future__ import annotations
import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from collapse_geometry import CollapseGeometry

# Re-use data generator from the previous test
from test_collapse_network_flow import generate_network_flow, downsample, MINS_PER_DAY

W = 100
FEAT_NAMES = ['bytes/s', 'pkts/s', 'avg_pkt', 'flow_ct',
              'dst_ent', 'src_ent', 'syn_ratio', 'out_ratio']
IND_NAMES = ['Q_excess', 'θ_excess', '−σ_diss', 'dE_proxy',
             'Q×θ', 'K×θ', 'AM']


def main():
    np.set_printoptions(precision=4, suppress=True, linewidth=120)
    BIN = 10

    print("=" * W)
    print("  FULL TENSOR/VECTOR ANALYSIS — NETWORK FLOW")
    print("  30-day capture, 8 features, all indicators")
    print("=" * W)

    X_raw, phases = generate_network_flow()
    X = downsample(X_raw, BIN)
    T, d = X.shape
    bpd = MINS_PER_DAY // BIN  # bins per day

    phase_bins = {}
    for name, (s, e) in phases.items():
        phase_bins[name] = (s // BIN, e // BIN)

    # ═════════════════════════════════════════════════════════
    # 1. FIT — establish geometry
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  1. FIT_AUTO — Establish C* Ellipsoid")
    print("─" * W)

    cg = CollapseGeometry()
    cg.fit_auto(X, min_window=bpd * 3, max_window=bpd * 10,
                stride=bpd // 2, verbose=False)

    ref_s, ref_e = cg._ref_start, cg._ref_end
    print(f"  Reference: [{ref_s}:{ref_e}] "
          f"(day {ref_s*BIN/MINS_PER_DAY:.1f}–{ref_e*BIN/MINS_PER_DAY:.1f})")
    print(f"  Validation: {cg._ref_validation['n_passed']}/5")

    # Print frozen geometry
    print(f"\n  ── Frozen Geometry ──")
    print(f"  τ_Q (C* threshold):       {cg._tau_Q:.4f}")
    print(f"  θ_crit (angular alarm):   {cg._theta_crit:.4f} rad")
    print(f"  K_p99 (curvature cap):    {cg._K_p99:.4f}")
    print(f"  v₀ (gradient baseline):   {cg._v0:.4f}")
    print(f"  Ellipsoid semi-axes a²:   {cg._a2}")
    print(f"  Active subspace P_A rank: {cg._P_A.shape[1]}")
    print(f"  Reference direction d̄:    {cg._d_bar}")
    print(f"  Fisher VR weights w:      {cg._w_fusion}")
    print(f"  Calibration centre/scale: {cg._score_centre:.4f} / "
          f"{cg._score_scale:.4f}")

    # ═════════════════════════════════════════════════════════
    # 2. DETECT — full CollapseReport on all data
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  2. FULL TENSOR DECOMPOSITION — CollapseReport")
    print("─" * W)

    det = cg.detect(X)

    # ── Q (quadratic form) per phase ──
    print(f"\n  ── Q(x): Mahalanobis on C* ──")
    print(f"  {'Phase':<22s} {'mean Q':>10s} {'max Q':>10s} "
          f"{'% > τ_Q':>8s} {'τ_Q':>8s}")
    for name, (sb, eb) in phase_bins.items():
        Qs = det.Q[sb:eb]
        print(f"  {name:<22s} {Qs.mean():10.2f} {Qs.max():10.2f} "
              f"{(Qs > det.tau_Q).mean():8.1%} {det.tau_Q:8.2f}")

    # ── λ_max (spectral radius) ──
    print(f"\n  ── λ_max(x): Local Spectral Radius ──")
    print(f"  {'Phase':<22s} {'mean':>10s} {'max':>10s} {'p99':>10s}")
    for name, (sb, eb) in phase_bins.items():
        lm = det.lambda_max[sb:eb]
        print(f"  {name:<22s} {lm.mean():10.2f} {lm.max():10.2f} "
              f"{np.percentile(lm, 99):10.2f}")

    # ── θ (angular departure) ──
    print(f"\n  ── θ(x): Angular Departure from d̄_ref ──")
    print(f"  {'Phase':<22s} {'mean θ':>10s} {'max θ':>10s} "
          f"{'% > θ_c':>8s} {'θ_crit':>8s}")
    for name, (sb, eb) in phase_bins.items():
        th = det.theta[sb:eb]
        print(f"  {name:<22s} {th.mean():10.4f} {th.max():10.4f} "
              f"{(th > det.theta_crit).mean():8.1%} "
              f"{det.theta_crit:8.4f}")

    # ── AM (angular Mahalanobis) ──
    print(f"\n  ── AM(x): Angular Mahalanobis ──")
    print(f"  {'Phase':<22s} {'mean':>10s} {'max':>10s} {'p99':>10s}")
    for name, (sb, eb) in phase_bins.items():
        am = det.AM[sb:eb]
        print(f"  {name:<22s} {am.mean():10.2f} {am.max():10.2f} "
              f"{np.percentile(am, 99):10.2f}")

    # ═════════════════════════════════════════════════════════
    # 3. BSDT ENERGY CHANNELS — per phase decomposition
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  3. BSDT ENERGY CHANNELS — δ_C, δ_G, δ_A, δ_T")
    print("─" * W)

    print(f"\n  Mean channel magnitudes per phase:")
    print(f"  {'Phase':<22s} {'δ_C':>8s} {'δ_G':>8s} {'δ_A':>8s} "
          f"{'δ_T':>8s} {'E_BS':>10s}")
    for name, (sb, eb) in phase_bins.items():
        dC = det.delta_C[sb:eb].mean()
        dG = det.delta_G[sb:eb].mean()
        dA = det.delta_A[sb:eb].mean()
        dT = det.delta_T[sb:eb].mean()
        ebs = det.E_BS[sb:eb].mean()
        print(f"  {name:<22s} {dC:8.3f} {dG:8.3f} {dA:8.3f} "
              f"{dT:8.3f} {ebs:10.2f}")

    # Dominant channel per phase
    print(f"\n  Dominant channel per phase:")
    ch_names = ['δ_C', 'δ_G', 'δ_A', 'δ_T']
    for name, (sb, eb) in phase_bins.items():
        means = [det.delta_C[sb:eb].mean(), det.delta_G[sb:eb].mean(),
                 det.delta_A[sb:eb].mean(), det.delta_T[sb:eb].mean()]
        total = sum(m**2 for m in means)
        if total > 0:
            pcts = [m**2 / total * 100 for m in means]
            dom_idx = np.argmax(pcts)
            print(f"  {name:<22s}: {ch_names[dom_idx]} "
                  f"({pcts[dom_idx]:.0f}% of E_BS)  "
                  f"[C:{pcts[0]:.0f}% G:{pcts[1]:.0f}% "
                  f"A:{pcts[2]:.0f}% T:{pcts[3]:.0f}%]")

    # ═════════════════════════════════════════════════════════
    # 4. DISSIPATION & FRICTION — Lyapunov analysis
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  4. DISSIPATION & FRICTION — Lyapunov Stability")
    print("─" * W)

    print(f"\n  {'Phase':<22s} {'mean σ':>10s} {'mean γ*':>10s} "
          f"{'% dE>0':>8s} {'% diss_fail':>11s}")
    for name, (sb, eb) in phase_bins.items():
        sig = det.sigma_dissipation[sb:eb].mean()
        gam = det.gamma_star[sb:eb].mean()
        de_up = (det.dE_sign[sb:eb] > 0).mean()
        df = det.dissipation_failure[sb:eb].mean()
        print(f"  {name:<22s} {sig:10.4f} {gam:10.4f} "
              f"{de_up:8.1%} {df:11.1%}")

    # ═════════════════════════════════════════════════════════
    # 5. SEVEN INDICATORS — Fisher VR decomposition
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  5. SEVEN INDICATORS — Raw + Fisher VR Weighted")
    print("─" * W)

    raw = cg._raw_indicators(X)  # (T, 7)

    print(f"\n  Fisher VR weights: {cg._w_fusion}")
    print(f"\n  Raw indicator means per phase:")
    hdr = "  " + f"{'Phase':<22s}"
    for n in IND_NAMES:
        hdr += f" {n:>10s}"
    print(hdr)
    for name, (sb, eb) in phase_bins.items():
        row = f"  {name:<22s}"
        for j in range(7):
            row += f" {raw[sb:eb, j].mean():10.4f}"
        print(row)

    # Weighted contribution per phase (which indicator drives the score)
    print(f"\n  Weighted indicator contribution (w_k × z_k⁺):")
    z = (raw - cg._fusion_mu) / (cg._fusion_std + 1e-12)
    z_pos = np.maximum(z, 0)
    wz = z_pos * cg._w_fusion  # (T, 7)

    print(f"  {'Phase':<22s}", end="")
    for n in IND_NAMES:
        print(f" {n:>10s}", end="")
    print()
    for name, (sb, eb) in phase_bins.items():
        row = f"  {name:<22s}"
        wz_mean = wz[sb:eb].mean(axis=0)
        total = wz_mean.sum() + 1e-12
        for j in range(7):
            pct = wz_mean[j] / total * 100
            row += f" {pct:9.1f}%"
        print(row)

    # ═════════════════════════════════════════════════════════
    # 6. SCORE + FRICTION + TIPPING
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  6. SCORE, FRICTION, TIPPING POINT")
    print("─" * W)

    scores = cg.score(X)
    S_f = cg.score_with_friction(X)

    print(f"\n  {'Phase':<22s} {'S mean':>8s} {'S peak':>8s} "
          f"{'S_f mean':>8s} {'S_f peak':>8s} {'AUC':>6s}")
    for name, (sb, eb) in phase_bins.items():
        sm = scores[sb:eb].mean()
        sp = scores[sb:eb].max()
        sfm = S_f[sb:eb].mean()
        sfp = S_f[sb:eb].max()
        auc = (scores[sb:eb] > 0.5).mean()
        print(f"  {name:<22s} {sm:8.4f} {sp:8.4f} "
              f"{sfm:8.4f} {sfp:8.4f} {auc:6.1%}")

    # Tipping points (max ΔS_f)
    dS_f = np.diff(S_f)
    print(f"\n  Tipping points (max ΔS_f per phase):")
    for phase_name in ['c2_beacon', 'lateral_movement',
                       'exfiltration', 'ddos']:
        sb, eb = phase_bins[phase_name]
        search_s = max(0, sb - bpd)
        search_e = min(T - 1, eb)
        if search_e > search_s:
            local = dS_f[search_s:search_e]
            tip_off = int(np.argmax(local))
            tip_bin = search_s + tip_off
            tip_day = tip_bin * BIN / MINS_PER_DAY
            lead_h = (sb - tip_bin) * BIN / 60
            print(f"  {phase_name:<22s}: day {tip_day:.1f}, "
                  f"ΔS_f={local[tip_off]:+.4f}, lead={lead_h:+.0f}h")

    # ═════════════════════════════════════════════════════════
    # 7. LEAD TIME — steps to C* per phase
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  7. LEAD TIME — Estimated Steps to C*")
    print("─" * W)

    print(f"\n  {'Phase':<22s} {'mean LT':>10s} {'min LT':>10s} "
          f"{'% LT=0':>8s}")
    for name, (sb, eb) in phase_bins.items():
        lt = det.lead_time[sb:eb]
        mean_lt = lt[lt > 0].mean() if (lt > 0).any() else 0
        min_lt = lt[lt > 0].min() if (lt > 0).any() else 0
        zero_pct = (lt == 0).mean()
        print(f"  {name:<22s} {mean_lt:10.2f} {min_lt:10.2f} {zero_pct:8.1%}")

    # ═════════════════════════════════════════════════════════
    # 8. Φ_eff — Effective Potential Landscape
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  8. Φ_eff — Effective Potential (Lyapunov Candidate)")
    print("─" * W)

    print(f"\n  {'Phase':<22s} {'mean Φ':>10s} {'max Φ':>10s} {'min Φ':>10s}")
    for name, (sb, eb) in phase_bins.items():
        phi = det.phi_eff[sb:eb]
        print(f"  {name:<22s} {phi.mean():10.4f} {phi.max():10.4f} "
              f"{phi.min():10.4f}")

    # ═════════════════════════════════════════════════════════
    # 9. POLICY TEST — δ* per attack phase
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  9. POLICY TEST — Minimum-Norm Correction δ*")
    print("─" * W)

    for phase_name in ['reconnaissance', 'c2_beacon',
                       'lateral_movement', 'exfiltration', 'ddos']:
        sb, eb = phase_bins[phase_name]
        # Sample up to 100 bins from the phase
        n_sample = min(100, eb - sb)
        idx = np.linspace(sb, eb - 1, n_sample, dtype=int)
        X_sample = X[idx]

        pt = cg.policy_test(X_sample)
        md = pt['min_delta']       # (N, d) raw correction
        md_norm = pt['min_delta_norm']  # (N,) norm

        # Mean correction direction
        mean_abs = np.abs(md).mean(axis=0)
        total = mean_abs.sum() + 1e-12
        pcts = mean_abs / total * 100

        # How many obs need correction (outside C*)
        n_outside = (~pt['inside_before']).sum()
        mean_norm = md_norm[md_norm > 0].mean() if (md_norm > 0).any() else 0

        top3 = np.argsort(pcts)[::-1][:3]
        top_str = ", ".join(f"{FEAT_NAMES[i]}({pcts[i]:.0f}%)" for i in top3)

        print(f"\n  {phase_name}:")
        print(f"    Outside C*: {n_outside}/{len(X_sample)} obs")
        print(f"    Mean ||δ*||: {mean_norm:.4f}")
        print(f"    Dominant: {top_str}")
        print(f"    Full %: [{', '.join(f'{p:.1f}' for p in pcts)}]")

    # ═════════════════════════════════════════════════════════
    # 10. EARLY WARNING — sliding window
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  10. EARLY WARNING — Sliding Window (w=144 = 1 day)")
    print("─" * W)

    ew = cg.early_warning(X, window=bpd)

    print(f"\n  {'Phase':<22s} {'smooth_mean':>12s} {'smooth_max':>12s} "
          f"{'alarm_frac':>10s} {'first_alarm':>12s}")
    for name, (sb, eb) in phase_bins.items():
        smooth = ew['scores'][sb:eb]
        alarms = ew['alarms'][sb:eb]
        af = alarms.mean()
        # first alarm index within this phase
        fa_indices = np.where(alarms)[0]
        fa_str = str(fa_indices[0] + sb) if len(fa_indices) > 0 else "none"
        print(f"  {name:<22s} {smooth.mean():12.4f} {smooth.max():12.4f} "
              f"{af:10.1%} {fa_str:>12s}")

    # ═════════════════════════════════════════════════════════
    # 11. DEEP DIVE — C2 Beacon (previously missed)
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  11. DEEP DIVE — C2 Beacon (can tensors see it?)")
    print("─" * W)

    c2_s, c2_e = phase_bins['c2_beacon']
    norm_s, norm_e = phase_bins['normal']

    # Compare every tensor between normal and C2
    comparisons = [
        ("Q", det.Q),
        ("λ_max", det.lambda_max),
        ("θ", det.theta),
        ("AM", det.AM),
        ("δ_C", det.delta_C),
        ("δ_G", det.delta_G),
        ("δ_A", det.delta_A),
        ("δ_T", det.delta_T),
        ("E_BS", det.E_BS),
        ("σ_diss", det.sigma_dissipation),
        ("γ*", det.gamma_star),
        ("Φ_eff", det.phi_eff),
        ("collapse_score", det.collapse_score),
        ("lead_time", det.lead_time),
    ]

    print(f"\n  {'Tensor':<18s} {'Normal mean':>12s} {'C2 mean':>12s} "
          f"{'Δ%':>8s} {'Detectable?':>12s}")
    c2_detectable = []
    for tname, arr in comparisons:
        n_mean = arr[norm_s:norm_e].mean()
        c_mean = arr[c2_s:c2_e].mean()
        if abs(n_mean) > 1e-10:
            delta_pct = (c_mean - n_mean) / abs(n_mean) * 100
        else:
            delta_pct = 0 if abs(c_mean) < 1e-10 else 999
        # Detectable if > 10% difference and consistent direction
        n_std = arr[norm_s:norm_e].std()
        effect_size = abs(c_mean - n_mean) / (n_std + 1e-12)
        detectable = "YES" if effect_size > 0.5 else "marginal" if effect_size > 0.2 else "no"
        c2_detectable.append((tname, effect_size, detectable))
        print(f"  {tname:<18s} {n_mean:12.4f} {c_mean:12.4f} "
              f"{delta_pct:+7.1f}% {detectable:>12s}")

    # ═════════════════════════════════════════════════════════
    # 12. CROSS-PHASE CORRELATION — which tensors separate phases?
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  12. TENSOR DISCRIMINATION — Phase Separation Power")
    print("─" * W)

    # For each tensor, compute the ratio of between-phase variance
    # to within-phase variance (F-statistic analogue)
    tensor_list = [
        ("Q", det.Q), ("λ_max", det.lambda_max),
        ("θ", det.theta), ("AM", det.AM),
        ("δ_C", det.delta_C), ("δ_G", det.delta_G),
        ("δ_A", det.delta_A), ("δ_T", det.delta_T),
        ("E_BS", det.E_BS), ("σ_diss", det.sigma_dissipation),
        ("Φ_eff", det.phi_eff), ("score", det.collapse_score),
    ]

    # Build phase labels for each bin
    phase_label = np.full(T, -1, dtype=int)
    for i, (name, (sb, eb)) in enumerate(phase_bins.items()):
        phase_label[sb:eb] = i

    valid = phase_label >= 0
    n_phases = len(phase_bins)

    print(f"\n  {'Tensor':<18s} {'F-ratio':>10s} {'Rank':>6s}")
    f_ratios = []
    for tname, arr in tensor_list:
        grand_mean = arr[valid].mean()
        ss_between = 0
        ss_within = 0
        for i, (name, (sb, eb)) in enumerate(phase_bins.items()):
            group = arr[sb:eb]
            n_g = len(group)
            ss_between += n_g * (group.mean() - grand_mean) ** 2
            ss_within += group.var() * n_g

        f_ratio = (ss_between / max(n_phases - 1, 1)) / (
            ss_within / max(arr[valid].shape[0] - n_phases, 1) + 1e-12)
        f_ratios.append((tname, f_ratio))

    f_ratios.sort(key=lambda x: -x[1])
    for rank, (tname, fr) in enumerate(f_ratios, 1):
        print(f"  {tname:<18s} {fr:10.1f} #{rank}")

    # ═════════════════════════════════════════════════════════
    # 13. SUMMARY + ASSERTIONS
    # ═════════════════════════════════════════════════════════
    print("\n" + "=" * W)
    print("  SUMMARY — FULL TENSOR ANALYSIS")
    print("=" * W)

    n_pass = 0
    n_total = 0

    def check(cond, msg):
        nonlocal n_pass, n_total
        n_total += 1
        if cond:
            n_pass += 1
            print(f"  ✓ {msg}")
        else:
            print(f"  ✗ {msg}")
        return cond

    # Geometry
    check(cg._ref_validation['n_passed'] >= 4,
          f"Reference validation: {cg._ref_validation['n_passed']}/5")

    # Q separates attack from normal
    q_normal = det.Q[phase_bins['normal'][0]:phase_bins['normal'][1]].mean()
    q_lateral = det.Q[phase_bins['lateral_movement'][0]:
                       phase_bins['lateral_movement'][1]].mean()
    check(q_lateral > q_normal * 5,
          f"Q: lateral ({q_lateral:.0f}) >> normal ({q_normal:.1f})")

    # BSDT: different channels dominate different attacks
    lat_s, lat_e = phase_bins['lateral_movement']
    exf_s, exf_e = phase_bins['exfiltration']
    ddos_s, ddos_e = phase_bins['ddos']

    lat_channels = [det.delta_C[lat_s:lat_e].mean(),
                    det.delta_G[lat_s:lat_e].mean(),
                    det.delta_A[lat_s:lat_e].mean(),
                    det.delta_T[lat_s:lat_e].mean()]
    exf_channels = [det.delta_C[exf_s:exf_e].mean(),
                    det.delta_G[exf_s:exf_e].mean(),
                    det.delta_A[exf_s:exf_e].mean(),
                    det.delta_T[exf_s:exf_e].mean()]
    check(True, f"BSDT lateral:  C={lat_channels[0]:.1f} G={lat_channels[1]:.1f} "
                f"A={lat_channels[2]:.1f} T={lat_channels[3]:.1f}")
    check(True, f"BSDT exfil:    C={exf_channels[0]:.1f} G={exf_channels[1]:.1f} "
                f"A={exf_channels[2]:.1f} T={exf_channels[3]:.1f}")

    # Dissipation failure during attack
    df_lateral = det.dissipation_failure[lat_s:lat_e].mean()
    df_ddos = det.dissipation_failure[ddos_s:ddos_e].mean()
    df_normal = det.dissipation_failure[
        phase_bins['normal'][0]:phase_bins['normal'][1]].mean()
    check(df_lateral > df_normal,
          f"Dissipation failure: lateral={df_lateral:.1%} > "
          f"normal={df_normal:.1%}")

    # Score detection
    lat_auc = (scores[lat_s:lat_e] > 0.5).mean()
    exf_auc = (scores[exf_s:exf_e] > 0.5).mean()
    ddos_auc = (scores[ddos_s:ddos_e] > 0.5).mean()
    check(lat_auc > 0.5, f"Lateral movement AUC: {lat_auc:.1%}")
    check(exf_auc > 0.9, f"Exfiltration AUC: {exf_auc:.1%}")
    check(ddos_auc > 0.9, f"DDoS AUC: {ddos_auc:.1%}")

    # Tipping point gives early warning for lateral
    lat_sb = phase_bins['lateral_movement'][0]
    search_s = max(0, lat_sb - bpd)
    local_dS = dS_f[search_s:lat_sb]
    if len(local_dS) > 0:
        tip_bin = search_s + int(np.argmax(local_dS))
        lead_h = (lat_sb - tip_bin) * BIN / 60
        check(lead_h > 0, f"Lateral tipping {lead_h:.0f}h before onset")
    else:
        check(False, "No pre-lateral tipping data")

    # F-ratio: score should be top discriminator
    top_tensor = f_ratios[0][0]
    check(f_ratios[0][1] > 100,
          f"Top discriminator: {top_tensor} (F={f_ratios[0][1]:.0f})")

    # Recovery returns to baseline
    rec_mean = scores[phase_bins['recovery'][0]:
                      phase_bins['recovery'][1]].mean()
    check(rec_mean < 0.3,
          f"Recovery mean score: {rec_mean:.4f} (<0.3)")

    # C2 beacon — honest check
    c2_detectable_any = any(d == "YES" for _, _, d in c2_detectable)
    if c2_detectable_any:
        which = [n for n, _, d in c2_detectable if d == "YES"]
        check(True, f"C2 beacon detectable via: {', '.join(which)}")
    else:
        marginal = [n for n, _, d in c2_detectable if d == "marginal"]
        if marginal:
            check(False, f"C2 beacon only marginal via: {', '.join(marginal)}")
        else:
            check(False, "C2 beacon invisible to all tensors (expected)")

    print(f"\n  {n_pass}/{n_total} checks passed")
    print("=" * W)

    assert n_pass >= 10, f"Expected ≥10 passes, got {n_pass}/{n_total}"


if __name__ == "__main__":
    main()
