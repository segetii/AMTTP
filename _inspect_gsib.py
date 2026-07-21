import numpy as np, json, pandas as pd
npz = np.load(r'research\adaptive-friction\banklevel_enhanced\gsib_cache_real\gsib_real_panel.npz')
X = npz['X']
print('Shape:', X.shape)

m = json.load(open(r'research\adaptive-friction\banklevel_enhanced\gsib_cache_real\gsib_real_meta.json'))
print('N_banks:', len(m))
print('Meta keys:', list(m[0].keys()) if m else '[]')
for i, b in enumerate(m):
    name = b.get('name', b.get('bank', b.get('cert', '?')))
    print(f"  {i:2d}: {name!r:40s} | region={b.get('region','?'):6s} | country={b.get('country','?')}")
