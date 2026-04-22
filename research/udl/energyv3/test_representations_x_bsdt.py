#!/usr/bin/env python3
"""
4 Representations × Paper BSDT × CollapseGeometry
===================================================
Proper experiment using the actual UDL framework:

  Representations (data → feature space):
    1. Full Tensor    — RepresentationStack (all 6 law operators)
    2. Reduced Tensor — ReducedTensorDescriptor (6-tuple: grad, eigs, mahal, medoid, trace, det)
    3. MDN Vector     — AnomalyTensor (Magnitude-Direction-Novelty)
    4. Coordinate     — CoefficientCoordinates (polynomial + DCT profiles)

  Detection layer:
    A. Paper BSDT     — BSDTChannels (δ_C camouflage, δ_G feature gap,
                         δ_A activity anomaly, δ_T temporal novelty)
    B. CollapseGeometry — geometric detection (Q, θ, BSDT_v3, Fisher VR)

  Pipeline per representation R:
    Raw X → R.fit(X_ref) → R.transform(X) → R_space
    R_space → BSDTChannels.fit(R_ref) → channels(R_test) → δ_C, δ_G, δ_A, δ_T, E_BS
    R_space → CollapseGeometry.fit(R_ref) → score(R_test) → S(t)

  Output: 4 reps × 2 detectors × 7 attack phases → effectiveness matrix
"""
from __future__ import annotations
import sys, os, time, warnings
import numpy as np

warnings.filterwarnings("ignore")

# ── Path setup ──
ROOT = r"c:\amttp"
sys.path.insert(0, os.path.join(ROOT, "research", "udl"))
sys.path.insert(0, os.path.join(ROOT, "research", "udl", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from collapse_geometry import CollapseGeometry
from test_collapse_network_flow import generate_network_flow, downsample, MINS_PER_DAY

# UDL framework — the actual paper implementations
from udl.system_mode import BSDTChannels, ReducedTensorDescriptor
from udl.stack import RepresentationStack
from udl.tensor import AnomalyTensor
from udl.coordinates import CoefficientCoordinates

W = 100
BIN = 10
FEAT_NAMES = ['bytes/s', 'pkts/s', 'avg_pkt', 'flow_ct',
              'dst_ent', 'src_ent', 'syn_ratio', 'out_ratio']


def main():
    np.set_printoptions(precision=4, suppress=True, linewidth=120)

    print("=" * W)
    print("  4 REPRESENTATIONS × PAPER BSDT × COLLAPSE GEOMETRY")
    print("  Network Flow: 30-day capture, 8 features, 7 attack phases")
    print("=" * W)

    # ═══════════════════════════════════════════════════════════
    # DATA
    # ═══════════════════════════════════════════════════════════
    X_raw, phases = generate_network_flow()
    X = downsample(X_raw, BIN)
    T, d = X.shape
    bpd = MINS_PER_DAY // BIN  # bins per day = 144

    phase_bins = {}
    for name, (s, e) in phases.items():
        phase_bins[name] = (s // BIN, e // BIN)

    # Reference: days 1–11 (known normal from prior fit_auto)
    ref_s, ref_e = 144, 1584
    X_ref = X[ref_s:ref_e]
    print(f"\n  Data: {T} bins × {d} features, reference [{ref_s}:{ref_e}]")

    # ═══════════════════════════════════════════════════════════
    # STEP 1: Build 4 representations
    # ═══════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  STEP 1: TRANSFORM DATA INTO 4 REPRESENTATION SPACES")
    print("─" * W)

    representations = {}

    # ── 1a. Full Tensor (RepresentationStack) ──
    print("\n  [1] Full Tensor — RepresentationStack (safe law selection)...")
    t0 = time.time()
    from udl.spectra import (
        StatisticalSpectrum, ChaosSpectrum, SpectralSpectrum,
        ExponentialSpectrum, ReconstructionSpectrum, RankOrderSpectrum,
    )
    safe_ops = [
        ("stat", StatisticalSpectrum()),
        ("chaos", ChaosSpectrum()),
        ("freq", SpectralSpectrum()),
        ("exp", ExponentialSpectrum()),
        ("recon", ReconstructionSpectrum()),
        ("rank", RankOrderSpectrum()),
    ]
    stack = RepresentationStack(operators=safe_ops)
    stack.fit(X_ref)
    R_full_ref = stack.transform(X_ref)
    R_full = stack.transform(X)
    t_full = time.time() - t0
    print(f"      Laws selected: {stack.law_names_}")
    print(f"      Dims per law:  {stack.law_dims_}")
    print(f"      Total D = {R_full.shape[1]}  ({t_full:.1f}s)")
    representations['FullTensor'] = (R_full_ref, R_full, stack.law_dims_)

    # ── 1b. Reduced Tensor (ReducedTensorDescriptor) ──
    print("\n  [2] Reduced Tensor — ReducedTensorDescriptor...")
    t0 = time.time()
    rtd = ReducedTensorDescriptor(k_neighbors=min(15, len(X_ref) - 1))
    rtd.fit(X_ref)
    R_red_ref = rtd.transform(X_ref)
    R_red = rtd.transform(X)
    t_red = time.time() - t0
    print(f"      Descriptor: {rtd.feature_names()}")
    print(f"      D = {R_red.shape[1]}  ({t_red:.1f}s)")
    representations['ReducedTensor'] = (R_red_ref, R_red, None)

    # ── 1c. MDN Vector (AnomalyTensor via RepresentationStack) ──
    print("\n  [3] MDN Vector — AnomalyTensor on Full Tensor output...")
    t0 = time.time()
    mdn = AnomalyTensor()
    mdn.fit(R_full_ref)
    tr_ref = mdn.build(R_full_ref, stack.law_dims_)
    mdn.store_ref_law_stats(tr_ref)
    tr_all = mdn.build(R_full, stack.law_dims_)

    # MDN feature vector: [magnitude, novelty, per-law-magnitudes]
    R_mdn_ref = np.column_stack([
        tr_ref.magnitude[:, None],
        tr_ref.novelty[:, None],
        tr_ref.law_magnitudes,
    ])
    R_mdn = np.column_stack([
        tr_all.magnitude[:, None],
        tr_all.novelty[:, None],
        tr_all.law_magnitudes,
    ])
    t_mdn = time.time() - t0
    n_laws = tr_all.law_magnitudes.shape[1]
    mdn_names = ['magnitude', 'novelty'] + [f'law_{i}' for i in range(n_laws)]
    print(f"      Features: {mdn_names}")
    print(f"      D = {R_mdn.shape[1]}  ({t_mdn:.1f}s)")
    representations['MDN'] = (R_mdn_ref, R_mdn, None)

    # ── 1d. Coordinate (CoefficientCoordinates) ──
    print("\n  [4] Coordinate — CoefficientCoordinates (poly + DCT)...")
    t0 = time.time()
    coord = CoefficientCoordinates(views=['sorted', 'variance'])
    coord.fit(X_ref)
    R_coord_ref, coord_names = coord.transform(X_ref)
    R_coord, _ = coord.transform(X)
    t_coord = time.time() - t0
    print(f"      Axes: {coord_names}")
    print(f"      D = {R_coord.shape[1]}  ({t_coord:.1f}s)")
    representations['Coordinate'] = (R_coord_ref, R_coord, None)

    # ═══════════════════════════════════════════════════════════
    # STEP 2: Paper BSDT on each representation
    # ═══════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  STEP 2: PAPER BSDT CHANNELS ON EACH REPRESENTATION")
    print("  (δ_C=camouflage, δ_G=feature gap, δ_A=activity, δ_T=temporal)")
    print("─" * W)

    bsdt_results = {}
    for rep_name, (R_ref_rep, R_all_rep, _) in representations.items():
        print(f"\n  ── {rep_name} → BSDTChannels ──")
        bsdt = BSDTChannels(k=min(15, len(R_ref_rep) - 1))
        bsdt.fit(R_ref_rep)
        ch = bsdt.channels(R_all_rep)
        E = bsdt.energy(R_all_rep)
        bsdt_results[rep_name] = (ch, E, bsdt)

        # Per-phase channel table
        print(f"  {'Phase':<22s} {'δ_C':>8s} {'δ_G':>8s} "
              f"{'δ_A':>8s} {'δ_T':>8s} {'E_BS':>10s}")
        for phase_name, (sb, eb) in phase_bins.items():
            dC = ch['delta_C'][sb:eb].mean()
            dG = ch['delta_G'][sb:eb].mean()
            dA = ch['delta_A'][sb:eb].mean()
            dT = ch['delta_T'][sb:eb].mean()
            ebs = E[sb:eb].mean()
            print(f"  {phase_name:<22s} {dC:8.4f} {dG:8.4f} "
                  f"{dA:8.4f} {dT:8.4f} {ebs:10.4f}")

    # ═══════════════════════════════════════════════════════════
    # STEP 3: CollapseGeometry on each representation
    # ═══════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  STEP 3: COLLAPSE GEOMETRY ON EACH REPRESENTATION")
    print("─" * W)

    cg_results = {}
    for rep_name, (R_ref_rep, R_all_rep, _) in representations.items():
        print(f"\n  ── {rep_name} → CollapseGeometry ──")
        cg = CollapseGeometry()
        try:
            cg.fit(R_ref_rep)
            scores = cg.score(R_all_rep)
            S_f = cg.score_with_friction(R_all_rep)
            det = cg.detect(R_all_rep)
            cg_results[rep_name] = (scores, S_f, det, cg)

            print(f"  τ_Q={cg._tau_Q:.2f}, θ_crit={cg._theta_crit:.4f}")
            print(f"  Fisher w: {cg._w_fusion}")
            print(f"  {'Phase':<22s} {'S mean':>8s} {'S peak':>8s} "
                  f"{'S_f mean':>8s} {'AUC>0.5':>8s}")
            for phase_name, (sb, eb) in phase_bins.items():
                sm = scores[sb:eb].mean()
                sp = scores[sb:eb].max()
                sfm = S_f[sb:eb].mean()
                auc = (scores[sb:eb] > 0.5).mean()
                print(f"  {phase_name:<22s} {sm:8.4f} {sp:8.4f} "
                      f"{sfm:8.4f} {auc:8.1%}")
        except Exception as e:
            print(f"  FAILED: {e}")
            cg_results[rep_name] = None

    # ═══════════════════════════════════════════════════════════
    # STEP 4: BSDT CHANNEL DEEP DIVE — which channel catches what
    # ═══════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  STEP 4: BSDT CHANNEL × PHASE × REPRESENTATION — EFFECT SIZES")
    print("─" * W)

    ch_names = ['delta_C', 'delta_G', 'delta_A', 'delta_T']
    norm_sb, norm_eb = phase_bins['normal']

    for rep_name, (ch, E, bsdt_obj) in bsdt_results.items():
        print(f"\n  ── {rep_name}: Effect size (Cohen's d) vs normal ──")
        print(f"  {'Phase':<22s}", end="")
        for cn in ch_names:
            print(f" {cn:>10s}", end="")
        print(f" {'E_BS':>10s}")

        for phase_name, (sb, eb) in phase_bins.items():
            if phase_name == 'normal':
                continue
            row = f"  {phase_name:<22s}"
            for cn in ch_names:
                norm_vals = ch[cn][norm_sb:norm_eb]
                phase_vals = ch[cn][sb:eb]
                pooled_std = np.sqrt(
                    (norm_vals.var() + phase_vals.var()) / 2 + 1e-12)
                d_cohen = (phase_vals.mean() - norm_vals.mean()) / pooled_std
                row += f" {d_cohen:+10.2f}"
            # E_BS effect size
            e_norm = E[norm_sb:norm_eb]
            e_phase = E[sb:eb]
            pooled = np.sqrt((e_norm.var() + e_phase.var()) / 2 + 1e-12)
            d_e = (e_phase.mean() - e_norm.mean()) / pooled
            row += f" {d_e:+10.2f}"
            print(row)

    # ═══════════════════════════════════════════════════════════
    # STEP 5: C2 BEACON DEEP DIVE — can any combo detect it?
    # ═══════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  STEP 5: C2 BEACON DETECTION — ALL REPRESENTATIONS × ALL CHANNELS")
    print("─" * W)

    c2_sb, c2_eb = phase_bins['c2_beacon']

    print(f"\n  Effect sizes (Cohen's d) for C2 beacon vs normal:")
    print(f"  {'Representation':<18s}", end="")
    for cn in ch_names:
        print(f" {cn:>10s}", end="")
    print(f" {'E_BS':>10s} {'CG_score':>10s}")

    for rep_name in representations:
        ch, E, _ = bsdt_results[rep_name]
        row = f"  {rep_name:<18s}"
        for cn in ch_names:
            nv = ch[cn][norm_sb:norm_eb]
            cv = ch[cn][c2_sb:c2_eb]
            ps = np.sqrt((nv.var() + cv.var()) / 2 + 1e-12)
            row += f" {(cv.mean() - nv.mean()) / ps:+10.3f}"
        # E_BS
        en = E[norm_sb:norm_eb]
        ec = E[c2_sb:c2_eb]
        ps = np.sqrt((en.var() + ec.var()) / 2 + 1e-12)
        row += f" {(ec.mean() - en.mean()) / ps:+10.3f}"
        # CG score
        if cg_results[rep_name] is not None:
            scores = cg_results[rep_name][0]
            sn = scores[norm_sb:norm_eb]
            sc = scores[c2_sb:c2_eb]
            ps = np.sqrt((sn.var() + sc.var()) / 2 + 1e-12)
            row += f" {(sc.mean() - sn.mean()) / ps:+10.3f}"
        else:
            row += f" {'FAIL':>10s}"
        print(row)

    # ═══════════════════════════════════════════════════════════
    # STEP 6: MASTER SUMMARY — EFFECTIVENESS MATRIX
    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * W)
    print("  MASTER EFFECTIVENESS MATRIX (AUC>0.5 for attacks)")
    print("=" * W)

    attack_phases = ['reconnaissance', 'c2_beacon', 'lateral_movement',
                     'exfiltration', 'ddos']

    # BSDT E_BS detection rate
    print(f"\n  ── BSDT E_BS: fraction above normal p95 ──")
    print(f"  {'Representation':<18s}", end="")
    for ap in attack_phases:
        print(f" {ap[:10]:>12s}", end="")
    print()

    for rep_name in representations:
        ch, E, _ = bsdt_results[rep_name]
        e_thresh = np.percentile(E[norm_sb:norm_eb], 95)
        row = f"  {rep_name:<18s}"
        for ap in attack_phases:
            sb, eb = phase_bins[ap]
            det_rate = (E[sb:eb] > e_thresh).mean()
            row += f" {det_rate:12.1%}"
        print(row)

    # CG score detection rate
    print(f"\n  ── CollapseGeometry: fraction with score > 0.5 ──")
    print(f"  {'Representation':<18s}", end="")
    for ap in attack_phases:
        print(f" {ap[:10]:>12s}", end="")
    print()

    for rep_name in representations:
        if cg_results[rep_name] is None:
            print(f"  {rep_name:<18s} {'FAILED':>12s}")
            continue
        scores = cg_results[rep_name][0]
        row = f"  {rep_name:<18s}"
        for ap in attack_phases:
            sb, eb = phase_bins[ap]
            det_rate = (scores[sb:eb] > 0.5).mean()
            row += f" {det_rate:12.1%}"
        print(row)

    # ═══════════════════════════════════════════════════════════
    # STEP 7: DOMINANT BSDT CHANNEL PER REPRESENTATION × PHASE
    # ═══════════════════════════════════════════════════════════
    print(f"\n  ── Dominant BSDT Channel per representation × attack ──")
    print(f"  {'Rep × Phase':<30s} {'Winner':>10s} {'Effect':>8s}")

    for rep_name in representations:
        ch, E, _ = bsdt_results[rep_name]
        for ap in attack_phases:
            sb, eb = phase_bins[ap]
            best_ch = 'none'
            best_d = 0.0
            for cn in ch_names:
                nv = ch[cn][norm_sb:norm_eb]
                pv = ch[cn][sb:eb]
                ps = np.sqrt((nv.var() + pv.var()) / 2 + 1e-12)
                d_cohen = (pv.mean() - nv.mean()) / ps
                if abs(d_cohen) > abs(best_d):
                    best_d = d_cohen
                    best_ch = cn
            label = f"{rep_name[:12]}×{ap[:10]}"
            print(f"  {label:<30s} {best_ch:>10s} {best_d:+8.2f}")

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
        status = "✓" if cond else "✗"
        n_pass += cond
        print(f"  {status} {msg}")
        return cond

    # All 4 representations produced output
    for rn in ['FullTensor', 'ReducedTensor', 'MDN', 'Coordinate']:
        check(rn in representations and representations[rn][1].shape[0] == T,
              f"{rn} produced {representations[rn][1].shape[1]}D output")

    # All 4 BSDT results exist
    for rn in representations:
        check(rn in bsdt_results,
              f"BSDT computed on {rn}")

    # At least 2 CG fits succeeded
    n_cg_ok = sum(1 for v in cg_results.values() if v is not None)
    check(n_cg_ok >= 2, f"CollapseGeometry succeeded on {n_cg_ok}/4 reps")

    # Lateral/exfil/DDoS detected by at least one method
    for ap in ['lateral_movement', 'exfiltration', 'ddos']:
        sb, eb = phase_bins[ap]
        detected = False
        for rn in representations:
            ch, E, _ = bsdt_results[rn]
            thresh = np.percentile(E[norm_sb:norm_eb], 95)
            if (E[sb:eb] > thresh).mean() > 0.5:
                detected = True
                break
            if cg_results[rn] is not None:
                if (cg_results[rn][0][sb:eb] > 0.5).mean() > 0.5:
                    detected = True
                    break
        check(detected, f"{ap} detected by at least one rep × detector")

    # BSDT channels are paper-correct (camouflage inverts for attacks)
    # δ_C should be LOW for large attacks (they don't blend in)
    for rn in representations:
        ch, _, _ = bsdt_results[rn]
        dc_normal = ch['delta_C'][norm_sb:norm_eb].mean()
        dc_ddos = ch['delta_C'][phase_bins['ddos'][0]:
                                 phase_bins['ddos'][1]].mean()
        check(dc_ddos < dc_normal,
              f"{rn}: δ_C(DDoS)={dc_ddos:.3f} < δ_C(normal)={dc_normal:.3f} "
              f"(camouflage correct)")

    # δ_T should be HIGH for novel attacks
    for rn in representations:
        ch, _, _ = bsdt_results[rn]
        dt_normal = ch['delta_T'][norm_sb:norm_eb].mean()
        dt_ddos = ch['delta_T'][phase_bins['ddos'][0]:
                                 phase_bins['ddos'][1]].mean()
        check(dt_ddos > dt_normal,
              f"{rn}: δ_T(DDoS)={dt_ddos:.3f} > δ_T(normal)={dt_normal:.3f} "
              f"(temporal novelty correct)")

    print(f"\n  {n_pass}/{n_total} checks passed")
    print("=" * W)

    assert n_pass >= n_total - 3, \
        f"Too many failures: {n_pass}/{n_total}"


if __name__ == "__main__":
    main()
