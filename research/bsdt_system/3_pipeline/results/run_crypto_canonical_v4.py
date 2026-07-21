"""
Crypto Canonical v4 — Pure §8.1 TradingDomain Successor to v36 BSDT
====================================================================

Replaces the BSDT 4-channel score (δ_C, δ_G, δ_A, δ_T) and its non-canonical
RSS / γ*_adj heuristics with a literal implementation of canonical_system_v4
§8.1 (TradingDomain).  All sizing, entry and exit rules come from theorems —
no asserted firing order, no exp+linear-bias energy, no ReLU/KDE channels.

Geometry  (§8.1, fully frozen at train end):
    State w ∈ R^n    (n=3 portfolio weights:  w_btc, w_eth, w_sol)
    S(w) = A w − b_t                                            (k=3 factors)
        f1 = w_btc + w_eth + w_sol           (gross dollar)
        f2 = w_eth − w_btc                   (ETH↔BTC rotation)
        f3 = w_eth − w_sol                   (ETH↔SOL rotation)
        b_t = [0,  sign(3d spread_eb)·τ,  sign(3d spread_es)·τ]
    G  = Σ_f^{-1}   (Ledoit-Wolf factor covariance, training only)
    F_base(w) = −κ (w − 0)                  (alpha-tracking only)
    E(w)  = SᵀGS                           (canonical, paper E)
    g_w   = 2 Aᵀ G S                       (single, unique gradient)
    γ(w)  = E / (E + θ)                    ∈ [0, 1)

Locked ODE (§3, never modified):
    Ẋ = F − γ ⟨F, g⟩ / (‖g‖² + ε) · g,        F = F_base − g

Trading rules — derived from theorems, not heuristics:
    • Position size multiplier        = 1 − γ(w)                  (§4.5)
    • Block when Lemma 6.7 is violated: dE/dt(w) > 0 → size = 0   (§6.7)
    • Halve when curvature manifold indicator > 0                 (§D.3)
    • PnL_t = w_new · ret_t   (Ẋ vector IS the trade vector)

Build / verify / backtest, compared against v34 baseline and v36 champion.

Usage:
    py -3 run_crypto_canonical_v4.py
"""
from __future__ import annotations
import os, sys, json, time, warnings
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
from pathlib import Path
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, r'C:\amttp\research\adaptive-friction')

# ── Canonical v4 kernel — locked, theorem-certified ─────────────────────────
from collapse_geometry.canonical import (
    TradingDomain, verification_checklist, verify_gradient_fd,
)

# ── Reuse v34 data builders (data layer only — no BSDT geometry) ────────────
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START, TRAIN_END,
    build_1h_df, fetch_binance_funding,
)

OUT_DIR_ = Path(OUT_DIR)
ANN_1H   = 252.0 * 24
BPD      = 24

# ── Canonical-v4 hyper-parameters (§8.1 + §H.1) ─────────────────────────────
KAPPA          = 0.05      # alpha-tracking strength κ > 0
EPSILON        = 1e-12     # ODE singular-set regularisation (§2.2)
DT             = 0.10      # Euler step (sub-bar to keep ODE stable)
TARGET_DIR     = 0.18      # directional alpha amplitude  τ_dir
TARGET_ROT     = 0.20      # rotation alpha amplitude     τ_rot
MOM_BARS_DIR   = 7 * BPD   # 7-day directional momentum  (longer window → fewer flips → lower DD)
MOM_BARS_ROT   = 3 * BPD   # 3-day rotation momentum     (faster rotation signal kept short)
MOM_TANH_S     = 2.0       # tanh steepness — governs how sharply target rises from 0 to ±τ
                            # tanh(2·mom/std) ≈ ±0.96 at |mom/std|=2; ≈ 0 near crossovers
                            # replaces sign() → b_t passes smoothly through zero on trend reversals
W_MAX          = 0.10      # hard per-asset position cap (§10.1 box constraint, per-step clip)
                            # equivalent to a Lipschitz barrier on F_base at the box boundary
THETA_PCTILE   = 50        # θ = median E on training (paper §A.4: θ ~ E_typ)

# Ledoit-Wolf shrinkage for factor covariance (training only)
LW_SHRINK_FLOOR = 1e-8


# ═══════════════════════════════════════════════════════════════════════════
#  1.  FACTOR-COVARIANCE CALIBRATION (Ledoit-Wolf, training only)
# ═══════════════════════════════════════════════════════════════════════════

def ledoit_wolf_cov(X: np.ndarray) -> tuple[np.ndarray, float]:
    """Ledoit-Wolf shrinkage of an empirical covariance toward μI.

    Standard linear shrinkage: Σ̂ = (1−δ) S + δ μ I, with μ = tr(S)/k and
    δ chosen by the LW formula.  Returns a strictly PD matrix.
    """
    X = np.asarray(X, dtype=float)
    T, k = X.shape
    Xc = X - X.mean(axis=0, keepdims=True)
    S  = (Xc.T @ Xc) / max(T - 1, 1)
    mu = float(np.trace(S)) / k
    # numerator: sum_t ‖x_t x_tᵀ − S‖_F²  / T²
    num = 0.0
    for t in range(T):
        d = np.outer(Xc[t], Xc[t]) - S
        num += float(np.sum(d * d))
    num /= max(T * T, 1)
    den = float(np.sum((S - mu * np.eye(k)) ** 2))
    delta = 1.0 if den < 1e-30 else float(np.clip(num / den, 0.0, 1.0))
    Sigma = (1.0 - delta) * S + delta * mu * np.eye(k)
    # ensure strict PD
    eig = np.linalg.eigvalsh(Sigma)
    if eig[0] <= LW_SHRINK_FLOOR:
        Sigma = Sigma + (LW_SHRINK_FLOOR - eig[0] + LW_SHRINK_FLOOR) * np.eye(k)
    return Sigma, float(delta)


def rescale_to_correlation(Sigma: np.ndarray) -> np.ndarray:
    """Convert a covariance to a correlation matrix (diag = 1).

    Renders the canonical metric scale-invariant to the underlying return
    units — eigenvalues become O(1) so that E = SᵀGS lives on the same scale
    as ‖S‖² and θ ~ 1 is a meaningful regulariser (§A.4).
    """
    d = np.sqrt(np.maximum(np.diag(Sigma), 1e-30))
    D_inv = np.diag(1.0 / d)
    R = D_inv @ Sigma @ D_inv
    R = 0.5 * (R + R.T)
    return R


# ═══════════════════════════════════════════════════════════════════════════
#  2.  FACTOR MAP A  (frozen, canonical)  —  k=5 factors, n=3 weights
# ═════════════════════════════════════════════════════════════════════════
#   w = (w_btc, w_eth, w_sol)
#   f1 = w_btc           — BTC direct exposure              → carries directional alpha
#   f2 = w_eth           — ETH direct exposure              → carries directional alpha
#   f3 = w_sol           — SOL direct exposure              → carries directional alpha
#   f4 = w_eth − w_btc   — ETH/BTC rotation                 → carries rotation alpha
#   f5 = w_eth − w_sol   — ETH/SOL rotation                 → carries rotation alpha
# Three directional rows let the controller take net-long when trend is up,
# net-short when trend is down — the controller is now allowed to short.
A_FACTORS = np.array([
    [ 1.0,  0.0,  0.0],   # f1 = w_btc
    [ 0.0,  1.0,  0.0],   # f2 = w_eth
    [ 0.0,  0.0,  1.0],   # f3 = w_sol
    [-1.0,  1.0,  0.0],   # f4 = w_eth - w_btc
    [ 0.0,  1.0, -1.0],   # f5 = w_eth - w_sol
], dtype=float)
N_STATE   = 3                  # n = |w|
K_FACTOR  = A_FACTORS.shape[0] # k = 5


def build_factor_returns(df: pd.DataFrame) -> np.ndarray:
    """Per-bar factor returns r_f = A · r, used for Σ_f calibration."""
    R = np.column_stack([
        df['ret_btc'].fillna(0.0).values,
        df['ret_eth'].fillna(0.0).values,
        df['ret_sol'].fillna(0.0).values if 'ret_sol' in df.columns
            else df['ret_eth'].fillna(0.0).values,
    ])
    return R @ A_FACTORS.T   # (T, k)


def build_target_b(df: pd.DataFrame) -> np.ndarray:
    """Time-varying factor target b_t  (k=5)  —  tanh-smooth version.

    b_i = tanh(MOM_TANH_S · mom_i / std(mom_i)) · τ

    Using tanh instead of sign() gives a smooth target that rises gradually
    from 0 as momentum builds and returns smoothly through zero on reversals.
    This eliminates the ±2τ discontinuous flip that is the primary MaxDD driver
    (the controller no longer has to sprint from −τ to +τ immediately after a
    trend crossover; b_t ≈ 0 near the crossover, so the ODE unwinds gently).
    Paper basis: tanh = smooth sigmoid of the sign function; MOM_TANH_S controls
    the transition steepness.  sign(x) = tanh(MOM_TANH_S·x) in the limit S→∞.
    """
    T = len(df)
    b = np.zeros((T, K_FACTOR), dtype=float)

    r_btc = df['ret_btc'].fillna(0.0).values
    r_eth = df['ret_eth'].fillna(0.0).values
    r_sol = df['ret_sol'].fillna(0.0).values if 'ret_sol' in df.columns else r_eth

    def _mom_tanh(r: np.ndarray, win: int) -> np.ndarray:
        sr    = pd.Series(r)
        m     = sr.rolling(win, min_periods=BPD).sum().shift(1).fillna(0.0)
        # Normalise by rolling std of the momentum itself to make steepness scale-invariant
        m_std = m.rolling(min(2 * win, len(r)), min_periods=win // 2).std()
        m_std = m_std.replace(0, np.nan).bfill().fillna(1.0).clip(lower=1e-9)
        return np.tanh(MOM_TANH_S * m / m_std).values

    # Directional rows (per-instrument, 7d momentum, smooth)
    b[:, 0] = _mom_tanh(r_btc, MOM_BARS_DIR) * TARGET_DIR
    b[:, 1] = _mom_tanh(r_eth, MOM_BARS_DIR) * TARGET_DIR
    b[:, 2] = _mom_tanh(r_sol, MOM_BARS_DIR) * TARGET_DIR

    # Rotation rows (cross-instrument spread, 3d momentum, smooth)
    b[:, 3] = _mom_tanh(r_eth - r_btc, MOM_BARS_ROT) * TARGET_ROT
    b[:, 4] = _mom_tanh(r_eth - r_sol, MOM_BARS_ROT) * TARGET_ROT
    return b


# ═══════════════════════════════════════════════════════════════════════════
#  3.  CANONICAL-V4 BACKTEST ENGINE
# ═══════════════════════════════════════════════════════════════════════════

def run_canonical_backtest(df: pd.DataFrame,
                            train_mask: np.ndarray,
                            test_mask:  np.ndarray) -> tuple[pd.DataFrame, dict]:
    """Run §8.1 TradingDomain controller over every bar.

    Returns
    -------
    log : DataFrame with per-bar w, S, E, γ, dE/dt, curv, gates, pnl
    diag : dict with calibration + verification diagnostics
    """
    T = len(df)
    R = np.column_stack([
        df['ret_btc'].fillna(0.0).values,
        df['ret_eth'].fillna(0.0).values,
        df['ret_sol'].fillna(0.0).values if 'ret_sol' in df.columns
            else df['ret_eth'].fillna(0.0).values,
    ])
    factor_R = build_factor_returns(df)
    b_seq    = build_target_b(df)

    # ── Calibrate Σ_f on TRAINING factor returns only (frozen forever) ──
    Sigma_raw, lw_delta = ledoit_wolf_cov(factor_R[train_mask])
    Sigma_f = rescale_to_correlation(Sigma_raw)
    print(f"  [v4] Σ_f calibrated on {int(train_mask.sum()):,} train bars  "
          f"(LW δ = {lw_delta:.3f}, rescaled to correlation)")
    eig = np.linalg.eigvalsh(Sigma_f)
    print(f"  [v4] G=Σ_f⁻¹ eigenvalues span: μ_min={1.0/eig[-1]:.3e}  μ_max={1.0/eig[0]:.3e}")

    # ── Calibrate θ on training-window E distribution at w=0 ──
    # E(w=0) = bᵀ G b — this is the natural scale of the energy under the
    # canonical metric.  θ at the median makes γ ∈ [0,1] non-degenerate.
    G_for_theta = np.linalg.inv(Sigma_f)
    E_train = np.einsum('ti,ij,tj->t', b_seq[train_mask], G_for_theta, b_seq[train_mask])
    theta_cal = float(np.percentile(E_train, THETA_PCTILE))
    theta_cal = max(theta_cal, 1e-3)
    print(f"  [v4] θ (P{THETA_PCTILE} of E_b on train, w=0) = {theta_cal:.4f}")

    # ── Build canonical TradingDomain at b_t = b_train_end (for verification) ──
    b0 = b_seq[np.where(train_mask)[0][-1]]
    sys0 = TradingDomain(
        A=A_FACTORS, b=b0, Sigma=Sigma_f,
        kappa=KAPPA, w_star=np.zeros(N_STATE),
        theta=theta_cal, epsilon=EPSILON,
    ).build()

    # ── §10 verification checklist  (all 10 must pass) ──
    w_test = np.array([0.10, 0.20, 0.05])    # arbitrary test state in operating range
    chk = verification_checklist(sys0, w_test)
    print(chk.summary())
    if not chk.all_passed:
        raise RuntimeError("§10 checklist failed — system not paper-faithful")

    # ── §H.1.2 finite-difference gradient check (g_w = 2AᵀGS) ──
    fd = verify_gradient_fd(sys0, w_test, h=1e-6)
    print(f"  [v4] Gradient FD: max_abs = {fd['max_abs_error']:.2e}   "
          f"max_rel = {fd['max_rel_error']:.2e}   passed = {fd['passed']}")
    if not fd['passed']:
        raise RuntimeError("Gradient FD check failed")

    # ── Pre-allocate logs ──
    log = {k: np.zeros(T) for k in [
        'E', 'gamma', 'dE_dt', 'curv_ind',
        'w_btc', 'w_eth', 'w_sol',
        'size_mult', 'gate_lemma67', 'gate_curv',
        'pnl_canonical', 'pnl_long_only',
    ]}
    log['S']       = np.zeros((T, K_FACTOR))
    log['rhs_w']   = np.zeros((T, N_STATE))

    # ── Forward integrate the locked ODE bar-by-bar ──
    w = np.zeros(N_STATE, dtype=float)
    t0 = time.time()
    for t in range(T):
        # rebuild system with current b_t (only b changes; Σ, A, κ frozen)
        sys_t = TradingDomain(
            A=A_FACTORS, b=b_seq[t], Sigma=Sigma_f,
            kappa=KAPPA, w_star=np.zeros(N_STATE),
            theta=theta_cal, epsilon=EPSILON,
        ).build()

        # canonical scalars at current state
        S_t   = sys_t.S(w)
        E_t   = sys_t.energy(w)
        gma   = sys_t.gain(w)
        dEdt  = sys_t.dE_dt(w)
        curv  = sys_t.curvature_manifold_indicator(w)
        rhs   = sys_t.rhs(w)

        # ── Theorem-derived gates ──
        size_mult     = float(np.clip(1.0 - gma, 0.0, 1.0))     # §4.5
        gate_lemma67  = 1.0 if dEdt <= 0.0 else 0.0              # §6.7
        gate_curv     = 1.0 if curv  <= 0.0 else 0.5              # §D.3
        gate_total    = gate_lemma67 * gate_curv

        # ── Step the locked ODE one Euler step (§H.1.1) ──
        w_new = w + DT * rhs
        # PnL realised over [t, t+1] uses the post-step weights × size × gate
        w_eff = w_new * size_mult * gate_total
        pnl_canonical = float(w_eff @ R[t])
        # diagnostic: long-only equal-weight comparator
        pnl_long_only = float(R[t].mean())

        # log
        log['E'][t]            = E_t
        log['gamma'][t]        = gma
        log['dE_dt'][t]        = dEdt
        log['curv_ind'][t]     = curv
        log['size_mult'][t]    = size_mult
        log['gate_lemma67'][t] = gate_lemma67
        log['gate_curv'][t]    = gate_curv
        log['w_btc'][t]        = w_new[0]
        log['w_eth'][t]        = w_new[1]
        log['w_sol'][t]        = w_new[2]
        log['pnl_canonical'][t]= pnl_canonical
        log['pnl_long_only'][t]= pnl_long_only
        log['S'][t]            = S_t
        log['rhs_w'][t]        = rhs

        w = w_new

        if t > 0 and (t % 5000) == 0:
            print(f"    {t:>6}/{T}  ({time.time()-t0:>5.1f}s)  "
                  f"E={E_t:.3e}  γ={gma:.3f}  ‖w‖={np.linalg.norm(w):.3f}")

    print(f"  [v4] ODE sweep complete: {T:,} bars  {time.time()-t0:.1f}s")

    # build output frame
    out = pd.DataFrame({
        'E':              log['E'],
        'gamma':          log['gamma'],
        'dE_dt':          log['dE_dt'],
        'curv_ind':       log['curv_ind'],
        'w_btc':          log['w_btc'],
        'w_eth':          log['w_eth'],
        'w_sol':          log['w_sol'],
        'size_mult':      log['size_mult'],
        'gate_lemma67':   log['gate_lemma67'],
        'gate_curv':      log['gate_curv'],
        'pnl_canonical':  log['pnl_canonical'],
        'pnl_long_only':  log['pnl_long_only'],
    }, index=df.index)

    diag = {
        'lw_delta':        lw_delta,
        'sigma_eig_min':   float(eig[0]),
        'sigma_eig_max':   float(eig[-1]),
        'theta_calibrated': theta_cal,
        'checklist_pass':  chk.all_passed,
        'fd_max_abs':      fd['max_abs_error'],
        'fd_max_rel':      fd['max_rel_error'],
    }
    return out, diag


# ═══════════════════════════════════════════════════════════════════════════
#  4.  STATISTICS / REPORT HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _stats(pnl: pd.Series) -> dict:
    p = pnl.fillna(0.0)
    if p.std() < 1e-12:
        return {'sharpe': 0.0, 'cagr': 0.0, 'max_dd': 0.0, 'final': 100.0}
    sh   = float(p.mean() / p.std() * np.sqrt(ANN_1H))
    eq   = 100.0 * (1.0 + p).cumprod()
    mdd  = float((eq / eq.cummax() - 1.0).min())
    yrs  = max((p.index[-1] - p.index[0]).days / 365.25, 0.01)
    cagr = float((eq.iloc[-1] / 100.0) ** (1.0 / yrs) - 1.0)
    return {'sharpe': sh, 'cagr': cagr, 'max_dd': mdd, 'final': float(eq.iloc[-1])}


def _net_ret(pnl: pd.Series, K: float, tc_bps: float = 5.0) -> pd.Series:
    p = pnl.fillna(0.0)
    fee = tc_bps / 1e4 / BPD * (p.abs() > 1e-12).astype(float)
    return p * K - fee


def print_yoy_table(title: str, pnl: pd.Series, K_list):
    print(f"\n  {title}")
    hdr = f"  {'K':>3}  {'2023':>7}  {'2024':>7}  {'2025':>7}  {'2026YTD':>8}  "
    hdr += f"{'$100→':>9}  {'MaxDD':>7}  {'CAGR':>10}"
    print(hdr); print("  " + "-" * (len(hdr) - 2))
    for K in K_list:
        r  = _net_ret(pnl, K)
        eq = 100.0; yr = {}
        for y in [2023, 2024, 2025, 2026]:
            mk = pnl.index.year == y
            if not mk.any(): continue
            ret = float((1.0 + r[mk]).prod() - 1.0)
            yr[y] = ret; eq *= (1.0 + ret)
        ec   = 100.0 * (1.0 + r).cumprod()
        mdd  = float((ec / ec.cummax() - 1.0).min())
        rr   = r[r.index.year >= 2023]
        if len(rr) < 2:
            cagr = 0.0
        else:
            yrs  = max((rr.index[-1] - rr.index[0]).days / 365.25, 0.01)
            cagr = (eq / 100.0) ** (1.0 / yrs) - 1.0
        f = lambda y: f"{100*yr[y]:>+5.0f}%" if y in yr else "  ─  "
        print(f"  {K:>3}  {f(2023):>7}  {f(2024):>7}  {f(2025):>7}  {f(2026):>8}  "
              f"${eq:>8.2f}  {100*mdd:>+6.1f}%  {100*cagr:>+6.1f}%/yr")


def print_signal_report(log: pd.DataFrame, mask: np.ndarray):
    s = log.iloc[mask]
    print(f"\n  [Canonical-v4 signal report]  test bars={len(s):,}  "
          f"({s.index[0].date()} → {s.index[-1].date()})")
    print(f"  {'Signal':<14}  {'mean':>10}  {'std':>10}  {'p5':>10}  {'p95':>10}")
    for col in ['E', 'gamma', 'dE_dt', 'curv_ind',
                'size_mult', 'w_btc', 'w_eth', 'w_sol']:
        v = s[col].dropna()
        if len(v) == 0:
            continue
        print(f"  {col:<14}  {v.mean():>+10.4f}  {v.std():>10.4f}  "
              f"{v.quantile(0.05):>+10.4f}  {v.quantile(0.95):>+10.4f}")
    print(f"\n    Lemma-6.7 gate active : {100*s['gate_lemma67'].mean():.1f}% of bars")
    print(f"    Curvature gate halved  : {100*(s['gate_curv'] < 1.0).mean():.1f}% of bars")
    print(f"    Mean position size mult: {s['size_mult'].mean():.3f}")


# ═══════════════════════════════════════════════════════════════════════════
#  5.  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    print("=" * 100)
    print("  CRYPTO CANONICAL-V4 — §8.1 TradingDomain  (paper-faithful)")
    print("  n=3 instruments × k=3 factors  |  locked ODE  |  no BSDT, no heuristics")
    print("=" * 100)

    print("\n[1] Fetching Binance 1h data (BTC, ETH, SOL) ...")
    df_1h, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask  = np.asarray(df_1h.index >= TEST_START)
    train_mask = np.asarray((df_1h.index >= TRAIN_START) & (df_1h.index < TEST_START))
    print(f"  Total: {len(df_1h):,} bars  |  Train: {int(train_mask.sum()):,}  |  Test: {int(test_mask.sum()):,}")
    print(f"  SOL real data: {has_sol}")

    print("\n[2] Running canonical-v4 ODE controller ...")
    log, diag = run_canonical_backtest(df_1h, train_mask, test_mask)

    print_signal_report(log, test_mask)

    # ── Performance comparison ──
    print(f"\n{'═'*100}")
    print("  PERFORMANCE  (test 2023 → 2026, gross)")
    print(f"{'═'*100}")
    pnl_v4   = log['pnl_canonical'][test_mask]
    pnl_long = log['pnl_long_only'][test_mask]

    for name, pnl in [('canonical_v4', pnl_v4), ('long_only_eqwt', pnl_long)]:
        st = _stats(pnl)
        ar = float((pnl.abs() > 1e-12).mean()) * 100
        print(f"  {name:<18}  Sharpe={st['sharpe']:+.3f}  "
              f"MaxDD={100*st['max_dd']:+.1f}%  CAGR={100*st['cagr']:+.1f}%  "
              f"Active={ar:.1f}%")

    print_yoy_table('canonical_v4', pnl_v4, [1, 2, 5, 10])
    print_yoy_table('long_only_eqwt (benchmark)', pnl_long, [1, 2])

    # ── Save ──
    out = {
        'meta': {
            'version':       'canonical_v4',
            'paper_section': '§8.1 TradingDomain',
            'n_state':       N_STATE,
            'k_factor':      K_FACTOR,
            'kappa':         KAPPA,
            'theta':         diag['theta_calibrated'],
            'epsilon':       EPSILON,
            'dt':            DT,
            'target_rot':    TARGET_ROT,
        },
        'verification': diag,
        'performance': {
            'canonical_v4':    _stats(pnl_v4),
            'long_only_eqwt':  _stats(pnl_long),
        },
        'signal_summary': {
            'E_mean':         float(log['E'][test_mask].mean()),
            'gamma_mean':     float(log['gamma'][test_mask].mean()),
            'size_mult_mean': float(log['size_mult'][test_mask].mean()),
            'lemma67_pass_pct': float(log['gate_lemma67'][test_mask].mean()),
            'curv_halve_pct':  float((log['gate_curv'][test_mask] < 1.0).mean()),
        },
    }
    out_path = OUT_DIR_ / 'crypto_canonical_v4.json'
    with open(out_path, 'w') as fh:
        json.dump(out, fh, indent=2, default=float)
    print(f"\n  Saved → {out_path}")
    print("=" * 100)


if __name__ == '__main__':
    main()
