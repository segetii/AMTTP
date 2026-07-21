#!/usr/bin/env python3
"""
Physics Signals Early Warning Analysis
=======================================
Runs BSDTChannels directly on each domain's raw time-series
(no engine simulation) to measure the intrinsic lead time of
each physics observable:

  E_BS    — Blind-spot energy (anomaly potential well depth)
  MFLS    — Mahalanobis Field Line Score  ‖∇E_BS‖  (gradient norm)
  ρ_MFLS  — State/channel alignment ratio  (>1 = collapse amplification)
  γ*      — Adaptive friction = E_BS / (E_BS + θ)  (damping onset)
  δ_A     — Mahalanobis activity anomaly channel
  δ_T     — Temporal novelty channel

Key physics insight (user's observation):
  - γ* rising IS the early warning: as E_BS climbs the system needs
    more damping to resist collapse.  First γ* > θ marks the tipping point.
  - Curvature (λ_max Hessian of E_BS) turning negative → saddle → collapse.
  - MFLS > baseline → gradient of anomaly potential growing → approaching cliff.

All thresholds are derived from the pre-onset window only (zero label leakage).
"""
from __future__ import annotations
import sys, os, time, json, warnings
import numpy as np

warnings.filterwarnings("ignore")

ROOT = r"c:\amttp"
sys.path.insert(0, os.path.join(ROOT, "research", "udl"))
sys.path.insert(0, ROOT)

from udl.system_mode import BSDTChannels
from sklearn.preprocessing import StandardScaler

# ─── Re-use domain loaders from the main benchmark ────────────────────────────
from test_all_engines_all_domains import (
    load_gsib_banking, load_fdic_us, load_ercot_combined,
    load_protein, load_chbmit,
)

# ──────────────────────────────────────────────────────────────────────────────
#  PHYSICS SIGNAL EXTRACTOR
# ──────────────────────────────────────────────────────────────────────────────

def compute_physics_signals(X: np.ndarray, onset_idx: int,
                             k: int = 15, theta: float | None = None,
                             win: int = 20) -> dict:
    """
    Compute per-sample physics signals using BSDTChannels fitted on
    the pre-onset window only.

    Parameters
    ----------
    X         : (N, d) feature array (raw, will be z-scored internally)
    onset_idx : first crisis sample index
    k         : kNN parameter for BSDT
    theta     : θ for γ* = E_BS/(E_BS+θ).  None = auto from pre-onset median.
    win       : rolling window for smoothing signals (causal)

    Returns dict of (N,) arrays: E_BS, MFLS, rho_MFLS, gamma_star,
                                  delta_A, delta_T, delta_C, delta_G
    and scalar metadata.
    """
    # ── Z-score on pre-onset only ──
    scaler = StandardScaler()
    X_ref  = X[:onset_idx].astype(np.float64)
    scaler.fit(X_ref)
    X_scaled = scaler.transform(X.astype(np.float64))
    X_ref_sc = X_scaled[:onset_idx]

    # ── Fit BSDT on pre-onset reference ──
    k_use = min(k, len(X_ref_sc) - 2)
    bsdt = BSDTChannels(k=k_use)
    bsdt.fit(X_ref_sc)

    # ── Auto-calibrate θ from pre-onset E_BS median ──
    E_ref = bsdt.energy(X_ref_sc)
    if theta is None:
        theta = float(np.median(E_ref))
    theta = max(theta, 1e-10)

    # ── Compute all signals per sample ──
    N = len(X_scaled)
    E_BS    = np.zeros(N)
    MFLS    = np.zeros(N)
    rho     = np.zeros(N)
    gamma   = np.zeros(N)
    dA      = np.zeros(N)
    dT      = np.zeros(N)
    dC      = np.zeros(N)
    dG      = np.zeros(N)

    bs = 256   # batch size — avoids OOM on large EEG
    for start in range(0, N, bs):
        end  = min(start + bs, N)
        Xb   = X_scaled[start:end]
        e    = bsdt.energy(Xb)
        ml   = bsdt.mfls_state(Xb)
        rh   = bsdt.rho_mfls(Xb)
        ch   = bsdt.channels(Xb)
        E_BS[start:end]  = e
        MFLS[start:end]  = ml
        rho[start:end]   = rh
        gamma[start:end] = e / (e + theta)
        dA[start:end]    = ch['delta_A']
        dT[start:end]    = ch['delta_T']
        dC[start:end]    = ch['delta_C']
        dG[start:end]    = ch['delta_G']

    # ── Causal rolling mean ──
    def _roll(s, w):
        if w <= 1:
            return s
        k = np.ones(w) / w
        return np.convolve(s, k, mode='full')[:N]

    signals = {
        'E_BS':       E_BS,
        'MFLS':       MFLS,
        'rho_MFLS':   rho,
        'gamma_star': gamma,
        'delta_A':    dA,
        'delta_T':    dT,
        'delta_C':    dC,
        'delta_G':    dG,
    }

    # ── Early warning metrics for each signal ──
    results = {}
    roll_signals = {k: _roll(v, win) for k, v in signals.items()}

    for name, sig in roll_signals.items():
        pre  = sig[:onset_idx]
        thresh = float(pre.mean() + 2.0 * pre.std())

        lead  = 0
        hit   = False
        for i in range(onset_idx):
            if sig[i] >= thresh:
                lead = onset_idx - i
                hit  = True
                break

        # FA rate: alarm bursts per 100 pre-onset periods
        bursts, in_burst = 0, False
        for v in pre >= thresh:
            if v and not in_burst:
                bursts += 1; in_burst = True
            elif not v:
                in_burst = False
        fa = 100.0 * bursts / max(onset_idx, 1)

        # Discrimination: mean post / mean pre
        post = sig[onset_idx:]
        disc = float(post.mean() / (pre.mean() + 1e-10)) if len(post) else 1.0

        results[name] = dict(lead=int(lead), hit=hit,
                             fa=round(fa, 2), disc=round(disc, 3),
                             thresh=round(thresh, 6))

    return results, signals, {'theta': theta, 'onset_idx': onset_idx,
                               'N': N, 'd': X.shape[1]}


# ──────────────────────────────────────────────────────────────────────────────
#  PRINTER
# ──────────────────────────────────────────────────────────────────────────────

def print_domain(label: str, meta: dict, results: dict, domain_meta: dict):
    unit   = domain_meta.get('unit', 'periods')
    onset  = domain_meta.get('onset_idx', meta['onset_idx'])
    N      = meta['N']
    theta  = meta['theta']

    print(f"\n{'═'*70}")
    print(f"  {label}")
    print(f"  N={N}  d={meta['d']}  onset@{onset}  θ={theta:.4f}  unit={unit}")
    print(f"{'═'*70}")
    print(f"  {'Signal':<12} {'Lead':>6} {'Hit':>5} {'FA/100':>8} {'Disc×':>7}")
    print(f"  {'':─<12} {'':─>6} {'':─>5} {'':─>8} {'':─>7}")
    for sig, r in results.items():
        lead_str = f"{r['lead']}*" if r['hit'] else f"{r['lead']}"
        print(f"  {sig:<12} {lead_str:>6} "
              f"{'YES' if r['hit'] else 'no':>5} "
              f"{r['fa']:>8.2f} {r['disc']:>7.3f}")

    # Highlight the physics story
    hit_sigs = {k: v for k, v in results.items() if v['hit']}
    if hit_sigs:
        first = max(hit_sigs, key=lambda k: hit_sigs[k]['lead'])
        last  = min(hit_sigs, key=lambda k: hit_sigs[k]['lead'])
        print(f"\n  ► First alarm : {first:<12}  lead={hit_sigs[first]['lead']} {unit}")
        print(f"  ► Last alarm  : {last:<12}  lead={hit_sigs[last]['lead']} {unit}")

        # γ* vs E_BS comparison
        if 'gamma_star' in results and 'E_BS' in results:
            gam = results['gamma_star']
            ebs = results['E_BS']
            if gam['hit'] and ebs['hit']:
                diff = gam['lead'] - ebs['lead']
                print(f"  ► γ* leads E_BS by {diff:+d} {unit}  "
                      f"(damping onset {'before' if diff>0 else 'after'} energy peak)")

        # MFLS vs γ*
        if 'MFLS' in results and 'gamma_star' in results:
            mf = results['MFLS']
            gm = results['gamma_star']
            if mf['hit'] and gm['hit']:
                diff = mf['lead'] - gm['lead']
                print(f"  ► MFLS leads γ* by {diff:+d} {unit}  "
                      f"(gradient alarm {'before' if diff>0 else 'after'} friction onset)")


# ──────────────────────────────────────────────────────────────────────────────
#  CROSS-DOMAIN SUMMARY TABLE
# ──────────────────────────────────────────────────────────────────────────────

def print_summary(all_domain_results: dict, domain_metas: dict):
    signals = ['E_BS', 'MFLS', 'rho_MFLS', 'gamma_star', 'delta_A', 'delta_T']
    domains = list(all_domain_results.keys())

    print(f"\n{'█'*70}")
    print("  PHYSICS SIGNALS — CROSS-DOMAIN LEAD TIME MATRIX")
    print("  (* = signal fired before onset, number = periods of advance warning)")
    print(f"{'█'*70}\n")

    # Column widths
    short_d = [d.split(':')[0].strip() + ':' + d.split(':')[1][:7].strip()
               for d in domains]
    cw = 11

    hdr = f"  {'Signal':<12}" + "".join(f" {sd:>{cw}}" for sd in short_d)
    print(hdr)
    print("  " + "─" * (12 + (cw + 1) * len(domains)))

    for sig in signals:
        row = f"  {sig:<12}"
        for dom in domains:
            res = all_domain_results[dom].get(sig)
            if res is None:
                cell = "-"
            else:
                lead = res['lead']
                mark = "*" if res['hit'] else ""
                cell = f"{lead}{mark}"
            row += f" {cell:>{cw}}"
        print(row)

    print(f"\n  Physics reading:")
    print(f"    E_BS     = blind-spot energy — fundamental anomaly potential")
    print(f"    MFLS     = ‖∇E_BS‖ — gradient of that potential (pre-collapse cliff)")
    print(f"    rho_MFLS = state/channel alignment — >1 means collapse is amplifying")
    print(f"    gamma_*  = E_BS/(E_BS+θ) — adaptive friction; rising = system resisting")
    print(f"    delta_A  = Mahalanobis activity anomaly")
    print(f"    delta_T  = temporal novelty (sudden change in data character)")
    print(f"")
    print(f"  Interpretation: when gamma_* rises first, the system WANTS to collapse")
    print(f"  (high E_BS) and the physics damps it.  MFLS rising = the gradient")
    print(f"  of the anomaly potential is steepening — the cliff is getting closer.")
    print(f"  rho_MFLS > 1 means the physical state is AMPLIFYING the channel signals")
    print(f"  rather than containing them — this is the strongest collapse indicator.")


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────────────────────

DOMAINS = [
    ("A: G-SIB Banking",   load_gsib_banking,   dict(k=5,  win=1)),
    ("B: FDIC US Banks",   load_fdic_us,         dict(k=5,  win=1)),
    ("C: ERCOT Grid",      load_ercot_combined,  dict(k=15, win=5)),
    ("D: Protein Folding", load_protein,         dict(k=10, win=3)),
    ("E: CHB-MIT EEG",     load_chbmit,          dict(k=15, win=60)),
]


def main():
    t0_total = time.time()
    print("=" * 70)
    print("  PHYSICS SIGNALS EARLY WARNING — BSDTChannels direct analysis")
    print("  No engine simulation.  Raw time-series → E_BS, MFLS, γ*, ρ")
    print("=" * 70)

    all_results: dict = {}
    all_domain_metas: dict = {}

    for label, loader, ew_kw in DOMAINS:
        print(f"\n{'─'*70}")
        print(f"  Loading: {label}")
        t0 = time.time()
        X, y, onset_idx, dmeta = loader()
        if X is None:
            print(f"  SKIPPED — {dmeta.get('status','?')}")
            continue
        print(f"  Loaded {X.shape} in {time.time()-t0:.1f}s  onset@{onset_idx}")

        t0 = time.time()
        res, sigs, meta = compute_physics_signals(
            X, onset_idx,
            k=ew_kw['k'], win=ew_kw['win'])
        print(f"  Signals computed in {time.time()-t0:.1f}s")

        print_domain(label, meta, res, dmeta)
        all_results[label] = res
        all_domain_metas[label] = dmeta

    print_summary(all_results, all_domain_metas)

    out = os.path.join(ROOT, "physics_signals_results.json")

    def _j(o):
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        if isinstance(o, np.ndarray): return o.tolist()
        return str(o)

    with open(out, "w") as f:
        json.dump({"results": all_results, "metas": all_domain_metas,
                   "elapsed_s": round(time.time()-t0_total, 1)},
                  f, indent=2, default=_j)
    print(f"\n  Results → {out}")
    print(f"  Total: {time.time()-t0_total:.0f}s")


if __name__ == "__main__":
    main()
