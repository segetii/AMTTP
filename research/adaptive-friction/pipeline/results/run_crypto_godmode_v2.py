"""
Crypto Godmode v2 — All Leaks Fixed
=====================================
Builds on v1 best (v_anneal, Sharpe=1.807, CAGR=+46.9%, $100→$358.83).

Seven targeted improvements, each isolated and then combined:

  F1  flags      — activate stop/stale geometry flags to gate ODE step
                   (were computed but IGNORED in v1 — capital bled on bad bars)
  F2  peak15     — shift ANNEAL_PEAK 12→15 UTC  (BTC actual peak volume window)
  F3  nofloor    — remove CONV_MIN=0.20 floor  (allow genuine zero on flat bars)
  F4  multiwin   — composite momentum 30%×1d + 50%×7d + 20%×30d  (richer signal)
  F5  rollsig    — rolling 90-day Ledoit-Wolf Σ updated every 7 days
                   (v1 Sigma was calibrated once on 2020-2022, then frozen)
  F6  adaptk     — adaptive κ(E): κ ∈ [0.05, 0.25] via tanh(E / E_med_train)
                   (restores aggressively when far from manifold, gently near it)
  F7  wbox       — W_BOX sweep: 0.50 (v1), 0.75, 1.00
                   (hard position cap is the primary exposure limiter)

Variants (9 strategy variants + 2 baselines):
  v_ann_v1       exact replica of v1 best (reference)
  v_ann_peak15   +F2
  v_ann_flags    +F1+F3  (flags gate + no conv_min floor)
  v_ann_multiwin +F4
  v_ann_rollsig  +F5
  v_ann_adaptk   +F6
  v_ann_wbox75   +F7(0.75)
  v_ann_wbox100  +F7(1.00)
  v_ann_all      +F1+F2+F3+F4+F5+F6+F7(1.00)  — everything combined
  v60            old champion baseline
  long_only      equal-weight benchmark
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

from collapse_geometry.canonical import (
    TradingDomain, verification_checklist, verify_gradient_fd,
)
from run_crypto_canonical_v4 import (
    A_FACTORS, N_STATE, K_FACTOR,
    EPSILON, DT, THETA_PCTILE,
    LW_SHRINK_FLOOR,
    ledoit_wolf_cov, rescale_to_correlation,
    _stats, _net_ret, print_yoy_table,
)
from run_crypto_canonical_v58_v60 import (
    print_dollar_simulation,
    run_canonical_sweep as _run_v4_sweep,
    overlay_v60,
)
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START,
    build_1h_df,
)

OUT_DIR_ = Path(OUT_DIR)
ANN_1H   = 252.0 * 24
BPD      = 24

# ═══════════════════════════════════════════════════════════════════════════
#  V2 HYPER-PARAMETERS
# ═══════════════════════════════════════════════════════════════════════════

KAPPA_A          = 0.15        # base κ (same as v1)
W_TARGET         = 0.30        # per-asset momentum amplitude
W_BOX_V1         = 0.50        # v1 position cap
W_BOX_75         = 0.75        # F7 medium
W_BOX_100        = 1.00        # F7 maximum

TANH_S           = 2.0
CONV_MAX         = 1.00
CONV_MIN_V1      = 0.20        # v1 floor
CONV_MIN_V2      = 0.00        # F3 no-floor

# v_anneal θ-schedule
ANNEAL_AMP       = 0.50
ANNEAL_PEAK_V1   = 12          # UTC hour θ is narrowest (v1)
ANNEAL_PEAK_V2   = 15          # UTC hour θ is narrowest (F2 — actual BTC peak)

# Multi-window composite weights (must sum to 1.0)  [F4]
MW_W1D  = 0.30
MW_W7D  = 0.50
MW_W30D = 0.20
MOM_WIN_1D  = 1  * BPD
MOM_WIN_7D  = 7  * BPD
MOM_WIN_30D = 30 * BPD

# Adaptive κ range  [F6]
KAPPA_ADAPT_MIN = 0.05
KAPPA_ADAPT_MAX = 0.25

# Rolling Sigma schedule  [F5]
SIGMA_ROLL_WIN_DAYS    = 90
SIGMA_ROLL_UPDATE_DAYS = 7


# ═══════════════════════════════════════════════════════════════════════════
#  SIGNAL BUILDERS
# ═══════════════════════════════════════════════════════════════════════════

def _tanh_signal(r: np.ndarray, win: int, tanh_s: float = TANH_S) -> np.ndarray:
    """Smooth tanh-momentum signal ∈ (-1, +1). Causal (shift-1)."""
    sr    = pd.Series(r)
    m     = sr.rolling(win, min_periods=BPD).sum().shift(1).fillna(0.0)
    m_std = m.rolling(min(2 * win, len(r)), min_periods=win // 2).std()
    m_std = m_std.replace(0, np.nan).bfill().fillna(1.0).clip(lower=1e-9)
    return np.tanh(tanh_s * m / m_std).values


def _three_col(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    r_btc = df['ret_btc'].fillna(0.0).values
    r_eth = df['ret_eth'].fillna(0.0).values
    r_sol = df['ret_sol'].fillna(0.0).values if 'ret_sol' in df.columns else r_eth
    return r_btc, r_eth, r_sol


def build_w_star_7d(df: pd.DataFrame, W_TARGET: float = W_TARGET) -> np.ndarray:
    """Single 7-day momentum w_star (T×3) — identical to v1."""
    r_btc, r_eth, r_sol = _three_col(df)
    return np.column_stack([
        _tanh_signal(r_btc, MOM_WIN_7D),
        _tanh_signal(r_eth, MOM_WIN_7D),
        _tanh_signal(r_sol, MOM_WIN_7D),
    ]) * W_TARGET


def build_w_star_composite(df: pd.DataFrame, W_TARGET: float = W_TARGET) -> np.ndarray:
    """Multi-window composite: 30%×1d + 50%×7d + 20%×30d  [F4]."""
    r_btc, r_eth, r_sol = _three_col(df)

    def composite(r: np.ndarray) -> np.ndarray:
        s1  = _tanh_signal(r, MOM_WIN_1D)
        s7  = _tanh_signal(r, MOM_WIN_7D)
        s30 = _tanh_signal(r, MOM_WIN_30D)
        return MW_W1D * s1 + MW_W7D * s7 + MW_W30D * s30

    return np.column_stack([composite(r_btc), composite(r_eth), composite(r_sol)]) * W_TARGET


def build_b_aligned(w_star_arr: np.ndarray) -> np.ndarray:
    """b_t = A_FACTORS @ w_star_t  → E=0 at momentum target. (T×5)"""
    return w_star_arr @ A_FACTORS.T


# ═══════════════════════════════════════════════════════════════════════════
#  ROLLING SIGMA SCHEDULE  [F5]
# ═══════════════════════════════════════════════════════════════════════════

def build_sigma_schedule(
    df: pd.DataFrame,
    initial_sigma: np.ndarray,
    win_days: int = SIGMA_ROLL_WIN_DAYS,
    update_days: int = SIGMA_ROLL_UPDATE_DAYS,
) -> list[tuple[int, np.ndarray]]:
    """Build list of (t_start, Sigma_f) for rolling Ledoit-Wolf updates.

    Each entry means: use this Sigma from bar t_start onward until the next
    entry.  The list is sorted by t_start.  Entry 0 covers bars 0→first_update.

    Parameters
    ----------
    initial_sigma : Sigma_f from training calibration (covers bars 0→first_window)
    win_days : look-back window in days
    update_days : recompute interval in days
    """
    from run_crypto_canonical_v4 import build_factor_returns
    factor_R = build_factor_returns(df)
    T    = len(df)
    win  = win_days  * BPD
    step = update_days * BPD

    schedule = [(0, initial_sigma)]
    skipped  = 0

    for t in range(win, T, step):
        window_R = factor_R[max(0, t - win): t]
        if len(window_R) < 100:
            skipped += 1
            continue
        try:
            Sigma_raw, _ = ledoit_wolf_cov(window_R)
            Sigma_f      = rescale_to_correlation(Sigma_raw)
            np.linalg.cholesky(Sigma_f)    # PD guard
            schedule.append((t, Sigma_f))
        except np.linalg.LinAlgError:
            skipped += 1

    schedule.sort(key=lambda x: x[0])
    print(f"  [rolling Σ] {len(schedule)} updates  "
          f"({win_days}d window, every {update_days}d)  {skipped} skipped")
    return schedule


# ═══════════════════════════════════════════════════════════════════════════
#  CALIBRATION
# ═══════════════════════════════════════════════════════════════════════════

def calibrate(
    df: pd.DataFrame,
    train_mask: np.ndarray,
    w_star_arr: np.ndarray,
    b_arr: np.ndarray,
    kappa: float = KAPPA_A,
    label: str = '',
) -> tuple[np.ndarray, float, float, dict]:
    """Returns (Sigma_f, theta, E_median_train, diag).

    E_median_train is now returned for adaptive-κ scaling in the sweep.
    §10 verification and FD gradient check are enforced.
    """
    from run_crypto_canonical_v4 import build_factor_returns
    factor_R   = build_factor_returns(df)
    Sigma_raw, lw_delta = ledoit_wolf_cov(factor_R[train_mask])
    Sigma_f    = rescale_to_correlation(Sigma_raw)
    G_cal      = np.linalg.inv(Sigma_f)

    b_train    = b_arr[train_mask]
    E_train    = np.einsum('ti,ij,tj->t', b_train, G_cal, b_train)
    theta_cal  = max(float(np.percentile(E_train, THETA_PCTILE)), 1e-3)
    E_median   = max(float(np.median(E_train)), 1e-6)

    if label:
        print(f"  [{label}] LW δ={lw_delta:.3f}  θ(P{THETA_PCTILE})={theta_cal:.4f}  "
              f"E_med={E_median:.4f}")

    # §10 verification at last training point
    idx_rep = np.where(train_mask)[0][-1]
    b_rep   = b_arr[idx_rep]
    ws_rep  = w_star_arr[idx_rep]
    sys0    = TradingDomain(A=A_FACTORS, b=b_rep, Sigma=Sigma_f,
                            kappa=kappa, w_star=ws_rep,
                            theta=theta_cal, epsilon=EPSILON).build()
    chk     = verification_checklist(sys0, np.array([0.10, 0.15, 0.05]))
    print(chk.summary())
    if not chk.all_passed:
        raise RuntimeError(f"§10 checklist failed for [{label}]")
    fd      = verify_gradient_fd(sys0, np.array([0.10, 0.15, 0.05]), h=1e-6)
    print(f"  [{label}] FD: max_abs={fd['max_abs_error']:.2e}  passed={fd['passed']}")

    diag = {'lw_delta': lw_delta, 'theta': theta_cal, 'E_median': E_median,
            'checklist': chk.all_passed, 'fd_max_abs': fd['max_abs_error']}
    return Sigma_f, theta_cal, E_median, diag


# ═══════════════════════════════════════════════════════════════════════════
#  PREDICTIVE SCALARS (identical to v1)
# ═══════════════════════════════════════════════════════════════════════════

def _predictive_scalars(sys_t, w: np.ndarray) -> dict:
    """Compute the §10 five-scalar dashboard for one bar."""
    gw     = sys_t.gradient(w)
    Fb     = np.asarray(sys_t.F_base(w), dtype=float)
    E_t    = sys_t.energy(w)
    gma    = sys_t.gain(w)
    dEdt   = sys_t.dE_dt(w)
    rhs    = sys_t.rhs(w)
    Fb_n   = float(np.linalg.norm(Fb))
    gw_n   = float(np.linalg.norm(gw))
    denom  = Fb_n * gw_n
    cos_th = float(Fb @ gw) / denom if denom > 1e-12 else 0.0
    v_E    = -dEdt
    rho_ef = v_E / max(E_t, 1e-9)
    return dict(E=E_t, gamma=gma, dE_dt=dEdt, rhs=rhs, gw=gw,
                cos_theta=cos_th, mfls=gw_n, v_E=v_E, rho_eff=rho_ef,
                rhs_norm=float(np.linalg.norm(rhs)))


# ═══════════════════════════════════════════════════════════════════════════
#  UNIFIED V2 SWEEP
# ═══════════════════════════════════════════════════════════════════════════

def run_v2_sweep(
    df: pd.DataFrame,
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    w_star_arr: np.ndarray,
    b_arr: np.ndarray,
    Sigma_f: np.ndarray,
    theta_base: float,
    E_median_train: float,
    sigma_schedule: list | None = None,   # None = fixed Sigma_f  [F5]
    kappa: float = KAPPA_A,
    W_box: float = W_BOX_V1,
    anneal: bool = True,
    anneal_peak: int = ANNEAL_PEAK_V1,
    use_flags: bool = False,               # [F1] gate ODE with stop/stale flags
    conv_min: float = CONV_MIN_V1,         # [F3] 0.0 = no floor
    adapt_kappa: bool = False,             # [F6] κ = f(E_lag)
    label: str = '',
) -> pd.DataFrame:
    """
    Unified v2 sweep.  All feature toggles are explicit keyword args.

    Feature mapping:
      sigma_schedule != None         → F5 rolling Sigma
      use_flags=True                 → F1 stop/stale gate
      conv_min=0.0                   → F3 no-floor conviction
      adapt_kappa=True               → F6 adaptive κ
      anneal_peak=15                 → F2 correct UTC peak
      W_box > 0.50                   → F7 expanded position cap
      w_star_arr = composite signal  → F4 multi-window (caller sets this)

    Flag semantics (F1):
      stop_flag  = γ > 0.90  → trajectory nearly tangent to manifold → gate=0
      stale_flag = ρ_eff < 0.10 × ρ_typ_train → force effectively dead → gate=0
      gate = (1 - stop_flag) * (1 - stale_flag)
      w_new = w + DT * rhs * conviction * gate

    Adaptive κ (F6):
      kappa_t = KAPPA_ADAPT_MIN + (KAPPA_ADAPT_MAX - KAPPA_ADAPT_MIN)
                × tanh(E_lag / E_median_train)
      Aggressive when far from manifold (large E), gentle when near it (small E).
    """
    T = len(df)
    R = np.column_stack([
        df['ret_btc'].fillna(0.0).values,
        df['ret_eth'].fillna(0.0).values,
        df['ret_sol'].fillna(0.0).values if 'ret_sol' in df.columns
            else df['ret_eth'].fillna(0.0).values,
    ])

    # Rolling sigma state
    if sigma_schedule is not None and len(sigma_schedule) > 0:
        sig_sched = sigma_schedule
        sig_idx   = 0
        Sigma_cur = sig_sched[0][1]
        use_rolling = True
    else:
        Sigma_cur   = Sigma_f
        sig_sched   = []
        sig_idx     = 0
        use_rolling = False

    # Calibrate rho_typ on training set for stale alarm  (subsample for speed)
    rho_train = []
    for t in np.where(train_mask)[0][::50]:
        try:
            sys_t = TradingDomain(
                A=A_FACTORS, b=b_arr[t], Sigma=Sigma_cur,
                kappa=kappa, w_star=w_star_arr[t],
                theta=theta_base, epsilon=EPSILON,
            ).build()
            sc = _predictive_scalars(sys_t, np.zeros(N_STATE))
            if sc['rho_eff'] > 0:
                rho_train.append(sc['rho_eff'])
        except Exception:
            pass
    rho_typ = float(np.median(rho_train)) if rho_train else 1.0

    hours = df.index.hour if anneal else None

    keys = ['E', 'gamma', 'dE_dt', 'cos_theta', 'mfls', 'v_E', 'rho_eff',
            'rhs_norm', 'w_btc', 'w_eth', 'w_sol', 'pnl', 'pnl_long_only',
            'stop_flag', 'stale_flag', 'drift_flag', 'conviction', 'theta_t',
            'kappa_t', 'gate']
    log = {k: np.zeros(T) for k in keys}

    w           = np.zeros(N_STATE, dtype=float)
    cos_th_prev = 0.0
    E_lag       = 0.0        # for adaptive κ
    t0          = time.time()

    for t in range(T):

        # [F5] Advance rolling Sigma if a new window is available
        if use_rolling:
            while (sig_idx + 1 < len(sig_sched)
                   and sig_sched[sig_idx + 1][0] <= t):
                sig_idx += 1
                Sigma_cur = sig_sched[sig_idx][1]

        # [F6] Adaptive κ from previous bar's energy
        if adapt_kappa:
            kappa_t = (KAPPA_ADAPT_MIN
                       + (KAPPA_ADAPT_MAX - KAPPA_ADAPT_MIN)
                       * np.tanh(E_lag / E_median_train))
        else:
            kappa_t = kappa

        # [F2] Per-bar θ: annealed with configurable peak
        if anneal:
            hr = int(hours[t])
            theta_t = theta_base * (
                1.0 + ANNEAL_AMP * np.cos(2.0 * np.pi * (hr - anneal_peak) / 24.0)
            )
        else:
            theta_t = theta_base

        sys_t = TradingDomain(
            A=A_FACTORS, b=b_arr[t], Sigma=Sigma_cur,
            kappa=kappa_t, w_star=w_star_arr[t],
            theta=theta_t, epsilon=EPSILON,
        ).build()

        sc = _predictive_scalars(sys_t, w)

        # [F3] Conviction: no floor when conv_min=0.0
        conviction = float(np.clip(-cos_th_prev, conv_min, CONV_MAX))

        # Regime flags — evaluated at current position w
        stop_flag  = 1.0 if sc['gamma'] > 0.90 else 0.0
        stale_flag = 1.0 if (sc['rho_eff'] > 0
                              and sc['rho_eff'] < 0.1 * rho_typ) else 0.0
        drift_flag = 1.0 if sc['cos_theta'] > 0.0 else 0.0

        # [F1] Gate ODE step with flags (v1: gate=1 always)
        if use_flags:
            gate = (1.0 - stop_flag) * (1.0 - stale_flag)
        else:
            gate = 1.0

        # ODE step
        w_new = w + DT * sc['rhs'] * conviction * gate
        w_new = np.clip(w_new, -W_box, W_box)

        log['E'][t]           = sc['E']
        log['gamma'][t]       = sc['gamma']
        log['dE_dt'][t]       = sc['dE_dt']
        log['cos_theta'][t]   = sc['cos_theta']
        log['mfls'][t]        = sc['mfls']
        log['v_E'][t]         = sc['v_E']
        log['rho_eff'][t]     = sc['rho_eff']
        log['rhs_norm'][t]    = sc['rhs_norm']
        log['w_btc'][t]       = w_new[0]
        log['w_eth'][t]       = w_new[1]
        log['w_sol'][t]       = w_new[2]
        log['pnl'][t]         = float(w_new @ R[t])
        log['pnl_long_only'][t] = float(R[t].mean())
        log['stop_flag'][t]   = stop_flag
        log['stale_flag'][t]  = stale_flag
        log['drift_flag'][t]  = drift_flag
        log['conviction'][t]  = conviction
        log['theta_t'][t]     = theta_t
        log['kappa_t'][t]     = kappa_t
        log['gate'][t]        = gate

        w           = w_new
        cos_th_prev = sc['cos_theta']
        E_lag       = sc['E']

        if t > 0 and (t % 5000) == 0:
            print(f"    [{label}] {t:>6}/{T}  ({time.time()-t0:>5.1f}s)")

    print(f"  [{label}] sweep done: {T:,} bars  {time.time()-t0:.1f}s")
    return pd.DataFrame(log, index=df.index)


# ═══════════════════════════════════════════════════════════════════════════
#  REPORTING HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def print_alignment_check(logs: dict, test_mask: np.ndarray):
    print(f"\n  {'Alignment Check — % bars with cos θ ≤ 0   (target ≥ 90%)'}")
    print(f"  {'─'*58}")
    for name, lg in logs.items():
        if 'cos_theta' not in lg.columns:
            continue
        s   = lg.iloc[test_mask]
        pct = 100.0 * (s['cos_theta'] <= 0.0).mean()
        tag = '' if pct >= 90.0 else '  ← MISALIGNED'
        print(f"  {name:<22}  {pct:>6.1f}%{tag}")


def print_strategy_table(strategies: dict, mask: np.ndarray):
    print(f"\n  {'Strategy':<22}  {'Sharpe':>8}  {'MaxDD':>8}  {'CAGR':>9}  "
          f"{'Active%':>8}  {'$100→':>9}")
    print(f"  {'─'*82}")
    for name, pnl in strategies.items():
        p  = pnl.iloc[mask]
        st = _stats(p)
        ar = float((p.abs() > 1e-12).mean()) * 100
        print(f"  {name:<22}  {st['sharpe']:>+8.3f}  {100*st['max_dd']:>+7.1f}%  "
              f"{100*st['cagr']:>+8.1f}%  {ar:>7.1f}%  ${st['final']:>7.2f}")


def print_flag_diagnostics(logs: dict, test_mask: np.ndarray):
    print(f"\n  {'─'*90}")
    print("  REGIME DIAGNOSTICS (test window)  — stop% stale% drift% gated% κ_mean")
    print(f"  {'─'*90}")
    for name, lg in logs.items():
        s = lg.iloc[test_mask]
        stop_pct  = 100.0 * s['stop_flag'].mean()
        stale_pct = 100.0 * s['stale_flag'].mean()
        drift_pct = 100.0 * s['drift_flag'].mean()
        gated_pct = 100.0 * (s['gate'] < 1.0).mean() if 'gate' in s.columns else 0.0
        kap_mean  = s['kappa_t'].mean() if 'kappa_t' in s.columns else KAPPA_A
        conv_mean = s['conviction'].mean() if 'conviction' in s.columns else float('nan')
        print(f"  {name:<22}  stop={stop_pct:>5.1f}%  stale={stale_pct:>5.1f}%  "
              f"drift={drift_pct:>5.1f}%  gated={gated_pct:>5.1f}%  "
              f"κ={kap_mean:.3f}  conv={conv_mean:.3f}")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    SEP = "=" * 100

    print(SEP)
    print("  CRYPTO GODMODE v2 — All Leaks Fixed")
    print("  F1=flags  F2=peak15  F3=nofloor  F4=multiwin  F5=rollsig  F6=adaptk  F7=wbox")
    print(SEP)

    # ── [1] Data ──────────────────────────────────────────────────────────
    print("\n[1] Fetching Binance 1h OHLCV ...")
    df, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask  = np.asarray(df.index >= TEST_START)
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    T          = len(df)
    print(f"  Bars: {T:,}   Train: {train_mask.sum():,}   "
          f"Test: {test_mask.sum():,}   SOL: {has_sol}")

    # ── [2] Signal arrays ────────────────────────────────────────────────
    print("\n[2] Building momentum signals ...")
    w_star_7d   = build_w_star_7d(df, W_TARGET=W_TARGET)          # (T, 3) — v1 style
    w_star_comp = build_w_star_composite(df, W_TARGET=W_TARGET)    # (T, 3) — multiwin
    b_7d        = build_b_aligned(w_star_7d)                       # (T, 5)
    b_comp      = build_b_aligned(w_star_comp)                     # (T, 5)
    print(f"  7d    signal range: [{w_star_7d.min():.3f}, {w_star_7d.max():.3f}]")
    print(f"  comp  signal range: [{w_star_comp.min():.3f}, {w_star_comp.max():.3f}]")
    print(f"  MW weights: 1d={MW_W1D}  7d={MW_W7D}  30d={MW_W30D}")

    # ── [3] Calibration ──────────────────────────────────────────────────
    print("\n[3] Calibrating (7d signal — main) ...")
    Sigma_f, theta, E_med, diag = calibrate(
        df, train_mask, w_star_7d, b_7d, kappa=KAPPA_A, label='7d')

    print("\n[3b] Calibrating (composite signal) ...")
    Sigma_fc, theta_c, E_med_c, diag_c = calibrate(
        df, train_mask, w_star_comp, b_comp, kappa=KAPPA_A, label='comp')

    # ── [4] Rolling Sigma schedules ──────────────────────────────────────
    print("\n[4] Building rolling Σ schedules ...")
    sigma_sched   = build_sigma_schedule(df, initial_sigma=Sigma_f)
    sigma_sched_c = build_sigma_schedule(df, initial_sigma=Sigma_fc)

    # ── [5] Sweeps ────────────────────────────────────────────────────────
    print("\n[5] Running v2 sweeps ...")

    # Common kwargs for the 7d-signal variants — v1-exact defaults
    base_kw = dict(
        Sigma_f=Sigma_f, theta_base=theta, E_median_train=E_med,
        kappa=KAPPA_A, W_box=W_BOX_V1, anneal=True,
        anneal_peak=ANNEAL_PEAK_V1, use_flags=False,
        conv_min=CONV_MIN_V1, adapt_kappa=False,
    )

    print("\n  ── v_ann_v1  (v1 anneal exact replica, ANNEAL_PEAK=12) ──")
    log_v1 = run_v2_sweep(
        df, train_mask, test_mask, w_star_7d, b_7d, label='ann_v1', **base_kw)

    print("\n  ── v_ann_peak15  (+F2: ANNEAL_PEAK 12→15 UTC) ──")
    log_p15 = run_v2_sweep(
        df, train_mask, test_mask, w_star_7d, b_7d, label='ann_peak15',
        **{**base_kw, 'anneal_peak': ANNEAL_PEAK_V2})

    print("\n  ── v_ann_flags  (+F1+F3: geometry gates active, conv_min=0) ──")
    log_flags = run_v2_sweep(
        df, train_mask, test_mask, w_star_7d, b_7d, label='ann_flags',
        **{**base_kw, 'use_flags': True, 'conv_min': CONV_MIN_V2})

    print("\n  ── v_ann_multiwin  (+F4: composite 30%×1d+50%×7d+20%×30d) ──")
    log_mw = run_v2_sweep(
        df, train_mask, test_mask, w_star_comp, b_comp, label='ann_multiwin',
        Sigma_f=Sigma_fc, theta_base=theta_c, E_median_train=E_med_c,
        kappa=KAPPA_A, W_box=W_BOX_V1, anneal=True,
        anneal_peak=ANNEAL_PEAK_V1, use_flags=False,
        conv_min=CONV_MIN_V1, adapt_kappa=False)

    print("\n  ── v_ann_rollsig  (+F5: rolling 90d Σ, updated weekly) ──")
    log_rs = run_v2_sweep(
        df, train_mask, test_mask, w_star_7d, b_7d, label='ann_rollsig',
        **{**base_kw, 'sigma_schedule': sigma_sched})

    print("\n  ── v_ann_adaptk  (+F6: κ ∈ [0.05,0.25] via tanh(E/E_med)) ──")
    log_ak = run_v2_sweep(
        df, train_mask, test_mask, w_star_7d, b_7d, label='ann_adaptk',
        **{**base_kw, 'adapt_kappa': True})

    print("\n  ── v_ann_wbox75  (+F7: W_BOX=0.75) ──")
    log_w75 = run_v2_sweep(
        df, train_mask, test_mask, w_star_7d, b_7d, label='ann_wbox75',
        **{**base_kw, 'W_box': W_BOX_75})

    print("\n  ── v_ann_wbox100  (+F7: W_BOX=1.00) ──")
    log_w100 = run_v2_sweep(
        df, train_mask, test_mask, w_star_7d, b_7d, label='ann_wbox100',
        **{**base_kw, 'W_box': W_BOX_100})

    print("\n  ── v_ann_all  (F1+F2+F3+F4+F5+F6+F7, W_BOX=1.00) ──")
    log_all = run_v2_sweep(
        df, train_mask, test_mask, w_star_comp, b_comp, label='ann_all',
        sigma_schedule=sigma_sched_c,
        Sigma_f=Sigma_fc, theta_base=theta_c, E_median_train=E_med_c,
        kappa=KAPPA_A, W_box=W_BOX_100, anneal=True,
        anneal_peak=ANNEAL_PEAK_V2, use_flags=True,
        conv_min=CONV_MIN_V2, adapt_kappa=True)

    # ── [6] Baselines ─────────────────────────────────────────────────────
    print("\n[6] Baselines (v60, long_only) ...")
    log_base, _ = _run_v4_sweep(df, train_mask, test_mask)
    pnl_v60     = overlay_v60(log_base, train_mask)
    pnl_long    = log_base['pnl_long_only']

    # ── [7] Assemble ──────────────────────────────────────────────────────
    strategies = {
        'v_ann_v1':       log_v1['pnl'],
        'v_ann_peak15':   log_p15['pnl'],
        'v_ann_flags':    log_flags['pnl'],
        'v_ann_multiwin': log_mw['pnl'],
        'v_ann_rollsig':  log_rs['pnl'],
        'v_ann_adaptk':   log_ak['pnl'],
        'v_ann_wbox75':   log_w75['pnl'],
        'v_ann_wbox100':  log_w100['pnl'],
        'v_ann_all':      log_all['pnl'],
        'v60':            pnl_v60,
        'long_only':      pnl_long,
    }

    logs_dict = {
        'v_ann_v1':       log_v1,
        'v_ann_peak15':   log_p15,
        'v_ann_flags':    log_flags,
        'v_ann_multiwin': log_mw,
        'v_ann_rollsig':  log_rs,
        'v_ann_adaptk':   log_ak,
        'v_ann_wbox75':   log_w75,
        'v_ann_wbox100':  log_w100,
        'v_ann_all':      log_all,
    }

    # ── [8] Performance table ─────────────────────────────────────────────
    print(f"\n{'═'*100}")
    print("  GODMODE V2 PERFORMANCE  (test 2023→2026, 1× gross, $100 start)")
    print(f"{'═'*100}")
    print_strategy_table(strategies, test_mask)

    # ── Alignment check ──
    print_alignment_check(logs_dict, test_mask)

    # ── Regime flag diagnostics ──
    print_flag_diagnostics(logs_dict, test_mask)

    # ── Feature improvement summary ──
    print(f"\n  {'─'*80}")
    print("  IMPROVEMENT DELTA vs v_ann_v1 (Sharpe | CAGR | MaxDD)")
    print(f"  {'─'*80}")
    base_st = _stats(log_v1['pnl'].iloc[test_mask])
    for name, pnl in strategies.items():
        if name in ('v_ann_v1', 'v60', 'long_only'):
            continue
        st = _stats(pnl.iloc[test_mask])
        d_sharpe = st['sharpe'] - base_st['sharpe']
        d_cagr   = (st['cagr'] - base_st['cagr']) * 100
        d_dd     = (st['max_dd'] - base_st['max_dd']) * 100
        flag     = '↑' if d_sharpe > 0.05 else ('↓' if d_sharpe < -0.05 else '~')
        print(f"  {name:<22}  dSharpe={d_sharpe:>+.3f}  dCAGR={d_cagr:>+.1f}%  "
              f"dMaxDD={d_dd:>+.1f}%  {flag}")

    # ── Year-on-year table ──
    K_LIST = [1, 2, 3, 5]
    for name, pnl in strategies.items():
        print_yoy_table(name, pnl.iloc[test_mask], K_LIST)

    # ── Dollar simulation ──
    print(f"\n\n{'▓'*110}")
    print(f"  $1,000 DOLLAR SIMULATION  —  v2 full suite")
    print(f"{'▓'*110}")
    print_dollar_simulation(strategies, test_mask, start_capital=1000.0,
                             K_list=[1, 2, 3, 5])

    # ── Save JSON ──
    out = {
        'meta': {
            'version': 'godmode_v2',
            'W_TARGET': W_TARGET,
            'KAPPA_A': KAPPA_A,
            'ANNEAL_AMP': ANNEAL_AMP,
            'ANNEAL_PEAK_V1': ANNEAL_PEAK_V1,
            'ANNEAL_PEAK_V2': ANNEAL_PEAK_V2,
            'MW_W1D': MW_W1D, 'MW_W7D': MW_W7D, 'MW_W30D': MW_W30D,
            'SIGMA_ROLL_WIN_DAYS': SIGMA_ROLL_WIN_DAYS,
            'SIGMA_ROLL_UPDATE_DAYS': SIGMA_ROLL_UPDATE_DAYS,
            'KAPPA_ADAPT_MIN': KAPPA_ADAPT_MIN,
            'KAPPA_ADAPT_MAX': KAPPA_ADAPT_MAX,
            'W_BOX_V1': W_BOX_V1, 'W_BOX_75': W_BOX_75, 'W_BOX_100': W_BOX_100,
            'CONV_MIN_V1': CONV_MIN_V1,
        },
        'calibration': {'7d': diag, 'comp': diag_c},
        'performance': {n: _stats(p.iloc[test_mask]) for n, p in strategies.items()},
    }
    out_path = OUT_DIR_ / 'crypto_godmode_v2.json'
    with open(out_path, 'w') as fh:
        json.dump(out, fh, indent=2, default=float)
    print(f"\n  Saved → {out_path}")
    print(SEP)


if __name__ == '__main__':
    main()
