"""
analyse_trades_cluster.py — Trade-level Feature Engineering + KMeans Clustering
================================================================================
Extracts every individual trade from the champion strategy (layered_daily_no_crash,
CB halt=8%/res=3%/win=180d), attaches rich contextual features, runs KMeans
clustering, and pinpoints which trade patterns drive the MaxDD of −27.13%.

Usage:
    py -3 analyse_trades_cluster.py
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
from collections import deque
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score

from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START
from test_daily_geometry_stop_tp_ohlc   import (
    build_daily_geometry, fetch_futures_ohlcv, get_channel_series,
)
from simulate_adaptive_y_drawdown_brake import INIT
from test_psi_adaptive_y                import BASE
from simulate_master_strategy           import (
    build_positions,
    RT_COST, FUND_HOURLY, HOURS_PER_DAY,
    DYN_K, DYN_DD_SOFT, DYN_DD_STOP, DYN_Y_FLOOR,
)
from simulate_v63_quadrant              import (
    _build_quadrant_multiplier,
    CB_HALT, CB_RESUME, CB_WINDOW_DAYS,
    TRAIL_TRIGGER_MULT, TRAIL_DIST_MULT,
)

BAR     = '=' * 100
SEP     = '-' * 100
TEST_TS = pd.Timestamp(TEST_START)


# ─────────────────────────────────────────────────────────────────────────────
#  MODIFIED SIMULATOR — records every trade
# ─────────────────────────────────────────────────────────────────────────────

def simulate_with_records(
    op, hi, lo, cl,
    hpos_arr, dpos_arr, dactive_arr,
    layered_size,          # p_day['size_mult'] * q_mult — the actual scale used
    psi_size_arr,          # p_day['size_mult'] alone (for feature recording)
    q_mult_arr,            # quadrant multiplier (1.25 or 1.0, for feature recording)
    sl: float, tp: float,
    trail_trigger: float, trail_dist: float,
    hours_index: pd.DatetimeIndex,
    ch_E7, ch_dG, ch_E6, ch_dT,
):
    """Exact replica of simulate_unit_trailing but captures per-trade records."""
    n = len(op)
    ret = np.zeros(n, dtype=float)
    pos = 0.0; size = 1.0; entry = 0.0
    stop_px = 0.0; take_px = 0.0
    trail_active = False; trail_ext = 0.0
    trailing_on  = (trail_trigger > 0 or trail_dist > 0)

    counts = dict(entries=0, exits=0, longs=0, shorts=0,
                  stop=0, tp=0, trail_exit=0, signal_exit=0, close_end=0,
                  skipped_daily_filter=0, psi_blocked=0, active_hours=0)
    trades: list[dict] = []
    cur:   dict | None = None
    psi_list = []

    # Precompute BTC momentum / vol features from the close-price array
    cl_s       = pd.Series(cl.astype(float), index=hours_index)
    btc_r24    = cl_s.pct_change(24).values
    btc_r168   = cl_s.pct_change(168).values
    log_r      = np.log(cl_s / cl_s.shift(1))
    btc_vol24  = log_r.rolling(24).std().values * np.sqrt(24 * 365.25)

    for i in range(n):
        hpos   = hpos_arr[i]; hactive = hpos != 0
        dpos_i = dpos_arr[i]; dact_i  = dactive_arr[i]
        scale  = layered_size[i]

        # daily-filter gating (mirrors simulate_unit_trailing exactly)
        if hactive:
            if dact_i and hpos == dpos_i:
                pass                          # full size
            elif dact_i and hpos != dpos_i:
                hactive = False; hpos = 0
                counts['skipped_daily_filter'] += 1
            else:
                scale *= 0.5                  # inactive-daily → half
        if hactive and scale <= 1e-12:
            hactive = False; hpos = 0
            counts['psi_blocked'] += 1

        # ── manage open position ──
        if pos != 0:
            counts['active_hours'] += 1
            exit_ret = None; reason = None

            if pos > 0:
                if hi[i] >= take_px:
                    exit_ret = take_px / entry - 1; reason = 'tp'
                else:
                    if trailing_on:
                        trail_ext = max(trail_ext, hi[i])
                        if trail_ext / entry - 1.0 >= trail_trigger:
                            trail_active = True
                        if trail_active:
                            ns = trail_ext * (1.0 - trail_dist)
                            if ns > stop_px: stop_px = ns
                    if lo[i] <= stop_px:
                        exit_ret = stop_px / entry - 1
                        reason   = 'trail_exit' if trail_active else 'stop'
            else:  # short
                if lo[i] <= take_px:
                    exit_ret = entry / take_px - 1; reason = 'tp'
                else:
                    if trailing_on:
                        trail_ext = min(trail_ext, lo[i])
                        if entry / trail_ext - 1.0 >= trail_trigger:
                            trail_active = True
                        if trail_active:
                            ns = trail_ext * (1.0 + trail_dist)
                            if ns < stop_px: stop_px = ns
                    if hi[i] >= stop_px:
                        exit_ret = entry / stop_px - 1
                        reason   = 'trail_exit' if trail_active else 'stop'

            if exit_ret is None and hactive and hpos == -pos:
                exit_ret = (op[i] / entry - 1) if pos > 0 else (entry / op[i] - 1)
                reason   = 'signal_exit'; counts['flips'] = counts.get('flips', 0) + 1

            if exit_ret is not None:
                ret[i] += size * (exit_ret - RT_COST)
                counts[reason] = counts.get(reason, 0) + 1
                counts['exits'] += 1
                if cur is not None:
                    holding  = i - cur['_bar']
                    net_pnl  = float(exit_ret) - RT_COST
                    cur.update(dict(
                        exit_time            = hours_index[i],
                        holding_bars         = holding,
                        gross_pnl_pct        = float(exit_ret) * 100,
                        net_pnl_pct          = net_pnl * 100,
                        scaled_pnl           = size * net_pnl * 100,
                        exit_reason          = reason,
                        was_winner           = int(net_pnl > 0),
                        trail_active_at_exit = int(trail_active),
                    ))
                    trades.append(cur); cur = None
                pos = 0; entry = 0; size = 1
                stop_px = 0; take_px = 0
                trail_active = False; trail_ext = 0.0
            else:
                ret[i] -= size * FUND_HOURLY

        # ── open new position ──
        if pos == 0 and hactive:
            ts    = hours_index[i]
            pos   = float(hpos)
            size  = float(layered_size[i])
            entry = float(op[i])
            psi_list.append(float(psi_size_arr[i]))
            trail_active = False; trail_ext = float(op[i])
            if pos > 0:
                stop_px = entry * (1.0 - sl); take_px = entry * (1.0 + tp)
                counts['longs'] += 1
            else:
                stop_px = entry * (1.0 + sl); take_px = entry * (1.0 - tp)
                counts['shorts'] += 1
            counts['entries'] += 1

            ie7 = float(ch_E7.iloc[i]) if i < len(ch_E7) else 0.0
            idg = float(ch_dG.iloc[i]) if i < len(ch_dG) else 0.0
            ie6 = float(ch_E6.iloc[i]) if i < len(ch_E6) else 0.0
            idt = float(ch_dT.iloc[i]) if i < len(ch_dT) else 0.0
            r24  = float(btc_r24[i])  if not np.isnan(btc_r24[i])  else 0.0
            r168 = float(btc_r168[i]) if not np.isnan(btc_r168[i]) else 0.0
            v24  = float(btc_vol24[i])if not np.isnan(btc_vol24[i])else 0.0

            cur = dict(
                _bar          = i,
                entry_time    = ts,
                is_oos        = int(ts >= TEST_TS),
                direction     = int(pos),
                size          = float(size),
                psi_y         = float(psi_size_arr[i]),      # Ψ sizing component
                q_mult        = float(q_mult_arr[i]),         # quadrant multiplier
                entry_price   = float(entry),
                # BSDT channel z-scores at entry
                zE7           = ie7,
                zdG           = idg,
                zE6           = ie6,
                zdT           = idt,
                comp          = (ie7 + ie6) / 2.0,
                abs_zE7       = abs(ie7),
                abs_zdG       = abs(idg),
                abs_zE6       = abs(ie6),
                abs_zdT       = abs(idt),
                channel_mag   = (abs(ie7) + abs(idg) + abs(ie6) + abs(idt)) / 4.0,
                # cyclic time encoding
                hour          = ts.hour,
                hour_sin      = np.sin(2 * np.pi * ts.hour / 24),
                hour_cos      = np.cos(2 * np.pi * ts.hour / 24),
                dow           = ts.dayofweek,
                dow_sin       = np.sin(2 * np.pi * ts.dayofweek / 7),
                dow_cos       = np.cos(2 * np.pi * ts.dayofweek / 7),
                month         = ts.month,
                month_sin     = np.sin(2 * np.pi * ts.month / 12),
                month_cos     = np.cos(2 * np.pi * ts.month / 12),
                year          = ts.year,
                # BTC market regime at entry
                btc_ret_24h   = r24,
                btc_ret_7d    = r168,
                btc_annvol    = v24,
            )

    # close at end of series
    if pos != 0:
        i = n - 1
        gross   = (cl[i] / entry - 1) if pos > 0 else (entry / cl[i] - 1)
        net_pnl = gross - RT_COST
        ret[i] += size * net_pnl
        counts['close_end'] += 1; counts['exits'] += 1
        if cur is not None:
            cur.update(dict(
                exit_time=hours_index[i], holding_bars=n - 1 - cur['_bar'],
                gross_pnl_pct=gross * 100, net_pnl_pct=net_pnl * 100,
                scaled_pnl=size * net_pnl * 100, exit_reason='close_end',
                was_winner=int(net_pnl > 0), trail_active_at_exit=int(trail_active),
            ))
            trades.append(cur)

    counts['avg_psi_y'] = float(np.mean(psi_list)) if psi_list else 0.0
    return ret, counts, trades


# ─────────────────────────────────────────────────────────────────────────────
#  CB CONTEXT REPLAY (equity state at each trade entry)
# ─────────────────────────────────────────────────────────────────────────────

def add_cb_context(trade_df: pd.DataFrame, unit_ret: pd.Series,
                   hours_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Replay the CB engine bar-by-bar; tag each trade with equity state at entry."""
    window_bars = CB_WINDOW_DAYS * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq = INIT; peak_ath = INIT; halted = False

    eq_map:        dict = {}
    roll_peak_map: dict = {}
    ath_dd_map:    dict = {}
    cb_dd_map:     dict = {}
    halted_map:    dict = {}

    for bar_i in range(len(unit_ret)):
        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_ath, 1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak, 1e-12))

        if not halted and cb_dd >= CB_HALT:  halted = True
        elif  halted and cb_dd <= CB_RESUME: halted = False

        if halted:
            y = 0.0
        elif dd_aty <= DYN_DD_SOFT:
            y = 1.0
        elif dd_aty >= DYN_DD_STOP:
            y = DYN_Y_FLOOR
        else:
            y = DYN_Y_FLOOR + (1.0 - DYN_Y_FLOOR) * (DYN_DD_STOP - dd_aty) / (DYN_DD_STOP - DYN_DD_SOFT)

        r  = DYN_K * y * float(unit_ret.iloc[bar_i])
        r  = max(r, -0.95)
        eq *= (1.0 + r)
        peak_ath = max(peak_ath, eq)

        ts = hours_index[bar_i]
        eq_map[ts]        = eq
        roll_peak_map[ts] = roll_peak
        ath_dd_map[ts]    = dd_aty
        cb_dd_map[ts]     = cb_dd
        halted_map[ts]    = int(halted)

    df = trade_df.copy()
    et = df['entry_time']
    df['eq_at_entry']        = et.map(eq_map).fillna(INIT)
    df['roll_peak_at_entry'] = et.map(roll_peak_map).fillna(INIT)
    df['ath_dd_at_entry']    = et.map(ath_dd_map).fillna(0.0)
    df['cb_dd_at_entry']     = et.map(cb_dd_map).fillna(0.0)
    df['cb_halted_at_entry'] = et.map(halted_map).fillna(0)   # should be 0 (can't enter when halted)
    return df


# ─────────────────────────────────────────────────────────────────────────────
#  EQUITY REPLAY (to get drawdown curve / MaxDD window)
# ─────────────────────────────────────────────────────────────────────────────

def replay_equity(unit_ret: pd.Series) -> pd.Series:
    """Replay the full K×Ψ×CB engine and return the equity Series."""
    window_bars = CB_WINDOW_DAYS * HOURS_PER_DAY
    mono_dq: deque = deque()
    eq = INIT; peak_ath = INIT; halted = False
    eq_vals = []

    for bar_i, ur in enumerate(unit_ret.values):
        while mono_dq and mono_dq[0][0] <= bar_i - window_bars:
            mono_dq.popleft()
        while mono_dq and mono_dq[-1][1] <= eq:
            mono_dq.pop()
        mono_dq.append((bar_i, eq))
        roll_peak = mono_dq[0][1]

        dd_aty = max(0.0, 1.0 - eq / max(peak_ath,  1e-12))
        cb_dd  = max(0.0, 1.0 - eq / max(roll_peak, 1e-12))

        if not halted and cb_dd >= CB_HALT:  halted = True
        elif  halted and cb_dd <= CB_RESUME: halted = False

        if halted:
            y = 0.0
        elif dd_aty <= DYN_DD_SOFT:
            y = 1.0
        elif dd_aty >= DYN_DD_STOP:
            y = DYN_Y_FLOOR
        else:
            y = DYN_Y_FLOOR + (1.0-DYN_Y_FLOOR)*(DYN_DD_STOP-dd_aty)/(DYN_DD_STOP-DYN_DD_SOFT)

        r  = max(DYN_K * y * float(ur), -0.95)
        eq *= (1.0 + r)
        peak_ath = max(peak_ath, eq)
        eq_vals.append(eq)

    return pd.Series(eq_vals, index=unit_ret.index)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(BAR)
    print('  TRADE-LEVEL CLUSTERING ANALYSIS')
    print('  Champion: layered_daily_no_crash  CB=halt8%/res3%/win180d')
    print('  Goal: identify which trade PATTERN is responsible for MaxDD −27.13%')
    print(BAR)

    # ── [1] Build geometry, positions, quadrant multiplier ────────────────────
    print('\n[1] Building geometry + positions ...')
    df_1h, comp_raw, calib_mask = build_daily_geometry()
    ch       = get_channel_series()        # {E7, dG, E6, dT}
    ohlc_all = fetch_futures_ohlcv()
    p        = build_positions(df_1h, comp_raw, calib_mask, ohlc_all)
    q_mult   = _build_quadrant_multiplier(ch, p['hours'])
    layered_size = p['size_mult'] * q_mult

    sl            = BASE['sl_mult']         * p['daily_vol']
    tp            = BASE['tp_mult']         * p['daily_vol']
    trail_trigger = TRAIL_TRIGGER_MULT      * p['daily_vol']
    trail_dist    = TRAIL_DIST_MULT         * p['daily_vol']
    print(f'  daily_vol={p["daily_vol"]:.3%}  sl={sl:.3%}  tp={tp:.3%}')
    print(f'  trail_trigger={trail_trigger:.3%}  trail_dist={trail_dist:.3%}')
    print(f'  CB: halt={CB_HALT:.0%}  resume={CB_RESUME:.0%}  window={CB_WINDOW_DAYS}d')

    # ── [2] Run simulation, capture every trade ───────────────────────────────
    print('\n[2] Simulating with trade recorder ...')
    unit_arr, cnts, trades = simulate_with_records(
        p['op'], p['hi'], p['lo'], p['cl'],
        p['hpos'], p['dpos'], p['dactive'],
        layered_size, p['size_mult'], q_mult,
        sl, tp, trail_trigger, trail_dist,
        p['hours'],
        ch['E7'], ch['dG'], ch['E6'], ch['dT'],
    )
    unit_series = pd.Series(unit_arr, index=p['hours'])
    print(f'  {len(trades)} trades  |  entries={cnts["entries"]}  exits={cnts["exits"]}')
    print(f'  Stops={cnts.get("stop",0)}  TPs={cnts.get("tp",0)}  '
          f'Trails={cnts.get("trail_exit",0)}  Flips={cnts.get("signal_exit",0)}  '
          f'TimeEnd={cnts.get("close_end",0)}')

    # ── [3] Assemble DataFrame + add CB context ───────────────────────────────
    print('\n[3] Building trade DataFrame + CB equity context ...')
    df = pd.DataFrame(trades)
    df.drop(columns=['_bar'], errors='ignore', inplace=True)
    df = add_cb_context(df, unit_series, p['hours'])
    df['trade_id'] = range(len(df))

    oos = df['is_oos'] == 1
    print(f'  Rows={len(df)}  cols={len(df.columns)}')
    print(f'  Train trades : {(~oos).sum()}   OOS trades: {oos.sum()}')
    print(f'  Win rate     : {df["was_winner"].mean():.1%}  '
          f'(train {df.loc[~oos,"was_winner"].mean():.1%}  '
          f'OOS {df.loc[oos,"was_winner"].mean():.1%})')
    print(f'  Avg net P&L  : {df["net_pnl_pct"].mean():+.4f}%  '
          f'Std={df["net_pnl_pct"].std():.4f}%')
    print(f'  Avg hold (h) : {df["holding_bars"].mean():.1f}  '
          f'median={df["holding_bars"].median():.0f}  '
          f'max={df["holding_bars"].max()}')

    print(f'\n  Exit breakdown (all trades):')
    for reason, grp in df.groupby('exit_reason'):
        wp  = grp['was_winner'].mean()
        ap  = grp['net_pnl_pct'].mean()
        sp  = grp['net_pnl_pct'].sum()
        print(f'    {reason:<20}  n={len(grp):>5} ({len(grp)/len(df):>5.1%})  '
              f'win={wp:.1%}  avgPnL={ap:+.4f}%  sumPnL={sp:+.2f}%')

    print(f'\n  Direction breakdown:')
    for d, grp in df.groupby('direction'):
        dname = 'LONG' if d == 1 else 'SHORT'
        wp  = grp['was_winner'].mean()
        ap  = grp['net_pnl_pct'].mean()
        sp  = grp['net_pnl_pct'].sum()
        print(f'    {dname}   n={len(grp):>5} ({len(grp)/len(df):>5.1%})  '
              f'win={wp:.1%}  avgPnL={ap:+.4f}%  sumPnL={sp:+.2f}%')

    # ── [4] Feature engineering for clustering ────────────────────────────────
    print('\n[4] Engineering clustering features ...')
    # Entry-time features only — outcome columns NOT used as cluster features
    feat_cols = [
        # BSDT signal
        'zE7', 'zdG', 'zE6', 'zdT',          # signed z-scores
        'abs_zE7', 'abs_zdG', 'abs_zE6',       # magnitude (unsigned)
        'comp',                                 # composite hourly signal
        'channel_mag',                          # avg abs magnitude across all 4
        # Strategy state
        'direction',                            # +1 long / −1 short
        'q_mult',                               # GH,TH boost active?
        'psi_y',                                # Ψ sizing
        # Time (cyclic encoded to avoid ordinal breaks)
        'hour_sin', 'hour_cos',
        'dow_sin',  'dow_cos',
        'month_sin','month_cos',
        # Market regime at entry
        'btc_ret_24h', 'btc_ret_7d',
        'btc_annvol',
        # Drawdown regime at entry
        'ath_dd_at_entry',
        'cb_dd_at_entry',
    ]
    X_raw = df[feat_cols].fillna(0.0).values
    scaler = StandardScaler()
    X      = scaler.fit_transform(X_raw)
    print(f'  Feature matrix: {X.shape}  ({len(feat_cols)} features)')

    # ── [5] PCA — variance decomposition ──────────────────────────────────────
    print('\n[5] PCA variance decomposition ...')
    pca_full  = PCA().fit(X)
    cum_var   = np.cumsum(pca_full.explained_variance_ratio_)
    n_90      = int(np.argmax(cum_var >= 0.90)) + 1
    n_80      = int(np.argmax(cum_var >= 0.80)) + 1
    print(f'  Variance explained cumulation:')
    for k in range(1, min(10, len(feat_cols)) + 1):
        ev  = pca_full.explained_variance_ratio_[k-1]
        cev = cum_var[k-1]
        bar_v = '#' * int(ev * 200)
        print(f'    PC{k:>2}: {ev:.3f}  (cum {cev:.3f})  {bar_v}')
    print(f'  → {n_80} components for 80% variance  |  {n_90} components for 90%')

    n_pca = min(n_90, 12)
    pca   = PCA(n_components=n_pca, random_state=42)
    X_pca = pca.fit_transform(X)

    # PCA loadings — what drives PC1 and PC2?
    pc1_loads = pd.Series(pca.components_[0], index=feat_cols)
    pc2_loads = pd.Series(pca.components_[1], index=feat_cols)
    print(f'\n  PC1 top positive: {", ".join(pc1_loads.nlargest(4).index.tolist())}')
    print(f'  PC1 top negative: {", ".join(pc1_loads.nsmallest(4).index.tolist())}')
    print(f'  PC2 top positive: {", ".join(pc2_loads.nlargest(4).index.tolist())}')
    print(f'  PC2 top negative: {", ".join(pc2_loads.nsmallest(4).index.tolist())}')

    # ── [6] KMeans sweep (k=3..7) ─────────────────────────────────────────────
    print('\n[6] KMeans sweep (k=3 → 7) ...')
    km_results: dict = {}
    samp = min(len(X_pca), 2000, len(X_pca))
    for k in range(3, 8):
        km     = KMeans(n_clusters=k, random_state=42, n_init=30, max_iter=500)
        labels = km.fit_predict(X_pca)
        sil    = silhouette_score(X_pca, labels,
                                  sample_size=min(samp, len(X_pca)), random_state=42)
        km_results[k] = dict(km=km, labels=labels, sil=sil, inertia=km.inertia_)
        print(f'  k={k}: inertia={km.inertia_:>10.1f}  silhouette={sil:>+.5f}')

    best_k  = max(km_results, key=lambda k: km_results[k]['sil'])
    print(f'\n  Best k by silhouette: k={best_k}  (sil={km_results[best_k]["sil"]:.5f})')
    labels  = km_results[best_k]['labels']
    df['cluster'] = labels
    df['pc1']     = X_pca[:, 0]
    df['pc2']     = X_pca[:, 1]
    df['pc3']     = X_pca[:, 2] if X_pca.shape[1] > 2 else 0.0

    # ── [7] Cluster summary table ─────────────────────────────────────────────
    print(f'\n{"─"*100}')
    print(f'  CLUSTER SUMMARY  (k={best_k}, all {len(df)} trades)')
    print(f'{"─"*100}')
    hdr = (f"  {'C':>2} {'N':>5} {'%':>5} {'Win%':>6} {'AvgPnL%':>9} "
           f"{'SumPnL%':>9} {'AvgHld':>7} {'Long%':>6} "
           f"{'zE7':>6} {'zdG':>6} {'zE6':>6} {'zdT':>6} "
           f"{'btcM24':>7} {'dd@ent':>7} {'q_mlt':>6} {'ExitMode':>12}")
    print(hdr); print(f'  {"─"*96}')

    cstats = []
    for c in sorted(df['cluster'].unique()):
        g   = df[df['cluster'] == c]
        n_c = len(g)
        wp  = g['was_winner'].mean()
        ap  = g['net_pnl_pct'].mean()
        sp  = g['net_pnl_pct'].sum()
        ah  = g['holding_bars'].mean()
        lp  = (g['direction'] == 1).mean()
        e7  = g['zE7'].mean()
        dg  = g['zdG'].mean()
        e6  = g['zE6'].mean()
        dt  = g['zdT'].mean()
        bm  = g['btc_ret_24h'].mean() * 100
        dd  = g['ath_dd_at_entry'].mean() * 100
        qm  = g['q_mult'].mean()
        em  = g['exit_reason'].value_counts().idxmax()
        print(f"  {c:>2}  {n_c:>5}  {n_c/len(df):>4.1%}  {wp:>5.1%}  "
              f"{ap:>+8.3f}%  {sp:>+8.2f}%  {ah:>6.1f}  {lp:>5.1%}  "
              f"{e7:>+5.3f} {dg:>+5.3f} {e6:>+5.3f} {dt:>+5.3f}  "
              f"{bm:>+6.2f}%  {dd:>6.2f}%  {qm:>5.3f}  {em:>12}")
        cstats.append(dict(
            cluster=c, n=n_c, win_pct=wp, avg_pnl=ap, sum_pnl=sp,
            avg_hold=ah, long_pct=lp, mean_e7=e7, mean_dg=dg,
            mean_qm=qm, exit_mode=em, mean_dd=dd, mean_btc=bm,
        ))

    cdf         = pd.DataFrame(cstats).sort_values('avg_pnl')
    worst_c     = int(cdf.iloc[0]['cluster'])
    best_c      = int(cdf.iloc[-1]['cluster'])
    mid_c       = int(cdf.iloc[len(cdf)//2]['cluster'])
    print(f'\n  Worst cluster : C{worst_c}  avgPnL={cdf.iloc[0]["avg_pnl"]:+.3f}%  '
          f'n={cdf.iloc[0]["n"]:.0f}  win={cdf.iloc[0]["win_pct"]:.1%}')
    print(f'  Best  cluster : C{best_c}  avgPnL={cdf.iloc[-1]["avg_pnl"]:+.3f}%  '
          f'n={cdf.iloc[-1]["n"]:.0f}  win={cdf.iloc[-1]["win_pct"]:.1%}')

    # ── [8] Worst-cluster deep dive ────────────────────────────────────────────
    print(f'\n[8] WORST CLUSTER C{worst_c} — deep dive')
    wc   = df[df['cluster'] == worst_c]
    rest = df[df['cluster'] != worst_c]

    compare_feats = [
        ('zE7',            'zE7 (velocity/impulse)'),
        ('zdG',            'zdG (structural novelty)'),
        ('zE6',            'zE6 (systemic distortion)'),
        ('zdT',            'zdT (temporal rarity)'),
        ('abs_zE7',        '|zE7| magnitude'),
        ('channel_mag',    'avg channel magnitude'),
        ('btc_ret_24h',    'BTC 24h return'),
        ('btc_ret_7d',     'BTC 7d return'),
        ('btc_annvol',     'BTC ann. vol (24h)'),
        ('ath_dd_at_entry','ATH drawdown at entry'),
        ('cb_dd_at_entry', 'CB rolling-peak DD'),
        ('psi_y',          'Ψ sizing'),
        ('q_mult',         'quadrant multiplier'),
        ('holding_bars',   'holding bars (outcome)'),
    ]
    print(f'\n  {"Feature":<32} {"Worst C":>10} {"Rest":>10} {"Diff":>10}')
    print(f'  {"─"*66}')
    for col, label in compare_feats:
        wm = wc[col].mean()
        rm = rest[col].mean()
        diff = wm - rm
        marker = ' <<<' if abs(diff) > 0.3 * (abs(wm) + abs(rm) + 1e-9) else ''
        print(f'  {label:<32} {wm:>10.4f} {rm:>10.4f} {diff:>+10.4f}{marker}')

    print(f'\n  Worst-C exit breakdown:')
    for reason, grp in wc.groupby('exit_reason'):
        pct = len(grp) / len(wc)
        wp  = grp['was_winner'].mean()
        ap  = grp['net_pnl_pct'].mean()
        print(f'    {reason:<20}  n={len(grp):>4} ({pct:>5.1%})  win={wp:.1%}  avgPnL={ap:+.4f}%')

    print(f'\n  Worst-C direction breakdown:')
    for d, grp in wc.groupby('direction'):
        dn = 'LONG' if d == 1 else 'SHORT'
        wp = grp['was_winner'].mean()
        ap = grp['net_pnl_pct'].mean()
        sp = grp['net_pnl_pct'].sum()
        print(f'    {dn}:  n={len(grp):>4} ({len(grp)/len(wc):.1%})  '
              f'win={wp:.1%}  avgPnL={ap:+.4f}%  sumPnL={sp:+.2f}%')

    print(f'\n  Worst-C yearly distribution:')
    wc2 = wc.copy()
    wc2['yr'] = pd.to_datetime(wc2['entry_time']).dt.year
    for yr, grp in wc2.groupby('yr'):
        ap = grp['net_pnl_pct'].mean()
        sp = grp['net_pnl_pct'].sum()
        print(f'    {yr}: n={len(grp):>4}  avgPnL={ap:+.4f}%  sumPnL={sp:+.2f}%')

    # ── [9] OOS-only analysis ─────────────────────────────────────────────────
    print(f'\n[9] OOS PERIOD ANALYSIS (2023→Apr 2026) ...')
    df_oos = df[df['is_oos'] == 1].copy()
    df_oos['yr'] = pd.to_datetime(df_oos['entry_time']).dt.year
    print(f'  OOS trades: {len(df_oos)}')
    print(f'  Win rate  : {df_oos["was_winner"].mean():.1%}')
    print(f'  Avg P&L   : {df_oos["net_pnl_pct"].mean():+.4f}%  '
          f'Sum={df_oos["net_pnl_pct"].sum():+.2f}%')

    print(f'\n  OOS cluster summary:')
    hdr2 = (f"  {'C':>2} {'N':>5} {'Win%':>6} {'AvgPnL%':>9} "
            f"{'SumPnL%':>9} {'AvgHld':>7} {'ExitMode':>12}")
    print(hdr2); print(f'  {"─"*65}')
    for c in sorted(df_oos['cluster'].unique()):
        g = df_oos[df_oos['cluster'] == c]
        em = g['exit_reason'].value_counts().idxmax()
        print(f"  {c:>2}  {len(g):>5}  {g['was_winner'].mean():>5.1%}  "
              f"{g['net_pnl_pct'].mean():>+8.4f}%  "
              f"{g['net_pnl_pct'].sum():>+8.2f}%  "
              f"{g['holding_bars'].mean():>6.1f}  {em:>12}")

    print(f'\n  OOS yearly breakdown:')
    print(f"  {'Year':>6} {'N':>5} {'Win%':>6} {'AvgPnL%':>9} {'SumPnL%':>9}")
    print(f'  {"─"*40}')
    for yr, g in df_oos.groupby('yr'):
        print(f"  {yr:>6}  {len(g):>5}  {g['was_winner'].mean():>5.1%}  "
              f"{g['net_pnl_pct'].mean():>+8.4f}%  {g['net_pnl_pct'].sum():>+8.2f}%")

    # ── [10] MaxDD window identification ─────────────────────────────────────
    print(f'\n[10] MaxDD WINDOW ANALYSIS ...')
    eq_curve = replay_equity(unit_series)
    eq_oos   = eq_curve[eq_curve.index >= TEST_TS]
    roll_max = eq_oos.cummax()
    dd_curve = (eq_oos - roll_max) / roll_max * 100

    trough_ts  = dd_curve.idxmin()
    maxdd_val  = dd_curve.min()
    peak_ts    = eq_oos[:trough_ts].idxmax()

    # Find secondary drawdown troughs > 5%
    significant_dds = dd_curve[dd_curve < -5.0]
    print(f'  OOS Equity: ${eq_oos.iloc[0]:.0f} → ${eq_oos.iloc[-1]:.0f}')
    print(f'  MaxDD: {maxdd_val:+.2f}%  (peak {peak_ts.date()} → trough {trough_ts.date()})')
    print(f'  Bars below −5% DD: {len(significant_dds)} / {len(eq_oos)} '
          f'({len(significant_dds)/len(eq_oos):.1%} of OOS)')

    # Tag trades as "in drawdown zone"
    df_oos2 = df_oos.copy()
    df_oos2['entry_dt'] = pd.to_datetime(df_oos2['entry_time'])
    df_oos2['dd_at_entry_pct'] = df_oos2['entry_dt'].apply(
        lambda t: float(dd_curve.get(t, dd_curve.asof(t) if t in dd_curve.index else 0.0))
    )
    df_oos2['in_maxdd_window'] = (
        (df_oos2['entry_dt'] >= peak_ts) &
        (df_oos2['entry_dt'] <= trough_ts)
    )
    dd_window_trades = df_oos2[df_oos2['in_maxdd_window']]
    print(f'\n  Trades IN MaxDD window ({peak_ts.date()}→{trough_ts.date()}): '
          f'{len(dd_window_trades)} / {len(df_oos2)} total OOS')

    if len(dd_window_trades) > 0:
        print(f'\n  MaxDD-window trade stats:')
        print(f'    Win rate:  {dd_window_trades["was_winner"].mean():.1%}')
        print(f'    Avg P&L:   {dd_window_trades["net_pnl_pct"].mean():+.4f}%')
        print(f'    Sum P&L:   {dd_window_trades["net_pnl_pct"].sum():+.2f}%')

        print(f'\n  MaxDD-window cluster distribution:')
        for c, g in dd_window_trades.groupby('cluster'):
            print(f'    C{c}: n={len(g):>4} ({len(g)/len(dd_window_trades):.1%})  '
                  f'win={g["was_winner"].mean():.1%}  avgPnL={g["net_pnl_pct"].mean():+.4f}%'
                  f'  sumPnL={g["net_pnl_pct"].sum():+.2f}%')

        print(f'\n  MaxDD-window exit reasons:')
        for reason, g in dd_window_trades.groupby('exit_reason'):
            print(f'    {reason:<20}  n={len(g):>4} ({len(g)/len(dd_window_trades):.1%})  '
                  f'win={g["was_winner"].mean():.1%}  avgPnL={g["net_pnl_pct"].mean():+.4f}%')

        print(f'\n  MaxDD-window direction:')
        for d, g in dd_window_trades.groupby('direction'):
            dn = 'LONG' if d == 1 else 'SHORT'
            print(f'    {dn}:  n={len(g):>4}  win={g["was_winner"].mean():.1%}  '
                  f'avgPnL={g["net_pnl_pct"].mean():+.4f}%  '
                  f'sumPnL={g["net_pnl_pct"].sum():+.2f}%')

        print(f'\n  10 worst individual trades in MaxDD window:')
        hdr3 = (f"  {'Entry':>17} {'Exit':>17} {'D':>2} "
                f"{'Hold':>5} {'PnL%':>8} {'Reason':>12} {'C':>2} "
                f"{'zE7':>6} {'zdG':>6} {'BM24':>6}")
        print(hdr3); print(f'  {"─"*90}')
        worst_t = dd_window_trades.nsmallest(10, 'net_pnl_pct')
        for _, r in worst_t.iterrows():
            dn = 'L' if r['direction'] == 1 else 'S'
            print(f"  {str(r['entry_time'])[:16]:>17}  "
                  f"{str(r['exit_time'])[:16]:>17}  {dn:>2}  "
                  f"{int(r['holding_bars']):>4}h  {r['net_pnl_pct']:>+7.3f}%  "
                  f"{r['exit_reason']:>12}  C{int(r['cluster']):>1}  "
                  f"{r['zE7']:>+5.3f}  {r['zdG']:>+5.3f}  "
                  f"{r['btc_ret_24h']*100:>+5.2f}%")

    # ── [11] Regime analysis — what state was the market in during MaxDD? ─────
    print(f'\n[11] MARKET REGIME DURING MaxDD WINDOW ...')
    print(f'  (Comparing channel z-scores: MaxDD-window vs non-MaxDD OOS trades)')
    non_dd_oos = df_oos2[~df_oos2['in_maxdd_window']]
    if len(dd_window_trades) > 0 and len(non_dd_oos) > 0:
        regime_feats = ['zE7', 'zdG', 'zE6', 'zdT', 'abs_zE7', 'channel_mag',
                        'btc_ret_24h', 'btc_ret_7d', 'btc_annvol',
                        'ath_dd_at_entry', 'cb_dd_at_entry', 'psi_y', 'q_mult']
        print(f'  {"Feature":<32} {"MaxDD-window":>14} {"Rest of OOS":>12} {"Diff":>10}')
        print(f'  {"─"*72}')
        for col in regime_feats:
            if col in dd_window_trades.columns and col in non_dd_oos.columns:
                dm = dd_window_trades[col].mean()
                rm = non_dd_oos[col].mean()
                diff = dm - rm
                marker = ' <<< REGIME SHIFT' if abs(diff) > 0.2 * (abs(dm) + abs(rm) + 1e-9) else ''
                print(f'  {col:<32} {dm:>14.4f} {rm:>12.4f} {diff:>+10.4f}{marker}')

    # ── [12] Filter hypothesis ────────────────────────────────────────────────
    print(f'\n[12] FILTER HYPOTHESIS: removing worst cluster C{worst_c}')
    non_worst  = df_oos[df_oos['cluster'] != worst_c]
    worst_only = df_oos[df_oos['cluster'] == worst_c]
    print(f'  All OOS trades:           n={len(df_oos):>4}  avgPnL={df_oos["net_pnl_pct"].mean():+.4f}%  '
          f'win={df_oos["was_winner"].mean():.1%}  sumPnL={df_oos["net_pnl_pct"].sum():+.2f}%')
    print(f'  Without C{worst_c}:           n={len(non_worst):>4}  '
          f'avgPnL={non_worst["net_pnl_pct"].mean():+.4f}%  '
          f'win={non_worst["was_winner"].mean():.1%}  '
          f'sumPnL={non_worst["net_pnl_pct"].sum():+.2f}%')
    print(f'  C{worst_c} alone:              n={len(worst_only):>4}  '
          f'avgPnL={worst_only["net_pnl_pct"].mean():+.4f}%  '
          f'win={worst_only["was_winner"].mean():.1%}  '
          f'sumPnL={worst_only["net_pnl_pct"].sum():+.2f}%')
    cutback_pct = len(worst_only) / len(df_oos) * 100
    print(f'\n  Removing C{worst_c} cuts {cutback_pct:.1f}% of OOS trades.')
    print(f'  → Key C{worst_c} signature vs rest (what rule could filter it):')

    for col, label in compare_feats:
        if col in df_oos.columns:
            wm = worst_only[col].mean()
            rm = non_worst[col].mean()
            diff = wm - rm
            if abs(diff) > 0.5 * df_oos[col].std():
                rule_hint = ''
                if abs(wm) < abs(rm) and abs(diff / (df_oos[col].std() + 1e-9)) > 0.3:
                    rule_hint = f'  → filter: |{col}| < {abs(wm):.3f}'
                elif wm > rm:
                    rule_hint = f'  → filter: {col} > {rm + abs(diff)*0.5:.3f}'
                else:
                    rule_hint = f'  → filter: {col} < {rm - abs(diff)*0.5:.3f}'
                print(f'    {label:<32} worst={wm:>8.4f}  rest={rm:>8.4f}  '
                      f'diff={diff:>+8.4f}{rule_hint}')

    # ── Save ──────────────────────────────────────────────────────────────────
    out_path = Path(OUT_DIR) / 'trade_cluster_analysis.csv'
    df.to_csv(out_path, index=False)
    print(f'\n  Full trade DataFrame saved → {out_path}')
    print(f'  Columns: {sorted(df.columns.tolist())}')

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print(f'\n{BAR}')
    print('  FINDINGS SUMMARY')
    print(BAR)
    print(f'  Total trades (all history): {len(df)}  '
          f'(train={len(df)-len(df_oos)}  OOS={len(df_oos)})')
    print(f'  Overall win rate: {df["was_winner"].mean():.1%}  '
          f'OOS win rate: {df_oos["was_winner"].mean():.1%}')
    print(f'  KMeans best k={best_k}  silhouette={km_results[best_k]["sil"]:.5f}')
    print(f'  Cluster rank by OOS avg P&L:')
    oos_cdf = df_oos.groupby('cluster').agg(
        n=('net_pnl_pct','count'),
        win_pct=('was_winner','mean'),
        avg_pnl=('net_pnl_pct','mean'),
    ).sort_values('avg_pnl')
    for c, row in oos_cdf.iterrows():
        marker = ' ← WORST (MaxDD driver)' if c == worst_c else (' ← BEST' if c == best_c else '')
        print(f'    C{c}: n={row["n"]:>4}  win={row["win_pct"]:.1%}  '
              f'avgPnL={row["avg_pnl"]:+.4f}%{marker}')
    print(f'  MaxDD window: {peak_ts.date()} → {trough_ts.date()}  ({maxdd_val:+.2f}%)')
    if len(dd_window_trades) > 0:
        print(f'  MaxDD-window trades: {len(dd_window_trades)}  '
              f'win={dd_window_trades["was_winner"].mean():.1%}  '
              f'sumPnL={dd_window_trades["net_pnl_pct"].sum():+.2f}%')
    print(BAR)


if __name__ == '__main__':
    main()
