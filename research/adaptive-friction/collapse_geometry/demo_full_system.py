"""End-to-end demo of the full collapse-geometry stack.

Builds a synthetic financial system (N=8 institutions, d=4 features), calibrates
on a normal period, then runs all three engines through a stress event and prints
every diagnostic from §VI–§XXVII.

Run:  py -3 demo_full_system.py
"""
from __future__ import annotations
import numpy as np
from collapse_geometry import (
    MasterOperator, Snapshot, LedoitWolfNetwork,
    LyapunovCertificate, CollapseGeometry, EarlyWarning,
    EscapeTime, StochasticExtension, AgentSensitivity,
    RecoveryDynamics, InformationGeometry, WelfareCalibration,
    Gravity, Molecular, Hybrid,
)


def synth_normal_period(T0: int = 200, N: int = 8, d: int = 4,
                        seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    mu = np.array([0.4, 0.6, 0.3, 0.5])[:d]
    L = 0.05 * np.eye(d) + 0.02 * rng.standard_normal((d, d))
    Sigma = L @ L.T + 0.01 * np.eye(d)
    X = rng.multivariate_normal(mu, Sigma, size=(T0, N))
    return X.astype(float)


def stress_snapshot(cal_panel: np.ndarray, magnitude: float = 5.0,
                    seed: int = 1) -> Snapshot:
    rng = np.random.default_rng(seed)
    last = cal_panel[-1].copy()
    # shock: 3 institutions move 5σ along leverage feature
    last[:3, 0] += magnitude * cal_panel[..., 0].std()
    return Snapshot(X=last, X_prev=cal_panel[-2], history=cal_panel[-20:])


def main() -> None:
    print("\n=== COLLAPSE GEOMETRY — FULL SYSTEM DEMO ===\n")
    panel = synth_normal_period()
    print(f"Calibration panel: {panel.shape}  (T0, N, d)")

    # 1. Calibrate master operator
    M = MasterOperator.calibrate(panel, k=2, theta=1.0)
    print(f"  μ0 = {M.cal.mu0.round(3)}")
    print(f"  v0 (95%-tile velocity) = {M.cal.v0:.4f}")

    # 2. Build network from leverage panel (T, N)
    net = LedoitWolfNetwork.from_panel(panel[..., 0])
    print(f"  Network: ρ_LW={net.rho:.3f}  λ_max(W)={net.lam_max:.3f}  "
          f"ρ_proxy={net.rho_proxy:.3f}")

    # 3. Construct stress snapshot
    snap = stress_snapshot(panel, magnitude=5.0)
    D = snap.distance_matrix()
    print(f"\n--- STRESS SNAPSHOT (3-of-8 agents shocked) ---")
    print(f"  Φ_total           = {M.potential.E_total(snap.X, M.cal.mu0, D):.4f}")
    print(f"  λ_max(∇²Φ) bound  = {M.potential.lambda_max_bound(D):.4f}")
    print(f"  e_BSDT            = {M.damp.e_BSDT(snap):.4f}")
    print(f"  γ*                = {M.damp.gamma_star(snap):.4f}")
    print(f"  MFLS_channel      = {M.mfls.channel_mfls(snap):.4f}")
    print(f"  MFLS_state        = {M.mfls.state_mfls(snap):.4f}")
    print(f"  ρ_MFLS amplif.    = {M.mfls.rho_mfls(snap):.4f}")
    print(f"  ψ_t (rad)         = {M.mfls.psi(snap):.4f}")

    # 4. Lyapunov & per-channel
    lyap = LyapunovCertificate(op=M)
    print(f"\n--- LYAPUNOV CERTIFICATE ---")
    print(f"  dV/dt             = {lyap.dV_dt(snap):.4f}")
    print(f"  margin M_t        = {lyap.margin(snap):.4f}")
    gmin = lyap.gamma_min(snap)
    print(f"  γ*_min required   = {gmin if gmin is None else f'{gmin:.4f}'}")
    print(f"  Per-channel attribution:")
    for k, v in lyap.channel_decomposition(snap).items():
        print(f"    {k}: V̇={v['v_total']:+.4f}  η={v['eta']:+.3f}  "
              f"a={v['attribution']:.3f}")

    # 5. Geometry — three equivalent collapse conditions
    geom = CollapseGeometry(op=M)
    print(f"\n--- COLLAPSE GEOMETRY ---")
    print(f"  cos θ_state       = {geom.cos_theta_state(snap):.4f}")
    print(f"  tan θ             = {geom.tan_theta(snap):.4f}")
    print(f"  tan θ*            = {geom.tan_theta_star(snap):.4f}")
    for k, v in geom.all_conditions(snap).items():
        print(f"  {k:<10}        = {'BREACH' if v else 'safe'}")

    # 6. Early Warning
    ews = EarlyWarning(op=M, geom=geom)
    s = ews.signals(snap, net)
    print(f"\n--- EARLY WARNING (6 signals) ---")
    for k, v in s.items():
        print(f"  {k} = {v:.4f}")
    print(f"  EWS composite     = {ews.score(snap, net):.4f}")

    # 7. Escape time
    esc = EscapeTime(op=M, lyap=lyap)
    info = InformationGeometry(op=M)
    e_star = info.chi2_threshold(snap.N, snap.d, alpha_conf=0.01)
    print(f"\n--- ESCAPE TIME (e* = χ²_{{Nd, .99}} = {e_star:.2f}) ---")
    print(f"  τ_lin             = {esc.linear(snap, e_star):.4f}")
    print(f"  τ_safe            = {esc.safe_horizon(snap, e_star):.4f}")

    # 8. Stochastic
    sde = StochasticExtension(op=M, lyap=lyap, sigma_n=1e-2)
    print(f"\n--- STOCHASTIC EXTENSION ---")
    print(f"  Itô correction    = {sde.ito_correction(snap):.6f}")
    print(f"  E[dV/dt]          = {sde.expected_dV(snap):.4f}")
    print(f"  Stable in expect. = {sde.stable_in_expectation(snap)}")
    print(f"  τ_Kramers         = {sde.kramers_time(snap, e_star):.2e}")

    # 9. Agent sensitivity
    sens = AgentSensitivity(op=M)
    imp = sens.normalised(snap)
    print(f"\n--- AGENT SENSITIVITY ---")
    print(f"  importance        = {imp.round(3)}")
    print(f"  critical agent    = #{int(np.argmax(imp))}")

    # 10. Recovery
    rec = RecoveryDynamics(op=M)
    print(f"\n--- RECOVERY ---")
    print(f"  γ_critical        = {rec.gamma_critical(snap):.4f}")
    print(f"  multiple equil.   = {rec.has_crisis_equilibria(snap)}")

    # 11. Information geometry
    print(f"\n--- INFORMATION GEOMETRY ---")
    print(f"  D_KL ≈ e_t/N      = {info.kl_to_normal(snap):.4f}")
    print(f"  Fisher trace      = {info.fisher_trace(snap):.4f}")
    print(f"  χ² breach (1%)    = {info.confidence_breach(snap)}")

    # 12. Run all three engines for 50 steps
    print(f"\n--- ENGINE COMPARISON (50 steps, dt=1e-2) ---")
    # 12. Run all three engines — every parameter derived from the panel
    print(f"\n--- ENGINE COMPARISON (50 steps, all params from panel) ---")
    grav = Gravity.from_panel(M, panel)
    mol  = Molecular.from_panel(M, panel)
    hyb  = Hybrid.from_panel(M, panel)
    print(f"  Gravity   {grav.report()}")
    print(f"  Molecular {mol.report()}")
    print(f"  Hybrid    {hyb.report()}")

    Xg = grav.trajectory(snap, T=50)
    Xm, _ = mol.trajectory(snap, T=50)
    Xh, _ = hyb.trajectory(snap, T=50)

    def final_e(X):
        return float(np.linalg.norm((X[-1] - M.cal.mu0) @ M.cal.Sigma0_inv_sqrt, "fro") ** 2)

    print(f"  Gravity   final e_BSDT = {final_e(Xg):.4f}")
    print(f"  Molecular final e_BSDT = {final_e(Xm):.4f}")
    print(f"  Hybrid    final e_BSDT = {final_e(Xh):.4f}")
    print(f"  initial    e_BSDT     = {M.damp.e_BSDT(snap):.4f}")

    # 13. §IX — CCyB regulatory calibration & welfare loss
    print(f"\n--- REGULATORY (§IX) — CCyB & WELFARE LOSS ---")
    welf = WelfareCalibration(op=M, sigma_calib=1.0)
    sigma_ell = panel[..., 0].std(axis=1)            # leverage vol per t
    ccyb = welf.ccyb(panel, sigma_ell)
    wloss = welf.welfare_loss(panel)
    print(f"  CCyB(t) range     = [{ccyb.min():.1f}, {ccyb.max():.1f}] bps")
    print(f"  Welfare loss      = {wloss:.4f} pp consumption-equivalent")

    # 14. §V — supercritical fraction over the panel trajectory
    p_sc = M.potential.supercritical_fraction(panel)
    print(f"\n--- §V SUPERCRITICAL FRACTION ---")
    print(f"  p̂_SC over panel   = {p_sc:.4f}")

    # 15. §VII channel-cosine + §XIV.3 curvature-tangent
    print(f"\n--- §VII / §XIV.3 ANGULAR DIAGNOSTICS ---")
    print(f"  cos θ_channel     = {geom.cos_theta_channel(snap):.4f}")
    print(f"  tan θ_curv (φ=π/4)= {geom.tan_theta_curv(snap, phi=np.pi/4):.4f}")

    # 16. §XVI MFLS decay rate, §XVII EWS threshold, §XIX stationary p*
    print(f"\n--- §XVI / §XVII / §XIX ADDITIONAL DIAGNOSTICS ---")
    print(f"  dMFLS/dt          = {lyap.mfls_rate(snap):.4f}")
    print(f"  EWS* threshold    = {ews.threshold(theta=M.damp.theta, e_star=e_star):.4f}")
    e_grid = np.linspace(0.1, e_star, 50)
    p_star = sde.stationary_density(snap, e_grid)
    print(f"  p*(e) at e_star   = {p_star[-1]:.4e}  (∫p*=1, len={len(e_grid)})")

    # 17. §XXI network amplification, §XXII energy barriers
    print(f"\n--- §XXI / §XXII NETWORK & BARRIER DIAGNOSTICS ---")
    amp = sens.network_amplification(snap)
    print(f"  ∂L/∂x_i amplif.   = {amp.round(3)}")
    # build a saddle and a crisis state for barrier comparison
    X_saddle = M.cal.mu0 + 0.5 * (snap.X - M.cal.mu0)
    X_crisis = M.cal.mu0 + 1.5 * (snap.X - M.cal.mu0)
    bars = rec.energy_barriers(M.cal.mu0[None, :].repeat(snap.N, 0),
                               X_saddle, X_crisis)
    print(f"  ΔΦ_collapse       = {bars['delta_collapse']:.4f}")
    print(f"  ΔΦ_recovery       = {bars['delta_recovery']:.4f}")
    print(f"  asymmetry         = {bars['asymmetry']:.4f}")

    # 18. §XII.4-5 unit collapse direction + per-channel attribution + dominant
    print(f"\n--- §XII.4-5 CHANNEL-SPACE DECOMPOSITION ---")
    S = M.bsdt.channel_state(snap)
    u_ch = M.energy.unit_direction(S)
    c_k  = M.energy.channel_attribution(S)
    k_st = M.energy.dominant_channel(S)
    print(f"  S (channel state) = {S.round(4)}")
    print(f"  u (unit, ||·||=1) = {u_ch.round(4)}  (||u||={np.linalg.norm(u_ch):.4f})")
    print(f"  c_k (Σ=1)         = {c_k.round(4)}")
    print(f"  dominant channel  = #{k_st}  ({'CGAT'[k_st]})")

    # 19. §XVI.7 intervention-cost ceiling  θ_max  (Basel III calibration limit)
    theta_max = lyap.theta_ceiling(snap)
    print(f"\n--- §XVI.7 INTERVENTION-COST CEILING ---")
    print(f"  current θ         = {M.damp.theta:.4f}")
    if theta_max is None:
        print(f"  θ_max             = None  (uncontrollable regime: P≤0 or Q≤0)")
    else:
        print(f"  θ_max             = {theta_max:.4f}  "
              f"({'OK' if M.damp.theta < theta_max else 'BREACH — control insufficient'})")

    print("\n=== DEMO COMPLETE — full §I–XXVII pipeline operational ===\n")


if __name__ == "__main__":
    main()
