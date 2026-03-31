import json
from collections import Counter

with open('model_artifacts/betti_morse_foundation/operational_configs.json') as f:
    ops = json.load(f)

region_counts = Counter(o['region'] for o in ops)
print('OPERATIONAL MODELS BY REGION:')
for reg, cnt in sorted(region_counts.items(), key=lambda x: -x[1]):
    print(f'  {reg}: {cnt} configs')
print(f'  TOTAL: {len(ops)} operational systems')
print()

configs_by_region = {}
for o in ops:
    r = o['region']
    if r not in configs_by_region:
        configs_by_region[r] = []
    configs_by_region[r].append(o)

print('BEST CONFIG PER REGION:')
for reg in ['Nigeria (WB-GFDD)', 'USA (FDIC)', 'Full G-SIB Panel',
            'Europe + UK', 'Asia (JP + CN)']:
    items = configs_by_region.get(reg, [])
    if items:
        b = items[0]
        cfg = b['config']
        ch = b['channel']
        f1 = b['f1']
        rec = b['recall']
        prec = b['prec']
        far = b['far']
        gfc = b['auroc_gfc']
        lead = b.get('gfc_lead', '?')
        print(f'  {reg}')
        print(f'    {cfg} ({ch})')
        print(f'    F1={f1:.1f}  R={rec:.1f}%  P={prec:.1f}%  '
              f'FAR={far:.1f}%  GFC={gfc:.3f}  Lead={lead}')
    else:
        print(f'  {reg}: NONE')
print()

config_regions = {}
for o in ops:
    cfg = o['config']
    if cfg not in config_regions:
        config_regions[cfg] = []
    config_regions[cfg].append((o['region'], o['f1'], o['auroc_gfc']))

print('MULTI-REGION COVERAGE (2+ regions):')
for cfg, regions in sorted(config_regions.items(), key=lambda x: -len(x[1])):
    if len(regions) >= 2:
        avg_f1 = sum(f for _, f, _ in regions) / len(regions)
        avg_gfc = sum(g for _, _, g in regions) / len(regions)
        print(f'  {cfg}: {len(regions)} regions, avg F1={avg_f1:.1f}, '
              f'avg GFC={avg_gfc:.3f}')
        for r, f, g in regions:
            print(f'    - {r}: F1={f:.1f}, GFC={g:.3f}')
