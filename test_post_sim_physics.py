#!/usr/bin/env python3
"""
Post-Simulation Physics Signals Analysis
=========================================
The key physical insight: MFLS, γ*, and curvature only become meaningful
collapse indicators AFTER the physics engine has evolved the particles.

Why: The engine simulation pushes anomalous particles toward saddle regions
of the energy landscape. Before simulation, all particles sit at their raw
feature positions — the collapse hasn't "wanted to happen" yet. After
simulation:
  - Normal particles settle into the energy minimum (low E_BS, low MFLS, low γ*)
  - Crisis particles are expelled to high-energy saddle regions
    (high MFLS, high γ*, negative Hessian eigenvalues)

This script runs two analyses:

1. STATIC: Run engine once on full domain. Compare physics observables on
   X_final_ for pre-onset particles vs crisis particles. Confirms that in
   evolved space, MFLS/γ*/curvature separate the two regimes.

2. SLIDING WINDOW: For each time t, run engine on [ref window + recent data],
   extract mean MFLS/γ*/E_BS from X_final_. This creates a temporal series
   showing those observables rising as collapse approaches — BEFORE the onset.
"""
from __future__ import annotations
import sys, os, time, json, warnings
import numpy as np

warnings.filterwarnings("ignore")

ROOT = r"c:\amttp"
sys.path.insert(0, os.path.join(ROOT, "research", "udl"))
sys.path.insert(0, ROOT)

from udl.system_mode import GravityModeEngine, CanonicalODEEngine, BSDTChannels
from sklearn.preprocessing import StandardScaler
from test_all_engines_all_domains import (
    load_gsib_banking, load_fdic_us, load_ercot_combined,
    load_protein, load_chbmit, early_warning_metrics,
)


# ──────────────────────────────────────────────────────────────────────────────
#  HESSIAN CURVATURE  (λ_max(∇²Ē_BS) − 1)
#  Exact replication of CanonicalODEEngine._system_curv(), exposed here so it
#  can be called on any BSDTChannels object + any particle array — in particular
#  on the fixed pre-onset reference BSDT evaluated at evolved positions.
# ──────────────────────────────────────────────────────────────────────────────

def compute_hessian_curv(X: np.ndarray, bsdt: 'BSDTChannels',
                         eps_fd: float = 1e-4) -> float:
    """λ_max(∇²Ē_BS) − 1  —  system-level marginal Hessian curvature indicator.

    Finite-difference Hessian of the mean BSDT gradient over all particles:

        H[i,j] = (∂Ē_BS/∂x_i ∂x_j) ≈ (ḡ(x+ε_j) − ḡ(x−ε_j)) / 2ε

    where ḡ(X) = mean_{particles} ∇E_BS.  Returns λ_max(H) − 1:

        > 0  →  curvature-dominated region  (collapse vicinity)
        ≤ 0  →  convex region               (normal, away from saddle)

    This is the same computation as CanonicalODEEngine._system_curv() and is
    O(d² × N) per call.
    """
    d = X.shape[1]
    H = np.zeros((d, d))
    for k in range(d):
        e_k = np.zeros(d)
        e_k[k] = eps_fd
        gp = bsdt._gradient_vectors(X + e_k).mean(axis=0)
        gm = bsdt._gradient_vectors(X - e_k).mean(axis=0)
        H[:, k] = (gp - gm) / (2.0 * eps_fd)
    H = 0.5 * (H + H.T)          # symmetrise numerical noise
    lam_max = float(np.linalg.eigvalsh(H)[-1])
    return lam_max - 1.0          # §D.3 zero on curvature manifold C_man


# ──────────────────────────────────────────────────────────────────────────────
#  CORE: extract physics observables from evolved X_final_
# ──────────────────────────────────────────────────────────────────────────────

def post_sim_observables(X_work: np.ndarray, normal_mask: np.ndarray,
                          k: int = 10) -> dict:
    """
    After the engine has evolved X_work (= engine.X_final_),
    fit BSDTChannels on the evolved normal particles and compute:
      E_BS, MFLS (‖∇E_BS‖), γ* = E/(E+θ), ρ_MFLS
    on every evolved particle.

    Returns per-particle arrays and Morse alarm (curvature).
    """
    k_use = min(k, int(normal_mask.sum()) - 2)
    if k_use < 2:
        return None

    X_ref_evolved = X_work[normal_mask]
    bsdt = BSDTChannels(k=k_use)
    bsdt.fit(X_ref_evolved)

    theta = max(float(np.median(bsdt.energy(X_ref_evolved))), 1e-10)

    E   = bsdt.energy(X_work)
    M   = bsdt.mfls_state(X_work)
    rho = bsdt.rho_mfls(X_work)
    gam = E / (E + theta)
    ch  = bsdt.channels(X_work)

    # Morse alarm (curvature) on full evolved state — expensive for large N
    # only run if N is manageable
    morse = None
    if len(X_work) <= 500:
        try:
            morse = bsdt.morse_alarm(X_work)
        except Exception:
            pass

    return {
        'E_BS':      E,
        'MFLS':      M,
        'rho_MFLS':  rho,
        'gamma_star': gam,
        'delta_A':   ch['delta_A'],
        'delta_T':   ch['delta_T'],
        'theta':     theta,
        'morse':     morse,
        'bsdt':      bsdt,
    }


# ──────────────────────────────────────────────────────────────────────────────
#  ANALYSIS 1 — STATIC: full-domain engine run, compare pre vs post onset
# ──────────────────────────────────────────────────────────────────────────────

def static_analysis(label: str, X_all: np.ndarray, y_all: np.ndarray,
                    onset_idx: int, meta: dict, k: int = 10) -> dict:
    """
    Run engine on full domain. In X_final_, compare evolved physics
    observables for pre-onset particles vs crisis particles.
    """
    print(f"\n  [Static] Running CanonicalODEEngine (full curvature-adaptive ODE) on "
          f"{label} ({X_all.shape}) ...")
    t0 = time.time()

    eng = CanonicalODEEngine(k_neighbors=min(k, len(X_all) - 2),
                              iterations=60, use_fused=True,
                              curv_update_every=5)
    scores = eng.fit_score(X_all, y_all)

    print(f"  [Static] Done in {time.time()-t0:.1f}s  "
          f"curv_trace_len={len(eng._curv_trace) if eng._curv_trace else 0}")

    # X_final_ : evolved positions — same length as X_all if no subsampling
    # (max_samples=3000, all our domains except CHB-MIT are < 3000)
    X_fin = eng.X_final_

    # Build normal mask from original y aligned to X_final_
    n_fin = len(X_fin)
    if n_fin == len(X_all):
        y_fin = y_all
    else:
        # Subsampled: y_all is sorted the same way as sim_idx
        # Use score magnitude to approximate (high score = crisis)
        y_fin = (scores[:n_fin] > np.percentile(scores[:n_fin], 70)).astype(int)

    normal_mask = y_fin == 0

    obs = post_sim_observables(X_fin, normal_mask, k=k)
    if obs is None:
        return {}

    # Compute early-warning metrics from each evolved-state signal
    # Map X_final_ observables back to the full N via scores
    # For non-subsampled: X_final_[i] = evolved position of X_all[i]
    unit = meta.get('unit', 'periods')
    results = {}

    for sig_name in ['E_BS', 'MFLS', 'gamma_star', 'rho_MFLS', 'delta_A', 'delta_T']:
        sig = obs[sig_name]
        if n_fin < len(X_all):
            # Can't map back cleanly; use score proxy
            sig_full = scores  # fallback
        else:
            sig_full = sig

        m = early_warning_metrics(sig_full, onset_idx, roll_win=3, thresh_sigma=2.0)
        # normalise key names from early_warning_metrics
        m['fa']   = m.get('fa_rate',    m.get('fa', 0.0))
        m['disc'] = m.get('disc_ratio', m.get('disc', 1.0))
        results[sig_name] = m

    # ── Hessian curvature on full X_final_ (single scalar, not per-particle) ──
    # Uses the same finite-difference Hessian as CanonicalODEEngine._system_curv.
    # bsdt here is obs['bsdt'], fitted on the evolved normal particles.
    hcurv_static = None
    try:
        hcurv_static = compute_hessian_curv(X_fin, obs['bsdt'])
    except Exception as ex:
        print(f"  [Hessian curv static] failed: {ex}")

    # Also compare mean values: pre-onset evolved particles vs crisis evolved particles
    pre_mask  = (y_fin == 0)[:n_fin]
    cris_mask = (y_fin == 1)[:n_fin]

    print(f"\n  {label} — Post-simulation physics observables (CanonicalODEEngine)")
    print(f"  (X_final_ = evolved particle positions after {eng.iterations} ODE steps)")
    unit_str = meta.get('unit', 'periods')
    print(f"  {'Signal':<14} {'Lead':>6} {'Hit':>5} {'FA/100':>8} {'Disc×':>7}  "
          f"| pre-onset mean → crisis mean")
    print("  " + "─" * 75)

    for sig_name in ['E_BS', 'MFLS', 'gamma_star', 'rho_MFLS', 'delta_A', 'delta_T']:
        sig = obs[sig_name]
        r   = results[sig_name]
        lead_str = f"{r['lead']}*" if r['hit'] else f"{r['lead']}"

        pre_mean  = float(sig[pre_mask].mean())  if pre_mask.any()  else 0.0
        cris_mean = float(sig[cris_mask].mean()) if cris_mask.any() else 0.0

        print(f"  {sig_name:<14} {lead_str:>6} "
              f"{'YES' if r['hit'] else 'no':>5} "
              f"{r['fa']:>8.2f} {r['disc']:>7.3f}  "
              f"| {pre_mean:.4f} → {cris_mean:.4f}")

    # ── Report Hessian curvature scalar ──────────────────────────────────────
    if hcurv_static is not None:
        curv_sign = "SADDLE region (λ_max > 1, collapse vicinity)" \
                    if hcurv_static > 0 else "convex region (λ_max ≤ 1, normal)"
        print(f"\n  Hessian curvature (λ_max(∇²Ē_BS)−1) on full X_final_:")
        print(f"    curv_static = {hcurv_static:.6f}  → {curv_sign}")
        if eng._curv_trace:
            ct = eng._curv_trace
            print(f"    Engine _curv_trace (per {eng.curv_update_every} ODE steps): "
                  f"min={min(ct):.4f}  max={max(ct):.4f}  "
                  f"final={ct[-1]:.4f}  n_updates={len(ct)}")
        results['hessian_curv_static'] = float(hcurv_static)

    if hasattr(eng, '_morse_alarm') and eng._morse_alarm:
        ma = eng._morse_alarm
        print(f"\n  Morse alarm (full-domain X_final_):")
        print(f"    Morse index : {ma['morse_index']}  "
              f"({'SADDLE — collapse indicated' if ma['alarm'] else 'no saddle'})")
        print(f"    Hessian trace : {ma['trace']:.4f}  "
              f"({'negative — inward curvature' if ma['trace'] < 0 else 'positive — outward'})")
        print(f"    Eigenvalues  : "
              f"min={float(ma['eigenvalues'].min()):.4f}  "
              f"max={float(ma['eigenvalues'].max()):.4f}")

    return results


# ──────────────────────────────────────────────────────────────────────────────
#  ANALYSIS 2 — SLIDING WINDOW: temporal evolution of post-sim physics signals
# ──────────────────────────────────────────────────────────────────────────────

def sliding_window_analysis(label: str, X_all: np.ndarray, onset_idx: int,
                             meta: dict,
                             ref_len: int = 40,
                             win: int = 20,
                             stride: int = 5,
                             iters: int = 30,
                             k: int = 8) -> dict:
    """
    For each time t, run GravityEngine on X[t-win:t] (recent window).
    The reference for BSDT is X[0:ref_len] (fixed pre-onset reference).
    After simulation, compute mean MFLS/γ*/E_BS on the evolved positions.

    This creates a time series showing how physics observables rise
    as collapse approaches.
    """
    N = len(X_all)
    unit = meta.get('unit', 'periods')

    # z-score on global reference (pre-onset first ref_len samples)
    scaler = StandardScaler()
    scaler.fit(X_all[:ref_len].astype(float))
    X_sc = scaler.transform(X_all.astype(float))

    # Fit reference BSDT on X[0:ref_len] (fixed, pre-crisis baseline)
    k_ref = min(k, ref_len - 2)
    bsdt_ref = BSDTChannels(k=k_ref)
    bsdt_ref.fit(X_sc[:ref_len])
    theta_ref = max(float(np.median(bsdt_ref.energy(X_sc[:ref_len]))), 1e-10)

    times, E_list, M_list, G_list, R_list, C_list = [], [], [], [], [], []

    start = ref_len + win
    for t in range(start, N, stride):
        # Window: recent `win` observations
        X_win = X_sc[t - win: t].copy()
        n_win = len(X_win)
        k_use = min(k, n_win - 2)
        if k_use < 2:
            continue

        # Run FULL CanonicalODEEngine simulation on the window.
        # This uses curvature-adaptive friction (Layers 1 + 2) — not a shortcut.
        # After simulation, we evaluate ALL signals on X_final_ against the
        # FIXED pre-onset reference BSDT (bsdt_ref), not the window's own BSDT.
        try:
            eng = CanonicalODEEngine(
                k_neighbors=k_use,
                iterations=iters,
                normalize=False,
                use_fused=False,
                curv_update_every=5,   # full Hessian every 5 ODE steps
            )
            eng.fit_score(X_win, None)
            X_fin = eng.X_final_  # evolved positions of the window

            # ── Standard signals on evolved positions vs fixed reference BSDT ──
            E  = bsdt_ref.energy(X_fin)
            M  = bsdt_ref.mfls_state(X_fin)
            R  = bsdt_ref.rho_mfls(X_fin)
            Gm = E / (E + theta_ref)

            E_list.append(float(E.mean()))
            M_list.append(float(M.mean()))
            G_list.append(float(Gm.mean()))
            R_list.append(float(R.mean()))

            # ── Hessian curvature (λ_max(∇²Ē_BS)−1) on evolved positions ────
            # Uses the fixed pre-onset bsdt_ref so the curvature reflects
            # how far evolved particles have moved into the saddle region
            # of the NORMAL energy landscape — the true post-simulation
            # curvature temporal signal.
            curv = compute_hessian_curv(X_fin, bsdt_ref)
            C_list.append(float(curv))

            times.append(t)
        except Exception as ex:
            # Skip failed windows
            continue

    if not times:
        return {}

    times  = np.array(times)
    E_arr  = np.array(E_list)
    M_arr  = np.array(M_list)
    G_arr  = np.array(G_list)
    R_arr  = np.array(R_list)
    C_arr  = np.array(C_list)

    # Early-warning lead for each signal
    # Find onset_idx position in times array
    onset_in_times = int(np.searchsorted(times, onset_idx))
    if onset_in_times <= 1 or onset_in_times >= len(times):
        print(f"  [Sliding] onset not well-covered, skipping lead calc")
        return {}

    print(f"\n  {label} — Sliding-window post-simulation physics (CanonicalODEEngine)")
    print(f"  (ref={ref_len}, win={win}, stride={stride}, iters={iters})")
    print(f"  Windows computed: {len(times)}  onset at t-index {onset_in_times}/{len(times)}")
    print(f"\n  {'Signal':<16} {'Lead (t-steps)':>16} {'Lead (periods)':>16} {'Hit':>5} {'FA/100':>8}")
    print("  " + "─" * 66)

    lead_results = {}
    for sig_name, sig in [('E_BS', E_arr), ('MFLS', M_arr),
                           ('gamma_star', G_arr), ('rho_MFLS', R_arr),
                           ('hessian_curv', C_arr)]:
        pre   = sig[:onset_in_times]
        thresh = float(pre.mean() + 2.0 * pre.std())

        lead, hit = 0, False
        for i in range(onset_in_times):
            if sig[i] >= thresh:
                lead = onset_in_times - i
                hit  = True
                break

        bursts, in_burst = 0, False
        for v in pre >= thresh:
            if v and not in_burst:
                bursts += 1; in_burst = True
            elif not v:
                in_burst = False
        fa = 100.0 * bursts / max(onset_in_times, 1)

        lead_periods = int(lead * stride)
        lead_str = f"{lead}*" if hit else f"{lead}"
        lead_p_str = f"{lead_periods}*" if hit else f"{lead_periods}"
        print(f"  {sig_name:<16} {lead_str:>16} {lead_p_str:>16} {'YES' if hit else 'no':>5} {fa:>8.2f}")
        lead_results[sig_name] = dict(lead_steps=int(lead), hit=hit, fa=round(fa, 2),
                                       lead_periods=lead_periods)

    # Show signal means at different epochs
    n_pre    = onset_in_times
    n_window = max(5, n_pre // 4)

    print(f"\n  Signal means at key epochs (post-simulation evolved state):")
    print(f"  {'Signal':<16}  {'Early normal':>14}  {'Pre-onset':>12}  "
          f"{'Post-onset':>12}  Trend")
    print("  " + "─" * 66)
    for sig_name, sig in [('E_BS', E_arr), ('MFLS', M_arr),
                           ('gamma_star', G_arr), ('rho_MFLS', R_arr),
                           ('hessian_curv', C_arr)]:
        early  = float(sig[:n_window].mean())
        pre_w  = float(sig[max(0, onset_in_times - n_window):onset_in_times].mean())
        post_w = float(sig[onset_in_times: onset_in_times + n_window].mean())
        trend  = "↗ RISING" if pre_w > 1.5 * early else ("→ flat" if pre_w > 0.8 * early else "↘")
        print(f"  {sig_name:<16}  {early:>14.4f}  {pre_w:>12.4f}  {post_w:>12.4f}  {trend}")

    # ── Curvature sign counts ─────────────────────────────────────────────────
    n_pos_pre  = int((C_arr[:onset_in_times] > 0).sum())
    n_neg_pre  = onset_in_times - n_pos_pre
    n_pos_post = int((C_arr[onset_in_times:] > 0).sum()) if onset_in_times < len(C_arr) else 0
    print(f"\n  Hessian curvature sign analysis (pre vs post onset):")
    print(f"    Pre-onset  windows: {onset_in_times:3d}  "
          f"→ curv>0 (saddle): {n_pos_pre:3d}  curv≤0 (convex): {n_neg_pre:3d}")
    if onset_in_times < len(C_arr):
        n_post_tot = len(C_arr) - onset_in_times
        print(f"    Post-onset windows: {n_post_tot:3d}  "
              f"→ curv>0 (saddle): {n_pos_post:3d}  "
              f"curv≤0 (convex): {n_post_tot - n_pos_post:3d}")

    return lead_results


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN
# ──────────────────────────────────────────────────────────────────────────────

DOMAIN_PARAMS = {
    # label:               (loader,             static_k, sw_ref, sw_win, sw_stride, sw_iters, sw_k)
    "A: G-SIB Banking":   (load_gsib_banking,  5,        8,      6,      1,         20,        4),
    "B: FDIC US Banks":   (load_fdic_us,        5,        8,      6,      1,         20,        4),
    "C: ERCOT Grid":      (load_ercot_combined, 12,       60,     30,     5,         30,        8),
    "D: Protein Folding": (load_protein,        10,       60,     20,     5,         30,        8),
    "E: CHB-MIT EEG":     (load_chbmit,         12,       300,    120,    60,        20,        8),
}


def main():
    t_total = time.time()
    print("=" * 72)
    print("  POST-SIMULATION PHYSICS SIGNALS — MFLS / γ* / Curvature")
    print("  Engine simulation first → then observables on evolved X_final_")
    print("=" * 72)
    print()
    print("  Thesis: raw data cannot show collapse wanting to happen.")
    print("  Only after the N-body/ODE simulation evolves particles do")
    print("  crisis-regime points reach high-MFLS / high-γ* saddle regions.")
    print()

    all_static  = {}
    all_sliding = {}

    for label, params in DOMAIN_PARAMS.items():
        loader, sk, sw_ref, sw_win, sw_stride, sw_iters, sw_k = params

        print(f"\n{'━'*72}")
        print(f"  DOMAIN: {label}")
        print(f"{'━'*72}")

        t0 = time.time()
        X, y, onset_idx, dmeta = loader()
        if X is None:
            print(f"  SKIPPED — {dmeta.get('status','?')}")
            continue
        print(f"  Loaded {X.shape}  onset@{onset_idx}  unit={dmeta.get('unit','?')}  "
              f"({time.time()-t0:.1f}s)")

        # Analysis 1: static full-domain
        sr = static_analysis(label, X, y, onset_idx, dmeta, k=sk)
        all_static[label] = sr

        # Analysis 2: sliding window
        # Skip if too few pre-onset points for meaningful window
        if onset_idx >= sw_ref + sw_win + 2:
            swr = sliding_window_analysis(
                label, X, onset_idx, dmeta,
                ref_len=sw_ref, win=sw_win, stride=sw_stride,
                iters=sw_iters, k=sw_k)
            all_sliding[label] = swr
        else:
            print(f"  [Sliding] Skipped — onset ({onset_idx}) too close to start")

    # ── Cross-domain summary ──────────────────────────────────────────
    print(f"\n{'█'*72}")
    print("  SUMMARY — Post-Simulation Lead Times (sliding window)")
    print(f"{'█'*72}\n")
    print(f"  {'Domain':<22} {'E_BS':>8} {'MFLS':>8} {'γ*':>8} {'ρ_MFLS':>8} {'H-curv':>8}")
    print("  " + "─" * 70)
    for label, res in all_sliding.items():
        if not res:
            print(f"  {label:<22} {'—':>8}")
            continue
        stride = DOMAIN_PARAMS[label][4]
        row = f"  {label:<22}"
        for sig in ['E_BS', 'MFLS', 'gamma_star', 'rho_MFLS', 'hessian_curv']:
            r = res.get(sig, {})
            if r and r.get('hit'):
                lead_p = r['lead_periods']
                row += f" {str(lead_p)+'*':>8}"
            elif r:
                row += f" {'0':>8}"
            else:
                row += f" {'—':>8}"
        print(row)
    print(f"  (* = lead periods before onset, 0 = signal did not cross threshold)")

    print(f"\n  Key physics sequence confirmed when engine runs first:")
    print(f"  MFLS rises → γ* rises (system resisting) → ρ_MFLS > 1 (amplifying)")
    print(f"  This is the collapse trajectory in particle space.")

    out = os.path.join(ROOT, "post_sim_physics_results.json")
    def _j(o):
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        if isinstance(o, np.ndarray): return o.tolist()
        return str(o)

    with open(out, "w") as f:
        json.dump({"static": all_static, "sliding": all_sliding,
                   "elapsed_s": round(time.time()-t_total, 1)}, f, indent=2, default=_j)
    print(f"\n  Results → {out}")
    print(f"  Total: {time.time()-t_total:.0f}s")


if __name__ == "__main__":
    main()
