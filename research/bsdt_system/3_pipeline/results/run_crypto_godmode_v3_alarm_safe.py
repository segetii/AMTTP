"""
Crypto Godmode v3 — Alarm-Safe Canonical Solution
==================================================

v2 proved the mistake: γ and stale alarms must NOT be hard trade gates.
γ≈1 often marks a high-curvature/high-correction state where the canonical
engine is doing useful work. Killing the ODE there deleted the profitable bars.

This script tests corrected alarm handling on top of the v1 champion:

  v1_ref              exact v_anneal v1 behavior
  stale_soft          stale alarm only slows weak-signal bars; γ never gates
  gamma_step_clip     γ reduces step size softly only above 0.95; no kill switch
  gamma_boost         γ is treated as useful curvature: boost step on strong signal
  cap_on_strength     W_BOX expands 0.50→0.75 only when signal+geometry agree
  boost_cap           gamma_boost + cap_on_strength
  alarm_safe_combo    stale_soft + gamma_boost + cap_on_strength

Core rule:
  alarms may change step magnitude or cap softly, but never set gate=0.
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
from run_crypto_canonical_v4 import (
    A_FACTORS, N_STATE, EPSILON, DT, _stats, print_yoy_table,
)
from run_crypto_canonical_v58_v60 import (
    print_dollar_simulation, run_canonical_sweep as _run_v4_sweep, overlay_v60,
)
from run_crypto_pairs_v34_full_combined import (
    OUT_DIR, TEST_START, TRAIN_START, build_1h_df,
)
from run_crypto_godmode_v2 import (
    W_TARGET, W_BOX_V1, KAPPA_A, CONV_MIN_V1, CONV_MAX,
    ANNEAL_AMP, ANNEAL_PEAK_V1,
    build_w_star_7d, build_b_aligned, calibrate, _predictive_scalars,
    print_alignment_check, print_strategy_table, print_flag_diagnostics,
)

OUT_DIR_ = Path(OUT_DIR)
BPD = 24


def run_alarm_safe_sweep(
    df: pd.DataFrame,
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    w_star_arr: np.ndarray,
    b_arr: np.ndarray,
    Sigma_f: np.ndarray,
    theta_base: float,
    mode: str,
    label: str,
) -> pd.DataFrame:
    """v1 anneal sweep with corrected alarm usage.

    Modes:
      v1_ref:            exact v1 logic
      stale_soft:        stale only slows weak-signal bars by 75%; γ ignored
      gamma_step_clip:   if γ>0.95, step multiplier bottoms at 0.50; no gate=0
      gamma_boost:       if signal strong, multiplier = 1 + 0.35*γ*signal_strength
      cap_on_strength:   W_BOX=0.75 only when signal_strength>0.80 and γ>0.75
      boost_cap:         gamma_boost + cap_on_strength
      alarm_safe_combo:  stale_soft + gamma_boost + cap_on_strength
    """
    T = len(df)
    R = np.column_stack([
        df['ret_btc'].fillna(0.0).values,
        df['ret_eth'].fillna(0.0).values,
        df['ret_sol'].fillna(0.0).values if 'ret_sol' in df.columns else df['ret_eth'].fillna(0.0).values,
    ])

    # stale threshold calibrated from train, identical spirit to v1/v2
    rho_train = []
    for t in np.where(train_mask)[0][::50]:
        sys_t = TradingDomain(
            A=A_FACTORS, b=b_arr[t], Sigma=Sigma_f,
            kappa=KAPPA_A, w_star=w_star_arr[t], theta=theta_base, epsilon=EPSILON,
        ).build()
        sc = _predictive_scalars(sys_t, np.zeros(N_STATE))
        if sc['rho_eff'] > 0:
            rho_train.append(sc['rho_eff'])
    rho_typ = float(np.median(rho_train)) if rho_train else 1.0

    keys = ['E', 'gamma', 'dE_dt', 'cos_theta', 'mfls', 'v_E', 'rho_eff',
            'rhs_norm', 'w_btc', 'w_eth', 'w_sol', 'pnl', 'pnl_long_only',
            'stop_flag', 'stale_flag', 'drift_flag', 'conviction', 'theta_t',
            'kappa_t', 'gate', 'step_mult', 'W_box_t', 'signal_strength']
    log = {k: np.zeros(T) for k in keys}

    hours = df.index.hour
    w = np.zeros(N_STATE, dtype=float)
    cos_th_prev = 0.0
    t0 = time.time()

    for t in range(T):
        hr = int(hours[t])
        theta_t = theta_base * (1.0 + ANNEAL_AMP * np.cos(
            2.0 * np.pi * (hr - ANNEAL_PEAK_V1) / 24.0))

        sys_t = TradingDomain(
            A=A_FACTORS, b=b_arr[t], Sigma=Sigma_f,
            kappa=KAPPA_A, w_star=w_star_arr[t], theta=theta_t, epsilon=EPSILON,
        ).build()
        sc = _predictive_scalars(sys_t, w)

        signal_strength = float(np.linalg.norm(w_star_arr[t]) / (np.sqrt(N_STATE) * W_TARGET + 1e-12))
        signal_strength = float(np.clip(signal_strength, 0.0, 1.0))

        conviction = float(np.clip(-cos_th_prev, CONV_MIN_V1, CONV_MAX))
        stop_flag  = 1.0 if sc['gamma'] > 0.90 else 0.0
        stale_flag = 1.0 if (sc['rho_eff'] > 0 and sc['rho_eff'] < 0.1 * rho_typ) else 0.0
        drift_flag = 1.0 if sc['cos_theta'] > 0.0 else 0.0

        # Corrected alarm semantics: no binary kill gate.
        gate = 1.0
        step_mult = 1.0
        W_box_t = W_BOX_V1

        if mode in ('stale_soft', 'alarm_safe_combo'):
            # Only weak signals are slowed on stale geometry.
            if stale_flag > 0 and signal_strength < 0.35:
                step_mult *= 0.25

        if mode == 'gamma_step_clip':
            # Softly slow only extreme γ, never below 50% step.
            excess = max(0.0, sc['gamma'] - 0.95) / 0.05
            step_mult *= max(0.50, 1.0 - 0.50 * min(1.0, excess))

        if mode in ('gamma_boost', 'boost_cap', 'alarm_safe_combo'):
            # Treat aligned high γ as curvature opportunity, not danger.
            step_mult *= (1.0 + 0.35 * sc['gamma'] * signal_strength)

        if mode in ('cap_on_strength', 'boost_cap', 'alarm_safe_combo'):
            # Expand cap only when geometry and signal are both strong.
            if signal_strength > 0.80 and sc['gamma'] > 0.75 and conviction > 0.70:
                W_box_t = 0.75

        w_new = w + DT * sc['rhs'] * conviction * step_mult * gate
        w_new = np.clip(w_new, -W_box_t, W_box_t)

        log['E'][t] = sc['E']
        log['gamma'][t] = sc['gamma']
        log['dE_dt'][t] = sc['dE_dt']
        log['cos_theta'][t] = sc['cos_theta']
        log['mfls'][t] = sc['mfls']
        log['v_E'][t] = sc['v_E']
        log['rho_eff'][t] = sc['rho_eff']
        log['rhs_norm'][t] = sc['rhs_norm']
        log['w_btc'][t] = w_new[0]
        log['w_eth'][t] = w_new[1]
        log['w_sol'][t] = w_new[2]
        log['pnl'][t] = float(w_new @ R[t])
        log['pnl_long_only'][t] = float(R[t].mean())
        log['stop_flag'][t] = stop_flag
        log['stale_flag'][t] = stale_flag
        log['drift_flag'][t] = drift_flag
        log['conviction'][t] = conviction
        log['theta_t'][t] = theta_t
        log['kappa_t'][t] = KAPPA_A
        log['gate'][t] = gate
        log['step_mult'][t] = step_mult
        log['W_box_t'][t] = W_box_t
        log['signal_strength'][t] = signal_strength

        w = w_new
        cos_th_prev = sc['cos_theta']

        if t > 0 and (t % 5000) == 0:
            print(f"    [{label}] {t:>6}/{T}  ({time.time()-t0:>5.1f}s)")

    print(f"  [{label}] sweep done: {T:,} bars  {time.time()-t0:.1f}s")
    return pd.DataFrame(log, index=df.index)


def print_alarm_solution_diag(logs: dict, test_mask: np.ndarray):
    print(f"\n  {'─'*100}")
    print("  ALARM-SAFE DIAGNOSTICS — γ alarm is never a gate; it only changes step/cap")
    print(f"  {'─'*100}")
    for name, lg in logs.items():
        s = lg.iloc[test_mask]
        stop_pct = 100.0 * s['stop_flag'].mean()
        stale_pct = 100.0 * s['stale_flag'].mean()
        step_mean = s['step_mult'].mean()
        cap75_pct = 100.0 * (s['W_box_t'] > W_BOX_V1).mean()
        sig_mean = s['signal_strength'].mean()
        print(f"  {name:<18} stop={stop_pct:>5.1f}%  stale={stale_pct:>5.1f}%  "
              f"step={step_mean:>5.3f}  cap75={cap75_pct:>5.1f}%  sig={sig_mean:>5.3f}")


def main():
    OUT_DIR_.mkdir(parents=True, exist_ok=True)
    SEP = "=" * 100
    print(SEP)
    print("  CRYPTO GODMODE v3 — Alarm-Safe Solution")
    print("  γ/stale alarms are not gates. Test soft throttle/boost/cap semantics.")
    print(SEP)

    print("\n[1] Fetching Binance data ...")
    df, has_sol = build_1h_df(start='2021-01-01', end='2026-05-01')
    test_mask  = np.asarray(df.index >= TEST_START)
    train_mask = np.asarray((df.index >= TRAIN_START) & (df.index < TEST_START))
    print(f"  Bars={len(df):,}  Train={train_mask.sum():,}  Test={test_mask.sum():,}  SOL={has_sol}")

    print("\n[2] Building v1 champion signal ...")
    w_star = build_w_star_7d(df, W_TARGET=W_TARGET)
    b_arr = build_b_aligned(w_star)

    print("\n[3] Calibrating ...")
    Sigma_f, theta, E_med, diag = calibrate(df, train_mask, w_star, b_arr, kappa=KAPPA_A, label='v3')

    modes = [
        ('v1_ref', 'v1_ref'),
        ('stale_soft', 'stale_soft'),
        ('gamma_step_clip', 'gamma_step_clip'),
        ('gamma_boost', 'gamma_boost'),
        ('cap_on_strength', 'cap_on_strength'),
        ('boost_cap', 'boost_cap'),
        ('alarm_safe_combo', 'alarm_safe_combo'),
    ]

    print("\n[4] Running alarm-safe sweeps ...")
    logs = {}
    for label, mode in modes:
        print(f"\n  -- {label} --")
        logs[label] = run_alarm_safe_sweep(
            df, train_mask, test_mask, w_star, b_arr, Sigma_f, theta, mode=mode, label=label)

    print("\n[5] Baselines ...")
    log_base, _ = _run_v4_sweep(df, train_mask, test_mask)
    pnl_v60 = overlay_v60(log_base, train_mask)
    pnl_long = log_base['pnl_long_only']

    strategies = {name: lg['pnl'] for name, lg in logs.items()}
    strategies['v60'] = pnl_v60
    strategies['long_only'] = pnl_long

    print(f"\n{'═'*100}")
    print("  GODMODE V3 ALARM-SAFE PERFORMANCE  (test 2023→2026, 1× gross, $100 start)")
    print(f"{'═'*100}")
    print_strategy_table(strategies, test_mask)
    print_alignment_check(logs, test_mask)
    print_flag_diagnostics(logs, test_mask)
    print_alarm_solution_diag(logs, test_mask)

    print(f"\n  {'─'*80}")
    print("  DELTA vs v1_ref")
    print(f"  {'─'*80}")
    base = _stats(strategies['v1_ref'].iloc[test_mask])
    for name, pnl in strategies.items():
        if name in ('v1_ref', 'v60', 'long_only'):
            continue
        st = _stats(pnl.iloc[test_mask])
        print(f"  {name:<18} dSharpe={st['sharpe']-base['sharpe']:+.3f}  "
              f"dCAGR={(st['cagr']-base['cagr'])*100:+.1f}%  "
              f"dMaxDD={(st['max_dd']-base['max_dd'])*100:+.1f}%")

    K_LIST = [1, 2, 3, 5]
    for name, pnl in strategies.items():
        print_yoy_table(name, pnl.iloc[test_mask], K_LIST)

    print(f"\n\n{'▓'*110}")
    print("  $1,000 DOLLAR SIMULATION — alarm-safe variants")
    print(f"{'▓'*110}")
    print_dollar_simulation(strategies, test_mask, start_capital=1000.0, K_list=K_LIST)

    out = {
        'meta': {
            'version': 'godmode_v3_alarm_safe',
            'core_rule': 'gamma/stale alarms are never binary gates',
            'W_TARGET': W_TARGET,
            'W_BOX_V1': W_BOX_V1,
            'KAPPA_A': KAPPA_A,
            'ANNEAL_PEAK': ANNEAL_PEAK_V1,
        },
        'calibration': diag,
        'performance': {n: _stats(p.iloc[test_mask]) for n, p in strategies.items()},
    }
    out_path = OUT_DIR_ / 'crypto_godmode_v3_alarm_safe.json'
    with open(out_path, 'w') as fh:
        json.dump(out, fh, indent=2, default=float)
    print(f"\n  Saved → {out_path}")
    print(SEP)


if __name__ == '__main__':
    main()
