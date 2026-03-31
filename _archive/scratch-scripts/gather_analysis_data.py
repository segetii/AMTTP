"""Gather all data from the 3 simulations for analysis document."""
import json

# ── Simulation 1: Comprehensive Operational Sweep (bench_operational.py) ──
with open('operational_model_search.json') as f:
    sim1 = json.load(f)

regions = ['Full G-SIB Panel', 'USA (FDIC)', 'Europe + UK', 'Asia (JP + CN)', 'Nigeria (WB-GFDD)']

print("=" * 90)
print("SIMULATION 1: COMPREHENSIVE OPERATIONAL SWEEP (bench_operational.py)")
print("  41 configs × 5 regions = 205 runs")
print("=" * 90)

for reg in regions:
    rdata = sim1.get(reg, {})
    configs = list(rdata.keys())
    # Collect operational configs
    ops = []
    for cfg_name, cfg_data in rdata.items():
        if isinstance(cfg_data, dict):
            channels = cfg_data.get('channels', {})
            for ch_name, ch_data in channels.items():
                if isinstance(ch_data, dict) and ch_data.get('operational', False):
                    ops.append({
                        'config': cfg_name,
                        'channel': ch_name,
                        'f1': ch_data.get('f1', 0),
                        'recall': ch_data.get('recall', 0),
                        'precision': ch_data.get('precision', 0),
                        'far': ch_data.get('far', 100),
                        'auroc_gfc': ch_data.get('auroc_gfc', 0),
                        'gfc_lead': ch_data.get('gfc_lead', ''),
                    })
    ops.sort(key=lambda x: -x['f1'])
    print(f"\n  {reg}: {len(configs)} configs tested, {len(ops)} operational")
    if ops:
        for o in ops[:5]:
            print(f"    {o['config']:30s} ({o['channel']:12s}) F1={o['f1']:5.1f}  "
                  f"R={o['recall']:5.1f}%  P={o['precision']:5.1f}%  "
                  f"FAR={o['far']:5.1f}%  GFC={o['auroc_gfc']:.3f}  Lead={o['gfc_lead']}")

# ── Simulation 2: International Banks Extended (bench_international_banks.py) ──
print("\n" + "=" * 90)
print("SIMULATION 2: INTERNATIONAL BANKS EXTENDED (bench_international_banks.py)")
print("  ReducedTensor, MDN_Tensor, QuadSurf × 5 regions")
print("=" * 90)

with open('international_bank_benchmark_extended.json') as f:
    sim2 = json.load(f)

for reg in regions:
    rdata = sim2.get(reg, {})
    configs = list(rdata.keys())
    ops = []
    for cfg_name, cfg_data in rdata.items():
        if isinstance(cfg_data, dict):
            channels = cfg_data.get('channels', {})
            for ch_name, ch_data in channels.items():
                if isinstance(ch_data, dict) and ch_data.get('operational', False):
                    ops.append({
                        'config': cfg_name,
                        'channel': ch_name,
                        'f1': ch_data.get('f1', 0),
                        'recall': ch_data.get('recall', 0),
                        'precision': ch_data.get('precision', 0),
                        'far': ch_data.get('far', 100),
                        'auroc_gfc': ch_data.get('auroc_gfc', 0),
                        'gfc_lead': ch_data.get('gfc_lead', ''),
                    })
    ops.sort(key=lambda x: -x['f1'])
    print(f"\n  {reg}: {len(configs)} configs tested, {len(ops)} operational")
    if ops:
        for o in ops[:5]:
            print(f"    {o['config']:30s} ({o['channel']:12s}) F1={o['f1']:5.1f}  "
                  f"R={o['recall']:5.1f}%  P={o['precision']:5.1f}%  "
                  f"FAR={o['far']:5.1f}%  GFC={o['auroc_gfc']:.3f}  Lead={o['gfc_lead']}")

# Also load original benchmark
with open('international_bank_benchmark.json') as f:
    sim2_orig = json.load(f)

print("\n  --- Original engines (Molecular, Gravity, Hybrid) ---")
for reg in regions:
    rdata = sim2_orig.get(reg, {})
    configs = list(rdata.keys())
    ops = []
    for cfg_name, cfg_data in rdata.items():
        if isinstance(cfg_data, dict):
            channels = cfg_data.get('channels', {})
            for ch_name, ch_data in channels.items():
                if isinstance(ch_data, dict) and ch_data.get('operational', False):
                    ops.append({
                        'config': cfg_name,
                        'channel': ch_name,
                        'f1': ch_data.get('f1', 0),
                        'recall': ch_data.get('recall', 0),
                        'precision': ch_data.get('precision', 0),
                        'far': ch_data.get('far', 100),
                        'auroc_gfc': ch_data.get('auroc_gfc', 0),
                        'gfc_lead': ch_data.get('gfc_lead', ''),
                    })
    ops.sort(key=lambda x: -x['f1'])
    print(f"\n  {reg}: {len(configs)} configs tested, {len(ops)} operational")
    if ops:
        for o in ops[:3]:
            print(f"    {o['config']:30s} ({o['channel']:12s}) F1={o['f1']:5.1f}  "
                  f"R={o['recall']:5.1f}%  P={o['precision']:5.1f}%  "
                  f"FAR={o['far']:5.1f}%  GFC={o['auroc_gfc']:.3f}  Lead={o['gfc_lead']}")


# ── Simulation 3: Betti+Morse Foundation (bench_betti_morse_foundation.py) ──
print("\n" + "=" * 90)
print("SIMULATION 3: BETTI+MORSE FOUNDATION (bench_betti_morse_foundation.py)")
print("  25 configs × 5 regions = 125 runs")
print("=" * 90)

with open('operational_betti_morse_search.json') as f:
    sim3_full = json.load(f)

with open('model_artifacts/betti_morse_foundation/operational_configs.json') as f:
    sim3_ops = json.load(f)

for reg in regions:
    rdata = sim3_full.get(reg, {})
    configs = list(rdata.keys())
    reg_ops = [o for o in sim3_ops if o['region'] == reg]
    reg_ops.sort(key=lambda x: -x['f1'])
    print(f"\n  {reg}: {len(configs)} configs tested, {len(reg_ops)} operational")
    if reg_ops:
        for o in reg_ops[:5]:
            print(f"    {o['config']:30s} ({o['channel']:12s}) F1={o['f1']:5.1f}  "
                  f"R={o['recall']:5.1f}%  P={o['precision']:5.1f}%  "
                  f"FAR={o['far']:5.1f}%  GFC={o['auroc_gfc']:.3f}  Lead={o['gfc_lead']}")

# ── Cross-simulation best-per-region ──
print("\n" + "=" * 90)
print("CROSS-SIMULATION BEST PER REGION")
print("=" * 90)

# Collect ALL operational from all 3 sims
all_ops_by_region = {r: [] for r in regions}

# Sim 1
for reg in regions:
    rdata = sim1.get(reg, {})
    for cfg_name, cfg_data in rdata.items():
        if isinstance(cfg_data, dict):
            for ch_name, ch_data in cfg_data.get('channels', {}).items():
                if isinstance(ch_data, dict) and ch_data.get('operational', False):
                    all_ops_by_region[reg].append({
                        'sim': 'Sim1-OpSweep',
                        'config': cfg_name,
                        'channel': ch_name,
                        'f1': ch_data.get('f1', 0),
                        'recall': ch_data.get('recall', 0),
                        'precision': ch_data.get('precision', 0),
                        'far': ch_data.get('far', 100),
                        'auroc_gfc': ch_data.get('auroc_gfc', 0),
                    })

# Sim 2 extended
for reg in regions:
    rdata = sim2.get(reg, {})
    for cfg_name, cfg_data in rdata.items():
        if isinstance(cfg_data, dict):
            for ch_name, ch_data in cfg_data.get('channels', {}).items():
                if isinstance(ch_data, dict) and ch_data.get('operational', False):
                    all_ops_by_region[reg].append({
                        'sim': 'Sim2-IntlBank',
                        'config': cfg_name,
                        'channel': ch_name,
                        'f1': ch_data.get('f1', 0),
                        'recall': ch_data.get('recall', 0),
                        'precision': ch_data.get('precision', 0),
                        'far': ch_data.get('far', 100),
                        'auroc_gfc': ch_data.get('auroc_gfc', 0),
                    })

# Sim 2 original
for reg in regions:
    rdata = sim2_orig.get(reg, {})
    for cfg_name, cfg_data in rdata.items():
        if isinstance(cfg_data, dict):
            for ch_name, ch_data in cfg_data.get('channels', {}).items():
                if isinstance(ch_data, dict) and ch_data.get('operational', False):
                    all_ops_by_region[reg].append({
                        'sim': 'Sim2-OrigEngine',
                        'config': cfg_name,
                        'channel': ch_name,
                        'f1': ch_data.get('f1', 0),
                        'recall': ch_data.get('recall', 0),
                        'precision': ch_data.get('precision', 0),
                        'far': ch_data.get('far', 100),
                        'auroc_gfc': ch_data.get('auroc_gfc', 0),
                    })

# Sim 3
for o in sim3_ops:
    all_ops_by_region[o['region']].append({
        'sim': 'Sim3-BettiMorse',
        'config': o['config'],
        'channel': o['channel'],
        'f1': o['f1'],
        'recall': o['recall'],
        'precision': o['prec'],
        'far': o['far'],
        'auroc_gfc': o['auroc_gfc'],
    })

for reg in regions:
    items = all_ops_by_region[reg]
    items.sort(key=lambda x: -x['f1'])
    print(f"\n  {reg}: {len(items)} total operational across all sims")
    if items:
        best = items[0]
        print(f"    BEST: [{best['sim']}] {best['config']} ({best['channel']})")
        print(f"           F1={best['f1']:.1f}  R={best['recall']:.1f}%  "
              f"P={best['precision']:.1f}%  FAR={best['far']:.1f}%  GFC={best['auroc_gfc']:.3f}")
        # Top 3 from each sim
        sims_seen = set()
        for it in items:
            if it['sim'] not in sims_seen:
                sims_seen.add(it['sim'])
                if it != best:
                    print(f"    Best from {it['sim']}: {it['config']} ({it['channel']}) "
                          f"F1={it['f1']:.1f} GFC={it['auroc_gfc']:.3f}")

# ── Method family analysis ──
print("\n" + "=" * 90)
print("METHOD FAMILY ANALYSIS (all operational configs)")
print("=" * 90)

families = {}
for reg in regions:
    for o in all_ops_by_region[reg]:
        cfg = o['config']
        if cfg.startswith('BM_'):
            fam = 'BettiMorse-' + cfg.split('_')[1]
        elif 'MDN' in cfg:
            fam = 'MDN_Tensor'
        elif 'RT' in cfg or 'ReducedTensor' in cfg:
            fam = 'ReducedTensor'
        elif 'BSDT' in cfg:
            fam = 'BSDT'
        elif 'Fused' in cfg:
            fam = 'FusedSystem'
        elif 'Morse' in cfg:
            fam = 'Morse'
        elif 'Betti' in cfg:
            fam = 'Betti'
        elif 'Molecular' in cfg or 'Gravity' in cfg or 'Hybrid' in cfg:
            fam = 'PhysicsEngine'
        elif 'SubScan' in cfg or 'SubspaceScan' in cfg:
            fam = 'SubspaceScan'
        elif 'QuadSurf' in cfg:
            fam = 'QuadSurf'
        elif 'EFlow' in cfg or 'Energy' in cfg:
            fam = 'EnergyFlow'
        else:
            fam = 'Other'
        if fam not in families:
            families[fam] = {'count': 0, 'f1s': [], 'gfcs': [], 'regions': set()}
        families[fam]['count'] += 1
        families[fam]['f1s'].append(o['f1'])
        families[fam]['gfcs'].append(o['auroc_gfc'])
        families[fam]['regions'].add(reg)

print(f"  {'Family':<25s} {'Count':>5s} {'Avg F1':>7s} {'Max F1':>7s} "
      f"{'Avg GFC':>8s} {'Max GFC':>8s} {'Regions':>7s}")
print("  " + "-" * 75)
for fam, data in sorted(families.items(), key=lambda x: -max(x[1]['f1s'])):
    avg_f1 = sum(data['f1s']) / len(data['f1s'])
    max_f1 = max(data['f1s'])
    avg_gfc = sum(data['gfcs']) / len(data['gfcs'])
    max_gfc = max(data['gfcs'])
    print(f"  {fam:<25s} {data['count']:5d} {avg_f1:7.1f} {max_f1:7.1f} "
          f"{avg_gfc:8.3f} {max_gfc:8.3f} {len(data['regions']):7d}")

# ── Full all-ops dump for doc ──
print("\n" + "=" * 90)
print("ALL OPERATIONAL CONFIGS ACROSS ALL SIMULATIONS")
print("=" * 90)

for reg in regions:
    items = all_ops_by_region[reg]
    items.sort(key=lambda x: -x['f1'])
    print(f"\n--- {reg} ({len(items)} operational) ---")
    for o in items:
        print(f"  [{o['sim']:16s}] {o['config']:30s} ({o['channel']:12s}) "
              f"F1={o['f1']:5.1f}  R={o['recall']:5.1f}%  P={o['precision']:5.1f}%  "
              f"FAR={o['far']:5.1f}%  GFC={o['auroc_gfc']:.3f}")
