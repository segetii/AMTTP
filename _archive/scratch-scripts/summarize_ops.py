import json
from collections import Counter

with open('model_artifacts/operational_search/operational_configs.json') as f:
    ops = json.load(f)

region_counts = Counter(o['region'] for o in ops)
print("OPERATIONAL MODELS BY REGION:")
for reg, cnt in sorted(region_counts.items(), key=lambda x: -x[1]):
    print(f"  {reg}: {cnt} configs")
print(f"  TOTAL: {len(ops)} operational systems\n")

# Group by region
configs_by_region = {}
for o in ops:
    r = o['region']
    if r not in configs_by_region:
        configs_by_region[r] = []
    configs_by_region[r].append(o)

# Best per region
print("=" * 120)
print("BEST CONFIG PER REGION (sorted by F1 desc)")
print("=" * 120)
regions_ordered = ['Nigeria (WB-GFDD)', 'Full G-SIB Panel', 'USA (FDIC)',
                   'Asia (JP + CN)', 'Europe + UK']
for reg in regions_ordered:
    items = configs_by_region.get(reg, [])
    if items:
        best = items[0]
        cfg = best['config']
        f1 = best['f1']
        rec = best['recall']
        prec = best['prec']
        far = best['far']
        auroc = best['auroc']
        gfc = best['auroc_gfc']
        lead = best.get('gfc_lead', '?')
        alarm = best.get('first_alarm', '?')
        ch = best.get('channel', '?')
        print(f"  {reg}")
        print(f"    Best: {cfg} ({ch})")
        print(f"    F1={f1:.1f}  Recall={rec:.1f}%  Precision={prec:.1f}%  FAR={far:.1f}%")
        print(f"    AUROC={auroc:.3f}  GFC-AUC={gfc:.3f}  Lead={lead}  Alarm={alarm}")
        print()
    else:
        print(f"  {reg}: NO OPERATIONAL CONFIGS\n")

# All unique config names that are operational somewhere
print("=" * 120)
print("UNIQUE CONFIGS THAT ARE OPERATIONAL IN AT LEAST ONE REGION")
print("=" * 120)
config_regions = {}
for o in ops:
    cfg = o['config']
    if cfg not in config_regions:
        config_regions[cfg] = []
    config_regions[cfg].append((o['region'], o['f1'], o['auroc_gfc']))

for cfg, regions in sorted(config_regions.items(), key=lambda x: -len(x[1])):
    region_str = ", ".join(f"{r}(F1={f:.0f})" for r, f, g in regions)
    print(f"  {cfg}: {len(regions)} regions - {region_str}")

# Count how many regions each config covers
print(f"\n{'=' * 120}")
print("MULTI-REGION COVERAGE (configs operational in 2+ regions)")
print("=" * 120)
for cfg, regions in sorted(config_regions.items(), key=lambda x: -len(x[1])):
    if len(regions) >= 2:
        avg_f1 = sum(f for _, f, _ in regions) / len(regions)
        avg_gfc = sum(g for _, _, g in regions) / len(regions)
        region_names = [r for r, _, _ in regions]
        print(f"  {cfg}: {len(regions)} regions, avg F1={avg_f1:.1f}, avg GFC={avg_gfc:.3f}")
        for r, f, g in regions:
            print(f"    - {r}: F1={f:.1f}, GFC={g:.3f}")
