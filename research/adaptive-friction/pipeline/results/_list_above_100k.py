"""List all algorithm variants with Final equity >= $100K across v40-v46."""
import json, os
from pathlib import Path

BASE = Path(r'c:\amttp\research\adaptive-friction\pipeline\results')

files = [
    ('v40', 'v40_full_metrics/crypto_godmode_v40_full_metrics.json'),
    ('v41', 'v41_full/crypto_godmode_v41_full.json'),
    ('v42', 'v42_cb_param_sweep/crypto_godmode_v42_cb_sweep.json'),
    ('v43', 'v43_regime_cb/crypto_godmode_v43_regime_cb.json'),
    ('v44', 'v44_seg_trailstop/crypto_godmode_v44_seg_trailstop.json'),
    ('v45', 'v45_cb_window/crypto_godmode_v45_cb_window.json'),
    ('v46', 'v46_omega_adaptive/crypto_godmode_v46_omega_adaptive.json'),
]

rows = []
for ver, rel in files:
    p = BASE / rel
    if not p.exists():
        print(f'  [skip] {rel} not found')
        continue
    with open(p) as f:
        data = json.load(f)
    results = data.get('results', data) if isinstance(data, dict) else data
    for r in results:
        final = r.get('final', 0) or 0
        if final >= 100_000:
            rows.append({
                'ver':    ver,
                'name':   r.get('name', '?'),
                'final':  final,
                'maxdd':  r.get('maxdd', float('nan')),
                'calmar': r.get('calmar', float('nan')),
                'sharpe': r.get('sharpe', float('nan')),
                'cagr':   r.get('cagr', float('nan')),
                'pct_halted': r.get('pct_halted', float('nan')),
                'n_trips':    r.get('n_trips', 0),
            })

# Add v34/v35 baseline as reference
rows.append({
    'ver': 'v34', 'name': 'd025_q050_top5_cb_v34_tight (BASELINE)',
    'final': 730_056, 'maxdd': -0.35, 'calmar': 17.49,
    'sharpe': float('nan'), 'cagr': float('nan'),
    'pct_halted': float('nan'), 'n_trips': 0,
})

rows.sort(key=lambda x: -x['final'])

def fmt(v, kind):
    if v != v:
        return '   nan'
    if kind == 'pct':   return f'{v*100:>6.1f}%'
    if kind == 'pctm':  return f'{v*100:>5.1f}%'
    if kind == 'flt':   return f'{v:>7.2f}'
    return str(v)

print(f'\n{"Ver":<5} {"Algorithm":<60} {"Final":>11}  {"MaxDD":>7}  '
      f'{"Calmar":>7}  {"Sharpe":>7}  {"CAGR":>7}  {"%Halt":>6}  {"Trips":>6}')
print('-' * 130)
for r in rows:
    print(f'{r["ver"]:<5} {r["name"][:60]:<60} '
          f'${r["final"]:>10,.0f}  '
          f'{fmt(r["maxdd"],   "pct"):>7}  '
          f'{fmt(r["calmar"],  "flt"):>7}  '
          f'{fmt(r["sharpe"],  "flt"):>7}  '
          f'{fmt(r["cagr"],    "pct"):>7}  '
          f'{fmt(r["pct_halted"], "pctm"):>6}  '
          f'{r["n_trips"]:>6}')

print(f'\nTotal algorithms with Final >= 100,000: {len(rows)}')
