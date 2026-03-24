import sys, numpy as np, json
from pathlib import Path

CACHE = Path(r'c:\amttp\research\adaptive-friction\banklevel_enhanced\gsib_cache_real')
npz = np.load(CACHE / 'gsib_real_panel.npz')
with open(CACHE / 'gsib_real_meta.json') as f:
    meta = json.load(f)

X = npz['X']
print(f'Shape: {X.shape}  (T quarters x N banks x d features)')
print(f'Banks: {len(meta)}')
print()
for i, m in enumerate(meta):
    name = m.get('name', '?')
    btype = m.get('type', '?')
    country = m.get('country', '?')
    src = m.get('data_source', '?')
    print(f'  [{i:2d}] {name:<26}  {btype:<14}  {country:<6}  src={src}')

print()
print(f'Feature keys: {list(npz.keys())}')
print(f'X shape: {X.shape}')
print(f'X min={X.min():.3f}  max={X.max():.3f}  mean={X.mean():.3f}  nan%={(np.isnan(X).mean()*100):.1f}%')
if 'feature_names' in npz:
    print(f'Features: {npz["feature_names"]}')
print()
print('First sample (bank 0, quarter 0):', X[0, 0])
