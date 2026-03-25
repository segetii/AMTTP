"""
Morse-Index Numerical Verification — Theorem C (C1)
=====================================================
Verifies  ind_{E_BS}(X_c) = ind_Phi(X_c)  using the correct
single-particle interpretation:

  Phi_probe(x) = LJ potential experienced by ONE probe particle
                 at position x, all environment particles FIXED.
  E_BS(x)      = BSDT energy of x with FIXED fitted model.

Both are functions R^d -> R, so Hessians are d x d and comparable.

Tests:
  T1. At the Phi minimum  (expect ind=0 for both)
  T2. At the E_BS minimum (expect ind=0 for both)
  T3. Far from equilibrium (expect matching alarm: both ind>=1 OR both 0)
  T4. Gradient correlation along trajectory (verify C3 bound structure)
  T5. Gravity-based system (same protocol)
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from scipy.optimize import minimize as sp_minimize
from udl.system_mode import BSDTChannels

np.random.seed(42)

# ── Utilities ──────────────────────────────────────────────

def hessian_d(func, x, eps=1e-5):
    """d x d Hessian via 4-point central finite difference."""
    d = len(x)
    H = np.zeros((d, d))
    for i in range(d):
        for j in range(i, d):
            ei = np.zeros(d); ei[i] = eps
            ej = np.zeros(d); ej[j] = eps
            H[i,j] = (func(x+ei+ej) - func(x+ei-ej)
                     - func(x-ei+ej) + func(x-ei-ej)) / (4*eps*eps)
            H[j,i] = H[i,j]
    return H

def gradient_d(func, x, eps=1e-6):
    """d-dimensional gradient via central FD."""
    d = len(x)
    g = np.zeros(d)
    for i in range(d):
        ei = np.zeros(d); ei[i] = eps
        g[i] = (func(x+ei) - func(x-ei)) / (2*eps)
    return g

def morse_index(H, tol=1e-8):
    """Number of negative eigenvalues of H."""
    eigs = np.linalg.eigvalsh(H)
    return int(np.sum(eigs < -tol)), eigs

def fmt_eigs(eigs, n=3):
    """Format eigenvalue summary."""
    s = np.sort(eigs)
    if len(s) <= 2*n:
        return str(np.round(s, 6))
    return f"[{', '.join(f'{v:.4e}' for v in s[:n])}, ..., {', '.join(f'{v:.4e}' for v in s[-n:])}]"


# ── Lennard-Jones probe potential ──────────────────────────

def make_lj_probe(env, epsilon=1.0, sigma=1.0):
    """Return Phi(x) = total LJ potential of probe at x in env."""
    def phi(x):
        E = 0.0
        for j in range(len(env)):
            r = np.linalg.norm(x - env[j])
            if r < 1e-12: return 1e12
            sr6 = (sigma / r) ** 6
            E += 4.0 * epsilon * (sr6*sr6 - sr6)
        return E
    return phi


def make_gravity_probe(env, alpha=1.0, gamma=1.0, sigma_g=1.0, lam=1.0):
    """Return Phi(x) = gravity potential of probe at x in env."""
    def phi(x):
        E = 0.0
        for j in range(len(env)):
            r = np.linalg.norm(x - env[j])
            # radial
            E += 0.5 * alpha * r * r
            # Gaussian attraction
            E -= gamma * np.exp(-r*r / (2*sigma_g*sigma_g))
            # Coulomb repulsion
            E += lam / (r + 0.01)
        return E
    return phi


# ── Fit BSDT once, return frozen evaluator ─────────────────

def fit_bsdt(env, d):
    """Fit BSDTChannels on (env + far anomalies), return energy(x)."""
    N_e = len(env)
    # BSDTChannels.fit takes only X_ref (unsupervised)
    # Use environment as reference distribution
    X_ref = env.copy()

    bs = BSDTChannels()
    bs.fit(X_ref)

    def ebs(x):
        return bs.energy(x.reshape(1, -1))[0]
    return ebs


# ── Single test at a point ──────────────────────────────────

def test_at_point(phi, ebs, x, label):
    """Compute gradients, Hessians, Morse indices at x."""
    g_phi = gradient_d(phi, x)
    g_ebs = gradient_d(ebs, x)
    H_phi = hessian_d(phi, x)
    H_ebs = hessian_d(ebs, x)
    ind_p, eigs_p = morse_index(H_phi)
    ind_e, eigs_e = morse_index(H_ebs)

    gp_n = np.linalg.norm(g_phi)
    ge_n = np.linalg.norm(g_ebs)
    denom = gp_n * ge_n
    cos_t = np.dot(g_phi, g_ebs) / denom if denom > 1e-20 else 0.0

    match = ind_p == ind_e
    alarm = (ind_p >= 1) == (ind_e >= 1)

    print(f"\n--- {label} ---")
    print(f"  |nabla Phi|  = {gp_n:.4e}   |nabla E_BS| = {ge_n:.4e}")
    print(f"  cos theta    = {cos_t:.4f}")
    print(f"  Phi eigs:    {fmt_eigs(eigs_p)}")
    print(f"  E_BS eigs:   {fmt_eigs(eigs_e)}")
    print(f"  ind_Phi={ind_p}  ind_E_BS={ind_e}  "
          f"INDEX MATCH: {match}  ALARM AGREE: {alarm}")
    return dict(label=label, ind_phi=ind_p, ind_ebs=ind_e,
                match=match, alarm=alarm, cos_theta=cos_t,
                grad_phi=gp_n, grad_ebs=ge_n)


# ── Gradient correlation along a trajectory ─────────────────

def gradient_trajectory(phi, ebs, x_start, x_end, n_pts=50):
    """Sample gradients along the line x_start -> x_end."""
    gp_norms, ge_norms, cos_ts = [], [], []
    for i in range(n_pts):
        t = i / max(n_pts - 1, 1)
        x_t = x_start * (1 - t) + x_end * t
        gp = gradient_d(phi, x_t)
        ge = gradient_d(ebs, x_t)
        gpn, gen = np.linalg.norm(gp), np.linalg.norm(ge)
        gp_norms.append(gpn)
        ge_norms.append(gen)
        d = gpn * gen
        cos_ts.append(np.dot(gp, ge) / d if d > 1e-20 else 0.0)
    return np.array(gp_norms), np.array(ge_norms), np.array(cos_ts)


# ── Main test routines ──────────────────────────────────────

def run_lj_test(d=4, N_env=20, label_prefix="LJ"):
    """Full test battery for LJ probe potential."""
    sigma = 1.0; epsilon = 1.0
    r_eq = sigma * 2**(1/6)

    # Environment cluster near origin
    env = np.random.randn(N_env, d) * 0.3 * r_eq

    phi = make_lj_probe(env, epsilon, sigma)
    ebs = fit_bsdt(env, d)

    print("=" * 64)
    print(f"{label_prefix}  d={d}  N_env={N_env}")
    print("=" * 64)

    results = []

    # T1: Phi minimum
    x0 = env.mean(axis=0)
    res = sp_minimize(phi, x0, method='Nelder-Mead',
                      options={'xatol':1e-10, 'fatol':1e-14, 'maxiter':300000})
    x_phi_min = res.x
    results.append(test_at_point(phi, ebs, x_phi_min,
                                 f"{label_prefix} T1: Phi minimum"))

    # T2: E_BS minimum
    res2 = sp_minimize(ebs, x0, method='Nelder-Mead',
                       options={'xatol':1e-10, 'fatol':1e-14, 'maxiter':300000})
    x_ebs_min = res2.x
    dist = np.linalg.norm(x_phi_min - x_ebs_min)
    print(f"  dist(Phi_min, E_BS_min) = {dist:.6f}")
    results.append(test_at_point(phi, ebs, x_ebs_min,
                                 f"{label_prefix} T2: E_BS minimum"))

    # T3: Far from equilibrium
    x_far = x_phi_min + np.zeros(d); x_far[0] += 3 * r_eq
    results.append(test_at_point(phi, ebs, x_far,
                                 f"{label_prefix} T3: 3r_eq away"))

    # T4: very far (beyond LJ cutoff)
    x_vfar = x_phi_min + np.zeros(d); x_vfar[0] += 8 * r_eq
    results.append(test_at_point(phi, ebs, x_vfar,
                                 f"{label_prefix} T4: 8r_eq away"))

    # T5: Gradient correlation
    gp_n, ge_n, ct = gradient_trajectory(phi, ebs, x_phi_min, x_far)
    valid = gp_n > 1e-6
    corr = np.corrcoef(gp_n[valid], ge_n[valid])[0,1] if valid.sum() > 2 else 0
    ratios = ge_n[valid] / (gp_n[valid] + 1e-30)
    print(f"\n--- {label_prefix} Gradient trajectory (Phi_min -> 3r_eq) ---")
    print(f"  |nabla| correlation = {corr:.4f}")
    print(f"  cos theta: [{ct.min():.4f}, {ct.max():.4f}], mean={ct.mean():.4f}")
    if len(ratios) > 0:
        print(f"  |nabla E|/|nabla Phi| ratio: [{ratios.min():.4e}, {ratios.max():.4e}]")

    return results


def run_gravity_test(d=4, N_env=20, label_prefix="Grav"):
    """Full test battery for gravity probe potential."""
    env = np.random.randn(N_env, d) * 0.5

    phi = make_gravity_probe(env, alpha=1.0, gamma=2.0, sigma_g=1.0, lam=0.5)
    ebs = fit_bsdt(env, d)

    print("\n" + "=" * 64)
    print(f"{label_prefix}  d={d}  N_env={N_env}")
    print("=" * 64)

    results = []

    # T1: Phi minimum
    x0 = env.mean(axis=0)
    res = sp_minimize(phi, x0, method='Nelder-Mead',
                      options={'xatol':1e-10, 'fatol':1e-14, 'maxiter':300000})
    x_phi_min = res.x
    results.append(test_at_point(phi, ebs, x_phi_min,
                                 f"{label_prefix} T1: Phi minimum"))

    # T2: E_BS minimum
    res2 = sp_minimize(ebs, x0, method='Nelder-Mead',
                       options={'xatol':1e-10, 'fatol':1e-14, 'maxiter':300000})
    x_ebs_min = res2.x
    dist = np.linalg.norm(x_phi_min - x_ebs_min)
    print(f"  dist(Phi_min, E_BS_min) = {dist:.6f}")
    results.append(test_at_point(phi, ebs, x_ebs_min,
                                 f"{label_prefix} T2: E_BS minimum"))

    # T3: displaced
    x_far = x_phi_min + np.zeros(d); x_far[0] += 3.0
    results.append(test_at_point(phi, ebs, x_far,
                                 f"{label_prefix} T3: 3 units away"))

    # T4: Gradient trajectory
    gp_n, ge_n, ct = gradient_trajectory(phi, ebs, x_phi_min, x_far)
    valid = gp_n > 1e-6
    corr = np.corrcoef(gp_n[valid], ge_n[valid])[0,1] if valid.sum() > 2 else 0
    print(f"\n--- {label_prefix} Gradient trajectory ---")
    print(f"  |nabla| correlation = {corr:.4f}")
    print(f"  cos theta: [{ct.min():.4f}, {ct.max():.4f}], mean={ct.mean():.4f}")

    return results


def main():
    print("MORSE INDEX VERIFICATION — Theorem C (C1)")
    print("Correct interpretation: single probe particle, d×d Hessians")
    print("Phi and E_BS as functions R^d → R, FIXED fitted model")
    print("=" * 64)

    all_results = []

    # LJ tests: d=3 (physical), d=4, d=6
    all_results.extend(run_lj_test(d=3, N_env=12, label_prefix="LJ-3D"))
    all_results.extend(run_lj_test(d=4, N_env=20, label_prefix="LJ-4D"))
    all_results.extend(run_lj_test(d=6, N_env=20, label_prefix="LJ-6D"))

    # Gravity tests
    all_results.extend(run_gravity_test(d=3, N_env=12, label_prefix="Grav-3D"))
    all_results.extend(run_gravity_test(d=4, N_env=20, label_prefix="Grav-4D"))

    # Print summary
    print("\n" + "=" * 64)
    print("SUMMARY")
    print("=" * 64)
    print(f"{'Test':<35} {'ind_Phi':>8} {'ind_EBS':>8} {'idx=':>5} {'alarm':>6} {'cosθ':>7}")
    print("-" * 70)
    total = len(all_results)
    idx_match = sum(1 for r in all_results if r['match'])
    alm_match = sum(1 for r in all_results if r['alarm'])
    for r in all_results:
        m = "YES" if r['match'] else " NO"
        a = "YES" if r['alarm'] else " NO"
        print(f"{r['label']:<35} {r['ind_phi']:>8} {r['ind_ebs']:>8} {m:>5} {a:>6} {r['cos_theta']:>7.3f}")
    print("-" * 70)
    print(f"Index match: {idx_match}/{total}  |  Alarm agree: {alm_match}/{total}")

    if idx_match == total:
        print("\n✓ C1 VERIFIED: Morse indices match at all test points")
    elif alm_match == total:
        print(f"\n≈ Alarm equivalence holds ({alm_match}/{total}), "
              f"exact index match {idx_match}/{total}")
    else:
        print(f"\n! {total - alm_match} alarm disagreements")


if __name__ == "__main__":
    main()
