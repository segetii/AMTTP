"""
Fast experiment: Adaptive vs Constant viscosity.
Reduced T and using semi-implicit for speed.
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from solver import NSParams, NavierStokesSolver, extract_timeseries, save_results
from proof_scaffolding import verify_regularity_conditions, verify_theorem_B

OUT = os.path.dirname(__file__)

results = {}
summaries = {}

for label, adaptive in [("constant_nu", False), ("adaptive_nu", True)]:
    print(f"\n{'='*60}")
    print(f"  {label.upper()}")
    print(f"{'='*60}")
    params = NSParams(
        N=32, nu_base=5e-3, dt=2e-3, T_final=2.0,  # shorter
        theta=1.0, adaptive=adaptive, integrator="semi_implicit",
        diag_interval=10, heavy_interval=50,
    )
    solver = NavierStokesSolver(params)
    solver.initialize("taylor_green")
    t0 = time.time()
    history = solver.run()
    elapsed = time.time() - t0
    results[label] = history

    data = extract_timeseries(history)
    s = {
        "label": label,
        "time_s": round(elapsed, 1),
        "final_energy": round(float(data["energy"][-1]), 6),
        "peak_enstrophy": round(float(np.max(data["enstrophy"])), 6),
        "peak_omega_inf": round(float(np.max(data["omega_inf"])), 4),
        "bkm_integral": round(float(data["bkm_integral"][-1]), 4),
        "peak_E_bs": round(float(np.max(data["E_bs"])), 4),
        "nu_eff_min": round(float(np.min(data["nu_eff"])), 6),
        "nu_eff_max": round(float(np.max(data["nu_eff"])), 6),
        "delta_A_mean": round(float(np.mean(data["delta_A"])), 4),
        "energy_decay_pct": round(100*(1 - data["energy"][-1]/data["energy"][0]), 2),
        "smooth": bool(np.max(data["enstrophy"]) < 1e6),
    }
    summaries[label] = s
    for k, v in s.items():
        print(f"  {k}: {v}")

# Regularity verification
print(f"\n{'='*60}")
print("  REGULARITY VERIFICATION")
print(f"{'='*60}")

for label, history in results.items():
    print(f"\n--- {label} ---")
    reg = verify_regularity_conditions(history)
    for k, v in reg.items():
        print(f"  {k}: {v}")

    thm = verify_theorem_B(history)
    print(f"  --- Theorem B ---")
    for k, v in thm.items():
        print(f"  {k}: {v}")
    summaries[label]["theorem_B"] = thm

# Save
save_results(results, os.path.join(OUT, "exp1_results.json"))
with open(os.path.join(OUT, "exp1_summary.json"), "w") as f:
    # Convert non-serializable
    def convert(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        return obj
    json.dump(summaries, f, indent=2, default=convert)

print(f"\nResults saved. Done.")
