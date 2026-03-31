"""Quick interim analysis of completed engine results."""
import numpy as np, pandas as pd
from pathlib import Path

lines = open(r'c:\amttp\posthoc_run_output.txt', encoding='utf-16').readlines()

engines = {}
cur_eng = None
for line in lines:
    line = line.strip()
    if line.startswith('== Engine:'):
        cur_eng = line.split(':')[1].strip().rstrip('=').strip()
        engines[cur_eng] = {'fused':[], 'fisher':[], 'quadsurf':[], 'expogate':[]}
    elif 'w=' in line and 'fused=' in line and cur_eng:
        import re as _re
        m = _re.search(r'w=\s*(\d+)', line)
        if not m: continue
        w = int(m.group(1))
        vals = {}
        for tok in _re.findall(r'(\w+)=([\d.]+)', line):
            try: vals[tok[0]] = float(tok[1])
            except: pass
        engines[cur_eng]['fused'].append((w, vals.get('fused', float('nan'))))
        engines[cur_eng]['fisher'].append((w, vals.get('fisher', float('nan'))))
        engines[cur_eng]['quadsurf'].append((w, vals.get('qs', float('nan'))))
        engines[cur_eng]['expogate'].append((w, vals.get('eg', float('nan'))))

ROOT = Path(r'c:\amttp'); H = 168
npz = np.load(ROOT/'data'/'ercot'/'ercot_hourly_2019_2022.npz', allow_pickle=True)
X = npz['X']; dates = pd.to_datetime(npz['dates']); y = npz['y'].astype(int)
n_weeks = len(X) // H; n_hours = n_weeks * H
y_t = y[:n_hours]
y_week = np.array([y_t[i*H:(i+1)*H].any() for i in range(n_weeks)]).astype(int)
week_dates = dates[:n_hours:H]
n_calib = int((week_dates <= pd.Timestamp('2019-06-30')).sum())

events = {
    'SummerPeak2019': pd.Timestamp('2019-08-12'),
    'COVID_Collapse': pd.Timestamp('2020-03-23'),
    'WinterStormUri': pd.Timestamp('2021-02-10'),
    'WinterStormElliott': pd.Timestamp('2022-12-22'),
}
event_weeks = {}
for name, ts in events.items():
    idx = np.where(week_dates >= ts)[0]
    event_weeks[name] = int(idx[0]) if len(idx) else None

print('EVENT WEEK INDICES:')
for name, w in event_weeks.items():
    if w is None:
        print(f'  {name}: NOT FOUND in date range')
        continue
    crisis_ws = [i for i in range(max(0,w-2), min(n_weeks,w+5)) if y_week[i]]
    print(f'  {name}: onset w={w} ({week_dates[w].date()}), crisis_weeks nearby={crisis_ws}')
print(f'  Total event-weeks in monitor: {y_week[n_calib:].sum()}')
print()

for eng_name in engines:
    done_lines = [l for l in lines if f'{eng_name} done' in l]
    is_done = len(done_lines) > 0
    status = 'COMPLETE' if is_done else 'partial'
    
    print(f'===== {eng_name} ({status}) =====')
    for var_name in ['fused', 'fisher', 'quadsurf', 'expogate']:
        data = engines[eng_name][var_name]
        if not data: continue
        weeks_arr = np.array([d[0] for d in data])
        scores_arr = np.array([d[1] for d in data])
        
        mon_mask = weeks_arr >= n_calib
        
        print(f'  -- {var_name} --')
        
        # Score dynamics around events
        for evt_name, evt_w in event_weeks.items():
            if evt_w is None: continue
            nearby = [(w, s) for w, s in zip(weeks_arr, scores_arr) 
                      if abs(w - evt_w) <= 20]
            if nearby:
                before = [(w, s) for w, s in nearby if w < evt_w]
                at_after = [(w, s) for w, s in nearby if w >= evt_w]
                b_str = f's={before[-1][1]:.4f}@w{before[-1][0]}' if before else 'N/A'
                a_str = f's={at_after[0][1]:.4f}@w{at_after[0][0]}' if at_after else 'N/A'
                print(f'    {evt_name}: pre={b_str}, at/post={a_str}')
        
        # Variability
        if mon_mask.sum() > 0:
            ms = scores_arr[mon_mask]
            print(f'    Monitor: range=[{ms.min():.4f}, {ms.max():.4f}], mean={ms.mean():.4f}, std={ms.std():.4f}')
            
            # Score at event weeks vs non-event (sampled points only)
            evt_scores = []
            norm_scores = []
            for w, s in zip(weeks_arr[mon_mask], scores_arr[mon_mask]):
                wi = int(w)
                if wi < n_weeks and y_week[wi] == 1:
                    evt_scores.append(s)
                else:
                    norm_scores.append(s)
            if evt_scores and norm_scores:
                e_mean = np.mean(evt_scores)
                n_mean = np.mean(norm_scores)
                sep = e_mean - n_mean
                direction = 'GOOD (higher during events)' if sep > 0 else 'WEAK/INVERTED'
                print(f'    Event-weeks: mean={e_mean:.4f} ({len(evt_scores)} sampled)')
                print(f'    Normal-weeks: mean={n_mean:.4f} ({len(norm_scores)} sampled)')
                print(f'    Separation: {sep:+.4f} -> {direction}')
            elif not evt_scores:
                print(f'    (no sampled event-weeks in 13-week grid)')
        print()

# Timing
for eng_name in engines:
    for l in lines:
        if f'{eng_name} done in' in l:
            print(l.strip())
