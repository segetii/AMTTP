"""Run the §I-XXVII collapse_geometry pipeline on four real datasets.

Datasets follow the **structural flow** of the prior pipeline (SIAM §7):
    Data → CalibrationState.fit(X_normal) → MasterOperator.calibrate
         → Snapshot(stress_event) → diagnostics(§I-XXVII)
         → CCyB / welfare / EWS / lead-time

Sources (located by the inventory step):
    1. FDIC  : research/adaptive-friction/upgraded/fred_cache/fdic_specgrp_quarterly.pkl
                (140 quarters × N=7 institution types × d=7 balance-sheet features)
    2. WB    : research/adaptive-friction/banklevel_enhanced/gsib_cache_real/wb_*.json
                (8 countries × 5 indicators, annual since ~2000)
    3. ERCOT : data/ercot/ercot_daily_2018_2022.npz
                (1826 days × d=6 grid features; sliding 30-day window → N=30 agents)
    4. Protein: test_protein_folding.py simulator
                (30-residue β-hairpin, folded vs unfolded trajectory)

Output: paper_real_data_results.txt (machine-friendly) + stdout summary.
"""
from __future__ import annotations
import json
import os
import pickle
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "adaptive-friction"))

from collapse_geometry import (              # noqa: E402
    MasterOperator, Snapshot, LedoitWolfNetwork,
    LyapunovCertificate, CollapseGeometry, EarlyWarning,
    EscapeTime, StochasticExtension, AgentSensitivity,
    InformationGeometry, WelfareCalibration, UDLTransform,
)


# ════════════════════════════════════════════════════════════════════════════
# Common diagnostics function — applies the full §I-XXVII pipeline
# ════════════════════════════════════════════════════════════════════════════
def run_diagnostics(name: str,
                    X_normal: np.ndarray,             # (T0, N, d) calibration panel
                    snap: Snapshot,                   # stress-event snapshot
                    network_panel: np.ndarray | None = None,  # (T0, N) leverage feature
                    crisis_panel: np.ndarray | None = None,    # (T_crisis, N, d)
                    sigma_ell: np.ndarray | None = None,      # (T_crisis,)
                    notes: str = "",
                    use_udl_transform: bool = False) -> dict:
    """Apply every §I-XXVII diagnostic and return a dict of scalars."""
    print(f"\n{'═'*72}\n  {name}\n{'═'*72}")
    if notes:
        print(f"  {notes}")
    T0, N, d = X_normal.shape
    print(f"  Calibration panel : T0={T0}, N={N}, d={d}")

    # ── Optional UDL multi-domain transform ─────────────────────────────────
    if use_udl_transform:
        print(f"  Applying UDLTransform (stat+chaos+spec+geom → PCA 8) ...")
        udl = UDLTransform(n_components=8, standardize=True)
        udl.fit(X_normal)
        X_normal = udl.transform(X_normal)                     # (T0, N, 8)
        # Transform the stress snapshot into the same UDL space
        def _udl_snap(s: Snapshot) -> Snapshot:
            X_u = udl.transform(s.X[None, :, :])[0]            # (N, 8)
            Xp = udl.transform(s.X_prev[None, :, :])[0]
            h  = s.history
            h_u = udl.transform(h) if h.ndim == 3 and h.shape[0] > 0 else h
            return Snapshot(X=X_u, X_prev=Xp, history=h_u)
        snap = _udl_snap(snap)
        if crisis_panel is not None:
            crisis_panel = udl.transform(crisis_panel)          # (T_c, N, 8)
        T0, N, d = X_normal.shape
        print(f"  UDL output panel  : T0={T0}, N={N}, d={d}")


    M = MasterOperator.calibrate(X_normal, k=min(4, d), theta=1.0)
    info = InformationGeometry(op=M)
    e_star = info.chi2_threshold(N, d, alpha_conf=0.01)
    print(f"  e* (χ²_{N*d}, .99)   = {e_star:.2f}")

    # Network — use the supplied feature panel or fall back to feature 0
    if network_panel is None:
        network_panel = X_normal[..., 0]
    net = LedoitWolfNetwork.from_panel(network_panel)
    print(f"  Network           : ρ_LW={net.rho:.3f}  λ_max(W)={net.lam_max:.3f}  "
          f"W̄_off={net.W_bar_off:.3f}")

    # Stress-snapshot diagnostics
    e_t = M.damp.e_BSDT(snap)
    gamma = M.damp.gamma_star(snap)
    mfls_st = M.mfls.state_mfls(snap)
    mfls_ch = M.mfls.channel_mfls(snap)
    rho_mfls = M.mfls.rho_mfls(snap)
    psi = M.mfls.psi(snap)

    geom = CollapseGeometry(op=M)
    cos_state = geom.cos_theta_state(snap)
    cos_chan  = geom.cos_theta_channel(snap)
    tan_t     = geom.tan_theta(snap)
    cond      = geom.all_conditions(snap)

    lyap = LyapunovCertificate(op=M)
    dV   = lyap.dV_dt(snap)
    Mt   = lyap.margin(snap)
    gmin = lyap.gamma_min(snap)
    th_max = lyap.theta_ceiling(snap)

    chans = lyap.channel_decomposition(snap)
    dom_ch = max(chans, key=lambda k: chans[k]["attribution"])
    S = M.bsdt.channel_state(snap)
    c_k = M.energy.channel_attribution(S)
    k_dom_ch = "CGAT"[M.energy.dominant_channel(S)]

    ews = EarlyWarning(op=M, geom=geom)
    ews_score = ews.score(snap, net)
    ews_thresh = ews.threshold(theta=M.damp.theta, e_star=e_star)
    sig = ews.signals(snap, net)

    esc = EscapeTime(op=M, lyap=lyap)
    tau_lin  = esc.linear(snap, e_star)
    tau_safe = esc.safe_horizon(snap, e_star)

    sde = StochasticExtension(op=M, lyap=lyap, sigma_n=1e-2)
    ito  = sde.ito_correction(snap)
    tauK = sde.kramers_time(snap, e_star)

    sens = AgentSensitivity(op=M)
    imp = sens.normalised(snap)
    crit_agent = int(np.argmax(imp))

    # Regulatory output (only if we have a crisis panel)
    ccyb_max = ccyb_mean = welfare = None
    if crisis_panel is not None:
        welf = WelfareCalibration(op=M, sigma_calib=1.0)
        if sigma_ell is None:
            sigma_ell = crisis_panel[..., 0].std(axis=1)
        ccyb_series = welf.ccyb(crisis_panel, sigma_ell)
        ccyb_max  = float(ccyb_series.max())
        ccyb_mean = float(ccyb_series.mean())
        welfare   = float(welf.welfare_loss(crisis_panel))

    res = dict(
        dataset=name, N=N, d=d, T0=T0,
        e_star=float(e_star), e_BSDT=float(e_t), gamma_star=float(gamma),
        rho_lw=float(net.rho), lam_W=float(net.lam_max), W_bar_off=float(net.W_bar_off),
        MFLS_state=float(mfls_st), MFLS_channel=float(mfls_ch),
        rho_MFLS=float(rho_mfls), psi=float(psi),
        cos_theta_state=float(cos_state), cos_theta_channel=float(cos_chan),
        tan_theta=float(tan_t),
        spectral=bool(cond["spectral"]),
        angular=bool(cond["angular"]),
        energetic=bool(cond["energetic"]),
        dV_dt=float(dV), margin_M=float(Mt),
        gamma_min=(None if gmin is None else float(gmin)),
        theta_ceiling=(None if th_max is None else float(th_max)),
        dominant_channel_lyap=dom_ch,
        dominant_channel_grad=k_dom_ch,
        channel_attribution=[float(x) for x in c_k],
        EWS=float(ews_score), EWS_threshold=float(ews_thresh),
        EWS_signals={k: float(v) for k, v in sig.items()},
        tau_linear=float(tau_lin), tau_safe=float(tau_safe),
        ito_correction=float(ito), tau_kramers=float(tauK),
        critical_agent=crit_agent,
        agent_importance=[float(x) for x in imp],
        CCyB_bps_max=ccyb_max, CCyB_bps_mean=ccyb_mean,
        welfare_loss_pp=welfare,
    )

    # Pretty stdout
    print(f"  e_BSDT            : {e_t:.4f}    γ*={gamma:.4f}    ψ={psi:.4f} rad")
    print(f"  MFLS state/chan   : {mfls_st:.3f} / {mfls_ch:.3f}    "
          f"ρ_MFLS={rho_mfls:.3f}")
    print(f"  cos θ_state/chan  : {cos_state:+.4f} / {cos_chan:+.4f}    "
          f"tan θ={tan_t:.4f}")
    print(f"  Conditions        : spectral={cond['spectral']}  "
          f"angular={cond['angular']}  energetic={cond['energetic']}")
    print(f"  Lyapunov          : dV/dt={dV:+.3e}  margin={Mt:+.4f}  "
          f"γ*_min={gmin}  θ_ceil={th_max}")
    print(f"  Dominant channel  : Lyap='{dom_ch}'  grad='{k_dom_ch}'  "
          f"c_k={[f'{x:.3f}' for x in c_k]}")
    print(f"  EWS               : {ews_score:.4f} (threshold {ews_thresh:.4f})  "
          f"breach={ews_score > ews_thresh}")
    print(f"  Escape time       : τ_lin={tau_lin:.3f}  τ_safe={tau_safe:.3f}  "
          f"τ_Kramers={tauK:.3e}")
    print(f"  Critical agent    : #{crit_agent}  importance={imp.round(3)}")
    if crisis_panel is not None:
        print(f"  CCyB (bps)        : max={ccyb_max:.1f}  mean={ccyb_mean:.1f}")
        print(f"  Welfare loss (pp) : {welfare:.4f}")
    return res


# ════════════════════════════════════════════════════════════════════════════
# Dataset 1 — FDIC  (140 quarters × 7 institution types × 7 features)
# ════════════════════════════════════════════════════════════════════════════
def load_fdic() -> tuple[np.ndarray, np.ndarray, list]:
    pkl = ROOT / "research/adaptive-friction/upgraded/fred_cache/fdic_specgrp_quarterly.pkl"
    df = pickle.load(open(pkl, "rb"))
    cols = ["ASSET", "LNLSNET", "EQ", "NETINC", "EINTEXP", "INTINC", "NCLNLS"]
    dates = sorted(df.index.get_level_values("REPDTE").unique())
    grps  = sorted(df.index.get_level_values("SPECGRP").unique())
    T, N, d = len(dates), len(grps), len(cols)
    X = np.zeros((T, N, d))
    for t, dt in enumerate(dates):
        for n, g in enumerate(grps):
            try:
                X[t, n] = df.loc[(dt, g), cols].to_numpy(dtype=float)
            except KeyError:
                X[t, n] = np.nan
    # Engineered ratios — the spec wants leverage etc., not raw $ values
    # feature 0: leverage = LNLSNET / ASSET
    # feature 1: equity   = EQ / ASSET
    # feature 2: NPL      = NCLNLS / LNLSNET
    # feature 3: ROA      = NETINC / ASSET
    # feature 4: int.cost = EINTEXP / ASSET
    # feature 5: NIM      = (INTINC - EINTEXP) / ASSET
    A = X[..., 0] + 1e-9
    L = X[..., 1] + 1e-9
    Y = np.stack([
        X[..., 1] / A,                 # leverage (LNLSNET/ASSET)
        X[..., 2] / A,                 # equity ratio
        X[..., 6] / L,                 # NPL ratio
        X[..., 3] / A,                 # ROA
        X[..., 4] / A,                 # interest expense ratio
        (X[..., 5] - X[..., 4]) / A,   # net interest margin
    ], axis=-1)
    Y = np.nan_to_num(Y, nan=0.0, posinf=0.0, neginf=0.0)
    return Y, np.array(dates), ["leverage", "equity", "NPL", "ROA", "int_cost", "NIM"]


def run_fdic() -> dict:
    Y, dates, fnames = load_fdic()
    import pandas as pd
    dts = pd.to_datetime(dates)
    # Normal: 1990-Q1 to 2007-Q2  (pre-GFC)
    mask_norm = dts < pd.Timestamp("2007-07-01")
    X_norm = Y[mask_norm]
    # Stress: 2008-Q4 (peak GFC)
    idx_stress = int(np.argmin(np.abs((dts - pd.Timestamp("2008-12-31")).total_seconds())))
    snap = Snapshot(X=Y[idx_stress], X_prev=Y[idx_stress - 1],
                    history=Y[max(0, idx_stress - 20): idx_stress])
    # Crisis window: 2007-Q4 .. 2010-Q1
    mask_crisis = (dts >= pd.Timestamp("2007-10-01")) & (dts <= pd.Timestamp("2010-03-31"))
    return run_diagnostics("FDIC — US banking (GFC Q4-2008 stress event)",
                           X_norm, snap,
                           network_panel=X_norm[..., 0],
                           crisis_panel=Y[mask_crisis],
                           sigma_ell=Y[mask_crisis][..., 0].std(axis=1),
                           notes="Source: FDIC Quarterly Banking Profile via FRED, "
                                 "7 SPECGRP institution types, 6 ratio features")


# ════════════════════════════════════════════════════════════════════════════
# Dataset 2 — World Bank (8 countries × 5 indicators)
# ════════════════════════════════════════════════════════════════════════════
def load_worldbank() -> tuple[np.ndarray, np.ndarray, list, list]:
    cache = ROOT / "research/adaptive-friction/banklevel_enhanced/gsib_cache_real"
    countries = ["CHN", "DEU", "FRA", "GBR", "ITA", "JPN", "NGA", "NLD"]
    # use 5 indicators present across most countries
    indicators = ["FB.AST.NPER.ZS", "FB.BNK.CAPA.ZS", "GFDD.SI.01",
                  "FR.INR.LEND", "FR.INR.DPST"]
    series = {}
    for c in countries:
        for ind in indicators:
            f = cache / f"wb_{c}_{ind}.json"
            if f.exists():
                d = json.load(open(f))
                series[(c, ind)] = {k[:4]: v for k, v in d.items() if v is not None}
    # union of years
    years = sorted({y for s in series.values() for y in s})
    Y = np.full((len(years), len(countries), len(indicators)), np.nan)
    for ci, c in enumerate(countries):
        for ii, ind in enumerate(indicators):
            s = series.get((c, ind), {})
            for ti, y in enumerate(years):
                Y[ti, ci, ii] = s.get(y, np.nan)
    # Forward-fill then nan→column-mean
    for ci in range(len(countries)):
        for ii in range(len(indicators)):
            col = Y[:, ci, ii]
            mask = ~np.isnan(col)
            if mask.sum() > 0:
                col[~mask] = np.interp(np.flatnonzero(~mask),
                                       np.flatnonzero(mask), col[mask])
                Y[:, ci, ii] = col
            else:
                Y[:, ci, ii] = 0.0
    Y = np.nan_to_num(Y, nan=0.0)
    years_arr = np.array([int(y) for y in years])
    return Y, years_arr, countries, indicators


def run_worldbank() -> dict:
    Y, years, countries, ind = load_worldbank()
    mask_norm = (years < 2008)
    X_norm = Y[mask_norm]
    if X_norm.shape[0] < 5:
        # not enough pre-crisis years — fall back to first half
        X_norm = Y[: max(5, len(years) // 2)]
    idx_stress = int(np.argmin(np.abs(years - 2008)))
    prev = max(0, idx_stress - 1)
    snap = Snapshot(X=Y[idx_stress], X_prev=Y[prev],
                    history=Y[max(0, idx_stress - 5): idx_stress])
    mask_crisis = (years >= 2007) & (years <= 2012)
    crisis_panel = Y[mask_crisis]
    return run_diagnostics("WORLD BANK — 8-country panel (2008 GFC stress)",
                           X_norm, snap,
                           network_panel=X_norm[..., 1],   # equity ratio
                           crisis_panel=crisis_panel,
                           notes=f"Countries={countries}, indicators={ind}, "
                                 f"years {years.min()}–{years.max()}")


# ════════════════════════════════════════════════════════════════════════════
# Dataset 3 — ERCOT (Texas grid; sliding 30-day window → N=30 agents)
# ════════════════════════════════════════════════════════════════════════════
def load_ercot() -> tuple[np.ndarray, np.ndarray, list]:
    z = np.load(ROOT / "data/ercot/ercot_daily_2018_2022.npz", allow_pickle=True)
    X_raw = z["X"].astype(float)                  # (T=1826, d=6)
    dates = np.array(z["dates"], dtype="datetime64[D]")
    fn_raw = [str(s) for s in z["feature_names"]]
    # In this archive only temp_f has real values; load_* / ramp / ixn are NaN.
    # Derive a 6-feature temperature panel for an honest cross-domain run.
    temp = X_raw[:, fn_raw.index("temp_f")]
    T = len(temp)
    def rolling(arr, w, fn):
        out = np.full_like(arr, np.nan)
        for i in range(len(arr)):
            lo = max(0, i - w + 1)
            out[i] = fn(arr[lo: i + 1])
        return out
    feat_temp        = temp
    feat_dtemp       = np.concatenate([[0.0], np.diff(temp)])
    feat_abs_dtemp   = np.abs(feat_dtemp)
    feat_roll7_mean  = rolling(temp, 7, np.mean)
    feat_roll30_mean = rolling(temp, 30, np.mean)
    feat_dev_norm    = (temp - feat_roll30_mean) / (rolling(temp, 30, np.std) + 1e-6)
    X = np.column_stack([feat_temp, feat_dtemp, feat_abs_dtemp,
                         feat_roll7_mean, feat_roll30_mean, feat_dev_norm])
    fn = ["temp_f", "dtemp", "abs_dtemp", "roll7_mean", "roll30_mean", "dev_z30"]
    return X, dates, fn


def windowed_panel(X: np.ndarray, t: int, N: int) -> np.ndarray:
    """Snapshot at day t = stack of last N days (each day is one 'agent')."""
    return X[t - N: t]


def run_ercot() -> dict:
    X, dates, fn = load_ercot()
    T, d = X.shape
    # Per-feature standardization (z-score) — ERCOT raw features have wildly
    # different magnitudes (load_mean_gw ~50, temp_f ~70, load×temp ~3500),
    # which produces an ill-conditioned covariance and breaks LAPACK eigh/svd.
    mu_g = X.mean(axis=0, keepdims=True)
    sd_g = X.std(axis=0, keepdims=True) + 1e-8
    X = (X - mu_g) / sd_g
    # Reshape into weekly snapshots: N=7 days × d=6 features per week
    N = 7
    n_weeks = T // N
    X = X[: n_weeks * N]
    dates = dates[: n_weeks * N]
    X_panel = X.reshape(n_weeks, N, d)                          # (T, 7, 6)
    week_dates = dates[::N][:n_weeks]
    # Normal: 2018 .. 2020-12-31  (pre Uri)
    mask_norm = week_dates < np.datetime64("2021-01-01")
    X_norm = X_panel[mask_norm]
    # Stress: week containing 2021-02-15  (Winter Storm Uri peak)
    idx_stress = int(np.argmin(np.abs(week_dates - np.datetime64("2021-02-15"))))
    snap = Snapshot(X=X_panel[idx_stress], X_prev=X_panel[idx_stress - 1],
                    history=X_panel[max(0, idx_stress - 12): idx_stress])
    # Crisis window: Feb-Mar 2021
    mask_crisis = (week_dates >= np.datetime64("2021-02-01")) & \
                  (week_dates <= np.datetime64("2021-03-31"))
    crisis_panel = X_panel[mask_crisis]
    return run_diagnostics("ERCOT — Texas grid (Winter Storm Uri week of 15-Feb-2021)",
                           X_norm, snap,
                           network_panel=X_norm[..., 0],
                           crisis_panel=crisis_panel,
                           notes="Daily 2018-2022 grid features derived from ERCOT temp_f "
                                 "(load columns NaN in this archive). 6 derived features: "
                                 "temp, dtemp, |dtemp|, roll7-mean, roll30-mean, z-dev. "
                                 "Weekly snapshot N=7 days × d=6")


# ════════════════════════════════════════════════════════════════════════════
# Dataset 4 — Protein folding (β-hairpin folded vs unfolded trajectory)
# ════════════════════════════════════════════════════════════════════════════
def load_protein() -> tuple[np.ndarray, np.ndarray]:
    """Run the protein simulator and extract per-residue features for two
    temperatures (folded T<Tm and unfolded T>Tm)."""
    sys.path.insert(0, str(ROOT))
    import test_protein_folding as P                   # noqa: E402
    cfg = P.ProteinConfig()
    native = P.build_native_structure(cfg)
    contacts, contact_d = P.compute_native_contacts(native, cfg)

    def sim(T_kelvin: float, n_steps: int = 4000, every: int = 50,
            seed: int = 0) -> np.ndarray:
        """Return (T_frames, N=N_residues, d=4) trajectory of per-residue features."""
        rng = np.random.default_rng(seed)
        np.random.seed(seed)
        pos = native.copy() + 0.05 * rng.standard_normal(native.shape)
        vel = np.zeros_like(pos)
        feats = []
        for step in range(n_steps):
            pos, vel, _ = P.langevin_step(pos, vel, cfg, contacts, contact_d,
                                          np.empty((0, 2), dtype=int),
                                          T_kelvin, cfg.gamma_const)
            if step % every == 0:
                centroid = pos.mean(axis=0)
                local_rmsd = np.linalg.norm(pos - native, axis=1)
                D = np.linalg.norm(pos[:, None, :] - pos[None, :, :], axis=2)
                local_dens = (D < 8.0).sum(axis=1) - 1
                radial = np.linalg.norm(pos - centroid, axis=1)
                cscore = np.ones(cfg.N)
                if len(contacts) > 0:
                    ci, cj = contacts[:, 0], contacts[:, 1]
                    dcur = np.linalg.norm(pos[cj] - pos[ci], axis=1)
                    formed = (dcur < 1.2 * contact_d).astype(float)
                    tot = np.zeros(cfg.N); fmd = np.zeros(cfg.N)
                    np.add.at(tot, ci, 1); np.add.at(tot, cj, 1)
                    np.add.at(fmd, ci, formed); np.add.at(fmd, cj, formed)
                    has = tot > 0
                    cscore[has] = fmd[has] / tot[has]
                feats.append(np.stack([local_rmsd, cscore, local_dens.astype(float),
                                       radial], axis=-1))
        return np.array(feats)                        # (T, N, 4)

    # T_melt is implicit in this Go-model (k_B T = epsilon_native at melting).
    # Use T such that k_B T = eps_native as a proxy for T_melt.
    T_melt = float(cfg.eps_native / cfg.kB)
    folded   = sim(T_kelvin=T_melt * 0.6, seed=1)
    unfolded = sim(T_kelvin=T_melt * 1.5, seed=2)
    return folded, unfolded


def run_protein() -> dict:
    folded, unfolded = load_protein()
    # Calibrate on folded (normal); stress = last frame of unfolded
    X_norm = folded
    snap = Snapshot(X=unfolded[-1], X_prev=unfolded[-2], history=unfolded[-20:])
    return run_diagnostics("PROTEIN — β-hairpin (unfolded above T_melt)",
                           X_norm, snap,
                           network_panel=X_norm[..., 1],   # contact-fraction couplings
                           crisis_panel=unfolded,
                           notes="30-residue Cα Go-model, 4 per-residue features "
                                 "(local RMSD, contact fraction, local density, "
                                 "radial distance from centroid)")


# ════════════════════════════════════════════════════════════════════════════
# Driver
# ════════════════════════════════════════════════════════════════════════════
def main() -> None:
    out_path = ROOT / "research/adaptive-friction/collapse_geometry_real_data_results.json"
    print("\n" + "═"*72)
    print("  COLLAPSE-GEOMETRY  §I-XXVII  ON FOUR REAL-WORLD DATASETS")
    print("═"*72)
    t0 = time.perf_counter()

    # ── Pass 1: raw features ─────────────────────────────────────────────
    results = {}
    for name, fn in [("FDIC", run_fdic),
                     ("WORLDBANK", run_worldbank),
                     ("ERCOT", run_ercot),
                     ("PROTEIN", run_protein)]:
        try:
            results[name] = fn()
        except Exception as exc:                          # pragma: no cover
            import traceback
            print(f"\n!! {name} FAILED: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            results[name] = dict(error=f"{type(exc).__name__}: {exc}")

    # ── Pass 2: UDL-transformed features ────────────────────────────────
    print("\n" + "─"*72)
    print("  PASS 2 — UDL Multi-Domain Transform (stat+chaos+spec+geom → PCA-8)")
    print("─"*72)
    results_udl = {}
    udl_fns = [
        ("FDIC",      lambda: run_fdic_udl()),
        ("WORLDBANK", lambda: run_worldbank_udl()),
        ("ERCOT",     lambda: run_ercot_udl()),
        ("PROTEIN",   lambda: run_protein_udl()),
    ]
    for name, fn in udl_fns:
        try:
            results_udl[name] = fn()
        except Exception as exc:
            import traceback
            print(f"\n!! {name} (UDL) FAILED: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            results_udl[name] = dict(error=f"{type(exc).__name__}: {exc}")

    # ── Comparison summary ───────────────────────────────────────────────
    print("\n" + "═"*72)
    print("  EWS COMPARISON  —  raw features vs UDL-transformed")
    print(f"  {'Dataset':<14}  {'EWS (raw)':>10}  {'EWS (UDL)':>10}  {'Δ':>8}")
    print("  " + "─"*50)
    for key in ("FDIC", "WORLDBANK", "ERCOT", "PROTEIN"):
        r   = results.get(key, {})
        r_u = results_udl.get(key, {})
        ews_raw = r.get("EWS", float("nan"))
        ews_udl = r_u.get("EWS", float("nan"))
        delta = ews_udl - ews_raw if not (np.isnan(ews_raw) or np.isnan(ews_udl)) else float("nan")
        print(f"  {key:<14}  {ews_raw:>10.4f}  {ews_udl:>10.4f}  {delta:>+8.4f}")

    out_path.write_text(json.dumps({"raw": results, "udl": results_udl}, indent=2, default=str))
    elapsed = time.perf_counter() - t0
    print(f"\n{'═'*72}\n  All runs complete in {elapsed:.1f}s")
    print(f"  Full results written to:\n    {out_path}\n{'═'*72}")


# ── UDL-transform dataset runners (called from main Pass 2) ─────────────────
def run_fdic_udl() -> dict:
    import pandas as pd
    Y, dates, fnames = load_fdic()
    dts = pd.to_datetime(dates)
    mask_norm = dts < pd.Timestamp("2007-07-01")
    X_norm = Y[mask_norm]
    idx_stress = int(np.argmin(np.abs((dts - pd.Timestamp("2008-12-31")).total_seconds())))
    snap = Snapshot(X=Y[idx_stress], X_prev=Y[idx_stress - 1],
                    history=Y[max(0, idx_stress - 20): idx_stress])
    mask_crisis = (dts >= pd.Timestamp("2007-10-01")) & (dts <= pd.Timestamp("2010-03-31"))
    return run_diagnostics("FDIC (UDL) — US banking (GFC Q4-2008)",
                           X_norm, snap,
                           network_panel=X_norm[..., 0],
                           crisis_panel=Y[mask_crisis],
                           sigma_ell=Y[mask_crisis][..., 0].std(axis=1),
                           use_udl_transform=True)


def run_worldbank_udl() -> dict:
    Y, years, countries, ind = load_worldbank()
    mask_norm = (years < 2007)
    X_norm = Y[mask_norm] if mask_norm.sum() >= 3 else Y[:max(3, len(years)//2)]
    idx_s = int(np.argmin(np.abs(years - 2008)))
    snap = Snapshot(X=Y[idx_s], X_prev=Y[idx_s - 1], history=Y[max(0, idx_s - 5): idx_s])
    return run_diagnostics("WORLD BANK (UDL) — 8-country panel (2008 GFC)",
                           X_norm, snap,
                           use_udl_transform=True)


def run_ercot_udl() -> dict:
    X, dates, fn = load_ercot()
    T, d = X.shape
    N = 7
    n_weeks = T // N
    X = X[: n_weeks * N]; dates = dates[: n_weeks * N]
    panel = X.reshape(n_weeks, N, d)
    week_dates = dates[::N][:n_weeks]
    mu = panel.mean(axis=(0, 1)); sd = panel.std(axis=(0, 1)) + 1e-8
    panel = (panel - mu) / sd
    mask_norm = week_dates < np.datetime64("2021-01-01")
    X_norm = panel[mask_norm]
    tw = int(np.argmin(np.abs(week_dates - np.datetime64("2021-02-15"))))
    snap = Snapshot(X=panel[tw], X_prev=panel[tw - 1], history=panel[max(0, tw - 5): tw])
    return run_diagnostics("ERCOT (UDL) — Texas grid (Winter Storm Uri)",
                           X_norm, snap,
                           network_panel=X_norm[..., 0],
                           crisis_panel=panel[max(0, tw - 8): tw + 1],
                           use_udl_transform=True)


def run_protein_udl() -> dict:
    folded, unfolded = load_protein()
    snap = Snapshot(X=unfolded[-1], X_prev=unfolded[-2], history=unfolded[-20:])
    return run_diagnostics("PROTEIN (UDL) — β-hairpin (unfolded above T_melt)",
                           folded, snap,
                           network_panel=folded[..., 1],
                           crisis_panel=unfolded,
                           use_udl_transform=True)


if __name__ == "__main__":
    main()

