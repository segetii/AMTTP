"""
Crypto Godmode v6 — Angular Canonical Control
==============================================

Uses the trigonometric structure of the canonical ODE directly.

Keep the proven v1 setup fixed:
  b(t) = A @ [tanh(7d momentum) * 0.30]
  κ=0.15, W_BOX=0.50, θ-anneal peak=12 UTC, fixed Sigma

Only change the external step/conviction law using angular cockpit scalars:
  cosθ  = <F_base,g_X> / (||F_base|| ||g_X||)
  sinθ  = sqrt(1-cos²θ)
  work  = max(0,-cosθ)
  orbit = 2π sqrt(E)/(||F_base|| sinθ)

Variants:
  v1_ref          exact v1 conviction: clip(-cosθ_lag, 0.20, 1.00)
  ang_work        conviction = clipped radial work fraction
  ang_radial      conviction = work * (1 - 0.50 sin²θ)  (penalize circulation)
  ang_orbit       slow down if predicted orbit period is too short
  ang_half_life   boost if rho_eff half-life is stable; throttle stale/violent decay
  ang_combo       radial + orbit + half-life
  ang_aggressive  v1 conviction with mild angular boost, still W_BOX=0.50

This tests whether the missing 1000–3000% is in angular control rather than b(t).
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

from collapse_geometry.canonical import TradingDomain
from run_crypto_canonical_v4 import A_FACTORS, N_STATE, EPSILON, DT, _stats, print_yoy_table
from run_crypto_canonical_v58_v60 import print_dollar_simulation, run_canonical_sweep as _run_v4_sweep, overlay_v60
from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START, TRAIN_START, build_1h_df
from run_crypto_godmode_v2 import (
    W_TARGET, W_BOX_V1, KAPPA_A, CONV_MIN_V1, CONV_MAX,
    ANNEAL_AMP, ANNEAL_PEAK_V1,
    build_w_star_7d, build_b_aligned, calibrate, _predictive_scalars,
    print_alignment_check, print_strategy_table, print_flag_diagnostics,
)

OUT_DIR_ = Path(OUT_DIR)
BPD = 24


def _angular_scalars(sc: dict) -> dict:
    cosv = float(np.clip(sc['cos_theta'], -1.0, 1.0))
    sinv = float(np.sqrt(max(0.0, 1.0 - cosv * cosv)))
    work = float(max(0.0, -cosv))
    E = float(max(sc['E'], 0.0))
    rhs_norm = float(max(sc['rhs_norm'], 1e-12))
    # Approximate orbital period in bars. If sin≈0, circulation is absent -> very long period.
    orbit = float(2.0 * np.pi * np.sqrt(E + 1e-12) / (rhs_norm * max(sinv, 1e-6)))
    # Half-life in bars from rho_eff.
    rho = float(sc['rho_eff'])
    half_life = float(np.log(2.0) / max(rho, 1e-9)) if rho > 0 else 1e9
    return {'cos': cosv, 'sin': sinv, 'work': work, 'orbit': orbit, 'half_life': half_life}


def _step_multiplier(mode: str, prev_ang: dict) -> tuple[float, float]:
    """Return (conviction, step_mult), causal from previous bar angles."""
    work = prev_ang['work']
    sinv = prev_ang['sin']
    orbit = prev_ang['orbit']
    hl = prev_ang['half_life']

    if mode == 'v1_ref':
        return float(np.clip(work, CONV_MIN_V1, CONV_MAX)), 1.0

    if mode == 'ang_work':
        return float(np.clip(work, 0.05, CONV_MAX)), 1.0

    if mode == 'ang_radial':
        radial_quality = work * (1.0 - 0.50 * sinv * sinv)
        return float(np.clip(radial_quality, 0.05, CONV_MAX)), 1.0

    if mode == 'ang_orbit':
        conv = float(np.clip(work, CONV_MIN_V1, CONV_MAX))
        # If orbit period < 12h, movement is too circulatory/noisy: slow it.
        if orbit < 12.0:
            mult = 0.55
        elif orbit < 24.0:
            mult = 0.75
        elif orbit > 24.0 * 21.0:
            mult = 0.80  # too slow/stale
        else:
            mult = 1.0
        return conv, mult

    if mode == 'ang_half_life':
        conv = float(np.clip(work, CONV_MIN_V1, CONV_MAX))
        # Desired half-life: 6h to 10d. Too short = violent; too long = stale.
        if hl < 6.0:
            mult = 0.60
        elif hl > 24.0 * 10.0:
            mult = 0.70
        else:
            mult = 1.10
        return conv, mult

    if mode == 'ang_combo':
        radial_quality = work * (1.0 - 0.35 * sinv * sinv)
        conv = float(np.clip(radial_quality, 0.08, CONV_MAX))
        mult = 1.0
        if orbit < 12.0:
            mult *= 0.65
        elif orbit > 24.0 * 21.0:
            mult *= 0.80
        if hl < 6.0:
            mult *= 0.75
        elif 6.0 <= hl <= 24.0 * 10.0:
            mult *= 1.10
        else:
            mult *= 0.85
        return conv, float(np.clip(mult, 0.35, 1.25))

    if mode == 'ang_aggressive':
        conv = float(np.clip(work, CONV_MIN_V1, CONV_MAX))
        # Boost only if radial work dominates tangential circulation.
        radial_dominance = max(0.0, work - 0.50 * sinv)
        mult = 1.0 + 0.25 * radial_dominance
        return conv, float(np.clip(mult, 1.0, 1.20))

    raise ValueError(f'unknown mode {mode}')


def run_angular_sweep(df, train_mask, test_mask, w_star_arr, b_arr, Sigma_f, theta_base, mode: str, label: str) -> pd.DataFrame:
    T = len(df)
    R = np.column_stack([
        df['ret_btc'].fillna(0.0).values,
        df['ret_eth'].fillna(0.0).values,
        df['ret_sol'].fillna(0.0).values if 'ret_sol' in df.columns else df['ret_eth'].fillna(0.0).values,
    ])
    hours = df.index.hour

    keys = ['E', 'gamma', 'dE_dt', 'cos_theta', 'sin_theta', 'mfls', 'v_E', 'rho_eff',
            'rhs_norm', 'orbit_period', 'half_life', 'w_btc', 'w_eth', 'w_sol',
            'pnl', 'pnl_long_only', 'stop_flag', 'stale_flag', 'drift_flag',
            'conviction', 'step_mult', 'theta_t', 'kappa_t', 'gate']
    log = {k: np.zeros(T) for k in keys}

    # stale diagnostic only
    rho_train = []
    for t in np.where(train_mask)[0][::50]:
        sys_t = TradingDomain(A=A_FACTORS, b=b_arr[t], Sigma=Sigma_f,
                              kappa=KAPPA_A, w_star=w_star_arr[t], theta=theta_base,
                              epsilon=EPSILON).build()
        sc = _predictive_scalars(sys_t, np.zeros(N_STATE))
        if sc['rho_eff'] > 0:
            rho_train.append(sc['rho_eff'])
    rho_typ = float(np.median(rho_train)) if rho_train else 1.0

    w = np.zeros(N_STATE, dtype=float)
    prev_ang = {'cos': 0.0, 'sin': 1.0, 'work': 0.0, 'orbit': 24.0 * 7.0, 'half_life': 24.0}
    t0 = time.time()

    for t in range(T):
        theta_t = theta_base * (1.0 + ANNEAL_AMP * np.cos(
            2.0 * np.pi * (int(hours[t]) - ANNEAL_PEAK_V1) / 24.0))
        sys_t = TradingDomain(A=A_FACTORS, b=b_arr[t], Sigma=Sigma_f,
                              kappa=KAPPA_A, w_star=w_star_arr[t], theta=theta_t,
                              epsilon=EPSILON).build()
        sc = _predictive_scalars(sys_t, w)
        ang = _angular_scalars(sc)

        conviction, step_mult = _step_multiplier(mode, prev_ang)
        w_new = np.clip(w + DT * sc['rhs'] * conviction * step_mult, -W_BOX_V1, W_BOX_V1)

        stop_flag = 1.0 if sc['gamma'] > 0.90 else 0.0
        stale_flag = 1.0 if (sc['rho_eff'] > 0 and sc['rho_eff'] < 0.1 * rho_typ) else 0.0
        drift_flag = 1.0 if sc['cos_theta'] > 0.0 else 0.0

        log['E'][t] = sc['E']
        log['gamma'][t] = sc['gamma']
        log['dE_dt'][t] = sc['dE_dt']
        log['cos_theta'][t] = sc['cos_theta']
        log['sin_theta'][t] = ang['sin']
        log['mfls'][t] = sc['mfls']
        log['v_E'][t] = sc['v_E']
        log['rho_eff'][t] = sc['rho_eff']
        log['rhs_norm'][t] = sc['rhs_norm']
        log['orbit_period'][t] = ang['orbit']
        log['half_life'][t] = ang['half_life']
        log['w_btc'][t] = w_new[0]
        log['w_eth'][t] = w_new[1]
        log['w_sol'][t] = w_new[2]
        log['pnl'][t] = float(w_new @ R[t])
        log['pnl_long_only'][t] = float(R[t].mean())
        log['stop_flag'][t] = stop_flag
        log['stale_flag'][t] = stale_flag
        log['drift_flag'][t] = drift_flag
        log['conviction'][t] = conviction
        log['step_mult'][t] = step_mult
        log['theta_t'][t] = theta_t
        log['kappa_t'][t] = KAPPA_A
        log['gate'][t] = 1.0

        w = w_new
        prev_ang = ang

        if t > 0 and (t % 5000) == 0:
            print(f"    [{label}] {t:>6}/{T}  ({time.time()-t0:>5.1f}s)")

    print(f"  [{label}] sweep done: {T:,} bars  {time.time()-t0:.1f}s")
    return pd.DataFrame(log, index=df.index)


def print_angular_diag(logs: dict, test_mask: np.ndarray):
    print(f"\n  {'─'*100}")
    print('  ANGULAR DIAGNOSTICS (test window)')
    print(f"  {'─'*100}")
    for name, lg in logs.items():
        s = lg.iloc[test_mask]
        print(f"  {name:<16} cos_mean={s['cos_theta'].mean():+.3f}  "
              f"sin_mean={s['sin_theta'].mean():.3f}  conv={s['conviction'].mean():.3f}  "
              f"step={s['step_mult'].mean():.3f}  orbit_med={s['orbit_period'].median():.1f}h  "
              f"hl_med={s['half_life'].median():.1f}h")


def main():
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    SEP = '=' * 100
    print(SEP)
    print('  CRYPTO GODMODE v6 — Angular Canonical Control')
    print('  Tests cosθ/sinθ/orbit/half-life control with frozen v1 b(t).')
    print(SEP)

    print('\n[1] Fetching Binance data ...')
    df, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask = np.asarray(df.index >= TEST_START)
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    print(f'  Bars={len(df):,}  Train={train_mask.sum():,}  Test={test_mask.sum():,}  SOL={has_sol}')

    print('\n[2] Building v1 b(t) ...')
    w_star = build_w_star_7d(df, W_TARGET=W_TARGET)
    b_arr = build_b_aligned(w_star)

    print('\n[3] Calibrating ...')
    Sigma_f, theta, E_med, diag = calibrate(df, train_mask, w_star, b_arr, kappa=KAPPA_A, label='v6')

    modes = ['v1_ref', 'ang_work', 'ang_radial', 'ang_orbit', 'ang_half_life', 'ang_combo', 'ang_aggressive']
    print('\n[4] Running angular sweeps ...')
    logs = {}
    for mode in modes:
        print(f"\n  -- {mode} --")
        logs[mode] = run_angular_sweep(df, train_mask, test_mask, w_star, b_arr, Sigma_f, theta, mode=mode, label=mode)

    print('\n[5] Baselines ...')
    log_base, _ = _run_v4_sweep(df, train_mask, test_mask)
    pnl_v60 = overlay_v60(log_base, train_mask)
    pnl_long = log_base['pnl_long_only']

    strategies = {name: lg['pnl'] for name, lg in logs.items()}
    strategies['v60'] = pnl_v60
    strategies['long_only'] = pnl_long

    print(f"\n{'═'*100}")
    print('  GODMODE V6 ANGULAR PERFORMANCE (test 2023→2026, 1× gross, $100 start)')
    print(f"{'═'*100}")
    print_strategy_table(strategies, test_mask)
    print_alignment_check(logs, test_mask)
    print_flag_diagnostics(logs, test_mask)
    print_angular_diag(logs, test_mask)

    print(f"\n  {'─'*80}")
    print('  DELTA vs v1_ref')
    print(f"  {'─'*80}")
    base = _stats(strategies['v1_ref'].iloc[test_mask])
    for name, pnl in strategies.items():
        if name in ('v1_ref', 'v60', 'long_only'):
            continue
        st = _stats(pnl.iloc[test_mask])
        print(f"  {name:<16} dSharpe={st['sharpe']-base['sharpe']:+.3f}  "
              f"dCAGR={(st['cagr']-base['cagr'])*100:+.1f}%  "
              f"dMaxDD={(st['max_dd']-base['max_dd'])*100:+.1f}%  $100→${st['final']:.2f}")

    K_LIST = [1, 2, 3, 5]
    for name, pnl in strategies.items():
        print_yoy_table(name, pnl.iloc[test_mask], K_LIST)

    print(f"\n\n{'▓'*110}")
    print('  $1,000 DOLLAR SIMULATION — angular variants')
    print(f"{'▓'*110}")
    print_dollar_simulation(strategies, test_mask, start_capital=1000.0, K_list=K_LIST)

    out = {
        'meta': {'version': 'godmode_v6_angular', 'rule': 'frozen v1 b(t); angular control laws'},
        'calibration': diag,
        'performance': {n: _stats(p.iloc[test_mask]) for n, p in strategies.items()},
    }
    out_path = OUT_DIR_ / 'crypto_godmode_v6_angular.json'
    with open(out_path, 'w') as fh:
        json.dump(out, fh, indent=2, default=float)
    print(f"\n  Saved → {out_path}")
    print(SEP)


if __name__ == '__main__':
    main()
