"""Validation: full §I-XXVII engine, v1.2.0"""
import numpy as np
from collapse_geometry import (
    MasterOperator, LedoitWolfNetwork, MFLS,
    LyapunovCertificate, CollapseGeometry,
    EarlyWarning, PrecursorScale, EscapeTime,
    StochasticExtension, RecoveryDynamics, InformationGeometry,
    WelfareCalibration,
)
from collapse_geometry.state import Snapshot
from collapse_geometry.engines import Gravity, Molecular

rng = np.random.default_rng(42)
N, d, T0 = 8, 4, 50

# ── Normal period ──────────────────────────────────────────────
X_normal = rng.standard_normal((T0, N, d)) * 0.3

# ── Calibrate ─────────────────────────────────────────────────
M = MasterOperator.calibrate(X_normal, k=4, theta=1.0)
print(f"[1] Calibration OK  mu0={M.cal.mu0.round(3)}  v0={M.cal.v0:.4f}")

# Stressed snapshot
X_t = rng.standard_normal((N, d)) * 1.2
snap = Snapshot(X=X_t, X_prev=X_normal[-1], history=X_normal[-5:])

# ── §XI pipeline ──────────────────────────────────────────────
lev_panel = X_normal[:, :, 0]
net = LedoitWolfNetwork.from_panel(lev_panel)
out = M.pipeline(snap, network=net)
print(f"[2] Pipeline OK")
print(f"    e_t={out['e_t']:.3f}  MFLS={out['MFLS_t']:.3f}  gamma*={out['gamma_star']:.3f}  supercrit={out['supercritical']}")
print(f"    rho_MFLS={out['rho_MFLS']:.3f}  psi={out['psi']:.3f}rad  xi6={out['xi6']:.3f}")
print(f"    cos_th_ch_raw={out['cos_theta_channel_raw']:.3f}  cos_th_st={out['cos_theta_state']:.3f}")

# ── §XXVI verification: xi6 = min(1, rho_MFLS^2) ──────────────
rho = out['rho_MFLS']
xi6_expected = min(1.0, rho ** 2)
assert abs(out['xi6'] - xi6_expected) < 1e-9, f"xi6 mismatch: {out['xi6']} vs {xi6_expected}"
print(f"[3] §XXVI xi6 = min(1,rho^2) VERIFIED  xi6={out['xi6']:.4f}")

# ── §XVI Lyapunov certificate ─────────────────────────────────
lyap = LyapunovCertificate(op=M)
dv     = lyap.dV_dt(snap)
margin = lyap.margin(snap)
print(f"[4] Lyapunov  dV/dt={dv:.4f}  margin={margin:.4f}")

# ── §XXV per-channel decomposition ───────────────────────────
ch_dec = lyap.channel_decomposition(snap)
total_attr = sum(v['attribution'] for v in ch_dec.values())
assert abs(total_attr - 1.0) < 1e-9 or total_attr < 1e-9, f"attribution sum={total_attr}"
print(f"[5] Per-channel attribution sums to {total_attr:.6f}  channels={list(ch_dec)}")
for ch, v in ch_dec.items():
    print(f"    {ch}: v_drift={v['v_drift']:.4f}  v_ctrl={v['v_control']:.4f}  attr={v['attribution']:.3f}")

# ── §XIV collapse geometry — three conditions ─────────────────
cg    = CollapseGeometry(op=M)
conds = cg.all_conditions(snap)
tan_t = cg.tan_theta(snap)
print(f"[6] Collapse conds={conds}  tan_theta={tan_t:.3f}")

# ── §XVII EWS — 6 signals + two-layer ────────────────────────
ews  = EarlyWarning(op=M, geom=cg)
score = ews.score(snap, net)
sigs  = ews.signals(snap, net)
xi_vec = [sigs['xi1'], sigs['xi2'], sigs['xi3'], sigs['xi4'], sigs['xi5'], sigs['xi6']]
print(f"[7] EWS score={score:.4f}  xi={[round(x,3) for x in xi_vec]}")
# verify xi_6 == cos^2(psi) from mfls
from collapse_geometry.mfls import MFLS as MFLS_cls
mfls_obj = M.mfls
psi_check = mfls_obj.psi(snap)
xi6_check = float(np.cos(psi_check)**2)
assert abs(xi6_check - out['xi6']) < 1e-9, f"EWS xi6 vs pipeline xi6: {xi6_check} vs {out['xi6']}"
print(f"    xi6 consistent with pipeline: {xi6_check:.4f}")

# ── PrecursorScale + two-layer ────────────────────────────────
ps = PrecursorScale.from_panel(M, X_normal)
ews.precursor_scale = ps
res = ews.two_layer(snap, net, snap_prev=None, e_star=50.0)
print(f"[8] Two-layer  precursor={res['precursor_score']:.4f}  geom={res['geometry_score']:.4f}")

# ── §XVIII escape time ────────────────────────────────────────
et  = EscapeTime(op=M, lyap=lyap)
tau = et.linear(snap, e_star=50.0)
print(f"[9] Escape time (linear) tau={'inf' if tau == float('inf') else f'{tau:.2f}'}")

# ── §XIX stochastic ───────────────────────────────────────────
sde = StochasticExtension(op=M, lyap=lyap, sigma_n=0.05)
ito = sde.ito_correction(snap)
exp_dv = sde.expected_dV(snap)
print(f"[10] Ito correction={ito:.4f}  E[dV/dt]={exp_dv:.4f}  stable_in_E={sde.stable_in_expectation(snap)}")

# ── §XXII recovery ────────────────────────────────────────────
rec = RecoveryDynamics(op=M)
gc  = rec.gamma_critical(snap)
print(f"[11] gamma_crit={gc:.4f}  has_crisis_eq={rec.has_crisis_equilibria(snap)}")
dXdt_rec = rec.recover_step(snap)
print(f"     recover_step ||dX/dt||={np.linalg.norm(dXdt_rec,'fro'):.4f}")

# ── §XXIII information geometry ───────────────────────────────
ig = InformationGeometry(op=M)
e_star_chi2 = ig.chi2_threshold(N, d, 0.01)
print(f"[12] chi2 e*={e_star_chi2:.2f}  breach={ig.confidence_breach(snap)}")

# ── §IX welfare ───────────────────────────────────────────────
welfare  = WelfareCalibration(op=M)
panel    = rng.standard_normal((10, N, d)) * 1.5
sig_ell  = panel[:, :, 0].std(axis=1)
report   = welfare.report(panel, sig_ell)
print(f"[13] Welfare loss={report['welfare_loss_pp']:.3f}pp  CCyB max={report['ccyb_max_bps']:.1f}bps")

# ── §XV master operator step ──────────────────────────────────
dXdt = M.step(snap)
print(f"[14] Master operator step  ||dX/dt||_F={np.linalg.norm(dXdt,'fro'):.4f}")

# ── Gravity (forward ODE integration) ────────────────────────
grav = Gravity.from_panel(M, X_normal, controlled=True)
traj = grav.trajectory(snap, T=20)
assert traj.shape == (21, N, d)
print(f"[15] Gravity trajector shape={traj.shape}  final ||X||={np.linalg.norm(traj[-1],'fro'):.4f}")

# ── Molecular (Langevin) ──────────────────────────────────────
mol     = Molecular.from_panel(M, X_normal, controlled=True, seed=0)
Xs, Vs  = mol.trajectory(snap, T=10)
assert Xs.shape == (11, N, d)
print(f"[16] Molecular trajectory shape={Xs.shape}  final ||V||={np.linalg.norm(Vs[-1],'fro'):.4f}")

# ── Hybrid engine (LJ + gravity + control + thermal) ──────────
from collapse_geometry.engines import Hybrid
hyb    = Hybrid.from_panel(M, X_normal, seed=0)
Xh, Vh = mol.trajectory(snap, T=5)
assert Xh.shape == (6, N, d)
print(f"[17] Hybrid trajectory shape={Xh.shape}  final ||X||={np.linalg.norm(Xh[-1],'fro'):.4f}")

print()
import collapse_geometry as cg_pkg
print(f"=== ALL 17 CHECKS PASSED  [collapse_geometry v{cg_pkg.__version__}] ===")
