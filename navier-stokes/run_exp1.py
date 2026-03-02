"""Quick run of Experiment 1: Adaptive vs Constant viscosity."""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from solver import NSParams, NavierStokesSolver, extract_timeseries, save_results

print("="*70)
print("  EXPERIMENT 1: Adaptive v(E) vs Constant v")
print("  Taylor-Green Vortex, N=32, Re~200")
print("="*70)

results = {}
for label, adaptive in [("constant_nu", False), ("adaptive_nu", True)]:
    print(f"\n--- {label} ---")
    params = NSParams(
        N=32, nu_base=5e-3, dt=2e-3, T_final=5.0,
        theta=1.0, adaptive=adaptive, integrator="rk4",
        diag_interval=10, heavy_interval=50,
    )
    solver = NavierStokesSolver(params)
    solver.initialize("taylor_green")
    t0 = time.time()
    history = solver.run()
    elapsed = time.time() - t0
    results[label] = history

    data = extract_timeseries(history)
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Final energy:    {data['energy'][-1]:.6f}")
    print(f"  Peak enstrophy:  {np.max(data['enstrophy']):.6f}")
    print(f"  Peak ||w||_inf:  {np.max(data['omega_inf']):.4f}")
    print(f"  BKM integral:    {data['bkm_integral'][-1]:.4f}")
    print(f"  Peak E_BS:       {np.max(data['E_bs']):.4f}")
    print(f"  v_eff range:     [{np.min(data['nu_eff']):.6f}, {np.max(data['nu_eff']):.6f}]")

save_results(results, os.path.join(os.path.dirname(__file__), "exp1_results.json"))

# Now run the proof verification
from proof_scaffolding import verify_regularity_conditions, verify_theorem_B
import json

print("\n" + "="*70)
print("  REGULARITY VERIFICATION")
print("="*70)

for label, history in results.items():
    print(f"\n--- {label} ---")
    reg = verify_regularity_conditions(history)
    for k, v in reg.items():
        print(f"  {k}: {v}")

    thm = verify_theorem_B(history)
    print(f"\n  Theorem B verification:")
    for k, v in thm.items():
        print(f"    {k}: {v}")

print("\nDone.")
