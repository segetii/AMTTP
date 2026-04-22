#!/usr/bin/env python3
"""
CollapseGeometry on Cybersecurity Network Flow
================================================
Network traffic doesn't have a guaranteed clean start — attackers may
already be present.  fit_auto() searches for the most stable baseline
window automatically.

Scenario: 30-day enterprise network capture (1-minute intervals).
  Days  0-3:  Reconnaissance (slow port scan, already embedded)
  Days  3-12: Normal operations (the actual baseline)
  Days 12-14: C2 beaconing begins (low-volume, periodic)
  Days 15-18: Lateral movement (internal flow explosion)
  Days 18-20: Data exfiltration (sustained outbound anomaly)
  Days 20-21: DDoS cover attack (massive traffic spike)
  Days 21-30: Normal + cleanup

Feature vector per minute:
  [0] bytes_per_sec     — total throughput
  [1] pkts_per_sec      — packet rate
  [2] avg_pkt_size      — bytes / packets (protocol mix indicator)
  [3] flow_count        — active flows in this minute
  [4] dst_port_entropy  — Shannon entropy of destination ports
  [5] src_ip_entropy    — Shannon entropy of source IPs
  [6] syn_ratio         — SYN packets / total (handshake anomaly)
  [7] outbound_ratio    — outbound bytes / total (exfil indicator)

fit_auto() should find the Day 3-12 normal window despite the
attack already being underway at t=0.
"""
from __future__ import annotations
import sys, os
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from collapse_geometry import CollapseGeometry

W = 100
MINS_PER_DAY = 1440


def generate_network_flow(seed: int = 2024) -> tuple[np.ndarray, dict]:
    """Generate realistic 30-day enterprise network flow data.

    Returns (X, phases) where X is (T, 8) and phases maps
    phase names to (start_min, end_min) ranges.
    """
    rng = np.random.default_rng(seed)
    T = 30 * MINS_PER_DAY  # 43200 minutes
    d = 8

    # ── Base: diurnal pattern (business hours + night) ──
    t = np.arange(T, dtype=float)
    hour_of_day = (t / 60) % 24

    # Business hours multiplier: peak at 10am-2pm, low at 2-6am
    diurnal = 0.3 + 0.7 * np.exp(-((hour_of_day - 12) ** 2) / 18)

    # Weekly pattern: weekends are ~40% of weekday
    day_of_week = (t / MINS_PER_DAY).astype(int) % 7
    weekly = np.where(day_of_week >= 5, 0.4, 1.0)

    base_activity = diurnal * weekly

    # ── Normal baseline profiles ──
    bytes_ps = 50e6 * base_activity + rng.normal(0, 2e6, T)     # ~50 MB/s peak
    pkts_ps = 40000 * base_activity + rng.normal(0, 2000, T)     # ~40k pps peak
    avg_pkt = 1250 + rng.normal(0, 50, T)                        # ~1250 bytes avg
    flow_ct = 8000 * base_activity + rng.normal(0, 500, T)       # ~8k flows
    dst_ent = 3.5 + 0.3 * base_activity + rng.normal(0, 0.1, T) # port entropy
    src_ent = 4.0 + 0.2 * base_activity + rng.normal(0, 0.08, T)# src IP entropy
    syn_rat = 0.12 + rng.normal(0, 0.01, T)                      # ~12% SYN
    out_rat = 0.35 + rng.normal(0, 0.02, T)                      # ~35% outbound

    phases = {}

    # ── Phase 1: Reconnaissance (Day 0-3) ──
    # Slow port scan: elevated dst_port_entropy, slightly more SYN
    p1_start, p1_end = 0, 3 * MINS_PER_DAY
    phases['reconnaissance'] = (p1_start, p1_end)
    scan_intensity = rng.uniform(0.3, 0.8, p1_end - p1_start)
    dst_ent[p1_start:p1_end] += 0.8 * scan_intensity  # more diverse ports
    syn_rat[p1_start:p1_end] += 0.03 * scan_intensity  # more SYN probes
    flow_ct[p1_start:p1_end] += 800 * scan_intensity   # extra micro-flows

    # ── Phase 2: Normal operations (Day 3-12) — THE BASELINE ──
    p2_start, p2_end = 3 * MINS_PER_DAY, 12 * MINS_PER_DAY
    phases['normal'] = (p2_start, p2_end)
    # No modifications — this is genuine normal

    # ── Phase 3: C2 beaconing (Day 12-14) ──
    # Periodic bursts every ~5 min, small but regular
    p3_start, p3_end = 12 * MINS_PER_DAY, 14 * MINS_PER_DAY
    phases['c2_beacon'] = (p3_start, p3_end)
    beacon_mask = np.zeros(p3_end - p3_start)
    beacon_mask[::5] = 1.0  # every 5 minutes
    bytes_ps[p3_start:p3_end] += 500e3 * beacon_mask     # 500KB bursts
    out_rat[p3_start:p3_end] += 0.04 * beacon_mask        # slightly more outbound
    # C2 uses consistent port → lower port entropy
    dst_ent[p3_start:p3_end] -= 0.15 * beacon_mask

    # ── Phase 4: Lateral movement (Day 15-18) ──
    # Internal flow explosion, new src-dst pairs
    p4_start, p4_end = 15 * MINS_PER_DAY, 18 * MINS_PER_DAY
    phases['lateral_movement'] = (p4_start, p4_end)
    lateral_ramp = np.linspace(0, 1, p4_end - p4_start)
    flow_ct[p4_start:p4_end] += 5000 * lateral_ramp       # +5k flows ramping
    src_ent[p4_start:p4_end] += 1.2 * lateral_ramp        # many new sources
    pkts_ps[p4_start:p4_end] += 15000 * lateral_ramp      # more packets
    avg_pkt[p4_start:p4_end] -= 300 * lateral_ramp         # smaller packets (SMB, RPC)
    syn_rat[p4_start:p4_end] += 0.08 * lateral_ramp        # connection storm

    # ── Phase 5: Data exfiltration (Day 18-20) ──
    # Sustained outbound anomaly
    p5_start, p5_end = 18 * MINS_PER_DAY, 20 * MINS_PER_DAY
    phases['exfiltration'] = (p5_start, p5_end)
    exfil_pattern = 0.7 + 0.3 * np.sin(np.linspace(0, 8 * np.pi,
                                                     p5_end - p5_start))
    bytes_ps[p5_start:p5_end] += 30e6 * exfil_pattern     # +30 MB/s outbound
    out_rat[p5_start:p5_end] += 0.25 * exfil_pattern       # 35→60% outbound
    avg_pkt[p5_start:p5_end] += 300 * exfil_pattern         # large packets (data)
    dst_ent[p5_start:p5_end] -= 0.5 * exfil_pattern         # few exfil destinations

    # ── Phase 6: DDoS cover (Day 20-21) ──
    # Massive traffic spike to cover tracks
    p6_start, p6_end = 20 * MINS_PER_DAY, 21 * MINS_PER_DAY
    phases['ddos'] = (p6_start, p6_end)
    ddos_wave = np.abs(np.sin(np.linspace(0, 6 * np.pi,
                                           p6_end - p6_start)))
    bytes_ps[p6_start:p6_end] += 200e6 * ddos_wave        # +200 MB/s flood
    pkts_ps[p6_start:p6_end] += 300000 * ddos_wave        # +300k pps
    flow_ct[p6_start:p6_end] += 50000 * ddos_wave         # massive flow count
    syn_rat[p6_start:p6_end] += 0.40 * ddos_wave          # SYN flood
    avg_pkt[p6_start:p6_end] -= 800 * ddos_wave           # tiny SYN packets
    src_ent[p6_start:p6_end] += 2.0 * ddos_wave           # spoofed sources

    # ── Phase 7: Recovery (Day 21-30) ──
    p7_start, p7_end = 21 * MINS_PER_DAY, 30 * MINS_PER_DAY
    phases['recovery'] = (p7_start, p7_end)
    # Gradual return to normal with slight residual elevation
    recovery_decay = np.exp(-np.linspace(0, 3, p7_end - p7_start))
    flow_ct[p7_start:p7_end] += 1000 * recovery_decay
    syn_rat[p7_start:p7_end] += 0.02 * recovery_decay

    # ── Clamp to physical bounds ──
    bytes_ps = np.maximum(bytes_ps, 1e3)
    pkts_ps = np.maximum(pkts_ps, 10)
    avg_pkt = np.clip(avg_pkt, 64, 9000)  # MTU bounds
    flow_ct = np.maximum(flow_ct, 10)
    dst_ent = np.clip(dst_ent, 0, 8)
    src_ent = np.clip(src_ent, 0, 8)
    syn_rat = np.clip(syn_rat, 0.01, 0.95)
    out_rat = np.clip(out_rat, 0.05, 0.95)

    X = np.column_stack([bytes_ps, pkts_ps, avg_pkt, flow_ct,
                         dst_ent, src_ent, syn_rat, out_rat])

    return X, phases


def downsample(X: np.ndarray, factor: int = 10) -> np.ndarray:
    """Downsample to N-minute bins by averaging."""
    T = (len(X) // factor) * factor
    return X[:T].reshape(-1, factor, X.shape[1]).mean(axis=1)


def main():
    np.set_printoptions(precision=4, suppress=True)

    print("=" * W)
    print("  COLLAPSE GEOMETRY — CYBERSECURITY NETWORK FLOW")
    print("  30-day enterprise capture, 8 features")
    print("=" * W)

    X_raw, phases = generate_network_flow()
    # Downsample to 10-minute bins for tractability
    BIN = 10
    X = downsample(X_raw, BIN)
    T, d = X.shape
    bins_per_day = MINS_PER_DAY // BIN

    print(f"\n  Raw: {len(X_raw)} minutes → Binned: {T} × {d} "
          f"({BIN}-min bins)")
    print(f"  Features: bytes/s, pkts/s, avg_pkt, flow_count, "
          f"dst_port_ent, src_ip_ent, syn_ratio, outbound_ratio")

    phase_labels = {}
    for name, (s, e) in phases.items():
        sb, eb = s // BIN, e // BIN
        phase_labels[name] = (sb, eb)
        day_s, day_e = s / MINS_PER_DAY, e / MINS_PER_DAY
        print(f"  {name:20s}: bins [{sb:5d}:{eb:5d}]  "
              f"(day {day_s:.0f}–{day_e:.0f})")

    # ═════════════════════════════════════════════════════════
    # A. fit_auto — find normal window despite recon at start
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  A. FIT_AUTO — Finding baseline in compromised capture")
    print("─" * W)

    cg = CollapseGeometry()
    cg.fit_auto(X, min_window=bins_per_day * 3,    # min 3 days
                max_window=bins_per_day * 10,        # max 10 days
                stride=bins_per_day // 2,            # slide by half-day
                verbose=True)

    ref_s, ref_e = cg._ref_start, cg._ref_end
    ref_days = (ref_s * BIN / MINS_PER_DAY, ref_e * BIN / MINS_PER_DAY)
    print(f"\n  Selected reference: bins [{ref_s}:{ref_e}] "
          f"(day {ref_days[0]:.1f}–{ref_days[1]:.1f})")
    print(f"  Validation: {cg._ref_validation['n_passed']}/5 tests")

    # The normal phase is Day 3-12.  fit_auto should land there.
    norm_s, norm_e = phase_labels['normal']
    overlap_s = max(ref_s, norm_s)
    overlap_e = min(ref_e, norm_e)
    overlap = max(0, overlap_e - overlap_s)
    ref_len = ref_e - ref_s
    overlap_pct = overlap / ref_len * 100 if ref_len > 0 else 0
    print(f"  Overlap with true normal: {overlap_pct:.0f}%")

    # ═════════════════════════════════════════════════════════
    # B. Score all phases — detect attack progression
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  B. ATTACK PHASE SCORING")
    print("─" * W)

    scores = cg.score(X)
    S_f = cg.score_with_friction(X)

    phase_results = {}
    print(f"\n  {'Phase':<22s} {'Mean S':>8s} {'Peak S':>8s} "
          f"{'Mean S_f':>8s} {'Peak S_f':>8s} {'AUC':>6s}")
    print("  " + "─" * 68)

    for name, (sb, eb) in phase_labels.items():
        s_slice = scores[sb:eb]
        sf_slice = S_f[sb:eb]
        mean_s = float(s_slice.mean())
        peak_s = float(s_slice.max())
        mean_sf = float(sf_slice.mean())
        peak_sf = float(sf_slice.max())

        # AUC: fraction of bins above 0.5
        auc = float((s_slice > 0.5).mean())

        phase_results[name] = {
            'mean': mean_s, 'peak': peak_s,
            'mean_f': mean_sf, 'peak_f': peak_sf, 'auc': auc,
        }
        print(f"  {name:<22s} {mean_s:8.4f} {peak_s:8.4f} "
              f"{mean_sf:8.4f} {peak_sf:8.4f} {auc:6.1%}")

    # ═════════════════════════════════════════════════════════
    # C. Tipping points — when does each attack phase "ignite"?
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  C. TIPPING POINTS — Attack Phase Transitions")
    print("─" * W)

    # ΔS_f between consecutive bins
    dS = np.diff(S_f)

    for phase_name in ['c2_beacon', 'lateral_movement', 'exfiltration', 'ddos']:
        sb, eb = phase_labels[phase_name]
        # Look for tipping in a window around phase start
        search_start = max(0, sb - bins_per_day)
        search_end = min(T - 1, eb)
        if search_end > search_start:
            local_dS = dS[search_start:search_end]
            tip_offset = int(np.argmax(local_dS))
            tip_bin = search_start + tip_offset
            tip_day = tip_bin * BIN / MINS_PER_DAY
            tip_dS = float(local_dS[tip_offset])
            lead_bins = sb - tip_bin
            lead_hours = lead_bins * BIN / 60

            print(f"  {phase_name:<22s}: tipping at day {tip_day:.1f} "
                  f"(ΔS_f={tip_dS:+.4f}), "
                  f"lead={lead_hours:+.0f}h before phase start")

    # ═════════════════════════════════════════════════════════
    # D. Dominant features per phase — what channel deviates?
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  D. DOMINANT DIVERGENCE CHANNELS")
    print("─" * W)

    feature_names = ['bytes/s', 'pkts/s', 'avg_pkt', 'flow_ct',
                     'dst_ent', 'src_ent', 'syn_ratio', 'out_ratio']

    det = cg.detect(X)
    for phase_name in ['reconnaissance', 'lateral_movement',
                       'exfiltration', 'ddos']:
        sb, eb = phase_labels[phase_name]
        # Use δ* to find dominant correction channel
        # Take a slice of the phase (up to 50 bins)
        end_sample = min(eb, sb + 50)
        X_slice = X[sb:end_sample]
        pt = cg.policy_test(X_slice)
        min_delta = pt['min_delta']  # (N, d)

        if min_delta is not None:
            mean_delta = np.abs(min_delta).mean(axis=0)
            total = mean_delta.sum() + 1e-12
            pcts = mean_delta / total * 100

            top_idx = np.argsort(pcts)[::-1][:3]
            top_str = ", ".join(f"{feature_names[i]}({pcts[i]:.0f}%)"
                                for i in top_idx)
            print(f"  {phase_name:<22s}: {top_str}")
        else:
            print(f"  {phase_name:<22s}: (no gradient available)")

    # ═════════════════════════════════════════════════════════
    # E. Early warning timeline — minute-by-minute around attacks
    # ═════════════════════════════════════════════════════════
    print("\n" + "─" * W)
    print("  E. EARLY WARNING TIMELINE — Lateral Movement Onset")
    print("─" * W)

    lat_start = phase_labels['lateral_movement'][0]
    window = range(max(0, lat_start - 6 * 6),  # 6 hours before
                   min(T, lat_start + 6 * 6))   # 6 hours after
    print(f"\n  {'Bin':>6s} {'Day':>6s} {'Score':>8s} {'S_f':>8s} {'Status'}")
    for b in window:
        day = b * BIN / MINS_PER_DAY
        status = ""
        if b == lat_start:
            status = " ← LATERAL START"
        elif S_f[b] > 0.5 and (b == 0 or S_f[b-1] <= 0.5):
            status = " ← FIRST ALARM"
        elif scores[b] > 0.9:
            status = " ← CRITICAL"
        if status or b % 6 == 0:  # print every hour + transitions
            print(f"  {b:6d} {day:6.2f} {scores[b]:8.4f} "
                  f"{S_f[b]:8.4f}{status}")

    # ═════════════════════════════════════════════════════════
    # F. SUMMARY & ASSERTIONS
    # ═════════════════════════════════════════════════════════
    print("\n" + "=" * W)
    print("  SUMMARY")
    print("=" * W)

    # 1. fit_auto should overlap with true normal
    assert overlap_pct > 30, \
        f"Reference should overlap >30% with normal, got {overlap_pct:.0f}%"
    print(f"  ✓ fit_auto found normal window ({overlap_pct:.0f}% overlap)")

    # 2. Recon should be detected (elevated vs normal)
    recon_peak = phase_results['reconnaissance']['peak']
    normal_mean = phase_results['normal']['mean']
    assert recon_peak > normal_mean + 0.1, \
        f"Recon peak ({recon_peak:.3f}) should exceed normal mean ({normal_mean:.3f})"
    print(f"  ✓ Reconnaissance detected (peak={recon_peak:.4f} vs "
          f"normal mean={normal_mean:.4f})")

    # 3. Lateral movement should be clearly detected
    lateral_peak = phase_results['lateral_movement']['peak']
    assert lateral_peak > 0.7, \
        f"Lateral movement peak should be >0.7, got {lateral_peak:.4f}"
    print(f"  ✓ Lateral movement detected (peak={lateral_peak:.4f})")

    # 4. DDoS should saturate
    ddos_peak = phase_results['ddos']['peak']
    assert ddos_peak > 0.95, \
        f"DDoS peak should be >0.95, got {ddos_peak:.4f}"
    print(f"  ✓ DDoS detected (peak={ddos_peak:.4f})")

    # 5. Exfiltration should be detected
    exfil_mean = phase_results['exfiltration']['mean']
    assert exfil_mean > 0.5, \
        f"Exfil mean should be >0.5, got {exfil_mean:.4f}"
    print(f"  ✓ Exfiltration detected (mean={exfil_mean:.4f})")

    # 6. Normal should be low
    assert normal_mean < 0.4, \
        f"Normal mean should be <0.4, got {normal_mean:.4f}"
    print(f"  ✓ Normal baseline is low (mean={normal_mean:.4f})")

    # 7. Recovery should trend back down
    recovery_end_mean = float(scores[-bins_per_day:].mean())
    ddos_mean = phase_results['ddos']['mean']
    assert recovery_end_mean < ddos_mean, \
        f"Recovery ({recovery_end_mean:.3f}) should be below DDoS ({ddos_mean:.3f})"
    print(f"  ✓ Recovery trending down "
          f"(last day mean={recovery_end_mean:.4f})")

    print(f"\n  7/7 assertions passed")
    print("=" * W)


if __name__ == "__main__":
    main()
