"""
simulate_dynamic_ze7_sweep.py
==============================
Regime-adaptive version of the abs(zE7) >= 0.10 minimum-force gate.

CONTEXT
  Fixed gate abs(zE7) >= 0.10 → Calmar=+7.974, MaxDD=−16.80% (vs +7.086/−27.13% baseline).
  Only 148 entries blocked (5.1%). Hypothesis: an adaptive threshold that tracks the
  current regime's zE7 distribution can:
    - compress MaxDD further in high-force regimes (raise threshold)
    - release entries in low-force regimes where 0.10 is too tight
  resulting in better Calmar or Sharpe without manual re-tuning.

METHODS
  A — Rolling percentile of |zE7|:
        thresh[i] = percentile(|zE7|_{causal window}, pct)
        Parameters: window ∈ {168h, 336h, 720h}  ×  pct ∈ {50, 60, 70, 80}
        Semantics: "only trade if THIS bar's |zE7| is above the Nth percentile of
                    recent |zE7| values" — adapts to regime strength automatically.

  B — Rolling std scale:
        thresh[i] = k × rolling_std(zE7, window)
        Parameters: window ∈ {168h, 336h, 720h}  ×  k ∈ {0.05, 0.07, 0.10, 0.15}
        Semantics: "threshold is a fixed multiple of recent zE7 volatility" —
                    expands in high-vol, contracts in low-vol.

All threshold arrays are fully CAUSAL: computed with shift(1) so bar i uses only
data from bars 0..i-1.

Baselines included:
  fixed_0.10  — proven champion (eps=0.10, constant)
  no_filter   — raw champion (no gate)

Grid: 12 (A) + 12 (B) + 2 (baselines) = 26 combinations
"""
from __future__ import annotations
import time
import numpy as np
import pandas as pd
from pathlib import Path

from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START
from test_daily_geometry_stop_tp_ohlc   import (
    build_daily_geometry, fetch_futures_ohlcv, get_channel_series,
)
from test_psi_adaptive_y                import BASE
from simulate_adaptive_y_drawdown_brake import INIT
from simulate_master_strategy           import (
    build_positions, simulate_combined, equity_metrics,
    simulate_unit_trailing,
    RT_COST, FUND_HOURLY, HOURS_PER_DAY,
    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
)
from simulate_v63_quadrant              import (
    _build_quadrant_multiplier, simulate_unit_trailing_ze7gate,
    CB_HALT, CB_RESUME, CB_WINDOW_DAYS,
    TRAIL_TRIGGER_MULT, TRAIL_DIST_MULT,
    ZE7_MIN_FORCE,
)

BAR     = '=' * 110
SEP     = '-' * 110
TEST_TS = pd.Timestamp(TEST_START)

# ─────────────────────────────────────────────────────────────────────────────
#  PARAMETER GRID
# ─────────────────────────────────────────────────────────────────────────────
WINDOWS_H    = [168, 336, 720]        # 7d, 14d, 30d in hourly bars
PERCENTILES  = [50, 60, 70, 80]       # for method A
K_SCALES     = [0.05, 0.07, 0.10, 0.15]  # for method B
WARMUP_BARS  = 24                      # fallback to fixed 0.10 until window fills


# ─────────────────────────────────────────────────────────────────────────────
#  THRESHOLD BUILDERS (causal: shift(1) applied)
# ─────────────────────────────────────────────────────────────────────────────

def build_percentile_thresh(ze7_s: pd.Series, window: int, pct: float,
                             fallback: float = ZE7_MIN_FORCE) -> np.ndarray:
    """Rolling causal percentile of |zE7|.

    Returns per-bar threshold array aligned to ze7_s.index.
    Warm-up bars (window not yet full) fall back to `fallback`.
    """
    raw = ze7_s.abs().rolling(window, min_periods=WARMUP_BARS).quantile(pct / 100.0)
    # shift(1): bar i uses data from bars 0..i-1 only
    causal = raw.shift(1).fillna(fallback)
    return causal.values.astype(float)


def build_std_thresh(ze7_s: pd.Series, window: int, k: float,
                     fallback: float = ZE7_MIN_FORCE) -> np.ndarray:
    """Rolling causal std-scaled threshold: k × std(zE7, window).

    Returns per-bar threshold array aligned to ze7_s.index.
    """
    raw = ze7_s.rolling(window, min_periods=WARMUP_BARS).std()
    causal = (raw * k).shift(1).fillna(fallback)
    return causal.values.astype(float)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    t0 = time.time()
    print(BAR)
    print('  DYNAMIC zE7 THRESHOLD SWEEP')
    print(f'  Fixed baseline: abs(zE7) >= {ZE7_MIN_FORCE}  '
          f'→ Calmar=+7.974  MaxDD=−16.80%')
    print('  Methods: (A) rolling percentile  (B) rolling std × k')
    print(BAR)

    # ── [1] Build positions ───────────────────────────────────────────────────
    print('\n[1] Building geometry + positions ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ch        = get_channel_series()
    ohlc_all  = fetch_futures_ohlcv()
    p         = build_positions(df_1h, comp_raw, calib_mask, ohlc_all)
    q_mult    = _build_quadrant_multiplier(ch, p['hours'])
    layered_size = p['size_mult'] * q_mult

    sl            = BASE['sl_mult']    * p['daily_vol']
    tp            = BASE['tp_mult']    * p['daily_vol']
    trail_trigger = TRAIL_TRIGGER_MULT * p['daily_vol']
    trail_dist    = TRAIL_DIST_MULT    * p['daily_vol']

    hours     = p['hours']
    unit_zero = pd.Series(np.zeros(len(hours)), index=hours)

    print(f'  daily_vol={p["daily_vol"]:.3%}  sl={sl:.3%}  tp={tp:.3%}')
    print(f'  CB: halt={CB_HALT:.0%}  resume={CB_RESUME:.0%}  window={CB_WINDOW_DAYS}d')

    # ── [2] zE7 causal series ─────────────────────────────────────────────────
    print('\n[2] Precomputing zE7 signal series ...')
    ze7_s   = ch['E7'].reindex(hours, method='ffill').fillna(0.0).shift(1).fillna(0.0)
    ze7_arr = ze7_s.values  # already causal (shifted in build_daily_geometry context)

    # Regime diagnostics
    ze7_abs = ze7_s.abs()
    print(f'  |zE7| stats:  mean={ze7_abs.mean():.4f}  std={ze7_abs.std():.4f}  '
          f'p50={ze7_abs.quantile(0.50):.4f}  p60={ze7_abs.quantile(0.60):.4f}  '
          f'p70={ze7_abs.quantile(0.70):.4f}  p80={ze7_abs.quantile(0.80):.4f}')
    # Compare threshold levels across methods
    print(f'\n  Percentile thresholds (global):')
    for pct in PERCENTILES:
        v = ze7_abs.quantile(pct / 100.0)
        pct_blocked = (ze7_abs < v).mean()
        print(f'    p{pct}: {v:.4f}  →  would block {pct_blocked:.1%} of bars')
    print(f'\n  Std-scale thresholds (global std={ze7_s.std():.4f}):')
    for k in K_SCALES:
        v = ze7_s.std() * k
        pct_blocked = (ze7_abs < v).mean()
        print(f'    k={k:.2f}: {v:.4f}  →  would block {pct_blocked:.1%} of bars')

    # ── [3] Run helper ─────────────────────────────────────────────────────────
    def _run(thresh_input, label: str) -> dict:
        """Run one config and return metrics dict."""
        unit_arr, cnts = simulate_unit_trailing_ze7gate(
            p['op'], p['hi'], p['lo'], p['cl'],
            p['hpos'], p['dpos'], p['dactive'],
            layered_size, sl, tp, trail_trigger, trail_dist,
            ze7_arr=ze7_arr, ze7_min=thresh_input,
        )
        unit_s = pd.Series(unit_arr, index=hours)
        res    = simulate_combined(
            unit_s, unit_zero,
            K_normal=DYN_K, K_crash=0.0,
            dd_soft=DYN_DD_SOFT, dd_stop=DYN_DD_STOP, y_floor=DYN_Y_FLOOR,
            cb_halt=CB_HALT, cb_resume=CB_RESUME,
            cb_window_days=CB_WINDOW_DAYS, use_cb=True,
        )
        eq    = res['eq']
        m_oos = equity_metrics(eq[eq.index >= TEST_TS], label='oos')
        n_vetoed = cnts.get('vetoed_force', 0)
        n_entries = cnts['entries']
        pct_blocked = n_vetoed / max(n_entries + n_vetoed, 1)

        # Compute time-varying thresh stats if array
        if hasattr(thresh_input, '__len__'):
            thresh_arr = np.asarray(thresh_input)
            thresh_mean = float(thresh_arr.mean())
            thresh_std  = float(thresh_arr.std())
        else:
            thresh_mean = float(thresh_input)
            thresh_std  = 0.0

        return dict(
            label=label,
            calmar  = m_oos['calmar'],
            ret_pct = m_oos['return_pct'],
            cagr    = m_oos['cagr'],
            sharpe  = m_oos['sharpe'],
            maxdd   = m_oos['maxdd'],
            entries = n_entries,
            stops   = cnts.get('stop', 0),
            stop_rt = cnts.get('stop', 0) / max(n_entries, 1),
            vetoed  = n_vetoed,
            pct_blocked = pct_blocked,
            thresh_mean = thresh_mean,
            thresh_std  = thresh_std,
        )

    # ── [4] Build and run all 26 combinations ─────────────────────────────────
    total_combos = 2 + len(WINDOWS_H) * len(PERCENTILES) + len(WINDOWS_H) * len(K_SCALES)
    print(f'\n[3] Sweeping {total_combos} combinations ...')
    results = []

    # Baselines
    results.append(_run(0.0,          'baseline_no_filter'))
    results.append(_run(ZE7_MIN_FORCE, f'fixed_{ZE7_MIN_FORCE}'))

    # Method A — rolling percentile
    for W in WINDOWS_H:
        for pct in PERCENTILES:
            thresh = build_percentile_thresh(ze7_s, W, pct)
            label  = f'A_p{pct}_W{W}h'
            r      = _run(thresh, label)
            r.update(method='A', window=W, param=pct)
            results.append(r)

    # Method B — rolling std × k
    for W in WINDOWS_H:
        for k in K_SCALES:
            thresh = build_std_thresh(ze7_s, W, k)
            label  = f'B_k{k:.2f}_W{W}h'
            r      = _run(thresh, label)
            r.update(method='B', window=W, param=k)
            results.append(r)

    df_res = pd.DataFrame(results).sort_values('calmar', ascending=False)

    # ── [5] Full results table ─────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  FULL RESULTS — sorted by OOS Calmar')
    print(f'  Reference (fixed 0.10): Calmar=+7.974  MaxDD=−16.80%  Sharpe=+0.809')
    print(BAR)
    hdr = (f"  {'Label':<22} {'Calmar':>9} {'Return':>9} {'CAGR':>8} {'Sharpe':>8} "
           f"{'MaxDD':>8} {'Entries':>8} {'StopRt':>7} {'Blocked':>8} "
           f"{'T_mean':>7} {'T_std':>6}")
    print(hdr); print(SEP)
    for _, r in df_res.iterrows():
        marker = ''
        if r['maxdd'] > -0.17:    marker += ' ★★★'
        elif r['maxdd'] > -0.20:  marker += ' ★★'
        elif r['maxdd'] > -0.23:  marker += ' ★'
        print(f"  {r['label']:<22} {r['calmar']:>+9.3f} {r['ret_pct']:>+8.1%} "
              f"{r['cagr']:>+7.1%} {r['sharpe']:>+8.3f} {r['maxdd']:>+7.2%} "
              f"{int(r['entries']):>8} {r['stop_rt']:>6.1%} "
              f"{r['pct_blocked']:>7.1%} "
              f"{r['thresh_mean']:>7.4f} {r['thresh_std']:>6.4f}{marker}")

    # ── [6] Method A summary ──────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  METHOD A — rolling percentile of |zE7|')
    print(BAR)
    df_a = df_res[df_res['label'].str.startswith('A_')].copy()
    if len(df_a):
        df_a['window'] = df_a['label'].str.extract(r'W(\d+)h').astype(int)
        df_a['pct']    = df_a['label'].str.extract(r'p(\d+)').astype(int)
        # Pivot: rows = window, cols = pct, values = Calmar
        piv_calmar = df_a.pivot(index='window', columns='pct', values='calmar')
        piv_maxdd  = df_a.pivot(index='window', columns='pct', values='maxdd')
        print(f'\n  Calmar by window (rows) × percentile (cols):')
        print(f"  {'Window':>8}", end='')
        for pc in sorted(df_a['pct'].unique()):
            print(f'  p{pc:>3}', end='')
        print()
        for W in sorted(df_a['window'].unique()):
            print(f'  {W:>6}h  ', end='')
            for pc in sorted(df_a['pct'].unique()):
                val = piv_calmar.loc[W, pc] if (W, pc) in [(r, c) for r in piv_calmar.index for c in piv_calmar.columns] else float('nan')
                try:
                    val = piv_calmar.loc[W, pc]
                    print(f'  {val:>+5.2f}', end='')
                except Exception:
                    print(f'    nan', end='')
            print()
        print(f'\n  MaxDD by window (rows) × percentile (cols):')
        print(f"  {'Window':>8}", end='')
        for pc in sorted(df_a['pct'].unique()):
            print(f'  p{pc:>3}', end='')
        print()
        for W in sorted(df_a['window'].unique()):
            print(f'  {W:>6}h  ', end='')
            for pc in sorted(df_a['pct'].unique()):
                try:
                    val = piv_maxdd.loc[W, pc]
                    print(f'  {val:>+5.1%}', end='')
                except Exception:
                    print(f'    nan', end='')
            print()

    # ── [7] Method B summary ──────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  METHOD B — rolling std(zE7) × k')
    print(BAR)
    df_b = df_res[df_res['label'].str.startswith('B_')].copy()
    if len(df_b):
        df_b['window'] = df_b['label'].str.extract(r'W(\d+)h').astype(int)
        df_b['k']      = df_b['label'].str.extract(r'k([0-9.]+)').astype(float)
        piv_calmar_b = df_b.pivot(index='window', columns='k', values='calmar')
        piv_maxdd_b  = df_b.pivot(index='window', columns='k', values='maxdd')
        print(f'\n  Calmar by window (rows) × k (cols):')
        print(f"  {'Window':>8}", end='')
        for kv in sorted(df_b['k'].unique()):
            print(f'  k={kv:.2f}', end='')
        print()
        for W in sorted(df_b['window'].unique()):
            print(f'  {W:>6}h  ', end='')
            for kv in sorted(df_b['k'].unique()):
                try:
                    val = piv_calmar_b.loc[W, kv]
                    print(f'  {val:>+5.2f}', end='')
                except Exception:
                    print(f'    nan', end='')
            print()
        print(f'\n  MaxDD by window (rows) × k (cols):')
        print(f"  {'Window':>8}", end='')
        for kv in sorted(df_b['k'].unique()):
            print(f'  k={kv:.2f}', end='')
        print()
        for W in sorted(df_b['window'].unique()):
            print(f'  {W:>6}h  ', end='')
            for kv in sorted(df_b['k'].unique()):
                try:
                    val = piv_maxdd_b.loc[W, kv]
                    print(f'  {val:>+5.1%}', end='')
                except Exception:
                    print(f'    nan', end='')
            print()

    # ── [8] Efficient frontier ────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  EFFICIENT FRONTIER — best Calmar at each MaxDD cap')
    print(BAR)
    print(f'  {"MaxDD cap":>10}  {"Best Calmar":>12}  {"Return":>9}  {"CAGR":>8}  '
          f'{"Sharpe":>8}  {"Label"}')
    print(SEP)
    for cap in [0.12, 0.14, 0.16, 0.17, 0.18, 0.20, 0.25]:
        subset = df_res[df_res['maxdd'] > -cap]
        if len(subset) == 0:
            print(f'  DD < {cap:.0%}:  no config qualifies')
            continue
        best = subset.iloc[0]
        print(f'  DD < {cap:.0%}:  {best["calmar"]:>+12.3f}  {best["ret_pct"]:>+8.1%}  '
              f'{best["cagr"]:>+7.1%}  {best["sharpe"]:>+8.3f}  {best["label"]}')

    # ── [9] Summary ───────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  TRADEOFF SUMMARY')
    print(BAR)
    print(f'\n  {"Label":<28} {"Calmar":>9} {"Return":>9} {"MaxDD":>8} '
          f'{"Sharpe":>8} {"Blocked":>8} {"T_mean":>8}')
    print(SEP)
    for lbl in ['baseline_no_filter', f'fixed_{ZE7_MIN_FORCE}']:
        row = df_res[df_res['label'] == lbl]
        if len(row):
            r = row.iloc[0]
            print(f'  {r["label"]:<28} {r["calmar"]:>+9.3f} {r["ret_pct"]:>+8.1%} '
                  f'{r["maxdd"]:>+7.2%} {r["sharpe"]:>+8.3f} '
                  f'{r["pct_blocked"]:>7.1%} {r["thresh_mean"]:>8.4f}')
    print(SEP)
    best_overall = df_res.iloc[0]
    best_sharpe  = df_res.sort_values('sharpe', ascending=False).iloc[0]
    best_dd      = df_res.sort_values('maxdd',  ascending=False).iloc[0]
    for r in [best_overall, best_sharpe, best_dd]:
        print(f'  {r["label"]:<28} {r["calmar"]:>+9.3f} {r["ret_pct"]:>+8.1%} '
              f'{r["maxdd"]:>+7.2%} {r["sharpe"]:>+8.3f} '
              f'{r["pct_blocked"]:>7.1%} {r["thresh_mean"]:>8.4f}')

    elapsed = time.time() - t0
    print(f'\n  Total time: {elapsed:.1f}s   Combinations: {total_combos}')
    print(BAR)


if __name__ == '__main__':
    main()
