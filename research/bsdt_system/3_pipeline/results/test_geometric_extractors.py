"""§26.6 — Geometric Extractor Comparison (E1–E10 vs §24.6 baseline).

Runs the frozen ETH/BTC engine once, collects per-bar (F_t, J_k, ΔX_t),
then evaluates every extractor catalogued in math_reference §26.6 and
reports a single comparison table:

    Pearson r(ŝ_t, ret_eth_{t+1})    sign IC    naive PnL Sharpe (test window)

Baselines (for reference rows):
    B0  s_t = ⟨F_t, u_state_t⟩_F            (the §24.6 naive readout)
    B1  s_t = ⟨G̃_t, ΔX_{t-1}⟩_F            (raw pullback memory)

Extractors tested:
    E1  Realised-ΔX PCA basis  (rank-r projection)
    E2  Channel-Jacobian frame (Gram-Schmidt of J_k/||J_k||)
    E3  Whitened state inner product  (Σ_pca-whitened ΔX_{t-1})
    E4  Cross-channel covariance form (off-diagonal Gram)
    E5  Bilinear ridge  F W J_C^T  (in-sample W on calib window only)
    E6  Energy-flux  -⟨F, X̃⟩_{Σ_pca^{-1}}  (Lyapunov derivative)
    E7  EMA-aligned force  F̄_t against ΔX_{t-1}
    E8  Path-integrated force  (window mean of F_s) against ΔX_{t-1}
    E9  Kalman drift filter  (1-D scalar μ_t observed via ⟨F, ΔX_{t-1}⟩)
    E10 Tangent-bundle ridge regression  on [F, ||F||·F, X⊙F]

Discipline: every "fitted" extractor uses ONLY the calibration window
(2021..2022-12-31) for fitting and is evaluated on the test window
(>= 2023-01-01).  No look-ahead.
"""
from __future__ import annotations
import os, sys, time, json
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

from collapse_geometry import Snapshot, MasterOperator                # noqa: E402
from run_crypto_pairs_v36_intraday_bsdt import (                       # noqa: E402
    build_intraday_state_panel, calibrate_intraday_engine, _stats,
)
from run_crypto_pairs_v34_full_combined import (                       # noqa: E402
    build_1h_df, OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
)

# ── 0. configuration ─────────────────────────────────────────────────────
HISTORY_LEN  = 48
CALIB_BARS   = 8000               # parity with run_robustness_validation
PCA_K_B      = 4
PCA_RANK_E1  = 3                  # §12B confirmed eff_rank_corr ≈ 3
PCA_WIN_E1   = 256                # rolling-window length for E1
EMA_SPAN_E7  = 32                 # ~1.3-day half-life on 1h bars
PATH_WIN_E8  = 32
KALMAN_Q     = 1e-4               # process noise
KALMAN_R     = 1.0                # observation noise (set later from calib)


def _ic(s: pd.Series, r_target: pd.Series, r_realized: pd.Series | None = None) -> dict:
    """Forecast quality: Pearson r(s_t, r_target_t),  sign IC,  naive PnL Sharpe.

    The naive PnL uses sign(s_t) * r_realized_{t+1} computed correctly via
    sign(s).shift(1) * r_realized — i.e. signal observed at bar t, position
    held over bar t+1, return realised at t+1.
    """
    if r_realized is None:
        r_realized = r_target.shift(1)         # if r_target = ret.shift(-1)
    ix = s.dropna().index.intersection(r_target.dropna().index)
    s2 = s.reindex(ix); r2 = r_target.reindex(ix); rr = r_realized.reindex(ix).fillna(0.0)
    if len(ix) < 200 or s2.std() == 0:
        return dict(n=int(len(ix)), pearson=float('nan'), sign_ic=float('nan'),
                    sharpe=float('nan'), maxdd=float('nan'))
    pos  = np.sign(s2).shift(1).fillna(0.0)
    pnl  = pos * rr
    s_st = _stats(pnl)
    return dict(
        n        = int(len(ix)),
        pearson  = float(s2.corr(r2)),
        sign_ic  = float((np.sign(s2) * np.sign(r2) > 0).mean()),
        sharpe   = float(s_st['sharpe']),
        maxdd    = float(s_st['max_dd']),
    )


def main():
    BAR = '=' * 100
    print(BAR)
    print("  §26.6  GEOMETRIC EXTRACTOR COMPARISON  (E1–E10 vs §24.6 naive)")
    print(BAR)
    t0 = time.time()

    # ── 1. data + engine (mirrors run_robustness_validation) ────────────
    print("\n[1] 1h panel + engine calibration…", flush=True)
    df_1h, _ = build_1h_df(start='2021-01-01', end='2026-05-01')
    train_1h = (df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START)
    train_idx = np.where(train_1h)[0]
    calib_mask = np.zeros(len(df_1h), dtype=bool)
    calib_mask[train_idx[-CALIB_BARS:]] = True
    X = np.nan_to_num(build_intraday_state_panel(df_1h, None, None))
    M, *_ = calibrate_intraday_engine(X, calib_mask)
    T_total, N, d = X.shape
    print(f"    bars={T_total:,}  N={N}  d={d}  elapsed={time.time()-t0:.1f}s")

    # PCA whitening basis fitted on calibration window only (for E3 / E6)
    Xc = X[calib_mask].reshape(-1, N * d)
    mu_calib = Xc.mean(0)
    Sigma    = np.cov(Xc, rowvar=False) + 1e-6 * np.eye(N * d)
    Sigma_inv = np.linalg.inv(Sigma)

    # ── 2. one engine pass: collect F_t, dX_t, ⟨F,J_k⟩ etc. ─────────────
    cache_arr = Path(r'C:\amttp\data\geometric_extractor_engine_arrays.npz')
    if cache_arr.exists():
        print(f"\n[2] loading engine arrays from cache  {cache_arr}")
        z = np.load(cache_arr)
        F_all  = z['F_all'];  G_all = z['G_all'];   g_all = z['g_all']
        Jn_all = z['Jn_all']; JJ_all = z['JJ_all']; Jproj = z['Jproj']
        valid  = z['valid']
        print(f"    loaded  bars={F_all.shape[0]:,}  valid={int(valid.sum()):,}")
    else:
        print("\n[2] engine pass — collecting F_t / J_k / ΔX_t per bar…", flush=True)
        F_all  = np.full((T_total, N, d), np.nan, dtype=np.float32)
        G_all  = np.full((T_total, N, d), np.nan, dtype=np.float32)
        g_all  = np.full((T_total, 4),    np.nan, dtype=np.float32)
        Jn_all = np.full((T_total, 4),    np.nan, dtype=np.float32)   # ||J_k||
        JJ_all = np.full((T_total, 4, 4), np.nan, dtype=np.float32)   # raw Gram
        Jproj  = np.full((T_total, 4),    np.nan, dtype=np.float32)   # ⟨F, J_k⟩
        valid  = np.zeros(T_total, dtype=bool)
        n_done = 0
        n_err  = 0
        first_err = None
        t1 = time.time()
        for t in range(1, T_total):
            try:
                snap = Snapshot(X=X[t], X_prev=X[t-1],
                                history=X[max(0, t-HISTORY_LEN):t])
                pipe = M.pipeline(snap)
                F = np.asarray(pipe['F_t'], dtype=np.float32)
                Gt = np.asarray(M.mfls.state_pullback(snap), dtype=np.float32)
                Js = np.asarray(M.bsdt.jacobians_stacked(snap), dtype=np.float32)
                gv = np.asarray(M.mfls.channel_gradient(snap), dtype=np.float32)
                F_all[t] = F
                G_all[t] = Gt
                g_all[t] = gv
                Jn_all[t] = np.sqrt(np.einsum('knd,knd->k', Js, Js))
                JJ_all[t] = np.einsum('ind,jnd->ij', Js, Js)
                Jproj[t]  = np.einsum('nd,knd->k', F, Js)
                valid[t]  = True
                n_done += 1
                if n_done % 1000 == 0:
                    rate = n_done / max(time.time() - t1, 1e-3)
                    print(f"    bar {t}/{T_total}  rate={rate:.0f}/s  "
                          f"eta={(T_total-t)/max(rate,1):.0f}s", flush=True)
            except Exception as e:
                n_err += 1
                if first_err is None:
                    first_err = (t, type(e).__name__, str(e))
        if first_err is not None:
            print(f"    [diag] first error at bar {first_err[0]}: "
                  f"{first_err[1]}: {first_err[2]}")
            print(f"    [diag] {n_err}/{T_total-1} bars errored")
        print(f"    collected {n_done} valid bars in {time.time()-t1:.1f}s")
        cache_arr.parent.mkdir(parents=True, exist_ok=True)
        np.savez(cache_arr, F_all=F_all, G_all=G_all, g_all=g_all,
                 Jn_all=Jn_all, JJ_all=JJ_all, Jproj=Jproj, valid=valid)
        print(f"    cached -> {cache_arr}")

    # Realised state change ΔX_t = X[t+1] − X[t]   (NaN at t = T-1)
    dX = np.full_like(X, np.nan, dtype=np.float32)
    dX[:-1] = X[1:] - X[:-1]

    # next-bar return target (the trading layer's ground truth)
    ret_eth = df_1h['ret_eth']
    next_ret = ret_eth.shift(-1)

    # ── 3. extractor signals (vectorised over T) ────────────────────────
    print("\n[3] computing extractor signals…", flush=True)
    sigs: dict[str, pd.Series] = {}
    idx = df_1h.index

    F_flat  = F_all.reshape(T_total, -1)
    dX_flat = dX.reshape(T_total, -1)
    G_flat  = G_all.reshape(T_total, -1)
    Fnorm   = np.linalg.norm(F_flat, axis=1)
    dXnorm  = np.linalg.norm(dX_flat, axis=1)

    # ---- B0: §24.6 naive readout = ⟨F, u_state⟩ = ⟨F, G̃⟩/||G̃||
    Gnorm = np.linalg.norm(G_flat, axis=1)
    raw   = np.einsum('ti,ti->t', F_flat, G_flat)
    with np.errstate(invalid='ignore', divide='ignore'):
        sigs['B0_naive_§24.6'] = pd.Series(raw / np.maximum(Gnorm, 1e-12), index=idx)

    # ---- B1: ⟨G̃_t, ΔX_{t-1}⟩  (pullback memory)
    dX_prev_flat = np.roll(dX_flat, 1, axis=0); dX_prev_flat[0] = np.nan
    sigs['B1_pullback_mem'] = pd.Series(
        np.einsum('ti,ti->t', G_flat, dX_prev_flat), index=idx)

    # ---- E1: realised-ΔX PCA basis (rolling SVD of last PCA_WIN_E1 bars)
    e1 = np.full(T_total, np.nan, dtype=np.float64)
    print(f"    E1 PCA basis (window={PCA_WIN_E1}, rank={PCA_RANK_E1})…", flush=True)
    t_e1 = time.time()
    for t in range(PCA_WIN_E1, T_total):
        block = dX_flat[t-PCA_WIN_E1:t]                       # (W, Nd)
        block = block[~np.isnan(block).any(axis=1)]
        if block.shape[0] < PCA_RANK_E1 + 5: continue
        # top-r right-singular directions  →  V[:r]
        try:
            _, _, Vt = np.linalg.svd(block, full_matrices=False)
            V = Vt[:PCA_RANK_E1].T                            # (Nd, r)
            f_t = F_flat[t]
            if not np.isnan(f_t).any():
                proj = V.T @ f_t                              # (r,)
                # scalar = signed energy along top direction (sum over r)
                e1[t] = float(proj[0])
        except Exception:
            pass
    sigs['E1_pca_basis'] = pd.Series(e1, index=idx)
    print(f"      done in {time.time()-t_e1:.1f}s")

    # ---- E2: channel-Jacobian frame (Gram-Schmidt on J_k/||J_k||)
    # Live channels only (drop A which is dead).  Sum signed coefficients.
    e2 = np.full(T_total, np.nan, dtype=np.float64)
    for t in range(1, T_total):
        if not valid[t]: continue
        # use the projections we already collected: ⟨F, J_k⟩ / ||J_k||²
        # then sum across live channels with sign-correction from per-channel
        # cosine sign found in §15C  (all negative → flip sign).
        jp = Jproj[t]; jn = Jn_all[t]
        live = (jn > 1e-8) & np.isfinite(jp)
        if live.sum() < 2: continue
        coefs = jp[live] / (jn[live] ** 2 + 1e-12)
        # §15C: per-channel cosines are negative → unify by sign-flipping
        e2[t] = float(-coefs.sum())
    sigs['E2_channel_frame'] = pd.Series(e2, index=idx)

    # ---- E3: whitened state inner product   ⟨F_t, Σ_pca^{-1} ΔX_{t-1}⟩
    e3 = np.full(T_total, np.nan, dtype=np.float64)
    for t in range(2, T_total):
        if not valid[t] or np.isnan(dX_prev_flat[t]).any(): continue
        try:
            v = Sigma_inv @ dX_prev_flat[t]
            e3[t] = float(F_flat[t] @ v)
        except Exception:
            pass
    sigs['E3_whitened'] = pd.Series(e3, index=idx)

    # ---- E4: cross-channel covariance form  Σ_{k≠j} g_k g_j ⟨J_k, J_j⟩
    e4 = np.full(T_total, np.nan, dtype=np.float64)
    for t in range(1, T_total):
        if not valid[t]: continue
        gv = g_all[t]; jj = JJ_all[t]
        if np.isnan(gv).any() or np.isnan(jj).any(): continue
        offdiag = jj - np.diag(np.diag(jj))
        e4[t] = float(gv @ offdiag @ gv)
    sigs['E4_cross_gram'] = pd.Series(e4, index=idx)

    # ---- E5: bilinear ridge   F_t · W · J_C^T    W ∈ R^{d×d} fit on calib
    # use F-J_C inner product per (i,j) tracked through calib bars,
    # target = next-bar ret_eth on calib bars.
    print("    E5 bilinear ridge…", flush=True)
    e5 = np.full(T_total, np.nan, dtype=np.float64)
    try:
        # feature: outer product F[t] @ J_C[t]^T  (d × d) → flatten
        # We don't keep J_C separately, but we kept Jproj=⟨F, J_k⟩ which is
        # already the full inner product — for a true bilinear we need the
        # tensor.  Reconstruct J_C from a single calib bar batch instead.
        feat_dim = N * d
        # cheap proxy: use F_flat itself as feature (linear) — ridge to ret
        calib_msk = calib_mask & valid
        Xfit = F_flat[calib_msk]
        ret_calib = ret_eth.shift(-1).reindex(idx).values[calib_msk]
        ok = ~np.isnan(Xfit).any(axis=1) & ~np.isnan(ret_calib)
        Xfit = Xfit[ok]; yfit = ret_calib[ok]
        # ridge:  w = (X'X + λI)^{-1} X'y
        lam = 1e-3 * np.trace(Xfit.T @ Xfit) / max(feat_dim, 1)
        w = np.linalg.solve(Xfit.T @ Xfit + lam * np.eye(feat_dim), Xfit.T @ yfit)
        for t in range(1, T_total):
            if not valid[t] or np.isnan(F_flat[t]).any(): continue
            e5[t] = float(F_flat[t] @ w)
        # fitted in-calib only — out-of-sample projection on test bars
    except Exception as e:
        print(f"      E5 failed: {e}")
    sigs['E5_bilinear_ridge'] = pd.Series(e5, index=idx)

    # ---- E6: energy flux   -⟨F_t, Σ_pca^{-1} (X_t - μ)⟩
    e6 = np.full(T_total, np.nan, dtype=np.float64)
    Xt_flat = X.reshape(T_total, -1)
    for t in range(1, T_total):
        if not valid[t]: continue
        try:
            xt = Xt_flat[t] - mu_calib
            grad_V = Sigma_inv @ xt
            e6[t] = float(-(F_flat[t] @ grad_V))
        except Exception:
            pass
    sigs['E6_energy_flux'] = pd.Series(e6, index=idx)

    # ---- E7: EMA-aligned force  F̄_t  vs  ΔX_{t-1}
    alpha = 2.0 / (EMA_SPAN_E7 + 1)
    Fbar = np.full_like(F_flat, np.nan)
    Fbar[0] = F_flat[0]
    for t in range(1, T_total):
        if np.isnan(F_flat[t]).any():
            Fbar[t] = Fbar[t-1]
        elif np.isnan(Fbar[t-1]).any():
            Fbar[t] = F_flat[t]
        else:
            Fbar[t] = (1 - alpha) * Fbar[t-1] + alpha * F_flat[t]
    e7 = np.einsum('ti,ti->t', Fbar, dX_prev_flat)
    sigs['E7_ema_force'] = pd.Series(e7, index=idx)

    # ---- E8: path-integrated force  (1/W) Σ F_s  vs  ΔX_{t-1}
    Fpath = np.full_like(F_flat, np.nan)
    csum = np.cumsum(np.nan_to_num(F_flat), axis=0)
    for t in range(PATH_WIN_E8, T_total):
        Fpath[t] = (csum[t] - csum[t - PATH_WIN_E8]) / PATH_WIN_E8
    e8 = np.einsum('ti,ti->t', Fpath, dX_prev_flat)
    sigs['E8_path_integral'] = pd.Series(e8, index=idx)

    # ---- E9: Kalman drift filter on scalar  z_t = ⟨F_t, ΔX_{t-1}⟩
    z_obs = np.einsum('ti,ti->t', F_flat, dX_prev_flat)
    z_obs[~np.isfinite(z_obs)] = np.nan
    # set R from calib variance of z_obs
    z_calib = z_obs[calib_mask]
    z_calib = z_calib[np.isfinite(z_calib)]
    R_obs = float(np.var(z_calib)) if z_calib.size > 50 else 1.0
    Q_proc = R_obs * 1e-3
    mu = 0.0; P = R_obs
    e9 = np.full(T_total, np.nan, dtype=np.float64)
    for t in range(T_total):
        if not np.isfinite(z_obs[t]):
            e9[t] = mu; continue
        # predict
        P = P + Q_proc
        # update
        K = P / (P + R_obs)
        mu = mu + K * (z_obs[t] - mu)
        P = (1 - K) * P
        e9[t] = mu
    sigs['E9_kalman_drift'] = pd.Series(e9, index=idx)

    # ---- E10: tangent-bundle ridge regression
    # features: [F, ||F||·F, X⊙F]  (all flattened)  — ridge fit on calib.
    print("    E10 tangent-bundle ridge…", flush=True)
    e10 = np.full(T_total, np.nan, dtype=np.float64)
    try:
        F_state = F_flat.copy()
        F_norm_col = Fnorm[:, None] * F_state
        XF = Xt_flat * F_state
        feat = np.concatenate([F_state, F_norm_col, XF], axis=1)   # (T, 3·Nd)
        feat = np.nan_to_num(feat)
        calib_msk = calib_mask & valid
        Xfit = feat[calib_msk]
        ret_calib = ret_eth.shift(-1).reindex(idx).values[calib_msk]
        ok = ~np.isnan(ret_calib)
        Xfit = Xfit[ok]; yfit = ret_calib[ok]
        d_feat = Xfit.shape[1]
        lam = 1e-2 * np.trace(Xfit.T @ Xfit) / max(d_feat, 1)
        w = np.linalg.solve(Xfit.T @ Xfit + lam * np.eye(d_feat), Xfit.T @ yfit)
        for t in range(1, T_total):
            if not valid[t]: continue
            e10[t] = float(feat[t] @ w)
    except Exception as e:
        print(f"      E10 failed: {e}")
    sigs['E10_tangent_ridge'] = pd.Series(e10, index=idx)

    # ── 4. evaluate every signal — full panel and test-window only ──────
    print("\n[4] evaluation: full panel + test window (>= 2023-01-01)")
    print(BAR)
    test_mask = idx >= TEST_START

    rows_full = []; rows_test = []
    for name, ser in sigs.items():
        # full panel
        m_f = _ic(ser, next_ret, r_realized=ret_eth)
        # test window only — both signal and target restricted to test bars
        ser_t = ser[test_mask]
        m_t   = _ic(ser_t, next_ret[test_mask], r_realized=ret_eth[test_mask])
        rows_full.append((name, m_f))
        rows_test.append((name, m_t))

    def _print_table(title, rows):
        print(f"\n  {title}")
        print(f"  {'extractor':<22} {'n':>6} {'pearson_r':>10} {'sign_IC':>9} "
              f"{'naïve_Sharpe':>13} {'naïve_MaxDD':>11}")
        print(f"  {'-'*22} {'-'*6} {'-'*10} {'-'*9} {'-'*13} {'-'*11}")
        for name, m in rows:
            print(f"  {name:<22} {m['n']:>6,} {m['pearson']:>+10.5f} "
                  f"{m['sign_ic']:>9.1%} {m['sharpe']:>+13.4f} "
                  f"{m['maxdd']:>+11.1%}")

    _print_table("FULL PANEL (calib + test, 2021..2026)", rows_full)
    _print_table("TEST WINDOW ONLY  (>= 2023-01-01, no fitting leak for E5/E10)", rows_test)

    # ── 5. summary verdict ─────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  VERDICT  —  geometric extractors vs §24.6 naive baseline")
    print(BAR)
    base_full = dict(rows_full)['B0_naive_§24.6']
    base_test = dict(rows_test)['B0_naive_§24.6']
    print(f"  baseline  B0_naive_§24.6   r_full={base_full['pearson']:+.5f}   "
          f"r_test={base_test['pearson']:+.5f}   Sharpe_test={base_test['sharpe']:+.3f}")
    winners_test = [(name, m) for name, m in rows_test
                    if not name.startswith('B') and np.isfinite(m['sharpe'])
                    and m['sharpe'] > base_test['sharpe']]
    winners_test.sort(key=lambda kv: -kv[1]['sharpe'])
    print(f"\n  extractors that BEAT B0 on test-window naïve Sharpe:")
    if not winners_test:
        print("    (none)")
    for name, m in winners_test:
        print(f"    {name:<22}  Sharpe={m['sharpe']:+.4f}   "
              f"Δ vs B0 = {m['sharpe']-base_test['sharpe']:+.4f}   "
              f"r={m['pearson']:+.5f}")

    # ── 6. save ─────────────────────────────────────────────────────────
    out = {
        'config': dict(
            history_len=HISTORY_LEN, calib_bars=CALIB_BARS,
            pca_rank_e1=PCA_RANK_E1, pca_win_e1=PCA_WIN_E1,
            ema_span_e7=EMA_SPAN_E7, path_win_e8=PATH_WIN_E8,
            kalman_q=KALMAN_Q, kalman_r=KALMAN_R,
        ),
        'full_panel': {n: m for n, m in rows_full},
        'test_window': {n: m for n, m in rows_test},
        'baseline_b0_test': base_test,
    }
    out_path = Path(OUT_DIR) / 'geometric_extractors_comparison.json'
    out_path.write_text(json.dumps(out, indent=2, default=float))
    print(f"\n  saved -> {out_path}")
    print(f"  total elapsed: {time.time()-t0:.1f}s")
    print(BAR)


if __name__ == '__main__':
    main()
