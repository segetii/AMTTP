"""
diagnose_wrong_trades.py — Engine Misfire Forensics
=====================================================
Loads the trade CSV and asks: WHERE exactly did the engine get it wrong?
Focuses on:
 1. Stop-hit anatomy — what BSDT was saying at entry
 2. Direction error — entered wrong way relative to next-bar BTC move
 3. Zero-signal entries — comp≈0 entries that became stops
 4. 2025 regime breakdown — what changed
 5. Actual market events during the 10 worst stop-clusters
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
from run_crypto_pairs_v34_full_combined import OUT_DIR, TEST_START

BAR = '=' * 100
SEP = '-' * 100

CSV = Path(OUT_DIR) / 'trade_cluster_analysis.csv'
df  = pd.read_csv(CSV, parse_dates=['entry_time', 'exit_time'])
df['yr']     = df['entry_time'].dt.year
df['month']  = df['entry_time'].dt.month
df['is_stop']= (df['exit_reason'] == 'stop').astype(int)

oos = df[df['is_oos'] == 1].copy()
oos_stops = oos[oos['exit_reason'] == 'stop']
oos_wins  = oos[oos['was_winner'] == 1]
oos_loss  = oos[oos['was_winner'] == 0]

print(BAR)
print('  ENGINE MISFIRE FORENSICS')
print(BAR)

# ─── [1] STOP ANATOMY — what was BSDT saying? ────────────────────────────────
print('\n[1] STOP-HIT ANATOMY — BSDT z-scores at entry (OOS)')
print(f'  Total OOS stops: {len(oos_stops)} / {len(oos)} trades ({len(oos_stops)/len(oos):.1%})')

print(f'\n  Distribution of |comp| at stop entries vs winners:')
bins = [0.0, 0.10, 0.25, 0.50, 0.75, 1.0, 2.0, 999]
labels = ['0–0.10', '0.10–0.25', '0.25–0.50', '0.50–0.75', '0.75–1.0', '1.0–2.0', '>2.0']
oos['comp_abs'] = oos['comp'].abs()
oos_stops2 = oos[oos['is_stop'] == 1]
oos_nowins = oos[oos['is_stop'] == 0]
print(f'  {"Bin":>12}  {"Stop n":>8}  {"NotStop n":>10}  {"Stop%":>8}  {"AvgPnL(stop)":>14}')
print(f'  {"─"*60}')
for i, (lo, hi) in enumerate(zip(bins[:-1], bins[1:])):
    s   = oos_stops2[(oos_stops2['comp_abs'] >= lo) & (oos_stops2['comp_abs'] < hi)]
    ns  = oos_nowins[(oos_nowins['comp_abs'] >= lo) & (oos_nowins['comp_abs'] < hi)]
    tot = len(s) + len(ns)
    sp  = len(s) / max(tot, 1)
    ap  = s['net_pnl_pct'].mean() if len(s) > 0 else 0.0
    print(f'  {labels[i]:>12}  {len(s):>8}  {len(ns):>10}  {sp:>7.1%}  {ap:>+12.4f}%')

print(f'\n  |zE7| distribution at OOS stops:')
print(f'  {"Bin":>12}  {"Stop n":>8}  {"% of stops":>12}')
print(f'  {"─"*40}')
oos_stops2['abs_zE7_cat'] = pd.cut(
    oos_stops2['abs_zE7'], bins=[0, 0.05, 0.20, 0.50, 1.0, 999],
    labels=['~zero(0–0.05)', 'low(0.05–0.2)', 'med(0.2–0.5)', 'high(0.5–1.0)', 'extreme(>1.0)']
)
for cat, g in oos_stops2.groupby('abs_zE7_cat', observed=True):
    print(f'  {str(cat):>20}  {len(g):>8}  {len(g)/len(oos_stops2):>11.1%}')

# ─── [2] DIRECTION ERRORS ─────────────────────────────────────────────────────
print(f'\n[2] DIRECTION ERROR ANALYSIS (OOS)')
print(f'  "Wrong direction" = entered LONG when btc_ret_24h <0  OR  SHORT when btc_ret_24h >0')
oos['dir_aligned_24h'] = (
    ((oos['direction'] == 1)  & (oos['btc_ret_24h'] >= 0)) |
    ((oos['direction'] == -1) & (oos['btc_ret_24h'] <= 0))
).astype(int)
oos['dir_error_24h'] = 1 - oos['dir_aligned_24h']

aligned   = oos[oos['dir_aligned_24h'] == 1]
misaligned= oos[oos['dir_error_24h']   == 1]

print(f'\n  Aligned (same dir as 24h BTC move):  n={len(aligned):>4}  '
      f'win={aligned["was_winner"].mean():.1%}  avgPnL={aligned["net_pnl_pct"].mean():+.4f}%  '
      f'stopRate={aligned["is_stop"].mean():.1%}')
print(f'  Misaligned (vs 24h BTC move):         n={len(misaligned):>4}  '
      f'win={misaligned["was_winner"].mean():.1%}  avgPnL={misaligned["net_pnl_pct"].mean():+.4f}%  '
      f'stopRate={misaligned["is_stop"].mean():.1%}')

# Direction error × stop
wrong_dir_stops = oos[(oos['dir_error_24h'] == 1) & (oos['is_stop'] == 1)]
right_dir_stops = oos[(oos['dir_aligned_24h'] == 1) & (oos['is_stop'] == 1)]
print(f'\n  Stops WITH direction error:   n={len(wrong_dir_stops):>4}  '
      f'({len(wrong_dir_stops)/len(oos_stops):.1%} of all stops)')
print(f'  Stops WITHOUT direction error: n={len(right_dir_stops):>4}  '
      f'({len(right_dir_stops)/len(oos_stops):.1%} of all stops)')

# ─── [3] ZERO-SIGNAL ENTRIES (THE PHANTOM ENTRIES) ───────────────────────────
print(f'\n[3] ZERO-SIGNAL (PHANTOM) ENTRIES (OOS)')
print(f'  Definition: |zE7| < 0.05 AND |zE6| < 0.05  — no velocity AND no distortion')
phantom = oos[(oos['abs_zE7'] < 0.05) & (oos['zE6'].abs() < 0.05)]
active  = oos[~((oos['abs_zE7'] < 0.05) & (oos['zE6'].abs() < 0.05))]
print(f'\n  Phantom (zero signal): n={len(phantom):>4}  '
      f'win={phantom["was_winner"].mean():.1%}  '
      f'avgPnL={phantom["net_pnl_pct"].mean():+.4f}%  '
      f'stopRate={phantom["is_stop"].mean():.1%}  '
      f'sumPnL={phantom["net_pnl_pct"].sum():+.2f}%')
print(f'  Active signal:         n={len(active):>4}  '
      f'win={active["was_winner"].mean():.1%}  '
      f'avgPnL={active["net_pnl_pct"].mean():+.4f}%  '
      f'stopRate={active["is_stop"].mean():.1%}  '
      f'sumPnL={active["net_pnl_pct"].sum():+.2f}%')

print(f'\n  Phantom entry yearly breakdown:')
for yr, g in phantom.groupby('yr'):
    print(f'    {yr}: n={len(g):>4}  win={g["was_winner"].mean():.1%}  '
          f'avgPnL={g["net_pnl_pct"].mean():+.4f}%  '
          f'stopRate={g["is_stop"].mean():.1%}  '
          f'sumPnL={g["net_pnl_pct"].sum():+.2f}%')

print(f'\n  Phantom entry direction:')
for d, g in phantom.groupby('direction'):
    dn = 'LONG' if d == 1 else 'SHORT'
    print(f'    {dn}: n={len(g):>4}  win={g["was_winner"].mean():.1%}  '
          f'avgPnL={g["net_pnl_pct"].mean():+.4f}%  '
          f'stopRate={g["is_stop"].mean():.1%}  '
          f'sumPnL={g["net_pnl_pct"].sum():+.2f}%')

# ─── [4] THE 2025 BREAKDOWN — WHAT CHANGED? ──────────────────────────────────
print(f'\n[4] 2025 REGIME BREAKDOWN (the bad year)')
y25  = oos[oos['yr'] == 2025]
y24  = oos[oos['yr'] == 2024]
y23  = oos[oos['yr'] == 2023]

cols_compare = [
    ('abs_zE7',        '|zE7| velocity magnitude'),
    ('zdG',            'zdG structural novelty'),
    ('comp',           'comp composite signal'),
    ('channel_mag',    'channel_mag overall'),
    ('btc_ret_24h',    'BTC 24h return'),
    ('btc_ret_7d',     'BTC 7d return'),
    ('btc_annvol',     'BTC ann vol'),
    ('ath_dd_at_entry','ATH DD at entry'),
    ('holding_bars',   'holding bars'),
    ('is_stop',        'stop rate'),
]
print(f'\n  {"Feature":<34} {"2023":>10} {"2024":>10} {"2025":>10}  {"2025-2024":>10}')
print(f'  {"─"*80}')
for col, label in cols_compare:
    v23 = y23[col].mean() if col in y23 else 0.0
    v24 = y24[col].mean() if col in y24 else 0.0
    v25 = y25[col].mean() if col in y25 else 0.0
    diff = v25 - v24
    marker = ' <-- DIVERGED' if abs(diff) > 0.15 * (abs(v24) + 1e-9) else ''
    print(f'  {label:<34} {v23:>10.4f} {v24:>10.4f} {v25:>10.4f}  {diff:>+10.4f}{marker}')

print(f'\n  2025 exit-type breakdown:')
for reason, g in y25.groupby('exit_reason'):
    wp = g['was_winner'].mean()
    ap = g['net_pnl_pct'].mean()
    sp = g['net_pnl_pct'].sum()
    print(f'    {reason:<18} n={len(g):>4} ({len(g)/len(y25):.1%})  '
          f'win={wp:.1%}  avgPnL={ap:+.4f}%  sumPnL={sp:+.2f}%')

print(f'\n  2025 monthly breakdown:')
print(f'  {"Month":>7}  {"N":>5}  {"Win%":>6}  {"AvgPnL%":>9}  {"SumPnL%":>9}  {"StopRate":>9}')
print(f'  {"─"*55}')
for m, g in y25.groupby('month'):
    import calendar
    mn = calendar.month_abbr[m]
    print(f'  {mn:>7}  {len(g):>5}  {g["was_winner"].mean():>5.1%}  '
          f'{g["net_pnl_pct"].mean():>+8.4f}%  '
          f'{g["net_pnl_pct"].sum():>+8.2f}%  '
          f'{g["is_stop"].mean():>8.1%}')

# ─── [5] STOP CLUSTER EVENTS — consecutive stop losses ───────────────────────
print(f'\n[5] STOP CLUSTER EVENTS (consecutive losses, OOS)')
print(f'  Looking for runs of ≥2 consecutive stops ...')
oos_sorted = oos.sort_values('entry_time').copy()
oos_sorted['stop_run'] = 0
run_id = 0; in_run = False; prev_stop = False
run_ids = []
for _, row in oos_sorted.iterrows():
    cur_stop = (row['exit_reason'] == 'stop')
    if cur_stop and prev_stop:
        run_ids.append(run_id)
    elif cur_stop and not prev_stop:
        run_id += 1
        run_ids.append(run_id)
        in_run = True
    else:
        run_ids.append(0)
        in_run = False
    prev_stop = cur_stop
oos_sorted['stop_run_id'] = run_ids

run_stops = oos_sorted[oos_sorted['stop_run_id'] > 0]
run_summary = run_stops.groupby('stop_run_id').agg(
    n_stops       = ('stop_run_id','count'),
    first_entry   = ('entry_time','min'),
    last_exit     = ('exit_time','max'),
    pnl_sum       = ('net_pnl_pct','sum'),
    yr            = ('yr','first'),
    dir_mode      = ('direction','first'),
    zE7_mean      = ('zE7','mean'),
    btc24_mean    = ('btc_ret_24h','mean'),
).sort_values('pnl_sum')

print(f'\n  Total stop-run events: {run_summary["n_stops"].gt(1).sum()}')
print(f'  (runs of ≥2 consecutive stops)')
print(f'\n  10 WORST stop-cluster events:')
hdr = f"  {'RunID':>5}  {'N':>3}  {'From':>16}  {'To':>16}  {'SumPnL%':>9}  {'Year':>5}  {'Dir':>5}  {'avgzE7':>8}  {'avgBTC24':>9}"
print(hdr); print(f'  {"─"*93}')
for rid, row in run_summary.head(10).iterrows():
    dn = 'LONG' if row['dir_mode'] == 1 else 'SHORT'
    print(f'  {int(rid):>5}  {int(row["n_stops"]):>3}  '
          f'{str(row["first_entry"])[:16]:>16}  '
          f'{str(row["last_exit"])[:16]:>16}  '
          f'{row["pnl_sum"]:>+8.2f}%  {int(row["yr"]):>5}  {dn:>5}  '
          f'{row["zE7_mean"]:>+7.4f}  {row["btc24_mean"]*100:>+8.2f}%')

# ─── [6] ENGINE vs MARKET — WHERE WAS IT CONFIDENTLY WRONG ──────────────────
print(f'\n[6] CONFIDENT MISFIRES — high-signal entries that became stops (OOS)')
print(f'  Definition: |comp| > 0.5 AND exit=stop (engine was "sure" but wrong)')
confident_wrong = oos[(oos['comp'].abs() > 0.5) & (oos['exit_reason'] == 'stop')]
confident_right = oos[(oos['comp'].abs() > 0.5) & (oos['was_winner'] == 1)]
low_signal_stop = oos[(oos['comp'].abs() <= 0.5) & (oos['exit_reason'] == 'stop')]

print(f'\n  High-signal entries (|comp|>0.5):')
print(f'    Wins:  n={len(confident_right):>4}  avgPnL={confident_right["net_pnl_pct"].mean():+.4f}%  '
      f'sumPnL={confident_right["net_pnl_pct"].sum():+.2f}%')
print(f'    Stops: n={len(confident_wrong):>4}  avgPnL={confident_wrong["net_pnl_pct"].mean():+.4f}%  '
      f'sumPnL={confident_wrong["net_pnl_pct"].sum():+.2f}%')
print(f'  Low-signal stops (|comp|<=0.5):  n={len(low_signal_stop):>4}  '
      f'sumPnL={low_signal_stop["net_pnl_pct"].sum():+.2f}%')
print(f'\n  Confident wrongs by year:')
for yr, g in confident_wrong.groupby('yr'):
    print(f'    {yr}: n={len(g):>4}  sumPnL={g["net_pnl_pct"].sum():+.2f}%  '
          f'avgBTC24={g["btc_ret_24h"].mean()*100:+.2f}%  avgzE7={g["zE7"].mean():+.4f}')

print(f'\n  Confident wrongs — channel signature:')
for col in ['zE7','zdG','zE6','zdT','comp','btc_ret_24h','btc_ret_7d','btc_annvol']:
    cw = confident_wrong[col].mean()
    cr = confident_right[col].mean()
    print(f'    {col:<20} wrong_mean={cw:>+8.4f}  right_mean={cr:>+8.4f}  diff={cw-cr:>+8.4f}')

# ─── [7] THE DEFINITIVE LIST: EVERY WRONG TRADE CATEGORIZED ──────────────────
print(f'\n[7] WRONG TRADE TAXONOMY (OOS stops, full list)')
print(f'  Categorizing each stop into why the engine was wrong ...\n')

def classify_misfire(row):
    c    = row['comp']
    e7   = row['zE7']
    dg   = row['zdG']
    e6   = row['zE6']
    r24  = row['btc_ret_24h']
    dirn = row['direction']
    hold = row['holding_bars']
    dd   = row['ath_dd_at_entry']
    absE7 = abs(e7)

    if absE7 < 0.05 and abs(e6) < 0.05:
        return 'TYPE-A: PHANTOM (no signal, both channels dead)'
    if ((dirn == 1 and r24 < -0.02) or (dirn == -1 and r24 > 0.02)):
        return 'TYPE-B: COUNTER-TREND (BTC strongly opposing direction)'
    if absE7 < 0.05 and abs(c) < 0.20:
        return 'TYPE-C: WEAK-VELOCITY (zE7≈0, low comp — entry on noise)'
    if dd > 0.10 and dirn == 1:
        return 'TYPE-D: FADING (bought into drawdown > 10% from ATH)'
    if hold > 100 and abs(c) < 0.30:
        return 'TYPE-E: SLOW-DRIFT (held >100h without strong signal)'
    if abs(c) > 0.5:
        return 'TYPE-F: CONFIDENT-WRONG (strong signal, market reversed)'
    return 'TYPE-G: OTHER (no dominant pattern)'

oos_stops_copy = oos[oos['exit_reason'] == 'stop'].copy()
oos_stops_copy['misfire_type'] = oos_stops_copy.apply(classify_misfire, axis=1)

print(f'  {"Type":<52}  {"N":>5}  {"% stops":>8}  {"sumPnL":>9}  {"avgHold":>8}')
print(f'  {"─"*85}')
for mtype, g in oos_stops_copy.groupby('misfire_type'):
    print(f'  {mtype:<52}  {len(g):>5}  {len(g)/len(oos_stops_copy):>7.1%}  '
          f'{g["net_pnl_pct"].sum():>+8.2f}%  {g["holding_bars"].mean():>7.1f}h')

print(f'\n  Misfire distribution by year:')
mf_pivot = oos_stops_copy.groupby(['yr','misfire_type']).size().unstack(fill_value=0)
print(mf_pivot.to_string())

# ─── [8] SUMMARY — ENGINE vs REALITY ─────────────────────────────────────────
print(f'\n{BAR}')
print('  WHAT THE ENGINE GOT WRONG — EXECUTIVE SUMMARY')
print(BAR)
phantom_n    = len(oos_stops_copy[oos_stops_copy['misfire_type'].str.startswith('TYPE-A')])
counter_n    = len(oos_stops_copy[oos_stops_copy['misfire_type'].str.startswith('TYPE-B')])
weak_vel_n   = len(oos_stops_copy[oos_stops_copy['misfire_type'].str.startswith('TYPE-C')])
fading_n     = len(oos_stops_copy[oos_stops_copy['misfire_type'].str.startswith('TYPE-D')])
slow_n       = len(oos_stops_copy[oos_stops_copy['misfire_type'].str.startswith('TYPE-E')])
confident_n  = len(oos_stops_copy[oos_stops_copy['misfire_type'].str.startswith('TYPE-F')])
other_n      = len(oos_stops_copy[oos_stops_copy['misfire_type'].str.startswith('TYPE-G')])
total_stops  = len(oos_stops_copy)

print(f'\n  OOS Stops: {total_stops}   OOS trades: {len(oos)}   Stop rate: {total_stops/len(oos):.1%}')
print(f'\n  MISFIRE BREAKDOWN:')
print(f'    TYPE-A PHANTOM      : {phantom_n:>4} stops ({phantom_n/total_stops:.1%}) — zE7=0 AND zE6=0, engine had no real signal')
print(f'    TYPE-B COUNTER-TREND: {counter_n:>4} stops ({counter_n/total_stops:.1%}) — entered opposite to BTC 24h momentum')
print(f'    TYPE-C WEAK-VELOCITY: {weak_vel_n:>4} stops ({weak_vel_n/total_stops:.1%}) — zE7≈0, low comp — pure noise entry')
print(f'    TYPE-D FADING       : {fading_n:>4} stops ({fading_n/total_stops:.1%}) — bought into drawdown >10% from ATH')
print(f'    TYPE-E SLOW-DRIFT   : {slow_n:>4} stops ({slow_n/total_stops:.1%}) — held 100h+ on weak signal, drifted out')
print(f'    TYPE-F CONF.WRONG   : {confident_n:>4} stops ({confident_n/total_stops:.1%}) — high signal, market hard-reversed')
print(f'    TYPE-G OTHER        : {other_n:>4} stops ({other_n/total_stops:.1%}) — miscellaneous')
print()

abc_sum = phantom_n + weak_vel_n + counter_n
print(f'  CORE ISSUE: Types A+B+C = {abc_sum} / {total_stops} stops ({abc_sum/total_stops:.1%})')
print(f'  → Engine fires on weak/zero-velocity or counter-trend — these are PREVENTABLE')
print()
print(f'  REGIME ISSUE: 2025 saw stop rate jump from '
      f'{y23["is_stop"].mean():.1%} (2023) / {y24["is_stop"].mean():.1%} (2024) → '
      f'{y25["is_stop"].mean():.1%} (2025)')
print(f'  → 2025 avg |zE7|={y25["abs_zE7"].mean():.4f} vs 2024={y24["abs_zE7"].mean():.4f} — '
      f'channels were quieter, entries weaker')
print()
print(f'  FIXABLE with 2 rules:')
print(f'    Rule 1: abs_zE7 > 0.10   → blocks TYPE-A+C (phantom/weak-velocity)')
print(f'    Rule 2: direction × btc_ret_24h > -0.01  → blocks TYPE-B (counter-trend)')
print()

# estimate impact of filters
filter1 = oos[(oos['abs_zE7'] >  0.10)]
filter12= oos[(oos['abs_zE7'] >  0.10) & 
              ~((oos['direction'] == 1) & (oos['btc_ret_24h'] < -0.01)) &
              ~((oos['direction']==-1) & (oos['btc_ret_24h'] >  0.01))]

print(f'  ESTIMATED IMPACT (on OOS trades):')
print(f'    No filter:          n={len(oos):>4}  win={oos["was_winner"].mean():.1%}  '
      f'stop_rate={oos["is_stop"].mean():.1%}  '
      f'avgPnL={oos["net_pnl_pct"].mean():+.4f}%  sumPnL={oos["net_pnl_pct"].sum():+.2f}%')
print(f'    Rule 1 (|zE7|>0.10):n={len(filter1):>4}  win={filter1["was_winner"].mean():.1%}  '
      f'stop_rate={filter1["is_stop"].mean():.1%}  '
      f'avgPnL={filter1["net_pnl_pct"].mean():+.4f}%  sumPnL={filter1["net_pnl_pct"].sum():+.2f}%')
print(f'    Rule 1+2 combined:  n={len(filter12):>4}  win={filter12["was_winner"].mean():.1%}  '
      f'stop_rate={filter12["is_stop"].mean():.1%}  '
      f'avgPnL={filter12["net_pnl_pct"].mean():+.4f}%  sumPnL={filter12["net_pnl_pct"].sum():+.2f}%')
cutback = (len(oos) - len(filter12)) / len(oos)
pnl_gain = filter12["net_pnl_pct"].sum() - oos["net_pnl_pct"].sum()
print(f'\n    Trades cut: {len(oos)-len(filter12)} ({cutback:.1%} fewer entries)')
print(f'    Net P&L change from filtering: {pnl_gain:+.2f}% sum P&L')
print(BAR)
