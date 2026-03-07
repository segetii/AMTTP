#!/usr/bin/env python3
"""
Terra/Luna — Historically Calibrated DPD Simulation
=====================================================
Recalibrates the force model in run_terra_luna_sim.py to match the actual
120-hour collapse timeline from May 7-13, 2022.

Changes from the original:
  1. Attack onset delayed to hour 22 (matching Nansen timeline)
  2. LFG BTC defence modelled as extra peg restoration (hours 22-48)
  3. Force magnitudes reduced ~15x to match real timescale
  4. Anchor withdrawal modelled as gradual loss of restoration
  5. Chain halt modelled as force freeze at hour 120

This script re-runs Scenario A (γ=0) with the recalibrated parameters
and compares against real UST depeg data.
"""
from __future__ import annotations
import sys, time
import numpy as np
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPELINE_DIR))

from gravity_engine import (
    BSDTOperator, pairwise_force, radial_force, radial_energy,
    pairwise_energy, total_energy, total_force,
    spectral_radius, ALPHA,
)

# ═══════════════════════════════════════════════════════════════════════════════
# RECALIBRATED PARAMETERS (historically anchored)
# ═══════════════════════════════════════════════════════════════════════════════

# --- Agents (same as original) ---
N_UST, N_ANCHOR, N_STAKER, N_ARB, N_WHALE = 30, 15, 10, 8, 2
N_TOTAL = N_UST + N_ANCHOR + N_STAKER + N_ARB + N_WHALE
D = 5

# --- Timeline ---
N_HOURS = 168
DT = 0.02
STEPS_PER_HOUR = 50
N_STEPS = N_HOURS * STEPS_PER_HOUR

# --- Forces (RECALIBRATED for 120h collapse) ---
# Original values produced collapse in ~7h. These are tuned to match reality.
ALPHA_PEG   = 0.08     # was 0.8  → 10x weaker base restoration
BETA_SPIRAL = 0.065    # was 1.2  → ~18x weaker spiral
GAMMA_PAIR  = 0.02     # was 0.2  → weaker herding
SIGMA_PAIR  = 2.0      # same
ANCHOR_APY  = 0.04     # was 0.3  → gentler attraction

# --- Attack (delayed to hour 22, matching Nansen) ---
ATK_START   = 22       # NEW: attack begins at hour 22 (May 7, 21:44 UTC)
ATK_MAG     = 0.12     # was 0.8  → weaker impulse, sustained  
ATK_SUSTAIN = 0.04     # was 0.2
ATK_HOURS   = 8        # sustained for 8 hours (through May 8 morning)

# --- LFG Defence (NEW: temporary peg support) ---
LFG_START   = 22       # LFG activates when depeg detected
LFG_END     = 48       # LFG exhausts BTC reserves by May 9
LFG_STRENGTH = 0.15    # Extra peg restoration from $2.4B BTC deployment

# --- Chain halt (NEW) ---
CHAIN_HALT_HOUR = 120  # May 12: chain halted

# --- Clamps (relaxed for slower dynamics) ---
V_MAX = 0.8
X_MAX = 10.0
F_MAX_TOTAL = 0.5     # was 3.0 → much tighter force cap

# --- Critical friction (same physics) ---
GAMMA_CRITICAL = 0.6

# ═══════════════════════════════════════════════════════════════════════════════
# State builder (same as original)
# ═══════════════════════════════════════════════════════════════════════════════

def build_state(rng):
    X = np.zeros((N_TOTAL, D))
    M = np.zeros(N_TOTAL)
    labels = []
    i = 0
    for _ in range(N_UST):
        X[i] = [rng.normal(0, 0.003), rng.normal(0, 0.05),
                rng.exponential(1.0), rng.normal(0, 0.01), rng.normal(0, 0.02)]
        M[i] = 1.0 * (0.5 + rng.random())
        labels.append("UST"); i += 1
    for _ in range(N_ANCHOR):
        X[i] = [rng.normal(0, 0.001), rng.normal(0, 0.03),
                rng.exponential(2.0), rng.normal(0, 0.005), rng.normal(-0.05, 0.02)]
        M[i] = 2.0 * (0.8 + 0.4 * rng.random())
        labels.append("Anchor"); i += 1
    for _ in range(N_STAKER):
        X[i] = [rng.normal(0, 0.003), rng.normal(0, 0.05),
                rng.exponential(1.5), rng.normal(0, 0.01), rng.normal(-0.1, 0.03)]
        M[i] = 1.5 * (0.7 + 0.5 * rng.random())
        labels.append("Staker"); i += 1
    for _ in range(N_ARB):
        X[i] = [rng.normal(0, 0.005), rng.normal(0, 0.1),
                rng.exponential(0.5), rng.normal(0, 0.05), rng.normal(0, 0.05)]
        M[i] = 0.8 * (0.5 + 0.5 * rng.random())
        labels.append("Arb"); i += 1
    for _ in range(N_WHALE):
        X[i] = [rng.normal(0, 0.001), rng.normal(0, 0.02),
                3.0 + rng.exponential(1.0), rng.normal(0, 0.01), rng.normal(0.05, 0.02)]
        M[i] = 5.0
        labels.append("Whale"); i += 1
    return X, M, labels


# ═══════════════════════════════════════════════════════════════════════════════
# RECALIBRATED Force Model
# ═══════════════════════════════════════════════════════════════════════════════

def compute_forces(X, V, M, depeg, hour, labels, gamma_fric):
    """
    Same physics as original, with:
    1. Delayed attack (hour 22, not 0)
    2. LFG defence (hours 22-48, decaying)
    3. Recalibrated magnitudes for 120h collapse
    4. Chain halt at hour 120
    """
    N, d_feat = X.shape
    mu_peg = np.zeros(d_feat)

    # ── Chain halt: freeze all forces ────────────────────────────────────────
    if hour >= CHAIN_HALT_HOUR:
        # After halt, only slow diffusion (no active trading)
        return -0.01 * V  # tiny damping, near-frozen state

    # ── Peg restoration (via gravity engine radial_force) ─────────────────────
    # Uses the engine's radial_force(X, mu, alpha) = alpha * (mu - X)
    # with stress-dependent coupling: alpha weakens as depeg increases
    alpha_eff = ALPHA_PEG * max(0, (1 - depeg)) ** 2
    F_restore = radial_force(X, mu_peg, alpha=alpha_eff)

    # ── LFG defence (temporary extra peg support) ────────────────────────────
    F_lfg = np.zeros_like(X)
    if LFG_START <= hour < LFG_END:
        # LFG deploys BTC reserves, strength decays as reserves deplete
        lfg_frac = 1.0 - (hour - LFG_START) / (LFG_END - LFG_START)
        lfg_boost = LFG_STRENGTH * lfg_frac * max(0, 1 - depeg)
        F_lfg[:, 0] = -lfg_boost * X[:, 0]  # push depeg back toward 0
        F_lfg[:, 4] = -lfg_boost * 0.3 * X[:, 4]  # reduce fear

    # ── Death spiral (weakened by friction) ──────────────────────────────────
    # The spiral accelerates with depeg but saturates at high depeg levels
    # because remaining holders are illiquid or trapped. This creates
    # the real-world phenomenon of a slow grinding collapse after the
    # initial rapid phase (hour 48-60 → fast, hour 60-120 → grinding).
    feedback_suppression = max(0, 1 - gamma_fric / GAMMA_CRITICAL)
    F_spiral = np.zeros_like(X)
    if depeg > 0.005 and feedback_suppression > 0:
        # Two-phase spiral:
        # Phase 1 (depeg < 0.5): accelerating — tanh(2d) rises
        # Phase 2 (depeg > 0.5): saturating — remaining HODLers illiquid
        if depeg < 0.5:
            spiral_mag = BETA_SPIRAL * np.tanh(depeg * 2) * feedback_suppression
        else:
            # Saturating: remaining holders are illiquid (Anchor lockup,
            # exchange halts, trapped in staking). The spiral continues but
            # the effective selling rate drops dramatically.
            # This produces the real-world "grinding collapse" from 50% → 99%
            # that took ~70 hours (vs the rapid 5%→50% that took ~12h).
            base = BETA_SPIRAL * np.tanh(1.0)  # value at depeg=0.5
            decay = np.exp(-(depeg - 0.5) * 4.0)  # strong decay factor
            spiral_mag = base * decay * feedback_suppression
        F_spiral[:, 0] = spiral_mag
        F_spiral[:, 1] = spiral_mag * 0.5
        F_spiral[:, 4] = spiral_mag * 0.3

    # ── Inter-agent herding (gravity engine pairwise_force) ────────────────────
    # Uses the engine's erf-attraction / log-repulsion potential ∇Φ_pair
    F_herd = pairwise_force(X, gamma=GAMMA_PAIR, sigma=SIGMA_PAIR, lam=0.02)

    # ── Anchor yield ─────────────────────────────────────────────────────────
    F_anchor = np.zeros_like(X)
    # Anchor withdrawals accelerate after hour 36 (Nansen data)
    anchor_strength = ANCHOR_APY * max(0, 1 - 4 * depeg)
    if hour > 36:
        # Anchor TVL draining: $14B → $2B over 36h
        drain = min(1.0, (hour - 36) / 36)
        anchor_strength *= (1 - drain * 0.9)
    for i, lab in enumerate(labels):
        if lab == "Anchor":
            F_anchor[i] = -anchor_strength * X[i]

    # ── Attack impulse (delayed onset) ───────────────────────────────────────
    F_attack = np.zeros_like(X)
    for i, lab in enumerate(labels):
        if lab == "Whale":
            if ATK_START <= hour < ATK_START + ATK_HOURS:
                # Phase 1: main attack ($285M on Curve)
                t_atk = hour - ATK_START
                mag = ATK_MAG * np.exp(-t_atk / 3)
                F_attack[i, 0] = mag
                F_attack[i, 4] = mag * 0.3
            elif ATK_START + ATK_HOURS <= hour < ATK_START + 24:
                # Phase 2: sustained selling on CEXes
                t_sust = hour - ATK_START - ATK_HOURS
                mag = ATK_SUSTAIN * np.exp(-t_sust / 8)
                F_attack[i, 0] = mag

    # ── Agent panic (also suppressed by friction = cooldown periods) ─────────
    F_panic = np.zeros_like(X)
    if depeg > 0.01:
        panic_suppression = max(0, 1 - gamma_fric / (GAMMA_CRITICAL * 2))
        dp = np.tanh(depeg * 3) * panic_suppression
        
        # Panic also saturates at high depeg (trapped holders can't sell)
        if depeg > 0.5:
            dp *= np.exp(-(depeg - 0.5) * 1.0)
        
        for i, lab in enumerate(labels):
            if lab == "UST":
                F_panic[i, 0] = 0.01 * dp
                F_panic[i, 4] = 0.012 * dp
            elif lab == "Arb":
                F_panic[i, 0] = -0.003 * dp
            elif lab == "Staker" and depeg > 0.1:
                cap = np.tanh((depeg - 0.1) * 4)
                F_panic[i, 0] = 0.008 * cap * panic_suppression
                F_panic[i, 4] = 0.010 * cap * panic_suppression

    # ── Temporary bounces (exchange-driven, market-maker interventions) ──────
    # Real data shows brief bounces at hours 30, 64, 96, 100
    F_bounce = np.zeros_like(X)
    bounce_hours = [(30, 0.04), (64, 0.02), (96, 0.015), (100, 0.01)]
    for bh, bstr in bounce_hours:
        if abs(hour - bh) < 2:
            proximity = 1 - abs(hour - bh) / 2
            F_bounce[:, 0] = -bstr * proximity * X[:, 0]  # push depeg back

    # ── Fear contagion ───────────────────────────────────────────────────────
    F_fear = np.zeros_like(X)
    mean_fear = np.mean(X[:, 4])
    F_fear[:, 4] = 0.008 * (mean_fear - X[:, 4])  # was 0.05

    # ── Friction ─────────────────────────────────────────────────────────────
    # Natural market friction: always present, increases with stress.
    # Models bid-ask widening, exchange halts (Binance hour 60), DEX
    # liquidity drain (Curve pools emptied), withdrawal queues (Anchor
    # 7-day, LUNA 21-day unbonding).  This is NOT the AMTTP adaptive
    # friction — it's a market-microstructure effect that slows ALL
    # trading as the system seizes up.
    gamma_natural = 0.0
    if depeg > 0.3:
        gamma_natural = 15.0 * (depeg - 0.3) ** 2
    F_fric = -(gamma_fric + gamma_natural) * V

    # ── Total + clamp ────────────────────────────────────────────────────────
    F = F_restore + F_lfg + F_spiral + F_herd + F_anchor + F_attack + F_panic + F_bounce + F_fear + F_fric
    
    norms = np.linalg.norm(F, axis=1, keepdims=True)
    scale = np.where(norms > F_MAX_TOTAL, F_MAX_TOTAL / (norms + 1e-12), 1.0)
    return F * scale


# ═══════════════════════════════════════════════════════════════════════════════
# Run Scenario A
# ═══════════════════════════════════════════════════════════════════════════════

SCENARIOS = {
    "A_historical": {
        "name": "Historical (γ=0, calibrated)",
        "gamma": 0.0,
        "adaptive": False,
        "breaker": False,
        "desc": "Recalibrated to match actual May 2022 timeline",
    },
    "D_adaptive": {
        "name": "Adaptive γ*(t)",
        "gamma": None,
        "adaptive": True,
        "breaker": False,
        "desc": "AMTTP adaptive friction = α/λ_max(t)",
    },
}


def run_scenario(scen, seed=42):
    rng = np.random.default_rng(seed)
    X, M, labels = build_state(rng)
    V = np.zeros_like(X)

    X_ref = np.stack([X + rng.normal(0, 0.01, X.shape) for _ in range(20)])
    bsdt = BSDTOperator().fit(X_ref)

    rec_every = STEPS_PER_HOUR
    n_rec = N_STEPS // rec_every + 1

    out = {k: np.zeros(n_rec) for k in
           ["hours", "depeg", "luna_price", "energy", "mfls",
            "gamma", "lambda_max", "fear", "velocity",
            "lyapunov", "cos_theta", "above_cman",
            "energy_rad", "energy_pair"]}
    ri = 0
    _lam_cache = 1e-3
    gamma_t = scen["gamma"] if scen["gamma"] is not None else 0.0

    for step in range(N_STEPS):
        hour = step / STEPS_PER_HOUR
        depeg = max(float(np.mean(X[:, 0])), 0.0)

        if scen["adaptive"] and step % (STEPS_PER_HOUR * 2) == 0:
            # Gravity engine: γ*(t) = α / λ_max(D²Φ_pair(X))
            lam, _ = spectral_radius(X, K=10, rng=rng)
            gamma_t = np.clip(ALPHA / (lam + 1e-6), 0.05, 3.0)

        if scen.get("breaker") and depeg > 0.02:
            gamma_t = 2.0

        F = compute_forces(X, V, M, depeg, hour, labels, gamma_t)

        A = F / M[:, None]
        V = V + A * DT
        v_norms = np.linalg.norm(V, axis=1, keepdims=True)
        V = V * np.where(v_norms > V_MAX, V_MAX / (v_norms + 1e-12), 1.0)
        X = X + V * DT + rng.normal(0, 0.002, X.shape) * DT
        X = np.clip(X, -X_MAX, X_MAX)
        # Physical constraint: depeg can't exceed ~100% (price can't go below $0)
        X[:, 0] = np.clip(X[:, 0], -0.1, 1.05)

        if np.any(np.isnan(X)):
            break

        if step % rec_every == 0 and ri < n_rec:
            # ── Gravity engine observables ────────────────────────────
            mu_peg = np.zeros(D)   # equilibrium = peg = origin
            mu_now = X.mean(axis=0)

            # Energy: engine's Φ(X) = Φ_rad + Φ_pair
            PE_rad  = radial_energy(X, mu_peg, alpha=ALPHA_PEG)
            PE_pair = pairwise_energy(X, gamma=GAMMA_PAIR, sigma=SIGMA_PAIR, lam=0.02)
            PE = PE_rad + PE_pair
            KE = 0.5 * np.sum(M[:, None] * V**2)

            # BSDT blind-spot gradient → MFLS detection score
            G_bs = bsdt.gradient(X)
            mfls_val = float(np.linalg.norm(G_bs))

            # Gradient alignment: cos θ = ⟨∇E_BS, F_grav⟩ / (‖∇E_BS‖·‖F_grav‖)
            # Uses engine's total_force (radial + pairwise)
            F_grav = total_force(X, mu_now, alpha=ALPHA_PEG)
            dot_per  = np.sum(G_bs * F_grav, axis=1)
            norm_g   = np.linalg.norm(G_bs, axis=1)
            norm_f   = np.linalg.norm(F_grav, axis=1)
            cos_per  = dot_per / (norm_g * norm_f + 1e-12)
            cos_val  = float(np.mean(cos_per))

            # Spectral radius λ_max(D²Φ_pair) — every 10 recordings
            if ri % 10 == 0:
                lam_v, _ = spectral_radius(X, K=10, rng=rng)
                _lam_cache = lam_v
            else:
                lam_v = _lam_cache if ri > 0 else 1e-3

            out["hours"][ri] = hour
            out["depeg"][ri] = depeg
            out["luna_price"][ri] = float(np.mean(np.exp(np.clip(-X[:, 1], -5, 5))))
            out["energy"][ri] = float(PE)
            out["mfls"][ri] = mfls_val
            out["gamma"][ri] = gamma_t
            out["fear"][ri] = float(np.mean(X[:, 4]))
            out["velocity"][ri] = float(np.mean(np.linalg.norm(V, axis=1)))
            out["lyapunov"][ri] = float(PE + KE)
            out["cos_theta"][ri] = cos_val
            out["lambda_max"][ri] = lam_v
            out["above_cman"][ri] = float(lam_v > ALPHA)
            out["energy_rad"][ri] = float(PE_rad)
            out["energy_pair"][ri] = float(PE_pair)

            ri += 1

    n = ri
    return {
        "name": scen["name"],
        **{k: v[:n] for k, v in out.items()},
        "final_depeg": out["depeg"][n-1],
        "max_depeg": float(np.max(out["depeg"][:n])),
        "collapsed": bool(out["depeg"][n-1] > 0.5),
        "n_rec": n,
        # Gravity engine summary
        "mean_cos_theta": float(np.mean(out["cos_theta"][:n])),
        "max_lambda": float(np.max(out["lambda_max"][:n])),
        "above_cman_frac": float(np.mean(out["above_cman"][:n])),
        "peak_mfls": float(np.max(out["mfls"][:n])),
        "peak_energy": float(np.max(out["energy"][:n])),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Validation against real data
# ═══════════════════════════════════════════════════════════════════════════════

# Real UST price data (from validate_terra_luna.py)
UST_PRICE_HOURLY = {
    0: 1.000, 6: 0.999, 12: 0.998, 18: 0.997, 21: 0.995,
    22: 0.990, 23: 0.985,
    24: 0.980, 27: 0.975, 30: 0.985, 33: 0.990, 36: 0.975,
    40: 0.950, 44: 0.920, 47: 0.900,
    48: 0.800, 50: 0.700, 52: 0.600, 54: 0.500, 56: 0.400,
    60: 0.350, 64: 0.400, 68: 0.350, 71: 0.300,
    72: 0.280, 76: 0.250, 80: 0.220, 84: 0.200, 88: 0.180,
    92: 0.150, 95: 0.120,
    96: 0.150, 100: 0.180, 104: 0.120, 108: 0.100, 112: 0.080,
    116: 0.060, 119: 0.050,
    120: 0.060, 124: 0.050, 128: 0.040, 132: 0.030, 136: 0.025,
    140: 0.020, 143: 0.020,
    144: 0.020, 148: 0.020, 152: 0.015, 156: 0.015, 160: 0.010,
    164: 0.010, 168: 0.010,
}


def interpolate_hourly(data_dict, n_hours=168):
    hours = sorted(data_dict.keys())
    values = [data_dict[h] for h in hours]
    return np.interp(np.arange(n_hours + 1), hours, values)


def main():
    print("=" * 80)
    print("  TERRA/LUNA — HISTORICALLY CALIBRATED DPD SIMULATION")
    print("  Matching real May 2022 collapse timeline")
    print("=" * 80)

    # 1. Compute real depeg
    ust_prices = interpolate_hourly(UST_PRICE_HOURLY)
    real_depeg = (1.0 - ust_prices) * 100.0

    # 2. Run historically calibrated Scenario A
    print(f"\n  Running Scenario A (γ=0, calibrated)...")
    t0 = time.time()
    res_A = run_scenario(SCENARIOS["A_historical"])
    print(f"  Done in {time.time()-t0:.1f}s")

    # 3. Also run adaptive for comparison
    print(f"  Running Scenario D (adaptive γ*)...")
    t0 = time.time()
    res_D = run_scenario(SCENARIOS["D_adaptive"])
    print(f"  Done in {time.time()-t0:.1f}s")

    # 4. Interpolate sim to integer hours
    sim_hours = res_A["hours"]
    sim_depeg_raw = res_A["depeg"] * 100.0
    int_hours = np.arange(169)
    sim_depeg = np.interp(int_hours, sim_hours, sim_depeg_raw)
    sim_depeg_capped = np.minimum(sim_depeg, 100.0)

    adapt_depeg_raw = res_D["depeg"] * 100.0
    adapt_depeg = np.interp(int_hours, res_D["hours"], adapt_depeg_raw)
    adapt_depeg_capped = np.minimum(adapt_depeg, 100.0)

    # 5. Comparison table
    print(f"\n{'='*90}")
    print(f"  HOURLY COMPARISON: Real vs Simulation (γ=0) vs Adaptive (γ*)")
    print(f"{'='*90}")
    print(f"{'Hour':>5} {'Event':<30} {'Real%':>8} {'Sim%':>8} {'Err':>8} {'Adapt%':>8}")
    print("-" * 90)

    milestones = [
        (0,  "Start (May 7 00:00)"),
        (6,  "Pre-attack"),
        (22, "LFG withdrawal"),
        (24, "First attack"),
        (30, "LFG BTC defence"),
        (36, "Anchor withdrawals"),
        (42, "Defence weakening"),
        (48, "Spiral engages"),
        (54, "Rapid collapse"),
        (60, "UST ~$0.35"),
        (72, "May 10"),
        (84, "LUNA hyperinflation"),
        (96, "May 11"),
        (108, "LUNA → $0.10"),
        (120, "Chain halt (May 12)"),
        (144, "Post-halt (May 13)"),
        (168, "End (May 14)"),
    ]

    errors = []
    for h, event in milestones:
        rd = real_depeg[h]
        sd = sim_depeg_capped[h]
        ad = adapt_depeg_capped[h]
        err = abs(rd - sd)
        errors.append(err)
        print(f"{h:>5} {event:<30} {rd:>7.1f}% {sd:>7.1f}% {err:>7.1f}% {ad:>7.1f}%")

    # 6. Summary stats
    abs_err = np.abs(real_depeg - sim_depeg_capped)
    corr = np.corrcoef(real_depeg, sim_depeg_capped)[0, 1]
    mae = np.mean(abs_err)

    print(f"\n{'='*90}")
    print(f"  SUMMARY STATISTICS")
    print(f"{'='*90}")
    print(f"  Pearson Correlation:  r = {corr:.4f}")
    print(f"  Mean Absolute Error:  MAE = {mae:.2f}%")
    print(f"  Max Absolute Error:   {np.max(abs_err):.2f}%")

    # Time to milestones
    real_t5 = next((i for i, d in enumerate(real_depeg) if d >= 5.0), None)
    sim_t5 = next((i for i, d in enumerate(sim_depeg_capped) if d >= 5.0), None)
    real_t50 = next((i for i, d in enumerate(real_depeg) if d >= 50.0), None)
    sim_t50 = next((i for i, d in enumerate(sim_depeg_capped) if d >= 50.0), None)
    real_t90 = next((i for i, d in enumerate(real_depeg) if d >= 90.0), None)
    sim_t90 = next((i for i, d in enumerate(sim_depeg_capped) if d >= 90.0), None)

    print(f"\n  Time to 5% depeg:   Real = {real_t5}h   Sim = {sim_t5}h   Δ = {abs(real_t5 - sim_t5) if real_t5 and sim_t5 else '?'}h")
    print(f"  Time to 50% depeg:  Real = {real_t50}h  Sim = {sim_t50}h  Δ = {abs(real_t50 - sim_t50) if real_t50 and sim_t50 else '?'}h")
    print(f"  Time to 90% depeg:  Real = {real_t90}h  Sim = {sim_t90}h  Δ = {abs(real_t90 - sim_t90) if real_t90 and sim_t90 else '?'}h")

    # Adaptive comparison
    print(f"\n  Terminal state:")
    print(f"    Real:      {real_depeg[-1]:.1f}% depeg")
    print(f"    Sim (γ=0): {sim_depeg_capped[-1]:.1f}% depeg  →  {'COLLAPSED' if res_A['collapsed'] else 'STABLE'}")
    print(f"    Adaptive:  {adapt_depeg_capped[-1]:.1f}% depeg  →  {'COLLAPSED' if res_D['collapsed'] else 'STABLE'}")

    if corr > 0.95:
        qual = "EXCELLENT"
    elif corr > 0.90:
        qual = "VERY GOOD"
    elif corr > 0.80:
        qual = "GOOD"
    elif corr > 0.70:
        qual = "MODERATE"
    else:
        qual = "POOR"

    print(f"\n  Qualitative Assessment: {qual} (r = {corr:.4f})")

    # ── Gravity Engine diagnostics ─────────────────────────────────────────
    print(f"\n{'='*90}")
    print(f"  GRAVITY ENGINE DIAGNOSTICS")
    print(f"{'='*90}")
    print(f"  {'Metric':<32} {'Scenario A (γ=0)':>18} {'Adaptive (γ*)':>16}")
    print(f"  {'-'*66}")
    print(f"  {'Peak Φ(X) energy':<32} {res_A['peak_energy']:>18.3f} {res_D['peak_energy']:>16.3f}")
    print(f"  {'Peak MFLS ‖∇E_BS‖':<32} {res_A['peak_mfls']:>18.3f} {res_D['peak_mfls']:>16.3f}")
    print(f"  {'Max λ_max(D²Φ_pair)':<32} {res_A['max_lambda']:>18.3f} {res_D['max_lambda']:>16.3f}")
    print(f"  {'Mean cos θ alignment':<32} {res_A['mean_cos_theta']:>18.4f} {res_D['mean_cos_theta']:>16.4f}")
    print(f"  {'Above critical manifold':<32} {res_A['above_cman_frac']*100:>17.1f}% {res_D['above_cman_frac']*100:>15.1f}%")
    print(f"\n  Interpretation:")
    print(f"    λ_max > α = {ALPHA:.2f} means system is above the critical manifold")
    print(f"    cos θ > 0.7 means gravity force aligns with blind-spot gradient")
    print(f"    High MFLS = large deviation from equilibrium (crisis detected)")

    # 7. ASCII comparison chart
    print(f"\n{'='*80}")
    print(f"  UST Depeg (%): ● Real   ░ Simulated   ▓ Adaptive")
    print(f"{'='*80}")
    chart_width = 72
    chart_height = 20
    for row in range(chart_height, -1, -1):
        thresh = (row / chart_height) * 100.0
        label = f"{thresh:>5.0f}%│"
        chars = []
        for h_idx in range(0, 169, max(1, 169 // chart_width)):
            rd = real_depeg[min(h_idx, 168)]
            sd = sim_depeg_capped[min(h_idx, 168)]
            r_above = rd >= thresh
            s_above = sd >= thresh
            if r_above and s_above:
                chars.append("█")
            elif r_above:
                chars.append("●")
            elif s_above:
                chars.append("░")
            else:
                chars.append(" ")
        print(f"  {label}{''.join(chars[:chart_width])}")
    print(f"  {'':>6}└{'─'*chart_width}")
    print(f"  {'':>7}0h{'':>{chart_width//4-2}}48h{'':>{chart_width//4-3}}96h{'':>{chart_width//4-3}}144h{'':>{chart_width//4-4}}168h")
    print(f"\n  Legend: █ = Both overlap  ● = Real only  ░ = Sim only")

    # 8. Save
    import json
    output = {
        "calibration": "historical_may_2022",
        "correlation": float(corr),
        "mae_pct": float(mae),
        "real_depeg_pct": real_depeg.tolist(),
        "sim_depeg_pct": sim_depeg_capped.tolist(),
        "adapt_depeg_pct": adapt_depeg_capped.tolist(),
        "sim_collapsed": res_A["collapsed"],
        "adapt_collapsed": res_D["collapsed"],
        "time_to_5pct": {"real": real_t5, "sim": sim_t5},
        "time_to_50pct": {"real": real_t50, "sim": sim_t50},
        "time_to_90pct": {"real": real_t90, "sim": sim_t90},
        "parameters": {
            "ALPHA_PEG": ALPHA_PEG, "BETA_SPIRAL": BETA_SPIRAL,
            "GAMMA_PAIR": GAMMA_PAIR, "ATK_MAG": ATK_MAG,
            "ATK_START": ATK_START, "LFG_STRENGTH": LFG_STRENGTH,
            "V_MAX": V_MAX, "F_MAX_TOTAL": F_MAX_TOTAL,
        },
        "gravity_engine": {
            "scenario_A": {
                "peak_energy": res_A["peak_energy"],
                "peak_mfls": res_A["peak_mfls"],
                "max_lambda": res_A["max_lambda"],
                "mean_cos_theta": res_A["mean_cos_theta"],
                "above_cman_frac": res_A["above_cman_frac"],
            },
            "scenario_D": {
                "peak_energy": res_D["peak_energy"],
                "peak_mfls": res_D["peak_mfls"],
                "max_lambda": res_D["max_lambda"],
                "mean_cos_theta": res_D["mean_cos_theta"],
                "above_cman_frac": res_D["above_cman_frac"],
            },
            "engine_components": [
                "radial_force (peg restoration)",
                "pairwise_force (inter-agent herding)",
                "spectral_radius (adaptive γ*)",
                "BSDTOperator (MFLS + cos θ alignment)",
                "radial_energy + pairwise_energy (Φ tracking)",
                "total_force (cos θ computation)",
            ],
        },
    }
    out_path = Path(__file__).resolve().parent / "terra_luna_calibrated.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results saved: {out_path}")

    print(f"\n{'='*80}")
    print(f"  CALIBRATED VALIDATION COMPLETE")
    print(f"{'='*80}\n")
    return output


if __name__ == "__main__":
    main()
