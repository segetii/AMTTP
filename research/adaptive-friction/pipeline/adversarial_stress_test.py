"""
adversarial_stress_test.py
===========================
Systematic adversarial attack on the Molecular engine (MFLS / cos θ / spectral radius).

We throw 12 attacks at increasing severity and find the EXACT breaking point of each.

Attack categories:
  1. NOISE:          Gaussian noise injection (σ = 0.01 → 100.0)
  2. DROPOUT:        Random feature dropout (1% → 95%)
  3. BANK_DROP:      Random bank removal (1 → N-2)
  4. COORDINATED:    All banks shifted identically (hiding divergence)
  5. OUTLIER:        Single extreme bank injected
  6. DIM_COLLAPSE:   Feature dimensions zeroed out (d=5 → d=1)
  7. TEMPORAL_SHUF:  Shuffle time ordering  
  8. ADVERSARIAL_GD: Gradient-based adversarial perturbation (minimise MFLS)
  9. SCALE_ATTACK:   Rescale features to extreme ranges
  10. COVARIANCE_POISON: Corrupt the BSDT reference covariance
  11. CLONE_BANKS:   Duplicate banks to dilute real signal
  12. MEAN_SHIFT:    Slowly drift equilibrium away from true normal

For each attack, we measure:
  - MFLS score (crisis vs normal)
  - Separation ratio (MFLS_crisis / MFLS_normal) — detection power
  - cos θ alignment  
  - Spectral radius λ_max
  - Whether crisis dates are still correctly ranked

A detection is "broken" when separation ratio < 1.5 (crisis indistinguishable from normal).

All on real World Bank + FDIC data. Zero heuristics.
"""
from __future__ import annotations
import sys, time
import numpy as np
import pandas as pd
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

THIS_DIR = Path(__file__).parent
BL_DIR   = THIS_DIR.parent / "banklevel_enhanced"
for p in [str(THIS_DIR), str(BL_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from gsib_loader_real import build_gsib_panel_real, FEATURE_NAMES
import gravity_engine as engine
from gravity_engine import BSDTOperator, total_energy, total_force, spectral_radius

NORMAL_START = "2005-03-31"
NORMAL_END   = "2006-12-31"

# Crisis quarters (indices) and calm quarters for separation ratio
CRISIS_NAMES = ["GFC 2008", "Nigeria 2009", "EurDebt 2011",
                "Nigeria 2016", "COVID 2020", "RateShock 2022"]
CRISIS_DATES = ["2008-09-30", "2009-09-30", "2011-09-30",
                "2016-06-30", "2020-03-31", "2022-09-30"]

SEP_THRESHOLD = 1.5   # separation ratio below this → detection broken


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_panel():
    panel = build_gsib_panel_real(
        quarters_start="2005-01-01", quarters_end="2023-12-31",
        force_refresh=False, min_coverage=0.50, verbose=False)
    X_raw = panel["X"]
    dates = panel["dates"]
    meta  = panel["meta"]
    T, N, d = X_raw.shape

    norm_mask = (dates >= pd.Timestamp(NORMAL_START)) & \
                (dates <= pd.Timestamp(NORMAL_END))
    if norm_mask.sum() < 4:
        norm_mask[:8] = True
    X_ref = X_raw[norm_mask]
    mu_ref = X_ref.reshape(-1, d).mean(axis=0)
    sd_ref = X_ref.reshape(-1, d).std(axis=0) + 1e-9
    X_std  = (X_raw - mu_ref) / sd_ref
    mu_eq  = X_std[norm_mask].reshape(-1, d).mean(axis=0)

    # crisis indices
    crisis_idx = []
    for cd in CRISIS_DATES:
        ts = pd.Timestamp(cd)
        idx = int(np.argmin(np.abs(dates - ts)))
        crisis_idx.append(idx)

    # calm indices (normal period)
    calm_idx = list(np.where(norm_mask)[0])

    return X_std, mu_eq, dates, meta, norm_mask, crisis_idx, calm_idx


def evaluate(X_series, mu_eq, bsdt, crisis_idx, calm_idx):
    """Compute detection metrics on (possibly attacked) data."""
    T, N, d = X_series.shape

    # MFLS at crisis vs calm
    mfls_crisis = [bsdt.mfls_score(X_series[i]) for i in crisis_idx if i < T]
    mfls_calm   = [bsdt.mfls_score(X_series[i]) for i in calm_idx   if i < T]

    if not mfls_crisis or not mfls_calm:
        return {"sep_ratio": 0.0, "mfls_crisis": 0.0, "mfls_calm": 0.0,
                "cos_theta": 0.0, "lam_max": 0.0, "broken": True,
                "rank_preserved": False}

    mean_crisis = np.mean(mfls_crisis)
    mean_calm   = np.mean(mfls_calm)
    sep_ratio   = mean_crisis / (mean_calm + 1e-12)

    # cos θ at worst crisis
    worst_idx = crisis_idx[np.argmax(mfls_crisis)]
    X_w = X_series[worst_idx]
    mu_t = X_w.mean(axis=0)
    F = total_force(X_w, mu_t)
    G_bs = bsdt.gradient(X_w)
    dot_ = np.sum(G_bs * F, axis=1)
    nG = np.linalg.norm(G_bs, axis=1)
    nF = np.linalg.norm(F, axis=1)
    cos_ = dot_ / (nG * nF + 1e-12)
    cos_theta = float(np.mean(cos_))

    # Spectral radius at worst crisis
    lam, _ = spectral_radius(X_w, K=15)

    # Rank preservation: is the max MFLS still at a crisis quarter?
    all_mfls = np.array([bsdt.mfls_score(X_series[t]) for t in range(T)])
    top5_idx = set(np.argsort(all_mfls)[-5:])
    rank_preserved = any(ci in top5_idx for ci in crisis_idx)

    return {
        "sep_ratio":      sep_ratio,
        "mfls_crisis":    mean_crisis,
        "mfls_calm":      mean_calm,
        "cos_theta":      cos_theta,
        "lam_max":        lam,
        "broken":         sep_ratio < SEP_THRESHOLD,
        "rank_preserved": rank_preserved,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Attack functions — each returns modified X_series
# ─────────────────────────────────────────────────────────────────────────────

def attack_noise(X, level, rng):
    """Add Gaussian noise σ=level to all entries."""
    return X + rng.normal(0, level, size=X.shape)


def attack_dropout(X, frac, rng):
    """Zero out frac of all entries randomly."""
    mask = rng.random(X.shape) < frac
    Xp = X.copy()
    Xp[mask] = 0.0
    return Xp


def attack_bank_drop(X, n_drop, rng):
    """Remove n_drop banks (replace with mean)."""
    T, N, d = X.shape
    n_drop = min(n_drop, N - 2)
    victims = rng.choice(N, size=n_drop, replace=False)
    Xp = X.copy()
    for v in victims:
        Xp[:, v, :] = Xp.mean(axis=1)  # replace with cross-section mean
    return Xp


def attack_coordinated(X, strength, _rng):
    """Shift ALL banks identically each quarter → hides relative divergence."""
    T, N, d = X.shape
    Xp = X.copy()
    for t in range(T):
        shift = strength * Xp[t].mean(axis=0)  # shift towards centroid
        Xp[t] = Xp[t] + shift[None, :]
    return Xp


def attack_outlier(X, magnitude, rng):
    """Inject one extreme synthetic bank at random position."""
    T, N, d = X.shape
    victim = rng.integers(0, N)
    Xp = X.copy()
    Xp[:, victim, :] = magnitude * rng.standard_normal((T, d))
    return Xp


def attack_dim_collapse(X, n_zero, _rng):
    """Zero out n_zero feature dimensions (of 5)."""
    T, N, d = X.shape
    n_zero = min(n_zero, d - 1)
    Xp = X.copy()
    Xp[:, :, :n_zero] = 0.0
    return Xp


def attack_temporal_shuffle(X, frac, rng):
    """Shuffle frac of time steps randomly (destroys temporal structure)."""
    T = X.shape[0]
    n_shuf = max(1, int(frac * T))
    idx = np.arange(T)
    victims = rng.choice(T, size=n_shuf, replace=False)
    shuffled = rng.permutation(victims)
    idx[victims] = shuffled
    return X[idx]


def attack_adversarial_gd(X, bsdt, n_steps, eta=0.05):
    """Gradient-descent attack: move data to MINIMISE MFLS at each crisis step."""
    Xp = X.copy()
    T = X.shape[0]
    for t in range(T):
        Xt = Xp[t].copy()
        for _ in range(n_steps):
            G = bsdt.gradient(Xt)
            Xt = Xt - eta * G  # move OPPOSITE to gradient → minimise MFLS
        Xp[t] = Xt
    return Xp


def attack_scale(X, scale, _rng):
    """Multiply all features by scale → breaks normalisation assumptions."""
    return X * scale


def attack_covariance_poison(X, bsdt, noise_level, rng):
    """Corrupt the BSDT reference by adding noise to its inverse covariance."""
    bsdt_copy = BSDTOperator()
    bsdt_copy.mu0_ = bsdt.mu0_.copy()
    d = bsdt.Sigma0_inv_.shape[0]
    noise = rng.normal(0, noise_level, size=(d, d))
    noise = (noise + noise.T) / 2  # keep symmetric
    bsdt_copy.Sigma0_inv_ = bsdt.Sigma0_inv_ + noise
    return X, bsdt_copy  # returns BOTH modified bsdt


def attack_clone_banks(X, n_clones, rng):
    """Duplicate random banks n_clones times → dilutes real signal."""
    T, N, d = X.shape
    sources = rng.choice(N, size=n_clones, replace=True)
    clones = X[:, sources, :] + rng.normal(0, 0.01, size=(T, n_clones, d))
    return np.concatenate([X, clones], axis=1)


def attack_mean_shift(X, drift_per_q, _rng):
    """Cumulative drift: add drift_per_q * t to all features each quarter."""
    T, N, d = X.shape
    Xp = X.copy()
    for t in range(T):
        Xp[t] += drift_per_q * t
    return Xp


# ─────────────────────────────────────────────────────────────────────────────
# Main driver
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t_start = time.perf_counter()
    rng = np.random.default_rng(42)

    print("=" * 90)
    print("  ADVERSARIAL STRESS TEST — Molecular Engine Breaking Points")
    print("  12 attack vectors.  Increasing severity.  Real G-SIB data.")
    print("=" * 90)

    # Load data
    print("\nLoading real G-SIB panel...")
    X_std, mu_eq, dates, meta, norm_mask, crisis_idx, calm_idx = load_panel()
    T, N, d = X_std.shape
    print(f"  Panel: T={T}, N={N}, d={d}")

    # Fit BSDT on clean normal data
    X_normal = X_std[norm_mask]
    bsdt = BSDTOperator().fit(X_normal)

    # Baseline (no attack)
    print("\nBaseline (no attack):")
    baseline = evaluate(X_std, mu_eq, bsdt, crisis_idx, calm_idx)
    print(f"  MFLS_crisis = {baseline['mfls_crisis']:.1f}")
    print(f"  MFLS_calm   = {baseline['mfls_calm']:.1f}")
    print(f"  Sep ratio   = {baseline['sep_ratio']:.2f}")
    print(f"  cos θ       = {baseline['cos_theta']:+.4f}")
    print(f"  λ_max       = {baseline['lam_max']:.4f}")
    print(f"  Rank ok     = {baseline['rank_preserved']}")

    # ── The 12 attacks ──
    attacks = [
        # (name, function, severity_levels, param_name, needs_bsdt)
        ("1. GAUSSIAN NOISE (σ)",
         "noise", [0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0, 100.0]),

        ("2. FEATURE DROPOUT (%)",
         "dropout", [0.01, 0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.80, 0.90, 0.95]),

        ("3. BANK REMOVAL (count)",
         "bank_drop", [1, 2, 3, 5, 8, 10, 15, 20, 23]),

        ("4. COORDINATED SHIFT (strength)",
         "coordinated", [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0]),

        ("5. OUTLIER INJECTION (magnitude)",
         "outlier", [1.0, 2.0, 5.0, 10.0, 50.0, 100.0, 500.0, 1000.0]),

        ("6. DIMENSION COLLAPSE (dims zeroed)",
         "dim_collapse", [1, 2, 3, 4]),

        ("7. TEMPORAL SHUFFLE (%)",
         "temporal", [0.05, 0.10, 0.20, 0.30, 0.50, 0.70, 0.90, 1.00]),

        ("8. ADVERSARIAL GRADIENT (steps)",
         "adversarial_gd", [1, 2, 5, 10, 20, 50, 100]),

        ("9. SCALE ATTACK (multiplier)",
         "scale", [0.001, 0.01, 0.1, 0.5, 2.0, 5.0, 10.0, 100.0, 1000.0]),

        ("10. COVARIANCE POISON (noise level)",
         "cov_poison", [0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0]),

        ("11. CLONE BANKS (# clones)",
         "clone", [5, 10, 25, 50, 100, 200, 500]),

        ("12. MEAN DRIFT (per quarter)",
         "drift", [0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.5, 1.0]),
    ]

    results = {}

    for attack_name, attack_key, levels in attacks:
        print(f"\n{'─' * 90}")
        print(f"  {attack_name}")
        print(f"{'─' * 90}")
        print(f"  {'Level':>12s} | {'MFLS_cris':>10s} | {'MFLS_calm':>10s} | "
              f"{'Sep Ratio':>10s} | {'cos θ':>8s} | {'λ_max':>8s} | "
              f"{'Rank OK':>7s} | {'Status':>10s}")
        print(f"  {'-' * 85}")

        break_level = None
        attack_results = []

        for level in levels:
            bsdt_use = bsdt  # default

            if attack_key == "noise":
                Xp = attack_noise(X_std, level, rng)
            elif attack_key == "dropout":
                Xp = attack_dropout(X_std, level, rng)
            elif attack_key == "bank_drop":
                Xp = attack_bank_drop(X_std, level, rng)
            elif attack_key == "coordinated":
                Xp = attack_coordinated(X_std, level, rng)
            elif attack_key == "outlier":
                Xp = attack_outlier(X_std, level, rng)
            elif attack_key == "dim_collapse":
                Xp = attack_dim_collapse(X_std, level, rng)
            elif attack_key == "temporal":
                Xp = attack_temporal_shuffle(X_std, level, rng)
            elif attack_key == "adversarial_gd":
                Xp = attack_adversarial_gd(X_std, bsdt, level)
            elif attack_key == "scale":
                Xp = attack_scale(X_std, level, rng)
            elif attack_key == "cov_poison":
                Xp, bsdt_use = attack_covariance_poison(X_std, bsdt, level, rng)
            elif attack_key == "clone":
                Xp = attack_clone_banks(X_std, level, rng)
            elif attack_key == "drift":
                Xp = attack_mean_shift(X_std, level, rng)
            else:
                continue

            # For clone attack, crisis/calm indices don't change (time axis same)
            res = evaluate(Xp, mu_eq, bsdt_use, crisis_idx, calm_idx)

            status = "BROKEN" if res["broken"] else "OK"
            if not res["rank_preserved"]:
                status = "RANK LOST" if not res["broken"] else "BROKEN+RANK"

            print(f"  {str(level):>12s} | {res['mfls_crisis']:>10.1f} | "
                  f"{res['mfls_calm']:>10.1f} | {res['sep_ratio']:>10.2f} | "
                  f"{res['cos_theta']:>+8.4f} | {res['lam_max']:>8.4f} | "
                  f"{'YES' if res['rank_preserved'] else 'NO':>7s} | "
                  f"{status:>10s}")

            attack_results.append({"level": level, **res})

            if break_level is None and res["broken"]:
                break_level = level

        results[attack_key] = {
            "name": attack_name,
            "break_level": break_level,
            "details": attack_results,
        }

    # ── Summary table ──
    print("\n\n" + "=" * 90)
    print("  BREAKING POINT SUMMARY")
    print("=" * 90)
    print(f"\n  {'Attack':>35s} | {'Breaks at':>15s} | {'Margin to break':>15s}")
    print(f"  {'-' * 70}")

    for akey in ["noise", "dropout", "bank_drop", "coordinated", "outlier",
                  "dim_collapse", "temporal", "adversarial_gd", "scale",
                  "cov_poison", "clone", "drift"]:
        r = results[akey]
        bl = r["break_level"]
        if bl is not None:
            print(f"  {r['name']:>35s} | {str(bl):>15s} | -- BROKEN --")
        else:
            print(f"  {r['name']:>35s} | {'NEVER':>15s} | ROBUST")

    # ── Robustness profile ──
    n_broken = sum(1 for r in results.values() if r["break_level"] is not None)
    n_total  = len(results)
    n_robust = n_total - n_broken

    print(f"\n  Attacks survived (all levels): {n_robust}/{n_total}")
    print(f"  Attacks that eventually broke:  {n_broken}/{n_total}")

    if n_broken > 0:
        print("\n  VULNERABILITY RANKING (easiest to break first):")
        broken_attacks = [(k, v) for k, v in results.items() if v["break_level"] is not None]
        # Sort by break level (normalise to 0-1 scale based on level position)
        for akey, r in broken_attacks:
            levels = [d["level"] for d in r["details"]]
            bl_pos = levels.index(r["break_level"])
            pct = bl_pos / len(levels) * 100
            print(f"    {r['name']:>35s}: breaks at level {r['break_level']} "
                  f"({pct:.0f}% through severity range)")

    # ── Hardest attacks ──
    print("\n  RESILIENCE RANKING (most robust survivors):")
    for akey, r in results.items():
        if r["break_level"] is None:
            last = r["details"][-1]
            print(f"    {r['name']:>35s}: survived max severity "
                  f"(sep={last['sep_ratio']:.2f}, rank={'OK' if last['rank_preserved'] else 'LOST'})")

    # ── Minsky classification under each attack at break point ──
    print("\n  MINSKY CLASSIFICATION AT BREAKING POINTS:")
    print(f"  {'Attack':>35s} | {'Level':>8s} | {'Hedge':>7s} | {'Spec':>7s} | {'Ponzi':>7s}")
    print(f"  {'-' * 70}")

    # Get full trajectory cos θ for clean baseline
    stats_clean = engine.analyse_trajectory(X_std, mu_eq, bsdt, verbose=False)
    h, s, p = classify_minsky(stats_clean["cos_theta"])
    print(f"  {'[BASELINE - no attack]':>35s} | {'--':>8s} | {h*100:>6.1f}% | {s*100:>6.1f}% | {p*100:>6.1f}%")

    for akey in ["noise", "dropout", "bank_drop", "coordinated", "outlier",
                  "dim_collapse", "temporal", "adversarial_gd", "scale",
                  "cov_poison", "clone", "drift"]:
        r = results[akey]
        bl = r["break_level"]
        if bl is None:
            # Use max level
            bl = r["details"][-1]["level"]
        
        # Reconstruct attacked data at break level
        bsdt_use = bsdt
        if akey == "noise":
            Xp = attack_noise(X_std, bl, rng)
        elif akey == "dropout":
            Xp = attack_dropout(X_std, bl, rng)
        elif akey == "bank_drop":
            Xp = attack_bank_drop(X_std, bl, rng)
        elif akey == "coordinated":
            Xp = attack_coordinated(X_std, bl, rng)
        elif akey == "outlier":
            Xp = attack_outlier(X_std, bl, rng)
        elif akey == "dim_collapse":
            Xp = attack_dim_collapse(X_std, bl, rng)
        elif akey == "temporal":
            Xp = attack_temporal_shuffle(X_std, bl, rng)
        elif akey == "adversarial_gd":
            Xp = attack_adversarial_gd(X_std, bsdt, bl)
        elif akey == "scale":
            Xp = attack_scale(X_std, bl, rng)
        elif akey == "cov_poison":
            Xp, bsdt_use = attack_covariance_poison(X_std, bsdt, bl, rng)
        elif akey == "clone":
            Xp = attack_clone_banks(X_std, bl, rng)
        elif akey == "drift":
            Xp = attack_mean_shift(X_std, bl, rng)
        else:
            continue

        stats_atk = engine.analyse_trajectory(Xp, mu_eq, bsdt_use, verbose=False)
        h, s, p = classify_minsky(stats_atk["cos_theta"])
        tag = "BREAK" if r["break_level"] is not None else "MAX"
        print(f"  {r['name']:>35s} | {str(bl)+' '+tag:>8s} | "
              f"{h*100:>6.1f}% | {s*100:>6.1f}% | {p*100:>6.1f}%")

    elapsed = time.perf_counter() - t_start
    print(f"\n  Total elapsed: {elapsed:.1f}s")
    print("  Done.")


def classify_minsky(cos_arr):
    hedge = np.sum(cos_arr > 0.0) / len(cos_arr)
    ponzi = np.sum(cos_arr < -0.3) / len(cos_arr)
    spec  = 1.0 - hedge - ponzi
    return hedge, spec, ponzi


if __name__ == "__main__":
    main()
