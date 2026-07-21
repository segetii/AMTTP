"""§XXIV / §XXVI / §XVI / §XXV / §XXX  paper-correct per-bar diagnostics.

Builds a DataFrame aligned to df_1h.index with engine-canonical quantities used
by the corrected-paper sections of run_robustness_validation.py.

Columns produced
----------------
    MFLS_ch          ||g_t||                        — §XXIV.4 channel MFLS
    MFLS_st          ||G̃_t||_F                      — §XXIV.4 state MFLS
    rho_MFLS         MFLS_st / MFLS_ch              — §XXIV.4 amplification
    cos_psi          min(1, rho_MFLS)               — §XXVI.1 (canonical)
    psi              arccos(min(1, rho_MFLS)) [rad] — §XXVI.1
    xi6              cos² psi  ∈ [0,1]              — §XXVI.3 (6th EWS)
    P_t              ⟨G̃, F⟩_F                       — §XVI.6
    Q_t              ⟨F,g⟩ · R_t                    — §XVI.6
    R_t              g^T Gram g = ||G̃||_F²           — §XXIV.5
    F_norm           ||F_t||_F                      — restoring force magnitude
    X_norm           ||X_t||_F                      — state magnitude (for §XXX RC)
    inner_GtF        P_t                            — alias for §XXX RC test
    dV_dt            P_t − γ* Q_t / ||g||²          — §XVI.4
    M_margin         (γ* Q/||g||² − P)/(|P|+|Q|/||g||²) — §XXIV.5 stability margin
    theta_ceiling    e_t · (Q/(||g||² P) − 1)       — §XVI.7  (NaN where uncontrollable)
    gamma_min        ||g||² P / Q                   — §XVI.6  (NaN where uncontrollable)
    a_C, a_G, a_A, a_T   per-channel attribution    — §XXV
    eta_C, eta_G, eta_A, eta_T   control-correction ratio per channel — §XXV
    vdrift_C/G/A/T   per-channel drift V̇_drift,k    — §XXV
    vctrl_C/G/A/T    per-channel control V̇_ctrl,k   — §XXV
    gamma_star       γ*_t (from M.damp)             — §VIII

Cache: on disk under C:\\amttp\\data\\corrected_diagnostics_v58.pkl with TTL = 72h.
"""
from __future__ import annotations
import os, time, pickle
from pathlib import Path
import numpy as np
import pandas as pd

from collapse_geometry import Snapshot, MasterOperator, LyapunovCertificate

_CACHE_DIR = Path(r'C:\amttp\data')
_CACHE_TTL_H = 72
_HISTORY_LEN_DEFAULT = 48      # parity with run_crypto_pairs_v36_intraday_bsdt history_len


def _safe(x, default=np.nan):
    if x is None:
        return default
    if isinstance(x, float) and (np.isnan(x) or np.isinf(x)):
        return default
    return x


def compute_corrected_diagnostics(
    X: np.ndarray,
    df_1h: pd.DataFrame,
    M: MasterOperator,
    lyap: LyapunovCertificate,
    *,
    start_idx: int = 0,
    history_len: int = _HISTORY_LEN_DEFAULT,
    cache_key: str = 'v58_default',
    use_cache: bool = True,
    verbose: bool = True,
) -> pd.DataFrame:
    """Iterate over bars [start_idx, T), build Snapshot, run engine, return aligned DataFrame.

    Bars before start_idx contain NaN (we typically only need post-calibration bars).
    """
    cache_path = _CACHE_DIR / f'corrected_diagnostics_{cache_key}.pkl'
    if use_cache and cache_path.exists():
        age_h = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_h < _CACHE_TTL_H:
            try:
                df = pd.read_pickle(str(cache_path))
                if len(df) == len(df_1h) and (df.index == df_1h.index).all():
                    if verbose:
                        print(f'  corrected_diagnostics [CACHE age={age_h:.1f}h]')
                    return df
            except Exception:
                pass

    T = len(df_1h)
    cols = [
        # §VII paper-original (bounded, dimensionally consistent) — use these
        'cos_theta',          # §VII state-space cosθ ∈ [−1, 1]  (canonical alignment)
        'cos_theta_ch',       # §XXIV.3 channel cosθ (unbounded, for diagnostic only)
        'MFLS_paper',         # §VI.5  paper-original MFLS = 2 ||X̃ Σ⁻¹||_F  (single scalar)
        # §XXIV / §XXVI candidates (kept as scale-inconsistency diagnostics)
        'MFLS_ch', 'MFLS_st', 'rho_MFLS', 'cos_psi', 'psi', 'xi6',
        'lambda_max_Gram',    # operator norm of T(g) = Σ g_k J_k  (§XXIV scale fix)
        'rho_normalised',     # ρ_MFLS / sqrt(λ_max(Gram))  ∈ [0, 1] by Rayleigh
        'gram_eff_rank',      # (Σλ)² / Σλ²  effective rank of Gram ∈ [1, 4] — §XXIV activity gauge
        'drift_ctrl_coh',     # cos(vdrift, vctrl) over 4 channels — §XXV agreement / fight regime
        # SCALE-AUDIT block — per-channel norms + correlation-Gram (magnitude-free)
        'J_norm_C', 'J_norm_G', 'J_norm_A', 'J_norm_T',  # ||J_k||_F per channel
        'J_norm_spread',          # log10( max ||J_k|| / min ||J_k|| ) — channel scale gap
        'gram_corr_eff_rank',     # eff rank of CORRELATION Gram (each J normalised first)
        'lambda_max_GramCorr',    # λ_max of correlation Gram ∈ [1, 4]
        'rho_corr_normalised',    # ρ in correlation basis (magnitude-free)
        'drift_ctrl_disagree',    # fraction of channels with sign(vdrift_k) ≠ sign(vctrl_k)
        'drift_ctrl_coh_norm',    # cos(vdrift, vctrl) AFTER per-channel z-norm to ±1
        'dom_channel',            # 0=C 1=G 2=A 3=T — channel with max ||J_k||_F
        # ENGINE-INTRINSIC FORECAST SKILL block — engine output vs realised dynamics,
        # NO trading abstraction in between.  These quantities measure whether the
        # state-space force field F_t actually predicts ΔX_t = X[t+1] − X[t].
        'engine_signal',          # ⟨F_t, u_state_t⟩_F   (engine's scalar "gas pedal")
        'engine_signal_norm',     # engine_signal / ||F_t||_F  ∈ [-1, 1]
        'F_dx_align',             # cos(F_t, ΔX_{t→t+1})  — raw forecast cosine
        'G_dx_align',             # cos(G̃_t, ΔX_{t→t+1}) — pullback forecast cosine
        'dx_norm',                # ||ΔX_{t→t+1}||_F      (realised state change scale)
        'F_dot_dx',               # ⟨F_t, ΔX⟩_F           (signed projection)
        'ar1_dx_align',           # cos(ΔX_{t-1→t}, ΔX_{t→t+1})  AR(1) baseline cosine
        'F_dx_align_C',           # cos(g_C·J_C, ΔX)  — C-channel only forecast
        'F_dx_align_G',           # cos(g_G·J_G, ΔX)  — G-channel only forecast
        'F_dx_align_A',           # cos(g_A·J_A, ΔX)  — A-channel only forecast (likely NaN)
        'F_dx_align_T',           # cos(g_T·J_T, ΔX)  — T-channel only forecast
        # §XVI Lyapunov bundle
        'P_t', 'Q_t', 'R_t', 'F_norm', 'X_norm', 'inner_GtF',
        'dV_dt', 'M_margin', 'theta_ceiling', 'gamma_min', 'gamma_star',
        # §XXV per-channel attribution
        'a_C', 'a_G', 'a_A', 'a_T',
        'eta_C', 'eta_G', 'eta_A', 'eta_T',
        'vdrift_C', 'vdrift_G', 'vdrift_A', 'vdrift_T',
        'vctrl_C',  'vctrl_G',  'vctrl_A',  'vctrl_T',
    ]
    buf = {c: np.full(T, np.nan, dtype=float) for c in cols}

    t0 = time.time()
    n_done = 0
    for t in range(max(start_idx, 1), T):
        try:
            snap = Snapshot(
                X=X[t],
                X_prev=X[t-1],
                history=X[max(0, t-history_len):t],
            )
            # MasterOperator.pipeline gives us rho/psi/MFLS/F in one call (with caching)
            pipe = M.pipeline(snap)
            buf['MFLS_ch'][t]   = float(pipe['MFLS_channel'])
            buf['MFLS_st'][t]   = float(pipe['MFLS_state'])
            buf['rho_MFLS'][t]  = float(pipe['rho_MFLS'])
            buf['psi'][t]       = float(pipe['psi'])
            buf['xi6'][t]       = float(pipe['xi6'])
            buf['cos_psi'][t]   = float(np.cos(pipe['psi']))
            buf['gamma_star'][t]= float(pipe['gamma_star'])
            F = pipe['F_t']
            buf['F_norm'][t]    = float(np.linalg.norm(F, 'fro'))
            buf['X_norm'][t]    = float(np.linalg.norm(X[t], 'fro'))
            # §VII paper-original bounded alignment (already in pipeline)
            buf['cos_theta'][t]    = float(pipe['cos_theta_state'])      # ∈ [-1, 1]
            buf['cos_theta_ch'][t] = float(pipe['cos_theta_channel_raw']) # diagnostic
            # §VI.5 paper-original MFLS = 2||X̃ Σ⁻¹||_F  (single scalar, MFLS_t in pipe)
            buf['MFLS_paper'][t]   = float(pipe['MFLS_t'])

            # Lyapunov bundle (margin/dV_dt/theta_ceiling/gamma_min/per-channel)
            # _bundle is cached on the snapshot, so subsequent calls are cheap.
            b = lyap._bundle(snap)                    # noqa: SLF001 (intentional reuse)
            buf['P_t'][t]          = float(b['Pt'])
            buf['Q_t'][t]          = float(b['Qt'])
            buf['R_t'][t]          = float(b['Rt'])
            buf['inner_GtF'][t]    = float(b['Pt'])    # alias: <G̃, F> = P_t
            buf['dV_dt'][t]        = float(lyap.dV_dt(snap))
            buf['M_margin'][t]     = float(lyap.margin(snap))
            buf['theta_ceiling'][t] = _safe(lyap.theta_ceiling(snap))
            buf['gamma_min'][t]    = _safe(lyap.gamma_min(snap))

            ch = lyap.channel_decomposition(snap)
            for k in ('C', 'G', 'A', 'T'):
                buf[f'a_{k}'][t]      = float(ch[k]['attribution'])
                buf[f'eta_{k}'][t]    = float(ch[k]['eta'])
                buf[f'vdrift_{k}'][t] = float(ch[k]['v_drift'])
                buf[f'vctrl_{k}'][t]  = float(ch[k]['v_control'])

            # §XXIV scale fix: ρ_normalised = ||G̃||_F / (sqrt(λ_max(Gram)) · ||g||)
            # This is the Rayleigh quotient of T*T = Gram, bounded by 1 — a true cosine
            # between g ∈ R⁴ and the top singular direction of T(g) = Σ_k g_k J_k.
            try:
                Js   = M.bsdt.jacobians_stacked(snap)              # (4, N, d)
                Gram = np.einsum('ind,jnd->ij', Js, Js)            # (4, 4)
                eigs = np.linalg.eigvalsh(Gram).clip(min=0.0)      # nonneg
                lam_max = float(eigs.max())
                buf['lambda_max_Gram'][t] = lam_max
                rho   = buf['rho_MFLS'][t]
                if lam_max > 1e-12 and rho == rho:                  # not NaN
                    buf['rho_normalised'][t] = float(rho / np.sqrt(lam_max))
                # Effective rank (participation ratio) of the BSDT Gram —
                # 1 ⇒ a single channel-direction dominates the manifold;
                # 4 ⇒ all four channels span equally-weighted modes.
                s1 = float(eigs.sum()); s2 = float((eigs**2).sum())
                if s2 > 1e-24:
                    buf['gram_eff_rank'][t] = (s1 * s1) / s2

                # ---- SCALE AUDIT: per-channel norms and CORRELATION Gram ----
                # If ||J_k||_F spans many orders of magnitude, the raw Gram
                # collapses to its largest diagonal entry and eff_rank → 1
                # by algebra alone (a scale artefact, NOT physics).
                # Fix: normalise each J_k by its Frobenius norm before forming
                # the Gram → produces a true 4×4 correlation matrix whose
                # eigenstructure reflects channel *geometry*, not magnitude.
                J_norms = np.sqrt(np.einsum('knd,knd->k', Js, Js))   # (4,)
                for ki, kn in enumerate(('C','G','A','T')):
                    buf[f'J_norm_{kn}'][t] = float(J_norms[ki])
                buf['dom_channel'][t] = int(np.argmax(J_norms))
                jmax = float(J_norms.max()); jmin = float(J_norms.min())
                if jmin > 1e-24:
                    buf['J_norm_spread'][t] = float(np.log10(jmax / jmin))

                # Correlation Gram: J̃_k = J_k / ||J_k||_F  (diag(GramC) = 1)
                safe = np.where(J_norms > 1e-18, J_norms, 1.0)
                Js_n = Js / safe[:, None, None]
                GramC = np.einsum('ind,jnd->ij', Js_n, Js_n)        # 4×4
                eigsC = np.linalg.eigvalsh(GramC).clip(min=0.0)
                lamC_max = float(eigsC.max())
                buf['lambda_max_GramCorr'][t] = lamC_max
                s1c = float(eigsC.sum()); s2c = float((eigsC**2).sum())
                if s2c > 1e-24:
                    buf['gram_corr_eff_rank'][t] = (s1c * s1c) / s2c

                # ρ in correlation basis: g'_k = g_k * ||J_k||_F
                # so T(g) = Σ g'_k J̃_k preserves the same map.
                try:
                    gvec = M.mfls.channel_gradient(snap)             # (4,)
                except Exception:
                    gvec = None
                if gvec is not None:
                    gp  = np.asarray(gvec, dtype=float) * J_norms
                    gpn = float(np.linalg.norm(gp))
                    Tg  = np.einsum('k,knd->nd', gp, Js_n)
                    if lamC_max > 1e-12 and gpn > 1e-18:
                        buf['rho_corr_normalised'][t] = float(
                            np.linalg.norm(Tg) / (np.sqrt(lamC_max) * gpn))
            except Exception:
                pass

            # Drift-vs-Control coherence — cosine of (vdrift, vctrl) ∈ R⁴.
            # +1 = control aligned with drift (engine surfs the flow);
            #  0 = orthogonal (control acts perpendicular to drift);
            # −1 = engine fights the drift (collapse-mode signal).
            try:
                vd = np.array([buf[f'vdrift_{k}'][t] for k in ('C','G','A','T')], dtype=float)
                vc = np.array([buf[f'vctrl_{k}'][t]  for k in ('C','G','A','T')], dtype=float)
                nd = float(np.linalg.norm(vd)); nc = float(np.linalg.norm(vc))
                if nd > 1e-18 and nc > 1e-18:
                    buf['drift_ctrl_coh'][t] = float(np.dot(vd, vc) / (nd * nc))
                # Per-channel sign disagreement — magnitude-free.  If raw
                # D ≡ −1 is a scale artefact this should NOT be 1.0.
                with np.errstate(invalid='ignore'):
                    sd = np.sign(vd); sc = np.sign(vc)
                    nz = (sd != 0) & (sc != 0)
                    if nz.any():
                        buf['drift_ctrl_disagree'][t] = float((sd[nz] != sc[nz]).mean())
                # Magnitude-free cosine: project each component to ±1 first.
                vd_z = np.sign(vd); vc_z = np.sign(vc)
                nzd = float(np.linalg.norm(vd_z)); nzc = float(np.linalg.norm(vc_z))
                if nzd > 1e-18 and nzc > 1e-18:
                    buf['drift_ctrl_coh_norm'][t] = float(
                        np.dot(vd_z, vc_z) / (nzd * nzc))
            except Exception:
                pass

            # ── ENGINE-INTRINSIC FORECAST SKILL ─────────────────────────
            # Measures whether the engine's STATE-SPACE force field F_t
            # actually predicts the realised next-bar state change ΔX_t,
            # independent of any trading abstraction (no gate, no sizing).
            # ΔX_t = X[t+1] − X[t].  Available at index t iff t+1 < T.
            try:
                if t + 1 < T:
                    dX = X[t+1] - X[t]                        # (N, d)
                    dx_n = float(np.linalg.norm(dX, 'fro'))
                    buf['dx_norm'][t] = dx_n
                    # The engine's state-space restoring force F_t is in pipe['F_t']
                    Fn = float(np.linalg.norm(F, 'fro'))
                    if Fn > 1e-18 and dx_n > 1e-18:
                        Fdx = float(np.einsum('nd,nd->', F, dX))
                        buf['F_dot_dx'][t]    = Fdx
                        buf['F_dx_align'][t]  = Fdx / (Fn * dx_n)
                    # u_state direction (G̃ / ||G̃||_F)
                    Gt = M.mfls.state_pullback(snap)            # (N, d)
                    Gn = float(np.linalg.norm(Gt, 'fro'))
                    if Gn > 1e-18 and dx_n > 1e-18:
                        Gdx = float(np.einsum('nd,nd->', Gt, dX))
                        buf['G_dx_align'][t] = Gdx / (Gn * dx_n)
                        # engine "gas pedal" — scalar engine signal
                        if Fn > 1e-18:
                            us = Gt / Gn
                            es = float(np.einsum('nd,nd->', F, us))
                            buf['engine_signal'][t]      = es
                            buf['engine_signal_norm'][t] = es / Fn
                    # Per-channel forecast: cos(g_k · J_k, ΔX)
                    if gvec is not None:
                        for ki, kn in enumerate(('C','G','A','T')):
                            comp = float(gvec[ki]) * Js[ki]      # (N, d)
                            cn = float(np.linalg.norm(comp, 'fro'))
                            if cn > 1e-18 and dx_n > 1e-18:
                                cdx = float(np.einsum('nd,nd->', comp, dX))
                                buf[f'F_dx_align_{kn}'][t] = cdx / (cn * dx_n)
                    # AR(1) baseline: cos(ΔX_{t-1→t}, ΔX_{t→t+1})
                    if t >= 1:
                        dXp = X[t] - X[t-1]
                        dpn = float(np.linalg.norm(dXp, 'fro'))
                        if dpn > 1e-18 and dx_n > 1e-18:
                            buf['ar1_dx_align'][t] = float(
                                np.einsum('nd,nd->', dXp, dX) / (dpn * dx_n))
            except Exception:
                pass
            n_done += 1
            if verbose and n_done % 500 == 0:
                rate = n_done / max(time.time() - t0, 1e-3)
                eta_s = (T - t) / max(rate, 1e-3)
                print(f'    diag bar {t}/{T}  rate={rate:.1f}/s  eta={eta_s:.0f}s', flush=True)
        except Exception as e:
            # Don't blow the loop on a single bad bar (e.g. degenerate covariance)
            if verbose and n_done < 5:
                print(f'    bar {t} skipped: {type(e).__name__}: {e}')

    df = pd.DataFrame(buf, index=df_1h.index)
    if use_cache:
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            df.to_pickle(str(cache_path))
            if verbose:
                print(f'  corrected_diagnostics cached -> {cache_path}')
        except Exception as e:
            print(f'    cache write failed: {e}')
    if verbose:
        print(f'  corrected_diagnostics built ({n_done} bars in {time.time()-t0:.1f}s)')
    return df


# ── §XXIX v58 production-spec dynamic θ_G law (B9 reference, inline) ──────────
# Source of truth: run_crypto_pairs_v58_stability_patch.py (_dynamic_gth)
# Locked formula, reproduced here for self-containment of the validator:
#     rv      = ret_eth.rolling(168).std()
#     rv_norm = (rv / rv.rolling(1000).mean()).ewm(span=3).mean().shift(1)
#     adj     = clip(0.10 * (1 - rv_norm), -0.01, +0.10)
#     gth(t)  = clip(0.45 * (1 + adj), 0.20, 0.70)
def v58_dynamic_gth(
    df_1h: pd.DataFrame,
    *,
    G_THRESH_BASE: float = 0.45,
    K_G: float = 0.10,
    ema_span: int = 3,
    lo: float = -0.01,
    hi: float = 0.10,
    floor: float = 0.20,
    ceil: float = 0.70,
) -> pd.Series:
    rv      = df_1h['ret_eth'].rolling(168, min_periods=24).std()
    rv_mean = rv.rolling(1000, min_periods=100).mean()
    rv_norm = (rv / rv_mean.replace(0, np.nan)).fillna(1.0)
    if ema_span > 1:
        rv_norm = rv_norm.ewm(span=ema_span, adjust=False).mean()
    rv_norm = rv_norm.shift(1).fillna(1.0)
    adj = (K_G * (1.0 - rv_norm)).clip(lo, hi)
    return (G_THRESH_BASE * (1.0 + adj)).clip(floor, ceil)
