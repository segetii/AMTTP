import numpy as np
from pathlib import Path

cyber = Path(r'c:\amttp\data\external_validation\cyber')
for f in sorted(cyber.glob('*.npz')):
    d = np.load(f, allow_pickle=True)
    y = d['y']
    X = d.get('X10', d.get('X_full'))
    at = d.get('attack_types', d.get('attack_categories', None))
    n_types = len(set(at)) - 1 if at is not None else '?'
    print(f"{f.stem:<25} {len(y):>8,} samples  {int(y.sum()):>7,} attacks ({100*y.mean():5.1f}%)  {X.shape[1]:>3}D  {n_types} types")
    # check keys
    print(f"  keys: {list(d.keys())}")

kdd = Path(r'c:\amttp\data\external_validation\kddcup99_cyber.npz')
if kdd.exists():
    d = np.load(kdd, allow_pickle=True)
    y = d['y']
    print(f"{'kddcup99 (legacy)':<25} {len(y):>8,} samples  {int(y.sum()):>7,} attacks ({100*y.mean():5.1f}%)  {d['X10'].shape[1]:>3}D")
